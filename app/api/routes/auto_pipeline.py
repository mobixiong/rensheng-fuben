from typing import Any

from fastapi import APIRouter, HTTPException

from app.workflow.auto_pipeline import (
    cancel_auto_pipeline_job,
    create_auto_pipeline_job,
    get_auto_pipeline_job,
    list_auto_pipeline_jobs,
    resume_auto_pipeline_job,
)
from app.core.schemas import AutoPipelineRequest


router = APIRouter()


@router.post("/api/auto-pipeline/jobs")
def auto_pipeline_create(req: AutoPipelineRequest) -> dict[str, Any]:
    try:
        return {"job": create_auto_pipeline_job(req.model_dump())}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto pipeline create failed: {exc}") from exc


@router.get("/api/auto-pipeline/jobs")
def auto_pipeline_list(project_id: str, active_only: bool = False) -> dict[str, Any]:
    try:
        return {"jobs": list_auto_pipeline_jobs(project_id, active_only=active_only)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto pipeline list failed: {exc}") from exc


@router.get("/api/auto-pipeline/jobs/{project_id}/{job_id}")
def auto_pipeline_get(project_id: str, job_id: str) -> dict[str, Any]:
    try:
        return {"job": get_auto_pipeline_job(project_id, job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Auto pipeline job not found: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto pipeline get failed: {exc}") from exc


@router.post("/api/auto-pipeline/jobs/{project_id}/{job_id}/cancel")
def auto_pipeline_cancel(project_id: str, job_id: str) -> dict[str, Any]:
    try:
        return {"job": cancel_auto_pipeline_job(project_id, job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Auto pipeline job not found: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto pipeline cancel failed: {exc}") from exc


@router.post("/api/auto-pipeline/jobs/{project_id}/{job_id}/resume")
def auto_pipeline_resume(project_id: str, job_id: str, req: AutoPipelineRequest | None = None) -> dict[str, Any]:
    try:
        payload = req.model_dump() if req else None
        return {"job": resume_auto_pipeline_job(project_id, job_id, payload)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Auto pipeline job not found: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto pipeline resume failed: {exc}") from exc
