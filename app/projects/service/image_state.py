from __future__ import annotations

from .policy import (
    PROMPT_POLICY_ERROR_MARKERS,
    PROMPT_POLICY_ERROR_MESSAGE,
    _has_prompt_policy_error,
    _image_failure_count,
    _mark_prompt_policy_errors,
)
from .sync import (
    _apply_latest_image_job_statuses,
    _copy_project_images,
    _mark_shot_image_done,
    _preserve_existing_image_errors,
    _project_image_for_index,
    _sync_cover_from_selected_shot,
    _workspace_path_from_url,
)
from .hydrate import hydrate_project_images

# Keep late-bound helper for callers that imported it historically.
def _svc():
    """Late-bind package attributes for monkeypatch-friendly path constants."""
    from app.projects import service as svc
    return svc

__all__ = [
    "PROMPT_POLICY_ERROR_MARKERS",
    "PROMPT_POLICY_ERROR_MESSAGE",
    "_apply_latest_image_job_statuses",
    "_copy_project_images",
    "_has_prompt_policy_error",
    "_image_failure_count",
    "_mark_prompt_policy_errors",
    "_mark_shot_image_done",
    "_preserve_existing_image_errors",
    "_project_image_for_index",
    "_svc",
    "_sync_cover_from_selected_shot",
    "_workspace_path_from_url",
    "hydrate_project_images",
]
