import asyncio
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .audio_assets import default_reveal_sfx_path, resolve_bgm_path
from .errors import RenderError
from .paths import WORKSPACE
from .tts_adapter import TtsConfig, synthesize_tts

W, H = 1080, 1920
FPS = 30
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
FAST_CUT_TRANSITION_SECONDS = 0.3
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


DEFAULT_STYLE = (
    "中国网络科普动画风格，赛璐璐着色，粗黑描边，干净利落的矢量线条，"
    "2D平面动画，高对比阴影，高饱和色调，少量关键词花字。主角是无脸圆形白色光头角色，"
    "极简点状眼睛，夸张眉毛，表情包风格，穿连帽衫或制服，Q版但不过度幼稚。"
)


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    if proc.returncode != 0:
        raise RenderError(f"Command failed: {' '.join(cmd)}\n{proc.stderr[-3000:]}")


def _safe_unlink(path: Path) -> None:
    for _ in range(4):
        try:
            if path.exists():
                path.unlink()
            return
        except OSError:
            time.sleep(0.15)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _safe_rmtree(path: Path) -> None:
    for _ in range(4):
        try:
            if path.exists():
                shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.15)
    shutil.rmtree(path, ignore_errors=True)


def _intro_image_seconds(value: float | int | str | None) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = FAST_CUT_IMAGE_SECONDS
    if not seconds or seconds <= 0:
        seconds = FAST_CUT_IMAGE_SECONDS
    return max(0.08, min(3.0, seconds))


def _ffmpeg_path_arg(path: Path) -> str:
    return path.resolve().as_posix().replace(":", "\\:")


def _duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RenderError(proc.stderr)
    return float(proc.stdout.strip())


def _font_path() -> str:
    for p in [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\Dengb.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    ]:
        if Path(p).exists():
            return p
    return ""


FONT_PATH = _font_path()


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.truetype(FONT_PATH, size=size) if FONT_PATH else ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text:
        test = cur + ch
        box = draw.textbbox((0, 0), test, font=font)
        if box[2] - box[0] > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def _palette(idx: int) -> tuple[str, str, str]:
    palettes = [
        ("#ffcc33", "#30c5ff", "#ff5a5f"),
        ("#62d26f", "#fff176", "#1e88e5"),
        ("#f06292", "#4dd0e1", "#ffd54f"),
        ("#7e57c2", "#ff7043", "#80cbc4"),
        ("#ef5350", "#ffee58", "#42a5f5"),
        ("#26c6da", "#ab47bc", "#ffee58"),
    ]
    return palettes[idx % len(palettes)]


def _hex_mix(a: str, b: str, t: float) -> tuple[int, int, int]:
    return tuple(int(int(a[i : i + 2], 16) * (1 - t) + int(b[i : i + 2], 16) * t) for i in (1, 3, 5))


