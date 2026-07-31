from __future__ import annotations

from typing import Any

from app.core.errors import RenderError
from .drafts import (
    _copy_draft_to_root,
    _read_export_manifest,
    _safe_draft_name,
    _update_draft_meta,
    _update_root_meta,
    _user_draft_root,
)
from .paths import (
    _draft_source_dir,
    _jianying_project_config_root,
    _pkg,
    _read_json,
    _root_meta_path,
    _start_menu_shortcut,
)


def _launch_jianying() -> tuple[bool, str]:
    os = _pkg().os
    shortcut = _start_menu_shortcut()
    if shortcut:
        try:
            os.startfile(str(shortcut))  # type: ignore[attr-defined]
            return True, str(shortcut)
        except Exception:
            pass
    try:
        os.startfile(str(_jianying_project_config_root()))  # type: ignore[attr-defined]
        return False, str(_jianying_project_config_root())
    except Exception:
        return False, ""


def open_draft_in_jianying(draft_dir: str) -> dict[str, Any]:
    source = _draft_source_dir(draft_dir)
    root_meta_path = _root_meta_path()
    if not root_meta_path.exists():
        raise RenderError("未找到剪映本地草稿索引，请先启动一次剪映专业版。")
    root_meta = _read_json(root_meta_path)
    target_root = _user_draft_root(root_meta)
    target = _copy_draft_to_root(source, target_root)
    manifest = _read_export_manifest(source)
    draft_name = _safe_draft_name(str(manifest.get("draft_name") or target.name))
    if draft_name != target.name:
        draft_name = _safe_draft_name(target.name)
    duration_us = int(round(float(manifest.get("duration_sec") or 0) * 1_000_000))
    _update_draft_meta(target, draft_name, target_root, duration_us)
    _update_root_meta(root_meta_path, target, target_root, draft_name, duration_us)
    launched, launch_target = _launch_jianying()
    return {
        "ok": True,
        "draft_name": draft_name,
        "source_draft_dir": str(source),
        "jianying_draft_dir": str(target.resolve()),
        "jianying_draft_root": str(target_root.resolve()),
        "root_meta": str(root_meta_path.resolve()),
        "launched": launched,
        "launch_target": launch_target,
        "message": "已同步到剪映草稿目录并尝试启动剪映。若剪映已打开，请回到首页刷新草稿列表后进入编辑。",
    }
