from __future__ import annotations

import shutil
import time
import uuid
from typing import Any

from app.core.errors import RenderError
from app.media.render.intro_templates import (
    FAST_CUT_IMAGE_SECONDS,
    FAST_CUT_MAX_IMAGES,
    INTRO_PREVIEW_TEMPLATES,
    INTRO_TEMPLATES,
    normalize_intro_image_seconds,
    render_intro_template,
)
from app.core.paths import WORKSPACE
from app.core.project_ids import public_project_id
from app.media.render.constants import render_size

from .story_model import _preview_image_paths, _public_project_id, _workspace_project_id, _workspace_project_ref, normalize_story

def render_intro_previews(
    story: dict[str, Any],
    project_id: str | None = None,
    templates: list[str] | None = None,
    duration: float = 3.0,
    image_seconds: float = FAST_CUT_IMAGE_SECONDS,
    image_size: str = "9:16",
) -> dict[str, Any]:
    clean = normalize_story(story)
    image_seconds = normalize_intro_image_seconds(image_seconds)
    canvas_size = render_size(image_size or story.get("image_size"))
    size_slug = f"{canvas_size[0]}x{canvas_size[1]}"
    project_id = _workspace_project_id(project_id) or time.strftime("%Y%m%d_%H%M%S_preview_") + uuid.uuid4().hex[:8]
    project_ref = _workspace_project_ref(project_id)
    public_project_id = _public_project_id(project_ref)
    project_dir = WORKSPACE / project_ref
    workspace_url = f"/workspace/{project_ref}"
    preview_dir = project_dir / "previews" / "intro_templates"
    preview_dir.mkdir(parents=True, exist_ok=True)

    duration = max(0.2, min(12.0, float(duration or 3.0)))
    requested_templates = templates or INTRO_PREVIEW_TEMPLATES
    valid_templates = [template for template in requested_templates if template in INTRO_TEMPLATES]
    if not valid_templates:
        valid_templates = INTRO_PREVIEW_TEMPLATES

    image_paths = _preview_image_paths(story, clean, project_dir, preview_dir)
    if not image_paths:
        raise RenderError("请先生成至少 1 张项目图片后再预览开头模板")

    items: list[dict[str, str]] = []
    for template in valid_templates:
        out_path = preview_dir / f"{template}_{size_slug}.mp4"
        render_intro_template(template, image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, canvas_size)
        items.append({
            "id": template,
            "video": f"{workspace_url}/previews/intro_templates/{template}_{size_slug}.mp4",
            "width": str(canvas_size[0]),
            "height": str(canvas_size[1]),
            "image_size": image_size or "",
        })
    preview_image_dir = preview_dir / "images"
    if preview_image_dir.exists():
        shutil.rmtree(preview_image_dir)
    return {
        "project_id": public_project_id,
        "duration_sec": duration,
        "image_seconds": image_seconds,
        "video_width": canvas_size[0],
        "video_height": canvas_size[1],
        "image_size": image_size or "",
        "items": items,
    }

