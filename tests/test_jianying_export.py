from __future__ import annotations

import json
import wave
from pathlib import Path

from PIL import Image

from app import jianying_export, project_service


def _write_wav(path: Path, seconds: float = 0.4) -> None:
    sample_rate = 16_000
    frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(sample_rate)
        file.writeframes(b"\x00\x00" * frames)


def test_create_jianying_draft_from_project_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("app.core.paths.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(jianying_export, "render_story", lambda **kwargs: {
        "project_id": "jy_project",
        "title": "剪映测试",
        "duration_sec": 0.4,
        "video": "/workspace/projects/jy_project/final.mp4",
        "video_width": 1080,
        "video_height": 1920,
    })

    target = project_service.project_dir("jy_project")
    (target / "images").mkdir(parents=True)
    (target / "audio").mkdir()
    Image.new("RGB", (1080, 1920), "#336699").save(target / "images" / "shot_01.png")
    Image.new("RGB", (1080, 1920), "#663399").save(target / "images" / "shot_02.png")
    _write_wav(target / "audio" / "shot_01.wav")
    _write_wav(target / "audio" / "shot_02.wav")
    (target / "script.json").write_text(
        json.dumps({
            "title": "剪映测试",
            "shots": [
                {
                    "voiceover": "测试口播。",
                    "start": 0,
                    "end": 0.4,
                },
                {
                    "voiceover": "第二段口播。",
                    "start": 0.4,
                    "end": 0.8,
                }
            ],
            "audio_duration": 0.8,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (target / "subtitle.srt").write_text(
        "1\n00:00:00,000 --> 00:00:00,400\n测试口播。\n\n2\n00:00:00,400 --> 00:00:00,800\n第二段口播。\n",
        encoding="utf-8",
    )

    result = jianying_export.create_jianying_draft({
        "project_id": "projects/jy_project",
        "story": {
            "title": "剪映测试",
            "shots": [
                {"voiceover": "测试口播。", "image_url": "/workspace/projects/jy_project/images/shot_01.png"},
                {"voiceover": "第二段口播。", "image_url": "/workspace/projects/jy_project/images/shot_02.png"},
            ],
            "cover": {"source_shot_index": 0, "image_url": "/workspace/projects/jy_project/images/shot_01.png"},
        },
        "intro_sfx_id": "none",
        "bgm_id": "none",
    })

    draft_dir = Path(result["draft_dir"])
    assert (draft_dir / "draft_content.json").exists()
    assert (draft_dir / "draft_meta_info.json").exists()
    assert (draft_dir / "export_manifest.json").exists()

    content = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
    track_types = {track["type"] for track in content["tracks"]}
    assert {"video", "audio", "text"}.issubset(track_types)
    assert result["shots"] == 2
    assert result["subtitle_track"] is True
