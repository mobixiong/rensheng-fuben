from __future__ import annotations

import json

from app import auto_pipeline_jobs, project_service
from app.job_store import read_job


def _persisted_job(project_id: str, job_id: str) -> dict:
    return json.loads(
        (project_service.project_dir(project_id) / "jobs" / f"{job_id}.json").read_text(encoding="utf-8")
    )


def test_resume_resets_failed_render_step_and_clears_render_job_id(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("app.core.paths.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(auto_pipeline_jobs, "_runner", type("R", (), {"submit": staticmethod(lambda *a, **k: None)})())

    project_id = "resume_render"
    job_id = "auto_breakdown_00000001"
    steps = auto_pipeline_jobs._step_template()
    for step in steps:
        if step["key"] == "render":
            step["status"] = "failed"
            step["error"] = "boom"
        elif step["key"] == "images":
            step["status"] = "done"
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "failed",
        "current_step": "render",
        "progress": 0.9,
        "input": {},
        "steps": steps,
        "artifacts": {
            "theme_ideas": [],
            "selected_idea": None,
            "copy_preset": "random",
            "copy_preset_label": "random",
            "image_job_id": "img_done_prev",
            "render_job_id": "render_failed_prev",
        },
        "result": {},
        "error": "prev",
    }
    auto_pipeline_jobs._save(job)

    result = auto_pipeline_jobs.resume_auto_pipeline_job(project_id, job_id)

    assert result["status"] == "queued"
    saved = _persisted_job(project_id, job_id)
    render_step = next(step for step in saved["steps"] if step["key"] == "render")
    images_step = next(step for step in saved["steps"] if step["key"] == "images")
    assert render_step["status"] == "pending"
    assert render_step["error"] == ""
    assert saved["artifacts"]["render_job_id"] == ""
    assert saved["artifacts"]["image_job_id"] == "img_done_prev"
    assert images_step["status"] == "done"


def test_resume_skips_completed_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("app.core.paths.PROJECTS_DIR", tmp_path)

    project_id = "resume_complete"
    job_id = "auto_done_00000001"
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "complete",
        "current_step": "complete",
        "progress": 1,
        "input": {},
        "steps": auto_pipeline_jobs._step_template(),
        "artifacts": {
            "theme_ideas": [],
            "selected_idea": None,
            "copy_preset": "random",
            "copy_preset_label": "random",
            "image_job_id": "",
            "render_job_id": "",
        },
        "result": {"video_url": "/workspace/projects/resume_complete/final.mp4"},
        "error": "",
    }
    auto_pipeline_jobs._save(job)

    result = auto_pipeline_jobs.resume_auto_pipeline_job(project_id, job_id)

    assert result["status"] == "complete"
def test_wait_render_job_raises_on_stalled_render(monkeypatch, tmp_path):
    import time as _time
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("app.core.paths.PROJECTS_DIR", tmp_path)
    old_stamp = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(_time.time() - 31 * 60))
    stalls = {"count": 0}

    def fake_get_render_job(job_id, project_id=""):
        return {
            "job_id": job_id,
            "project_id": project_id,
            "status": "running",
            "progress": 0.5,
            "updated_at": old_stamp,
            "detail": "",
            "stage": "",
        }

    def no_cancel(job):
        return None

    monkeypatch.setattr(auto_pipeline_jobs, "get_render_job", fake_get_render_job)
    monkeypatch.setattr(auto_pipeline_jobs, "_check_cancelled", no_cancel)

    project_id = "stall_render"
    job_id = "auto_stall_00000001"
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "running",
        "current_step": "render",
        "progress": 0.9,
        "input": {},
        "steps": auto_pipeline_jobs._step_template(),
        "artifacts": {
            "theme_ideas": [],
            "selected_idea": None,
            "copy_preset": "random",
            "copy_preset_label": "random",
            "image_job_id": "",
            "render_job_id": "render_running_prev",
        },
        "result": {},
        "error": "",
    }
    auto_pipeline_jobs._save(job)
    persisted = auto_pipeline_jobs._read(project_id, job_id)

    raised = False
    try:
        auto_pipeline_jobs._wait_render_job(persisted)
    except auto_pipeline_jobs.AutoPipelineError as exc:
        raised = True
        assert "无进展" in str(exc) or "疑似" in str(exc)
    assert raised

