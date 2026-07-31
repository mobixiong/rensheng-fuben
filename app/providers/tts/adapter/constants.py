from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import edge_tts

from app.core.errors import RenderError
from app.providers.tts.doubao_voices import default_doubao_voice_for_resource

TTS_RETRY_COUNT = 3

MINIMAX_TTS_BASE_URL = "https://api.minimaxi.com/v1/t2a_v2"

DOUBAO_TTS_BASE_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

DOUBAO_TTS_RESOURCE_ID = "volc.service_type.10029"

DOUBAO_TTS_SPEAKER = "zh_male_beijingxiaoye_emo_v2_mars_bigtts"

def _coerce_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))

def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))

@dataclass
class TtsConfig:
    provider: str = "edge"
    voice: str = "zh-CN-YunxiNeural"
    rate: str = "+12%"
    base_url: str = ""
    api_key: str = ""
    group_id: str = ""
    model: str = "speech-2.8-hd"
    voice_id: str = "male-qn-qingse"
    speed: float = 1.0
    volume: float = 1.0
    pitch: int = 0
    emotion: str = ""
    language_boost: str = "Chinese"

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None = None) -> "TtsConfig":
        payload = payload or {}
        provider = str(payload.get("tts_provider") or payload.get("provider") or os.getenv("TTS_PROVIDER") or "edge").strip().lower()
        if provider == "volcengine":
            provider = "doubao"
        if provider not in {"edge", "minimax", "doubao"}:
            provider = "edge"
        if provider == "doubao":
            base_url = str(payload.get("tts_base_url") or payload.get("base_url") or os.getenv("DOUBAO_TTS_BASE_URL") or "").strip()
            api_key = str(payload.get("tts_api_key") or payload.get("api_key") or os.getenv("DOUBAO_TTS_API_KEY") or "").strip()
            model = str(payload.get("tts_model") or payload.get("model") or "").strip()
            if not model or model == "speech-2.8-hd":
                model = str(os.getenv("DOUBAO_TTS_RESOURCE_ID") or DOUBAO_TTS_RESOURCE_ID).strip()
            voice_id = str(payload.get("tts_voice_id") or payload.get("voice_id") or "").strip()
            if not voice_id or voice_id == "male-qn-qingse":
                env_speaker = str(os.getenv("DOUBAO_TTS_SPEAKER") or "").strip()
                env_resource_id = str(os.getenv("DOUBAO_TTS_RESOURCE_ID") or DOUBAO_TTS_RESOURCE_ID).strip()
                if env_speaker and model == env_resource_id:
                    voice_id = env_speaker
                else:
                    voice_id = default_doubao_voice_for_resource(model)
        else:
            base_url = str(payload.get("tts_base_url") or payload.get("base_url") or os.getenv("MINIMAX_TTS_BASE_URL") or "").strip()
            api_key = str(payload.get("tts_api_key") or payload.get("api_key") or os.getenv("MINIMAX_TTS_API_KEY") or "").strip()
            model = str(payload.get("tts_model") or payload.get("model") or os.getenv("MINIMAX_TTS_MODEL") or "speech-2.8-hd").strip()
            voice_id = str(payload.get("tts_voice_id") or payload.get("voice_id") or os.getenv("MINIMAX_TTS_VOICE_ID") or "male-qn-qingse").strip()
        return cls(
            provider=provider,
            voice=str(payload.get("voice") or "zh-CN-YunxiNeural").strip(),
            rate=str(payload.get("rate") or "+12%").strip(),
            base_url=base_url,
            api_key=api_key,
            group_id=str(payload.get("tts_group_id") or payload.get("group_id") or os.getenv("MINIMAX_TTS_GROUP_ID") or "").strip(),
            model=model,
            voice_id=voice_id,
            speed=_coerce_float(payload.get("tts_speed") or payload.get("speed"), 1.0, 0.5, 2.0),
            volume=_coerce_float(payload.get("tts_volume") or payload.get("volume"), 1.0, 0.1, 10.0),
            pitch=_coerce_int(payload.get("tts_pitch") or payload.get("pitch"), 0, -12, 12),
            emotion=str(payload.get("tts_emotion") or payload.get("emotion") or "").strip(),
            language_boost=str(payload.get("tts_language_boost") or payload.get("language_boost") or "Chinese").strip(),
        )

