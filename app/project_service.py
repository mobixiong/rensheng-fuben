import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .image_status import (
    IMAGE_JOB_DONE,
    IMAGE_JOB_FAILED,
    IMAGE_STATUS_ERROR,
    IMAGE_STATUS_PENDING,
    IMAGE_STATUS_POLICY_ERROR,
    TERMINAL_IMAGE_ITEM_STATUSES,
    has_shot_image,
    mark_image_done,
    mark_image_failure,
    normalize_persisted_image_state,
    should_keep_incoming_image_error,
)
from .paths import ACTIVE_PROJECT, LEGACY_PROJECT_STATE, PROJECTS_DIR, WORKSPACE

PROMPT_POLICY_ERROR_MARKERS = (
    "content_policy_violation",
    "policy_violation",
    "提示词被内容安全策略拦截",
    "防护限制",
    "不合规",
    "内容安全",
)
PROMPT_POLICY_ERROR_MESSAGE = (
    "提示词被内容安全策略拦截：日志显示本次生图返回 content_policy_violation，"
    "可能包含暴力、血腥或敏感表达。请修改该镜头的口播、画面描述或图片提示词后重试。"
)
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
    projects_root = PROJECTS_DIR.resolve()
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
    return PROJECTS_DIR / project_id


def _workspace_path_from_url(url: str) -> Path | None:
    prefix = "/workspace/"
    if not isinstance(url, str) or not url.startswith(prefix):
        return None
    candidate = (WORKSPACE / url[len(prefix):]).resolve()
    try:
        candidate.relative_to(WORKSPACE.resolve())
    except ValueError:
        return None
    return candidate


def _project_image_for_index(image_dir: Path, index: int) -> Path | None:
    stem = f"shot_{index:02d}"
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = image_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    matches = sorted(image_dir.glob(f"{stem}.*"))
    return matches[0] if matches else None


def _mark_shot_image_done(shot: dict[str, Any], project_id: str, image_path: Path) -> None:
    shot["image_path"] = str(image_path.resolve())
    shot["image_url"] = f"/workspace/projects/{project_id}/images/{image_path.name}"
    mark_image_done(shot)


def _has_prompt_policy_error(value: Any) -> bool:
    text = str(value or "")
    lowered = text.lower()
    return any(marker in lowered or marker in text for marker in PROMPT_POLICY_ERROR_MARKERS)


