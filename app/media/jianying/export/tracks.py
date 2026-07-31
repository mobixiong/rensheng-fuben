from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from app.media.audio.assets import resolve_bgm_path, resolve_intro_sfx_path
from app.core.errors import RenderError
from app.media.render.pipeline import render_story
from app.projects.service import project_dir
from app.media.render.constants import FPS, render_size
from app.media.render.validation import validate_ready_for_render
from app.providers.tts.adapter import TtsConfig

from .constants import SFX_TRACK_NAME, SUBTITLE_TRACK_NAME, VIDEO_TRACK_NAME, VOICE_TRACK_NAME
from .utils import _copy_asset, _duration_microseconds, _material_fill_scale, _shot_audio_path, _shot_image_path, _time_microseconds

def _add_video_segments(
    script: Any,
    classes: dict[str, Any],
    target_project_dir: Path,
    draft_assets_dir: Path,
    shots: list[dict[str, Any]],
    canvas_size: tuple[int, int],
) -> int:
    video_assets_dir = draft_assets_dir / "images"
    total_duration = 0
    for index, shot in enumerate(shots, 1):
        try:
            start = _time_microseconds(float(shot["start"]))
            duration = _duration_microseconds(float(shot["end"]) - float(shot["start"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise RenderError(f"第 {index} 个镜头缺少有效时间轴，请先渲染一次后再导出剪映草稿。") from exc

        source = _shot_image_path(target_project_dir, index)
        copied = _copy_asset(source, video_assets_dir, f"shot_{index:02d}{source.suffix.lower()}")
        material = classes["VideoMaterial"](str(copied), material_name=f"镜头 {index:02d}")
        scale = _material_fill_scale(material, canvas_size)
        clip_settings = classes["ClipSettings"](scale_x=scale, scale_y=scale)
        segment = classes["VideoSegment"](material, classes["Timerange"](start, duration), clip_settings=clip_settings, volume=0)
        script.add_segment(segment, VIDEO_TRACK_NAME)
        total_duration = max(total_duration, start + duration)
    return total_duration

def _add_voice_segments(
    script: Any,
    classes: dict[str, Any],
    target_project_dir: Path,
    draft_assets_dir: Path,
    shots: list[dict[str, Any]],
    total_duration: int,
) -> list[str]:
    audio_assets_dir = draft_assets_dir / "audio"
    exported: list[str] = []
    shot_audio_dir = target_project_dir / "audio"
    shot_audio_paths = [_shot_audio_path(shot_audio_dir, index) for index in range(1, len(shots) + 1)]

    if all(path is not None for path in shot_audio_paths):
        for index, (shot, source) in enumerate(zip(shots, shot_audio_paths), 1):
            if source is None:
                continue
            start = _time_microseconds(float(shot["start"]))
            duration = _duration_microseconds(float(shot["end"]) - float(shot["start"]))
            copied = _copy_asset(source, audio_assets_dir, f"voice_{index:02d}{source.suffix.lower()}")
            material = classes["AudioMaterial"](str(copied), material_name=f"配音 {index:02d}")
            source_duration = max(1, min(duration, int(material.duration)))
            segment = classes["AudioSegment"](
                material,
                classes["Timerange"](start, duration),
                source_timerange=classes["Timerange"](0, source_duration),
                volume=1.0,
            )
            script.add_segment(segment, VOICE_TRACK_NAME)
            exported.append(str(copied))
        return exported

    merged_voice = target_project_dir / "voice.mp3"
    if not merged_voice.exists() or merged_voice.stat().st_size <= 0:
        raise RenderError("未找到配音文件 voice.mp3，无法导出剪映草稿。")
    copied = _copy_asset(merged_voice, audio_assets_dir, merged_voice.name)
    material = classes["AudioMaterial"](str(copied), material_name="完整配音")
    duration = min(total_duration, int(material.duration))
    script.add_segment(classes["AudioSegment"](material, classes["Timerange"](0, duration), volume=1.0), VOICE_TRACK_NAME)
    return [str(copied)]

def _add_looped_audio(
    script: Any,
    classes: dict[str, Any],
    track_name: str,
    source: Path,
    draft_assets_dir: Path,
    total_duration: int,
    volume: float,
) -> list[str]:
    copied = _copy_asset(source, draft_assets_dir / "audio", source.name)
    material = classes["AudioMaterial"](str(copied), material_name=source.stem)
    cursor = 0
    material_duration = max(1, int(material.duration))
    exported: list[str] = []
    while cursor < total_duration:
        duration = min(material_duration, total_duration - cursor)
        source_range = classes["Timerange"](0, duration)
        target_range = classes["Timerange"](cursor, duration)
        script.add_segment(classes["AudioSegment"](material, target_range, source_timerange=source_range, volume=volume), track_name)
        exported.append(str(copied))
        cursor += duration
    return exported

def _add_intro_sfx(script: Any, classes: dict[str, Any], source: Path, draft_assets_dir: Path, total_duration: int) -> list[str]:
    copied = _copy_asset(source, draft_assets_dir / "audio", source.name)
    material = classes["AudioMaterial"](str(copied), material_name=source.stem)
    duration = min(total_duration, int(material.duration))
    script.add_segment(classes["AudioSegment"](material, classes["Timerange"](0, duration), volume=0.72), SFX_TRACK_NAME)
    return [str(copied)]

def _add_subtitles(script: Any, classes: dict[str, Any], srt_path: Path) -> bool:
    if not srt_path.exists() or srt_path.stat().st_size <= 0:
        return False
    text_style = classes["TextStyle"](size=6.0, bold=True, align=1, auto_wrapping=True, max_line_width=0.82)
    clip_settings = classes["ClipSettings"](transform_y=-0.78)
    script.import_srt(str(srt_path), SUBTITLE_TRACK_NAME, text_style=text_style, clip_settings=clip_settings)
    return True

