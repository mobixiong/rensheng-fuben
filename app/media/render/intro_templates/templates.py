from __future__ import annotations

from pathlib import Path

from app.media.render.constants import H as DEFAULT_H, W as DEFAULT_W

from .common import render_still_clip
from .constants import (
    EXPAND_CUT_TEMPLATE,
    FAST_CUT_MAX_IMAGES,
    FAST_CUT_TEMPLATE,
    FLASH_HORIZONTAL_TEMPLATE,
    FLASH_VERTICAL_TEMPLATE,
    MOSAIC_COLLAGE_TEMPLATE,
    STAGGERED_MASK_TEMPLATE,
)
from .expand import _expand_cut_clip
from .fast_cut import _fast_cut_clip
from .flash import _feather_flash_clip
from .mosaic import _mosaic_collage_clip
from .staggered import _staggered_mask_clip


def render_intro_template(
    template: str,
    image_paths: list[Path],
    out_path: Path,
    duration: float,
    image_seconds: float,
    size: tuple[int, int] | None = None,
) -> None:
    size = size or (DEFAULT_W, DEFAULT_H)
    effect_paths = list(image_paths[:FAST_CUT_MAX_IMAGES])
    if len(effect_paths) > 1:
        effect_paths.reverse()
    if template == FAST_CUT_TEMPLATE:
        _fast_cut_clip(effect_paths, out_path, duration, image_seconds, size)
    elif template == EXPAND_CUT_TEMPLATE:
        _expand_cut_clip(effect_paths, out_path, duration, image_seconds, size)
    elif template == FLASH_HORIZONTAL_TEMPLATE:
        _feather_flash_clip(effect_paths, out_path, duration, image_seconds, "horizontal", size)
    elif template == FLASH_VERTICAL_TEMPLATE:
        _feather_flash_clip(effect_paths, out_path, duration, image_seconds, "vertical", size)
    elif template == STAGGERED_MASK_TEMPLATE:
        _staggered_mask_clip(effect_paths, out_path, duration, image_seconds, size)
    elif template == MOSAIC_COLLAGE_TEMPLATE:
        _mosaic_collage_clip(effect_paths, out_path, duration, image_seconds, size)
    else:
        render_still_clip(image_paths[0], out_path, duration, size)
