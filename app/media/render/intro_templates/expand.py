from __future__ import annotations

import shutil
from pathlib import Path

from app.media.render.ffmpeg_utils import run_command, safe_rmtree, safe_unlink
from app.media.render.constants import FPS

from .common import _concat_video, _static_intro_clip, normalize_intro_image_seconds
from .constants import EXPAND_CUT_INITIAL_HALF_HEIGHT, EXPAND_CUT_MASK_FEATHER, FAST_CUT_MAX_IMAGES

def _expand_mask_segment(image_path: Path, out_path: Path, duration: float, start_frame: int, total_frames: int, size: tuple[int, int]) -> None:
    W, H = size
    frames = max(1, int(round(duration * FPS)))
    duration = frames / FPS
    total_frames = max(frames, int(total_frames))
    denom = max(total_frames - 1, 1)
    start_half = EXPAND_CUT_INITIAL_HALF_HEIGHT
    end_half = (H / 2) + EXPAND_CUT_MASK_FEATHER
    feather = EXPAND_CUT_MASK_FEATHER
    half_expr = f"({start_half}+({end_half:.1f}-{start_half})*(N+{max(0, start_frame)})/{denom})"
    mask_expr = f"clip(255*((({half_expr})+{feather}-abs(Y-{H / 2:.1f}))/{feather}),0,255)"
    image_vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"fps={FPS},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
        "eq=contrast=1.07:saturation=1.08,format=rgba"
    )
    filter_complex = (
        f"[0:v]{image_vf}[img];"
        f"[1:v]format=gray,geq=lum='{mask_expr}',boxblur=18:1,"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS[alpha];"
        "[img][alpha]alphamerge[masked];"
        "[2:v]format=rgba[base];"
        "[base][masked]overlay=shortest=1:format=auto,format=yuv420p[v]"
    )
    run_command([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-f", "lavfi", "-i", f"nullsrc=s={W}x{H}:r={FPS}:d={duration:.3f}",
        "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[v]", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])

def _expand_cut_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float, size: tuple[int, int]) -> None:
    W, H = size
    image_seconds = normalize_intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration, size)
        return

    effect_duration = min(duration, len(usable) * image_seconds)
    frames_per_image = max(1, int(round(image_seconds * FPS)))
    total_effect_frames = max(1, int(round(effect_duration * FPS)))
    segment_dir = out_path.parent / f"{out_path.stem}_expand"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    elapsed_frames = 0

    try:
        for idx, image_path in enumerate(usable):
            if elapsed_frames >= total_effect_frames:
                break
            remaining_frames = total_effect_frames - elapsed_frames
            segment_frames = min(frames_per_image, remaining_frames)
            if segment_frames <= 0:
                break
            segment_path = segment_dir / f"expand_{idx + 1:02d}.mp4"
            _expand_mask_segment(image_path, segment_path, segment_frames / FPS, elapsed_frames, total_effect_frames, size)
            segments.append(segment_path)
            elapsed_frames += segment_frames

        remaining = max(0.0, duration - (elapsed_frames / FPS))
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

