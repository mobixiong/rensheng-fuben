"""Render pipeline package (split from monolithic pipeline module)."""
from __future__ import annotations

from .style import DEFAULT_STYLE, FONT_PATH, render_placeholder_image
from .story_model import normalize_story
from .intro import render_intro_previews
from .story_render import render_story

# Keep private helpers available for internal/tests if needed.
from .media_ops import (
    _concat,
    _concat_audio,
    _file_hash,
    _safe_media_duration,
    _sha256_json,
    _valid_audio,
    _valid_image,
    _valid_video,
)
from .resume import (
    _asset_signature,
    _mark_stage,
    _read_resume_manifest,
    _render_fingerprint,
    _stage_done,
    _tts_signature,
    _write_resume_manifest,
)
from .story_model import (
    _preview_image_paths,
    _project_image_for_index,
    _public_project_id,
    _shot_image_source,
    _workspace_path_from_url,
    _workspace_project_id,
    _workspace_project_ref,
)
from .final_export import _cleanup_intermediate, _final, _video_filter
from .style import _draw_character, _font, _font_path, _hex_mix, _palette, _wrap

__all__ = [
    "DEFAULT_STYLE",
    "FONT_PATH",
    "normalize_story",
    "render_intro_previews",
    "render_placeholder_image",
    "render_story",
]
