from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.images.repair import ImageRepairHooks, ImageRepairPolicy, repair_missing_images
from app.core.image_status import IMAGE_STATUS_ERROR
from app.jobs.store import now_ms
from app.providers.image.adapter import generate_one_story_image
from app.providers.llm.adapter import improve_image_prompt
from app.projects.service import write_project_files

from .constants import (
    AutoPipelineError,
    IMAGE_REPAIR_BURST_SIZE,
    IMAGE_REPAIR_INFINITE_BURST_SIZE,
    IMAGE_REPAIR_SINGLE_RETRY_SIZE,
)
from .presets import _default_image_prompt, _default_improve_prompt
from .state import (
    _apply_repair_success,
    _check_cancelled,
    _clear_image_failure,
    _image_config,
    _image_failure_message,
    _image_repair_concurrency,
    _latest_job,
    _llm_config,
    _mark_repair_failure,
    _missing_image_indexes,
    _secrets,
    _set_step,
    _shot_has_image,
    _state_or_default,
    _write_state,
)


def _repair_burst_for_shots(
    job: dict[str, Any],
    shot_indexes: list[int],
    stage: str,
    attempts_per_shot: int,
) -> tuple[set[int], dict[int, list[str]]]:
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list):
        raise AutoPipelineError("缺少分镜，无法自动补救图片")
    active_indexes = [
        index for index in sorted(set(shot_indexes))
        if 0 <= index < len(shots) and not _shot_has_image(shots[index])
    ]
    if not active_indexes:
        return set(), {}
    cfg = _image_config(job)
    fixed_prompt = (job.get("input") or {}).get("image_prompt") or _default_image_prompt()
    burst_id = f"{str(job.get('job_id') or 'auto')[-8:]}_{stage}_{now_ms()}"
    successes: dict[int, list[dict[str, Any]]] = {index: [] for index in active_indexes}
    errors: dict[int, list[str]] = {index: [] for index in active_indexes}
    tasks = [
        (shot_index, attempt)
        for shot_index in active_indexes
        for attempt in range(1, max(1, attempts_per_shot) + 1)
    ]
    with ThreadPoolExecutor(max_workers=min(max(1, len(tasks)), _image_repair_concurrency(job))) as pool:
        futures = {
            pool.submit(
                generate_one_story_image,
                story,
                shot_index,
                cfg,
                fixed_prompt,
                filename_suffix=f"_{burst_id}_shot{shot_index + 1:02d}_{attempt:02d}",
            ): shot_index
            for shot_index, attempt in tasks
        }
        for future in as_completed(futures):
            _check_cancelled(job)
            shot_index = futures[future]
            try:
                successes[shot_index].append(future.result())
            except Exception as exc:
                errors[shot_index].append(str(exc).splitlines()[0][:240])
    repaired: set[int] = set()
    for shot_index, results in successes.items():
        if results:
            _apply_repair_success(job, shot_index, random.choice(results), stage)
            repaired.add(shot_index)
        else:
            _mark_repair_failure(job, shot_index, errors.get(shot_index) or [], stage)
    return repaired, errors

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

def _optimize_failed_image_prompts(job: dict[str, Any], shot_indexes: list[int], stage: str) -> tuple[set[int], set[int]]:
    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list):
        raise AutoPipelineError("缺少分镜，无法优化失败镜头图片提示词")
    active_indexes = [
        index for index in sorted(set(shot_indexes))
        if 0 <= index < len(shots) and not _shot_has_image(shots[index])
    ]
    if not active_indexes:
        return set(), set()
    prompt = (job.get("input") or {}).get("improve_image_prompt") or _default_improve_prompt()
    cfg = _llm_config(job, 0.4)
    optimized: dict[int, str] = {}
    failed: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(active_indexes))) as pool:
        futures = {
            pool.submit(improve_image_prompt, story, shot_index, cfg, prompt): shot_index
            for shot_index in active_indexes
        }
        for future in as_completed(futures):
            _check_cancelled(job)
            shot_index = futures[future]
            try:
                data = future.result()
                next_prompt = str(data.get("image_prompt") or "").strip()
                if not next_prompt:
                    raise AutoPipelineError("返回为空")
                optimized[shot_index] = next_prompt
            except Exception as exc:
                failed[shot_index] = str(exc)

    state = _state_or_default(job)
    story = state.get("story") or {}
    shots = story.get("shots") if isinstance(story, dict) else []
    if not isinstance(shots, list):
        raise AutoPipelineError("缺少分镜，无法写回优化后的图片提示词")
    for shot_index, next_prompt in optimized.items():
        if 0 <= shot_index < len(shots) and isinstance(shots[shot_index], dict):
            shot = shots[shot_index]
            shot["image_prompt"] = next_prompt
            shot["_image_prompt_status"] = stage
            shot["_image_prompt_auto_optimized_at"] = now_ms()
            shot["_image_prompt_message"] = "失败补救时自动优化"
            _clear_image_failure(shot)
    for shot_index, message in failed.items():
        _mark_repair_failure(job, shot_index, [message], stage)
    story["project_id"] = job["project_id"]
    state["story"] = story
    _write_state(job, state)
    return set(optimized), set(failed)

def _repair_missing_images(job: dict[str, Any], missing_indexes: list[int], total: int) -> dict[str, Any]:
    return repair_missing_images(
        job,
        missing_indexes,
        total,
        hooks=ImageRepairHooks(
            check_cancelled=_check_cancelled,
            set_step=_set_step,
            repair_burst_for_shots=_repair_burst_for_shots,
            optimize_failed_image_prompts=_optimize_failed_image_prompts,
            state_or_default=_state_or_default,
            latest_job=_latest_job,
            image_failure_message=_image_failure_message,
            image_repair_concurrency=_image_repair_concurrency,
            error_factory=AutoPipelineError,
        ),
        policy=ImageRepairPolicy(
            single_retry_size=IMAGE_REPAIR_SINGLE_RETRY_SIZE,
            burst_size=IMAGE_REPAIR_BURST_SIZE,
            infinite_burst_size=IMAGE_REPAIR_INFINITE_BURST_SIZE,
        ),
    )

