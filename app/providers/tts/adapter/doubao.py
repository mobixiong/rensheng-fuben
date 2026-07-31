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

from .constants import DOUBAO_TTS_BASE_URL, DOUBAO_TTS_RESOURCE_ID, TtsConfig
from .utils import _read_url_error

def _doubao_tts_url(config: TtsConfig) -> str:
    return (config.base_url or DOUBAO_TTS_BASE_URL).strip() or DOUBAO_TTS_BASE_URL

def _doubao_speech_rate(speed: float) -> int:
    return max(-50, min(100, int(round((speed - 1.0) * 100))))

def _doubao_loudness_rate(volume: float) -> int:
    return max(-50, min(100, int(round((volume - 1.0) * 100))))

def _doubao_additions(config: TtsConfig) -> str:
    additions: dict[str, Any] = {
        "disable_markdown_filter": True,
        "enable_language_detector": True,
        "enable_latex_tn": True,
        "disable_default_bit_rate": True,
        "max_length_to_filter_parenthesis": 0,
        "cache_config": {
            "text_type": 1,
            "use_cache": True,
        },
    }
    if config.pitch:
        additions["post_process"] = {"pitch": config.pitch}
    return json.dumps(additions, ensure_ascii=False, separators=(",", ":"))

def _iter_json_objects_from_stream(resp: Any) -> Any:
    decoder = json.JSONDecoder()
    buffer = ""
    while True:
        chunk = resp.read(8192)
        if not chunk:
            break
        buffer += chunk.decode("utf-8", errors="ignore")
        while True:
            stripped = buffer.lstrip()
            if not stripped:
                buffer = ""
                break
            if stripped.startswith("data:"):
                line, sep, rest = stripped.partition("\n")
                if not sep:
                    buffer = stripped
                    break
                payload = line[5:].strip()
                buffer = rest
                if payload and payload != "[DONE]":
                    yield json.loads(payload)
                continue
            try:
                value, index = decoder.raw_decode(stripped)
            except json.JSONDecodeError:
                buffer = stripped
                break
            yield value
            buffer = stripped[index:]
    if buffer.strip():
        stripped = buffer.strip()
        if stripped.startswith("data:"):
            stripped = stripped[5:].strip()
        if stripped and stripped != "[DONE]":
            yield json.loads(stripped)

def _doubao_tts(text: str, out_path: Path, config: TtsConfig) -> None:
    if not config.api_key:
        raise RenderError("Doubao TTS missing API key")
    if not config.voice_id:
        raise RenderError("Doubao TTS missing speaker")

    audio_params: dict[str, Any] = {
        "format": "mp3",
        "sample_rate": 24000,
        "bit_rate": 128000,
        "speech_rate": _doubao_speech_rate(config.speed),
        "loudness_rate": _doubao_loudness_rate(config.volume),
    }
    if config.emotion:
        audio_params["emotion"] = config.emotion

    payload: dict[str, Any] = {
        "user": {"uid": "rensheng-fuben"},
        "req_params": {
            "text": text,
            "speaker": config.voice_id,
            "additions": _doubao_additions(config),
            "audio_params": audio_params,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _doubao_tts_url(config),
        data=data,
        method="POST",
        headers={
            "X-Api-Key": config.api_key,
            "X-Api-Resource-Id": config.model or DOUBAO_TTS_RESOURCE_ID,
            "X-Api-Request-Id": uuid.uuid4().hex,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "life-copy-workbench/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, out_path.open("wb") as file:
            wrote_audio = False
            for item in _iter_json_objects_from_stream(resp):
                if not isinstance(item, dict):
                    continue
                code = int(item.get("code") or 0)
                if code not in {0, 20000000}:
                    message = item.get("message") or "unknown error"
                    raise RenderError(f"Doubao TTS failed: {code} {message}")
                audio = item.get("data")
                if isinstance(audio, str) and audio.strip():
                    try:
                        file.write(base64.b64decode(audio, validate=True))
                    except binascii.Error as exc:
                        raise RenderError("Doubao TTS audio is not valid base64") from exc
                    wrote_audio = True
            if not wrote_audio:
                raise RenderError("Doubao TTS returned empty audio")
    except urllib.error.HTTPError as exc:
        raise RenderError(f"Doubao TTS HTTP {exc.code}: {_read_url_error(exc)[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RenderError(f"Doubao TTS request failed: {exc}") from exc

    if not out_path.exists() or out_path.stat().st_size <= 0:
        raise RenderError("Doubao TTS returned an empty audio file")

