from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from app.core.paths import WORKSPACE
from app.core.project_ids import public_project_id

from .client import _public_project_id, _workspace_project_id, _workspace_project_ref, generate_image
from .constants import ImageConfig, ImageError
from .prompting import build_shot_image_prompt

def generate_story_images(story: dict[str, Any], cfg: ImageConfig, fixed_prompt: str | None = None) -> dict[str, Any]:
    project_id = _workspace_project_id(story.get("project_id"))
    if not project_id:
        project_id = time.strftime("img_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    project_ref = _workspace_project_ref(project_id)
    public_project_id = _public_project_id(project_ref)
    image_dir = WORKSPACE / project_ref / "images"
    workspace_url = f"/workspace/{project_ref}"
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise ImageError("story.shots must be a non-empty array")

    updated = json.loads(json.dumps(story, ensure_ascii=False))
    updated["project_id"] = public_project_id
    updated["image_size"] = cfg.size
    updated_shots = updated["shots"]
    for idx, shot in enumerate(updated_shots, 1):
        shot["image_size"] = cfg.size
        prompt = build_shot_image_prompt(updated, shot, fixed_prompt, cfg.size)
        out_path = image_dir / f"shot_{idx:02d}.png"
        generate_image(prompt, cfg, out_path)
        shot["image_path"] = str(out_path.resolve())
        shot["image_url"] = f"{workspace_url}/images/shot_{idx:02d}.png"
        shot["resolved_image_prompt"] = prompt
    return updated

def _safe_filename_suffix(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    safe = "".join(char if char in allowed else "_" for char in raw)
    if safe and not safe.startswith("_"):
        safe = f"_{safe}"
    return safe[:80]

def generate_one_story_image(
    story: dict[str, Any],
    shot_index: int,
    cfg: ImageConfig,
    fixed_prompt: str | None = None,
    *,
    filename_suffix: str = "",
) -> dict[str, Any]:
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise ImageError("story.shots must be a non-empty array")
    if shot_index < 0 or shot_index >= len(shots):
        raise ImageError("shot_index out of range")

    project_id = _workspace_project_id(story.get("project_id"))
    if not project_id:
        project_id = time.strftime("img_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    project_ref = _workspace_project_ref(project_id)
    public_project_id = _public_project_id(project_ref)
    image_dir = WORKSPACE / project_ref / "images"
    workspace_url = f"/workspace/{project_ref}"

    updated = json.loads(json.dumps(story, ensure_ascii=False))
    updated["project_id"] = public_project_id
    updated["image_size"] = cfg.size
    shot = updated["shots"][shot_index]
    shot["image_size"] = cfg.size
    prompt = build_shot_image_prompt(updated, shot, fixed_prompt, cfg.size)
    filename = f"shot_{shot_index + 1:02d}{_safe_filename_suffix(filename_suffix)}.png"
    out_path = image_dir / filename
    generate_image(prompt, cfg, out_path)
    shot["image_path"] = str(out_path.resolve())
    shot["image_url"] = f"{workspace_url}/images/{filename}"
    shot["resolved_image_prompt"] = prompt
    return updated

