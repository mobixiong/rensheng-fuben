from __future__ import annotations

import json
import re
from typing import Any

from app.core.image_status import (
    ACTIVE_IMAGE_ITEM_STATUSES,
    IMAGE_JOB_CANCELLED,
    IMAGE_JOB_DONE,
    IMAGE_JOB_FAILED,
    IMAGE_JOB_QUEUED,
    IMAGE_JOB_RETRYING,
    IMAGE_JOB_RUNNING,
    TERMINAL_IMAGE_ITEM_STATUSES,
    mark_image_done,
    mark_image_failure,
)
from app.providers.image.adapter import ImageError
from app.jobs.store import (
    normalize_project_id,
    now_ms,
    public_job,
    read_job,
    save_job,
)
from app.jobs.health import mark_orphaned_active_job
from app.projects.service import project_dir, read_project_state, safe_project_id, write_project_files

from .constants import ACTIVE_JOB_STATUSES, IMAGE_JOB_FILE_PREFIX, IMAGE_JOB_KIND, STALE_ACTIVE_JOB_GRACE_MS, _active_job_ids

def _project_id_from_story(story: dict[str, Any], fallback: str = "") -> str:
    return normalize_project_id(fallback or story.get("project_id") or "", str(story.get("title") or ""))

def _bind_job_to_project(job: dict[str, Any], project_id: str) -> dict[str, Any]:
    before = json.dumps(job, ensure_ascii=False, sort_keys=True)
    safe_id = safe_project_id(project_id)
    old_id = str(job.get("project_id") or "")
    if old_id and old_id != safe_id:
        job = _replace_job_project_refs(job, old_id, safe_id)
    job = _normalize_job_project_urls(job, safe_id)
    job["project_id"] = safe_id
    after = json.dumps(job, ensure_ascii=False, sort_keys=True)
    if before != after:
        _save_job(job)
    return job

def _normalize_job_project_urls(value: Any, project_id: str) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_job_project_urls(item, project_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_job_project_urls(item, project_id) for item in value]
    if not isinstance(value, str):
        return value
    return re.sub(r"/workspace/projects/[^/\\]+", f"/workspace/projects/{project_id}", value)

