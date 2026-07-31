from __future__ import annotations


import json
import time
from typing import Any

from app.images.jobs import DEFAULT_IMAGE_JOB_CONCURRENCY, cancel_image_job, create_image_job, get_image_job
from app.jobs.store import now_ms
from app.providers.image.adapter import generate_one_story_image
from app.providers.llm.adapter import (
    generate_story_from_copy,
    generate_text,
    generate_theme_ideas,
    generate_topic_plan,
    improve_image_prompt,
)
from app.media.render.service import create_render_job, get_render_job
from app.projects.service import project_dir, write_project_files

from ..constants import (
    AutoPipelineError,
    RENDER_STALL_SECONDS,
    _RENDER_STALL_MSG,
)
from ..image_repair import _repair_missing_images
from ..presets import (
    _copy_preset_theme_instruction,
    _copy_preset_theme_profile,
    _default_copy_prompt,
    _default_copy_to_story_prompt,
    _default_image_prompt,
    _default_improve_prompt,
    _job_copy_preset,
)
from ..state import (
    _check_cancelled,
    _image_config,
    _image_failure_message,
    _llm_config,
    _missing_image_indexes,
    _save,
    _secrets,
    _set_step,
    _shot_has_image,
    _state_or_default,
    _story_has_valid_shots,
    _with_runtime_keys,
    _write_state,
)

def _api():
    """Late-bind package attributes so tests can monkeypatch the package surface."""
    from app.workflow import auto_pipeline as api
    return api

