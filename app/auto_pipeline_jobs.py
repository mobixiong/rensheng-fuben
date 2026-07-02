import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .image_adapter import ImageConfig, generate_one_story_image
from .image_jobs import DEFAULT_IMAGE_JOB_CONCURRENCY, cancel_image_job, create_image_job, get_image_job
from .job_store import list_jobs, make_job_id, normalize_project_id, now_ms, public_job, read_job, save_job
from .llm_adapter import (
    LLMConfig,
    generate_story_from_copy,
    generate_text,
    generate_theme_ideas,
    generate_topic_plan,
    improve_image_prompt,
)
from .paths import ROOT
from .project_service import project_dir, read_project_state, safe_project_id, write_project_files
from .render_service import create_render_job, get_render_job


AUTO_ACTIVE_STATUSES = {"queued", "running", "waiting_child_job"}
STEP_KEYS = [
    ("theme_ideas", "生成选题方向"),
    ("select_idea", "选择方向"),
    ("theme", "生成主题"),
    ("copy", "生成口播"),
    ("storyboard", "拆分镜"),
    ("improve_prompts", "优化图片提示词"),
    ("images", "生成图片"),
    ("cover", "选择封面"),
    ("render", "渲染视频"),
]
_runner = ThreadPoolExecutor(max_workers=2)
_lock = threading.RLock()
_cancelled: set[str] = set()
_runtime_secrets: dict[str, dict[str, Any]] = {}
IMAGE_REPAIR_BURST_SIZE = 9


class AutoPipelineError(RuntimeError):
    pass


class AutoPipelineCancelled(AutoPipelineError):
    pass


def _default_copy_prompt(preset: str) -> str:
    if preset == "xianxia":
        path = ROOT / "prompts" / "copy_xianxia.md"
    else:
        path = ROOT / "prompt.txt"
    return path.read_text(encoding="utf-8")


def _default_copy_to_story_prompt() -> str:
    return (ROOT / "prompts" / "copy_to_story.md").read_text(encoding="utf-8")


def _default_image_prompt() -> str:
    return (ROOT / "prompts" / "image_style.md").read_text(encoding="utf-8")


def _default_improve_prompt() -> str:
    return (ROOT / "prompts" / "image_prompt_improve.md").read_text(encoding="utf-8")


def _step_template() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "name": name,
            "status": "pending",
            "attempt": 0,
            "error": "",
            "detail": "",
            "updated_at": now_ms(),
        }
        for key, name in STEP_KEYS
    ]


def _step(job: dict[str, Any], key: str) -> dict[str, Any]:
    for item in job.get("steps", []):
        if item.get("key") == key:
            return item
    raise AutoPipelineError(f"Unknown step: {key}")


def _set_step(job: dict[str, Any], key: str, status: str, *, detail: str = "", error: str = "", progress: float | None = None) -> dict[str, Any]:
    with _lock:
        if _is_cancelled(job):
            latest = _latest_job(job) or job
            return _mark_cancelled(latest)
        step = _step(job, key)
        if step.get("status") != status and status == "running":
            step["attempt"] = int(step.get("attempt") or 0) + 1
        step["status"] = status
        step["detail"] = detail
        step["error"] = error
        step["updated_at"] = now_ms()
        job["current_step"] = key
        job["detail"] = detail or step.get("name") or key
        if progress is not None:
            job["progress"] = max(0, min(1, float(progress)))
        return _save(job)


def _save(job: dict[str, Any]) -> dict[str, Any]:
    job["updated_at"] = now_ms()
    return save_job(job)


def _read(project_id: str, job_id: str) -> dict[str, Any]:
    return read_job(safe_project_id(project_id), job_id)


