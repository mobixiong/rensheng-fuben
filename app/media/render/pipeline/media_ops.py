from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

from app.media.render.ffmpeg_utils import media_duration, run_command, video_dimensions

def _concat(clips: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".txt")
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
    run_command(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)])

def _concat_audio(files: list[Path], out_path: Path) -> None:
    list_path = out_path.with_suffix(".audio.txt")
    list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in files), encoding="utf-8")
    run_command([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-vn", "-c:a", "libmp3lame", "-b:a", "192k", str(out_path),
    ])

def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _safe_media_duration(path: Path) -> float | None:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return None
        duration = media_duration(path)
    except Exception:
        return None
    return duration if duration > 0 else None

def _valid_audio(path: Path) -> bool:
    duration = _safe_media_duration(path)
    return duration is not None and duration > 0.05

def _valid_image(path: Path) -> bool:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        with Image.open(path) as img:
            img.verify()
    except Exception:
        return False
    return True

def _valid_video(path: Path, size: tuple[int, int] | None = None, min_duration: float = 0.05) -> bool:
    duration = _safe_media_duration(path)
    if duration is None or duration < min_duration:
        return False
    if size is None:
        return True
    try:
        return video_dimensions(path) == size
    except Exception:
        return False

