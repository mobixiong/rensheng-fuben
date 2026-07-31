from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any

from app.core.paths import ROOT

from .client import _extract_json, _provider_text
from .constants import DEFAULT_STORYBOARD_GRANULARITY, LLMConfig, LLMError
from .prompts import _append_storyboard_granularity, load_copy_to_story_prompt, load_default_prompt, load_improve_image_prompt, load_theme_ideas_prompt, load_theme_prompt

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

