from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.errors import RenderError
from app.media.render.intro_templates import FAST_CUT_MAX_IMAGES
from app.core.project_ids import public_project_id, workspace_path_from_url, workspace_project_id, workspace_project_ref, project_image_for_index

from .style import DEFAULT_STYLE

def normalize_story(story: dict[str, Any]) -> dict[str, Any]:
    title = str(story.get("title") or "人生副本样片")
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise RenderError("story.shots must be a non-empty array")
    normalized = []
    for i, shot in enumerate(shots, 1):
        if not isinstance(shot, dict):
            raise RenderError(f"shot {i} must be an object")
        voiceover = str(shot.get("voiceover") or shot.get("narration") or shot.get("text") or "").strip()
        if not voiceover:
            raise RenderError(f"shot {i} missing voiceover")
        subtitle_chunks = shot.get("subtitle_chunks")
        if isinstance(subtitle_chunks, list):
            subtitle_chunks = [
                str(item.get("text") if isinstance(item, dict) else item).strip()
                for item in subtitle_chunks
                if str(item.get("text") if isinstance(item, dict) else item).strip()
            ]
        else:
            subtitle_chunks = []
        normalized.append({
            "id": int(shot.get("id") or i),
            "voiceover": voiceover,
            "visual": str(shot.get("visual") or shot.get("image_prompt") or voiceover),
            "punch": str(shot.get("punch") or shot.get("keyword") or f"镜头{i}"),
            "image_path": str(shot.get("image_path") or "").strip(),
            "image_prompt": str(shot.get("image_prompt") or ""),
            "video_prompt": str(shot.get("video_prompt") or ""),
            "subtitle_chunks": subtitle_chunks,
        })
    return {"title": title, "style_preset": str(story.get("style_preset") or DEFAULT_STYLE), "shots": normalized}

def _workspace_project_id(value: str | None) -> str:
    try:
        return workspace_project_id(value, strict=True)
    except ValueError as exc:
        from app.core.errors import RenderError
        raise RenderError(str(exc) if str(exc) else "Invalid project_id") from exc

def _workspace_project_ref(project_id: str) -> str:
    return workspace_project_ref(project_id)

def _public_project_id(project_ref: str) -> str:
    return public_project_id(project_ref)

def _workspace_path_from_url(url: str) -> Path | None:
    return workspace_path_from_url(url)

def _project_image_for_index(project_dir: Path, index: int) -> Path | None:
    return project_image_for_index(project_dir, index)

def _shot_image_source(
    raw_shot: dict[str, Any],
    normalized_shot: dict[str, Any],
    project_dir: Path,
    index: int,
) -> Path | None:
    candidates: list[Path] = []
    raw_path = str(raw_shot.get("image_path") or normalized_shot.get("image_path") or "").strip()
    if raw_path:
        candidates.append(Path(raw_path))
    raw_url = str(raw_shot.get("image_url") or "").strip()
    workspace_path = _workspace_path_from_url(raw_url)
    if workspace_path:
        candidates.append(workspace_path)
    project_image = _project_image_for_index(project_dir, index)
    if project_image:
        candidates.append(project_image)
    return next((path for path in candidates if path.exists()), None)

def _preview_image_paths(
    original_story: dict[str, Any],
    normalized_story: dict[str, Any],
    project_dir: Path,
    preview_dir: Path,
) -> list[Path]:
    source_shots = original_story.get("shots") if isinstance(original_story.get("shots"), list) else []
    normalized_shots = normalized_story["shots"][:FAST_CUT_MAX_IMAGES]
    image_paths: list[Path] = []
    for idx, normalized_shot in enumerate(normalized_shots, 1):
        raw_shot = source_shots[idx - 1] if idx - 1 < len(source_shots) and isinstance(source_shots[idx - 1], dict) else {}
        source = _shot_image_source(raw_shot, normalized_shot, project_dir, idx)
        if source:
            image_paths.append(source)
    return image_paths

