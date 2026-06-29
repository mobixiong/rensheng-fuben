import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_PATH = ROOT / "prompts" / "story_shots.md"


@dataclass
class LLMConfig:
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.8
    secure_1psid: str = ""
    secure_1psidts: str = ""
    proxy: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LLMConfig":
        return cls(
            provider=(payload.get("provider") or os.getenv("TEXT_PROVIDER") or "openai").strip(),
            base_url=(payload.get("base_url") or os.getenv("LLM_BASE_URL") or "").strip(),
            api_key=(payload.get("api_key") or os.getenv("LLM_API_KEY") or "").strip(),
            model=(payload.get("model") or os.getenv("LLM_MODEL") or "").strip(),
            temperature=float(payload.get("temperature") or os.getenv("LLM_TEMPERATURE") or 0.8),
            secure_1psid=(payload.get("secure_1psid") or os.getenv("GEMINI_SECURE_1PSID") or "").strip(),
            secure_1psidts=(payload.get("secure_1psidts") or os.getenv("GEMINI_SECURE_1PSIDTS") or "").strip(),
            proxy=(payload.get("proxy") or os.getenv("GEMINI_PROXY") or "").strip() or None,
        )


class LLMError(RuntimeError):
    pass


def load_default_prompt() -> str:
    return DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")


def _endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1/chat/completions") or clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/v1/chat/completions"


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


def _openai_text(prompt: str, topic: str, cfg: LLMConfig) -> str:
    if not cfg.base_url or not cfg.api_key or not cfg.model:
        raise LLMError("LLM base_url/api_key/model is required")

    body = {
        "model": cfg.model,
        "temperature": cfg.temperature,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"\u4e3b\u9898\uff1a{topic}"},
        ],
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
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:1000]
        raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise LLMError(f"Unexpected LLM response: {str(data)[:1000]}") from exc


def _gemini_webapi_text(prompt: str, topic: str, cfg: LLMConfig) -> str:
    if not cfg.secure_1psid:
        raise LLMError("Gemini WebAPI requires __Secure-1PSID")
    try:
        import asyncio
        from gemini_webapi import GeminiClient
    except Exception as exc:
        raise LLMError("gemini_webapi is not installed. Run: pip install gemini_webapi") from exc

    async def _run() -> str:
        client = GeminiClient(cfg.secure_1psid, cfg.secure_1psidts or None, proxy=cfg.proxy)
        await client.init(timeout=30, auto_close=True, close_delay=5, auto_refresh=True)
        response = await client.generate_content(f"{prompt}\n\n\u4e3b\u9898\uff1a{topic}")
        return str(response.text)

    return asyncio.run(_run())


def generate_story(topic: str, cfg: LLMConfig, system_prompt: str | None = None) -> dict[str, Any]:
    prompt = system_prompt or load_default_prompt()
    provider = (cfg.provider or "openai").lower()
    if provider in {"openai", "openai_compatible", "compatible"}:
        content = _openai_text(prompt, topic, cfg)
    elif provider in {"gemini", "gemini_webapi", "hanaoka", "hanaokayuzu"}:
        content = _gemini_webapi_text(prompt, topic, cfg)
    else:
        raise LLMError(f"Unsupported text provider: {cfg.provider}")

    try:
        return _extract_json(content)
    except Exception as exc:
        raise LLMError(f"LLM did not return valid JSON: {content[:1000]}") from exc
