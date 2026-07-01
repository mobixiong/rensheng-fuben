import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import ACTIVE_PROJECT, LEGACY_PROJECT_STATE, PROJECTS_DIR, WORKSPACE

TRANSIENT_IMAGE_STATUSES = {"generating", "retrying", "redrawing"}
TRANSIENT_IMAGE_STATUS_TTL_SECONDS = 20 * 60
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


def _slug(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:42] or "未命名项目"


def safe_project_id(value: Any, topic: str = "") -> str:
    raw = str(value or "").strip()
    if raw and not re.search(r'[<>:"/\\|?*\x00-\x1f]', raw) and ".." not in raw:
        return raw[:120]
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{_slug(topic)}_{uuid.uuid4().hex[:6]}"


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


def _clear_image_runtime_fields(shot: dict[str, Any]) -> None:
    shot.pop("_image_job", None)
    shot.pop("_image_attempt", None)
    shot.pop("_image_status_started_at", None)
    shot.pop("_image_status_updated_at", None)


def _image_job_status(shot: dict[str, Any]) -> str:
    job = shot.get("_image_job")
    if isinstance(job, dict) and job.get("status") in TRANSIENT_IMAGE_STATUSES:
        return str(job.get("status"))
    if shot.get("_image_status") in TRANSIENT_IMAGE_STATUSES:
        return str(shot.get("_image_status"))
    return ""


def _status_started_at_seconds(shot: dict[str, Any]) -> float:
    job = shot.get("_image_job") if isinstance(shot.get("_image_job"), dict) else {}
    raw = job.get("started_at") or job.get("updated_at") or shot.get("_image_status_started_at") or shot.get("_image_status_updated_at") or 0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return value / 1000 if value > 10_000_000_000 else value


def _transient_status_is_fresh(shot: dict[str, Any]) -> bool:
    if not _image_job_status(shot):
        return False
    started_at = _status_started_at_seconds(shot)
    return bool(started_at and time.time() - started_at <= TRANSIENT_IMAGE_STATUS_TTL_SECONDS)


def _migrate_image_job(shot: dict[str, Any], has_image: bool = False) -> None:
    status = _image_job_status(shot)
    if not status:
        return
    job = shot.get("_image_job")
    if not isinstance(job, dict):
        now = time.time()
        started_at = _status_started_at_seconds(shot) or now
        shot["_image_job"] = {
            "status": status,
            "attempt": shot.get("_image_attempt") or 1,
            "started_at": int(started_at * 1000),
            "updated_at": int(now * 1000),
        }
    shot["_image_status"] = "done" if has_image else "pending"
    shot.pop("_image_attempt", None)
    shot.pop("_image_status_started_at", None)
    shot.pop("_image_status_updated_at", None)


def _image_is_newer_than_status(image_path: Path, shot: dict[str, Any]) -> bool:
    started_at = _status_started_at_seconds(shot)
    if not started_at:
        return True
    try:
        return image_path.stat().st_mtime >= started_at
    except OSError:
        return True


def _mark_shot_image_done(shot: dict[str, Any], project_id: str, image_path: Path) -> None:
    shot["image_path"] = str(image_path.resolve())
    shot["image_url"] = f"/workspace/projects/{project_id}/images/{image_path.name}"
    if (
        _image_job_status(shot)
        and _transient_status_is_fresh(shot)
        and not _image_is_newer_than_status(image_path, shot)
    ):
        _migrate_image_job(shot, has_image=True)
        shot.pop("_image_error", None)
        shot.pop("_image_error_category", None)
        shot.pop("_image_error_code", None)
        return
    shot["_image_status"] = "done"
    _clear_image_runtime_fields(shot)
    shot.pop("_image_error", None)
    shot.pop("_image_error_category", None)
    shot.pop("_image_error_code", None)


