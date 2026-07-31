from __future__ import annotations


import json
import time
from typing import Any

from app.images.jobs import DEFAULT_IMAGE_JOB_CONCURRENCY, cancel_image_job, create_image_job, get_image_job
from app.jobs.store import now_ms
from app.providers.image.adapter import generate_one_story_image
from app.providers.llm.adapter import (
    generate_story_from_copy,
    generate_text,
    generate_theme_ideas,
    generate_topic_plan,
    improve_image_prompt,
)
from app.media.render.service import create_render_job, get_render_job
from app.projects.service import project_dir, write_project_files

from ..constants import (
    AutoPipelineError,
    RENDER_STALL_SECONDS,
    _RENDER_STALL_MSG,
)
from ..image_repair import _repair_missing_images
from ..presets import (
    _copy_preset_theme_instruction,
    _copy_preset_theme_profile,
    _default_copy_prompt,
    _default_copy_to_story_prompt,
    _default_image_prompt,
    _default_improve_prompt,
    _job_copy_preset,
)
from ..state import (
    _check_cancelled,
    _image_config,
    _image_failure_message,
    _llm_config,
    _missing_image_indexes,
    _save,
    _secrets,
    _set_step,
    _shot_has_image,
    _state_or_default,
    _story_has_valid_shots,
    _with_runtime_keys,
    _write_state,
)

def _run_theme_ideas(job: dict[str, Any]) -> dict[str, Any]:
    if job["artifacts"].get("theme_ideas"):
        return _set_step(job, "theme_ideas", "skipped", detail="已有候选方向", progress=0.1)
    _set_step(job, "theme_ideas", "running", detail="正在生成候选方向", progress=0.05)
    preset = _job_copy_preset(job)
    style_instruction = _copy_preset_theme_instruction(preset)
    job["artifacts"]["copy_preset"] = preset
    job["artifacts"]["copy_preset_label"] = _copy_preset_theme_profile(preset)["label"]
    job["result"]["copy_preset"] = preset
    job["result"]["copy_preset_label"] = _copy_preset_theme_profile(preset)["label"]
    data = generate_theme_ideas(
        str((job.get("input") or {}).get("brief") or ""),
        _llm_config(job, 0.8),
        (job.get("input") or {}).get("theme_idea_prompt") or None,
        count=6,
        instruction=style_instruction,
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
    preset = _job_copy_preset(job)
    style_instruction = _copy_preset_theme_instruction(preset)
    job["artifacts"]["copy_preset"] = preset
    job["artifacts"]["copy_preset_label"] = _copy_preset_theme_profile(preset)["label"]
    job["result"]["copy_preset"] = preset
    job["result"]["copy_preset_label"] = _copy_preset_theme_profile(preset)["label"]
    if str(state.get("topic") or "").strip() and str(state.get("theme_intro") or "").strip():
        job["result"]["topic"] = state.get("topic") or ""
        job["result"]["theme_intro"] = state.get("theme_intro") or ""
        return _set_step(job, "theme", "skipped", detail="已有主题", progress=0.25)
    _set_step(job, "theme", "running", detail="正在生成主题和主题介绍", progress=0.2)
    brief = str(state.get("theme_brief") or (job.get("input") or {}).get("brief") or "").strip()
    if not brief:
        selected = job["artifacts"].get("selected_idea") or {}
        brief = str(selected.get("direction") or selected.get("title") or "")
    theme_brief = "\n\n".join([
        style_instruction,
        f"用户原始顶层要求：{str((job.get('input') or {}).get('brief') or '').strip() or '未填写'}",
        f"当前候选方向：{brief or '请自动生成一个适配上述文案类型的人生副本方向'}",
    ])
    data = generate_topic_plan(theme_brief, _llm_config(job, 0.7), None)
    _check_cancelled(job)
    state["topic"] = data["topic"]
    state["theme_intro"] = data["intro"]
    state["copy_prompt_preset"] = preset
    job["result"]["topic"] = data["topic"]
    job["result"]["theme_intro"] = data["intro"]
    _write_state(job, state)
    return _set_step(job, "theme", "done", detail="主题已生成", progress=0.28)

def _run_copy(job: dict[str, Any]) -> dict[str, Any]:
    state = _state_or_default(job)
    if str(state.get("copy_text") or "").strip():
        return _set_step(job, "copy", "skipped", detail="已有口播文案", progress=0.38)
    _set_step(job, "copy", "running", detail="正在生成口播文案", progress=0.32)
    preset = _job_copy_preset(job)
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
        str((job.get("input") or {}).get("storyboard_granularity") or "balanced"),
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
    state["storyboard_granularity"] = (job.get("input") or {}).get("storyboard_granularity") or "balanced"
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

