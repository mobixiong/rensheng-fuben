from __future__ import annotations

from typing import Any

from app.jobs.store import now_ms, public_job, read_job, save_job
from app.projects.service import safe_project_id

from .constants import AutoPipelineCancelled, AutoPipelineError, STEP_KEYS, _cancelled, _lock, _runtime_secrets


def _step_template() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "name": name,
            "status": "pending",
            "attempt": 0,
            "error": "",
            "detail": "",
            "updated_at": now_ms(),
        }
        for key, name in STEP_KEYS
    ]


def _step(job: dict[str, Any], key: str) -> dict[str, Any]:
    for item in job.get("steps", []):
        if item.get("key") == key:
            return item
    raise AutoPipelineError(f"Unknown step: {key}")


def _save(job: dict[str, Any]) -> dict[str, Any]:
    return save_job(job)


def _read(project_id: str, job_id: str) -> dict[str, Any]:
    return read_job(safe_project_id(project_id), job_id)


def _latest_job(job: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return _read(str(job.get("project_id") or ""), str(job.get("job_id") or ""))
    except Exception:
        return None


def _is_cancelled(job: dict[str, Any]) -> bool:
    job_id = str(job.get("job_id") or "")
    if job_id in _cancelled or job.get("status") == "cancelled":
        return True
    latest = _latest_job(job)
    return bool(latest and latest.get("status") == "cancelled")


def _check_cancelled(job: dict[str, Any]) -> None:
    if _is_cancelled(job):
        raise AutoPipelineCancelled("任务已取消")


def _mark_cancelled(job: dict[str, Any]) -> dict[str, Any]:
    job["status"] = "cancelled"
    job["detail"] = "任务已取消"
    for step in job.get("steps", []):
        if step.get("status") in {"pending", "running", "waiting"}:
            step["status"] = "cancelled"
            step["updated_at"] = now_ms()
    return _save(job)


def _set_step(job: dict[str, Any], key: str, status: str, *, detail: str = "", error: str = "", progress: float | None = None) -> dict[str, Any]:
    with _lock:
        if _is_cancelled(job):
            latest = _latest_job(job) or job
            return _mark_cancelled(latest)
        step = _step(job, key)
        if step.get("status") != status and status == "running":
            step["attempt"] = int(step.get("attempt") or 0) + 1
        step["status"] = status
        step["detail"] = detail
        step["error"] = error
        step["updated_at"] = now_ms()
        job["current_step"] = key
        job["detail"] = detail or step.get("name") or key
        if progress is not None:
            job["progress"] = max(0, min(1, float(progress)))
        return _save(job)


def _public(job: dict[str, Any]) -> dict[str, Any]:
    return public_job(job)


def _secrets(job: dict[str, Any]) -> dict[str, Any]:
    return _runtime_secrets.get(str(job.get("job_id")), {})


def _with_runtime_keys(job: dict[str, Any], section: str) -> dict[str, Any]:
    data = dict((job.get("input") or {}).get(section) or {})
    runtime = _secrets(job).get(section)
    if isinstance(runtime, dict):
        data.update({key: value for key, value in runtime.items() if value})
    return data
