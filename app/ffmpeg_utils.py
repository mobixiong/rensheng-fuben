import shutil
import subprocess
import time
from pathlib import Path

from .errors import RenderError


def run_command(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    if proc.returncode != 0:
        raise RenderError(f"Command failed: {' '.join(cmd)}\n{proc.stderr[-3000:]}")


def safe_unlink(path: Path) -> None:
    for _ in range(4):
        try:
            if path.exists():
                path.unlink()
            return
        except OSError:
            time.sleep(0.15)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def safe_rmtree(path: Path) -> None:
    for _ in range(4):
        try:
            if path.exists():
                shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.15)
    shutil.rmtree(path, ignore_errors=True)


def ffmpeg_path_arg(path: Path) -> str:
    return path.resolve().as_posix().replace(":", "\\:")


def media_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RenderError(proc.stderr)
    return float(proc.stdout.strip())


def video_dimensions(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RenderError(proc.stderr)
    parts = [part.strip() for part in proc.stdout.strip().split(",")]
    if len(parts) < 2:
        raise RenderError(f"Unable to read video dimensions: {path}")
    return int(parts[0]), int(parts[1])
