from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any

from app.core.paths import ROOT

from .constants import COPY_TO_STORY_PROMPT_PATH, DEFAULT_PROMPT_PATH, DEFAULT_STORYBOARD_GRANULARITY, IMPROVE_IMAGE_PROMPT_PATH, STORYBOARD_GRANULARITY_RULES, THEME_IDEAS_PROMPT_PATH, THEME_PROMPT_PATH

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

