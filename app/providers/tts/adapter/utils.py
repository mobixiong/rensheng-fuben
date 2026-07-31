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

from .constants import MINIMAX_TTS_BASE_URL, TtsConfig

def _minimax_tts_url(config: TtsConfig) -> str:
    raw = (config.base_url or MINIMAX_TTS_BASE_URL).strip().rstrip("/")
    if not raw:
        raw = MINIMAX_TTS_BASE_URL
    if raw.endswith("/v1"):
        raw = f"{raw}/t2a_v2"
    elif "/v1/t2a_v2" not in raw:
        raw = f"{raw}/v1/t2a_v2"
    if "{group_id}" in raw:
        return raw.replace("{group_id}", urllib.parse.quote(config.group_id))
    if config.group_id:
        parsed = urllib.parse.urlsplit(raw)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not any(key.lower() == "groupid" for key, _ in query):
            query.append(("GroupId", config.group_id))
        raw = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))
    return raw

def _read_url_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="ignore")
    except Exception:
        return str(exc)

def _download_url_to_file(url: str, out_path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "life-copy-workbench/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        out_path.write_bytes(resp.read())

