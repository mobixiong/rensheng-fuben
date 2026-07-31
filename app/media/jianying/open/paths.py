from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.errors import RenderError


ROOT_META_NAME = "root_meta_info.json"


def _pkg():
    """Late-bind package attributes so tests can monkeypatch the package surface."""
    from app.media.jianying import open as pkg
    return pkg


def _local_appdata() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise RenderError("未找到 LOCALAPPDATA，无法定位剪映草稿目录。")
    return Path(value)


def _start_menu_shortcut() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    shortcut = (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "剪映专业版"
        / "剪映专业版.lnk"
    )
    return shortcut if shortcut.exists() else None


def _jianying_project_config_root() -> Path:
    return _local_appdata() / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"


def _root_meta_path() -> Path:
    return _jianying_project_config_root() / ROOT_META_NAME


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RenderError(f"无法读取剪映索引文件：{path}") from exc


def _draft_source_dir(value: str) -> Path:
    if not value:
        raise RenderError("缺少 draft_dir。")
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(_pkg().WORKSPACE.resolve())
    except ValueError as exc:
        raise RenderError("draft_dir 不在工作区内，已拒绝打开。") from exc
    if not (candidate / "draft_content.json").exists():
        raise RenderError("未找到 draft_content.json，请先导出剪映草稿。")
    if not (candidate / "draft_meta_info.json").exists():
        raise RenderError("未找到 draft_meta_info.json，请先导出剪映草稿。")
    return candidate


def _normalize_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")
