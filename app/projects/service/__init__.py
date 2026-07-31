"""Project service package."""
from __future__ import annotations

from app.core.paths import ACTIVE_PROJECT, LEGACY_PROJECT_STATE, PROJECTS_DIR, WORKSPACE

from .identity import (
    GENERATED_PROJECT_ID_RE,
    _ensure_project_child,
    _project_id_for_topic,
    _rename_project_dir_if_needed,
    _replace_project_refs,
    _rewrite_project_refs_in_files,
    _slug,
    _unique_project_id,
    project_dir,
    safe_project_id,
)
from .image_state import (
    PROMPT_POLICY_ERROR_MARKERS,
    PROMPT_POLICY_ERROR_MESSAGE,
    _apply_latest_image_job_statuses,
    _copy_project_images,
    _has_prompt_policy_error,
    _image_failure_count,
    _mark_prompt_policy_errors,
    _mark_shot_image_done,
    _preserve_existing_image_errors,
    _project_image_for_index,
    _sync_cover_from_selected_shot,
    _workspace_path_from_url,
    hydrate_project_images,
)
from .crud import (
    activate_project,
    active_project_id,
    current_project,
    delete_project,
    list_projects,
    project_summary,
    read_project_state,
    save_project_state,
    write_project_files,
)

__all__ = [
    "ACTIVE_PROJECT",
    "LEGACY_PROJECT_STATE",
    "PROJECTS_DIR",
    "WORKSPACE",
    "PROMPT_POLICY_ERROR_MARKERS",
    "PROMPT_POLICY_ERROR_MESSAGE",
    "GENERATED_PROJECT_ID_RE",
    "activate_project",
    "active_project_id",
    "current_project",
    "delete_project",
    "hydrate_project_images",
    "list_projects",
    "project_dir",
    "project_summary",
    "read_project_state",
    "safe_project_id",
    "save_project_state",
    "write_project_files",
]
