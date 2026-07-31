from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.errors import RenderError
from app.media.jianying.export import create_jianying_draft
from app.media.jianying.export_jobs import create_jianying_draft_job, get_jianying_draft_job
from app.media.jianying.open import open_draft_in_jianying
from app.core.schemas import JianyingDraftRequest, JianyingOpenRequest


router = APIRouter()


@router.post("/api/jianying/drafts")
def jianying_draft_create(req: JianyingDraftRequest) -> dict[str, Any]:
    try:
        return create_jianying_draft(req.model_dump())
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/jianying/drafts/jobs")
def jianying_draft_job_create(req: JianyingDraftRequest) -> dict[str, Any]:
    try:
        return create_jianying_draft_job(req.model_dump())
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/jianying/drafts/jobs/{job_id}")
def jianying_draft_job_get(job_id: str, project_id: str = "") -> dict[str, Any]:
    job = get_jianying_draft_job(job_id, project_id)
    if not job:
        raise HTTPException(status_code=404, detail="Jianying draft job not found")
    return job


@router.post("/api/jianying/drafts/open")
def jianying_draft_open(req: JianyingOpenRequest) -> dict[str, Any]:
    try:
        return open_draft_in_jianying(req.draft_dir)
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
