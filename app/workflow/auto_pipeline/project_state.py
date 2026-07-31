from __future__ import annotations

from typing import Any

from app.core.image_status import (
    IMAGE_STATUS_ERROR,
    clear_image_error_fields,
    clear_image_runtime_fields,
    mark_image_done,
)
from app.jobs.store import now_ms
from app.projects.service import read_project_state, write_project_files

from .constants import AutoPipelineError, COPY_PROMPT_PRESETS
from .presets import _job_copy_preset


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
            "copy_prompt_preset": _job_copy_preset(job),
            "storyboard_granularity": (job.get("input") or {}).get("storyboard_granularity") or "balanced",
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
    preset = _job_copy_preset(job)
    current_preset = str(state.get("copy_prompt_preset") or "").strip()
    if current_preset not in COPY_PROMPT_PRESETS:
        state["copy_prompt_preset"] = preset
    selected_idea = job.get("artifacts", {}).get("selected_idea") or {}
    result = job.get("result") or {}
    if not str(state.get("topic") or "").strip() and result.get("topic"):
        state["topic"] = result.get("topic") or ""
    if not str(state.get("theme_intro") or "").strip() and result.get("theme_intro"):
        state["theme_intro"] = result.get("theme_intro") or ""
    if not str(state.get("theme_brief") or "").strip():
        state["theme_brief"] = selected_idea.get("direction") or selected_idea.get("title") or (job.get("input") or {}).get("brief") or ""
    state["storyboard_granularity"] = (job.get("input") or {}).get("storyboard_granularity") or state.get("storyboard_granularity") or "balanced"
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
    clear_image_error_fields(shot)
    clear_image_runtime_fields(shot)


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
    shot["_image_status"] = IMAGE_STATUS_ERROR
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
    mark_image_done(target_shot)
    target_shot["_image_version"] = now_ms()
    target_shot["_image_repair_stage"] = stage
    target_shot["_image_repaired_at"] = now_ms()
    story["project_id"] = job["project_id"]
    state["story"] = story
    payload = _write_state(job, state)
    payload_shots = ((payload.get("story") or {}).get("shots") or [])
    if 0 <= shot_index < len(payload_shots) and isinstance(payload_shots[shot_index], dict):
        return str(payload_shots[shot_index].get("image_url") or "")
    return str(target_shot.get("image_url") or "")
