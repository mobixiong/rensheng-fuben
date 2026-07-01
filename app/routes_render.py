from typing import Any

from fastapi import APIRouter, HTTPException

from .errors import RenderError
from .pipeline import render_intro_previews, render_story
from .render_service import create_render_job, get_render_job
from .schemas import IntroPreviewRequest, RenderRequest
from .tts_adapter import TtsConfig


router = APIRouter()


@router.post("/api/render")
def render(req: RenderRequest) -> dict[str, Any]:
    try:
        return render_story(
            story=req.story,
            voice=req.voice,
            rate=req.rate,
            tts_config=TtsConfig.from_payload(req.model_dump()),
            project_id=req.project_id,
            cleanup_intermediate=req.cleanup_intermediate,
            intro_template=req.intro_template,
            bgm_id=req.bgm_id,
            intro_image_seconds=req.intro_image_seconds,
            intro_sfx_id=req.intro_sfx_id,
        )
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/render/intro-previews")
def render_intro_preview(req: IntroPreviewRequest) -> dict[str, Any]:
    try:
        return render_intro_previews(
            story=req.story,
            project_id=req.project_id,
            templates=req.templates,
            duration=req.duration,
            image_seconds=req.image_seconds,
        )
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/render/jobs")
def render_job_create(req: RenderRequest) -> dict[str, Any]:
    return create_render_job(req.model_dump())


@router.get("/api/render/jobs/{job_id}")
def render_job_get(job_id: str) -> dict[str, Any]:
    job = get_render_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    return job
