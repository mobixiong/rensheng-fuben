from __future__ import annotations

from typing import Any

from app.images.jobs import DEFAULT_IMAGE_JOB_CONCURRENCY, cancel_image_job
from app.jobs.health import mark_orphaned_active_job
from app.jobs.store import list_jobs, make_job_id, normalize_project_id, now_ms, public_job
from app.projects.service import safe_project_id

from .constants import (
    AUTO_ACTIVE_STATUSES,
    AutoPipelineCancelled,
    AutoPipelineError,
    _ACTIVE_AUTO_IDS,
    _cancelled,
    _lock,
    _runner,
    _runtime_secrets,
)
from .image_repair import _repair_missing_images
from .presets import _copy_preset_theme_profile, _job_copy_preset, _resolve_copy_preset
from .state import (
    _check_cancelled,
    _is_cancelled,
    _latest_job,
    _mark_cancelled,
    _public,
    _read,
    _save,
    _secrets,
    _set_step,
    _state_or_default,
    _step,
    _step_template,
    _story_has_valid_shots,
    _with_runtime_keys,
)
from .steps import (
    _run_copy,
    _run_cover,
    _run_images,
    _run_improve_prompts,
    _run_render,
    _run_select_idea,
    _run_storyboard,
    _run_theme,
    _run_theme_ideas,
)



def _api():
    """Late-bind package attributes so tests can monkeypatch the package surface."""
    from app.workflow import auto_pipeline as api
    return api



def _run_pipeline(job_id: str, project_id: str) -> None:
    api = _api()
    try:
        with _lock:
            job = _read(project_id, job_id)
            if job.get("status") == "cancelled":
                return
            job["status"] = "running"
            _save(job)
        api._ACTIVE_AUTO_IDS.add(job_id)
        for runner in (
            _run_theme_ideas,
            _run_select_idea,
            _run_theme,
            _run_copy,
            _run_storyboard,
            _run_improve_prompts,
            _run_images,
            _run_cover,
            _run_render,
        ):
            with _lock:
                job = _read(project_id, job_id)
            _check_cancelled(job)
            job = runner(job)
        with _lock:
            job = _read(project_id, job_id)
            job["status"] = "complete"
            job["current_step"] = "complete"
            job["detail"] = "自动流水线完成"
            job["progress"] = 1
            _save(job)
    except Exception as exc:
        with _lock:
            try:
                job = _read(project_id, job_id)
            except Exception:
                return
            if isinstance(exc, AutoPipelineCancelled) or job.get("status") == "cancelled":
                job = _mark_cancelled(job)
            else:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["detail"] = str(exc)
                try:
                    _set_step(job, str(job.get("current_step") or "theme_ideas"), "failed", error=str(exc), detail=str(exc))
                    job = _read(project_id, job_id)
                except Exception:
                    pass
            _save(job)
    finally:
        api._ACTIVE_AUTO_IDS.discard(job_id)
        _cancelled.discard(job_id)
        _runtime_secrets.pop(job_id, None)

