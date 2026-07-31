import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.workflow.auto_pipeline import list_auto_pipeline_jobs
from app.images.jobs import list_project_jobs
from app.core.paths import EXAMPLES
from app.projects.service import active_project_id, activate_project, current_project, delete_project, list_projects, save_project_state
from app.core.schemas import ProjectActivateRequest, ProjectDeleteRequest


router = APIRouter()


@router.get("/api/example")
def example() -> dict[str, Any]:
    return json.loads((EXAMPLES / "buffet_story.json").read_text(encoding="utf-8"))


@router.get("/api/project/current")
def project_current() -> dict[str, Any]:
    try:
        data = current_project()
        state = data.get("state") if isinstance(data, dict) else None
        project_id = state.get("project_id") if isinstance(state, dict) else ""
        data["image_jobs"] = list_project_jobs(str(project_id or ""), active_only=True) if project_id else []
        data["auto_pipeline_jobs"] = list_auto_pipeline_jobs(str(project_id or ""), active_only=True) if project_id else []
        return data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project state is unreadable: {exc}") from exc


@router.get("/api/projects")
def projects_list() -> dict[str, Any]:
    return {"projects": list_projects(), "active_project_id": active_project_id()}


@router.post("/api/project/activate")
def project_activate(req: ProjectActivateRequest) -> dict[str, Any]:
    try:
        data = activate_project(req.project_id)
        data["image_jobs"] = list_project_jobs(data.get("project_id", ""), active_only=True)
        data["auto_pipeline_jobs"] = list_auto_pipeline_jobs(data.get("project_id", ""), active_only=True)
        return data
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Project not found: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project activate failed: {exc}") from exc


@router.post("/api/project/delete")
def project_delete(req: ProjectDeleteRequest) -> dict[str, Any]:
    try:
        return delete_project(req.project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Project not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project delete failed: {exc}") from exc


@router.post("/api/project/current")
def project_save(state: dict[str, Any]) -> dict[str, Any]:
    try:
        return save_project_state(state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project save failed: {exc}") from exc