def test_wait_render_job_raises_on_stalled_render_with_int_ms_updated_at(monkeypatch, tmp_path):
    # Regression: save_job persists updated_at as integer epoch milliseconds, but the
    # old _render_updated_seconds only parsed "YYYY-MM-DD HH:MM:SS" strings, so the
    # RENDER_STALL_SECONDS check silently became a no-op in production. Feed the real
    # int-ms form (31 min stale) through _wait_render_job and assert it raises.
    import time as _time
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("app.core.paths.PROJECTS_DIR", tmp_path)
    old_ms = int(_time.time() * 1000) - 31 * 60 * 1000

    def fake_get_render_job(job_id, project_id=""):
        return {
            "job_id": job_id,
            "project_id": project_id,
            "status": "running",
            "progress": 0.5,
            "updated_at": old_ms,
            "detail": "",
            "stage": "",
        }

    monkeypatch.setattr(auto_pipeline_jobs, "get_render_job", fake_get_render_job)
    monkeypatch.setattr(auto_pipeline_jobs, "_check_cancelled", lambda job: None)
    # If the stall check is silently skipped, _wait_render_job would sleep-loop forever;
    # fail fast instead of hanging so this regression cannot pass silently again.
    monkeypatch.setattr(auto_pipeline_jobs.time, "sleep", lambda _s: (_ for _ in ()).throw(RuntimeError("stall detection no-op")))

    project_id = "stall_render_ms"
    job_id = "auto_stall_ms_00000001"
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "running",
        "current_step": "render",
        "progress": 0.9,
        "input": {},
        "steps": auto_pipeline_jobs._step_template(),
        "artifacts": {
            "theme_ideas": [],
            "selected_idea": None,
            "copy_preset": "random",
            "copy_preset_label": "random",
            "image_job_id": "",
            "render_job_id": "render_running_prev",
        },
        "result": {},
        "error": "",
    }
    auto_pipeline_jobs._save(job)
    persisted = auto_pipeline_jobs._read(project_id, job_id)

    raised = False
    try:
        auto_pipeline_jobs._wait_render_job(persisted)
    except auto_pipeline_jobs.AutoPipelineError as exc:
        raised = True
        assert "无进展" in str(exc) or "疑似" in str(exc)
    assert raised

def test_get_auto_pipeline_job_marks_orphaned_running_job_failed(tmp_path, monkeypatch):
    import json as _json
    import time as _time
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("app.core.paths.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(auto_pipeline_jobs, "_ACTIVE_AUTO_IDS", set())

    project_id = "auto_orphan"
    job_id = "auto_orphan_00000001"
    old_ms = int(_time.time() * 1000) - 120 * 1000
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "running",
        "current_step": "images",
        "progress": 0.6,
        "updated_at": old_ms,
        "input": {},
        "steps": auto_pipeline_jobs._step_template(),
        "artifacts": {
            "theme_ideas": [],
            "selected_idea": None,
            "copy_preset": "random",
            "copy_preset_label": "random",
            "image_job_id": "",
            "render_job_id": "",
        },
        "result": {},
        "error": "",
    }
    jobs_dir = project_service.project_dir(project_id) / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    (jobs_dir / f"{job_id}.json").write_text(_json.dumps(job, ensure_ascii=False), encoding="utf-8")

    result = auto_pipeline_jobs.get_auto_pipeline_job(project_id, job_id)

    assert result["status"] == "failed"
    assert result["stalled"] is True
    assert "中断" in result["error"]

    persisted = _persisted_job(project_id, job_id)
    assert persisted["status"] == "failed"


def test_get_auto_pipeline_job_keeps_live_running_job(tmp_path, monkeypatch):
    import time as _time
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("app.core.paths.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(auto_pipeline_jobs, "_ACTIVE_AUTO_IDS", {"auto_live_00000001"})

    project_id = "auto_live"
    job_id = "auto_live_00000001"
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "running",
        "current_step": "images",
        "progress": 0.6,
        "updated_at": int(_time.time() * 1000) - 120 * 1000,
        "input": {},
        "steps": auto_pipeline_jobs._step_template(),
        "artifacts": {
            "theme_ideas": [],
            "selected_idea": None,
            "copy_preset": "random",
            "copy_preset_label": "random",
            "image_job_id": "",
            "render_job_id": "",
        },
        "result": {},
        "error": "",
    }
    auto_pipeline_jobs._save(job)

    result = auto_pipeline_jobs.get_auto_pipeline_job(project_id, job_id)

    assert result["status"] == "running"
    assert "stalled" not in result
