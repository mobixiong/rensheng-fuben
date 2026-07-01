import shutil
from pathlib import Path

from .ffmpeg_utils import run_command, safe_rmtree, safe_unlink
from .render_constants import FPS, H as DEFAULT_H, W as DEFAULT_W


FAST_CUT_TEMPLATE = "life_copy_fast_cut"
EXPAND_CUT_TEMPLATE = "life_copy_expand_cut"
FLASH_HORIZONTAL_TEMPLATE = "life_copy_flash_horizontal"
FLASH_VERTICAL_TEMPLATE = "life_copy_flash_vertical"
STAGGERED_MASK_TEMPLATE = "life_copy_staggered_mask"
INTRO_TEMPLATES = {
    "none",
    FAST_CUT_TEMPLATE,
    EXPAND_CUT_TEMPLATE,
    FLASH_HORIZONTAL_TEMPLATE,
    FLASH_VERTICAL_TEMPLATE,
    STAGGERED_MASK_TEMPLATE,
}
FAST_CUT_MAX_IMAGES = 5
FAST_CUT_IMAGE_SECONDS = 0.3
FAST_CUT_MASK_FEATHER = 260
EXPAND_CUT_INITIAL_HALF_HEIGHT = 90
EXPAND_CUT_MASK_FEATHER = 180
FLASH_CUT_MASK_FEATHER = 220
STAGGERED_MASK_FEATHER = 42
STAGGERED_SWEEP_MULTIPLIER = 2.0
INTRO_PREVIEW_TEMPLATES = [
    FAST_CUT_TEMPLATE,
    EXPAND_CUT_TEMPLATE,
    FLASH_HORIZONTAL_TEMPLATE,
    FLASH_VERTICAL_TEMPLATE,
    STAGGERED_MASK_TEMPLATE,
    "none",
]


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
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
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


def render_intro_template(
    template: str,
    image_paths: list[Path],
    out_path: Path,
    duration: float,
    image_seconds: float,
    size: tuple[int, int] | None = None,
) -> None:
    size = size or (DEFAULT_W, DEFAULT_H)
    if template == FAST_CUT_TEMPLATE:
        _fast_cut_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, size)
    elif template == EXPAND_CUT_TEMPLATE:
        _expand_cut_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, size)
    elif template == FLASH_HORIZONTAL_TEMPLATE:
        _feather_flash_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, "horizontal", size)
    elif template == FLASH_VERTICAL_TEMPLATE:
        _feather_flash_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, "vertical", size)
    elif template == STAGGERED_MASK_TEMPLATE:
        _staggered_mask_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, size)
    else:
        render_still_clip(image_paths[0], out_path, duration, size)