def _draw_character(draw: ImageDraw.ImageDraw, x: int, y: int, accent: str, mood: int) -> None:
    scale = 1.05
    lw = 10
    head_r = int(105 * scale)
    body_w = int(190 * scale)
    body_h = int(245 * scale)
    draw.ellipse((x - head_r, y - head_r, x + head_r, y + head_r), fill="#ffffff", outline="#111111", width=lw)
    eye_y = y - 15
    draw.ellipse((x - 46, eye_y, x - 24, eye_y + 22), fill="#111111")
    draw.ellipse((x + 24, eye_y, x + 46, eye_y + 22), fill="#111111")
    tilt = (mood % 3 - 1) * 12
    draw.line((x - 62, eye_y - 35 + tilt, x - 14, eye_y - 45), fill="#111111", width=lw)
    draw.line((x + 14, eye_y - 45, x + 62, eye_y - 35 - tilt), fill="#111111", width=lw)
    top = y + 105
    draw.rounded_rectangle((x - body_w // 2, top, x + body_w // 2, top + body_h), radius=45, fill=accent, outline="#111111", width=lw)
    draw.line((x - body_w // 2, top + 55, x - 200, top + 170), fill="#111111", width=lw)
    draw.line((x + body_w // 2, top + 55, x + 200, top + 145), fill="#111111", width=lw)
    draw.line((x - 55, top + body_h, x - 100, top + body_h + 170), fill="#111111", width=lw)
    draw.line((x + 55, top + body_h, x + 100, top + body_h + 170), fill="#111111", width=lw)


def render_placeholder_image(shot: dict[str, Any], out_path: Path, idx: int, title: str) -> None:
    a, b, c = _palette(idx)
    img = Image.new("RGB", (W, H), "#f7f8fb")
    draw = ImageDraw.Draw(img)
    for y in range(0, H, 12):
        draw.rectangle((0, y, W, y + 12), fill=_hex_mix(a, b, y / H))
    overlay = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((-200, 160, 450, 820), fill=(255, 255, 255, 55))
    od.ellipse((700, 930, 1280, 1520), fill=(255, 255, 255, 45))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((110, 460, 970, 920), radius=50, fill="#ffffff", outline="#111111", width=9)
    for i in range(4):
        x = 180 + i * 190
        y = 590 - i * 24
        draw.ellipse((x, y, x + 145, y + 120), fill=[a, b, c, "#ffffff"][i], outline="#111111", width=7)
    _draw_character(draw, 540, 1040, c, idx)

    title_font = _font(58)
    punch_font = _font(90)
    body_font = _font(42)
    draw.rounded_rectangle((80, 90, 1000, 282), radius=35, fill="#ffffff", outline="#111111", width=8)
    lines = _wrap(draw, title, title_font, 830)[:2]
    for line_i, line in enumerate(lines):
        draw.text((125, 125 + line_i * 70), line, font=title_font, fill="#111111")

    punch = str(shot.get("punch") or shot.get("keyword") or f"镜头 {idx + 1}")
    box = draw.textbbox((0, 0), punch, font=punch_font, stroke_width=5)
    draw.text(((W - (box[2] - box[0])) // 2, 330), punch, font=punch_font, fill="#ffffff", stroke_fill="#111111", stroke_width=5)

    visual = str(shot.get("visual") or shot.get("image_prompt") or shot.get("voiceover") or "")
    draw.rounded_rectangle((70, 1540, 1010, 1765), radius=30, fill="#ffffff", outline="#111111", width=7)
    y = 1580
    for line in _wrap(draw, visual, body_font, 860)[:3]:
        draw.text((110, y), line, font=body_font, fill="#111111")
        y += 58
    draw.text((72, 1840), f"SHOT {idx + 1:02d}", font=_font(34), fill="#111111")
    img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=105, threshold=3)).save(out_path, quality=95)


def _srt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_ts(sec: float) -> str:
    cs = int(round(sec * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _write_subtitles(shots: list[dict[str, Any]], srt_path: Path, ass_path: Path) -> None:
    srt = []
    for i, shot in enumerate(shots, 1):
        srt.append(f"{i}\n{_srt_ts(shot['start'])} --> {_srt_ts(shot['end'])}\n{shot.get('voiceover', '')}\n")
    srt_path.write_text("\n".join(srt), encoding="utf-8")
    ass = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Microsoft YaHei,54,&H00FFFFFF,&H000000FF,&H00111111,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,2,70,70,150,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for shot in shots:
        text = "\\N".join([str(shot.get("voiceover", ""))[i : i + 18] for i in range(0, len(str(shot.get("voiceover", ""))), 18)])
        ass.append(f"Dialogue: 0,{_ass_ts(shot['start'])},{_ass_ts(shot['end'])},Default,,0,0,0,,{text}")
    ass_path.write_text("\n".join(ass), encoding="utf-8")


def _allocate(shots: list[dict[str, Any]], total: float) -> None:
    weights = [max(8, len(str(s.get("voiceover", "")))) for s in shots]
    durs = [max(3.4, total * w / sum(weights)) for w in weights]
    scale = total / sum(durs)
    cursor = 0.0
    for shot, dur in zip(shots, durs):
        shot["start"] = cursor
        cursor += dur * scale
        shot["end"] = cursor
    shots[-1]["end"] = total


def _clip(image_path: Path, out_path: Path, duration: float, intro_template: str = "none") -> None:
    frames = max(1, int(duration * FPS))
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"zoompan=z='1+0.035*on/{frames}':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p"
    )
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])


def _static_intro_clip(image_path: Path, out_path: Path, duration: float) -> None:
    frames = max(1, int(round(duration * FPS)))
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"fps={FPS},format=yuv420p"
    )
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])


def _linear_mask_transition(prev_path: Path, next_path: Path, out_path: Path, duration: float) -> None:
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
    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(prev_path),
        "-loop", "1", "-i", str(next_path),
        "-f", "lavfi", "-i", f"nullsrc=s={W}x{H}:r={FPS}:d={duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[v]", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])


