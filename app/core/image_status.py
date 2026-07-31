"""Shot/image status helpers shared across projects, jobs, and workflow."""
from __future__ import annotations

from typing import Any


IMAGE_STATUS_PENDING = "pending"
IMAGE_STATUS_DONE = "done"
IMAGE_STATUS_ERROR = "error"
IMAGE_STATUS_POLICY_ERROR = "policy_error"

FINAL_IMAGE_STATUSES = {
    IMAGE_STATUS_PENDING,
    IMAGE_STATUS_DONE,
    IMAGE_STATUS_ERROR,
    IMAGE_STATUS_POLICY_ERROR,
}
ERROR_IMAGE_STATUSES = {IMAGE_STATUS_ERROR, IMAGE_STATUS_POLICY_ERROR}

IMAGE_JOB_QUEUED = "queued"
IMAGE_JOB_RUNNING = "running"
IMAGE_JOB_RETRYING = "retrying"
IMAGE_JOB_DONE = "done"
IMAGE_JOB_FAILED = "failed"
IMAGE_JOB_CANCELLED = "cancelled"

ACTIVE_IMAGE_ITEM_STATUSES = {IMAGE_JOB_QUEUED, IMAGE_JOB_RUNNING, IMAGE_JOB_RETRYING}
TERMINAL_IMAGE_ITEM_STATUSES = {IMAGE_JOB_DONE, IMAGE_JOB_FAILED, IMAGE_JOB_CANCELLED}

# Legacy UI-only statuses that may exist in older state.json files.
# These are not valid final image states and should not be persisted as
# shot-level `_image_status`.
LEGACY_TRANSIENT_IMAGE_STATUSES = {
    IMAGE_JOB_QUEUED,
    IMAGE_JOB_RUNNING,
    IMAGE_JOB_RETRYING,
    "generating",
    "redrawing",
}

IMAGE_RUNTIME_FIELDS = (
    "_image_job",
    "_image_attempt",
    "_image_status_started_at",
    "_image_status_updated_at",
)
IMAGE_ERROR_FIELDS = (
    "_image_error",
    "_image_error_category",
    "_image_error_code",
)


def has_shot_image(shot: dict[str, Any] | None) -> bool:
    return bool(isinstance(shot, dict) and (shot.get("image_path") or shot.get("image_url")))


def clear_image_runtime_fields(shot: dict[str, Any]) -> None:
    for key in IMAGE_RUNTIME_FIELDS:
        shot.pop(key, None)


def clear_image_error_fields(shot: dict[str, Any]) -> None:
    for key in IMAGE_ERROR_FIELDS:
        shot.pop(key, None)


def has_image_runtime_fields(shot: dict[str, Any] | None) -> bool:
    if not isinstance(shot, dict):
        return False
    return any(key in shot for key in IMAGE_RUNTIME_FIELDS) or bool(legacy_transient_image_status(shot))


def mark_image_pending(shot: dict[str, Any]) -> None:
    shot["_image_status"] = IMAGE_STATUS_PENDING
    clear_image_runtime_fields(shot)
    clear_image_error_fields(shot)


def mark_image_done(shot: dict[str, Any]) -> None:
    shot["_image_status"] = IMAGE_STATUS_DONE
    clear_image_runtime_fields(shot)
    clear_image_error_fields(shot)


def mark_image_failure(
    shot: dict[str, Any],
    *,
    message: str,
    category: str = "unknown",
    code: str = "",
) -> None:
    shot["_image_status"] = IMAGE_STATUS_POLICY_ERROR if category == "prompt_policy" else IMAGE_STATUS_ERROR
    shot["_image_error"] = message
    shot["_image_error_category"] = category or "unknown"
    shot["_image_error_code"] = code
    clear_image_runtime_fields(shot)


def has_terminal_image_error(shot: dict[str, Any]) -> bool:
    return bool(
        shot.get("_image_error")
        or shot.get("_image_error_category")
        or shot.get("_image_error_code")
        or shot.get("_image_status") in ERROR_IMAGE_STATUSES
    )


def legacy_transient_image_status(shot: dict[str, Any]) -> str:
    job = shot.get("_image_job")
    if isinstance(job, dict) and job.get("status") in LEGACY_TRANSIENT_IMAGE_STATUSES:
        return str(job.get("status"))
    if shot.get("_image_status") in LEGACY_TRANSIENT_IMAGE_STATUSES:
        return str(shot.get("_image_status"))
    return ""


def normalize_final_image_status(shot: dict[str, Any], *, has_image: bool = False) -> str:
    status = str(shot.get("_image_status") or "")
    if status == IMAGE_STATUS_DONE or has_image:
        return IMAGE_STATUS_DONE
    if status == IMAGE_STATUS_POLICY_ERROR or shot.get("_image_error_category") == "prompt_policy":
        return IMAGE_STATUS_POLICY_ERROR
    if status == IMAGE_STATUS_ERROR or has_terminal_image_error(shot):
        return IMAGE_STATUS_ERROR
    return IMAGE_STATUS_PENDING


def normalize_persisted_image_state(shot: dict[str, Any]) -> str:
    """Normalize a shot before it is exposed or written to state.json."""
    status = normalize_final_image_status(shot, has_image=has_shot_image(shot))
    if status == IMAGE_STATUS_DONE:
        mark_image_done(shot)
        return IMAGE_STATUS_DONE
    if status == IMAGE_STATUS_PENDING:
        mark_image_pending(shot)
        return IMAGE_STATUS_PENDING
    if has_image_runtime_fields(shot):
        clear_image_runtime_fields(shot)
    shot["_image_status"] = status
    return status


def should_keep_incoming_image_error(shot: dict[str, Any]) -> bool:
    return str(shot.get("_image_status") or "") in {"", IMAGE_STATUS_PENDING, IMAGE_STATUS_ERROR, IMAGE_STATUS_POLICY_ERROR}