def _mark_cover_image_done(cover: dict[str, Any], project_id: str, image_path: Path) -> None:
    cover["image_path"] = str(image_path.resolve())
    cover["image_url"] = f"/workspace/projects/{project_id}/cover/{image_path.name}"
    cover["_cover_status"] = "done"
    cover.pop("_cover_error", None)


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
        if shot.get("image_path") or shot.get("image_url"):
            continue
        if shot.get("_image_error"):
            continue
        if shot.get("_image_status") not in {None, "", "pending", "error", "policy_error"}:
            continue
        candidates.append(shot)

    failed_count = _image_failure_count(result_text)
    if failed_count is not None and failed_count != len(candidates):
        return

    for shot in candidates:
        shot["_image_status"] = "policy_error"
        shot["_image_error"] = PROMPT_POLICY_ERROR_MESSAGE
        shot["_image_error_category"] = "prompt_policy"
        shot["_image_error_code"] = "content_policy_violation"


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
        if existing_shot.get("_image_status") != "policy_error":
            continue
        if shot.get("image_path") or shot.get("image_url"):
            continue
        if shot.get("_image_status") not in {None, "", "pending", "error", "policy_error"}:
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
        elif _image_job_status(shot):
            if shot.get("_image_error"):
                shot["_image_status"] = "error"
                _clear_image_runtime_fields(shot)
                continue
            if _transient_status_is_fresh(shot):
                _migrate_image_job(shot, has_image=False)
                continue
            shot["_image_status"] = "pending"
            _clear_image_runtime_fields(shot)
            shot.pop("_image_error", None)
            shot.pop("_image_error_category", None)
            shot.pop("_image_error_code", None)
    _mark_prompt_policy_errors(state)


def _copy_project_cover(state: dict[str, Any], target_project_dir: Path) -> None:
    story = state.get("story")
    if not isinstance(story, dict):
        return
    cover = story.get("cover")
    if not isinstance(cover, dict):
        return

    cover_dir = target_project_dir / "cover"
    cover_dir.mkdir(parents=True, exist_ok=True)
    source = None
    raw_path = str(cover.get("image_path") or "").strip()
    if raw_path:
        source = Path(raw_path)
    if (not source or not source.exists()) and cover.get("image_url"):
        source = _workspace_path_from_url(str(cover.get("image_url")))
    if source and source.exists():
        target = cover_dir / f"cover{source.suffix or '.png'}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        _mark_cover_image_done(cover, state["project_id"], target)
    else:
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            target = cover_dir / f"cover{suffix}"
            if target.exists():
                _mark_cover_image_done(cover, state["project_id"], target)
                break

    raw_source = None
    raw_cover_path = str(cover.get("raw_image_path") or "").strip()
    if raw_cover_path:
        raw_source = Path(raw_cover_path)
    if (not raw_source or not raw_source.exists()) and cover.get("raw_image_url"):
        raw_source = _workspace_path_from_url(str(cover.get("raw_image_url")))
    if raw_source and raw_source.exists():
        raw_target = cover_dir / f"cover_raw{raw_source.suffix or '.png'}"
        if raw_source.resolve() != raw_target.resolve():
            shutil.copy2(raw_source, raw_target)
        cover["raw_image_path"] = str(raw_target.resolve())
        cover["raw_image_url"] = f"/workspace/projects/{state['project_id']}/cover/{raw_target.name}"


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
        elif _image_job_status(shot):
            if shot.get("_image_error"):
                shot["_image_status"] = "error"
                _clear_image_runtime_fields(shot)
                continue
            if _transient_status_is_fresh(shot):
                _migrate_image_job(shot, has_image=False)
                continue
            shot["_image_status"] = "pending"
            _clear_image_runtime_fields(shot)
            shot.pop("_image_error", None)
            shot.pop("_image_error_category", None)
            shot.pop("_image_error_code", None)
    _mark_prompt_policy_errors(state)
    cover = story.get("cover")
    if isinstance(cover, dict):
        cover_dir = project_dir(project_id) / "cover"
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            cover_path = cover_dir / f"cover{suffix}"
            if cover_path.exists():
                _mark_cover_image_done(cover, project_id, cover_path)
                break
    return state


def write_project_files(state: dict[str, Any]) -> dict[str, Any]:
    project_id = safe_project_id(state.get("project_id"), str(state.get("topic") or ""))
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
    _copy_project_cover(payload, target_project_dir)
    story = payload.get("story")

    (target_project_dir / "state.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (target_project_dir / "copy.txt").write_text(str(payload.get("copy_text") or ""), encoding="utf-8")
    (target_project_dir / "result.txt").write_text(str(payload.get("result_text") or ""), encoding="utf-8")
    (prompts_dir / "copy_prompt.txt").write_text(str(payload.get("copy_prompt") or ""), encoding="utf-8")
    (prompts_dir / "copy_to_story_prompt.txt").write_text(str(payload.get("copy_to_story_prompt") or ""), encoding="utf-8")
    (prompts_dir / "image_prompt.txt").write_text(str(payload.get("image_prompt") or ""), encoding="utf-8")
    (prompts_dir / "improve_image_prompt.txt").write_text(str(payload.get("improve_image_prompt") or ""), encoding="utf-8")
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
