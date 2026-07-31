"""Shared project path and workspace identity helpers.

These helpers used to live under projects/ and were imported by providers and
media layers, creating package cycles. Keep the pure path/id utilities in core
so domain packages can depend downward only.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.paths import PROJECTS_DIR, WORKSPACE


def workspace_project_id(value: Any, *, strict: bool = False) -> str:
    """Normalize a free-form project id into a relative workspace path segment.

    When *strict* is True, invalid values raise ValueError. When False, invalid
    or empty values return an empty string (image generation tolerates blanks).
    """
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw or raw == "images":
        if strict:
            raise ValueError("Invalid project_id")
        return ""
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} or ":" in part for part in parts):
        if strict:
            raise ValueError("Invalid project_id")
        return ""
    return "/".join(parts)


def workspace_project_ref(project_id: str) -> str:
    """Prefer projects/<id> when that on-disk project already exists."""
    if project_id.startswith("projects/"):
        return project_id
    if (PROJECTS_DIR / project_id).exists():
        return f"projects/{project_id}"
    return project_id


def public_project_id(project_ref: str) -> str:
    """Strip the projects/ prefix for API/public project ids."""
    if project_ref.startswith("projects/"):
        return project_ref[len("projects/") :]
    return project_ref


def workspace_path_from_url(url: str) -> Path | None:
    prefix = "/workspace/"
    if not isinstance(url, str) or not url.startswith(prefix):
        return None
    candidate = (WORKSPACE / url[len(prefix) :]).resolve()
    try:
        candidate.relative_to(WORKSPACE.resolve())
    except ValueError:
        return None
    return candidate


def project_image_for_index(image_dir: Path, index: int) -> Path | None:
    stem = f"shot_{index:02d}"
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = image_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    matches = sorted(image_dir.glob(f"{stem}.*"))
    return matches[0] if matches else None


def slug_project_topic(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:42] or "未命名项目"


def safe_project_id(value: Any, topic: str = "") -> str:
    """Return a filesystem-safe project id, generating one when the input is unsafe."""
    raw = str(value or "").strip()
    if raw and not re.search(r'[<>:"/\\|?*\x00-\x1f]', raw) and ".." not in raw:
        return raw[:120]
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{slug_project_topic(topic)}_{uuid.uuid4().hex[:6]}"


def project_dir(project_id: str) -> Path:
    """Resolve a project directory under the current PROJECTS_DIR.

    Reads PROJECTS_DIR from ``app.core.paths`` at call time so tests can
    monkeypatch ``app.core.paths.PROJECTS_DIR``.
    """
    from app.core import paths as path_mod
    return path_mod.PROJECTS_DIR / project_id

