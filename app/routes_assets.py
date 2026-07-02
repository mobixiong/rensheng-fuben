from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .audio_assets import WORKSPACE_SFX_DIR, list_bgm_options, list_intro_sfx_options
from .paths import WORKSPACE
from .reference_assets import (
    ReferenceAssetError,
    add_asset,
    create_collection,
    delete_asset,
    delete_collection,
    get_collection,
    list_collections,
)
from .schemas import ReferenceCollectionCreateRequest
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


@router.get("/api/reference-collections")
def reference_collections_list() -> dict[str, Any]:
    return {"collections": list_collections()}


@router.post("/api/reference-collections")
def reference_collection_create(req: ReferenceCollectionCreateRequest) -> dict[str, Any]:
    try:
        return {"collection": create_collection(req.name, req.description)}
    except ReferenceAssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/reference-collections/{collection_id}")
def reference_collection_get(collection_id: str) -> dict[str, Any]:
    try:
        return {"collection": get_collection(collection_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Reference collection not found: {exc}") from exc


@router.delete("/api/reference-collections/{collection_id}")
def reference_collection_delete(collection_id: str) -> dict[str, Any]:
    try:
        return delete_collection(collection_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Reference collection not found: {exc}") from exc
    except ReferenceAssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/reference-collections/{collection_id}/assets")
def reference_collection_asset_upload(
    collection_id: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    asset_type: str = Form("character"),
    description: str = Form(""),
    tags: str = Form(""),
) -> dict[str, Any]:
    try:
        return add_asset(
            collection_id,
            filename=file.filename or "image",
            source=file.file,
            name=name,
            asset_type=asset_type,
            description=description,
            tags=tags,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Reference collection not found: {exc}") from exc
    except ReferenceAssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/reference-collections/{collection_id}/assets/{asset_id}")
def reference_collection_asset_delete(collection_id: str, asset_id: str) -> dict[str, Any]:
    try:
        return {"collection": delete_asset(collection_id, asset_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Reference asset not found: {exc}") from exc