def _latest_job(job: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return _read(str(job.get("project_id") or ""), str(job.get("job_id") or ""))
    except Exception:
        return None


def _is_cancelled(job: dict[str, Any]) -> bool:
    job_id = str(job.get("job_id") or "")
    if job_id in _cancelled or job.get("status") == "cancelled":
        return True
    latest = _latest_job(job)
    return bool(latest and latest.get("status") == "cancelled")


def _check_cancelled(job: dict[str, Any]) -> None:
    if _is_cancelled(job):
        raise AutoPipelineCancelled("任务已取消")


def _mark_cancelled(job: dict[str, Any]) -> dict[str, Any]:
    job["status"] = "cancelled"
    job["detail"] = "任务已取消"
    for step in job.get("steps", []):
        if step.get("status") in {"pending", "running", "waiting"}:
            step["status"] = "cancelled"
            step["updated_at"] = now_ms()
    return _save(job)


def _public(job: dict[str, Any]) -> dict[str, Any]:
    return public_job(job)


def _secrets(job: dict[str, Any]) -> dict[str, Any]:
    return _runtime_secrets.get(str(job.get("job_id")), {})


def _with_runtime_keys(job: dict[str, Any], section: str) -> dict[str, Any]:
    data = dict((job.get("input") or {}).get(section) or {})
    runtime = _secrets(job).get(section)
    if isinstance(runtime, dict):
        data.update({key: value for key, value in runtime.items() if value})
    return data


def _llm_config(job: dict[str, Any], temperature: float = 0.8) -> LLMConfig:
    data = _with_runtime_keys(job, "text_config")
    data.setdefault("temperature", temperature)
    return LLMConfig.from_payload(data)


def _image_config(job: dict[str, Any]) -> ImageConfig:
    data = _with_runtime_keys(job, "image_config")
    data["size"] = (job.get("input") or {}).get("image_size") or data.get("size") or "9:16"
    return ImageConfig.from_payload(data)


def _state_or_default(job: dict[str, Any]) -> dict[str, Any]:
    project_id = str(job["project_id"])
    try:
        return read_project_state(project_id)
    except FileNotFoundError:
        return {
            "version": 1,
            "project_id": project_id,
            "_lock_project_id": True,
            "topic": "",
            "theme_brief": "",
            "theme_intro": "",
            "copy_text": "",
            "story": {"title": "", "style_preset": "", "shots": [], "project_id": project_id},
            "result_text": "{}",
            "copy_prompt_preset": (job.get("input") or {}).get("copy_preset") or "reality",
            "image_size": (job.get("input") or {}).get("image_size") or "9:16",
            "intro_template": (job.get("input") or {}).get("intro_template") or "none",
            "intro_image_seconds": (job.get("input") or {}).get("intro_image_seconds") or "0.3",
            "tts_preset": (job.get("input") or {}).get("tts_preset") or "custom",
            "bgm_id": (job.get("input") or {}).get("bgm_id") or "none",
            "intro_sfx_id": (job.get("input") or {}).get("intro_sfx_id") or "default",
        }


def _write_state(job: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    state["project_id"] = job["project_id"]
    state["_lock_project_id"] = True
    selected_idea = job.get("artifacts", {}).get("selected_idea") or {}
    result = job.get("result") or {}
    if not str(state.get("topic") or "").strip() and result.get("topic"):
        state["topic"] = result.get("topic") or ""
    if not str(state.get("theme_intro") or "").strip() and result.get("theme_intro"):
        state["theme_intro"] = result.get("theme_intro") or ""
    if not str(state.get("theme_brief") or "").strip():
        state["theme_brief"] = selected_idea.get("direction") or selected_idea.get("title") or (job.get("input") or {}).get("brief") or ""
    if (job.get("input") or {}).get("reference_collection_id"):
        state["reference_collection_id"] = (job.get("input") or {}).get("reference_collection_id") or ""
        state["auto_reference_enabled"] = bool((job.get("input") or {}).get("auto_reference_enabled"))
    payload = write_project_files(state, set_active=False)
    job["result"]["project_url"] = payload.get("project_url") or f"/workspace/projects/{job['project_id']}"
    return payload


def _story_has_valid_shots(story: Any) -> bool:
    return (
        isinstance(story, dict)
        and isinstance(story.get("shots"), list)
        and bool(story["shots"])
        and all(isinstance(shot, dict) and str(shot.get("voiceover") or "").strip() for shot in story["shots"])
    )


def _shot_has_image(shot: Any) -> bool:
    return isinstance(shot, dict) and bool(shot.get("image_url") or shot.get("image_path"))


def _image_failure_message(job: dict[str, Any], shots: list[Any], missing_indexes: list[int]) -> str:
    image_job = (job.get("artifacts") or {}).get("image_job") or {}
    items = image_job.get("items") if isinstance(image_job, dict) else []
    failed_by_index = {
        int(item.get("shot_index")) + 1: item
        for item in items
        if isinstance(item, dict)
        and item.get("shot_index") is not None
        and item.get("status") == "failed"
    }
    details: list[str] = []
    for index in missing_indexes[:8]:
        item = failed_by_index.get(index) or {}
        shot = shots[index - 1] if 0 <= index - 1 < len(shots) and isinstance(shots[index - 1], dict) else {}
        message = str(shot.get("_image_error") or item.get("error") or "").strip().splitlines()[0:1]
        category = str(shot.get("_image_error_category") or item.get("error_category") or "").strip()
        reason = message[0] if message else category
        if reason:
            if len(reason) > 90:
                reason = reason[:87] + "..."
            details.append(f"第 {index} 个（{reason}）")
        else:
            details.append(f"第 {index} 个")
    if len(missing_indexes) > 8:
        details.append(f"另有 {len(missing_indexes) - 8} 个")
    return "、".join(details)


def _missing_image_indexes(shots: list[Any]) -> list[int]:
    return [
        index
        for index, shot in enumerate(shots)
        if not _shot_has_image(shot)
    ]


def _clear_image_failure(shot: dict[str, Any]) -> None:
    for key in (
        "_image_error",
        "_image_error_category",
        "_image_error_code",
        "_image_status_started_at",
        "_image_status_updated_at",
        "_image_job",
        "_image_attempt",
    ):
        shot.pop(key, None)


def _mark_repair_failure(job: dict[str, Any], shot_index: int, errors: list[str], stage: str) -> None:
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list) or shot_index < 0 or shot_index >= len(shots):
        return
    shot = shots[shot_index]
    if not isinstance(shot, dict):
        return
    message = "；".join(error for error in errors if error)[:1000]
    shot["_image_status"] = "error"
    shot["_image_error"] = message or "自动补救生图失败"
    shot["_image_error_category"] = "auto_repair_failed"
    shot["_image_error_code"] = stage
    shot["_image_repair_stage"] = stage
    shot["_image_repaired_at"] = now_ms()
    story["project_id"] = job["project_id"]
    state["story"] = story
    _write_state(job, state)


def _apply_repair_success(job: dict[str, Any], shot_index: int, result_story: dict[str, Any], stage: str) -> str:
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    source_shots = result_story.get("shots") if isinstance(result_story, dict) else []
    if not isinstance(shots, list) or not isinstance(source_shots, list):
        raise AutoPipelineError("自动补救生图成功后写回失败：分镜结构无效")
    if shot_index < 0 or shot_index >= len(shots) or shot_index >= len(source_shots):
        raise AutoPipelineError("自动补救生图成功后写回失败：镜头索引越界")
    source_shot = source_shots[shot_index]
    target_shot = shots[shot_index]
    if not isinstance(source_shot, dict) or not isinstance(target_shot, dict):
        raise AutoPipelineError("自动补救生图成功后写回失败：镜头数据无效")
    for key in (
        "image_path",
        "image_url",
        "resolved_image_prompt",
        "image_size",
        "reference_collection_id",
        "reference_mode",
        "primary_reference_asset_id",
        "primary_reference_asset",
        "_reference_selection",
    ):
        if source_shot.get(key):
            target_shot[key] = source_shot[key]
    target_shot["_image_status"] = "done"
    target_shot["_image_version"] = now_ms()
    target_shot["_image_repair_stage"] = stage
    target_shot["_image_repaired_at"] = now_ms()
    _clear_image_failure(target_shot)
    story["project_id"] = job["project_id"]
    state["story"] = story
    payload = _write_state(job, state)
    payload_shots = ((payload.get("story") or {}).get("shots") or [])
    if 0 <= shot_index < len(payload_shots) and isinstance(payload_shots[shot_index], dict):
        return str(payload_shots[shot_index].get("image_url") or "")
    return str(target_shot.get("image_url") or "")


def _repair_burst_once(job: dict[str, Any], shot_index: int, stage: str) -> tuple[bool, list[str]]:
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list) or shot_index < 0 or shot_index >= len(shots):
        raise AutoPipelineError("缺少分镜，无法自动补救图片")
    if _shot_has_image(shots[shot_index]):
        return True, []

    cfg = _image_config(job)
    fixed_prompt = (job.get("input") or {}).get("image_prompt") or _default_image_prompt()
    burst_id = f"{str(job.get('job_id') or 'auto')[-8:]}_{stage}_{now_ms()}"
    successes: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=IMAGE_REPAIR_BURST_SIZE) as pool:
        futures = [
            pool.submit(
                generate_one_story_image,
                story,
                shot_index,
                cfg,
                fixed_prompt,
                filename_suffix=f"_{burst_id}_{attempt:02d}",
            )
            for attempt in range(1, IMAGE_REPAIR_BURST_SIZE + 1)
        ]
        for future in as_completed(futures):
            _check_cancelled(job)
            try:
                successes.append(future.result())
            except Exception as exc:
                errors.append(str(exc).splitlines()[0][:240])
    if successes:
        _apply_repair_success(job, shot_index, random.choice(successes), stage)
        return True, errors
    _mark_repair_failure(job, shot_index, errors, stage)
    return False, errors


