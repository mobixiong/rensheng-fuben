from pathlib import Path

from .errors import RenderError
from .paths import ROOT, WORKSPACE


AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
BGM_DIRS = [ROOT / "assets" / "bgm", WORKSPACE / "bgm"]
SFX_DIR = ROOT / "assets" / "sfx"
WORKSPACE_SFX_DIR = WORKSPACE / "sfx"
DEFAULT_REVEAL_SFX = SFX_DIR / "gear.mp3"


def list_bgm_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for base in BGM_DIRS:
        base.mkdir(parents=True, exist_ok=True)
        for path in sorted(base.iterdir()):
            if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            option_id = path.name
            if base == WORKSPACE / "bgm":
                option_id = f"workspace/bgm/{path.name}"
            if option_id in seen:
                continue
            seen.add(option_id)
            options.append({
                "id": option_id,
                "name": path.stem,
                "filename": path.name,
            })
    return options


def list_intro_sfx_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    if DEFAULT_REVEAL_SFX.exists():
        options.append({
            "id": "default",
            "name": DEFAULT_REVEAL_SFX.stem,
            "filename": DEFAULT_REVEAL_SFX.name,
        })
    WORKSPACE_SFX_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(WORKSPACE_SFX_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        options.append({
            "id": f"workspace/sfx/{path.name}",
            "name": path.stem,
            "filename": path.name,
        })
    return options


def resolve_bgm_path(value: str | None) -> Path | None:
    raw = str(value or "").strip()
    if not raw or raw == "none":
        return None
    normalized = raw.replace("\\", "/").strip("/")
    if normalized.startswith("workspace/"):
        candidate = (WORKSPACE / normalized.removeprefix("workspace/")).resolve()
        try:
            candidate.relative_to(WORKSPACE.resolve())
        except ValueError as exc:
            raise RenderError("Invalid bgm path") from exc
        if candidate.exists():
            return candidate
    for base in BGM_DIRS:
        candidate = (base / normalized).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            continue
        if candidate.exists():
            return candidate
    raise RenderError(f"BGM not found: {raw}")


def resolve_intro_sfx_path(value: str | None, intro_template: str) -> Path | None:
    if intro_template == "none":
        return None
    raw = str(value or "default").strip()
    if not raw or raw == "none":
        return None
    if raw == "default":
        return DEFAULT_REVEAL_SFX if DEFAULT_REVEAL_SFX.exists() else None
    normalized = raw.replace("\\", "/").strip("/")
    if normalized.startswith("workspace/sfx/"):
        candidate = (WORKSPACE / normalized.removeprefix("workspace/")).resolve()
        try:
            candidate.relative_to(WORKSPACE_SFX_DIR.resolve())
        except ValueError as exc:
            raise RenderError("Invalid intro sfx path") from exc
        if candidate.exists() and candidate.suffix.lower() in AUDIO_SUFFIXES:
            return candidate
    candidate = (SFX_DIR / normalized).resolve()
    try:
        candidate.relative_to(SFX_DIR.resolve())
    except ValueError as exc:
        raise RenderError("Invalid intro sfx path") from exc
    if candidate.exists() and candidate.suffix.lower() in AUDIO_SUFFIXES:
        return candidate
    raise RenderError(f"Intro sfx not found: {raw}")
