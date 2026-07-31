from __future__ import annotations

from typing import Any

from app.core.image_status import normalize_persisted_image_state

from .identity import project_dir
from .policy import _mark_prompt_policy_errors
from .sync import (
    _apply_latest_image_job_statuses,
    _project_image_for_index,
    _mark_shot_image_done,
    _sync_cover_from_selected_shot,
)


def hydrate_project_images(state: dict[str, Any], project_id: str) -> dict[str, Any]:
    story = state.get("story")
    if not isinstance(story, dict):
        return state
    shots = story.get("shots")
    if not isinstance(shots, list):
        return state
    image_dir = project_dir(project_id) / "images"
    for index, shot in enumerate(shots, 1):
        if not isinstance(shot, dict):
            continue
        image_path = _project_image_for_index(image_dir, index) if image_dir.exists() else None
        if image_path and image_path.exists():
            _mark_shot_image_done(shot, project_id, image_path)
        else:
            normalize_persisted_image_state(shot)
    _mark_prompt_policy_errors(state)
    _apply_latest_image_job_statuses(state, project_id)
    _sync_cover_from_selected_shot(state)
    return state