def _replace_job_project_refs(value: Any, old_project_id: str, new_project_id: str) -> Any:
    if isinstance(value, dict):
        return {key: _replace_job_project_refs(item, old_project_id, new_project_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_job_project_refs(item, old_project_id, new_project_id) for item in value]
    if not isinstance(value, str):
        return value
    old_project_path = str(project_dir(old_project_id).resolve())
    new_project_path = str(project_dir(new_project_id).resolve())
    return (
        value
        .replace(f"/workspace/projects/{old_project_id}", f"/workspace/projects/{new_project_id}")
        .replace(old_project_path, new_project_path)
    )

def _save_job(job: dict[str, Any]) -> dict[str, Any]:
    job.setdefault("kind", IMAGE_JOB_KIND)
    job["done"] = sum(1 for item in job.get("items", []) if item.get("status") == IMAGE_JOB_DONE)
    job["failed"] = sum(1 for item in job.get("items", []) if item.get("status") == IMAGE_JOB_FAILED)
    job["cancelled"] = sum(1 for item in job.get("items", []) if item.get("status") == IMAGE_JOB_CANCELLED)
    job["active"] = sum(1 for item in job.get("items", []) if item.get("status") in {IMAGE_JOB_RUNNING, IMAGE_JOB_RETRYING})
    job["active_peak"] = max(int(job.get("active_peak") or 0), int(job.get("active") or 0))
    return save_job(job)

def _update_item(
    job: dict[str, Any],
    shot_index: int,
    *,
    status: str | None = None,
    attempt: int | None = None,
    error: str | None = None,
    error_category: str | None = None,
    error_code: str | None = None,
    image_url: str | None = None,
) -> None:
    for item in job.get("items", []):
        if item.get("shot_index") != shot_index:
            continue
        if status is not None:
            item["status"] = status
        if attempt is not None:
            item["attempt"] = attempt
        if error is not None:
            item["error"] = error
        if error_category is not None:
            item["error_category"] = error_category
        if error_code is not None:
            item["error_code"] = error_code
        if image_url is not None:
            item["image_url"] = image_url
        item["updated_at"] = now_ms()
        break

def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return public_job(job)

def _is_image_job(job: dict[str, Any]) -> bool:
    kind = str(job.get("kind") or "").strip()
    job_id = str(job.get("job_id") or "")
    return kind == IMAGE_JOB_KIND or (not kind and job_id.startswith(IMAGE_JOB_FILE_PREFIX))

def _read_image_job(project_id: str, job_id: str) -> dict[str, Any]:
    job = read_job(project_id, job_id)
    if not _is_image_job(job):
        raise FileNotFoundError(job_id)
    return job

def _mark_image_children_stale(job: dict[str, Any]) -> None:
    for item in job.get("items", []):
        if item.get("status") in ACTIVE_IMAGE_ITEM_STATUSES:
            item["status"] = IMAGE_JOB_FAILED
            item["error"] = "图片任务已中断，当前没有后台生成线程在运行。请重新点击批量生成图片。"
            item["error_category"] = "stalled"
            item["error_code"] = "worker_stopped"
            item["updated_at"] = now_ms()

def _mark_stale_if_orphaned(job: dict[str, Any]) -> dict[str, Any]:
    if not _is_image_job(job):
        return job
    return mark_orphaned_active_job(
        job,
        active_statuses=ACTIVE_JOB_STATUSES,
        terminal_status=IMAGE_JOB_FAILED,
        active_ids=_active_job_ids,
        grace_ms=STALE_ACTIVE_JOB_GRACE_MS,
        error_message="图片任务已中断，当前没有后台生成线程在运行。",
        mark_children=_mark_image_children_stale,
        save=_save_job,
    )

def _item_error(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, ImageError):
        message = exc.suggestion and f"{exc.message}\n{exc.suggestion}" or exc.message
        return message, exc.category, exc.code
    return str(exc), "unknown", ""

def _is_non_retryable(exc: Exception) -> bool:
    if not isinstance(exc, ImageError):
        return False
    return exc.category in {"prompt_policy", "quota", "auth", "config"} or exc.status_code == 429

def _apply_success(project_id: str, shot_index: int, result_story: dict[str, Any]) -> str:
    state = read_project_state(project_id)
    current_story = state.get("story")
    source_shot = (result_story.get("shots") or [])[shot_index]
    if not isinstance(current_story, dict) or not isinstance(current_story.get("shots"), list):
        raise ImageError("Project story is missing", category="request")
    target_shot = current_story["shots"][shot_index]
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
    current_story["project_id"] = project_id
    state["project_id"] = project_id
    write_project_files(state, set_active=False)
    return str(target_shot.get("image_url") or "")

def _apply_failure(project_id: str, shot_index: int, exc: Exception) -> tuple[str, str, str]:
    message, category, code = _item_error(exc)
    state = read_project_state(project_id)
    current_story = state.get("story")
    if isinstance(current_story, dict) and isinstance(current_story.get("shots"), list) and 0 <= shot_index < len(current_story["shots"]):
        shot = current_story["shots"][shot_index]
        mark_image_failure(shot, message=message, category=category, code=code)
        state["project_id"] = project_id
        current_story["project_id"] = project_id
        write_project_files(state, set_active=False)
    return message, category, code

def _claim_next(job: dict[str, Any]) -> int | None:
    for item in job.get("items", []):
        if item.get("status") == IMAGE_JOB_QUEUED:
            item["status"] = IMAGE_JOB_RUNNING
            item["updated_at"] = now_ms()
            return int(item["shot_index"])
    return None

def _finish_job_if_ready(job: dict[str, Any]) -> None:
    items = job.get("items", [])
    if not items or any(item.get("status") not in TERMINAL_IMAGE_ITEM_STATUSES for item in items):
        return
    if any(item.get("status") == IMAGE_JOB_FAILED for item in items):
        job["status"] = IMAGE_JOB_FAILED
    elif any(item.get("status") == IMAGE_JOB_CANCELLED for item in items):
        job["status"] = IMAGE_JOB_CANCELLED
    else:
        job["status"] = IMAGE_JOB_DONE
    _save_job(job)