def _linear_mask_intro_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float) -> None:
    image_seconds = _intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration)
        return

    segment_dir = out_path.parent / f"{out_path.stem}_linear_mask"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    elapsed = 0.0

    try:
        first_hold = segment_dir / "hold_01.mp4"
        first_duration = min(image_seconds, duration)
        _static_intro_clip(usable[0], first_hold, first_duration)
        segments.append(first_hold)
        elapsed += first_duration

        for idx in range(1, len(usable)):
            if elapsed >= duration - 0.03:
                break
            trans_path = segment_dir / f"mask_{idx:02d}.mp4"
            transition_duration = min(image_seconds, max(0.03, duration - elapsed))
            _linear_mask_transition(usable[idx - 1], usable[idx], trans_path, transition_duration)
            segments.append(trans_path)
            elapsed += transition_duration

        if len(segments) == 1:
            shutil.copy2(segments[0], out_path)
        else:
            _concat_video(segments, out_path)
    finally:
        list_path = out_path.with_suffix(".txt")
        _safe_unlink(list_path)
        _safe_rmtree(segment_dir)


def _expand_mask_segment(image_path: Path, out_path: Path, duration: float, start_frame: int, total_frames: int) -> None:
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
    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-f", "lavfi", "-i", f"nullsrc=s={W}x{H}:r={FPS}:d={duration:.3f}",
        "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[v]", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])


def _expand_cut_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float) -> None:
    image_seconds = _intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration)
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
            _expand_mask_segment(image_path, segment_path, segment_frames / FPS, elapsed_frames, total_effect_frames)
            segments.append(segment_path)
            elapsed_frames += segment_frames

        remaining = max(0.0, duration - (elapsed_frames / FPS))
        if remaining > 0.08:
            hold_path = segment_dir / "hold.mp4"
            _static_intro_clip(usable[-1], hold_path, remaining)
            segments.append(hold_path)

        if len(segments) == 1:
            shutil.copy2(segments[0], out_path)
        else:
            _concat_video(segments, out_path)
    finally:
        list_path = out_path.with_suffix(".txt")
        _safe_unlink(list_path)
        _safe_rmtree(segment_dir)


def _feather_wipe_transition(
    prev_path: Path,
    next_path: Path,
    out_path: Path,
    duration: float,
    direction: str,
) -> None:
    duration = max(0.08, float(duration))
    frames = max(2, int(round(duration * FPS)))
    duration = frames / FPS
    feather = FLASH_CUT_MASK_FEATHER
    axis = "Y" if direction == "vertical" else "X"
    size = H if direction == "vertical" else W
    edge_expr = f"(-{feather}+({size + feather * 2})*N/{max(frames - 1, 1)})"
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
    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(prev_path),
        "-loop", "1", "-i", str(next_path),
        "-f", "lavfi", "-i", f"nullsrc=s={W}x{H}:r={FPS}:d={duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[v]", "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])


def _feather_flash_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float, direction: str) -> None:
    image_seconds = _intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration)
        return

    effect_duration = min(duration, len(usable) * image_seconds)
    segment_dir = out_path.parent / f"{out_path.stem}_{direction}_flash"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    elapsed = 0.0

    try:
        first_path = segment_dir / "flash_01.mp4"
        first_duration = min(image_seconds, effect_duration)
        _static_intro_clip(usable[0], first_path, first_duration)
        segments.append(first_path)
        elapsed += first_duration

        for idx in range(1, len(usable)):
            if elapsed >= effect_duration - 0.03:
                break
            segment_path = segment_dir / f"flash_{idx + 1:02d}.mp4"
            segment_duration = min(image_seconds, max(0.03, effect_duration - elapsed))
            _feather_wipe_transition(usable[idx - 1], usable[idx], segment_path, segment_duration, direction)
            segments.append(segment_path)
            elapsed += segment_duration

        remaining = max(0.0, duration - elapsed)
        if remaining > 0.08:
            hold_path = segment_dir / "hold.mp4"
            _static_intro_clip(usable[-1], hold_path, remaining)
            segments.append(hold_path)

        if len(segments) == 1:
            shutil.copy2(segments[0], out_path)
        else:
            _concat_video(segments, out_path)
    finally:
        list_path = out_path.with_suffix(".txt")
        _safe_unlink(list_path)
        _safe_rmtree(segment_dir)


