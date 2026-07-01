import threading
import time
import uuid
from typing import Any

from .errors import RenderError
from .pipeline import render_story
from .tts_adapter import TtsConfig


_RENDER_JOBS: dict[str, dict[str, Any]] = {}
_RENDER_JOBS_LOCK = threading.Lock()
_MAX_RENDER_JOBS = 60
_RENDER_JOB_TTL_SECONDS = 6 * 60 * 60


def _now_ts() -> float:
    return time.time()


def _prune_render_jobs_locked() -> None:
    now = _now_ts()
    stale_ids = [
        job_id for job_id, job in _RENDER_JOBS.items()
        if job.get("status") in {"complete", "error"} and now - float(job.get("finished_ts") or job.get("created_ts") or now) > _RENDER_JOB_TTL_SECONDS
    ]
    for job_id in stale_ids:
        _RENDER_JOBS.pop(job_id, None)

    if len(_RENDER_JOBS) <= _MAX_RENDER_JOBS:
        return
    removable = sorted(
        (
            (float(job.get("finished_ts") or job.get("created_ts") or 0), job_id)
            for job_id, job in _RENDER_JOBS.items()
            if job.get("status") in {"complete", "error"}
        ),
        key=lambda item: item[0],
    )
    for _, job_id in removable[: max(0, len(_RENDER_JOBS) - _MAX_RENDER_JOBS)]:
        _RENDER_JOBS.pop(job_id, None)


def _set_render_job(job_id: str, **updates: Any) -> None:
    with _RENDER_JOBS_LOCK:
        job = _RENDER_JOBS.setdefault(job_id, {})
        job.update(updates)
        if updates.get("status") in {"complete", "error"}:
            job["finished_ts"] = _now_ts()
        job["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _prune_render_jobs_locked()


def _render_job_worker(job_id: str, payload: dict[str, Any]) -> None:
    _set_render_job(job_id, status="running", progress=0.02, stage="准备渲染", detail="渲染任务已启动")
    try:
        def on_progress(event: dict[str, Any]) -> None:
            _set_render_job(job_id, status="running", **event)

        data = render_story(
            story=payload["story"],
            voice=payload.get("voice") or "zh-CN-YunxiNeural",
            rate=payload.get("rate") or "+12%",
            tts_config=TtsConfig.from_payload(payload),
            project_id=payload.get("project_id"),
            cleanup_intermediate=payload.get("cleanup_intermediate", True),
            progress_callback=on_progress,
            intro_template=payload.get("intro_template") or "none",
            bgm_id=payload.get("bgm_id") or "none",
            intro_image_seconds=payload.get("intro_image_seconds") or 0.3,
            intro_sfx_id=payload.get("intro_sfx_id") or "default",
            image_size=payload.get("image_size") or "9:16",
        )
        _set_render_job(job_id, status="complete", progress=1, stage="渲染完成", detail="成片已导出", result=data)
    except RenderError as exc:
        _set_render_job(job_id, status="error", stage="渲染失败", detail=str(exc), error=str(exc))
    except Exception as exc:
        _set_render_job(job_id, status="error", stage="渲染失败", detail=str(exc), error=str(exc))


def create_render_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    queued = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "stage": "排队中",
        "detail": "等待渲染任务启动",
        "created_ts": _now_ts(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _RENDER_JOBS_LOCK:
        _RENDER_JOBS[job_id] = dict(queued)
        _prune_render_jobs_locked()
    thread = threading.Thread(target=_render_job_worker, args=(job_id, payload), daemon=True)
    thread.start()
    return {key: queued[key] for key in ("job_id", "status", "progress", "stage", "detail")}


def get_render_job(job_id: str) -> dict[str, Any] | None:
    with _RENDER_JOBS_LOCK:
        job = _RENDER_JOBS.get(job_id)
        return dict(job) if job else None