def _optimize_failed_image_prompt(job: dict[str, Any], shot_index: int) -> None:
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list) or shot_index < 0 or shot_index >= len(shots):
        raise AutoPipelineError("缺少分镜，无法优化失败镜头图片提示词")
    prompt = (job.get("input") or {}).get("improve_image_prompt") or _default_improve_prompt()
    data = improve_image_prompt(story, shot_index, _llm_config(job, 0.4), prompt)
    next_prompt = str(data.get("image_prompt") or "").strip()
    if not next_prompt:
        raise AutoPipelineError(f"第 {shot_index + 1} 个镜头自动优化图片提示词失败：返回为空")
    shot = shots[shot_index]
    shot["image_prompt"] = next_prompt
    shot["_image_prompt_status"] = "optimized_after_failure"
    shot["_image_prompt_auto_optimized_at"] = now_ms()
    shot["_image_prompt_message"] = "首次 9 连抽失败后自动优化"
    _clear_image_failure(shot)
    story["project_id"] = job["project_id"]
    state["story"] = story
    _write_state(job, state)


def _repair_missing_images(job: dict[str, Any], missing_indexes: list[int], total: int) -> dict[str, Any]:
    failed_indexes: list[int] = []
    for position, shot_index in enumerate(missing_indexes, 1):
        _check_cancelled(job)
        job = _set_step(
            job,
            "images",
            "waiting",
            detail=f"第 {shot_index + 1} 个镜头失败，正在自动补抽 9 张（{position}/{len(missing_indexes)}）",
            progress=0.78 + 0.04 * (position - 1) / max(len(missing_indexes), 1),
        )
        ok, _errors = _repair_burst_once(job, shot_index, "retry9")
        if ok:
            continue
        _check_cancelled(job)
        job = _set_step(
            job,
            "images",
            "waiting",
            detail=f"第 {shot_index + 1} 个镜头 9 连抽失败，正在优化提示词后再抽 9 张",
            progress=0.82 + 0.03 * (position - 1) / max(len(missing_indexes), 1),
        )
        try:
            _optimize_failed_image_prompt(job, shot_index)
        except Exception as exc:
            _mark_repair_failure(job, shot_index, [str(exc)], "optimize_prompt")
            failed_indexes.append(shot_index)
            continue
        _check_cancelled(job)
        ok, _errors = _repair_burst_once(job, shot_index, "optimized9")
        if not ok:
            failed_indexes.append(shot_index)
    if failed_indexes:
        state = _state_or_default(job)
        shots = ((state.get("story") or {}).get("shots") or [])
        failure_detail = _image_failure_message(job, shots, [index + 1 for index in failed_indexes]) if isinstance(shots, list) else ""
        suffix = f"失败镜头：{failure_detail}" if failure_detail else f"失败镜头：{', '.join(str(index + 1) for index in failed_indexes)}"
        success = total - len(failed_indexes)
        raise AutoPipelineError(f"图片自动补救后仍未完成：成功 {success}/{total}，失败 {len(failed_indexes)}。{suffix}")
    return _latest_job(job) or job