def _staggered_mask_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float) -> None:
    image_seconds = _intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration)
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
        _run([
            *cmd,
            "-filter_complex", ";".join(filters) + f";[{current}]format=yuv420p[v]",
            "-map", "[v]", "-frames:v", str(frames),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(relay_path),
        ])
        if hold_path:
            _static_intro_clip(usable[-1], hold_path, duration - effect_duration)
            _concat_video([relay_path, hold_path], out_path)
    finally:
        if hold_path:
            _safe_rmtree(hold_path.parent)


def _fast_cut_clip(image_paths: list[Path], out_path: Path, duration: float, image_seconds: float) -> None:
    image_seconds = _intro_image_seconds(image_seconds)
    usable = [path for path in image_paths[:FAST_CUT_MAX_IMAGES] if path.exists()]
    if duration <= 0.4 or len(usable) < 2:
        _static_intro_clip(usable[0] if usable else image_paths[0], out_path, duration)
        return

    effect_duration = min(duration, len(usable) * image_seconds)
    remaining = max(0.0, duration - effect_duration)

    segment_dir = out_path.parent / f"{out_path.stem}_intro"
    segment_dir.mkdir(parents=True, exist_ok=True)
    mask_path = segment_dir / "linear_mask.mp4"
    hold_path = segment_dir / "hold.mp4"
    segments = [mask_path]

    try:
        _linear_mask_intro_clip(usable, mask_path, effect_duration, image_seconds)
        if remaining > 0.08:
            _static_intro_clip(usable[-1], hold_path, remaining)
            segments.append(hold_path)
        if len(segments) == 1:
            shutil.copy2(mask_path, out_path)
        else:
            _concat_video(segments, out_path)
    finally:
        list_path = out_path.with_suffix(".txt")
        _safe_unlink(list_path)
        _safe_rmtree(segment_dir)


def _concat(clips: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".txt")
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)])


def _concat_video(clips: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".txt")
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
    try:
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-an", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(out_path),
        ])
    finally:
        _safe_unlink(list_path)


def _concat_audio(files: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".audio.txt")
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in files), encoding="utf-8")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-vn", "-c:a", "libmp3lame", "-b:a", "192k", str(out_path),
    ])


def _video_filter(ass: Path, intro_template: str, duration: float) -> str:
    ass_arg = _ffmpeg_path_arg(ass)
    return f"ass='{ass_arg}'"


def _final(
    video: Path,
    audio: Path,
    ass: Path,
    out_path: Path,
    duration: float,
    intro_template: str = "none",
    bgm_path: Path | None = None,
    sfx_path: Path | None = None,
    sfx_offsets: list[float] | None = None,
) -> None:
    intro_template = intro_template if intro_template in INTRO_TEMPLATES else "none"
    vf = _video_filter(ass, intro_template, duration)
    sfx_offsets = [offset for offset in (sfx_offsets or []) if 0 <= float(offset) < duration]
    if bgm_path or (sfx_path and sfx_offsets):
        cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(audio)]
        filters = [f"[0:v]{vf}[vout]", "[1:a]volume=1.0[a0]"]
        audio_labels = ["[a0]"]
        next_input = 2

        if bgm_path:
            cmd.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
            filters.append(f"[{next_input}:a]volume=0.18,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[bgm]")
            audio_labels.append("[bgm]")
            next_input += 1

        if sfx_path:
            for idx, offset in enumerate(sfx_offsets):
                cmd.extend(["-i", str(sfx_path)])
                delay_ms = max(0, int(round(float(offset) * 1000)))
                label = f"sfx{idx}"
                filters.append(f"[{next_input}:a]volume=0.72,adelay={delay_ms}:all=1[{label}]")
                audio_labels.append(f"[{label}]")
                next_input += 1

        filters.append(f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:duration=first:dropout_transition=2[aout]")
        _run([
            *cmd,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]", "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(out_path),
        ])
        return
    _run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-vf", vf,
        "-map", "0:v", "-map", "1:a", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(out_path),
    ])


