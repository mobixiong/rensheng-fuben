from __future__ import annotations

from typing import Any

from app.images.jobs import DEFAULT_IMAGE_JOB_CONCURRENCY
from app.providers.image.adapter import ImageConfig
from app.providers.llm.adapter import LLMConfig

from .job_ops import _with_runtime_keys


def _llm_config(job: dict[str, Any], temperature: float = 0.8) -> LLMConfig:
    data = _with_runtime_keys(job, "text_config")
    data.setdefault("temperature", temperature)
    return LLMConfig.from_payload(data)


def _image_config(job: dict[str, Any]) -> ImageConfig:
    data = _with_runtime_keys(job, "image_config")
    data["size"] = (job.get("input") or {}).get("image_size") or data.get("size") or "9:16"
    return ImageConfig.from_payload(data)


def _image_repair_concurrency(job: dict[str, Any]) -> int:
    raw = (job.get("input") or {}).get("image_concurrency") or DEFAULT_IMAGE_JOB_CONCURRENCY
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_IMAGE_JOB_CONCURRENCY
    return max(1, min(value, DEFAULT_IMAGE_JOB_CONCURRENCY))
