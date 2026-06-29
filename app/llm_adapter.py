import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_PATH = ROOT / "prompts" / "story_shots.md"
COPY_TO_STORY_PROMPT_PATH = ROOT / "prompts" / "copy_to_story.md"
GEMINI_WEB2API_BASE_URL = "http://127.0.0.1:8081/v1"
GEMINI_WEB2API_MODEL = "gemini-3.5-flash-thinking"


@dataclass
class LLMConfig:
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.8

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LLMConfig":
        return cls(
            provider=(payload.get("provider") or os.getenv("TEXT_PROVIDER") or "openai").strip(),
            base_url=(payload.get("base_url") or os.getenv("LLM_BASE_URL") or "").strip(),
            api_key=(payload.get("api_key") or os.getenv("LLM_API_KEY") or "").strip(),
            model=(payload.get("model") or os.getenv("LLM_MODEL") or "").strip(),
            temperature=float(payload.get("temperature") or os.getenv("LLM_TEMPERATURE") or 0.8),
        )


class LLMError(RuntimeError):
    pass


def load_default_prompt() -> str:
    return DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")


def load_copy_to_story_prompt() -> str:
    return COPY_TO_STORY_PROMPT_PATH.read_text(encoding="utf-8")


def _endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1/chat/completions") or clean.endswith("/chat/completions"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/chat/completions"
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


def _chat_text(system_prompt: str, user_content: str, cfg: LLMConfig) -> str:
    if not cfg.base_url or not cfg.api_key or not cfg.model:
        raise LLMError("LLM base_url/api_key/model is required")

    body = {
        "model": cfg.model,
        "temperature": cfg.temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
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


def _provider_text(system_prompt: str, user_content: str, cfg: LLMConfig) -> str:
    provider = (cfg.provider or "openai").lower()
    if provider in {"openai", "openai_compatible", "compatible"}:
        return _chat_text(system_prompt, user_content, cfg)
    if provider in {"gemini", "gemini_web2api", "web2api", "gemini_reverse_proxy"}:
        return _gemini_web2api_text(system_prompt, user_content, cfg)
    raise LLMError(f"Unsupported text provider: {cfg.provider}")


def _openai_text(prompt: str, topic: str, cfg: LLMConfig) -> str:
    return _chat_text(prompt, f"\u4e3b\u9898\uff1a{topic}", cfg)


def _gemini_web2api_text(prompt: str, user_content: str, cfg: LLMConfig) -> str:
    web2api_cfg = replace(
        cfg,
        base_url=cfg.base_url or os.getenv("GEMINI_WEB2API_BASE_URL") or GEMINI_WEB2API_BASE_URL,
        api_key=cfg.api_key or os.getenv("GEMINI_WEB2API_API_KEY") or "sk-local",
        model=cfg.model or os.getenv("GEMINI_WEB2API_MODEL") or GEMINI_WEB2API_MODEL,
    )
    return _chat_text(prompt, user_content, web2api_cfg)


def _fill_topic_placeholders(prompt: str, topic: str) -> str:
    replacements = {
        "【填写主题】": topic,
        "【主题】": topic,
        "{主题}": topic,
        "【在这里填写主题，比如：快递小哥 / 外卖员 / 县城宝妈 / 北漂程序员 / 房产中介】": topic,
    }
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def generate_text(topic: str, cfg: LLMConfig, system_prompt: str | None = None) -> str:
    prompt = _fill_topic_placeholders(system_prompt or load_default_prompt(), topic)
    content = _provider_text(prompt, f"\u4e3b\u9898\uff1a{topic}", cfg)
    return content.strip()


def generate_story(topic: str, cfg: LLMConfig, system_prompt: str | None = None) -> dict[str, Any]:
    content = generate_text(topic, cfg, system_prompt)
    try:
        return _extract_json(content)
    except Exception as exc:
        raise LLMError(f"LLM did not return valid JSON: {content[:1000]}") from exc


def generate_story_from_copy(topic: str, copy_text: str, cfg: LLMConfig, system_prompt: str | None = None) -> dict[str, Any]:
    prompt = system_prompt or load_copy_to_story_prompt()
    user_content = "\n\n".join([
        f"主题：{topic}",
        "完整口播文案：",
        copy_text.strip(),
    ])
    content = _provider_text(prompt, user_content, cfg)
    try:
        return _extract_json(content)
    except Exception as exc:
        raise LLMError(f"LLM did not return valid storyboard JSON: {content[:1000]}") from exc


def test_text_connection(cfg: LLMConfig) -> dict[str, Any]:
    content = _provider_text("你是接口连通性测试助手。只回复 OK。", "请回复 OK", replace(cfg, temperature=0))
    return {
        "ok": True,
        "provider": cfg.provider,
        "model": cfg.model,
        "sample": content.strip()[:80],
    }
