"""Shared job status literals.

Centralizing these constants removes magic strings scattered across render_service,
image_jobs, auto_pipeline_jobs and job_health. Values are kept identical to the
existing written form (render keeps complete/error, image keeps done/failed/
cancelled, auto keeps complete/failed/cancelled/waiting_child_job) so on-disk
records and the frontend contract stay back-compatible.
"""

from typing import Any

# Render job statuses
RENDER_JOB_QUEUED = "queued"
RENDER_JOB_RUNNING = "running"
RENDER_JOB_COMPLETE = "complete"
RENDER_JOB_ERROR = "error"

RENDER_ACTIVE_STATUSES = {RENDER_JOB_QUEUED, RENDER_JOB_RUNNING}
RENDER_TERMINAL_STATUSES = {RENDER_JOB_COMPLETE, RENDER_JOB_ERROR}


def render_is_terminal(status: Any) -> bool:
    return str(status or "") in RENDER_TERMINAL_STATUSES
