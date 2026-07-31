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

from .api import _api

def _wait_image_job(job: dict[str, Any]) -> dict[str, Any]:
    api = _api()
    project_id = str(job["project_id"])
    image_job_id = str(job["artifacts"].get("image_job_id") or "")
    if not image_job_id:
        return job
    while True:
        api._check_cancelled(job)
        image_job = get_image_job(project_id, image_job_id)
        total = int(image_job.get("total") or 0)
        done = int(image_job.get("done") or 0)
        failed = int(image_job.get("failed") or 0)
        job["artifacts"]["image_job"] = image_job
        job = _set_step(job, "images", "waiting", detail=f"图片生成 {done}/{total}，失败 {failed}", progress=0.66 + 0.2 * (done + failed) / max(total, 1))
        if image_job.get("status") in {"done", "failed", "cancelled"}:
            return job
        api.time.sleep(2)

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

