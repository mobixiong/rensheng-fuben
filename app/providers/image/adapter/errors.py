from __future__ import annotations

import json
import urllib.error
import urllib.request

from .constants import IMAGE_QUOTA_SUGGESTION, ImageError, PROMPT_POLICY_SUGGESTION

def _extract_provider_error(raw: str) -> tuple[str, str, str]:
    message = raw.strip()
    code = ""
    error_type = ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return message, code, error_type
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or message)
            code = str(error.get("code") or "")
            error_type = str(error.get("type") or "")
        else:
            message = str(data.get("message") or data.get("detail") or message)
            code = str(data.get("code") or "")
            error_type = str(data.get("type") or "")
    return message.strip(), code.strip(), error_type.strip()

def _is_prompt_policy_error(message: str, code: str = "", error_type: str = "") -> bool:
    text = " ".join([message or "", code or "", error_type or ""]).lower()
    english_markers = (
        "content_policy_violation",
        "policy_violation",
        "content policy",
        "safety policy",
        "safety system",
        "moderation",
        "blocked",
        "unsafe",
        "sensitive",
    )
    chinese_markers = ("违反", "不合规", "防护限制", "内容安全", "安全策略", "敏感", "违规", "审核")
    return any(marker in text for marker in english_markers) or any(marker in message for marker in chinese_markers)

def classify_image_http_error(status_code: int, raw_detail: str) -> ImageError:
    message, code, error_type = _extract_provider_error(raw_detail)
    quota_text = " ".join([message or "", code or "", error_type or ""]).lower()
    if status_code == 429 or "quota" in quota_text or "rate limit" in quota_text or "too many requests" in quota_text:
        return ImageError(
            f"图片接口额度不足或限流：{message or raw_detail}",
            code=code or f"http_{status_code}",
            category="quota",
            status_code=status_code,
            suggestion=IMAGE_QUOTA_SUGGESTION,
        )
    if _is_prompt_policy_error(message, code, error_type):
        return ImageError(
            f"提示词被内容安全策略拦截：{message}",
            code=code or f"http_{status_code}",
            category="prompt_policy",
            status_code=status_code,
            suggestion=PROMPT_POLICY_SUGGESTION,
        )
    return ImageError(
        f"Image HTTP {status_code}: {message or raw_detail}",
        code=code or f"http_{status_code}",
        category="request",
        status_code=status_code,
    )

