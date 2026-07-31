from __future__ import annotations

import shutil
from pathlib import Path

from app.media.render.ffmpeg_utils import run_command, safe_rmtree, safe_unlink
from app.media.render.constants import FPS

from .common import _concat_video, _static_intro_clip, normalize_intro_image_seconds
from .constants import FAST_CUT_MAX_IMAGES, MOSAIC_TILE_COUNT

def _mosaic_tile_specs(size: tuple[int, int], variant: int = 0) -> list[dict[str, int | float]]:
    W, H = size
    col_a = int(W * 0.34)
    col_b = int(W * 0.33)
    cols = [
        (0, col_a),
        (col_a, col_b),
        (col_a + col_b, W - col_a - col_b),
    ]
    row_a = int(H * 0.31)
    row_b = int(H * 0.34)
    rows = [
        (0, row_a),
        (row_a, row_b),
        (row_a + row_b, H - row_a - row_b),
    ]
    offsets = [
        (-44, -22, -220, -80, 0.00),
        (18, 0, 0, -180, 0.04),
        (46, -18, 220, -70, 0.08),
        (-26, 10, -180, 0, 0.05),
        (0, 0, 0, 0, 0.11),
        (52, 14, 230, 20, 0.02),
        (-54, 28, -260, 110, 0.10),
        (14, 42, 0, 230, 0.07),
        (42, 36, 240, 130, 0.13),
    ]
    if variant % 2:
        offsets = list(reversed(offsets))
    specs: list[dict[str, int | float]] = []
    for row_index, (src_y, tile_h) in enumerate(rows):
        for col_index, (src_x, tile_w) in enumerate(cols):
            idx = row_index * 3 + col_index
            dx, dy, sx, sy, delay = offsets[idx]
            specs.append({
                "x": src_x,
                "y": src_y,
                "w": tile_w,
                "h": tile_h,
                "tx": max(-W, min(W, src_x + dx)),
                "ty": max(-H, min(H, src_y + dy)),
                "sx": sx,
                "sy": sy,
                "delay": delay,
            })
    return specs

def _mosaic_expr(target: float, offset: float, delay: float, move_duration: float) -> str:
    progress = f"min(max((t-{delay:.3f})/{move_duration:.3f},0),1)"
    return f"{target:.1f}+({offset:.1f})*(1-{progress})"

def _mosaic_collage_segment(image_path: Path, out_path: Path, duration: float, size: tuple[int, int], variant: int = 0) -> None:
    W, H = size
    duration = max(0.12, float(duration))
    frames = max(1, int(round(duration * FPS)))
    duration = frames / FPS
    specs = _mosaic_tile_specs(size, variant)
    fade_duration = max(0.04, min(0.10, duration * 0.32))
    move_duration = max(0.06, min(0.18, duration * 0.55))

    split_labels = "".join(f"[s{idx}]" for idx in range(MOSAIC_TILE_COUNT))
    filters = [
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},fps={FPS},trim=duration={duration:.3f},"
        f"setpts=PTS-STARTPTS,eq=contrast=1.08:saturation=1.12,format=rgba,"
        f"split={MOSAIC_TILE_COUNT}{split_labels}",
        f"[1:v]format=rgba[base]",
    ]
    for idx, spec in enumerate(specs):
        delay = min(float(spec["delay"]), max(0.0, duration - 0.06))
        filters.append(
            f"[s{idx}]crop={int(spec['w'])}:{int(spec['h'])}:{int(spec['x'])}:{int(spec['y'])},"
            f"format=rgba,fade=t=in:st={delay:.3f}:d={fade_duration:.3f}:alpha=1[tile{idx}]"
        )

    current = "base"
    for idx, spec in enumerate(specs):
        delay = min(float(spec["delay"]), max(0.0, duration - 0.06))
        x_expr = _mosaic_expr(float(spec["tx"]), float(spec["sx"]), delay, move_duration)
        y_expr = _mosaic_expr(float(spec["ty"]), float(spec["sy"]), delay, move_duration)
        out_label = f"mosaic{idx}"
        filters.append(
            f"[{current}][tile{idx}]overlay=x='{x_expr}':y='{y_expr}':"
            f"enable='gte(t,{delay:.3f})':shortest=1:format=auto[{out_label}]"
        )
        current = out_label

    run_command([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={duration:.3f}",
        "-filter_complex", ";".join(filters) + f";[{current}]format=yuv420p[v]",
        "-map", "[v]", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])

def _mosaic_collage_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float, size: tuple[int, int]) -> None:
    image_seconds = normalize_intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or not usable:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration, size)
        return

    effect_duration = min(duration, len(usable) * image_seconds)
    segment_dir = out_path.parent / f"{out_path.stem}_mosaic"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    elapsed = 0.0

    try:
        for idx, image_path in enumerate(usable):
            if elapsed >= effect_duration - 0.03:
                break
            segment_duration = min(image_seconds, max(0.03, effect_duration - elapsed))
            segment_path = segment_dir / f"mosaic_{idx + 1:02d}.mp4"
            _mosaic_collage_segment(image_path, segment_path, segment_duration, size, idx)
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

