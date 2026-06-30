import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import edge_tts

from .errors import RenderError


TTS_RETRY_COUNT = 3
MINIMAX_TTS_BASE_URL = "https://api.minimaxi.com/v1/t2a_v2"


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
        return cls(
            provider=provider if provider in {"edge", "minimax"} else "edge",
            voice=str(payload.get("voice") or "zh-CN-YunxiNeural").strip(),
            rate=str(payload.get("rate") or "+12%").strip(),
            base_url=str(payload.get("tts_base_url") or payload.get("base_url") or os.getenv("MINIMAX_TTS_BASE_URL") or "").strip(),
            api_key=str(payload.get("tts_api_key") or payload.get("api_key") or os.getenv("MINIMAX_TTS_API_KEY") or "").strip(),
            group_id=str(payload.get("tts_group_id") or payload.get("group_id") or os.getenv("MINIMAX_TTS_GROUP_ID") or "").strip(),
            model=str(payload.get("tts_model") or payload.get("model") or os.getenv("MINIMAX_TTS_MODEL") or "speech-2.8-hd").strip(),
            voice_id=str(payload.get("tts_voice_id") or payload.get("voice_id") or os.getenv("MINIMAX_TTS_VOICE_ID") or "male-qn-qingse").strip(),
            speed=_coerce_float(payload.get("tts_speed") or payload.get("speed"), 1.0, 0.5, 2.0),
            volume=_coerce_float(payload.get("tts_volume") or payload.get("volume"), 1.0, 0.1, 10.0),
            pitch=_coerce_int(payload.get("tts_pitch") or payload.get("pitch"), 0, -12, 12),
            emotion=str(payload.get("tts_emotion") or payload.get("emotion") or "").strip(),
            language_boost=str(payload.get("tts_language_boost") or payload.get("language_boost") or "Chinese").strip(),
        )


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


async def _edge_tts(text: str, out_path: Path, voice: str, rate: str) -> None:
    await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(out_path))


async def synthesize_tts(text: str, out_path: Path, config: TtsConfig) -> None:
    last_error: Exception | None = None
    for attempt in range(1, TTS_RETRY_COUNT + 1):
        try:
            if config.provider == "minimax":
                await asyncio.to_thread(_minimax_tts, text, out_path, config)
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
