from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any

from app.core.paths import ROOT

DEFAULT_PROMPT_PATH = ROOT / "prompts" / "story_shots.md"

COPY_TO_STORY_PROMPT_PATH = ROOT / "prompts" / "copy_to_story.md"

THEME_PROMPT_PATH = ROOT / "prompts" / "theme_plan.md"

THEME_IDEAS_PROMPT_PATH = ROOT / "prompts" / "theme_ideas.md"

IMPROVE_IMAGE_PROMPT_PATH = ROOT / "prompts" / "image_prompt_improve.md"

DEFAULT_LLM_BASE_URL = "http://43.131.249.187:3000/v1"

DEFAULT_TEXT_MODEL = "gpt-5.5"

ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-5"

GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"

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

