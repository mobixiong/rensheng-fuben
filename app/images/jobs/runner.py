from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.core.image_status import (
    ACTIVE_IMAGE_ITEM_STATUSES,
    IMAGE_JOB_CANCELLED,
    IMAGE_JOB_DONE,
    IMAGE_JOB_FAILED,
    IMAGE_JOB_RETRYING,
    IMAGE_JOB_RUNNING,
)
from app.providers.image.adapter import ImageConfig, generate_one_story_image
from app.jobs.store import now_ms, read_job
from app.providers.llm.adapter import LLMConfig, select_primary_reference_asset
from app.projects.reference_assets import assets_for_llm, resolve_asset

from .constants import DEFAULT_IMAGE_JOB_CONCURRENCY, IMAGE_JOB_RETRY_LIMIT, MAX_IMAGE_JOB_CONCURRENCY, _active_job_ids, _cancelled, _lock
from .state import _apply_failure, _apply_success, _claim_next, _finish_job_if_ready, _is_non_retryable, _save_job, _update_item

def _run_item(job: dict[str, Any], shot_index: int, story: dict[str, Any], cfg: ImageConfig, fixed_prompt: str | None) -> None:
    project_id = job["project_id"]
    last_error: Exception | None = None
    for attempt in range(1, IMAGE_JOB_RETRY_LIMIT + 2):
        if job["job_id"] in _cancelled:
            with _lock:
                current = read_job(project_id, job["job_id"])
                _update_item(current, shot_index, status=IMAGE_JOB_CANCELLED, attempt=attempt)
                _save_job(current)
            return
        with _lock:
            current = read_job(project_id, job["job_id"])
            _update_item(current, shot_index, status=IMAGE_JOB_RETRYING if attempt > 1 else IMAGE_JOB_RUNNING, attempt=attempt)
            _save_job(current)
        try:
            result_story = generate_one_story_image(story, shot_index, cfg, fixed_prompt)
            with _lock:
                image_url = _apply_success(project_id, shot_index, result_story)
                current = read_job(project_id, job["job_id"])
                _update_item(current, shot_index, status=IMAGE_JOB_DONE, attempt=attempt, error="", error_category="", error_code="", image_url=image_url)
                _save_job(current)
            return
        except Exception as exc:
            last_error = exc
            if attempt <= IMAGE_JOB_RETRY_LIMIT and not _is_non_retryable(exc):
                continue
            with _lock:
                message, category, code = _apply_failure(project_id, shot_index, exc)
                current = read_job(project_id, job["job_id"])
                _update_item(current, shot_index, status=IMAGE_JOB_FAILED, attempt=attempt, error=message, error_category=category, error_code=code)
                _save_job(current)
            return
    if last_error is not None:
        with _lock:
            message, category, code = _apply_failure(project_id, shot_index, last_error)
            current = read_job(project_id, job["job_id"])
            _update_item(current, shot_index, status=IMAGE_JOB_FAILED, error=message, error_category=category, error_code=code)
            _save_job(current)

def _run_job(job_id: str, project_id: str, story: dict[str, Any], cfg: ImageConfig, fixed_prompt: str | None) -> None:
    try:
        with _lock:
            _active_job_ids.add(job_id)
            job = read_job(project_id, job_id)
            job["status"] = IMAGE_JOB_RUNNING
            _save_job(job)

        def worker() -> None:
            while True:
                with _lock:
                    current = read_job(project_id, job_id)
                    if job_id in _cancelled:
                        for item in current.get("items", []):
                            if item.get("status") in ACTIVE_IMAGE_ITEM_STATUSES:
                                item["status"] = IMAGE_JOB_CANCELLED
                                item["updated_at"] = now_ms()
                        _finish_job_if_ready(current)
                        return
                    shot_index = _claim_next(current)
                    _save_job(current)
                if shot_index is None:
                    return
                _run_item(current, shot_index, story, cfg, fixed_prompt)

        concurrency = max(1, min(int(job.get("concurrency") or DEFAULT_IMAGE_JOB_CONCURRENCY), MAX_IMAGE_JOB_CONCURRENCY))
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(worker) for _ in range(concurrency)]
            for future in futures:
                try:
                    future.result()
                except Exception:
                    pass
        with _lock:
            current = read_job(project_id, job_id)
            _finish_job_if_ready(current)
            _cancelled.discard(job_id)
    finally:
        with _lock:
            _active_job_ids.discard(job_id)

def _apply_primary_references(
    story: dict[str, Any],
    indexes: list[int],
    *,
    collection_id: str = "",
    enabled: bool = False,
    llm_cfg: LLMConfig | None = None,
) -> dict[str, Any]:
    if not enabled or not collection_id:
        return story
    try:
        assets = assets_for_llm(collection_id)
    except Exception:
        return story
    if not assets:
        return story
    assets_by_id = {asset["id"]: asset for asset in assets if asset.get("id")}
    shots = story.get("shots") if isinstance(story.get("shots"), list) else []
    for index in indexes:
        if index < 0 or index >= len(shots) or not isinstance(shots[index], dict):
            continue
        shot = shots[index]
        if shot.get("reference_mode") == "manual" and shot.get("primary_reference_asset_id"):
            selected_id = str(shot.get("primary_reference_asset_id") or "")
        else:
            selection = select_primary_reference_asset(shot, assets, llm_cfg or LLMConfig(temperature=0))
            selected_id = str(selection.get("selected_asset_id") or "")
            shot["_reference_selection"] = {
                "mode": "auto",
                "collection_id": collection_id,
                "reason": selection.get("reason") or "",
                "selection_type": selection.get("selection_type") or "none",
                "selected_at": now_ms(),
            }
        if selected_id and selected_id in assets_by_id:
            asset = assets_by_id[selected_id]
            shot["reference_collection_id"] = collection_id
            shot["reference_mode"] = shot.get("reference_mode") or "auto"
            shot["primary_reference_asset_id"] = selected_id
            shot["primary_reference_asset"] = asset
            try:
                full_asset = resolve_asset(collection_id, selected_id)
            except Exception:
                full_asset = None
            if isinstance(full_asset, dict) and full_asset.get("image_url"):
                shot["primary_reference_asset"] = {
                    **asset,
                    "image_url": full_asset.get("image_url") or asset.get("image_url") or "",
                }
        elif shot.get("reference_mode") != "manual":
            shot["reference_collection_id"] = collection_id
            shot["reference_mode"] = "auto"
            shot["primary_reference_asset_id"] = ""
            shot.pop("primary_reference_asset", None)
    return story

