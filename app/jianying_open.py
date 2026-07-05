import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .errors import RenderError
from .job_store import write_json_atomic
from .paths import WORKSPACE


ROOT_META_NAME = "root_meta_info.json"


def _local_appdata() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise RenderError("未找到 LOCALAPPDATA，无法定位剪映草稿目录。")
    return Path(value)


def _start_menu_shortcut() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    shortcut = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "剪映专业版" / "剪映专业版.lnk"
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
        candidate.relative_to(WORKSPACE.resolve())
    except ValueError as exc:
        raise RenderError("draft_dir 不在工作区内，已拒绝打开。") from exc
    if not (candidate / "draft_content.json").exists():
        raise RenderError("未找到 draft_content.json，请先导出剪映草稿。")
    if not (candidate / "draft_meta_info.json").exists():
        raise RenderError("未找到 draft_meta_info.json，请先导出剪映草稿。")
    return candidate


def _normalize_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _candidate_user_draft_roots(root_meta: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    entries = root_meta.get("all_draft_store")
    if isinstance(entries, list):
        sorted_entries = sorted(
            entries,
            key=lambda item: int(item.get("tm_draft_modified") or 0) if isinstance(item, dict) else 0,
            reverse=True,
        )
        for item in sorted_entries:
            if not isinstance(item, dict):
                continue
            for key in ("draft_root_path", "draft_fold_path"):
                raw = str(item.get(key) or "").strip()
                if not raw:
                    continue
                path = Path(raw)
                root = path.parent if key == "draft_fold_path" else path
                if root.exists() and root.is_dir() and root not in roots:
                    roots.append(root)
    raw_root = str(root_meta.get("root_path") or "").strip()
    if raw_root:
        root = Path(raw_root)
        if root.exists() and root.is_dir() and root not in roots:
            roots.append(root)
    return roots


def _user_draft_root(root_meta: dict[str, Any]) -> Path:
    roots = _candidate_user_draft_roots(root_meta)
    if roots:
        return roots[0]
    fallback = _jianying_project_config_root()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _safe_draft_name(value: str) -> str:
    cleaned = "".join(ch for ch in str(value or "").strip() if ch not in '<>:"/\\|?*\x00-\x1f')
    return cleaned[:80].strip() or "人生副本剪映草稿"


def _copy_draft_to_root(source: Path, target_root: Path) -> Path:
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / _safe_draft_name(source.name)
    if source.resolve() == target.resolve():
        return target
    if target.exists():
        if (target / "export_manifest.json").exists():
            shutil.rmtree(target)
        else:
            target = target_root / _safe_draft_name(f"{source.name}_{time.strftime('%H%M%S')}")
    shutil.copytree(source, target)
    return target


def _folder_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _read_export_manifest(source: Path) -> dict[str, Any]:
    path = source / "export_manifest.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_draft_id(target: Path) -> str:
    meta_path = target / "draft_meta_info.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return str(uuid.uuid4()).upper()
    draft_id = str(meta.get("draft_id") or "").strip()
    return draft_id or str(uuid.uuid4()).upper()


def _update_draft_meta(target: Path, draft_name: str, target_root: Path, duration_us: int) -> None:
    meta_path = target / "draft_meta_info.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return
    now_us = int(time.time() * 1_000_000)
    meta.update({
        "draft_fold_path": str(target.resolve()),
        "draft_name": draft_name,
        "draft_root_path": str(target_root.resolve()),
        "tm_duration": duration_us,
        "tm_draft_modified": now_us,
    })
    write_json_atomic(meta_path, meta)


def _root_entry(target: Path, target_root: Path, draft_name: str, duration_us: int) -> dict[str, Any]:
    now_us = int(time.time() * 1_000_000)
    return {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False,
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "",
        "draft_fold_path": _normalize_path(target),
        "draft_id": _read_draft_id(target),
        "draft_is_ai_shorts": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_invisible": False,
        "draft_is_pippit_draft": False,
        "draft_is_web_article_video": False,
        "draft_json_file": _normalize_path(target / "draft_content.json"),
        "draft_name": draft_name,
        "draft_new_version": "",
        "draft_root_path": _normalize_path(target_root),
        "draft_timeline_materials_size": _folder_size(target),
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "pippit_avatar_url": "",
        "pippit_extra_info": "",
        "pippit_id": "",
        "pippit_user_name": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": duration_us,
    }


def _backup_once(path: Path) -> None:
    backup = path.with_name(path.name + ".bak_rensheng")
    if not backup.exists() and path.exists():
        shutil.copy2(path, backup)


def _update_root_meta(root_meta_path: Path, target: Path, target_root: Path, draft_name: str, duration_us: int) -> None:
    root_meta = _read_json(root_meta_path)
    entries = root_meta.setdefault("all_draft_store", [])
    if not isinstance(entries, list):
        raise RenderError("剪映索引 all_draft_store 格式异常。")
    target_path = _normalize_path(target)
    entries[:] = [
        entry for entry in entries
        if not (isinstance(entry, dict) and _normalize_path(Path(str(entry.get("draft_fold_path") or ""))) == target_path)
    ]
    entries.insert(0, _root_entry(target, target_root, draft_name, duration_us))
    root_meta["draft_ids"] = max(int(root_meta.get("draft_ids") or 0), len(entries)) + 1
    _backup_once(root_meta_path)
    write_json_atomic(root_meta_path, root_meta)


def _launch_jianying() -> tuple[bool, str]:
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
