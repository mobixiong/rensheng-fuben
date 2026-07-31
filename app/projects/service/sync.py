from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.core.image_status import (
    IMAGE_JOB_DONE,
    IMAGE_JOB_FAILED,
    IMAGE_STATUS_POLICY_ERROR,
    TERMINAL_IMAGE_ITEM_STATUSES,
    has_shot_image,
    mark_image_done,
    mark_image_failure,
    normalize_persisted_image_state,
    should_keep_incoming_image_error,
)
from app.core.project_ids import project_image_for_index, workspace_path_from_url

from .identity import project_dir
from .policy import _mark_prompt_policy_errors


def _workspace_path_from_url(url: str) -> Path | None:
    return workspace_path_from_url(url)


def _project_image_for_index(image_dir: Path, index: int) -> Path | None:
    return project_image_for_index(image_dir, index)


def _mark_shot_image_done(shot: dict[str, Any], project_id: str, image_path: Path) -> None:
    shot["image_path"] = str(image_path.resolve())
    shot["image_url"] = f"/workspace/projects/{project_id}/images/{image_path.name}"
    mark_image_done(shot)


def _apply_latest_image_job_statuses(state: dict[str, Any], project_id: str) -> None:
    story = state.get("story")
    if not isinstance(story, dict):
        return
    shots = story.get("shots")
    if not isinstance(shots, list):
        return
    jobs_dir = project_dir(project_id) / "jobs"
    if not jobs_dir.exists():
        return
    seen: set[int] = set()
    for path in sorted(jobs_dir.glob("*.json"), key=lambda file: file.stat().st_mtime, reverse=True):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in job.get("items", []):
            try:
                index = int(item.get("shot_index"))
            except (TypeError, ValueError):
                continue
            if index in seen or index < 0 or index >= len(shots) or not isinstance(shots[index], dict):
                continue
            status = str(item.get("status") or "")
            if status not in TERMINAL_IMAGE_ITEM_STATUSES:
                continue
            seen.add(index)
            shot = shots[index]
            if has_shot_image(shot):
                mark_image_done(shot)
                continue
            if status == IMAGE_JOB_DONE:
                image_url = str(item.get("image_url") or "").strip()
                if image_url and not shot.get("image_url"):
                    shot["image_url"] = image_url
                    image_path = _workspace_path_from_url(image_url)
                    if image_path is not None:
                        shot["image_path"] = str(image_path)
                normalize_persisted_image_state(shot)
                continue
            if status != IMAGE_JOB_FAILED:
                continue
            error = str(item.get("error") or "").strip()
            category = str(item.get("error_category") or "").strip()
            code = str(item.get("error_code") or "").strip()
            if not error and not category and not code:
                continue
            mark_image_failure(shot, message=error or "图片生成失败", category=category or "unknown", code=code)


def _preserve_existing_image_errors(state: dict[str, Any], target_project_dir: Path) -> None:
    state_path = target_project_dir / "state.json"
    if not state_path.exists():
        return
    try:
        existing = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return
    existing_shots = ((existing.get("story") or {}).get("shots") or [])
    incoming_story = state.get("story")
    if not isinstance(incoming_story, dict):
        return
    incoming_shots = incoming_story.get("shots")
    if not isinstance(incoming_shots, list):
        return
    for index, shot in enumerate(incoming_shots):
        if index >= len(existing_shots) or not isinstance(shot, dict):
            continue
        existing_shot = existing_shots[index]
        if not isinstance(existing_shot, dict):
            continue
        if existing_shot.get("_image_status") != IMAGE_STATUS_POLICY_ERROR:
            continue
        if has_shot_image(shot):
            continue
        if not should_keep_incoming_image_error(shot):
            continue
        for key in ("_image_status", "_image_error", "_image_error_category", "_image_error_code"):
            if existing_shot.get(key):
                shot[key] = existing_shot[key]


def _copy_project_images(state: dict[str, Any], target_project_dir: Path) -> None:
    story = state.get("story")
    if not isinstance(story, dict):
        return
    shots = story.get("shots")
    if not isinstance(shots, list):
        return

    image_dir = target_project_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for index, shot in enumerate(shots, 1):
        if not isinstance(shot, dict):
            continue
        source = None
        raw_path = str(shot.get("image_path") or "").strip()
        if raw_path:
            source = Path(raw_path)
        if (not source or not source.exists()) and shot.get("image_url"):
            source = _workspace_path_from_url(str(shot.get("image_url")))
        if source and source.exists():
            target = image_dir / f"shot_{index:02d}{source.suffix or '.png'}"
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
        else:
            target = _project_image_for_index(image_dir, index)
        if target and target.exists():
            _mark_shot_image_done(shot, state["project_id"], target)
        else:
            normalize_persisted_image_state(shot)
    _mark_prompt_policy_errors(state)
    _apply_latest_image_job_statuses(state, state["project_id"])


def _sync_cover_from_selected_shot(state: dict[str, Any]) -> None:
    story = state.get("story")
    if not isinstance(story, dict):
        return
    cover = story.get("cover")
    if not isinstance(cover, dict):
        return
    shots = story.get("shots")
    if not isinstance(shots, list):
        return
    try:
        index = int(cover.get("source_shot_index"))
    except (TypeError, ValueError):
        return
    if index < 0 or index >= len(shots) or not isinstance(shots[index], dict):
        return
    shot = shots[index]
    image_path = str(shot.get("image_path") or "").strip()
    image_url = str(shot.get("image_url") or "").strip()
    if not image_path and not image_url:
        cover["_cover_status"] = "pending"
        return
    cover["image_path"] = image_path
    cover["image_url"] = image_url
    cover["image_size"] = shot.get("image_size") or story.get("image_size") or cover.get("image_size") or ""
    cover["image_prompt"] = str(cover.get("image_prompt") or shot.get("image_prompt") or shot.get("visual") or shot.get("voiceover") or "").strip()
    cover["_cover_status"] = "selected"
    cover.pop("_cover_error", None)
    cover.pop("raw_image_path", None)
    cover.pop("raw_image_url", None)
