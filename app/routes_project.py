import json
from typing import Any

from fastapi import APIRouter, HTTPException

from .paths import EXAMPLES
from .project_service import active_project_id, activate_project, current_project, list_projects, save_project_state
from .schemas import ProjectActivateRequest


router = APIRouter()


@router.get("/api/example")
def example() -> dict[str, Any]:
    return json.loads((EXAMPLES / "buffet_story.json").read_text(encoding="utf-8"))


@router.get("/api/project/current")
def project_current() -> dict[str, Any]:
    try:
        return current_project()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project state is unreadable: {exc}") from exc


@router.get("/api/projects")
def projects_list() -> dict[str, Any]:
    return {"projects": list_projects(), "active_project_id": active_project_id()}


@router.post("/api/project/activate")
def project_activate(req: ProjectActivateRequest) -> dict[str, Any]:
    try:
        return activate_project(req.project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Project not found: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project activate failed: {exc}") from exc


@router.post("/api/project/current")
def project_save(state: dict[str, Any]) -> dict[str, Any]:
    try:
        return save_project_state(state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project save failed: {exc}") from exc
