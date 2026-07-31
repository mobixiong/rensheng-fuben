from __future__ import annotations

import random
from typing import Any

from app.core.paths import ROOT

from .constants import COPY_PRESET_THEME_PROFILES, COPY_PROMPT_PRESETS


def _default_copy_prompt(preset: str) -> str:
    if preset == "reality_breakout":
        path = ROOT / "prompts" / "copy_reality_breakout.md"
    elif preset == "reality_stop_loss":
        path = ROOT / "prompts" / "copy_reality_stop_loss.md"
    elif preset == "reality_burnout_support":
        path = ROOT / "prompts" / "copy_reality_burnout_support.md"
    elif preset == "reality_reverse":
        path = ROOT / "prompt.txt"
    elif preset == "xianxia":
        path = ROOT / "prompts" / "copy_xianxia.md"
    elif preset == "fantasy_wuxia":
        path = ROOT / "prompts" / "copy_fantasy_wuxia.md"
    elif preset == "fantasy_zombie":
        path = ROOT / "prompts" / "copy_fantasy_zombie.md"
    elif preset == "fantasy_otherworld":
        path = ROOT / "prompts" / "copy_fantasy_otherworld.md"
    elif preset == "fantasy_cyberpunk":
        path = ROOT / "prompts" / "copy_fantasy_cyberpunk.md"
    elif preset == "fantasy_weird_rules":
        path = ROOT / "prompts" / "copy_fantasy_weird_rules.md"
    else:
        path = ROOT / "prompt.txt"
    return path.read_text(encoding="utf-8")

def _resolve_copy_preset(value: Any) -> str:
    preset = str(value or "").strip()
    if preset == "random":
        return random.choice(COPY_PROMPT_PRESETS)
    if preset == "reality":
        return "reality_reverse"
    if preset in COPY_PROMPT_PRESETS:
        return preset
    return "reality_reverse"

def _copy_preset_theme_profile(preset: Any) -> dict[str, str]:
    resolved = _resolve_copy_preset(preset)
    return COPY_PRESET_THEME_PROFILES.get(resolved) or COPY_PRESET_THEME_PROFILES["reality_reverse"]

def _copy_preset_theme_instruction(preset: Any) -> str:
    profile = _copy_preset_theme_profile(preset)
    return "\n".join([
        f"本次自动流水线已经选定文案类型：{profile['label']}。",
        f"选题必须适配这个文案类型，只能从这个范围中抽取：{profile['domain']}。",
        f"主题和主题介绍的情绪/结构方向：{profile['direction']}",
        f"可参考的选题形态：{profile['examples']}",
        f"必须避开：{profile['avoid']}",
        "如果用户提供了顶层要求，例如“猎奇”“温馨”“斗罗大陆世界观”，只能在上述文案类型范围内吸收这些要求，不要改变文案类型。",
        "输出的 title、direction、topic、intro 都要能直接支撑后续对应类型的口播文案生成。",
    ])

def _job_copy_preset(job: dict[str, Any]) -> str:
    input_data = job.get("input") or {}
    preset = _resolve_copy_preset(input_data.get("copy_preset") or "random")
    if input_data.get("copy_preset") != preset:
        input_data["copy_preset"] = preset
        job["input"] = input_data
    return preset

def _default_copy_to_story_prompt() -> str:
    return (ROOT / "prompts" / "copy_to_story.md").read_text(encoding="utf-8")

def _default_image_prompt() -> str:
    return (ROOT / "prompts" / "image_style.md").read_text(encoding="utf-8")

def _default_improve_prompt() -> str:
    return (ROOT / "prompts" / "image_prompt_improve.md").read_text(encoding="utf-8")

