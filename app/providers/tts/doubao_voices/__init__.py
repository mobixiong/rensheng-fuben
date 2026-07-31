"""Doubao TTS voice catalog package."""
from __future__ import annotations

from .catalog import default_doubao_voice_for_resource, get_doubao_voice_catalog
from .constants import (
    DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID,
    DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
    DOUBAO_TTS_1_0_RESOURCE_ID,
    DOUBAO_TTS_2_0_DEFAULT_VOICE_ID,
    DOUBAO_TTS_2_0_RESOURCE_ID,
    DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID,
    DOUBAO_TTS_RESOURCE_MODELS,
    DOUBAO_TTS_VOICE_DOC_API,
    DOUBAO_TTS_VOICE_DOC_URL,
)
from .parser import parse_doubao_voice_groups

__all__ = [
    "DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID",
    "DOUBAO_TTS_1_0_DEFAULT_VOICE_ID",
    "DOUBAO_TTS_1_0_RESOURCE_ID",
    "DOUBAO_TTS_2_0_DEFAULT_VOICE_ID",
    "DOUBAO_TTS_2_0_RESOURCE_ID",
    "DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID",
    "DOUBAO_TTS_RESOURCE_MODELS",
    "DOUBAO_TTS_VOICE_DOC_API",
    "DOUBAO_TTS_VOICE_DOC_URL",
    "default_doubao_voice_for_resource",
    "get_doubao_voice_catalog",
    "parse_doubao_voice_groups",
]