def _run_theme_ideas(job: dict[str, Any]) -> dict[str, Any]:
    if job["artifacts"].get("theme_ideas"):
        return _set_step(job, "theme_ideas", "skipped", detail="已有候选方向", progress=0.1)
    _set_step(job, "theme_ideas", "running", detail="正在生成候选方向", progress=0.05)
    data = generate_theme_ideas(
        str((job.get("input") or {}).get("brief") or ""),
        _llm_config(job, 0.8),
        (job.get("input") or {}).get("theme_idea_prompt") or None,
        count=6,
    )
    _check_cancelled(job)
    ideas = data.get("ideas") or []
    if not ideas:
        raise AutoPipelineError("AI 没有返回候选方向")
    job["artifacts"]["theme_ideas"] = ideas
    return _set_step(job, "theme_ideas", "done", detail=f"生成 {len(ideas)} 条候选方向", progress=0.12)


def _run_select_idea(job: dict[str, Any]) -> dict[str, Any]:
    if job["artifacts"].get("selected_idea"):
        return _set_step(job, "select_idea", "skipped", detail="已有选中方向", progress=0.16)
    _set_step(job, "select_idea", "running", detail="自动选择候选方向", progress=0.14)
    ideas = job["artifacts"].get("theme_ideas") or []
    if not ideas:
        raise AutoPipelineError("缺少候选方向")
    selected = ideas[0]
    job["artifacts"]["selected_idea"] = selected
    state = _state_or_default(job)
    state["theme_brief"] = selected.get("direction") or selected.get("title") or ""
    _write_state(job, state)
    return _set_step(job, "select_idea", "done", detail="已自动采用第 1 条方向", progress=0.18)


def _run_theme(job: dict[str, Any]) -> dict[str, Any]:
    state = _state_or_default(job)
    if str(state.get("topic") or "").strip() and str(state.get("theme_intro") or "").strip():
        job["result"]["topic"] = state.get("topic") or ""
        job["result"]["theme_intro"] = state.get("theme_intro") or ""
        return _set_step(job, "theme", "skipped", detail="已有主题", progress=0.25)
    _set_step(job, "theme", "running", detail="正在生成主题和主题介绍", progress=0.2)
    brief = str(state.get("theme_brief") or (job.get("input") or {}).get("brief") or "").strip()
    if not brief:
        selected = job["artifacts"].get("selected_idea") or {}
        brief = str(selected.get("direction") or selected.get("title") or "")
    data = generate_topic_plan(brief or "请自动生成一个适合人生副本短视频的方向", _llm_config(job, 0.7), None)
    _check_cancelled(job)
    state["topic"] = data["topic"]
    state["theme_intro"] = data["intro"]
    job["result"]["topic"] = data["topic"]
    job["result"]["theme_intro"] = data["intro"]
    _write_state(job, state)
    return _set_step(job, "theme", "done", detail="主题已生成", progress=0.28)


