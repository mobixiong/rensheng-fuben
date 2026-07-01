import asyncio
import hashlib
import json
import shutil
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .audio_assets import resolve_bgm_path, resolve_intro_sfx_path
from .errors import RenderError
from .ffmpeg_utils import ffmpeg_path_arg, media_duration, run_command, safe_unlink, video_dimensions
from .intro_templates import (
    FAST_CUT_IMAGE_SECONDS,
    FAST_CUT_MAX_IMAGES,
    INTRO_PREVIEW_TEMPLATES,
    INTRO_TEMPLATES,
    normalize_intro_image_seconds,
    render_intro_template,
    render_still_clip,
)
from .paths import WORKSPACE
from .render_constants import H, W, render_size
from .subtitle_renderer import SUBTITLE_RENDER_VERSION, write_subtitles
from .tts_adapter import TtsConfig, synthesize_tts


DEFAULT_STYLE = (
    "中国网络科普动画风格，赛璐璐着色，粗黑描边，干净利落的矢量线条，"
    "2D平面动画，高对比阴影，高饱和色调，少量关键词花字。主角是无脸圆形白色光头角色，"
    "极简点状眼睛，夸张眉毛，表情包风格，穿连帽衫或制服，Q版但不过度幼稚。"
)


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


def render_placeholder_image(
    shot: dict[str, Any],
    out_path: Path,
    idx: int,
    title: str,
    size: tuple[int, int] | None = None,
) -> None:
    W, H = size or render_size()
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


def _concat(clips: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".txt")
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
    run_command(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)])


def _concat_audio(files: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".audio.txt")
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in files), encoding="utf-8")
    run_command([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-vn", "-c:a", "libmp3lame", "-b:a", "192k", str(out_path),
    ])


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_media_duration(path: Path) -> float | None:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return None
        duration = media_duration(path)
    except Exception:
        return None
    return duration if duration > 0 else None


def _valid_audio(path: Path) -> bool:
    duration = _safe_media_duration(path)
    return duration is not None and duration > 0.05


def _valid_image(path: Path) -> bool:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        with Image.open(path) as img:
            img.verify()
    except Exception:
        return False
    return True


def _valid_video(path: Path, size: tuple[int, int] | None = None, min_duration: float = 0.05) -> bool:
    duration = _safe_media_duration(path)
    if duration is None or duration < min_duration:
        return False
    if size is None:
        return True
    try:
        return video_dimensions(path) == size
    except Exception:
        return False


def _render_fingerprint(
    clean: dict[str, Any],
    image_size: str,
    canvas_size: tuple[int, int],
    intro_template: str,
    intro_image_seconds: float,
    bgm_id: str | None,
    intro_sfx_id: str | None,
    tts: TtsConfig,
) -> str:
    tts_payload = asdict(tts)
    tts_payload["api_key"] = "***" if tts_payload.get("api_key") else ""
    return _sha256_json({
        "story": clean,
        "image_size": image_size,
        "canvas_size": canvas_size,
        "intro_template": intro_template,
        "intro_image_seconds": intro_image_seconds,
        "bgm_id": bgm_id or "none",
        "intro_sfx_id": intro_sfx_id or "default",
        "tts": tts_payload,
        "pipeline": 2,
    })


