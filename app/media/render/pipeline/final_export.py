from __future__ import annotations

import shutil
from pathlib import Path

from app.media.render.ffmpeg_utils import ffmpeg_path_arg, run_command
from app.media.render.intro_templates import INTRO_TEMPLATES


def _video_filter(ass: Path, intro_template: str, duration: float) -> str:
    ass_arg = ffmpeg_path_arg(ass)
    return f"ass='{ass_arg}'"


def _final(
    video: Path,
    audio: Path,
    ass: Path,
    out_path: Path,
    duration: float,
    intro_template: str = "none",
    bgm_path: Path | None = None,
    sfx_path: Path | None = None,
    sfx_offsets: list[float] | None = None,
) -> None:
    intro_template = intro_template if intro_template in INTRO_TEMPLATES else "none"
    vf = _video_filter(ass, intro_template, duration)
    sfx_offsets = [offset for offset in (sfx_offsets or []) if 0 <= float(offset) < duration]
    if bgm_path or (sfx_path and sfx_offsets):
        cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(audio)]
        filters = [f"[0:v]{vf}[vout]", "[1:a]volume=1.0[a0]"]
        audio_labels = ["[a0]"]
        next_input = 2

        if bgm_path:
            cmd.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
            filters.append(f"[{next_input}:a]volume=0.18,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[bgm]")
            audio_labels.append("[bgm]")
            next_input += 1

        if sfx_path:
            for idx, offset in enumerate(sfx_offsets):
                cmd.extend(["-i", str(sfx_path)])
                delay_ms = max(0, int(round(float(offset) * 1000)))
                label = f"sfx{idx}"
                filters.append(f"[{next_input}:a]volume=0.72,adelay={delay_ms}:all=1[{label}]")
                audio_labels.append(f"[{label}]")
                next_input += 1

        filters.append(f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:duration=first:dropout_transition=2[aout]")
        run_command([
            *cmd,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]", "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(out_path),
        ])
        return
    run_command([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-vf", vf,
        "-map", "0:v", "-map", "1:a", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(out_path),
    ])


def _cleanup_intermediate(project_dir: Path, audio_dir: Path, clips_dir: Path, merged_path: Path) -> None:
    for path in [audio_dir, clips_dir]:
        if path.exists():
            shutil.rmtree(path)
    for path in [
        merged_path,
        merged_path.with_suffix(".txt"),
        (project_dir / "voice.audio.txt"),
    ]:
        if path.exists():
            path.unlink()
