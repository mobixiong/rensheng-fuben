from __future__ import annotations


import json
import time
from typing import Any

from app.images.jobs import DEFAULT_IMAGE_JOB_CONCURRENCY, cancel_image_job, create_image_job, get_image_job
from app.jobs.store import now_ms
from app.providers.image.adapter import generate_one_story_image
from app.providers.llm.adapter import (
    generate_story_from_copy,
    generate_text,
    generate_theme_ideas,
    generate_topic_plan,
    improve_image_prompt,
)
from app.media.render.service import create_render_job, get_render_job
from app.projects.service import project_dir, write_project_files

from ..constants import (
    AutoPipelineError,
    RENDER_STALL_SECONDS,
    _RENDER_STALL_MSG,
)
from ..image_repair import _repair_missing_images
from ..presets import (
    _copy_preset_theme_instruction,
    _copy_preset_theme_profile,
    _default_copy_prompt,
    _default_copy_to_story_prompt,
    _default_image_prompt,
    _default_improve_prompt,
    _job_copy_preset,
)
from ..state import (
    _check_cancelled,
    _image_config,
    _image_failure_message,
    _llm_config,
    _missing_image_indexes,
    _save,
    _secrets,
    _set_step,
    _shot_has_image,
    _state_or_default,
    _story_has_valid_shots,
    _with_runtime_keys,
    _write_state,
)

from .api import _api

def _render_payload(job: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    input_data = job.get("input") or {}
    tts_config = _with_runtime_keys(job, "tts_config")
    tts_provider = tts_config.get("provider") or input_data.get("tts_provider") or "edge"
    default_tts_model = "volc.service_type.10029" if tts_provider == "doubao" else "speech-2.8-hd"
    default_tts_voice_id = "zh_male_beijingxiaoye_emo_v2_mars_bigtts" if tts_provider == "doubao" else "male-qn-qingse"
    return {
        "story": state.get("story") or {},
        "voice": input_data.get("voice") or "zh-CN-YunxiNeural",
        "rate": input_data.get("rate") or "+12%",
        "tts_preset": input_data.get("tts_preset") or "custom",
        "tts_provider": tts_provider,
        "tts_base_url": tts_config.get("base_url") or "",
        "tts_api_key": tts_config.get("api_key") or "",
        "tts_group_id": tts_config.get("group_id") or "",
        "tts_model": tts_config.get("model") or default_tts_model,
        "tts_voice_id": tts_config.get("voice_id") or input_data.get("tts_voice_id") or default_tts_voice_id,
        "tts_speed": input_data.get("tts_speed") or 1,
        "tts_emotion": input_data.get("tts_emotion") or "",
        "tts_language_boost": input_data.get("tts_language_boost") or "Chinese",
        "project_id": str(job["project_id"]),
        "cleanup_intermediate": True,
        "intro_template": input_data.get("intro_template") or "none",
        "intro_image_seconds": input_data.get("intro_image_seconds") or 0.3,
        "image_size": input_data.get("image_size") or "9:16",
        "bgm_id": input_data.get("bgm_id") or "none",
        "intro_sfx_id": input_data.get("intro_sfx_id") or "default",
    }

def _render_updated_seconds(value: Any) -> float | None:
    if value is None or value == "":
        return None
    # save_job persists updated_at as integer epoch milliseconds (now_ms()); the
    # legacy "YYYY-MM-DD HH:MM:SS" string form came from the old time.strftime path.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return time.time() - float(value) / 1000.0
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    try:
        return time.time() - time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return None

def _wait_render_job(job: dict[str, Any]) -> dict[str, Any]:
    api = _api()
    render_job_id = str(job["artifacts"].get("render_job_id") or "")
    if not render_job_id:
        return job
    while True:
        api._check_cancelled(job)
        render_job = api.get_render_job(render_job_id, str(job["project_id"]))
        if not render_job:
            raise AutoPipelineError("渲染任务丢失")
        if render_job.get("status") == "running":
            ma = _render_updated_seconds(render_job.get("updated_at"))
            if ma is not None and ma > RENDER_STALL_SECONDS:
                raise AutoPipelineError(_RENDER_STALL_MSG)
        job["artifacts"]["render_job"] = render_job
        progress = float(render_job.get("progress") or 0)
        job = _set_step(job, "render", "waiting", detail=str(render_job.get("detail") or render_job.get("stage") or "渲染中"), progress=0.9 + 0.09 * progress)
        if render_job.get("status") == "complete":
            result = render_job.get("result") or {}
            job["result"]["video_url"] = result.get("video") or ""
            state = _state_or_default(job)
            state["rendered_video"] = job["result"]["video_url"]
            state["result_text"] = json.dumps(result, ensure_ascii=False, indent=2)
            _write_state(job, state)
            return job
        if render_job.get("status") == "error":
            raise AutoPipelineError(str(render_job.get("error") or "渲染失败"))
        api.time.sleep(2)

def _run_render(job: dict[str, Any]) -> dict[str, Any]:
    if not (job.get("input") or {}).get("render_after_images", True):
        return _set_step(job, "render", "skipped", detail="已关闭自动渲染", progress=1)
    state = _state_or_default(job)
    final_path = project_dir(str(job["project_id"])) / "final.mp4"
    if final_path.exists() and final_path.stat().st_size > 0:
        job["result"]["video_url"] = f"/workspace/projects/{job['project_id']}/final.mp4"
        state["rendered_video"] = job["result"]["video_url"]
        _write_state(job, state)
        return _set_step(job, "render", "skipped", detail="成片已存在", progress=1)
    if not job["artifacts"].get("render_job_id"):
        _set_step(job, "render", "running", detail="正在创建渲染任务", progress=0.9)
        render_job = create_render_job(_render_payload(job, state))
        job["artifacts"]["render_job_id"] = render_job["job_id"]
        job["status"] = "waiting_child_job"
        _save(job)
    job = _wait_render_job(job)
    job["status"] = "running"
    return _set_step(job, "render", "done", detail="视频渲染完成", progress=1)

