from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .render_constants import H, W

SUBTITLE_FONT_SIZE = 54
SUBTITLE_MAX_WIDTH = W - 180


def _font_path() -> str:
    for p in [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\Dengb.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    ]:
        if Path(p).exists():
            return p
    return ""


FONT_PATH = _font_path()


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.truetype(FONT_PATH, size=size) if FONT_PATH else ImageFont.load_default()


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


def _subtitle_chunks(text: str, max_width: int = SUBTITLE_MAX_WIDTH) -> list[str]:
    clean = " ".join(str(text or "").split())
    if not clean:
        return [""]

    font = _font(SUBTITLE_FONT_SIZE)
    draw = ImageDraw.Draw(Image.new("RGB", (8, 8), "#000000"))
    break_chars = "，。！？；、,.!?; "
    chunks: list[str] = []
    current = ""

    def text_width(value: str) -> int:
        box = draw.textbbox((0, 0), value, font=font, stroke_width=4)
        return box[2] - box[0]

    for ch in clean:
        candidate = current + ch
        if current and text_width(candidate) > max_width:
            split_at = max(current.rfind(mark) for mark in break_chars)
            if split_at >= 8 and len(current) - split_at <= 8:
                head = current[: split_at + 1].strip()
                tail = current[split_at + 1 :].strip()
                if head:
                    chunks.append(head)
                current = tail + ch
            else:
                chunks.append(current.strip())
                current = ch.strip()
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk] or [clean]


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


def write_subtitles(shots: list[dict[str, Any]], srt_path: Path, ass_path: Path) -> None:
    events = _subtitle_events(shots)
    srt = []
    for i, event in enumerate(events, 1):
        srt.append(f"{i}\n{_srt_ts(event['start'])} --> {_srt_ts(event['end'])}\n{event['text']}\n")
    srt_path.write_text("\n".join(srt), encoding="utf-8")
    ass = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
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
