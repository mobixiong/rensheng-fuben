import threading
import time
from typing import Any

from app.core.errors import RenderError
from app.media.jianying.export import create_jianying_draft
from app.jobs.store import make_job_id, normalize_project_id, public_job, read_job, save_job
from app.jobs.status import RENDER_JOB_COMPLETE, RENDER_JOB_ERROR, RENDER_JOB_QUEUED, RENDER_JOB_RUNNING, RENDER_TERMINAL_STATUSES
from app.projects.service import safe_project_id
from app.media.render.validation import validate_ready_for_render


_JY_JOBS: dict[str, dict[str, Any]] = {}
_JY_JOBS_LOCK = threading.Lock()
_MAX_JY_JOBS = 60
_JY_JOB_TTL_SECONDS = 6 * 60 * 60


def _now_ts() -> float:
    return time.time()


def _project_id_from_payload(payload: dict[str, Any]) -> str:
    story = payload.get("story") if isinstance(payload.get("story"), dict) else {}
    topic = str(story.get("title") or payload.get("topic") or "")
    return normalize_project_id(payload.get("project_id") or story.get("project_id") or "", topic)


def _job_base(job_id: str, project_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "project_id": project_id,
        "created_ts": _now_ts(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _prune_jobs_locked() -> None:
    now = _now_ts()
    stale_ids = [
        job_id for job_id, job in _JY_JOBS.items()
        if (
            job.get("status") in RENDER_TERMINAL_STATUSES
            and now - float(job.get("finished_ts") or job.get("created_ts") or now) > _JY_JOB_TTL_SECONDS
        )
    ]
    for job_id in stale_ids:
        _JY_JOBS.pop(job_id, None)

    if len(_JY_JOBS) <= _MAX_JY_JOBS:
        return
    removable = sorted(
        (
            (float(job.get("finished_ts") or job.get("created_ts") or 0), job_id)
            for job_id, job in _JY_JOBS.items()
            if job.get("status") in RENDER_TERMINAL_STATUSES
        ),
        key=lambda item: item[0],
    )
    for _, job_id in removable[: max(0, len(_JY_JOBS) - _MAX_JY_JOBS)]:
        _JY_JOBS.pop(job_id, None)


def _store_job(job: dict[str, Any]) -> dict[str, Any]:
    with _JY_JOBS_LOCK:
        _JY_JOBS[str(job["job_id"])] = dict(job)
        save_job(job)
        _prune_jobs_locked()
    return public_job(job)


def _set_job(job_id: str, **updates: Any) -> None:
    with _JY_JOBS_LOCK:
        job = _JY_JOBS.setdefault(job_id, {})
        job.update(updates)
        if updates.get("status") in RENDER_TERMINAL_STATUSES:
            job["finished_ts"] = _now_ts()
        if job.get("project_id"):
            save_job(job)
        _prune_jobs_locked()


def _queued_job(project_id: str) -> dict[str, Any]:
    return {
        **_job_base(make_job_id("jianying"), project_id),
        "status": RENDER_JOB_QUEUED,
        "progress": 0,
        "stage": "排队中",
        "detail": "等待剪映草稿导出任务启动",
    }


def _worker(job_id: str, payload: dict[str, Any]) -> None:
    project_id = _project_id_from_payload(payload)
    _set_job(job_id, project_id=project_id, status=RENDER_JOB_RUNNING, progress=0.01, stage="准备剪映草稿", detail="导出任务已启动")
    try:
        def on_progress(event: dict[str, Any]) -> None:
            _set_job(job_id, status=RENDER_JOB_RUNNING, **event)

        data = create_jianying_draft(payload, progress_callback=on_progress)
        _set_job(job_id, status=RENDER_JOB_COMPLETE, progress=1, stage="剪映草稿已导出", detail=str(data.get("draft_dir") or ""), result=data)
    except RenderError as exc:
        _set_job(job_id, status=RENDER_JOB_ERROR, stage="剪映草稿导出失败", detail=str(exc), error=str(exc))
    except Exception as exc:
        _set_job(job_id, status=RENDER_JOB_ERROR, stage="剪映草稿导出失败", detail=str(exc), error=str(exc))


def create_jianying_draft_job(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = _project_id_from_payload(payload)
    payload = {**payload, "project_id": project_id}
    story = payload.get("story") if isinstance(payload.get("story"), dict) else {}
    validate_ready_for_render(story)

    queued = _queued_job(project_id)
    _store_job(queued)
    thread = threading.Thread(target=_worker, args=(queued["job_id"], payload), daemon=True)
    thread.start()
    return public_job(queued)


def get_jianying_draft_job(job_id: str, project_id: str = "") -> dict[str, Any] | None:
    with _JY_JOBS_LOCK:
        job = _JY_JOBS.get(job_id)
        if job:
            return public_job(job)
    if project_id:
        try:
            return public_job(read_job(safe_project_id(project_id), job_id))
        except FileNotFoundError:
            return None
    return None
