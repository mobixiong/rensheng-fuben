from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any
from urllib.parse import urlencode

from .constants import (
    ANTHROPIC_DEFAULT_BASE_URL,
    ANTHROPIC_DEFAULT_MODEL,
    GEMINI_DEFAULT_BASE_URL,
    GEMINI_DEFAULT_MODEL,
    LLMConfig,
    LLMError,
    MISSING_API_KEY_MESSAGE,
)


def _endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1/chat/completions") or clean.endswith("/chat/completions"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/chat/completions"
    return f"{clean}/v1/chat/completions"


def _anthropic_endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1/messages") or clean.endswith("/messages"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/messages"
    return f"{clean}/v1/messages"


def _gemini_endpoint(base_url: str, model: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith(":generateContent"):
        return clean
    if "/models/" in clean:
        return clean if clean.endswith(":generateContent") else f"{clean}:generateContent"
    if clean.endswith("/v1beta") or clean.endswith("/v1"):
        return f"{clean}/models/{model}:generateContent"
    return f"{clean}/v1beta/models/{model}:generateContent"


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def _http_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int = 120) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:1000]
        raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc


def _chat_text(system_prompt: str, user_content: str, cfg: LLMConfig) -> str:
    if not cfg.api_key:
        raise LLMError(MISSING_API_KEY_MESSAGE)
    if not cfg.base_url or not cfg.model:
        raise LLMError("LLM base_url/model is required")

    body = {
        "model": cfg.model,
        "temperature": cfg.temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    data = _http_json(
        _endpoint(cfg.base_url),
        body,
        {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise LLMError(f"Unexpected LLM response: {str(data)[:1000]}") from exc


def _anthropic_text(system_prompt: str, user_content: str, cfg: LLMConfig) -> str:
    if not cfg.api_key:
        raise LLMError(MISSING_API_KEY_MESSAGE)
    base_url = cfg.base_url or ANTHROPIC_DEFAULT_BASE_URL
    model = cfg.model or ANTHROPIC_DEFAULT_MODEL
    if not base_url or not model:
        raise LLMError("LLM base_url/model is required")

    body = {
        "model": model,
        "max_tokens": 4096,
        "temperature": cfg.temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    data = _http_json(
        _anthropic_endpoint(base_url),
        body,
        {
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        content = data.get("content") or []
        texts = [
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        text = "\n".join(part for part in texts if part).strip()
        if not text:
            raise KeyError("empty content")
        return text
    except Exception as exc:
        raise LLMError(f"Unexpected Anthropic response: {str(data)[:1000]}") from exc


def _gemini_text(system_prompt: str, user_content: str, cfg: LLMConfig) -> str:
    if not cfg.api_key:
        raise LLMError(MISSING_API_KEY_MESSAGE)
    base_url = cfg.base_url or GEMINI_DEFAULT_BASE_URL
    model = cfg.model or GEMINI_DEFAULT_MODEL
    if not base_url or not model:
        raise LLMError("LLM base_url/model is required")

    endpoint = _gemini_endpoint(base_url, model)
    if "key=" not in endpoint:
        sep = "&" if "?" in endpoint else "?"
        endpoint = f"{endpoint}{sep}{urlencode({'key': cfg.api_key})}"

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": {"temperature": cfg.temperature},
    }
    data = _http_json(
        endpoint,
        body,
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        candidates = data.get("candidates") or []
        parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
        texts = [str(part.get("text") or "") for part in parts if isinstance(part, dict)]
        text = "\n".join(part for part in texts if part).strip()
        if not text:
            raise KeyError("empty content")
        return text
    except Exception as exc:
        raise LLMError(f"Unexpected Gemini response: {str(data)[:1000]}") from exc


def _provider_text(system_prompt: str, user_content: str, cfg: LLMConfig) -> str:
    provider = (cfg.provider or "openai").lower()
    if provider in {"openai", "openai_compatible", "compatible"}:
        return _chat_text(system_prompt, user_content, cfg)
    if provider in {"anthropic", "claude"}:
        return _anthropic_text(
            system_prompt,
            user_content,
            replace(
                cfg,
                base_url=cfg.base_url or ANTHROPIC_DEFAULT_BASE_URL,
                model=cfg.model or ANTHROPIC_DEFAULT_MODEL,
            ),
        )
    if provider in {"gemini", "google", "google_gemini"}:
        return _gemini_text(
            system_prompt,
            user_content,
            replace(
                cfg,
                base_url=cfg.base_url or GEMINI_DEFAULT_BASE_URL,
                model=cfg.model or GEMINI_DEFAULT_MODEL,
            ),
        )
    raise LLMError(f"Unsupported text provider: {cfg.provider}")


def _openai_text(prompt: str, topic: str, cfg: LLMConfig) -> str:
    return _chat_text(prompt, f"???{topic}", cfg)
