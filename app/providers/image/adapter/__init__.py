"""Image provider adapter package."""
from __future__ import annotations

from .constants import (
    ANTHROPIC_IMAGE_UNSUPPORTED_MESSAGE,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_LLM_BASE_URL,
    GEMINI_IMAGE_DEFAULT_BASE_URL,
    GEMINI_IMAGE_DEFAULT_MODEL,
    IMAGE_PROMPT_PATH,
    IMAGE_QUOTA_SUGGESTION,
    ImageConfig,
    ImageError,
    MISSING_API_KEY_MESSAGE,
    PROMPT_POLICY_SUGGESTION,
)
from .errors import classify_image_http_error
from .prompting import build_shot_image_prompt, load_image_prompt
from .client import _openai_image_response, generate_image, test_image_connection
from .story import generate_one_story_image, generate_story_images

__all__ = [
    "ANTHROPIC_IMAGE_UNSUPPORTED_MESSAGE",
    "DEFAULT_IMAGE_MODEL",
    "DEFAULT_LLM_BASE_URL",
    "GEMINI_IMAGE_DEFAULT_BASE_URL",
    "GEMINI_IMAGE_DEFAULT_MODEL",
    "IMAGE_PROMPT_PATH",
    "IMAGE_QUOTA_SUGGESTION",
    "ImageConfig",
    "ImageError",
    "MISSING_API_KEY_MESSAGE",
    "PROMPT_POLICY_SUGGESTION",
    "_openai_image_response",
    "build_shot_image_prompt",
    "classify_image_http_error",
    "generate_image",
    "generate_one_story_image",
    "generate_story_images",
    "load_image_prompt",
    "test_image_connection",
]
