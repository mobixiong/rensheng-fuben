import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IMAGE_PROMPT_PATH = ROOT / "prompts" / "image_style.md"
WORKSPACE = ROOT / "workspace"


class ImageError(RuntimeError):
    pass


@dataclass
class ImageConfig:
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "1024x1792"
    secure_1psid: str = ""
    secure_1psidts: str = ""
    proxy: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ImageConfig":
        return cls(
            provider=(payload.get("provider") or os.getenv("IMAGE_PROVIDER") or "openai").strip(),
            base_url=(payload.get("base_url") or os.getenv("IMAGE_BASE_URL") or "").strip(),
            api_key=(payload.get("api_key") or os.getenv("IMAGE_API_KEY") or "").strip(),
            model=(payload.get("model") or os.getenv("IMAGE_MODEL") or "").strip(),
            size=(payload.get("size") or os.getenv("IMAGE_SIZE") or "1024x1792").strip(),
            secure_1psid=(payload.get("secure_1psid") or os.getenv("GEMINI_SECURE_1PSID") or "").strip(),
            secure_1psidts=(payload.get("secure_1psidts") or os.getenv("GEMINI_SECURE_1PSIDTS") or "").strip(),
            proxy=(payload.get("proxy") or os.getenv("GEMINI_PROXY") or "").strip() or None,
        )


def load_image_prompt() -> str:
    return IMAGE_PROMPT_PATH.read_text(encoding="utf-8")


def build_shot_image_prompt(story: dict[str, Any], shot: dict[str, Any], fixed_prompt: str | None = None) -> str:
    base = fixed_prompt or load_image_prompt()
    return "\n\n".join([
        base,
        "STYLE_PRESET:",
        str(story.get("style_preset") or ""),
        "SHOT:",
        f"voiceover: {shot.get('voiceover', '')}",
        f"visual: {shot.get('visual', '')}",
        f"image_prompt: {shot.get('image_prompt', '')}",
        "Return one clean vertical 9:16 illustration. Do not draw readable text.",
    ])


def _endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1/images/generations") or clean.endswith("/images/generations"):
        return clean
    return f"{clean}/v1/images/generations"


def _download(url: str, out_path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "RenshengFuben/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        out_path.write_bytes(resp.read())


def _openai_image(prompt: str, cfg: ImageConfig, out_path: Path) -> None:
    if not cfg.base_url or not cfg.api_key or not cfg.model:
        raise ImageError("Image base_url/api_key/model is required")
    body = {
        "model": cfg.model,
        "prompt": prompt,
        "size": cfg.size,
        "n": 1,
    }
    req = urllib.request.Request(
        _endpoint(cfg.base_url),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:1000]
        raise ImageError(f"Image HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ImageError(f"Image request failed: {exc}") from exc

    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        out_path.write_bytes(base64.b64decode(item["b64_json"]))
        return
    if item.get("url"):
        _download(item["url"], out_path)
        return
    raise ImageError(f"Unexpected image response: {str(data)[:1000]}")


def _gemini_image(prompt: str, cfg: ImageConfig, out_path: Path) -> None:
    if not cfg.secure_1psid:
        raise ImageError("Gemini WebAPI requires __Secure-1PSID")
    try:
        from gemini_webapi import GeminiClient
    except Exception as exc:
        raise ImageError("gemini_webapi is not installed. Run: pip install gemini_webapi") from exc

    async def _run() -> None:
        client = GeminiClient(cfg.secure_1psid, cfg.secure_1psidts or None, proxy=cfg.proxy)
        await client.init(timeout=30, auto_close=True, close_delay=5, auto_refresh=True)
        response = await client.generate_content(prompt)
        if not response.images:
            raise ImageError("Gemini returned no images")
        await response.images[0].save(path=str(out_path.parent), filename=out_path.name, verbose=False)

    asyncio.run(_run())


def generate_image(prompt: str, cfg: ImageConfig, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    provider = (cfg.provider or "openai").lower()
    if provider in {"openai", "openai_compatible", "compatible"}:
        _openai_image(prompt, cfg, out_path)
    elif provider in {"gemini", "gemini_webapi", "hanaoka", "hanaokayuzu"}:
        _gemini_image(prompt, cfg, out_path)
    else:
        raise ImageError(f"Unsupported image provider: {cfg.provider}")


def generate_story_images(story: dict[str, Any], cfg: ImageConfig, fixed_prompt: str | None = None) -> dict[str, Any]:
    project_id = story.get("project_id") if isinstance(story.get("project_id"), str) else "images"
    if not project_id or project_id == "images":
        project_id = time.strftime("img_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    image_dir = WORKSPACE / project_id / "images"
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise ImageError("story.shots must be a non-empty array")

    updated = json.loads(json.dumps(story, ensure_ascii=False))
    updated.setdefault("project_id", project_id)
    updated_shots = updated["shots"]
    for idx, shot in enumerate(updated_shots, 1):
        prompt = build_shot_image_prompt(updated, shot, fixed_prompt)
        out_path = image_dir / f"shot_{idx:02d}.png"
        generate_image(prompt, cfg, out_path)
        shot["image_path"] = str(out_path.resolve())
        shot["image_url"] = f"/workspace/{project_id}/images/shot_{idx:02d}.png"
        shot["resolved_image_prompt"] = prompt
    return updated


def generate_one_story_image(story: dict[str, Any], shot_index: int, cfg: ImageConfig, fixed_prompt: str | None = None) -> dict[str, Any]:
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise ImageError("story.shots must be a non-empty array")
    if shot_index < 0 or shot_index >= len(shots):
        raise ImageError("shot_index out of range")

    project_id = story.get("project_id") if isinstance(story.get("project_id"), str) else ""
    if not project_id:
        project_id = time.strftime("img_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    image_dir = WORKSPACE / project_id / "images"

    updated = json.loads(json.dumps(story, ensure_ascii=False))
    updated["project_id"] = project_id
    shot = updated["shots"][shot_index]
    prompt = build_shot_image_prompt(updated, shot, fixed_prompt)
    out_path = image_dir / f"shot_{shot_index + 1:02d}.png"
    generate_image(prompt, cfg, out_path)
    shot["image_path"] = str(out_path.resolve())
    shot["image_url"] = f"/workspace/{project_id}/images/shot_{shot_index + 1:02d}.png"
    shot["resolved_image_prompt"] = prompt
    return updated
