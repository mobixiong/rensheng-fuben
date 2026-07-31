from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

def _svc():
    """Late-bind package attributes for monkeypatch-friendly path constants."""
    from app.projects import service as svc
    return svc

GENERATED_PROJECT_ID_RE = re.compile(r"^(?P<stamp>\d{8}_\d{6})_(?P<slug>.+)_(?P<suffix>[0-9a-f]{6})$")

def _slug(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:42] or "未命名项目"

def safe_project_id(value: Any, topic: str = "") -> str:
    raw = str(value or "").strip()
    if raw and not re.search(r'[<>:"/\\|?*\x00-\x1f]', raw) and ".." not in raw:
        return raw[:120]
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{_slug(topic)}_{uuid.uuid4().hex[:6]}"

def _ensure_project_child(path: Path) -> Path:
    resolved = path.resolve()
    projects_root = _svc().PROJECTS_DIR.resolve()
    try:
        resolved.relative_to(projects_root)
    except ValueError as exc:
        raise ValueError("Invalid project path") from exc
    return resolved

def _unique_project_id(project_id: str, current_id: str = "") -> str:
    candidate = project_id[:120]
    if candidate == current_id or not project_dir(candidate).exists():
        return candidate
    base = candidate[:113].rstrip("_")
    for _ in range(20):
        candidate = f"{base}_{uuid.uuid4().hex[:6]}"[:120]
        if candidate == current_id or not project_dir(candidate).exists():
            return candidate
    return safe_project_id("", candidate)

def _project_id_for_topic(current_id: str, topic: str) -> str:
    safe_id = safe_project_id(current_id, topic)
    clean_topic = str(topic or "").strip()
    if not clean_topic:
        return safe_id
    match = GENERATED_PROJECT_ID_RE.match(safe_id)
    if not match:
        return safe_id
    next_id = f"{match.group('stamp')}_{_slug(clean_topic)}_{match.group('suffix')}"
    return _unique_project_id(next_id, safe_id)

def _replace_project_refs(value: Any, old_project_id: str, new_project_id: str) -> Any:
    if old_project_id == new_project_id:
        return value
    if isinstance(value, dict):
        return {key: _replace_project_refs(item, old_project_id, new_project_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_project_refs(item, old_project_id, new_project_id) for item in value]
    if not isinstance(value, str):
        return value
    old_project_path = str(project_dir(old_project_id).resolve())
    new_project_path = str(project_dir(new_project_id).resolve())
    return (
        value
        .replace(f"/workspace/projects/{old_project_id}", f"/workspace/projects/{new_project_id}")
        .replace(old_project_path, new_project_path)
    )

def _rename_project_dir_if_needed(old_project_id: str, new_project_id: str) -> None:
    if not old_project_id or old_project_id == new_project_id:
        return
    old_dir = _ensure_project_child(project_dir(old_project_id))
    new_dir = _ensure_project_child(project_dir(new_project_id))
    if not old_dir.exists():
        return
    if new_dir.exists():
        return
    new_dir.parent.mkdir(parents=True, exist_ok=True)
    old_dir.rename(new_dir)
    _rewrite_project_refs_in_files(new_dir, old_project_id, new_project_id)

def _rewrite_project_refs_in_files(target_dir: Path, old_project_id: str, new_project_id: str) -> None:
    if old_project_id == new_project_id or not target_dir.exists():
        return
    for path in target_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".txt", ".srt", ".ass"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        next_text = str(_replace_project_refs(text, old_project_id, new_project_id))
        if next_text != text:
            path.write_text(next_text, encoding="utf-8")

def project_dir(project_id: str) -> Path:
    return _svc().PROJECTS_DIR / project_id

