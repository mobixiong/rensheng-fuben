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
THEME_IDEAS_PROMPT_PATH = ROOT / "prompts" / "theme_ideas.md"
IMPROVE_IMAGE_PROMPT_PATH = ROOT / "prompts" / "image_prompt_improve.md"
DEFAULT_LLM_BASE_URL = "http://43.131.249.187:3000/v1"
DEFAULT_TEXT_MODEL = "gpt-5.5"
GEMINI_WEB2API_BASE_URL = "http://127.0.0.1:8081/v1"
GEMINI_WEB2API_MODEL = "gemini-3.5-flash-thinking"
MISSING_API_KEY_MESSAGE = "密钥未填写，密钥是群号"
STORYBOARD_GRANULARITY_RULES = {
    "coarse": """分镜粒度模式：粗。
- 目标是镜头更少、每个镜头承载更完整的一小段语义。
- 每个 shot 的 voiceover 建议控制在 70 到 100 个中文字符左右，短段可以略低，但不要低于 55 字。
- 一个 shot 可以覆盖同一地点、同一动作链或同一情绪推进下的连续 2 到 3 句口播。
- 不要把同一场景里的连续动作拆成过多镜头；优先保留完整语义和观看流畅度。
- 画面描述要概括这一小段口播的核心场景，不要为每个短句单独切镜头。""",
    "balanced": """分镜粒度模式：平衡。
- 目标是镜头数量和口播节奏均衡。
- 每个 shot 的 voiceover 建议控制在 30 到 50 个中文字符左右；短句可以略低于 30 字，但不要超过 55 字。
- 每段口播对应一个明确画面，再由口播总长度自然推导分镜数量。
- 不要为了凑镜头数量把一句完整表达拆得过碎，也不要把多个明显不同的情绪、动作或场景塞进同一个 shot。""",
    "fine": """分镜粒度模式：细。
- 目标是镜头更密、节奏更快、画面变化更频繁。
- 每个 shot 的 voiceover 建议控制在 18 到 30 个中文字符左右，原则上不要超过 35 字。
- 每个动作、账单数字、情绪变化、场景切换、人物反应都可以单独成为一个 shot。
- 适合强节奏短视频，但仍要保证 voiceover 来自原文，不要改写成另一种文风。""",
}
DEFAULT_STORYBOARD_GRANULARITY = "balanced"


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
            base_url=(payload.get("base_url") or os.getenv("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL).strip(),
            api_key=(payload.get("api_key") or os.getenv("LLM_API_KEY") or "").strip(),
            model=(payload.get("model") or os.getenv("LLM_MODEL") or DEFAULT_TEXT_MODEL).strip(),
            temperature=float(payload.get("temperature") or os.getenv("LLM_TEMPERATURE") or 0.8),
        )


class LLMError(RuntimeError):
    pass


def load_default_prompt() -> str:
    return DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")


def load_copy_to_story_prompt() -> str:
    return COPY_TO_STORY_PROMPT_PATH.read_text(encoding="utf-8")


def _storyboard_granularity(value: str | None) -> str:
    key = str(value or DEFAULT_STORYBOARD_GRANULARITY).strip().lower()
    return key if key in STORYBOARD_GRANULARITY_RULES else DEFAULT_STORYBOARD_GRANULARITY


def _append_storyboard_granularity(prompt: str, granularity: str | None) -> str:
    key = _storyboard_granularity(granularity)
    return "\n\n".join([
        prompt.strip(),
        "以下粒度规则优先级高于上文中关于 voiceover 字数、镜头数量和拆分密度的描述：",
        STORYBOARD_GRANULARITY_RULES[key],
    ])


def load_theme_prompt() -> str:
    return THEME_PROMPT_PATH.read_text(encoding="utf-8")


def load_theme_ideas_prompt() -> str:
    return THEME_IDEAS_PROMPT_PATH.read_text(encoding="utf-8")


def load_improve_image_prompt() -> str:
    return IMPROVE_IMAGE_PROMPT_PATH.read_text(encoding="utf-8")


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
        api_key=cfg.api_key or os.getenv("GEMINI_WEB2API_API_KEY") or "",
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


def generate_theme_ideas(
    brief: str,
    cfg: LLMConfig,
    system_prompt: str | None = None,
    *,
    count: int = 6,
    instruction: str = "",
) -> dict[str, Any]:
    prompt = system_prompt or load_theme_ideas_prompt()
    safe_count = max(1, min(int(count or 6), 12))
    user_parts = [
        f"需要生成 {safe_count} 条候选选题方向。",
        f"用户给出的粗略方向：{brief.strip() or '未填写，请直接给出候选方向'}",
    ]
    if instruction.strip():
        user_parts.append(f"额外要求：{instruction.strip()}")
    content = _provider_text(prompt, "\n".join(user_parts), replace(cfg, temperature=cfg.temperature or 0.8))
    try:
        data = _extract_json(content)
    except Exception as exc:
        raise LLMError(f"LLM did not return valid theme ideas JSON: {content[:1000]}") from exc
    raw_ideas = data.get("ideas") if isinstance(data, dict) else None
    if not isinstance(raw_ideas, list):
        raise LLMError(f"Theme ideas JSON missing ideas array: {content[:1000]}")
    ideas: list[dict[str, Any]] = []
    for item in raw_ideas:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        direction = str(item.get("direction") or item.get("brief") or item.get("idea") or "").strip()
        reason = str(item.get("reason") or item.get("description") or "").strip()
        raw_tags = item.get("tags")
        tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()] if isinstance(raw_tags, list) else []
        if not direction:
            continue
        ideas.append({
            "title": title or direction[:18],
            "direction": direction,
            "tags": tags[:5],
            "reason": reason,
        })
        if len(ideas) >= safe_count:
            break
    if not ideas:
        raise LLMError(f"Theme ideas JSON contains no valid ideas: {content[:1000]}")
    return {"ideas": ideas}


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
    storyboard_granularity: str = DEFAULT_STORYBOARD_GRANULARITY,
) -> dict[str, Any]:
    prompt = _append_storyboard_granularity(system_prompt or load_copy_to_story_prompt(), storyboard_granularity)
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


