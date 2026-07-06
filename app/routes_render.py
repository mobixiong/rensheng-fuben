import asyncio
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from .errors import RenderError
from .paths import WORKSPACE
from .pipeline import render_intro_previews, render_story
from .render_service import create_render_job, get_render_job
from .render_validation import validate_ready_for_render
from .schemas import IntroPreviewRequest, RenderRequest, TtsPreviewRequest
from .tts_adapter import TtsConfig, synthesize_tts
from .doubao_voices import get_doubao_voice_catalog


router = APIRouter()


TTS_PREVIEW_TEXT_LIMIT = 160
TTS_PREVIEW_DIR = WORKSPACE / "previews" / "tts"


def _prune_tts_previews() -> None:
    try:
        if not TTS_PREVIEW_DIR.exists():
            return
        files = sorted(TTS_PREVIEW_DIR.glob("preview_*.mp3"), key=lambda path: path.stat().st_mtime, reverse=True)
        cutoff = time.time() - 60 * 60 * 24
        for index, path in enumerate(files):
            if index >= 24 or path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except Exception:
        return


@router.post("/api/render")
def render(req: RenderRequest) -> dict[str, Any]:
    try:
        validate_ready_for_render(req.story)
        return render_story(
            story=req.story,
            voice=req.voice,
            rate=req.rate,
            tts_config=TtsConfig.from_payload(req.model_dump()),
            project_id=req.project_id,
            cleanup_intermediate=req.cleanup_intermediate,
            force_render=req.force_render,
            intro_template=req.intro_template,
            bgm_id=req.bgm_id,
            intro_image_seconds=req.intro_image_seconds,
            intro_sfx_id=req.intro_sfx_id,
            image_size=req.image_size,
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
            image_size=req.image_size,
        )
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/tts/preview")
def tts_preview(req: TtsPreviewRequest) -> dict[str, Any]:
    try:
        text = (req.text or "").strip()[:TTS_PREVIEW_TEXT_LIMIT]
        if not text:
            raise RenderError("Preview text is empty")
        TTS_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        _prune_tts_previews()
        out_path = TTS_PREVIEW_DIR / f"preview_{uuid.uuid4().hex[:12]}.mp3"
        config = TtsConfig.from_payload(req.model_dump())
        if config.provider in {"minimax", "doubao"} and not config.api_key:
            raise RenderError(f"{config.provider} TTS missing API key")
        if config.provider in {"minimax", "doubao"} and not config.voice_id:
            raise RenderError(f"{config.provider} TTS missing voice id")
        asyncio.run(synthesize_tts(text, out_path, config))
        if not out_path.exists() or out_path.stat().st_size <= 0:
            raise RenderError("TTS preview returned an empty audio file")
        return {
            "audio": f"/workspace/previews/tts/{out_path.name}",
            "provider": config.provider,
            "bytes": out_path.stat().st_size,
        }
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/tts/doubao/voices")
def doubao_tts_voices(resource_id: str = "") -> dict[str, Any]:
    return get_doubao_voice_catalog(resource_id)


@router.post("/api/render/jobs")
def render_job_create(req: RenderRequest) -> dict[str, Any]:
    try:
        return create_render_job(req.model_dump())
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/render/jobs/{job_id}")
def render_job_get(job_id: str, project_id: str = "") -> dict[str, Any]:
    job = get_render_job(job_id, project_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    return job
