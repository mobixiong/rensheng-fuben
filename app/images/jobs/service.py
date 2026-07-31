from __future__ import annotations

import json
from typing import Any

from app.core.image_status import IMAGE_JOB_CANCELLED, IMAGE_JOB_QUEUED
from app.providers.image.adapter import ImageConfig, ImageError
from app.jobs.store import jobs_dir, make_job_id, now_ms
from app.providers.llm.adapter import LLMConfig
from app.projects.service import read_project_state, safe_project_id, write_project_files

from .constants import ACTIVE_JOB_STATUSES, DEFAULT_IMAGE_JOB_CONCURRENCY, IMAGE_JOB_FILE_PREFIX, IMAGE_JOB_KIND, MAX_IMAGE_JOB_CONCURRENCY, _active_job_ids, _cancelled, _lock, _runner
from .runner import _apply_primary_references, _run_job
from .state import _bind_job_to_project, _finish_job_if_ready, _is_image_job, _mark_stale_if_orphaned, _project_id_from_story, _public_job, _read_image_job, _save_job

def create_image_job(
    story: dict[str, Any],
    cfg: ImageConfig,
    *,
    fixed_prompt: str | None = None,
    mode: str = "generate_missing",
    shot_indexes: list[int] | None = None,
    concurrency: int = DEFAULT_IMAGE_JOB_CONCURRENCY,
    project_id: str = "",
    reference_collection_id: str = "",
    auto_reference_enabled: bool = False,
    reference_llm_cfg: LLMConfig | None = None,
) -> dict[str, Any]:
    if not cfg.api_key:
        raise ImageError("密钥未填写，密钥是群号", code="missing_api_key", category="auth")
    if not cfg.base_url or not cfg.model:
        raise ImageError("Image base_url/model is required", code="missing_config", category="config")

    project_id = _project_id_from_story(story, project_id)
    shots = story.get("shots") if isinstance(story.get("shots"), list) else []
    if not shots:
        raise ImageError("story.shots must be a non-empty array", category="request")
    if shot_indexes is None:
        indexes = [index for index, shot in enumerate(shots) if not (shot.get("image_url") or shot.get("image_path"))]
    else:
        indexes = sorted({int(index) for index in shot_indexes if 0 <= int(index) < len(shots)})
    if not indexes:
        raise ImageError("No shots need image generation", category="request")

    normalized_story = json.loads(json.dumps(story, ensure_ascii=False))
    normalized_story["project_id"] = project_id
    normalized_story["image_size"] = cfg.size
    normalized_story["reference_collection_id"] = reference_collection_id or normalized_story.get("reference_collection_id") or ""
    normalized_story = _apply_primary_references(
        normalized_story,
        indexes,
        collection_id=normalized_story.get("reference_collection_id") or "",
        enabled=auto_reference_enabled,
        llm_cfg=reference_llm_cfg,
    )
    if auto_reference_enabled and normalized_story.get("reference_collection_id"):
        try:
            state = read_project_state(project_id)
            state["project_id"] = project_id
            state["reference_collection_id"] = normalized_story.get("reference_collection_id") or ""
            state["auto_reference_enabled"] = True
            state["story"] = normalized_story
            write_project_files(state, set_active=False)
        except Exception:
            pass
    job_id = make_job_id(IMAGE_JOB_FILE_PREFIX.rstrip("_"))
    now = now_ms()
    job = {
        "job_id": job_id,
        "kind": IMAGE_JOB_KIND,
        "project_id": project_id,
        "mode": mode,
        "status": IMAGE_JOB_QUEUED,
        "total": len(indexes),
        "done": 0,
        "failed": 0,
        "cancelled": 0,
        "active": 0,
        "active_peak": 0,
        "concurrency": max(1, min(int(concurrency or DEFAULT_IMAGE_JOB_CONCURRENCY), MAX_IMAGE_JOB_CONCURRENCY)),
        "created_at": now,
        "updated_at": now,
        "items": [
            {
                "shot_index": index,
                "status": IMAGE_JOB_QUEUED,
                "attempt": 0,
                "error": "",
                "error_category": "",
                "error_code": "",
                "image_url": "",
                "updated_at": now,
            }
            for index in indexes
        ],
    }
    with _lock:
        _active_job_ids.add(job_id)
        _save_job(job)
    _runner.submit(_run_job, job_id, project_id, normalized_story, cfg, fixed_prompt)
    return _public_job(job)

def get_image_job(project_id: str, job_id: str) -> dict[str, Any]:
    project_id = safe_project_id(project_id)
    with _lock:
        return _public_job(_mark_stale_if_orphaned(_bind_job_to_project(_read_image_job(project_id, job_id), project_id)))

def list_project_jobs(project_id: str, active_only: bool = False) -> list[dict[str, Any]]:
    project_id = safe_project_id(project_id)
    path = jobs_dir(project_id)
    jobs: list[dict[str, Any]] = []
    for item in sorted(path.glob(f"{IMAGE_JOB_FILE_PREFIX}*.json"), key=lambda file: file.stat().st_mtime, reverse=True):
        try:
            job = json.loads(item.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not _is_image_job(job):
            continue
        job = _bind_job_to_project(job, project_id)
        job = _mark_stale_if_orphaned(job)
        if active_only and job.get("status") not in ACTIVE_JOB_STATUSES:
            continue
        jobs.append(_public_job(job))
    return jobs

def cancel_image_job(project_id: str, job_id: str) -> dict[str, Any]:
    project_id = safe_project_id(project_id)
    with _lock:
        job = _bind_job_to_project(_read_image_job(project_id, job_id), project_id)
        _cancelled.add(job_id)
        for item in job.get("items", []):
            if item.get("status") == IMAGE_JOB_QUEUED:
                item["status"] = IMAGE_JOB_CANCELLED
                item["updated_at"] = now_ms()
        if job.get("status") == IMAGE_JOB_QUEUED:
            job["status"] = IMAGE_JOB_CANCELLED
        _finish_job_if_ready(job)
        _save_job(job)
        return _public_job(job)

