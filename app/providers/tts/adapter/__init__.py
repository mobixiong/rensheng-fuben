"""TTS provider adapter package."""
from __future__ import annotations

from .constants import (
    DOUBAO_TTS_BASE_URL,
    DOUBAO_TTS_RESOURCE_ID,
    DOUBAO_TTS_SPEAKER,
    MINIMAX_TTS_BASE_URL,
    TTS_RETRY_COUNT,
    TtsConfig,
)
from .doubao import _doubao_tts, _iter_json_objects_from_stream
from .service import synthesize_tts

__all__ = [
    "DOUBAO_TTS_BASE_URL",
    "DOUBAO_TTS_RESOURCE_ID",
    "DOUBAO_TTS_SPEAKER",
    "MINIMAX_TTS_BASE_URL",
    "TTS_RETRY_COUNT",
    "TtsConfig",
    "_doubao_tts",
    "_iter_json_objects_from_stream",
    "synthesize_tts",
]
