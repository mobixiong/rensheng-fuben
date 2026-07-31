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

def _import_jianying_draft() -> dict[str, Any]:
    try:
        from pyJianYingDraft import (  # type: ignore
            AudioMaterial,
            AudioSegment,
            ClipSettings,
            DraftFolder,
            TextStyle,
            Timerange,
            TrackType,
            VideoMaterial,
            VideoSegment,
        )
    except ImportError as exc:
        raise RenderError("未安装 pyJianYingDraft，无法导出剪映草稿。请先安装依赖：pip install -r requirements.txt") from exc

    return {
        "AudioMaterial": AudioMaterial,
        "AudioSegment": AudioSegment,
        "ClipSettings": ClipSettings,
        "DraftFolder": DraftFolder,
        "TextStyle": TextStyle,
        "Timerange": Timerange,
        "TrackType": TrackType,
        "VideoMaterial": VideoMaterial,
        "VideoSegment": VideoSegment,
    }

def _slug(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:42] or "人生副本"

def _draft_name(title: str, requested: str = "") -> str:
    base = _slug(requested or title)
    return f"{base}_剪映草稿_{time.strftime('%Y%m%d_%H%M%S')}"

def _time_microseconds(seconds: float) -> int:
    return max(0, int(round(float(seconds) * 1_000_000)))

def _duration_microseconds(seconds: float) -> int:
    return max(1, int(round(float(seconds) * 1_000_000)))

def _copy_asset(source: Path, target_dir: Path, target_name: str | None = None) -> Path:
    if not source.exists() or source.stat().st_size <= 0:
        raise RenderError(f"素材文件不存在或为空：{source}")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (target_name or source.name)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target

def _load_script(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RenderError("未找到渲染脚本 script.json，无法导出剪映草稿。")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RenderError("script.json 无法解析，无法导出剪映草稿。") from exc
    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        raise RenderError("script.json 中没有可导出的分镜。")
    return data

def _shot_image_path(target_project_dir: Path, index: int) -> Path:
    stem = f"shot_{index:02d}"
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = target_project_dir / "images" / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    matches = sorted((target_project_dir / "images").glob(f"{stem}.*"))
    if matches:
        return matches[0]
    raise RenderError(f"未找到第 {index} 个镜头图片，无法导出剪映草稿。")

def _shot_audio_path(audio_dir: Path, index: int) -> Path | None:
    stem = f"shot_{index:02d}"
    for suffix in (".mp3", ".wav", ".m4a", ".aac", ".flac"):
        candidate = audio_dir / f"{stem}{suffix}"
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    matches = sorted(path for path in audio_dir.glob(f"{stem}.*") if path.is_file() and path.stat().st_size > 0)
    return matches[0] if matches else None

def _material_fill_scale(material: Any, canvas_size: tuple[int, int]) -> float:
    material_width = max(1, int(getattr(material, "width", canvas_size[0]) or canvas_size[0]))
    material_height = max(1, int(getattr(material, "height", canvas_size[1]) or canvas_size[1]))
    return max(canvas_size[0] / material_width, canvas_size[1] / material_height)

