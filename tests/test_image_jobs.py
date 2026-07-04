from __future__ import annotations

import json

from app import image_jobs, project_service
from app.image_status import IMAGE_JOB_DONE, IMAGE_JOB_FAILED, IMAGE_JOB_QUEUED, IMAGE_JOB_RETRYING


def test_save_image_job_updates_counts_and_uses_shared_job_store(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)

    job = {
        "job_id": "img_test",
        "project_id": "image_job_project",
        "status": IMAGE_JOB_QUEUED,
        "active_peak": 1,
        "items": [
            {"shot_index": 0, "status": IMAGE_JOB_DONE},
            {"shot_index": 1, "status": IMAGE_JOB_FAILED},
            {"shot_index": 2, "status": IMAGE_JOB_RETRYING},
        ],
    }

    saved = image_jobs._save_job(job)

    assert saved["done"] == 1
    assert saved["failed"] == 1
    assert saved["cancelled"] == 0
    assert saved["active"] == 1
    assert saved["active_peak"] == 1

    saved_path = tmp_path / "image_job_project" / "jobs" / "img_test.json"
    assert saved_path.exists()
    data = json.loads(saved_path.read_text(encoding="utf-8"))
    assert data["done"] == 1
    assert data["updated_at"] == saved["updated_at"]


def test_list_project_jobs_ignores_non_image_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project_id = "mixed_jobs"
    jobs_dir = project_service.project_dir(project_id) / "jobs"
    jobs_dir.mkdir(parents=True)

    image_job = {
        "job_id": "img_keep",
        "kind": "image",
        "project_id": project_id,
        "status": IMAGE_JOB_QUEUED,
        "updated_at": 1,
        "items": [{"shot_index": 0, "status": IMAGE_JOB_QUEUED}],
    }
    auto_job = {
        "job_id": "auto_do_not_touch",
        "kind": "auto_pipeline",
        "project_id": project_id,
        "status": "queued",
        "updated_at": 1,
        "steps": [],
    }
    render_job = {
        "job_id": "render_do_not_touch",
        "kind": "render",
        "project_id": project_id,
        "status": "running",
        "updated_at": 1,
    }
    (jobs_dir / "img_keep.json").write_text(json.dumps(image_job), encoding="utf-8")
    (jobs_dir / "auto_do_not_touch.json").write_text(json.dumps(auto_job), encoding="utf-8")
    (jobs_dir / "render_do_not_touch.json").write_text(json.dumps(render_job), encoding="utf-8")

    jobs = image_jobs.list_project_jobs(project_id)

    assert [job["job_id"] for job in jobs] == ["img_keep"]
    assert json.loads((jobs_dir / "auto_do_not_touch.json").read_text(encoding="utf-8"))["status"] == "queued"
    assert json.loads((jobs_dir / "render_do_not_touch.json").read_text(encoding="utf-8"))["status"] == "running"


def test_public_image_job_uses_shared_secret_redaction():
    public = image_jobs._public_job({
        "job_id": "img_secret",
        "project_id": "demo",
        "fixed_prompt": "hidden",
        "api_key": "hidden",
        "image_config": {"api_key": "hidden", "model": "demo-model"},
    })

    assert "fixed_prompt" not in public
    assert "api_key" not in public
    assert public["image_config"] == {"model": "demo-model"}