def _cleanup_intermediate(project_dir: Path, audio_dir: Path, clips_dir: Path, merged_path: Path) -> None:
    for path in [audio_dir, clips_dir]:
        if path.exists():
            shutil.rmtree(path)
    for path in [
        merged_path,
        merged_path.with_suffix(".txt"),
        (project_dir / "voice.audio.txt"),
    ]:
        if path.exists():
            path.unlink()


def _workspace_project_id(value: str | None) -> str:
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw:
        return ""
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} or ":" in part for part in parts):
        raise RenderError("Invalid project_id")
    return "/".join(parts)


def normalize_story(story: dict[str, Any]) -> dict[str, Any]:
    title = str(story.get("title") or "人生副本样片")
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise RenderError("story.shots must be a non-empty array")
    normalized = []
    for i, shot in enumerate(shots, 1):
        if not isinstance(shot, dict):
            raise RenderError(f"shot {i} must be an object")
        voiceover = str(shot.get("voiceover") or shot.get("narration") or shot.get("text") or "").strip()
        if not voiceover:
            raise RenderError(f"shot {i} missing voiceover")
        normalized.append({
            "id": int(shot.get("id") or i),
            "voiceover": voiceover,
            "visual": str(shot.get("visual") or shot.get("image_prompt") or voiceover),
            "punch": str(shot.get("punch") or shot.get("keyword") or f"镜头{i}"),
            "image_path": str(shot.get("image_path") or "").strip(),
            "image_prompt": str(shot.get("image_prompt") or ""),
            "video_prompt": str(shot.get("video_prompt") or ""),
        })
    return {"title": title, "style_preset": str(story.get("style_preset") or DEFAULT_STYLE), "shots": normalized}


def _workspace_path_from_url(url: str) -> Path | None:
    prefix = "/workspace/"
    if not isinstance(url, str) or not url.startswith(prefix):
        return None
    candidate = (WORKSPACE / url[len(prefix):]).resolve()
    try:
        candidate.relative_to(WORKSPACE.resolve())
    except ValueError:
        return None
    return candidate


def _project_image_for_index(project_dir: Path, index: int) -> Path | None:
    stem = f"shot_{index:02d}"
    image_dir = project_dir / "images"
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = image_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    matches = sorted(image_dir.glob(f"{stem}.*"))
    return matches[0] if matches else None


def _shot_image_source(
    raw_shot: dict[str, Any],
    normalized_shot: dict[str, Any],
    project_dir: Path,
    index: int,
) -> Path | None:
    candidates: list[Path] = []
    raw_path = str(raw_shot.get("image_path") or normalized_shot.get("image_path") or "").strip()
    if raw_path:
        candidates.append(Path(raw_path))
    raw_url = str(raw_shot.get("image_url") or "").strip()
    workspace_path = _workspace_path_from_url(raw_url)
    if workspace_path:
        candidates.append(workspace_path)
    project_image = _project_image_for_index(project_dir, index)
    if project_image:
        candidates.append(project_image)
    return next((path for path in candidates if path.exists()), None)


def _preview_image_paths(
    original_story: dict[str, Any],
    normalized_story: dict[str, Any],
    project_dir: Path,
    preview_dir: Path,
) -> list[Path]:
    source_shots = original_story.get("shots") if isinstance(original_story.get("shots"), list) else []
    normalized_shots = normalized_story["shots"][:FAST_CUT_MAX_IMAGES]
    image_paths: list[Path] = []
    for idx, normalized_shot in enumerate(normalized_shots, 1):
        raw_shot = source_shots[idx - 1] if idx - 1 < len(source_shots) and isinstance(source_shots[idx - 1], dict) else {}
        source = _shot_image_source(raw_shot, normalized_shot, project_dir, idx)
        if source:
            image_paths.append(source)
    return image_paths


