from __future__ import annotations

import shutil
from pathlib import Path

from app.media.render.ffmpeg_utils import run_command, safe_rmtree, safe_unlink
from app.media.render.constants import FPS

from .common import _concat_video, _static_intro_clip, normalize_intro_image_seconds
from .constants import FAST_CUT_MAX_IMAGES, FLASH_CUT_MASK_FEATHER

def _feather_wipe_transition(
    prev_path: Path,
    next_path: Path,
    out_path: Path,
    duration: float,
    direction: str,
    size: tuple[int, int],
) -> None:
    W, H = size
    duration = max(0.08, float(duration))
    frames = max(2, int(round(duration * FPS)))
    duration = frames / FPS
    feather = FLASH_CUT_MASK_FEATHER
    axis = "Y" if direction == "vertical" else "X"
    axis_size = H if direction == "vertical" else W
    edge_expr = f"(-{feather}+({axis_size + feather * 2})*N/{max(frames - 1, 1)})"
    mask_expr = f"clip(255*((({edge_expr})-{axis}+{feather})/{2 * feather}),0,255)"
    image_vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"fps={FPS},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
        "eq=contrast=1.07:saturation=1.1,format=yuv420p"
    )
    filter_complex = (
        f"[0:v]{image_vf}[base];"
        f"[1:v]{image_vf}[overrgb];"
        f"[2:v]format=gray,geq=lum='{mask_expr}',boxblur=10:1,"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS[alpha];"
        "[overrgb][alpha]alphamerge[over];"
        "[base][over]overlay=shortest=1:format=auto,format=yuv420p[v]"
    )
    run_command([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(prev_path),
        "-loop", "1", "-i", str(next_path),
        "-f", "lavfi", "-i", f"nullsrc=s={W}x{H}:r={FPS}:d={duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[v]", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])

def _feather_flash_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float, direction: str, size: tuple[int, int]) -> None:
    W, H = size
    image_seconds = normalize_intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration, size)
        return

    effect_duration = min(duration, len(usable) * image_seconds)
    segment_dir = out_path.parent / f"{out_path.stem}_{direction}_flash"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    elapsed = 0.0

    try:
        first_path = segment_dir / "flash_01.mp4"
        first_duration = min(image_seconds, effect_duration)
        _static_intro_clip(usable[0], first_path, first_duration, size)
        segments.append(first_path)
        elapsed += first_duration

        for idx in range(1, len(usable)):
            if elapsed >= effect_duration - 0.03:
                break
            segment_path = segment_dir / f"flash_{idx + 1:02d}.mp4"
            segment_duration = min(image_seconds, max(0.03, effect_duration - elapsed))
            _feather_wipe_transition(usable[idx - 1], usable[idx], segment_path, segment_duration, direction, size)
            segments.append(segment_path)
            elapsed += segment_duration

        remaining = max(0.0, duration - elapsed)
        if remaining > 0.08:
            hold_path = segment_dir / "hold.mp4"
            _static_intro_clip(usable[-1], hold_path, remaining, size)
            segments.append(hold_path)

        if len(segments) == 1:
            shutil.copy2(segments[0], out_path)
        else:
            _concat_video(segments, out_path)
    finally:
        list_path = out_path.with_suffix(".txt")
        safe_unlink(list_path)
        safe_rmtree(segment_dir)

