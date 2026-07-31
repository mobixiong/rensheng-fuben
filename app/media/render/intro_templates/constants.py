from __future__ import annotations

import shutil
from pathlib import Path

from app.media.render.ffmpeg_utils import run_command, safe_rmtree, safe_unlink
from app.media.render.constants import FPS, H as DEFAULT_H, W as DEFAULT_W

FAST_CUT_TEMPLATE = "life_copy_fast_cut"

EXPAND_CUT_TEMPLATE = "life_copy_expand_cut"

FLASH_HORIZONTAL_TEMPLATE = "life_copy_flash_horizontal"

FLASH_VERTICAL_TEMPLATE = "life_copy_flash_vertical"

STAGGERED_MASK_TEMPLATE = "life_copy_staggered_mask"

MOSAIC_COLLAGE_TEMPLATE = "life_copy_mosaic_collage"

INTRO_TEMPLATES = {
    "none",
    FAST_CUT_TEMPLATE,
    EXPAND_CUT_TEMPLATE,
    FLASH_HORIZONTAL_TEMPLATE,
    FLASH_VERTICAL_TEMPLATE,
    STAGGERED_MASK_TEMPLATE,
    MOSAIC_COLLAGE_TEMPLATE,
}

FAST_CUT_MAX_IMAGES = 5

FAST_CUT_IMAGE_SECONDS = 0.3

FAST_CUT_MASK_FEATHER = 260

EXPAND_CUT_INITIAL_HALF_HEIGHT = 90

EXPAND_CUT_MASK_FEATHER = 180

FLASH_CUT_MASK_FEATHER = 220

STAGGERED_MASK_FEATHER = 42

STAGGERED_SWEEP_MULTIPLIER = 2.0

MOSAIC_TILE_COUNT = 9

INTRO_PREVIEW_TEMPLATES = [
    FAST_CUT_TEMPLATE,
    EXPAND_CUT_TEMPLATE,
    FLASH_HORIZONTAL_TEMPLATE,
    FLASH_VERTICAL_TEMPLATE,
    STAGGERED_MASK_TEMPLATE,
    MOSAIC_COLLAGE_TEMPLATE,
    "none",
]

