from __future__ import annotations

import shutil
from pathlib import Path

from app.media.render.ffmpeg_utils import safe_rmtree, safe_unlink

from .common import _concat_video, _linear_mask_intro_clip, _static_intro_clip, normalize_intro_image_seconds
from .constants import FAST_CUT_MAX_IMAGES

def _fast_cut_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float, size: tuple[int, int]) -> None:
    W, H = size
    image_seconds = normalize_intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration, size)
        return

    effect_duration = min(duration, len(usable) * image_seconds)
    remaining = max(0.0, duration - effect_duration)

    segment_dir = out_path.parent / f"{out_path.stem}_intro"
    segment_dir.mkdir(parents=True, exist_ok=True)
    mask_path = segment_dir / "linear_mask.mp4"
    hold_path = segment_dir / "hold.mp4"
    segments = [mask_path]

    try:
        _linear_mask_intro_clip(usable, mask_path, effect_duration, image_seconds, size)
        if remaining > 0.08:
            _static_intro_clip(usable[-1], hold_path, remaining, size)
            segments.append(hold_path)
        if len(segments) == 1:
            shutil.copy2(mask_path, out_path)
        else:
            _concat_video(segments, out_path)
    finally:
        list_path = out_path.with_suffix(".txt")
        safe_unlink(list_path)
        safe_rmtree(segment_dir)

