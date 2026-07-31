"""Jianying draft open package."""
from __future__ import annotations

import os

from app.core.paths import WORKSPACE

from .paths import (
    ROOT_META_NAME,
    _draft_source_dir,
    _jianying_project_config_root,
    _local_appdata,
    _normalize_path,
    _read_json,
    _root_meta_path,
    _start_menu_shortcut,
)
from .drafts import (
    _backup_once,
    _candidate_user_draft_roots,
    _copy_draft_to_root,
    _folder_size,
    _read_draft_id,
    _read_export_manifest,
    _root_entry,
    _safe_draft_name,
    _update_draft_meta,
    _update_root_meta,
    _user_draft_root,
)
from .service import _launch_jianying, open_draft_in_jianying

__all__ = [
    "ROOT_META_NAME",
    "WORKSPACE",
    "os",
    "_backup_once",
    "_candidate_user_draft_roots",
    "_copy_draft_to_root",
    "_draft_source_dir",
    "_folder_size",
    "_jianying_project_config_root",
    "_launch_jianying",
    "_local_appdata",
    "_normalize_path",
    "_read_draft_id",
    "_read_export_manifest",
    "_read_json",
    "_root_entry",
    "_root_meta_path",
    "_safe_draft_name",
    "_start_menu_shortcut",
    "_update_draft_meta",
    "_update_root_meta",
    "_user_draft_root",
    "open_draft_in_jianying",
]
