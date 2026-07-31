from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from app.media.audio.assets import resolve_bgm_path, resolve_intro_sfx_path
from app.core.errors import RenderError
from app.projects.service import project_dir
from app.media.render.constants import FPS, render_size
from app.media.render.validation import validate_ready_for_render
from app.providers.tts.adapter import TtsConfig

from .constants import BGM_TRACK_NAME, DRAFTS_DIR_NAME, DRAFT_ASSETS_DIR_NAME, SFX_TRACK_NAME, VIDEO_TRACK_NAME, VOICE_TRACK_NAME
from .tracks import _add_intro_sfx, _add_looped_audio, _add_subtitles, _add_video_segments, _add_voice_segments
from .utils import _draft_name, _import_jianying_draft, _load_script


def _pkg():
    """Late-bind package attributes so tests can monkeypatch the package surface."""
    from app.media.jianying import export as pkg
    return pkg


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

    render_result = _pkg().render_story(
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