def _run_copy(job: dict[str, Any]) -> dict[str, Any]:
    state = _state_or_default(job)
    if str(state.get("copy_text") or "").strip():
        return _set_step(job, "copy", "skipped", detail="已有口播文案", progress=0.38)
    _set_step(job, "copy", "running", detail="正在生成口播文案", progress=0.32)
    preset = str((job.get("input") or {}).get("copy_preset") or "reality")
    prompt = (job.get("input") or {}).get("copy_prompt") or _default_copy_prompt(preset)
    text = generate_text(str(state.get("topic") or ""), _llm_config(job, 0.8), prompt, str(state.get("theme_intro") or ""))
    _check_cancelled(job)
    if len(text.strip()) < 20:
        raise AutoPipelineError("口播文案过短或为空")
    state["copy_text"] = text
    state["copy_prompt_preset"] = preset
    state["copy_prompt"] = prompt
    _write_state(job, state)
    return _set_step(job, "copy", "done", detail="口播文案已生成", progress=0.4)


def _run_storyboard(job: dict[str, Any]) -> dict[str, Any]:
    state = _state_or_default(job)
    story = state.get("story")
    if _story_has_valid_shots(story):
        return _set_step(job, "storyboard", "skipped", detail="已有分镜", progress=0.5)
    _set_step(job, "storyboard", "running", detail="正在拆分镜", progress=0.44)
    prompt = (job.get("input") or {}).get("copy_to_story_prompt") or _default_copy_to_story_prompt()
    story = generate_story_from_copy(
        str(state.get("topic") or ""),
        str(state.get("copy_text") or ""),
        _llm_config(job, 0.5),
        prompt,
        str(state.get("theme_intro") or ""),
    )
    _check_cancelled(job)
    if not _story_has_valid_shots(story):
        raise AutoPipelineError("分镜结果缺少有效 shots")
    image_size = (job.get("input") or {}).get("image_size") or "9:16"
    story["project_id"] = job["project_id"]
    story["image_size"] = image_size
    for shot in story["shots"]:
        shot.setdefault("image_size", image_size)
        if not str(shot.get("image_prompt") or "").strip():
            shot["image_prompt"] = str(shot.get("visual") or shot.get("voiceover") or "").strip()
    state["story"] = story
    state["story_json"] = json.dumps(story, ensure_ascii=False, indent=2)
    state["copy_to_story_prompt"] = prompt
    state["image_size"] = image_size
    _write_state(job, state)
    return _set_step(job, "storyboard", "done", detail=f"分镜已生成：{len(story['shots'])} 个镜头", progress=0.52)


def _run_improve_prompts(job: dict[str, Any]) -> dict[str, Any]:
    if not (job.get("input") or {}).get("auto_optimize_image_prompts", True):
        return _set_step(job, "improve_prompts", "skipped", detail="已关闭自动优化", progress=0.6)
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list) or not shots:
        raise AutoPipelineError("缺少分镜，无法优化图片提示词")
    pending = [
        index for index, shot in enumerate(shots)
        if isinstance(shot, dict) and not shot.get("_image_prompt_auto_optimized_at")
    ]
    if not pending:
        return _set_step(job, "improve_prompts", "skipped", detail="图片提示词已优化", progress=0.62)
    _set_step(job, "improve_prompts", "running", detail=f"正在优化图片提示词 0/{len(pending)}", progress=0.54)
    prompt = (job.get("input") or {}).get("improve_image_prompt") or _default_improve_prompt()
    for position, index in enumerate(pending, 1):
        _check_cancelled(job)
        try:
            data = improve_image_prompt(story, index, _llm_config(job, 0.4), prompt)
            shots[index]["image_prompt"] = data.get("image_prompt") or shots[index].get("image_prompt") or ""
            shots[index]["_image_prompt_status"] = "optimized"
            shots[index]["_image_prompt_auto_optimized_at"] = now_ms()
            shots[index].pop("_image_prompt_message", None)
        except Exception as exc:
            shots[index]["_image_prompt_status"] = "error"
            shots[index]["_image_prompt_message"] = str(exc)
        _check_cancelled(job)
        state["story"] = story
        _write_state(job, state)
        job = _set_step(job, "improve_prompts", "running", detail=f"正在优化图片提示词 {position}/{len(pending)}", progress=0.54 + 0.08 * position / max(len(pending), 1))
    return _set_step(job, "improve_prompts", "done", detail="图片提示词优化完成", progress=0.64)


