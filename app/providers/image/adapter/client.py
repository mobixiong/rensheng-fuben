from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from app.core.project_ids import public_project_id, workspace_project_id, workspace_project_ref

from .constants import (
    ANTHROPIC_IMAGE_UNSUPPORTED_MESSAGE,
    GEMINI_IMAGE_DEFAULT_BASE_URL,
    GEMINI_IMAGE_DEFAULT_MODEL,
    ImageConfig,
    ImageError,
    MISSING_API_KEY_MESSAGE,
)
from .errors import classify_image_http_error


def _workspace_project_id(value: Any) -> str:
    return workspace_project_id(value, strict=False)


def _workspace_project_ref(project_id: str) -> str:
    return workspace_project_ref(project_id)


def _public_project_id(project_ref: str) -> str:
    return public_project_id(project_ref)


def _endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1/images/generations") or clean.endswith("/images/generations"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/images/generations"
    return f"{clean}/v1/images/generations"


def _gemini_image_endpoint(base_url: str, model: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith(":predict") or clean.endswith(":generateImages"):
        return clean
    if "/models/" in clean:
        return clean if clean.endswith(":predict") else f"{clean}:predict"
    if clean.endswith("/v1beta") or clean.endswith("/v1"):
        return f"{clean}/models/{model}:predict"
    return f"{clean}/v1beta/models/{model}:predict"


def _gemini_aspect_ratio(size: str) -> str:
    value = (size or "9:16").strip()
    mapping = {
        "9:16": "9:16",
        "16:9": "16:9",
        "1:1": "1:1",
        "1024x1792": "9:16",
        "1792x1024": "16:9",
        "1024x1024": "1:1",
    }
    return mapping.get(value, "9:16")


def _download(url: str, out_path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "RenshengFuben/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        out_path.write_bytes(resp.read())


def _openai_image_response(prompt: str, cfg: ImageConfig, timeout: int = 180) -> dict[str, Any]:
    if not cfg.api_key:
        raise ImageError(
            MISSING_API_KEY_MESSAGE,
            code="missing_api_key",
            category="auth",
        )
    if not cfg.base_url or not cfg.model:
        raise ImageError("Image base_url/model is required", code="missing_config", category="config")
    body = {
        "model": cfg.model,
        "prompt": prompt,
        "size": cfg.size,
        "n": 1,
    }
    req = urllib.request.Request(
        _endpoint(cfg.base_url),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:1000]
        raise classify_image_http_error(exc.code, detail) from exc
    except Exception as exc:
        raise ImageError(f"Image request failed: {exc}", category="network") from exc


def _openai_image(prompt: str, cfg: ImageConfig, out_path: Path) -> None:
    data = _openai_image_response(prompt, cfg)
    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        out_path.write_bytes(base64.b64decode(item["b64_json"]))
        return
    if item.get("url"):
        _download(item["url"], out_path)
        return
    raise ImageError(f"Unexpected image response: {str(data)[:1000]}")


def _gemini_image_response(prompt: str, cfg: ImageConfig, timeout: int = 180) -> dict[str, Any]:
    if not cfg.api_key:
        raise ImageError(
            MISSING_API_KEY_MESSAGE,
            code="missing_api_key",
            category="auth",
        )
    base_url = cfg.base_url or GEMINI_IMAGE_DEFAULT_BASE_URL
    model = cfg.model or GEMINI_IMAGE_DEFAULT_MODEL
    if not base_url or not model:
        raise ImageError("Image base_url/model is required", code="missing_config", category="config")

    endpoint = _gemini_image_endpoint(base_url, model)
    if "key=" not in endpoint:
        sep = "&" if "?" in endpoint else "?"
        endpoint = f"{endpoint}{sep}{urlencode({'key': cfg.api_key})}"

    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": _gemini_aspect_ratio(cfg.size),
        },
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:1000]
        raise classify_image_http_error(exc.code, detail) from exc
    except Exception as exc:
        raise ImageError(f"Image request failed: {exc}", category="network") from exc


