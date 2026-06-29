import asyncio
import json
import math
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import edge_tts
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace"
W, H = 1080, 1920
FPS = 30


DEFAULT_STYLE = (
    "中国网络科普动画风格，赛璐璐着色，粗黑描边，干净利落的矢量线条，"
    "2D平面动画，高对比阴影，高饱和色调，少量关键词花字。主角是无脸圆形白色光头角色，"
    "极简点状眼睛，夸张眉毛，表情包风格，穿连帽衫或制服，Q版但不过度幼稚。"
)


class RenderError(RuntimeError):
    pass


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    if proc.returncode != 0:
        raise RenderError(f"Command failed: {' '.join(cmd)}\n{proc.stderr[-3000:]}")


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


async def _tts(text: str, out_path: Path, voice: str, rate: str) -> None:
    await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(out_path))


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


def _clip(image_path: Path, out_path: Path, duration: float) -> None:
    frames = max(1, int(duration * FPS))
    vf = f"scale={W}:{H},zoompan=z='1+0.035*on/{frames}':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p"
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path),
    ])


def _concat(clips: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".txt")
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)])


def _final(video: Path, audio: Path, ass: Path, out_path: Path, duration: float) -> None:
    ass_arg = ass.resolve().as_posix().replace(":", "\\:")
    _run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-vf", f"ass='{ass_arg}'",
        "-map", "0:v", "-map", "1:a", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(out_path),
    ])


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


def render_story(story: dict[str, Any], voice: str = "zh-CN-YunxiNeural", rate: str = "+12%") -> dict[str, Any]:
    project_id = time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    project_dir = WORKSPACE / project_id
    assets = project_dir / "assets"
    clips_dir = project_dir / "clips"
    assets.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    clean = normalize_story(story)
    shots = clean["shots"]
    script_path = project_dir / "script.json"
    voice_path = project_dir / "voice.mp3"
    srt_path = project_dir / "subtitle.srt"
    ass_path = project_dir / "subtitle.ass"
    merged_path = project_dir / "storyboard_merged.mp4"
    final_path = project_dir / "final.mp4"

    script_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    text = "\n".join(s["voiceover"] for s in shots)
    asyncio.run(_tts(text, voice_path, voice, rate))
    total = _duration(voice_path)
    _allocate(shots, total)
    _write_subtitles(shots, srt_path, ass_path)
    script_path.write_text(json.dumps({**clean, "audio_duration": total}, ensure_ascii=False, indent=2), encoding="utf-8")

    clips: list[Path] = []
    for idx, shot in enumerate(shots):
        img_path = assets / f"shot_{idx + 1:02d}.png"
        provided = Path(shot["image_path"]) if shot.get("image_path") else None
        if provided and provided.exists():
            shutil.copy2(provided, img_path)
        else:
            render_placeholder_image(shot, img_path, idx, clean["title"])
        clip_path = clips_dir / f"shot_{idx + 1:02d}.mp4"
        _clip(img_path, clip_path, float(shot["end"]) - float(shot["start"]))
        clips.append(clip_path)
    _concat(clips, merged_path)
    _final(merged_path, voice_path, ass_path, final_path, total)
    return {
        "project_id": project_id,
        "title": clean["title"],
        "duration_sec": round(total, 2),
        "shots": len(shots),
        "script_json": f"/workspace/{project_id}/script.json",
        "srt": f"/workspace/{project_id}/subtitle.srt",
        "voice": f"/workspace/{project_id}/voice.mp3",
        "video": f"/workspace/{project_id}/final.mp4",
    }
