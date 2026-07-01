from pathlib import Path
from typing import Any

from .render_constants import H, W

SUBTITLE_FONT_SIZE = 54
SUBTITLE_SPLIT_MARKS = "，。！？；,.!?;"
SUBTITLE_MIN_CHARS = 10


def _srt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_ts(sec: float) -> str:
    cs = int(round(sec * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return str(text).replace("\n", " ").replace("\r", " ").replace("{", "｛").replace("}", "｝").strip()


def _visible_len(text: str) -> int:
    return len(str(text or "").strip().strip(SUBTITLE_SPLIT_MARKS))


def _merge_short_chunks(chunks: list[str]) -> list[str]:
    merged: list[str] = []
    pending = ""
    for chunk in chunks:
        if not chunk:
            continue
        pending = f"{pending}{chunk}" if pending else chunk
        if _visible_len(pending) >= SUBTITLE_MIN_CHARS:
            merged.append(pending)
            pending = ""
    if pending:
        if merged and (_visible_len(pending) < SUBTITLE_MIN_CHARS or _visible_len(merged[-1]) < SUBTITLE_MIN_CHARS):
            merged[-1] = f"{merged[-1]}{pending}"
        else:
            merged.append(pending)
    return merged or chunks


def _subtitle_chunks(text: str) -> list[str]:
    clean = " ".join(str(text or "").split())
    if not clean:
        return [""]

    chunks: list[str] = []
    current = ""
    for ch in clean:
        current += ch
        if ch in SUBTITLE_SPLIT_MARKS:
            chunks.append(current.strip())
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return _merge_short_chunks([chunk for chunk in chunks if chunk] or [clean])


def _subtitle_events(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for shot in shots:
        start = float(shot["start"])
        end = float(shot["end"])
        duration = max(0.1, end - start)
        chunks = _subtitle_chunks(str(shot.get("voiceover", "")))
        weights = [max(1, len(chunk)) for chunk in chunks]
        total_weight = max(1, sum(weights))
        cursor = start
        for index, (chunk, weight) in enumerate(zip(chunks, weights)):
            if index == len(chunks) - 1:
                chunk_end = end
            else:
                chunk_end = min(end, cursor + duration * weight / total_weight)
            events.append({
                "start": cursor,
                "end": max(cursor + 0.08, chunk_end),
                "text": _ass_escape(chunk),
            })
            cursor = chunk_end
    return events


def write_subtitles(shots: list[dict[str, Any]], srt_path: Path, ass_path: Path, size: tuple[int, int] | None = None) -> None:
    width, height = size or (W, H)
    events = _subtitle_events(shots)
    srt = []
    for i, event in enumerate(events, 1):
        srt.append(f"{i}\n{_srt_ts(event['start'])} --> {_srt_ts(event['end'])}\n{event['text']}\n")
    srt_path.write_text("\n".join(srt), encoding="utf-8")
    ass = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Microsoft YaHei,54,&H00FFFFFF,&H000000FF,&H00111111,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,2,70,70,150,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for event in events:
        ass.append(f"Dialogue: 0,{_ass_ts(event['start'])},{_ass_ts(event['end'])},Default,,0,0,0,,{event['text']}")
    ass_path.write_text("\n".join(ass), encoding="utf-8")
