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

from .constants import TTS_RETRY_COUNT, TtsConfig
from .doubao import _doubao_tts
from .minimax import _minimax_tts

async def _edge_tts(text: str, out_path: Path, voice: str, rate: str) -> None:
    await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(out_path))

async def synthesize_tts(text: str, out_path: Path, config: TtsConfig) -> None:
    last_error: Exception | None = None
    for attempt in range(1, TTS_RETRY_COUNT + 1):
        try:
            if config.provider == "minimax":
                await asyncio.to_thread(_minimax_tts, text, out_path, config)
            elif config.provider == "doubao":
                await asyncio.to_thread(_doubao_tts, text, out_path, config)
            else:
                await _edge_tts(text, out_path, config.voice, config.rate)
            if out_path.exists() and out_path.stat().st_size > 0:
                return
            last_error = RenderError("TTS returned an empty audio file")
        except Exception as exc:
            last_error = exc
        if attempt < TTS_RETRY_COUNT:
            await asyncio.sleep(attempt)
    raise RenderError(f"TTS failed after {TTS_RETRY_COUNT} attempts: {last_error}") from last_error

