from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from .constants import IMAGE_PROMPT_PATH

def load_image_prompt() -> str:
    return IMAGE_PROMPT_PATH.read_text(encoding="utf-8")

def _image_ratio_label(size: str) -> str:
    value = str(size or "").strip()
    if value in {"16:9", "16 / 9"}:
        return "横屏16:9"
    if value in {"1:1", "1 / 1"}:
        return "正方形1:1"
    return "竖屏9:16"

def build_shot_image_prompt(
    story: dict[str, Any],
    shot: dict[str, Any],
    fixed_prompt: str | None = None,
    size: str = "9:16",
) -> str:
    base = fixed_prompt or load_image_prompt()
    ratio_label = _image_ratio_label(size or shot.get("image_size") or story.get("image_size") or "9:16")
    shot_prompt = str(shot.get("image_prompt") or "").strip()
    parts = [
        base,
        "当前故事整体风格补充：",
        str(story.get("style_preset") or ""),
    ]
    if shot_prompt:
        parts.extend([
            "图片提示词（最高优先级，生图唯一画面内容来源）：",
            shot_prompt,
            "请以这条图片提示词为准，不扩写未提供的画面内容。",
        ])
    else:
        parts.extend([
            "当前分镜信息：",
            f"口播：{shot.get('voiceover', '')}",
            f"画面描述：{shot.get('visual', '')}",
        ])
    reference_asset = shot.get("primary_reference_asset")
    if isinstance(reference_asset, dict) and reference_asset.get("name"):
        tags = reference_asset.get("tags") if isinstance(reference_asset.get("tags"), list) else []
        reference_lines = [
            f"主参考图：{reference_asset.get('name')}",
            f"类型：{reference_asset.get('type') or 'other'}",
        ]
        if reference_asset.get("description"):
            reference_lines.append(f"参考图描述：{reference_asset.get('description')}")
        if tags:
            reference_lines.append(f"标签：{'，'.join(str(tag) for tag in tags if str(tag).strip())}")
        reference_lines.append("请优先参考这张图的核心人物/主体外观，不要把参考图中的无关背景强行带入当前镜头。")
        parts.extend([
            "单主参考图锚定：",
            "\n".join(reference_lines),
        ])
    parts.append(f"请生成一张{ratio_label}分镜图。画面中不要出现可读文字、字幕、Logo、水印、二维码、品牌名或界面文字。")
    return "\n\n".join(parts)

