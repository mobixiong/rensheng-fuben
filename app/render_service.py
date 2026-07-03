import threading
import time
from typing import Any

from .errors import RenderError
from .job_store import make_job_id, normalize_project_id, public_job, read_job, save_job
from .pipeline import render_story
from .project_service import project_dir, safe_project_id
from .render_validation import validate_ready_for_render
from .tts_adapter import TtsConfig


_RENDER_JOBS: dict[str, dict[str, Any]] = {}
_RENDER_JOBS_LOCK = threading.Lock()
_MAX_RENDER_JOBS = 60
_RENDER_JOB_TTL_SECONDS = 6 * 60 * 60


def _now_ts() -> float:
    return time.time()


def _project_id_from_payload(payload: dict[str, Any]) -> str:
    story = payload.get("story") if isinstance(payload.get("story"), dict) else {}
    topic = str(story.get("title") or payload.get("topic") or "")
    return normalize_project_id(payload.get("project_id") or story.get("project_id") or "", topic)


def _final_video_result(project_id: str) -> dict[str, Any] | None:
    final_path = project_dir(project_id) / "final.mp4"
    if not final_path.exists() or final_path.stat().st_size <= 0:
        return None
    return {
        "video": f"/workspace/projects/{project_id}/final.mp4",
        "project_id": project_id,
        "project_url": f"/workspace/projects/{project_id}",
    }


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
        if job.get("project_id"):
            save_job(job)
        _prune_render_jobs_locked()


def _render_job_worker(job_id: str, payload: dict[str, Any]) -> None:
    project_id = _project_id_from_payload(payload)
    force_render = bool(payload.get("force_render"))
    _set_render_job(job_id, project_id=project_id, force_render=force_render, status="running", progress=0.02, stage="准备渲染", detail="渲染任务已启动")
    try:
        def on_progress(event: dict[str, Any]) -> None:
            _set_render_job(job_id, status="running", **event)

        data = render_story(
            story=payload["story"],
            voice=payload.get("voice") or "zh-CN-YunxiNeural",
            rate=payload.get("rate") or "+12%",
            tts_config=TtsConfig.from_payload(payload),
            project_id=project_id,
            cleanup_intermediate=payload.get("cleanup_intermediate", True),
            force_render=force_render,
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
    project_id = _project_id_from_payload(payload)
    payload = {**payload, "project_id": project_id}
    story = payload.get("story") if isinstance(payload.get("story"), dict) else {}
    validate_ready_for_render(story)
    force_render = bool(payload.get("force_render"))
    existing = None if force_render else _final_video_result(project_id)
    if existing:
        job_id = make_job_id("render")
        complete = {
            "job_id": job_id,
            "project_id": project_id,
            "status": "complete",
            "progress": 1,
            "stage": "渲染完成",
            "detail": "成片已存在",
            "result": existing,
            "created_ts": _now_ts(),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_ts": _now_ts(),
            "force_render": False,
        }
        with _RENDER_JOBS_LOCK:
            _RENDER_JOBS[job_id] = dict(complete)
            save_job(complete)
        return public_job(complete)

    job_id = make_job_id("render")
    queued = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "queued",
        "progress": 0,
        "stage": "排队中",
        "detail": "等待渲染任务启动",
        "created_ts": _now_ts(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "force_render": force_render,
    }
    with _RENDER_JOBS_LOCK:
        _RENDER_JOBS[job_id] = dict(queued)
        save_job(queued)
        _prune_render_jobs_locked()
    thread = threading.Thread(target=_render_job_worker, args=(job_id, payload), daemon=True)
    thread.start()
    return public_job(queued)


def get_render_job(job_id: str, project_id: str = "") -> dict[str, Any] | None:
    with _RENDER_JOBS_LOCK:
        job = _RENDER_JOBS.get(job_id)
        if job:
            return public_job(job)
    if project_id:
        try:
            job = read_job(safe_project_id(project_id), job_id)
        except FileNotFoundError:
            return None
        result = None if job.get("force_render") else _final_video_result(str(job.get("project_id") or project_id))
        if result and job.get("status") not in {"complete", "error"}:
            job.update(status="complete", progress=1, stage="渲染完成", detail="成片已存在", result=result, finished_ts=_now_ts())
            save_job(job)
        return public_job(job)
    return None