def _gemini_image(prompt: str, cfg: ImageConfig, out_path: Path) -> None:
    data = _gemini_image_response(prompt, cfg)
    predictions = data.get("predictions") or data.get("generatedImages") or []
    if not predictions:
        # Some gateways wrap under data
        predictions = data.get("data") or []
    item = predictions[0] if predictions else {}
    if not isinstance(item, dict):
        raise ImageError(f"Unexpected Gemini image response: {str(data)[:1000]}")

    b64 = (
        item.get("bytesBase64Encoded")
        or item.get("b64_json")
        or item.get("image")
        or ((item.get("image") or {}) if isinstance(item.get("image"), dict) else {}).get("imageBytes")
    )
    if isinstance(b64, dict):
        b64 = b64.get("bytesBase64Encoded") or b64.get("b64_json")
    if b64:
        out_path.write_bytes(base64.b64decode(b64))
        return
    url = item.get("url") or item.get("imageUrl")
    if url:
        _download(url, out_path)
        return
    raise ImageError(f"Unexpected Gemini image response: {str(data)[:1000]}")


def generate_image(prompt: str, cfg: ImageConfig, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    provider = (cfg.provider or "openai").lower()
    if provider in {"openai", "openai_compatible", "compatible"}:
        _openai_image(prompt, cfg, out_path)
        return
    if provider in {"gemini", "google", "google_gemini", "imagen"}:
        _gemini_image(
            prompt,
            ImageConfig(
                provider=cfg.provider,
                base_url=cfg.base_url or GEMINI_IMAGE_DEFAULT_BASE_URL,
                api_key=cfg.api_key,
                model=cfg.model or GEMINI_IMAGE_DEFAULT_MODEL,
                size=cfg.size,
            ),
            out_path,
        )
        return
    if provider in {"anthropic", "claude"}:
        raise ImageError(
            ANTHROPIC_IMAGE_UNSUPPORTED_MESSAGE,
            code="unsupported_provider",
            category="config",
        )
    raise ImageError(f"Unsupported image provider: {cfg.provider}")


def test_image_connection(cfg: ImageConfig) -> dict[str, Any]:
    provider = (cfg.provider or "openai").lower()
    prompt = "??????????????????????Logo????"
    if provider in {"openai", "openai_compatible", "compatible"}:
        data = _openai_image_response(prompt, cfg, timeout=90)
        item = (data.get("data") or [{}])[0]
        if not (item.get("b64_json") or item.get("url")):
            raise ImageError(f"Unexpected image response: {str(data)[:1000]}")
        return {
            "ok": True,
            "provider": cfg.provider,
            "model": cfg.model,
            "returned": "b64_json" if item.get("b64_json") else "url",
        }
    if provider in {"gemini", "google", "google_gemini", "imagen"}:
        test_cfg = ImageConfig(
            provider=cfg.provider,
            base_url=cfg.base_url or GEMINI_IMAGE_DEFAULT_BASE_URL,
            api_key=cfg.api_key,
            model=cfg.model or GEMINI_IMAGE_DEFAULT_MODEL,
            size=cfg.size,
        )
        data = _gemini_image_response(prompt, test_cfg, timeout=90)
        predictions = data.get("predictions") or data.get("generatedImages") or data.get("data") or []
        item = predictions[0] if predictions else {}
        has_b64 = isinstance(item, dict) and bool(
            item.get("bytesBase64Encoded") or item.get("b64_json") or item.get("image")
        )
        has_url = isinstance(item, dict) and bool(item.get("url") or item.get("imageUrl"))
        if not (has_b64 or has_url):
            raise ImageError(f"Unexpected Gemini image response: {str(data)[:1000]}")
        return {
            "ok": True,
            "provider": cfg.provider,
            "model": test_cfg.model,
            "returned": "b64_json" if has_b64 else "url",
        }
    if provider in {"anthropic", "claude"}:
        raise ImageError(
            ANTHROPIC_IMAGE_UNSUPPORTED_MESSAGE,
            code="unsupported_provider",
            category="config",
        )
    raise ImageError(f"Unsupported image provider: {cfg.provider}")