def _read_resume_manifest(path: Path, fingerprint: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if data.get("fingerprint") != fingerprint:
        return {
            "previous_fingerprint": data.get("fingerprint"),
            "stages": data.get("stages") if isinstance(data.get("stages"), dict) else {},
        }
    return data


def _write_resume_manifest(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _tts_signature(text: str, tts: TtsConfig) -> str:
    payload = asdict(tts)
    payload["api_key"] = "***" if payload.get("api_key") else ""
    return _sha256_json({"text": text, "tts": payload})


def _asset_signature(path: Path | None) -> dict[str, str]:
    if not path:
        return {"path": "", "sha256": ""}
    return {
        "path": str(path.resolve()),
        "sha256": _file_hash(path) if path.exists() else "",
    }


def _stage_done(
    manifest: dict[str, Any],
    stage: str,
    key: str,
    signature: str,
    path: Path,
    validator: Callable[[Path], bool],
) -> bool:
    entry = ((manifest.get("stages") or {}).get(stage) or {}).get(key) or {}
    if entry.get("signature") == signature and validator(path):
        return True
    safe_unlink(path)
    return False


def _mark_stage(
    manifest_path: Path,
    manifest: dict[str, Any],
    stage: str,
    key: str,
    signature: str,
    path: Path,
    **extra: Any,
) -> None:
    stages = manifest.setdefault("stages", {})
    bucket = stages.setdefault(stage, {})
    bucket[key] = {
        "signature": signature,
        "path": str(path.resolve()),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **extra,
    }
    _write_resume_manifest(manifest_path, manifest)


def _video_filter(ass: Path, intro_template: str, duration: float) -> str:
    ass_arg = ffmpeg_path_arg(ass)
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
        run_command([
            *cmd,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]", "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(out_path),
        ])
        return
    run_command([
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
        subtitle_chunks = shot.get("subtitle_chunks")
        if isinstance(subtitle_chunks, list):
            subtitle_chunks = [
                str(item.get("text") if isinstance(item, dict) else item).strip()
                for item in subtitle_chunks
                if str(item.get("text") if isinstance(item, dict) else item).strip()
            ]
        else:
            subtitle_chunks = []
        normalized.append({
            "id": int(shot.get("id") or i),
            "voiceover": voiceover,
            "visual": str(shot.get("visual") or shot.get("image_prompt") or voiceover),
            "punch": str(shot.get("punch") or shot.get("keyword") or f"镜头{i}"),
            "image_path": str(shot.get("image_path") or "").strip(),
            "image_prompt": str(shot.get("image_prompt") or ""),
            "video_prompt": str(shot.get("video_prompt") or ""),
            "subtitle_chunks": subtitle_chunks,
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
    image_size: str = "9:16",
) -> dict[str, Any]:
    clean = normalize_story(story)
    image_seconds = normalize_intro_image_seconds(image_seconds)
    canvas_size = render_size(image_size or story.get("image_size"))
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
        render_intro_template(template, image_paths[:FAST_CUT_MAX_IMAGES], out_path, duration, image_seconds, canvas_size)
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
    intro_sfx_id: str | None = "default",
    intro_image_seconds: float = FAST_CUT_IMAGE_SECONDS,
    image_size: str = "9:16",
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
    canvas_size = render_size(image_size or story.get("image_size"))
    intro_template = intro_template if intro_template in INTRO_TEMPLATES else "none"
    intro_image_seconds = normalize_intro_image_seconds(intro_image_seconds)
    bgm_path = resolve_bgm_path(bgm_id)
    intro_sfx_path = resolve_intro_sfx_path(intro_sfx_id, intro_template)
    tts = tts_config or TtsConfig.from_payload({"voice": voice, "rate": rate})
    fingerprint = _render_fingerprint(
        clean,
        image_size,
        canvas_size,
        intro_template,
        intro_image_seconds,
        bgm_id,
        intro_sfx_id,
        tts,
    )
    manifest_path = project_dir / "render_resume.json"
    manifest = _read_resume_manifest(manifest_path, fingerprint) or {
        "fingerprint": fingerprint,
        "project_id": project_id,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stages": {},
    }
    manifest.update({
        "fingerprint": fingerprint,
        "project_id": project_id,
        "image_size": image_size,
        "video_width": canvas_size[0],
        "video_height": canvas_size[1],
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _write_resume_manifest(manifest_path, manifest)

    shots = clean["shots"]
    shot_total = len(shots)
    script_path = project_dir / "script.json"
    voice_path = project_dir / "voice.mp3"
    srt_path = project_dir / "subtitle.srt"
    ass_path = project_dir / "subtitle.ass"
    merged_path = project_dir / "storyboard_merged.mp4"
    final_path = project_dir / "final.mp4"

    script_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    voice_parts: list[Path] = []
    cursor = 0.0
    for idx, shot in enumerate(shots):
        part_path = audio_dir / f"shot_{idx + 1:02d}.mp3"
        part_signature = _tts_signature(str(shot["voiceover"]), tts)
        reused_audio = _stage_done(manifest, "tts", f"shot_{idx + 1:02d}", part_signature, part_path, _valid_audio)
        report(
            0.08 + (idx / max(shot_total, 1)) * 0.3,
            "生成配音",
            f"{'复用' if reused_audio else '正在生成'}第 {idx + 1}/{shot_total} 段配音",
            current=idx + 1,
            total=shot_total,
            reused=reused_audio,
        )
        if not reused_audio:
            asyncio.run(synthesize_tts(str(shot["voiceover"]), part_path, tts))
            if not _valid_audio(part_path):
                raise RenderError(f"TTS output is invalid: {part_path}")
            _mark_stage(manifest_path, manifest, "tts", f"shot_{idx + 1:02d}", part_signature, part_path)
        part_duration = media_duration(part_path)
        shot["start"] = cursor
        cursor += part_duration
        shot["end"] = cursor
        if not cleanup_intermediate:
            shot["audio_path"] = str(part_path.resolve())
        voice_parts.append(part_path)
    voice_signature = _sha256_json({
        "parts": [
            {"path": str(path.resolve()), "sha256": _file_hash(path)}
            for path in voice_parts
        ],
    })
    reused_voice = _stage_done(manifest, "audio", "voice", voice_signature, voice_path, _valid_audio)
    report(0.4, "合并配音", "复用已合并配音" if reused_voice else "正在合并全部配音片段", reused=reused_voice)
    if not reused_voice:
        _concat_audio(voice_parts, voice_path)
        if not _valid_audio(voice_path):
            raise RenderError(f"Merged audio is invalid: {voice_path}")
        _mark_stage(manifest_path, manifest, "audio", "voice", voice_signature, voice_path)
    total = media_duration(voice_path)
    if shots:
        shots[-1]["end"] = total
    subtitle_signature = _sha256_json({
        "subtitle_render_version": SUBTITLE_RENDER_VERSION,
        "shots": [
            {
                "voiceover": shot["voiceover"],
                "subtitle_chunks": shot.get("subtitle_chunks") or [],
                "start": shot["start"],
                "end": shot["end"],
            }
            for shot in shots
        ],
        "size": canvas_size,
    })
    subtitle_entry = ((manifest.get("stages") or {}).get("subtitle") or {}).get("ass") or {}
    reused_subtitle = (
        subtitle_entry.get("signature") == subtitle_signature
        and srt_path.exists()
        and ass_path.exists()
        and srt_path.stat().st_size > 0
        and ass_path.stat().st_size > 0
    )
    report(0.46, "生成字幕", "复用已生成字幕" if reused_subtitle else "正在写入 SRT 和 ASS 字幕", reused=reused_subtitle)
    if not reused_subtitle:
        safe_unlink(srt_path)
        safe_unlink(ass_path)
        write_subtitles(shots, srt_path, ass_path, canvas_size)
        _mark_stage(manifest_path, manifest, "subtitle", "ass", subtitle_signature, ass_path, srt=str(srt_path.resolve()))
    script_path.write_text(json.dumps({**clean, "audio_duration": total}, ensure_ascii=False, indent=2), encoding="utf-8")

    image_paths: list[Path] = []
    image_signatures: list[dict[str, str]] = []
    source_shots = story.get("shots") if isinstance(story.get("shots"), list) else []
    for idx, shot in enumerate(shots):
        img_path = images / f"shot_{idx + 1:02d}.png"
        raw_shot = source_shots[idx] if idx < len(source_shots) and isinstance(source_shots[idx], dict) else {}
        provided = _shot_image_source(raw_shot, shot, project_dir, idx + 1)
        report(
            0.5 + (idx / max(shot_total, 1)) * 0.12,
            "准备镜头图片",
            f"正在准备第 {idx + 1}/{shot_total} 张镜头图片",
            current=idx + 1,
            total=shot_total,
        )
        if provided and provided.resolve() != img_path.resolve():
            shutil.copy2(provided, img_path)
        elif provided and provided.exists():
            pass
        elif not _valid_image(img_path):
            render_placeholder_image(shot, img_path, idx, clean["title"], canvas_size)
        if not _valid_image(img_path):
            raise RenderError(f"Shot image is invalid: {img_path}")
        image_signature = _asset_signature(img_path)
        _mark_stage(
            manifest_path,
            manifest,
            "image",
            f"shot_{idx + 1:02d}",
            _sha256_json({"image": image_signature, "size": canvas_size}),
            img_path,
            sha256=image_signature["sha256"],
        )
        image_paths.append(img_path)
        image_signatures.append(image_signature)

    clips: list[Path] = []
    for idx, shot in enumerate(shots):
        img_path = image_paths[idx]
        clip_path = clips_dir / f"shot_{idx + 1:02d}.mp4"
        clip_duration = float(shot["end"]) - float(shot["start"])
        is_intro_clip = idx == 0 and intro_template != "none"
        clip_signature = _sha256_json({
            "shot": shot,
            "image": image_signatures[idx],
            "intro_images": image_signatures[:FAST_CUT_MAX_IMAGES] if is_intro_clip else [],
            "duration": round(clip_duration, 3),
            "size": canvas_size,
            "intro_template": intro_template if is_intro_clip else "none",
            "intro_image_seconds": intro_image_seconds if is_intro_clip else 0,
        })
        reused_clip = _stage_done(
            manifest,
            "clip",
            f"shot_{idx + 1:02d}",
            clip_signature,
            clip_path,
            lambda path: _valid_video(path, canvas_size, min_duration=max(0.05, min(clip_duration, 0.5))),
        )
        report(
            0.62 + (idx / max(shot_total, 1)) * 0.2,
            "生成镜头视频",
            f"{'复用' if reused_clip else '正在生成'}第 {idx + 1}/{shot_total} 个镜头",
            current=idx + 1,
            total=shot_total,
            reused=reused_clip,
        )
        if not reused_clip:
            if is_intro_clip:
                render_intro_template(intro_template, image_paths[:FAST_CUT_MAX_IMAGES], clip_path, clip_duration, intro_image_seconds, canvas_size)
            else:
                render_still_clip(img_path, clip_path, clip_duration, canvas_size)
            if not _valid_video(clip_path, canvas_size, min_duration=max(0.05, min(clip_duration, 0.5))):
                raise RenderError(f"Shot clip is invalid: {clip_path}")
            _mark_stage(manifest_path, manifest, "clip", f"shot_{idx + 1:02d}", clip_signature, clip_path)
        clips.append(clip_path)
    merged_signature = _sha256_json({
        "clips": [{"path": str(path.resolve()), "sha256": _file_hash(path)} for path in clips],
        "size": canvas_size,
    })
    reused_merged = _stage_done(
        manifest,
        "video",
        "merged",
        merged_signature,
        merged_path,
        lambda path: _valid_video(path, canvas_size, min_duration=max(0.05, min(total, 0.5))),
    )
    report(0.84, "合并镜头", "复用已合并镜头视频" if reused_merged else "正在合并镜头视频", reused=reused_merged)
    if not reused_merged:
        _concat(clips, merged_path)
        if not _valid_video(merged_path, canvas_size, min_duration=max(0.05, min(total, 0.5))):
            raise RenderError(f"Merged video is invalid: {merged_path}")
        _mark_stage(manifest_path, manifest, "video", "merged", merged_signature, merged_path)
    extra_audio_labels = [label for label, enabled in [("BGM", bgm_path), ("开头音效", intro_sfx_path)] if enabled]
    detail = f"正在压制字幕、配音和{'、'.join(extra_audio_labels)}" if extra_audio_labels else "正在压制字幕和音频"
    final_signature = _sha256_json({
        "merged": _asset_signature(merged_path),
        "voice": _asset_signature(voice_path),
        "ass": _asset_signature(ass_path),
        "bgm": _asset_signature(bgm_path),
        "intro_sfx": _asset_signature(intro_sfx_path),
        "duration": round(total, 3),
        "intro_template": intro_template,
        "size": canvas_size,
    })
    reused_final = _stage_done(
        manifest,
        "video",
        "final",
        final_signature,
        final_path,
        lambda path: _valid_video(path, canvas_size, min_duration=max(0.05, min(total, 0.5))),
    )
    report(0.9, "导出成片", "复用已导出成片" if reused_final else detail, reused=reused_final)
    if not reused_final:
        _final(
            merged_path,
            voice_path,
            ass_path,
            final_path,
            total,
            intro_template,
            bgm_path,
            intro_sfx_path,
            [0.0],
        )
        if not _valid_video(final_path, canvas_size, min_duration=max(0.05, min(total, 0.5))):
            raise RenderError(f"Final video is invalid: {final_path}")
        _mark_stage(manifest_path, manifest, "video", "final", final_signature, final_path)
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
        "image_size": image_size,
        "video_width": canvas_size[0],
        "video_height": canvas_size[1],
        "tts_provider": tts.provider,
        "bgm": str(bgm_path.resolve()) if bgm_path else "",
        "intro_sfx": str(intro_sfx_path.resolve()) if intro_sfx_path else "",
    }
