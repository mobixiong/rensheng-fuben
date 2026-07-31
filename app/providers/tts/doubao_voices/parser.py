from __future__ import annotations

import html
import re
from typing import Any

from .constants import (
    _FIELD_ALIASES,
    _GROUP_DEFINITIONS,
    _MULTILINGUAL_TEXT,
    _REALTIME_TEXT,
    _TTS_1_0_TEXT,
    _TTS_2_0_TEXT,
    _VOICE_LIST_TEXT,
)

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
        voice["supports_mix"] = mix in {"yes", "true", "1", "是"}
    return voice