def _wait_image_job(job: dict[str, Any]) -> dict[str, Any]:
    project_id = str(job["project_id"])
    image_job_id = str(job["artifacts"].get("image_job_id") or "")
    if not image_job_id:
        return job
    while True:
        _check_cancelled(job)
        image_job = get_image_job(project_id, image_job_id)
        total = int(image_job.get("total") or 0)
        done = int(image_job.get("done") or 0)
        failed = int(image_job.get("failed") or 0)
        job["artifacts"]["image_job"] = image_job
        job = _set_step(job, "images", "waiting", detail=f"图片生成 {done}/{total}，失败 {failed}", progress=0.66 + 0.2 * (done + failed) / max(total, 1))
        if image_job.get("status") in {"done", "failed", "cancelled"}:
            return job
        time.sleep(2)


def _run_images(job: dict[str, Any]) -> dict[str, Any]:
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list) or not shots:
        raise AutoPipelineError("缺少分镜，无法生成图片")
    if all(_shot_has_image(shot) for shot in shots):
        return _set_step(job, "images", "skipped", detail="图片已全部存在", progress=0.86)
    if not job["artifacts"].get("image_job_id"):
        _set_step(job, "images", "running", detail="正在创建图片任务", progress=0.66)
        story["project_id"] = job["project_id"]
        state["story"] = story
        _write_state(job, state)
        image_job = create_image_job(
            story,
            _image_config(job),
            fixed_prompt=(job.get("input") or {}).get("image_prompt") or _default_image_prompt(),
            mode="auto_pipeline",
            concurrency=int((job.get("input") or {}).get("image_concurrency") or DEFAULT_IMAGE_JOB_CONCURRENCY),
            project_id=str(job["project_id"]),
            reference_collection_id=(job.get("input") or {}).get("reference_collection_id") or "",
            auto_reference_enabled=bool((job.get("input") or {}).get("auto_reference_enabled")),
            reference_llm_cfg=_llm_config(job, 0),
        )
        job["artifacts"]["image_job_id"] = image_job["job_id"]
        job["status"] = "waiting_child_job"
        _save(job)
    job = _wait_image_job(job)
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    total = len(shots) if isinstance(shots, list) else 0
    success = sum(1 for shot in shots if _shot_has_image(shot)) if isinstance(shots, list) else 0
    missing_indexes = _missing_image_indexes(shots) if isinstance(shots, list) else []
    if missing_indexes:
        job = _repair_missing_images(job, missing_indexes, total)
        state = _state_or_default(job)
        story = state.get("story") or {}
        shots = story.get("shots") if isinstance(story, dict) else []
        success = sum(1 for shot in shots if _shot_has_image(shot)) if isinstance(shots, list) else 0
        missing_indexes = _missing_image_indexes(shots) if isinstance(shots, list) else []
    if missing_indexes:
        failure_detail = _image_failure_message(job, shots, [index + 1 for index in missing_indexes]) if isinstance(shots, list) else ""
        suffix = f"失败镜头：{failure_detail}" if failure_detail else f"失败镜头：{', '.join(str(index + 1) for index in missing_indexes)}"
        raise AutoPipelineError(f"图片生成未完成：成功 {success}/{total}，失败 {len(missing_indexes)}。{suffix}")
    job["status"] = "running"
    return _set_step(job, "images", "done", detail=f"图片生成完成：成功 {success}/{total}", progress=0.86)


def _run_cover(job: dict[str, Any]) -> dict[str, Any]:
    state = _state_or_default(job)
    story = state.get("story") or {}
    if isinstance(story.get("cover"), dict) and story["cover"].get("image_url"):
        return _set_step(job, "cover", "skipped", detail="已有封面", progress=0.89)
    _set_step(job, "cover", "running", detail="正在选择封面", progress=0.87)
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list):
        raise AutoPipelineError("缺少分镜，无法选择封面")
    for index, shot in enumerate(shots):
        if _shot_has_image(shot):
            story["cover"] = {
                "title": state.get("topic") or story.get("title") or "",
                "source_shot_index": index,
                "image_prompt": str(shot.get("image_prompt") or ""),
                "image_path": shot.get("image_path") or "",
                "image_url": shot.get("image_url") or "",
                "image_size": shot.get("image_size") or story.get("image_size") or (job.get("input") or {}).get("image_size") or "9:16",
                "_cover_status": "selected",
                "_cover_version": now_ms(),
            }
            state["story"] = story
            _write_state(job, state)
            return _set_step(job, "cover", "done", detail=f"已选择第 {index + 1} 张图为封面", progress=0.9)
    raise AutoPipelineError("没有可用图片作为封面")