def _image_failure_count(value: Any) -> int | None:
    match = re.search(r"失败\s*(\d+)\s*张", str(value or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _mark_prompt_policy_errors(state: dict[str, Any]) -> None:
    result_text = state.get("result_text")
    if not _has_prompt_policy_error(result_text):
        return
    story = state.get("story")
    if not isinstance(story, dict):
        return
    shots = story.get("shots")
    if not isinstance(shots, list):
        return
    candidates: list[dict[str, Any]] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        if has_shot_image(shot):
            continue
        if shot.get("_image_error"):
            continue
        if str(shot.get("_image_status") or "") not in {"", IMAGE_STATUS_PENDING, IMAGE_STATUS_ERROR, IMAGE_STATUS_POLICY_ERROR}:
            continue
        candidates.append(shot)

    failed_count = _image_failure_count(result_text)
    if failed_count is not None and failed_count != len(candidates):
        return

    for shot in candidates:
        shot["_image_status"] = IMAGE_STATUS_POLICY_ERROR
        shot["_image_error"] = PROMPT_POLICY_ERROR_MESSAGE
        shot["_image_error_category"] = "prompt_policy"
        shot["_image_error_code"] = "content_policy_violation"


def _apply_latest_image_job_statuses(state: dict[str, Any], project_id: str) -> None:
    story = state.get("story")
    if not isinstance(story, dict):
        return
    shots = story.get("shots")
    if not isinstance(shots, list):
        return
    jobs_dir = project_dir(project_id) / "jobs"
    if not jobs_dir.exists():
        return
    seen: set[int] = set()
    for path in sorted(jobs_dir.glob("*.json"), key=lambda file: file.stat().st_mtime, reverse=True):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in job.get("items", []):
            try:
                index = int(item.get("shot_index"))
            except (TypeError, ValueError):
                continue
            if index in seen or index < 0 or index >= len(shots) or not isinstance(shots[index], dict):
                continue
            status = str(item.get("status") or "")
            if status not in TERMINAL_IMAGE_ITEM_STATUSES:
                continue
            seen.add(index)
            shot = shots[index]
            if has_shot_image(shot):
                mark_image_done(shot)
                continue
            if status == IMAGE_JOB_DONE:
                image_url = str(item.get("image_url") or "").strip()
                if image_url and not shot.get("image_url"):
                    shot["image_url"] = image_url
                    image_path = _workspace_path_from_url(image_url)
                    if image_path is not None:
                        shot["image_path"] = str(image_path)
                normalize_persisted_image_state(shot)
                continue
            if status != IMAGE_JOB_FAILED:
                continue
            error = str(item.get("error") or "").strip()
            category = str(item.get("error_category") or "").strip()
            code = str(item.get("error_code") or "").strip()
            if not error and not category and not code:
                continue
            mark_image_failure(shot, message=error or "图片生成失败", category=category or "unknown", code=code)


def _preserve_existing_image_errors(state: dict[str, Any], target_project_dir: Path) -> None:
    state_path = target_project_dir / "state.json"
    if not state_path.exists():
        return
    try:
        existing = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return
    existing_shots = ((existing.get("story") or {}).get("shots") or [])
    incoming_story = state.get("story")
    if not isinstance(incoming_story, dict):
        return
    incoming_shots = incoming_story.get("shots")
    if not isinstance(incoming_shots, list):
        return
    for index, shot in enumerate(incoming_shots):
        if index >= len(existing_shots) or not isinstance(shot, dict):
            continue
        existing_shot = existing_shots[index]
        if not isinstance(existing_shot, dict):
            continue
        if existing_shot.get("_image_status") != IMAGE_STATUS_POLICY_ERROR:
            continue
        if has_shot_image(shot):
            continue
        if not should_keep_incoming_image_error(shot):
            continue
        for key in ("_image_status", "_image_error", "_image_error_category", "_image_error_code"):
            if existing_shot.get(key):
                shot[key] = existing_shot[key]


def _copy_project_images(state: dict[str, Any], target_project_dir: Path) -> None:
    story = state.get("story")
    if not isinstance(story, dict):
        return
    shots = story.get("shots")
    if not isinstance(shots, list):
        return

    image_dir = target_project_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for index, shot in enumerate(shots, 1):
        if not isinstance(shot, dict):
            continue
        source = None
        raw_path = str(shot.get("image_path") or "").strip()
        if raw_path:
            source = Path(raw_path)
        if (not source or not source.exists()) and shot.get("image_url"):
            source = _workspace_path_from_url(str(shot.get("image_url")))
        if source and source.exists():
            target = image_dir / f"shot_{index:02d}{source.suffix or '.png'}"
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
        else:
            target = _project_image_for_index(image_dir, index)
        if target and target.exists():
            _mark_shot_image_done(shot, state["project_id"], target)
        else:
            normalize_persisted_image_state(shot)
    _mark_prompt_policy_errors(state)
    _apply_latest_image_job_statuses(state, state["project_id"])


def _sync_cover_from_selected_shot(state: dict[str, Any]) -> None:
    story = state.get("story")
    if not isinstance(story, dict):
        return
    cover = story.get("cover")
    if not isinstance(cover, dict):
        return
    shots = story.get("shots")
    if not isinstance(shots, list):
        return
    try:
        index = int(cover.get("source_shot_index"))
    except (TypeError, ValueError):
        return
    if index < 0 or index >= len(shots) or not isinstance(shots[index], dict):
        return
    shot = shots[index]
    image_path = str(shot.get("image_path") or "").strip()
    image_url = str(shot.get("image_url") or "").strip()
    if not image_path and not image_url:
        cover["_cover_status"] = "pending"
        return
    cover["image_path"] = image_path
    cover["image_url"] = image_url
    cover["image_size"] = shot.get("image_size") or story.get("image_size") or cover.get("image_size") or ""
    cover["image_prompt"] = str(cover.get("image_prompt") or shot.get("image_prompt") or shot.get("visual") or shot.get("voiceover") or "").strip()
    cover["_cover_status"] = "selected"
    cover.pop("_cover_error", None)
    cover.pop("raw_image_path", None)
    cover.pop("raw_image_url", None)


def hydrate_project_images(state: dict[str, Any], project_id: str) -> dict[str, Any]:
    story = state.get("story")
    if not isinstance(story, dict):
        return state
    shots = story.get("shots")
    if not isinstance(shots, list):
        return state
    image_dir = project_dir(project_id) / "images"
    for index, shot in enumerate(shots, 1):
        if not isinstance(shot, dict):
            continue
        image_path = _project_image_for_index(image_dir, index) if image_dir.exists() else None
        if image_path and image_path.exists():
            _mark_shot_image_done(shot, project_id, image_path)
        else:
            normalize_persisted_image_state(shot)
    _mark_prompt_policy_errors(state)
    _apply_latest_image_job_statuses(state, project_id)
    _sync_cover_from_selected_shot(state)
    return state


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
        ACTIVE_PROJECT.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_PROJECT.write_text(json.dumps({"project_id": project_id}, ensure_ascii=False, indent=2), encoding="utf-8")
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
    if not ACTIVE_PROJECT.exists():
        if LEGACY_PROJECT_STATE.exists():
            try:
                return {"exists": True, "state": json.loads(LEGACY_PROJECT_STATE.read_text(encoding="utf-8"))}
            except Exception:
                pass
        return {"exists": False}
    active = json.loads(ACTIVE_PROJECT.read_text(encoding="utf-8-sig"))
    project_id = safe_project_id(active.get("project_id"))
    state_path = project_dir(project_id) / "state.json"
    if not state_path.exists():
        return {"exists": False}
    return {"exists": True, "state": read_project_state(project_id)}


def active_project_id() -> str:
    if not ACTIVE_PROJECT.exists():
        return ""
    try:
        return str(json.loads(ACTIVE_PROJECT.read_text(encoding="utf-8-sig")).get("project_id") or "")
    except Exception:
        return ""


def list_projects() -> list[dict[str, Any]]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects = [
        item for item in (project_summary(path) for path in PROJECTS_DIR.iterdir())
        if item is not None
    ]
    projects.sort(key=lambda item: item.get("saved_at") or "", reverse=True)
    return projects


def activate_project(project_id: str) -> dict[str, Any]:
    safe_id = safe_project_id(project_id)
    state = read_project_state(safe_id)
    ACTIVE_PROJECT.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_PROJECT.write_text(json.dumps({"project_id": safe_id}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "project_id": safe_id, "state": state}


def delete_project(project_id: str) -> dict[str, Any]:
    safe_id = safe_project_id(project_id)
    target = _ensure_project_child(project_dir(safe_id))
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(safe_id)
    shutil.rmtree(target)
    if target.exists():
        raise RuntimeError("Project folder was not removed")
    if active_project_id() == safe_id and ACTIVE_PROJECT.exists():
        ACTIVE_PROJECT.unlink()
    return {
        "ok": True,
        "project_id": safe_id,
        "deleted": True,
        "active_project_id": active_project_id(),
        "projects": list_projects(),
    }


def save_project_state(state: dict[str, Any]) -> dict[str, Any]:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = write_project_files(state)
    return {
        "ok": True,
        "project_id": payload["project_id"],
        "project_url": payload["project_url"],
        "saved_at": payload["saved_at"],
        "state": payload,
    }