def improve_image_prompt(
    story: dict[str, Any],
    shot_index: int,
    cfg: LLMConfig,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    shots = story.get("shots") or []
    if not isinstance(shots, list) or shot_index < 0 or shot_index >= len(shots):
        raise LLMError("shot_index out of range")
    shot = shots[shot_index] or {}
    prompt = system_prompt or load_improve_image_prompt()
    user_content = "\n".join([
        f"故事标题：{story.get('title') or ''}",
        f"整体风格：{story.get('style_preset') or ''}",
        f"镜头序号：{shot_index + 1}",
        f"口播：{shot.get('voiceover') or ''}",
        f"画面描述：{shot.get('visual') or ''}",
        f"原图片提示词：{shot.get('image_prompt') or ''}",
        "请输出优化后的图片提示词：",
    ])
    content = _provider_text(prompt, user_content, replace(cfg, temperature=cfg.temperature or 0.4))
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


REFERENCE_SELECTION_PROMPT = """你是短视频分镜参考图选择器。
你的任务不是选择所有相关图片，而是从资产列表中选择“最关键的一张参考图”。

选择规则：
1. 默认只选择 1 张参考图。
2. 如果镜头中出现明确人物，优先选择该人物。
3. 只有在没有明确人物时，才选择核心场景。
4. 只有在没有人物和场景时，才选择风格图。
5. 道具、服装只有在它们是镜头唯一主体时才选择。
6. 如果没有合适图片，返回 null。
7. 只能从资产列表中选择已有 id。
8. 不要为了凑数选择参考图。
9. 只返回 JSON，不要输出解释文本。

返回格式：
{"selected_asset_id": "资产 id 或 null", "selection_type": "character/scene/prop/costume/style/none", "reason": "一句中文原因"}"""


REFERENCE_TYPE_PRIORITY = {
    "character": 10,
    "scene": 8,
    "prop": 6,
    "costume": 5,
    "style": 3,
    "other": 1,
}


def _shot_reference_text(shot: dict[str, Any]) -> str:
    return "\n".join([
        str(shot.get("punch") or ""),
        str(shot.get("keyword") or ""),
        str(shot.get("voiceover") or ""),
        str(shot.get("visual") or ""),
        str(shot.get("image_prompt") or ""),
    ])


def _fallback_reference_selection(shot: dict[str, Any], assets: list[dict[str, Any]]) -> dict[str, Any]:
    shot_text = _shot_reference_text(shot)
    best: tuple[int, dict[str, Any]] | None = None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        terms = [str(asset.get("name") or "").strip()]
        terms.extend(str(tag or "").strip() for tag in asset.get("tags") or [])
        terms = [term for term in terms if term]
        if not terms or not any(term and term in shot_text for term in terms):
            continue
        score = max((len(term) for term in terms if term in shot_text), default=0)
        score += REFERENCE_TYPE_PRIORITY.get(str(asset.get("type") or "other"), 1)
        if best is None or score > best[0]:
            best = (score, asset)
    if best is None:
        return {"selected_asset_id": None, "selection_type": "none", "reason": "镜头没有命中任何资产名称或标签"}
    asset = best[1]
    return {
        "selected_asset_id": asset.get("id"),
        "selection_type": asset.get("type") or "other",
        "reason": f"镜头内容命中资产“{asset.get('name') or asset.get('id')}”",
    }


def select_primary_reference_asset(
    shot: dict[str, Any],
    assets: list[dict[str, Any]],
    cfg: LLMConfig,
) -> dict[str, Any]:
    valid_assets = [
        {
            "id": str(asset.get("id") or ""),
            "name": str(asset.get("name") or ""),
            "type": str(asset.get("type") or "other"),
            "description": str(asset.get("description") or ""),
            "tags": asset.get("tags") if isinstance(asset.get("tags"), list) else [],
        }
        for asset in assets
        if isinstance(asset, dict) and asset.get("id") and asset.get("name")
    ]
    if not valid_assets:
        return {"selected_asset_id": None, "selection_type": "none", "reason": "资产集合为空"}
    fallback = _fallback_reference_selection(shot, valid_assets)
    if not (cfg.base_url and cfg.api_key and cfg.model):
        return fallback

    user_content = json.dumps({
        "shot": {
            "voiceover": shot.get("voiceover") or "",
            "visual": shot.get("visual") or "",
            "image_prompt": shot.get("image_prompt") or "",
        },
        "available_assets": valid_assets,
    }, ensure_ascii=False, indent=2)
    try:
        content = _provider_text(REFERENCE_SELECTION_PROMPT, user_content, replace(cfg, temperature=0))
        data = _extract_json(content)
    except Exception:
        return fallback

    selected_id = data.get("selected_asset_id")
    selected_id = str(selected_id).strip() if selected_id is not None else ""
    allowed = {asset["id"]: asset for asset in valid_assets}
    if not selected_id or selected_id.lower() == "null" or selected_id not in allowed:
        return {"selected_asset_id": None, "selection_type": "none", "reason": str(data.get("reason") or "没有合适参考图")}
    asset = allowed[selected_id]
    return {
        "selected_asset_id": selected_id,
        "selection_type": asset.get("type") or str(data.get("selection_type") or "other"),
        "reason": str(data.get("reason") or f"选择最关键参考图：{asset.get('name')}")[:240],
    }
