from __future__ import annotations

from pathlib import Path

from app.media.render.ffmpeg_utils import run_command, safe_rmtree
from app.media.render.constants import FPS

from .common import _concat_video, _static_intro_clip, normalize_intro_image_seconds
from .constants import FAST_CUT_MAX_IMAGES, STAGGERED_MASK_FEATHER, STAGGERED_SWEEP_MULTIPLIER

def _staggered_mask_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float, size: tuple[int, int]) -> None:
    W, H = size
    image_seconds = normalize_intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration, size)
        return

    sweep_seconds = max(image_seconds * STAGGERED_SWEEP_MULTIPLIER, 0.16)
    effect_duration = min(duration, image_seconds * (len(usable) - 1) + sweep_seconds)
    frames = max(1, int(round(effect_duration * FPS)))
    effect_duration = frames / FPS
    delay_frames = max(1, int(round(image_seconds * FPS)))
    sweep_frames = max(2, int(round(sweep_seconds * FPS)))
    feather = STAGGERED_MASK_FEATHER

    cmd = ["ffmpeg", "-y"]
    filters: list[str] = []
    for idx, image_path in enumerate(usable):
        cmd.extend(["-loop", "1", "-i", str(image_path)])
    for _ in usable:
        cmd.extend(["-f", "lavfi", "-i", f"nullsrc=s={W}x{H}:r={FPS}:d={effect_duration:.3f}"])
    cmd.extend(["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={effect_duration:.3f}"])

    base_index = len(usable) * 2
    filters.append(f"[{base_index}:v]format=rgba[base]")
    current = "base"
    for idx, _ in enumerate(usable):
        filters.append(
            f"[{idx}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},fps={FPS},trim=duration={effect_duration:.3f},"
            f"setpts=PTS-STARTPTS,format=rgba[img{idx}]"
        )
        delay = idx * delay_frames
        edge_expr = f"(-{feather}+({H + feather * 2})*(N-{delay})/{max(sweep_frames - 1, 1)})"
        mask_expr = f"clip(255*((({edge_expr})-Y+{feather})/{2 * feather}),0,255)"
        filters.append(
            f"[{len(usable) + idx}:v]format=gray,geq=lum='{mask_expr}',"
            f"trim=duration={effect_duration:.3f},setpts=PTS-STARTPTS[alpha{idx}]"
        )
        filters.append(f"[img{idx}][alpha{idx}]alphamerge[layer{idx}]")
        out_label = f"relay{idx}"
        filters.append(f"[{current}][layer{idx}]overlay=shortest=1:format=auto[{out_label}]")
        current = out_label

    relay_path = out_path
    hold_path: Path | None = None
    if duration - effect_duration > 0.08:
        segment_dir = out_path.parent / f"{out_path.stem}_staggered"
        segment_dir.mkdir(parents=True, exist_ok=True)
        relay_path = segment_dir / "relay.mp4"
        hold_path = segment_dir / "hold.mp4"

    try:
        run_command([
            *cmd,
            "-filter_complex", ";".join(filters) + f";[{current}]format=yuv420p[v]",
            "-map", "[v]", "-frames:v", str(frames),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(relay_path),
        ])
        if hold_path:
            _static_intro_clip(usable[-1], hold_path, duration - effect_duration, size)
            _concat_video([relay_path, hold_path], out_path)
    finally:
        if hold_path:
            safe_rmtree(hold_path.parent)