def _render_payload(job: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    input_data = job.get("input") or {}
    tts_config = _with_runtime_keys(job, "tts_config")
    return {
        "story": state.get("story") or {},
        "voice": input_data.get("voice") or "zh-CN-YunxiNeural",
        "rate": input_data.get("rate") or "+12%",
        "tts_preset": input_data.get("tts_preset") or "custom",
        "tts_provider": tts_config.get("provider") or input_data.get("tts_provider") or "edge",
        "tts_base_url": tts_config.get("base_url") or "",
        "tts_api_key": tts_config.get("api_key") or "",
        "tts_group_id": tts_config.get("group_id") or "",
        "tts_model": tts_config.get("model") or "speech-2.8-hd",
        "tts_voice_id": tts_config.get("voice_id") or input_data.get("tts_voice_id") or "male-qn-qingse",
        "tts_speed": input_data.get("tts_speed") or 1,
        "tts_emotion": input_data.get("tts_emotion") or "",
        "tts_language_boost": input_data.get("tts_language_boost") or "Chinese",
        "project_id": str(job["project_id"]),
        "cleanup_intermediate": True,
        "intro_template": input_data.get("intro_template") or "none",
        "intro_image_seconds": input_data.get("intro_image_seconds") or 0.3,
        "image_size": input_data.get("image_size") or "9:16",
        "bgm_id": input_data.get("bgm_id") or "none",
        "intro_sfx_id": input_data.get("intro_sfx_id") or "default",
    }


def _wait_render_job(job: dict[str, Any]) -> dict[str, Any]:
    render_job_id = str(job["artifacts"].get("render_job_id") or "")
    if not render_job_id:
        return job
    while True:
        _check_cancelled(job)
        render_job = get_render_job(render_job_id, str(job["project_id"]))
        if not render_job:
            raise AutoPipelineError("渲染任务丢失")
        job["artifacts"]["render_job"] = render_job
        progress = float(render_job.get("progress") or 0)
        job = _set_step(job, "render", "waiting", detail=str(render_job.get("detail") or render_job.get("stage") or "渲染中"), progress=0.9 + 0.09 * progress)
        if render_job.get("status") == "complete":
            result = render_job.get("result") or {}
            job["result"]["video_url"] = result.get("video") or ""
            state = _state_or_default(job)
            state["rendered_video"] = job["result"]["video_url"]
            state["result_text"] = json.dumps(result, ensure_ascii=False, indent=2)
            _write_state(job, state)
            return job
        if render_job.get("status") == "error":
            raise AutoPipelineError(str(render_job.get("error") or "渲染失败"))
        time.sleep(2)


def _run_render(job: dict[str, Any]) -> dict[str, Any]:
    if not (job.get("input") or {}).get("render_after_images", True):
        return _set_step(job, "render", "skipped", detail="已关闭自动渲染", progress=1)
    state = _state_or_default(job)
    final_path = project_dir(str(job["project_id"])) / "final.mp4"
    if final_path.exists() and final_path.stat().st_size > 0:
        job["result"]["video_url"] = f"/workspace/projects/{job['project_id']}/final.mp4"
        state["rendered_video"] = job["result"]["video_url"]
        _write_state(job, state)
        return _set_step(job, "render", "skipped", detail="成片已存在", progress=1)
    if not job["artifacts"].get("render_job_id"):
        _set_step(job, "render", "running", detail="正在创建渲染任务", progress=0.9)
        render_job = create_render_job(_render_payload(job, state))
        job["artifacts"]["render_job_id"] = render_job["job_id"]
        job["status"] = "waiting_child_job"
        _save(job)
    job = _wait_render_job(job)
    job["status"] = "running"
    return _set_step(job, "render", "done", detail="视频渲染完成", progress=1)


def _run_pipeline(job_id: str, project_id: str) -> None:
    try:
        with _lock:
            job = _read(project_id, job_id)
            if job.get("status") == "cancelled":
                return
            job["status"] = "running"
            _save(job)
        for runner in (
            _run_theme_ideas,
            _run_select_idea,
            _run_theme,
            _run_copy,
            _run_storyboard,
            _run_improve_prompts,
            _run_images,
            _run_cover,
            _run_render,
        ):
            with _lock:
                job = _read(project_id, job_id)
            _check_cancelled(job)
            job = runner(job)
        with _lock:
            job = _read(project_id, job_id)
            job["status"] = "complete"
            job["current_step"] = "complete"
            job["detail"] = "自动流水线完成"
            job["progress"] = 1
            _save(job)
            _cancelled.discard(job_id)
            _runtime_secrets.pop(job_id, None)
    except Exception as exc:
        with _lock:
            try:
                job = _read(project_id, job_id)
            except Exception:
                return
            if isinstance(exc, AutoPipelineCancelled) or job.get("status") == "cancelled":
                job = _mark_cancelled(job)
            else:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["detail"] = str(exc)
                try:
                    _set_step(job, str(job.get("current_step") or "theme_ideas"), "failed", error=str(exc), detail=str(exc))
                    job = _read(project_id, job_id)
                except Exception:
                    pass
            _save(job)
            _cancelled.discard(job_id)
            _runtime_secrets.pop(job_id, None)


def create_auto_pipeline_job(payload: dict[str, Any]) -> dict[str, Any]:
    brief = str(payload.get("brief") or "").strip()
    project_id = normalize_project_id(payload.get("project_id") or "", brief or "自动流水线")
    job_id = make_job_id("auto")
    now = now_ms()
    input_data = {
        "brief": brief,
        "copy_preset": payload.get("copy_preset") or "reality",
        "image_size": payload.get("image_size") or "9:16",
        "reference_collection_id": payload.get("reference_collection_id") or "",
        "auto_reference_enabled": bool(payload.get("auto_reference_enabled")),
        "intro_template": payload.get("intro_template") or "none",
        "intro_image_seconds": payload.get("intro_image_seconds") or 0.3,
        "tts_preset": payload.get("tts_preset") or "custom",
        "voice": payload.get("voice") or "zh-CN-YunxiNeural",
        "rate": payload.get("rate") or "+12%",
        "bgm_id": payload.get("bgm_id") or "none",
        "intro_sfx_id": payload.get("intro_sfx_id") or "default",
        "auto_optimize_image_prompts": payload.get("auto_optimize_image_prompts", True),
        "render_after_images": payload.get("render_after_images", True),
        "image_concurrency": payload.get("image_concurrency") or DEFAULT_IMAGE_JOB_CONCURRENCY,
        "theme_idea_prompt": payload.get("theme_idea_prompt") or "",
        "copy_prompt": payload.get("copy_prompt") or "",
        "copy_to_story_prompt": payload.get("copy_to_story_prompt") or "",
        "image_prompt": payload.get("image_prompt") or "",
        "improve_image_prompt": payload.get("improve_image_prompt") or "",
        "text_config": {
            key: value for key, value in dict(payload.get("text_config") or {}).items() if key != "api_key"
        },
        "image_config": {
            key: value for key, value in dict(payload.get("image_config") or {}).items() if key != "api_key"
        },
        "tts_config": {
            key: value for key, value in dict(payload.get("tts_config") or {}).items() if key != "api_key"
        },
    }
    _runtime_secrets[job_id] = {
        "text_config": {"api_key": (payload.get("text_config") or {}).get("api_key") or ""},
        "image_config": {"api_key": (payload.get("image_config") or {}).get("api_key") or ""},
        "tts_config": {"api_key": (payload.get("tts_config") or {}).get("api_key") or ""},
    }
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "queued",
        "current_step": "theme_ideas",
        "progress": 0,
        "detail": "等待自动流水线启动",
        "created_at": now,
        "updated_at": now,
        "input": input_data,
        "steps": _step_template(),
        "artifacts": {
            "theme_ideas": [],
            "selected_idea": None,
            "image_job_id": "",
            "render_job_id": "",
        },
        "result": {
            "topic": "",
            "video_url": "",
            "project_url": f"/workspace/projects/{project_id}",
        },
        "error": "",
    }
    with _lock:
        _save(job)
    _runner.submit(_run_pipeline, job_id, project_id)
    return _public(job)


