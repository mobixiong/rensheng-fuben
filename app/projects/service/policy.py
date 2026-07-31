from __future__ import annotations

import re
from typing import Any

from app.core.image_status import (
    IMAGE_STATUS_ERROR,
    IMAGE_STATUS_PENDING,
    IMAGE_STATUS_POLICY_ERROR,
    has_shot_image,
)

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


def _has_prompt_policy_error(value: Any) -> bool:
    text = str(value or "")
    lowered = text.lower()
    return any(marker in lowered or marker in text for marker in PROMPT_POLICY_ERROR_MARKERS)


def _image_failure_count(value: Any) -> int | None:
    match = re.search("失败\\s*(\\d+)\\s*张", str(value or ""))
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

