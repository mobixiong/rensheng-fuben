from __future__ import annotations

import copy
import html
import json
import re
import time
import urllib.request
from typing import Any


DOUBAO_TTS_VOICE_DOC_URL = "https://www.volcengine.com/docs/6561/1257544?lang=zh"
DOUBAO_TTS_VOICE_DOC_API = "https://www.volcengine.com/api/doc/getDocDetail?LibraryID=6561&DocumentID=1257544&lang=zh&type="

DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID = "volc.service_type.10029"
DOUBAO_TTS_1_0_RESOURCE_ID = "seed-tts-1.0"
DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID = "seed-tts-1.0-concurr"
DOUBAO_TTS_2_0_RESOURCE_ID = "seed-tts-2.0"

DOUBAO_TTS_1_0_DEFAULT_VOICE_ID = "zh_male_beijingxiaoye_emo_v2_mars_bigtts"
DOUBAO_TTS_2_0_DEFAULT_VOICE_ID = "zh_female_vv_uranus_bigtts"

_CACHE_TTL_SECONDS = 6 * 60 * 60
_VOICE_CATALOG_CACHE: tuple[float, dict[str, Any]] | None = None

_VOICE_LIST_TEXT = "\u97f3\u8272\u5217\u8868"
_TTS_1_0_TEXT = "\u8c46\u5305\u8bed\u97f3\u5408\u6210\u6a21\u578b1.0"
_TTS_2_0_TEXT = "\u8c46\u5305\u8bed\u97f3\u5408\u6210\u6a21\u578b2.0"
_MULTILINGUAL_TEXT = "\u591a\u8bed\u79cd"
_REALTIME_TEXT = "\u7aef\u5230\u7aef\u5b9e\u65f6\u8bed\u97f3\u5927\u6a21\u578b"

_SCENE_HEADER = "\u573a\u666f"
_NAME_HEADER = "\u97f3\u8272\u540d\u79f0"
_LANGUAGE_HEADER = "\u8bed\u79cd"
_LANGUAGE_DIALECT_HEADER = "\u8bed\u79cd/\u65b9\u8a00"
_CAPABILITIES_HEADER = "\u652f\u6301\u80fd\u529b"
_EMOTIONS_HEADER = "\u652f\u6301\u7684\u60c5\u611f"
_TAGS_HEADER = "\u7279\u6b8a\u6807\u7b7e"
_COUNTERPART_HEADER = "\u5bf9\u5e942.0\u97f3\u8272"
_MIX_HEADER = "\u662f\u5426\u652f\u6301MIX"
_INFERENCE_MODE_HEADER = "\u63a8\u8350\u63a8\u7406\u6a21\u5f0f"
_NOTES_HEADER = "\u5907\u6ce8"

_FIELD_ALIASES = {
    _SCENE_HEADER: "scene",
    _NAME_HEADER: "name",
    "voice_type": "id",
    _LANGUAGE_HEADER: "language",
    _LANGUAGE_DIALECT_HEADER: "language",
    _CAPABILITIES_HEADER: "capabilities",
    _EMOTIONS_HEADER: "emotions",
    _TAGS_HEADER: "tags",
    _COUNTERPART_HEADER: "counterpart_2_0",
    _MIX_HEADER: "supports_mix",
    _INFERENCE_MODE_HEADER: "recommended_inference_mode",
    _NOTES_HEADER: "notes",
}

_GROUP_DEFINITIONS = {
    "doubao-tts-2.0": {
        "id": "doubao-tts-2.0",
        "model": "doubao-tts-2.0",
        "resource_ids": [DOUBAO_TTS_2_0_RESOURCE_ID],
        "tts_compatible": True,
    },
    "doubao-tts-2.0-multilingual": {
        "id": "doubao-tts-2.0-multilingual",
        "model": "doubao-tts-2.0",
        "resource_ids": [DOUBAO_TTS_2_0_RESOURCE_ID],
        "tts_compatible": True,
    },
    "doubao-realtime-s2s-sc-2.0": {
        "id": "doubao-realtime-s2s-sc-2.0",
        "model": "doubao-realtime-s2s-sc-2.0",
        "resource_ids": [],
        "tts_compatible": False,
    },
    "doubao-tts-1.0": {
        "id": "doubao-tts-1.0",
        "model": "doubao-tts-1.0",
        "resource_ids": [
            DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID,
            DOUBAO_TTS_1_0_RESOURCE_ID,
            DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID,
        ],
        "tts_compatible": True,
    },
}

DOUBAO_TTS_RESOURCE_MODELS = [
    {
        "value": DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID,
        "label": f"{DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID} (legacy 1.0)",
        "voice_groups": ["doubao-tts-1.0"],
        "default_voice_id": DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
        "selectable": True,
    },
    {
        "value": DOUBAO_TTS_2_0_RESOURCE_ID,
        "label": f"{DOUBAO_TTS_2_0_RESOURCE_ID} (2.0)",
        "voice_groups": ["doubao-tts-2.0", "doubao-tts-2.0-multilingual"],
        "default_voice_id": DOUBAO_TTS_2_0_DEFAULT_VOICE_ID,
        "selectable": True,
    },
    {
        "value": DOUBAO_TTS_1_0_RESOURCE_ID,
        "label": f"{DOUBAO_TTS_1_0_RESOURCE_ID} (1.0)",
        "voice_groups": ["doubao-tts-1.0"],
        "default_voice_id": DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
        "selectable": True,
    },
    {
        "value": DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID,
        "label": f"{DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID} (1.0 concurrent)",
        "voice_groups": ["doubao-tts-1.0"],
        "default_voice_id": DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
        "selectable": True,
    },
]

