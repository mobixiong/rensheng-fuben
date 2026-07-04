from __future__ import annotations

from pathlib import Path

from app import project_service, render_service


def _ready_story(project_id: str) -> dict:
    return {
        "project_id": project_id,
        "title": "测试项目",
        "shots": [
            {
                "voiceover": "测试口播。",
                "image_url": f"/workspace/projects/{project_id}/images/shot_01.png",
            }
        ],
        "cover": {
            "source_shot_index": 0,
            "image_url": f"/workspace/projects/{project_id}/images/shot_01.png",
        },
    }


def test_existing_final_video_is_reused_without_force_render(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    render_service._RENDER_JOBS.clear()
    project_id = "render_reuse"
    project_dir = project_service.project_dir(project_id)
    project_dir.mkdir(parents=True)
    (project_dir / "final.mp4").write_bytes(b"video")

    job = render_service.create_render_job({"project_id": project_id, "story": _ready_story(project_id)})

    assert job["status"] == "complete"
    assert job["force_render"] is False
    assert job["result"]["video"] == f"/workspace/projects/{project_id}/final.mp4"


def test_force_render_creates_new_queued_job_even_when_final_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    render_service._RENDER_JOBS.clear()
    started: list[bool] = []
    project_id = "render_force"
    project_dir = project_service.project_dir(project_id)
    project_dir.mkdir(parents=True)
    (project_dir / "final.mp4").write_bytes(b"video")

    class DummyThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            started.append(True)

    monkeypatch.setattr(render_service.threading, "Thread", DummyThread)

    job = render_service.create_render_job({
        "project_id": project_id,
        "story": _ready_story(project_id),
        "force_render": True,
    })

    assert job["status"] == "queued"
    assert job["force_render"] is True
    assert started == [True]