def render_intro_previews(
    story: dict[str, Any],
    project_id: str | None = None,
    templates: list[str] | None = None,
    duration: float = 3.0,
    image_seconds: float = FAST_CUT_IMAGE_SECONDS,
) -> dict[str, Any]:
    clean = normalize_story(story)
    image_seconds = _intro_image_seconds(image_seconds)
    project_id = _workspace_project_id(project_id) or time.strftime("%Y%m%d_%H%M%S_preview_") + uuid.uuid4().hex[:8]
    project_dir = WORKSPACE / project_id
    preview_dir = project_dir / "previews" / "intro_templates"
    preview_dir.mkdir(parents=True, exist_ok=True)

    duration = max(0.2, min(12.0, float(duration or 3.0)))
    requested_templates = templates or INTRO_PREVIEW_TEMPLATES
    valid_templates = [template for template in requested_templates if template in INTRO_TEMPLATES]
    if not valid_templates:
        valid_templates = INTRO_PREVIEW_TEMPLATES

    image_paths = _preview_image_paths(story, clean, project_dir, preview_dir)
    if not image_paths:
        raise RenderError("请先生成至少 1 张项目图片后再预览开头模板")

    items: list[dict[str, str]] = []
    for template in valid_templates:
        out_path = preview_dir / f"{template}.mp4"
        if template == FAST_CUT_TEMPLATE:
            _fast_cut_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds)
        elif template == EXPAND_CUT_TEMPLATE:
            _expand_cut_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds)
        elif template == FLASH_HORIZONTAL_TEMPLATE:
            _feather_flash_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, "horizontal")
        elif template == FLASH_VERTICAL_TEMPLATE:
            _feather_flash_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, "vertical")
        elif template == STAGGERED_MASK_TEMPLATE:
            _staggered_mask_clip(image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds)
        else:
            _clip(image_paths[0], out_path, duration, "none")
        items.append({
            "id": template,
            "video": f"/workspace/{project_id}/previews/intro_templates/{template}.mp4",
        })
    preview_image_dir = preview_dir / "images"
    if preview_image_dir.exists():
        shutil.rmtree(preview_image_dir)
    return {
        "project_id": project_id,
        "duration_sec": duration,
        "image_seconds": image_seconds,
        "items": items,
    }


