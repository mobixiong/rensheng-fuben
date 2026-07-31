from __future__ import annotations

import copy
import json
import time
import urllib.request
from typing import Any

from .constants import (
    DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
    DOUBAO_TTS_2_0_DEFAULT_VOICE_ID,
    DOUBAO_TTS_2_0_RESOURCE_ID,
    DOUBAO_TTS_RESOURCE_MODELS,
    DOUBAO_TTS_VOICE_DOC_API,
    DOUBAO_TTS_VOICE_DOC_URL,
    _CACHE_TTL_SECONDS,
    _FALLBACK_GROUPS,
)
from .parser import parse_doubao_voice_groups

_VOICE_CATALOG_CACHE: tuple[float, dict[str, Any]] | None = None


def default_doubao_voice_for_resource(resource_id: str) -> str:
    if resource_id == DOUBAO_TTS_2_0_RESOURCE_ID:
        return DOUBAO_TTS_2_0_DEFAULT_VOICE_ID
    return DOUBAO_TTS_1_0_DEFAULT_VOICE_ID


def get_doubao_voice_catalog(resource_id: str = "") -> dict[str, Any]:
    global _VOICE_CATALOG_CACHE
    now = time.time()
    if _VOICE_CATALOG_CACHE and now - _VOICE_CATALOG_CACHE[0] < _CACHE_TTL_SECONDS:
        catalog = copy.deepcopy(_VOICE_CATALOG_CACHE[1])
    else:
        try:
            content = _fetch_voice_doc_content()
            groups = parse_doubao_voice_groups(content)
            if not groups:
                raise ValueError("Volcengine voice doc did not contain voice groups")
            catalog = _build_catalog(groups, source="volc_doc_1257544")
        except Exception:
            catalog = _build_catalog(copy.deepcopy(_FALLBACK_GROUPS), source="fallback")
        _VOICE_CATALOG_CACHE = (now, copy.deepcopy(catalog))

    return _with_filtered_voices(catalog, resource_id.strip())


def _fetch_voice_doc_content() -> str:
    req = urllib.request.Request(DOUBAO_TTS_VOICE_DOC_API, headers={"User-Agent": "life-copy-workbench/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    result = payload.get("Result") or {}
    return str(result.get("MDContent") or result.get("Content") or "")


def _build_catalog(groups: list[dict[str, Any]], source: str) -> dict[str, Any]:
    models = copy.deepcopy(DOUBAO_TTS_RESOURCE_MODELS)
    for model in models:
        group_ids = set(model.get("voice_groups") or [])
        model["voice_count"] = sum(len(group.get("voices") or []) for group in groups if group.get("id") in group_ids)
    for group in groups:
        group["voice_count"] = len(group.get("voices") or [])
    return {
        "source": source,
        "doc_url": DOUBAO_TTS_VOICE_DOC_URL,
        "models": models,
        "groups": groups,
    }


def _with_filtered_voices(catalog: dict[str, Any], resource_id: str) -> dict[str, Any]:
    output = copy.deepcopy(catalog)
    voices = _voices_for_resource(output, resource_id)
    output["resource_id"] = resource_id
    output["voices"] = voices
    output["voice_count"] = len(voices)
    return output


def _voices_for_resource(catalog: dict[str, Any], resource_id: str) -> list[dict[str, Any]]:
    group_ids: set[str] = set()
    if resource_id:
        for model in catalog.get("models") or []:
            if model.get("value") == resource_id:
                group_ids.update(model.get("voice_groups") or [])
                break
    else:
        for model in catalog.get("models") or []:
            if model.get("selectable") is not False:
                group_ids.update(model.get("voice_groups") or [])

    voices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in catalog.get("groups") or []:
        if group.get("id") not in group_ids:
            continue
        for voice in group.get("voices") or []:
            voice_id = voice.get("id")
            if not voice_id or voice_id in seen:
                continue
            voices.append(voice)
            seen.add(voice_id)
    return voices
