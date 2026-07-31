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

from .constants import TtsConfig
from .utils import _download_url_to_file, _minimax_tts_url, _read_url_error

def _minimax_tts(text: str, out_path: Path, config: TtsConfig) -> None:
    if not config.api_key:
        raise RenderError("MiniMax TTS missing API key")
    if not config.voice_id:
        raise RenderError("MiniMax TTS missing voice_id")

    voice_setting: dict[str, Any] = {
        "voice_id": config.voice_id,
        "speed": config.speed,
        "vol": config.volume,
        "pitch": config.pitch,
    }
    if config.emotion:
        voice_setting["emotion"] = config.emotion

    payload: dict[str, Any] = {
        "model": config.model or "speech-2.8-hd",
        "text": text,
        "stream": False,
        "output_format": "hex",
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "subtitle_enable": False,
        "aigc_watermark": False,
    }
    if config.language_boost:
        payload["language_boost"] = config.language_boost

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _minimax_tts_url(config),
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "life-copy-workbench/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        raise RenderError(f"MiniMax TTS HTTP {exc.code}: {_read_url_error(exc)[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RenderError(f"MiniMax TTS request failed: {exc}") from exc

    try:
        response = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RenderError(f"MiniMax TTS returned non-JSON response: {body[:1000]}") from exc

    base_resp = response.get("base_resp") or {}
    status_code = int(base_resp.get("status_code") or 0)
    if status_code != 0:
        trace_id = response.get("trace_id") or ""
        status_msg = base_resp.get("status_msg") or "unknown error"
        suffix = f" trace_id={trace_id}" if trace_id else ""
        raise RenderError(f"MiniMax TTS failed: {status_code} {status_msg}{suffix}")

    audio = (response.get("data") or {}).get("audio")
    if not isinstance(audio, str) or not audio.strip():
        trace_id = response.get("trace_id") or ""
        raise RenderError(f"MiniMax TTS returned empty audio" + (f" trace_id={trace_id}" if trace_id else ""))

    audio = audio.strip()
    if audio.startswith("http://") or audio.startswith("https://"):
        _download_url_to_file(audio, out_path)
    else:
        try:
            out_path.write_bytes(bytes.fromhex(audio))
        except ValueError as exc:
            raise RenderError("MiniMax TTS audio is not valid hex") from exc

    if not out_path.exists() or out_path.stat().st_size <= 0:
        raise RenderError("MiniMax TTS returned an empty audio file")