def get_auto_pipeline_job(project_id: str, job_id: str) -> dict[str, Any]:
    with _lock:
        return _public(_read(project_id, job_id))


def list_auto_pipeline_jobs(project_id: str, active_only: bool = False) -> list[dict[str, Any]]:
    return list_jobs(project_id, prefix="auto_", active_only=active_only, active_statuses=AUTO_ACTIVE_STATUSES)


def cancel_auto_pipeline_job(project_id: str, job_id: str) -> dict[str, Any]:
    project_id = safe_project_id(project_id)
    with _lock:
        job = _read(project_id, job_id)
        _cancelled.add(job_id)
        image_job_id = str((job.get("artifacts") or {}).get("image_job_id") or "")
        if image_job_id:
            try:
                cancel_image_job(project_id, image_job_id)
            except Exception:
                pass
        job = _mark_cancelled(job)
        return _public(job)


def resume_auto_pipeline_job(project_id: str, job_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    project_id = safe_project_id(project_id)
    with _lock:
        job = _read(project_id, job_id)
        if job.get("status") == "complete":
            return _public(job)
        if payload:
            _runtime_secrets[job_id] = {
                "text_config": {"api_key": ((payload.get("text_config") or {}).get("api_key") or "")},
                "image_config": {"api_key": ((payload.get("image_config") or {}).get("api_key") or "")},
                "tts_config": {"api_key": ((payload.get("tts_config") or {}).get("api_key") or "")},
            }
        _cancelled.discard(job_id)
        job["status"] = "queued"
        job["detail"] = "等待恢复自动流水线"
        job["error"] = ""
        for step in job.get("steps", []):
            if step.get("status") == "cancelled":
                step["status"] = "pending"
                step["detail"] = ""
                step["error"] = ""
                step["updated_at"] = now_ms()
        _save(job)
    _runner.submit(_run_pipeline, job_id, project_id)
    return _public(job)
