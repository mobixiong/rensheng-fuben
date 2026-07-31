from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.core.paths import ROOT

IMAGE_PROMPT_PATH = ROOT / "prompts" / "image_style.md"

DEFAULT_LLM_BASE_URL = "http://43.131.249.187:3000/v1"

DEFAULT_IMAGE_MODEL = "gpt-image-2"

GEMINI_IMAGE_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_IMAGE_DEFAULT_MODEL = "imagen-3.0-generate-002"
ANTHROPIC_IMAGE_UNSUPPORTED_MESSAGE = "Anthropic 不提供官方图片生成接口，请改用 OpenAI 或 Gemini"

MISSING_API_KEY_MESSAGE = "密钥未填写，密钥是群号"

class ImageError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "",
        category: str = "unknown",
        status_code: int | None = None,
        suggestion: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.category = category
        self.status_code = status_code
        self.suggestion = suggestion

    def to_detail(self) -> dict[str, Any]:
        detail = {
            "message": self.message,
            "category": self.category,
            "code": self.code,
        }
        if self.status_code:
            detail["status_code"] = self.status_code
        if self.suggestion:
            detail["suggestion"] = self.suggestion
        return detail

PROMPT_POLICY_SUGGESTION = "请修改该镜头的口播、画面描述或图片提示词，降低暴力、血腥、敏感等表达后重试。"

IMAGE_QUOTA_SUGGESTION = "图片接口额度不足或触发限流，请更换可用 Key、降低并发，或等待额度恢复后重试。"

@dataclass
class ImageConfig:
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "9:16"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ImageConfig":
        return cls(
            provider=(payload.get("provider") or os.getenv("IMAGE_PROVIDER") or "openai").strip(),
            base_url=(payload.get("base_url") or os.getenv("IMAGE_BASE_URL") or DEFAULT_LLM_BASE_URL).strip(),
            api_key=(payload.get("api_key") or os.getenv("IMAGE_API_KEY") or "").strip(),
            model=(payload.get("model") or os.getenv("IMAGE_MODEL") or DEFAULT_IMAGE_MODEL).strip(),
            size=(payload.get("size") or os.getenv("IMAGE_SIZE") or "9:16").strip(),
        )

