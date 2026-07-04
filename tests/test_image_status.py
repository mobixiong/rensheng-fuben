import json

from app import project_service
from app.image_status import (
    IMAGE_STATUS_DONE,
    IMAGE_STATUS_ERROR,
    IMAGE_STATUS_PENDING,
    clear_image_runtime_fields,
    mark_image_done,
    normalize_final_image_status,
)


def test_done_clears_transient_and_error_fields():
    shot = {
        "_image_status": "error",
        "_image_error": "old error",
        "_image_error_category": "unknown",
        "_image_error_code": "old",
        "_image_job": {"status": "redrawing"},
        "_image_attempt": 3,
        "_image_status_started_at": 123,
        "_image_status_updated_at": 456,
    }

    mark_image_done(shot)

    assert shot["_image_status"] == IMAGE_STATUS_DONE
    assert "_image_error" not in shot
    assert "_image_error_category" not in shot
    assert "_image_error_code" not in shot
    assert "_image_job" not in shot
    assert "_image_attempt" not in shot


def test_existing_image_wins_over_old_error_status():
    shot = {
        "_image_status": "error",
        "_image_error": "stale error",
        "image_url": "/workspace/projects/demo/images/shot_01.png",
    }

    assert normalize_final_image_status(shot, has_image=True) == IMAGE_STATUS_DONE


def test_runtime_fields_can_be_cleaned_without_touching_final_status():
    shot = {
        "_image_status": IMAGE_STATUS_PENDING,
        "_image_job": {"status": "generating"},
        "_image_attempt": 1,
        "_image_status_started_at": 123,
        "_image_status_updated_at": 456,
    }

    clear_image_runtime_fields(shot)

    assert shot == {"_image_status": IMAGE_STATUS_PENDING}


def test_hydrate_clears_legacy_running_state_without_image(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    state = {
        "project_id": "legacy_runtime",
        "story": {
            "shots": [
                {
                    "_image_status": "running",
                    "_image_job": {"status": "redrawing"},
                    "_image_attempt": 2,
                    "_image_status_started_at": 123,
                    "_image_status_updated_at": 456,
                }
            ]
        },
    }

    project_service.hydrate_project_images(state, "legacy_runtime")

    shot = state["story"]["shots"][0]
    assert shot == {"_image_status": IMAGE_STATUS_PENDING}


def test_existing_image_fields_win_over_stale_error_when_hydrated(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    state = {
        "project_id": "existing_image",
        "story": {
            "shots": [
                {
                    "image_url": "/workspace/projects/existing_image/images/shot_01.png",
                    "_image_status": IMAGE_STATUS_ERROR,
                    "_image_error": "stale failure",
                    "_image_error_category": "unknown",
                    "_image_error_code": "old",
                }
            ]
        },
    }

    project_service.hydrate_project_images(state, "existing_image")

    shot = state["story"]["shots"][0]
    assert shot["_image_status"] == IMAGE_STATUS_DONE
    assert "_image_error" not in shot
    assert "_image_error_category" not in shot
    assert "_image_error_code" not in shot


def test_failed_job_terminal_does_not_override_existing_image(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project_id = "failed_job_with_image"
    jobs_dir = project_service.project_dir(project_id) / "jobs"
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "job.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "shot_index": 0,
                        "status": "failed",
                        "error": "new failure",
                        "error_category": "unknown",
                        "error_code": "boom",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state = {
        "project_id": project_id,
        "story": {
            "shots": [
                {
                    "image_url": f"/workspace/projects/{project_id}/images/shot_01.png",
                    "_image_status": IMAGE_STATUS_PENDING,
                }
            ]
        },
    }

    project_service.hydrate_project_images(state, project_id)

    shot = state["story"]["shots"][0]
    assert shot["_image_status"] == IMAGE_STATUS_DONE
    assert "_image_error" not in shot


def test_write_project_files_does_not_persist_legacy_runtime_state(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project_id = "persist_runtime"
    project_service.write_project_files(
        {
            "project_id": project_id,
            "story": {
                "shots": [
                    {
                        "_image_status": "redrawing",
                        "_image_job": {"status": "running"},
                        "_image_attempt": 3,
                        "_image_status_started_at": 123,
                        "_image_status_updated_at": 456,
                    }
                ]
            },
        },
        set_active=False,
    )

    saved = json.loads((project_service.project_dir(project_id) / "state.json").read_text(encoding="utf-8"))
    assert saved["story"]["shots"][0] == {"_image_status": IMAGE_STATUS_PENDING}
