import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any

from .paths import ROOT


DEFAULT_PROMPT_PATH = ROOT / "prompts" / "story_shots.md"
COPY_TO_STORY_PROMPT_PATH = ROOT / "prompts" / "copy_to_story.md"
THEME_PROMPT_PATH = ROOT / "prompts" / "theme_plan.md"
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


def load_theme_prompt() -> str:
    return THEME_PROMPT_PATH.read_text(encoding="utf-8")


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


def generate_topic_plan(brief: str, cfg: LLMConfig, system_prompt: str | None = None) -> dict[str, Any]:
    prompt = system_prompt or load_theme_prompt()
    content = _provider_text(prompt, f"用户给出的选题方向：{brief.strip()}", cfg)
    try:
        data = _extract_json(content)
    except Exception as exc:
        raise LLMError(f"LLM did not return valid theme JSON: {content[:1000]}") from exc
    topic = str(data.get("topic") or "").strip()
    intro = str(data.get("intro") or data.get("description") or "").strip()
    if not topic or not intro:
        raise LLMError(f"Theme JSON missing topic/intro: {content[:1000]}")
    return {"topic": topic, "intro": intro}


def revise_topic_plan(
    brief: str,
    topic: str,
    intro: str,
    instruction: str,
    cfg: LLMConfig,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    prompt = system_prompt or load_theme_prompt()
    user_content = "\n\n".join([
        "请在已有主题方案上继续修改，只输出修改后的严格 JSON。",
        f"原始选题方向：{brief.strip()}",
        f"当前主题：{topic.strip()}",
        f"当前主题介绍：{intro.strip()}",
        f"用户修改意见：{instruction.strip()}",
    ])
    content = _provider_text(prompt, user_content, cfg)
    try:
        data = _extract_json(content)
    except Exception as exc:
        raise LLMError(f"LLM did not return valid revised theme JSON: {content[:1000]}") from exc
    revised_topic = str(data.get("topic") or "").strip()
    revised_intro = str(data.get("intro") or data.get("description") or "").strip()
    if not revised_topic or not revised_intro:
        raise LLMError(f"Revised theme JSON missing topic/intro: {content[:1000]}")
    return {"topic": revised_topic, "intro": revised_intro}


def generate_text(topic: str, cfg: LLMConfig, system_prompt: str | None = None, topic_intro: str = "") -> str:
    prompt = _fill_topic_placeholders(system_prompt or load_default_prompt(), topic)
    user_content = f"主题：{topic}"
    if topic_intro.strip():
        user_content = "\n\n".join([user_content, f"主题介绍：{topic_intro.strip()}"])
    content = _provider_text(prompt, user_content, cfg)
    return content.strip()


def generate_story(topic: str, cfg: LLMConfig, system_prompt: str | None = None, topic_intro: str = "") -> dict[str, Any]:
    content = generate_text(topic, cfg, system_prompt, topic_intro)
    try:
        return _extract_json(content)
    except Exception as exc:
        raise LLMError(f"LLM did not return valid JSON: {content[:1000]}") from exc


def generate_story_from_copy(
    topic: str,
    copy_text: str,
    cfg: LLMConfig,
    system_prompt: str | None = None,
    topic_intro: str = "",
) -> dict[str, Any]:
    prompt = system_prompt or load_copy_to_story_prompt()
    user_parts = [
        f"主题：{topic}",
    ]
    if topic_intro.strip():
        user_parts.append(f"主题介绍：{topic_intro.strip()}")
    user_parts.extend([
        "完整口播文案：",
        copy_text.strip(),
    ])
    user_content = "\n\n".join(user_parts)
    content = _provider_text(prompt, user_content, cfg)
    try:
        return _extract_json(content)
    except Exception as exc:
        raise LLMError(f"LLM did not return valid storyboard JSON: {content[:1000]}") from exc


def improve_image_prompt(story: dict[str, Any], shot_index: int, cfg: LLMConfig) -> dict[str, Any]:
    shots = story.get("shots") or []
    if not isinstance(shots, list) or shot_index < 0 or shot_index >= len(shots):
        raise LLMError("shot_index out of range")
    shot = shots[shot_index] or {}
    system_prompt = (
        "你是短视频分镜生图提示词优化师。"
        "请只输出一条中文图片提示词，不要输出 JSON、解释、编号或 Markdown。"
        "目标是让生图更稳定、更贴合口播和画面描述，同时降低被安全策略拦截的风险。"
        "提示词应包含主体、场景、构图、光线、情绪、风格；不要包含可读文字、Logo、水印、血腥、肢解、尸体细节、露骨暴力或色情。"
        "如果原描述有暴力/血腥/恐怖内容，请改写成隐喻化、非血腥、镜头语言化的表达。"
        "长度控制在 40 到 90 个中文字符。"
    )
    user_content = "\n".join([
        f"故事标题：{story.get('title') or ''}",
        f"整体风格：{story.get('style_preset') or ''}",
        f"镜头序号：{shot_index + 1}",
        f"口播：{shot.get('voiceover') or ''}",
        f"画面描述：{shot.get('visual') or ''}",
        f"原图片提示词：{shot.get('image_prompt') or ''}",
        "请输出优化后的图片提示词：",
    ])
    content = _provider_text(system_prompt, user_content, replace(cfg, temperature=cfg.temperature or 0.4))
    prompt = content.strip().strip("`").strip()
    for prefix in ("图片提示词：", "优化后的图片提示词：", "提示词："):
        if prompt.startswith(prefix):
            prompt = prompt[len(prefix):].strip()
    if "\n" in prompt:
        prompt = "，".join(part.strip(" -\t") for part in prompt.splitlines() if part.strip())
    if not prompt:
        raise LLMError("LLM returned empty image prompt")
    return {"image_prompt": prompt[:500]}


def test_text_connection(cfg: LLMConfig) -> dict[str, Any]:
    content = _provider_text("你是接口连通性测试助手。只回复 OK。", "请回复 OK", replace(cfg, temperature=0))
    return {
        "ok": True,
        "provider": cfg.provider,
        "model": cfg.model,
        "sample": content.strip()[:80],
    }
