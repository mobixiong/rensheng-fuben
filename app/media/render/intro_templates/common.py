from __future__ import annotations

import shutil
from pathlib import Path

from app.media.render.ffmpeg_utils import run_command, safe_rmtree, safe_unlink
from app.media.render.constants import FPS, H as DEFAULT_H, W as DEFAULT_W

from .constants import FAST_CUT_IMAGE_SECONDS, FAST_CUT_MASK_FEATHER, FAST_CUT_MAX_IMAGES

def normalize_intro_image_seconds(value: float | int | str | None) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = FAST_CUT_IMAGE_SECONDS
    if not seconds or seconds <= 0:
        seconds = FAST_CUT_IMAGE_SECONDS
    return max(0.08, min(3.0, seconds))

def render_still_clip(image_path: Path, out_path: Path, duration: float, size: tuple[int, int] | None = None) -> None:
    W, H = size or (DEFAULT_W, DEFAULT_H)
    frames = max(1, int(duration * FPS))
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"zoompan=z='1+0.035*on/{frames}':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p"
    )
    run_command([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])

def _static_intro_clip(image_path: Path, out_path: Path, duration: float, size: tuple[int, int]) -> None:
    W, H = size
    frames = max(1, int(round(duration * FPS)))
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"fps={FPS},format=yuv420p"
    )
    run_command([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])

def _concat_video(clips: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".txt")
    list_path.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in clips), encoding="utf-8")
    try:
        run_command([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-an", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(out_path),
        ])
    finally:
        safe_unlink(list_path)

def _linear_mask_transition(prev_path: Path, next_path: Path, out_path: Path, duration: float, size: tuple[int, int]) -> None:
    W, H = size
    duration = max(0.08, float(duration))
    frames = max(2, int(round(duration * FPS)))
    duration = frames / FPS
    feather = FAST_CUT_MASK_FEATHER
    radius_expr = f"(({H / 2:.1f}+{feather})*N/{max(frames - 1, 1)})"
    mask_expr = f"clip(255*((({radius_expr})+{feather}-abs(Y-{H / 2:.1f}))/{2 * feather}),0,255)"
    image_vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"fps={FPS},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
        "format=yuv420p"
    )
    filter_complex = (
        f"[0:v]{image_vf}[base];"
        f"[1:v]{image_vf}[overrgb];"
        f"[2:v]format=gray,geq=lum='{mask_expr}',trim=duration={duration:.3f},setpts=PTS-STARTPTS[alpha];"
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

def _linear_mask_intro_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float, size: tuple[int, int]) -> None:
    W, H = size
    image_seconds = normalize_intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration, size)
        return

    segment_dir = out_path.parent / f"{out_path.stem}_linear_mask"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    elapsed = 0.0

    try:
        first_hold = segment_dir / "hold_01.mp4"
        first_duration = min(image_seconds, duration)
        _static_intro_clip(usable[0], first_hold, first_duration, size)
        segments.append(first_hold)
        elapsed += first_duration

        for idx in range(1, len(usable)):
            if elapsed >= duration - 0.03:
                break
            trans_path = segment_dir / f"mask_{idx:02d}.mp4"
            transition_duration = min(image_seconds, max(0.03, duration - elapsed))
            _linear_mask_transition(usable[idx - 1], usable[idx], trans_path, transition_duration, size)
            segments.append(trans_path)
            elapsed += transition_duration

        if len(segments) == 1:
            shutil.copy2(segments[0], out_path)
        else:
            _concat_video(segments, out_path)
    finally:
        list_path = out_path.with_suffix(".txt")
        safe_unlink(list_path)
        safe_rmtree(segment_dir)