def render_story(
    story: dict[str, Any],
    voice: str = "zh-CN-YunxiNeural",
    rate: str = "+12%",
    tts_config: TtsConfig | None = None,
    project_id: str | None = None,
    cleanup_intermediate: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    intro_template: str = "none",
    bgm_id: str | None = None,
    intro_image_seconds: float = FAST_CUT_IMAGE_SECONDS,
) -> dict[str, Any]:
    def report(progress: float, stage: str, detail: str = "", **extra: Any) -> None:
        if not progress_callback:
            return
        payload = {
            "progress": max(0.0, min(0.99, float(progress))),
            "stage": stage,
            "detail": detail,
            **extra,
        }
        progress_callback(payload)

    project_id = _workspace_project_id(project_id) or time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    project_dir = WORKSPACE / project_id
    images = project_dir / "images"
    audio_dir = project_dir / "audio"
    clips_dir = project_dir / "clips"
    images.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    report(0.02, "准备渲染", "检查分镜和项目目录")
    clean = normalize_story(story)
    shots = clean["shots"]
    shot_total = len(shots)
    script_path = project_dir / "script.json"
    voice_path = project_dir / "voice.mp3"
    srt_path = project_dir / "subtitle.srt"
    ass_path = project_dir / "subtitle.ass"
    merged_path = project_dir / "storyboard_merged.mp4"
    final_path = project_dir / "final.mp4"
    intro_template = intro_template if intro_template in INTRO_TEMPLATES else "none"
    intro_image_seconds = _intro_image_seconds(intro_image_seconds)
    bgm_path = resolve_bgm_path(bgm_id)
    reveal_sfx_path = default_reveal_sfx_path(intro_template)
    tts = tts_config or TtsConfig.from_payload({"voice": voice, "rate": rate})

    script_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    voice_parts: list[Path] = []
    cursor = 0.0
    for idx, shot in enumerate(shots):
        report(
            0.08 + (idx / max(shot_total, 1)) * 0.3,
            "生成配音",
            f"正在生成第 {idx + 1}/{shot_total} 段配音",
            current=idx + 1,
            total=shot_total,
        )
        part_path = audio_dir / f"shot_{idx + 1:02d}.mp3"
        asyncio.run(synthesize_tts(str(shot["voiceover"]), part_path, tts))
        part_duration = _duration(part_path)
        shot["start"] = cursor
        cursor += part_duration
        shot["end"] = cursor
        if not cleanup_intermediate:
            shot["audio_path"] = str(part_path.resolve())
        voice_parts.append(part_path)
    report(0.4, "合并配音", "正在合并全部配音片段")
    _concat_audio(voice_parts, voice_path)
    total = _duration(voice_path)
    if shots:
        shots[-1]["end"] = total
    report(0.46, "生成字幕", "正在写入 SRT 和 ASS 字幕")
    _write_subtitles(shots, srt_path, ass_path)
    script_path.write_text(json.dumps({**clean, "audio_duration": total}, ensure_ascii=False, indent=2), encoding="utf-8")

    image_paths: list[Path] = []
    source_shots = story.get("shots") if isinstance(story.get("shots"), list) else []
    for idx, shot in enumerate(shots):
        report(
            0.5 + (idx / max(shot_total, 1)) * 0.12,
            "准备镜头图片",
            f"正在准备第 {idx + 1}/{shot_total} 张镜头图片",
            current=idx + 1,
            total=shot_total,
        )
        img_path = images / f"shot_{idx + 1:02d}.png"
        raw_shot = source_shots[idx] if idx < len(source_shots) and isinstance(source_shots[idx], dict) else {}
        provided = _shot_image_source(raw_shot, shot, project_dir, idx + 1)
        if provided and provided.resolve() != img_path.resolve():
            shutil.copy2(provided, img_path)
        elif provided and provided.exists():
            pass
        else:
            render_placeholder_image(shot, img_path, idx, clean["title"])
        image_paths.append(img_path)

    clips: list[Path] = []
    for idx, shot in enumerate(shots):
        report(
            0.62 + (idx / max(shot_total, 1)) * 0.2,
            "生成镜头视频",
            f"正在生成第 {idx + 1}/{shot_total} 个镜头",
            current=idx + 1,
            total=shot_total,
        )
        img_path = image_paths[idx]
        clip_path = clips_dir / f"shot_{idx + 1:02d}.mp4"
        clip_duration = float(shot["end"]) - float(shot["start"])
        if idx == 0 and intro_template == FAST_CUT_TEMPLATE:
            _fast_cut_clip(image_paths[:FAST_CUT_MAX_IMAGES], clip_path, clip_duration, intro_image_seconds)
        elif idx == 0 and intro_template == EXPAND_CUT_TEMPLATE:
            _expand_cut_clip(image_paths[:FAST_CUT_MAX_IMAGES], clip_path, clip_duration, intro_image_seconds)
        elif idx == 0 and intro_template == FLASH_HORIZONTAL_TEMPLATE:
            _feather_flash_clip(image_paths[:FAST_CUT_MAX_IMAGES], clip_path, clip_duration, intro_image_seconds, "horizontal")
        elif idx == 0 and intro_template == FLASH_VERTICAL_TEMPLATE:
            _feather_flash_clip(image_paths[:FAST_CUT_MAX_IMAGES], clip_path, clip_duration, intro_image_seconds, "vertical")
        elif idx == 0 and intro_template == STAGGERED_MASK_TEMPLATE:
            _staggered_mask_clip(image_paths[:FAST_CUT_MAX_IMAGES], clip_path, clip_duration, intro_image_seconds)
        else:
            _clip(img_path, clip_path, clip_duration, intro_template if idx == 0 else "none")
        clips.append(clip_path)
    report(0.84, "合并镜头", "正在合并镜头视频")
    _concat(clips, merged_path)
    report(0.9, "导出成片", "正在压制字幕、配音和 BGM" if bgm_path else "正在压制字幕和音频")
    _final(
        merged_path,
        voice_path,
        ass_path,
        final_path,
        total,
        intro_template,
        bgm_path,
        reveal_sfx_path,
        [float(shot["start"]) for shot in shots],
    )
    if cleanup_intermediate:
        report(0.98, "清理文件", "正在清理临时渲染文件")
        _cleanup_intermediate(project_dir, audio_dir, clips_dir, merged_path)
    return {
        "project_id": project_id,
        "title": clean["title"],
        "duration_sec": round(total, 2),
        "shots": len(shots),
        "script_json": f"/workspace/{project_id}/script.json",
        "srt": f"/workspace/{project_id}/subtitle.srt",
        "voice": f"/workspace/{project_id}/voice.mp3",
        "video": f"/workspace/{project_id}/final.mp4",
        "cleanup_intermediate": cleanup_intermediate,
        "intro_template": intro_template,
        "intro_image_seconds": intro_image_seconds,
        "tts_provider": tts.provider,
        "bgm": str(bgm_path.resolve()) if bgm_path else "",
        "sfx": str(reveal_sfx_path.resolve()) if reveal_sfx_path else "",
    }
