import json
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.project_ids import project_dir, safe_project_id


def now_ms() -> int:
    return int(time.time() * 1000)


def utc_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def make_job_id(prefix: str) -> str:
    clean = "".join(ch for ch in str(prefix or "job") if ch.isalnum() or ch in {"_", "-"}).strip("_-") or "job"
    return f"{clean}_{utc_stamp()}_{uuid.uuid4().hex[:8]}"


def normalize_project_id(value: Any, topic: str = "") -> str:
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if raw.startswith("projects/"):
        raw = raw[len("projects/"):]
    return safe_project_id(raw, topic)


def jobs_dir(project_id: str) -> Path:
    path = project_dir(safe_project_id(project_id)) / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_path(project_id: str, job_id: str) -> Path:
    return jobs_dir(project_id) / f"{safe_project_id(job_id)}.json"


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_job(project_id: str, job_id: str) -> dict[str, Any]:
    path = job_path(project_id, job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    return json.loads(path.read_text(encoding="utf-8"))


def save_job(job: dict[str, Any]) -> dict[str, Any]:
    job["updated_at"] = now_ms()
    write_json_atomic(job_path(str(job["project_id"]), str(job["job_id"])), job)
    return job


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    public = json.loads(json.dumps(job, ensure_ascii=False))
    for key in ("api_key", "image_api_key", "tts_api_key", "fixed_prompt"):
        public.pop(key, None)
    for section in ("input", "text_config", "image_config", "tts_config"):
        value = public.get(section)
        if isinstance(value, dict):
            value.pop("api_key", None)
            value.pop("tts_api_key", None)
            value.pop("image_api_key", None)
    return public


def list_jobs(project_id: str, prefix: str = "", active_only: bool = False, active_statuses: set[str] | None = None) -> list[dict[str, Any]]:
    active_statuses = active_statuses or {"queued", "running", "waiting_child_job"}
    path = jobs_dir(project_id)
    jobs: list[dict[str, Any]] = []
    pattern = f"{prefix}*.json" if prefix else "*.json"
    for item in sorted(path.glob(pattern), key=lambda file: file.stat().st_mtime, reverse=True):
        try:
            job = json.loads(item.read_text(encoding="utf-8"))
        except Exception:
            continue
        if active_only and job.get("status") not in active_statuses:
            continue
        jobs.append(public_job(job))
    return jobs