def create_auto_pipeline_job(payload: dict[str, Any]) -> dict[str, Any]:
    api = _api()
    brief = str(payload.get("brief") or "").strip()
    project_id = normalize_project_id(payload.get("project_id") or "", brief or "自动流水线")
    job_id = make_job_id("auto")
    now = now_ms()
    copy_preset = _resolve_copy_preset(payload.get("copy_preset") or "random")
    copy_preset_label = _copy_preset_theme_profile(copy_preset)["label"]
    input_data = {
        "brief": brief,
        "copy_preset": copy_preset,
        "image_size": payload.get("image_size") or "9:16",
        "reference_collection_id": payload.get("reference_collection_id") or "",
        "auto_reference_enabled": bool(payload.get("auto_reference_enabled")),
        "intro_template": payload.get("intro_template") or "none",
        "intro_image_seconds": payload.get("intro_image_seconds") or 0.3,
        "tts_preset": payload.get("tts_preset") or "custom",
        "voice": payload.get("voice") or "zh-CN-YunxiNeural",
        "rate": payload.get("rate") or "+12%",
        "tts_speed": payload.get("tts_speed") or 1,
        "tts_emotion": payload.get("tts_emotion") or "",
        "tts_language_boost": payload.get("tts_language_boost") or "Chinese",
        "bgm_id": payload.get("bgm_id") or "none",
        "intro_sfx_id": payload.get("intro_sfx_id") or "default",
        "auto_optimize_image_prompts": payload.get("auto_optimize_image_prompts", True),
        "render_after_images": payload.get("render_after_images", True),
        "auto_infinite_image_retry": bool(payload.get("auto_infinite_image_retry")),
        "image_concurrency": payload.get("image_concurrency") or DEFAULT_IMAGE_JOB_CONCURRENCY,
        "storyboard_granularity": payload.get("storyboard_granularity") or "balanced",
        "theme_idea_prompt": payload.get("theme_idea_prompt") or "",
        "copy_prompt": payload.get("copy_prompt") or "",
        "copy_to_story_prompt": payload.get("copy_to_story_prompt") or "",
        "image_prompt": payload.get("image_prompt") or "",
        "improve_image_prompt": payload.get("improve_image_prompt") or "",
        "text_config": {
            key: value for key, value in dict(payload.get("text_config") or {}).items() if key != "api_key"
        },
        "image_config": {
            key: value for key, value in dict(payload.get("image_config") or {}).items() if key != "api_key"
        },
        "tts_config": {
            key: value for key, value in dict(payload.get("tts_config") or {}).items() if key != "api_key"
        },
    }
    _runtime_secrets[job_id] = {
        "text_config": {"api_key": (payload.get("text_config") or {}).get("api_key") or ""},
        "image_config": {"api_key": (payload.get("image_config") or {}).get("api_key") or ""},
        "tts_config": {"api_key": (payload.get("tts_config") or {}).get("api_key") or ""},
    }
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "queued",
        "current_step": "theme_ideas",
        "progress": 0,
        "detail": "等待自动流水线启动",
        "created_at": now,
        "updated_at": now,
        "input": input_data,
        "steps": _step_template(),
        "artifacts": {
            "theme_ideas": [],
            "selected_idea": None,
            "copy_preset": copy_preset,
            "copy_preset_label": copy_preset_label,
            "image_job_id": "",
            "render_job_id": "",
        },
        "result": {
            "topic": "",
            "copy_preset": copy_preset,
            "copy_preset_label": copy_preset_label,
            "video_url": "",
            "project_url": f"/workspace/projects/{project_id}",
        },
        "error": "",
    }
    with _lock:
        _save(job)
    api._runner.submit(_run_pipeline, job_id, project_id)
    return _public(job)

def _mark_auto_stale_if_orphaned(job: dict[str, Any]) -> dict[str, Any]:
    api = _api()
    return mark_orphaned_active_job(
        job,
        active_statuses=AUTO_ACTIVE_STATUSES,
        terminal_status="failed",
        active_ids=api._ACTIVE_AUTO_IDS,
        grace_ms=60 * 1000,
        error_message="自动流水线已中断，当前没有后台线程在运行。请重新启动。",
    )

def get_auto_pipeline_job(project_id: str, job_id: str) -> dict[str, Any]:
    api = _api()
    with _lock:
        return _public(_mark_auto_stale_if_orphaned(_read(project_id, job_id)))

def list_auto_pipeline_jobs(project_id: str, active_only: bool = False) -> list[dict[str, Any]]:
    return list_jobs(project_id, prefix="auto_", active_only=active_only, active_statuses=AUTO_ACTIVE_STATUSES)

def cancel_auto_pipeline_job(project_id: str, job_id: str) -> dict[str, Any]:
    api = _api()
    project_id = safe_project_id(project_id)
    with _lock:
        job = _read(project_id, job_id)
        _cancelled.add(job_id)
        image_job_id = str((job.get("artifacts") or {}).get("image_job_id") or "")
        if image_job_id:
            try:
                cancel_image_job(project_id, image_job_id)
            except Exception:
                pass
        job = _mark_cancelled(job)
        return _public(job)

def resume_auto_pipeline_job(project_id: str, job_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    api = _api()
    project_id = safe_project_id(project_id)
    with _lock:
        job = _read(project_id, job_id)
        if job.get("status") == "complete":
            return _public(job)
        if payload:
            _runtime_secrets[job_id] = {
                "text_config": {"api_key": ((payload.get("text_config") or {}).get("api_key") or "")},
                "image_config": {"api_key": ((payload.get("image_config") or {}).get("api_key") or "")},
                "tts_config": {"api_key": ((payload.get("tts_config") or {}).get("api_key") or "")},
            }
        _cancelled.discard(job_id)
        job["status"] = "queued"
        job["detail"] = "等待恢复自动流水线"
        job["error"] = ""
        for step in job.get("steps", []):
            if step.get("status") in {"cancelled", "failed"}:
                step["status"] = "pending"
                step["detail"] = ""
                step["error"] = ""
                step["updated_at"] = now_ms()
                key = str(step.get("key") or "")
                if key in {"images", "render"}:
                    child_field = "image_job_id" if key == "images" else "render_job_id"
                    if job.get("artifacts", {}).get(child_field):
                        job["artifacts"][child_field] = ""
        _save(job)
    api._runner.submit(_run_pipeline, job_id, project_id)
    return _public(job)

