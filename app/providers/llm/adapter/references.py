from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any

from app.core.paths import ROOT

from .client import _extract_json, _provider_text
from .constants import LLMConfig, REFERENCE_SELECTION_PROMPT, REFERENCE_TYPE_PRIORITY

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

