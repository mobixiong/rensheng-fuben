import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from .audio_assets import resolve_bgm_path, resolve_intro_sfx_path
from .errors import RenderError
from .pipeline import render_story
from .project_service import project_dir
from .render_constants import FPS, render_size
from .render_validation import validate_ready_for_render
from .tts_adapter import TtsConfig


DRAFTS_DIR_NAME = "jianying_drafts"
DRAFT_ASSETS_DIR_NAME = "assets"
VIDEO_TRACK_NAME = "画面"
VOICE_TRACK_NAME = "配音"
BGM_TRACK_NAME = "BGM"
SFX_TRACK_NAME = "开头音效"
SUBTITLE_TRACK_NAME = "字幕"


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


def create_jianying_draft(payload: dict[str, Any], progress_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    def report(progress: float, stage: str, detail: str = "", **extra: Any) -> None:
        if not progress_callback:
            return
        progress_callback({
            "progress": max(0.0, min(0.99, float(progress))),
            "stage": stage,
            "detail": detail,
            **extra,
        })

    story = payload.get("story") if isinstance(payload.get("story"), dict) else {}
    validate_ready_for_render(story)
    classes = _import_jianying_draft()

    report(0.02, "准备剪映草稿", "检查分镜、图片和导出依赖")

    def on_render_progress(event: dict[str, Any]) -> None:
        mapped = 0.05 + max(0.0, min(0.99, float(event.get("progress") or 0))) * 0.68
        report(mapped, str(event.get("stage") or "准备时间轴素材"), str(event.get("detail") or ""), render_event=event)

    render_result = render_story(
        story=story,
        voice=payload.get("voice") or "zh-CN-YunxiNeural",
        rate=payload.get("rate") or "+12%",
        tts_config=TtsConfig.from_payload(payload),
        project_id=payload.get("project_id"),
        cleanup_intermediate=False,
        force_render=False,
        intro_template=payload.get("intro_template") or "none",
        bgm_id=payload.get("bgm_id") or "none",
        intro_image_seconds=payload.get("intro_image_seconds") or 0.3,
        intro_sfx_id=payload.get("intro_sfx_id") or "default",
        image_size=payload.get("image_size") or "9:16",
        progress_callback=on_render_progress,
    )

    public_project_id = str(render_result.get("project_id") or "").strip()
    if not public_project_id:
        raise RenderError("渲染结果缺少 project_id，无法导出剪映草稿。")
    target_project_dir = project_dir(public_project_id)
    script_data = _load_script(target_project_dir / "script.json")
    shots = [shot for shot in script_data.get("shots", []) if isinstance(shot, dict)]
    if not shots:
        raise RenderError("没有可导出的分镜。")

    canvas_size = (
        int(render_result.get("video_width") or 0),
        int(render_result.get("video_height") or 0),
    )
    if canvas_size[0] <= 0 or canvas_size[1] <= 0:
        canvas_size = render_size(payload.get("image_size") or story.get("image_size"))

    drafts_root = target_project_dir / DRAFTS_DIR_NAME
    drafts_root.mkdir(parents=True, exist_ok=True)
    draft_name = _draft_name(str(script_data.get("title") or story.get("title") or ""), str(payload.get("draft_name") or ""))
    draft_folder = classes["DraftFolder"](str(drafts_root))
    draft_script = draft_folder.create_draft(
        draft_name,
        width=canvas_size[0],
        height=canvas_size[1],
        fps=FPS,
        maintrack_adsorb=True,
        allow_replace=bool(payload.get("replace_draft")),
    )
    draft_path = drafts_root / draft_name
    draft_assets_dir = draft_path / DRAFT_ASSETS_DIR_NAME

    report(0.76, "创建草稿目录", "正在写入剪映草稿基础文件")
    draft_script.add_track(classes["TrackType"].video, VIDEO_TRACK_NAME)
    draft_script.add_track(classes["TrackType"].audio, VOICE_TRACK_NAME)
    report(0.8, "写入画面轨", f"正在添加 {len(shots)} 个分镜图片片段")
    total_duration = _add_video_segments(draft_script, classes, target_project_dir, draft_assets_dir, shots, canvas_size)
    report(0.88, "写入配音轨", "正在添加配音片段")
    voice_assets = _add_voice_segments(draft_script, classes, target_project_dir, draft_assets_dir, shots, total_duration)

    bgm_assets: list[str] = []
    bgm_path = resolve_bgm_path(payload.get("bgm_id") or "none")
    if bgm_path:
        report(0.92, "写入 BGM 轨", "正在添加背景音乐")
        draft_script.add_track(classes["TrackType"].audio, BGM_TRACK_NAME)
        bgm_assets = _add_looped_audio(draft_script, classes, BGM_TRACK_NAME, bgm_path, draft_assets_dir, total_duration, 0.18)

    sfx_assets: list[str] = []
    intro_sfx_path = resolve_intro_sfx_path(payload.get("intro_sfx_id") or "default", payload.get("intro_template") or "none")
    if intro_sfx_path:
        report(0.94, "写入音效轨", "正在添加开头音效")
        draft_script.add_track(classes["TrackType"].audio, SFX_TRACK_NAME)
        sfx_assets = _add_intro_sfx(draft_script, classes, intro_sfx_path, draft_assets_dir, total_duration)

    report(0.96, "写入字幕轨", "正在导入 SRT 字幕")
    subtitle_added = _add_subtitles(draft_script, classes, target_project_dir / "subtitle.srt")
    report(0.98, "保存剪映草稿", "正在保存 draft_content.json")
    draft_script.save()

    draft_url = f"/workspace/projects/{public_project_id}/{DRAFTS_DIR_NAME}/{draft_name}"
    result = {
        "project_id": public_project_id,
        "title": script_data.get("title") or story.get("title") or "",
        "draft_name": draft_name,
        "draft_dir": str(draft_path.resolve()),
        "draft_url": draft_url,
        "draft_content": f"{draft_url}/draft_content.json",
        "draft_meta": f"{draft_url}/draft_meta_info.json",
        "assets_dir": str(draft_assets_dir.resolve()),
        "duration_sec": round(total_duration / 1_000_000, 2),
        "shots": len(shots),
        "voice_assets": voice_assets,
        "bgm_assets": sorted(set(bgm_assets)),
        "sfx_assets": sorted(set(sfx_assets)),
        "subtitle_track": subtitle_added,
        "source_video": render_result.get("video", ""),
        "note": "已生成剪映专业版草稿目录。素材路径写入为本机绝对路径，请在同一台电脑上打开或复制整份项目目录后再导入。",
    }
    (draft_path / "export_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["manifest"] = f"{draft_url}/export_manifest.json"
    return result
