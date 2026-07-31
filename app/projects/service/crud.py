from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

def _svc():
    """Late-bind package attributes for monkeypatch-friendly path constants."""
    from app.projects import service as svc
    return svc

from .identity import _ensure_project_child, _project_id_for_topic, _rename_project_dir_if_needed, _replace_project_refs, project_dir, safe_project_id
from .image_state import _apply_latest_image_job_statuses, _copy_project_images, _preserve_existing_image_errors, _sync_cover_from_selected_shot, hydrate_project_images

def write_project_files(state: dict[str, Any], *, set_active: bool = True) -> dict[str, Any]:
    old_project_id = safe_project_id(state.get("project_id"), str(state.get("topic") or ""))
    lock_project_id = bool(state.get("_lock_project_id") or state.get("lock_project_id"))
    project_id = old_project_id if lock_project_id else _project_id_for_topic(old_project_id, str(state.get("topic") or ""))
    if old_project_id != project_id:
        _rename_project_dir_if_needed(old_project_id, project_id)
        state = _replace_project_refs(state, old_project_id, project_id)
    target_project_dir = project_dir(project_id)
    prompts_dir = target_project_dir / "prompts"
    target_project_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        **state,
        "project_id": project_id,
        "project_url": f"/workspace/projects/{project_id}",
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _preserve_existing_image_errors(payload, target_project_dir)
    _copy_project_images(payload, target_project_dir)
    _apply_latest_image_job_statuses(payload, project_id)
    _sync_cover_from_selected_shot(payload)
    story = payload.get("story")

    (target_project_dir / "state.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (target_project_dir / "copy.txt").write_text(str(payload.get("copy_text") or ""), encoding="utf-8")
    (target_project_dir / "result.txt").write_text(str(payload.get("result_text") or ""), encoding="utf-8")
    (prompts_dir / "copy_prompt.txt").write_text(str(payload.get("copy_prompt") or ""), encoding="utf-8")
    (prompts_dir / "copy_to_story_prompt.txt").write_text(str(payload.get("copy_to_story_prompt") or ""), encoding="utf-8")
    (prompts_dir / "image_prompt.txt").write_text(str(payload.get("image_prompt") or ""), encoding="utf-8")
    (prompts_dir / "improve_image_prompt.txt").write_text(str(payload.get("improve_image_prompt") or ""), encoding="utf-8")
    (prompts_dir / "theme_idea_prompt.txt").write_text(str(payload.get("theme_idea_prompt") or ""), encoding="utf-8")
    if isinstance(story, dict):
        (target_project_dir / "story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    elif payload.get("story_json"):
        (target_project_dir / "story.json").write_text(str(payload.get("story_json")), encoding="utf-8")
    (target_project_dir / "metadata.json").write_text(json.dumps({
        "project_id": project_id,
        "topic": payload.get("topic") or "",
        "saved_at": payload["saved_at"],
        "project_url": payload["project_url"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if set_active:
        _svc().ACTIVE_PROJECT.parent.mkdir(parents=True, exist_ok=True)
        _svc().ACTIVE_PROJECT.write_text(json.dumps({"project_id": project_id}, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

def read_project_state(project_id: str) -> dict[str, Any]:
    safe_id = safe_project_id(project_id)
    state_path = project_dir(safe_id) / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(safe_id)
    return hydrate_project_images(json.loads(state_path.read_text(encoding="utf-8")), safe_id)

def project_summary(target_project_dir: Path) -> dict[str, Any] | None:
    if not target_project_dir.is_dir():
        return None
    state_path = target_project_dir / "state.json"
    metadata_path = target_project_dir / "metadata.json"
    source = metadata_path if metadata_path.exists() else state_path
    if not source.exists():
        return None
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        return None
    project_id = target_project_dir.name
    topic = str(data.get("topic") or project_id)
    saved_at = str(data.get("saved_at") or "")
    return {
        "project_id": project_id,
        "topic": topic,
        "saved_at": saved_at,
        "project_url": f"/workspace/projects/{project_id}",
    }

def current_project() -> dict[str, Any]:
    if not _svc().ACTIVE_PROJECT.exists():
        if _svc().LEGACY_PROJECT_STATE.exists():
            try:
                return {"exists": True, "state": json.loads(_svc().LEGACY_PROJECT_STATE.read_text(encoding="utf-8"))}
            except Exception:
                pass
        return {"exists": False}
    active = json.loads(_svc().ACTIVE_PROJECT.read_text(encoding="utf-8-sig"))
    project_id = safe_project_id(active.get("project_id"))
    state_path = project_dir(project_id) / "state.json"
    if not state_path.exists():
        return {"exists": False}
    return {"exists": True, "state": read_project_state(project_id)}

def active_project_id() -> str:
    if not _svc().ACTIVE_PROJECT.exists():
        return ""
    try:
        return str(json.loads(_svc().ACTIVE_PROJECT.read_text(encoding="utf-8-sig")).get("project_id") or "")
    except Exception:
        return ""

def list_projects() -> list[dict[str, Any]]:
    _svc().PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects = [
        item for item in (project_summary(path) for path in _svc().PROJECTS_DIR.iterdir())
        if item is not None
    ]
    projects.sort(key=lambda item: item.get("saved_at") or "", reverse=True)
    return projects

def activate_project(project_id: str) -> dict[str, Any]:
    safe_id = safe_project_id(project_id)
    state = read_project_state(safe_id)
    _svc().ACTIVE_PROJECT.parent.mkdir(parents=True, exist_ok=True)
    _svc().ACTIVE_PROJECT.write_text(json.dumps({"project_id": safe_id}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "project_id": safe_id, "state": state}

def delete_project(project_id: str) -> dict[str, Any]:
    safe_id = safe_project_id(project_id)
    target = _ensure_project_child(project_dir(safe_id))
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(safe_id)
    shutil.rmtree(target)
    if target.exists():
        raise RuntimeError("Project folder was not removed")
    if active_project_id() == safe_id and _svc().ACTIVE_PROJECT.exists():
        _svc().ACTIVE_PROJECT.unlink()
    return {
        "ok": True,
        "project_id": safe_id,
        "deleted": True,
        "active_project_id": active_project_id(),
        "projects": list_projects(),
    }

def save_project_state(state: dict[str, Any]) -> dict[str, Any]:
    _svc().WORKSPACE.mkdir(parents=True, exist_ok=True)
    _svc().PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = write_project_files(state)
    return {
        "ok": True,
        "project_id": payload["project_id"],
        "project_url": payload["project_url"],
        "saved_at": payload["saved_at"],
        "state": payload,
    }

