from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from app.media.render.ffmpeg_utils import safe_unlink
from app.providers.tts.adapter import TtsConfig

from .media_ops import _file_hash, _sha256_json

def _render_fingerprint(
    clean: dict[str, Any],
    image_size: str,
    canvas_size: tuple[int, int],
    intro_template: str,
    intro_image_seconds: float,
    bgm_id: str | None,
    intro_sfx_id: str | None,
    tts: TtsConfig,
) -> str:
    tts_payload = asdict(tts)
    tts_payload["api_key"] = "***" if tts_payload.get("api_key") else ""
    return _sha256_json({
        "story": clean,
        "image_size": image_size,
        "canvas_size": canvas_size,
        "intro_template": intro_template,
        "intro_image_seconds": intro_image_seconds,
        "bgm_id": bgm_id or "none",
        "intro_sfx_id": intro_sfx_id or "default",
        "tts": tts_payload,
        "pipeline": 2,
    })

def _read_resume_manifest(path: Path, fingerprint: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if data.get("fingerprint") != fingerprint:
        return {
            "previous_fingerprint": data.get("fingerprint"),
            "stages": data.get("stages") if isinstance(data.get("stages"), dict) else {},
        }
    return data

def _write_resume_manifest(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _tts_signature(text: str, tts: TtsConfig) -> str:
    payload = asdict(tts)
    payload["api_key"] = "***" if payload.get("api_key") else ""
    return _sha256_json({"text": text, "tts": payload})

def _asset_signature(path: Path | None) -> dict[str, str]:
    if not path:
        return {"path": "", "sha256": ""}
    return {
        "path": str(path.resolve()),
        "sha256": _file_hash(path) if path.exists() else "",
    }

def _stage_done(
    manifest: dict[str, Any],
    stage: str,
    key: str,
    signature: str,
    path: Path,
    validator: Callable[[Path], bool],
) -> bool:
    entry = ((manifest.get("stages") or {}).get(stage) or {}).get(key) or {}
    if entry.get("signature") == signature and validator(path):
        return True
    safe_unlink(path)
    return False

def _mark_stage(
    manifest_path: Path,
    manifest: dict[str, Any],
    stage: str,
    key: str,
    signature: str,
    path: Path,
    **extra: Any,
) -> None:
    stages = manifest.setdefault("stages", {})
    bucket = stages.setdefault(stage, {})
    bucket[key] = {
        "signature": signature,
        "path": str(path.resolve()),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **extra,
    }
    _write_resume_manifest(manifest_path, manifest)