_FALLBACK_GROUPS = [
    {
        **_GROUP_DEFINITIONS["doubao-tts-1.0"],
        "title": "Doubao TTS 1.0",
        "voices": [
            {
                "id": DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
                "name": "Beijing Xiaoye",
                "scene": "multi emotion",
                "language": "Chinese",
            }
        ],
    },
    {
        **_GROUP_DEFINITIONS["doubao-tts-2.0"],
        "title": "Doubao TTS 2.0",
        "voices": [
            {
                "id": DOUBAO_TTS_2_0_DEFAULT_VOICE_ID,
                "name": "Vivi 2.0",
                "scene": "general",
                "language": "Chinese",
            },
            {
                "id": "zh_female_jiaochuannv_uranus_bigtts",
                "name": "Jiaochuan Female 2.0",
                "scene": "general",
                "language": "Chinese",
            },
        ],
    },
]


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


def parse_doubao_voice_groups(content: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    headers: list[str] = []
    last_scene = ""
    seen_ids: set[tuple[str, str]] = set()

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            title = _clean_cell(stripped.lstrip("#").strip())
            group_id = _group_id_from_title(title)
            if group_id:
                definition = _GROUP_DEFINITIONS[group_id]
                current = {
                    **definition,
                    "title": title,
                    "voices": [],
                }
                groups.append(current)
            else:
                current = None
            headers = []
            last_scene = ""
            continue

        if not current or not stripped.startswith("|"):
            continue

        cells = _split_markdown_row(stripped)
        if not cells or _is_separator_row(cells):
            continue
        if any(cell == "voice_type" for cell in cells):
            headers = [_field_key(cell) for cell in cells]
            continue
        if not headers or len(cells) < 3:
            continue

        row: dict[str, Any] = {}
        for index, key in enumerate(headers[: len(cells)]):
            if key:
                row[key] = cells[index]

        voice_id = str(row.get("id") or "").strip()
        if not _looks_like_voice_id(voice_id):
            continue

        scene = str(row.get("scene") or "").strip()
        if scene:
            last_scene = scene
        elif last_scene:
            row["scene"] = last_scene

        dedupe_key = (current["id"], voice_id)
        if dedupe_key in seen_ids:
            continue
        seen_ids.add(dedupe_key)
        current["voices"].append(_voice_from_row(row, current))

    return groups


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


def _group_id_from_title(title: str) -> str:
    compact = title.replace(" ", "")
    if _VOICE_LIST_TEXT not in compact:
        return ""
    if _REALTIME_TEXT in compact or "S2S" in compact or "SC-2.0" in compact:
        return "doubao-realtime-s2s-sc-2.0"
    if _TTS_1_0_TEXT in compact:
        return "doubao-tts-1.0"
    if _TTS_2_0_TEXT in compact and _MULTILINGUAL_TEXT in compact:
        return "doubao-tts-2.0-multilingual"
    if _TTS_2_0_TEXT in compact:
        return "doubao-tts-2.0"
    return ""


def _split_markdown_row(line: str) -> list[str]:
    raw = line.strip()
    if not raw.startswith("|"):
        return []
    body = raw[1:]
    if body.endswith("|"):
        body = body[:-1]
    placeholder = "\0PIPE\0"
    body = body.replace(r"\|", placeholder)
    return [_clean_cell(cell.replace(placeholder, "|")) for cell in body.split("|")]


def _clean_cell(value: str) -> str:
    value = value.replace(r"\-", "-")
    value = value.replace("<br><br>", " / ").replace("<br>", " / ")
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("**", "").replace("`", "").replace("\\", "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _is_separator_row(cells: list[str]) -> bool:
    raw = "".join(cells).strip()
    return bool(raw) and set(raw) <= {"-", ":"}


def _field_key(header: str) -> str:
    normalized = _clean_cell(header).replace(" ", "")
    return _FIELD_ALIASES.get(normalized, "")


def _looks_like_voice_id(value: str) -> bool:
    return bool(re.search(r"(?:_bigtts|_tob|^ICL_|^saturn_)", value))


def _voice_from_row(row: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    voice: dict[str, Any] = {
        "id": str(row.get("id") or "").strip(),
        "name": str(row.get("name") or row.get("id") or "").strip(),
        "scene": str(row.get("scene") or "").strip(),
        "language": str(row.get("language") or "").strip(),
        "model": group.get("model") or "",
        "group_id": group.get("id") or "",
        "group_title": group.get("title") or "",
    }
    for key in ("capabilities", "emotions", "tags", "counterpart_2_0", "recommended_inference_mode", "notes"):
        value = str(row.get(key) or "").strip()
        if value:
            voice[key] = value
    mix = str(row.get("supports_mix") or "").strip()
    if mix:
        voice["supports_mix"] = mix in {"yes", "true", "1", "\u662f"}
    return voice
