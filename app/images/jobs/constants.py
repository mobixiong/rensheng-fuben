from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app.core.image_status import IMAGE_JOB_QUEUED, IMAGE_JOB_RETRYING, IMAGE_JOB_RUNNING

ACTIVE_JOB_STATUSES = {IMAGE_JOB_QUEUED, IMAGE_JOB_RUNNING, IMAGE_JOB_RETRYING}

IMAGE_JOB_KIND = "image"

IMAGE_JOB_FILE_PREFIX = "img_"

DEFAULT_IMAGE_JOB_CONCURRENCY = 100

MAX_IMAGE_JOB_CONCURRENCY = 100

IMAGE_JOB_RETRY_LIMIT = 2

STALE_ACTIVE_JOB_GRACE_MS = 60_000

_runner = ThreadPoolExecutor(max_workers=4)

_lock = threading.RLock()

_cancelled: set[str] = set()

_active_job_ids: set[str] = set()

