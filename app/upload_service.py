import re
import shutil
import time
import uuid
from pathlib import Path
from typing import BinaryIO

from .audio_assets import AUDIO_SUFFIXES


MAX_AUDIO_UPLOAD_BYTES = 100 * 1024 * 1024


class AudioUploadError(ValueError):
    pass


def _safe_audio_filename(filename: str) -> str:
    raw = Path(str(filename or "audio")).name
    suffix = Path(raw).suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise AudioUploadError("只支持 mp3、wav、m4a、aac、flac、ogg 音频")
    stem = Path(raw).stem
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", stem).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)[:48] or "audio"
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}_{cleaned}{suffix}"


def save_uploaded_audio(filename: str, source: BinaryIO, target_dir: Path) -> Path:
    safe_name = _safe_audio_filename(filename)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / safe_name).resolve()
    try:
        target.relative_to(target_dir.resolve())
    except ValueError as exc:
        raise AudioUploadError("Invalid audio path") from exc
    total = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_AUDIO_UPLOAD_BYTES:
                    raise AudioUploadError("音频文件不能超过 100MB")
                out.write(chunk)
        if total <= 0:
            raise AudioUploadError("上传的音频文件为空")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target
