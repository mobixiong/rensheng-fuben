from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from .audio_assets import WORKSPACE_SFX_DIR, list_bgm_options, list_intro_sfx_options
from .paths import WORKSPACE
from .upload_service import AudioUploadError, save_uploaded_audio


router = APIRouter()


@router.get("/api/bgm")
def bgm_list() -> dict[str, Any]:
    return {"items": list_bgm_options()}


@router.get("/api/intro-sfx")
def intro_sfx_list() -> dict[str, Any]:
    return {"items": list_intro_sfx_options()}


@router.post("/api/bgm/upload")
def bgm_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        target = save_uploaded_audio(file.filename or "audio", file.file, WORKSPACE / "bgm")
    except AudioUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": f"workspace/bgm/{target.name}",
        "name": target.stem,
        "filename": target.name,
        "items": list_bgm_options(),
    }


@router.post("/api/intro-sfx/upload")
def intro_sfx_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        target = save_uploaded_audio(file.filename or "audio", file.file, WORKSPACE_SFX_DIR)
    except AudioUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": f"workspace/sfx/{target.name}",
        "name": target.stem,
        "filename": target.name,
        "items": list_intro_sfx_options(),
    }
