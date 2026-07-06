import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .image_status import (
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
from .image_adapter import ImageConfig, ImageError, generate_one_story_image
from .job_store import jobs_dir, make_job_id, normalize_project_id, now_ms, public_job, read_job, save_job
from .job_health import mark_orphaned_active_job
from .llm_adapter import LLMConfig, select_primary_reference_asset
from .project_service import project_dir, read_project_state, safe_project_id, write_project_files
from .reference_assets import assets_for_llm, resolve_asset


ACTIVE_JOB_STATUSES = {IMAGE_JOB_QUEUED, IMAGE_JOB_RUNNING, IMAGE_JOB_RETRYING}
IMAGE_JOB_KIND = "image"
IMAGE_JOB_FILE_PREFIX = "img_"
DEFAULT_IMAGE_JOB_CONCURRENCY = 100
MAX_IMAGE_JOB_CONCURRENCY = 100
IMAGE_JOB_RETRY_LIMIT = 2
STALE_ACTIVE_JOB_GRACE_MS = 60_000

_runner = ThreadPoolExecutor(max_workers=4)
_lock = threading.RLock()
_cancelled: set[str] = set()
_active_job_ids: set[str] = set()


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
