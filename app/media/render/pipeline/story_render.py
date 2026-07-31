from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.media.audio.assets import resolve_bgm_path, resolve_intro_sfx_path
from app.core.errors import RenderError
from app.media.render.ffmpeg_utils import media_duration, safe_unlink
from app.media.render.intro_templates import (
    FAST_CUT_IMAGE_SECONDS,
    FAST_CUT_MAX_IMAGES,
    INTRO_TEMPLATES,
    normalize_intro_image_seconds,
    render_intro_template,
    render_still_clip,
)
from app.core.paths import WORKSPACE
from app.media.render.constants import render_size
from app.media.render.subtitle_renderer import SUBTITLE_RENDER_VERSION, write_subtitles
from app.providers.tts.adapter import TtsConfig, synthesize_tts

from .final_export import _cleanup_intermediate, _final
from .media_ops import _concat, _concat_audio, _file_hash, _sha256_json, _valid_audio, _valid_image, _valid_video
from .resume import _asset_signature, _mark_stage, _read_resume_manifest, _render_fingerprint, _stage_done, _write_resume_manifest
from .story_model import _public_project_id, _shot_image_source, _workspace_project_id, _workspace_project_ref, normalize_story
from .style import render_placeholder_image


def render_story(
    story: dict[str, Any],
    voice: str = "zh-CN-YunxiNeural",
    rate: str = "+12%",
    tts_config: TtsConfig | None = None,
    project_id: str | None = None,
    cleanup_intermediate: bool = True,
    force_render: bool = False,
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
    project_ref = _workspace_project_ref(project_id)
    public_project_id = _public_project_id(project_ref)
    project_dir = WORKSPACE / project_ref
    workspace_url = f"/workspace/{project_ref}"
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
    reused_final = (not force_render) and _stage_done(
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
        "project_id": public_project_id,
        "title": clean["title"],
        "duration_sec": round(total, 2),
        "shots": len(shots),
        "script_json": f"{workspace_url}/script.json",
        "srt": f"{workspace_url}/subtitle.srt",
        "voice": f"{workspace_url}/voice.mp3",
        "video": f"{workspace_url}/final.mp4",
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

