"""Generic stale/orphan detection for long-running job workers.

Long-running job workers (image batch generation, auto pipeline) live in
background threads. If a worker dies or the process restarts, the on-disk job
record stays in an active status forever. This module provides a shared
detection helper mirroring the model proven in image_jobs._mark_stale_if_orphaned
so every job kind can mark orphaned active jobs failed on read.

The caller supplies per-kind policy: which statuses count as active, the
terminal status to fall back to, the grace window, the live in-memory id set of
currently running workers, and a hook to mark any nested child records stale.
"""

from typing import Any, Callable

from .job_store import now_ms, save_job


def mark_orphaned_active_job(
    job: dict[str, Any],
    *,
    active_statuses: set[str],
    terminal_status: str,
    active_ids: set[str],
    grace_ms: int,
    error_message: str,
    error_category: str = "stalled",
    error_code: str = "worker_stopped",
    mark_children: Callable[[dict[str, Any]], None] | None = None,
    save: Callable[[dict[str, Any]], dict[str, Any]] = save_job,
    get_now_ms: Callable[[], int] = now_ms,
) -> dict[str, Any]:
    """Return the job, marking it terminal if it is an orphaned active job.

    A job is orphaned when its status is active but its worker id is no longer
    registered as live, and its updated_at has gaps exceeded grace_ms. Children
    (items/steps) are marked stale via mark_children before the job itself is
    finalised, so per-kind nested state stays consistent.
    """
    job_id = str(job.get("job_id") or "")
    if job.get("status") not in active_statuses or job_id in active_ids:
        return job
    updated_at = int(job.get("updated_at") or 0)
    if updated_at and get_now_ms() - updated_at < grace_ms:
        return job
    if mark_children is not None:
        mark_children(job)
    job["status"] = terminal_status
    job["stalled"] = True
    job["stalled_at"] = get_now_ms()
    job["error"] = error_message
    job["error_category"] = error_category
    job["error_code"] = error_code
    return save(job)
