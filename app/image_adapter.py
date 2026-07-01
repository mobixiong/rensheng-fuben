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

from .paths import ROOT, WORKSPACE


IMAGE_PROMPT_PATH = ROOT / "prompts" / "image_style.md"


class ImageError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "",
        category: str = "unknown",
        status_code: int | None = None,
        suggestion: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.category = category
        self.status_code = status_code
        self.suggestion = suggestion

    def to_detail(self) -> dict[str, Any]:
        detail = {
            "message": self.message,
            "category": self.category,
            "code": self.code,
        }
        if self.status_code:
            detail["status_code"] = self.status_code
        if self.suggestion:
            detail["suggestion"] = self.suggestion
        return detail


PROMPT_POLICY_SUGGESTION = "请修改该镜头的口播、画面描述或图片提示词，降低暴力、血腥、敏感等表达后重试。"


def _extract_provider_error(raw: str) -> tuple[str, str, str]:
    message = raw.strip()
    code = ""
    error_type = ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return message, code, error_type
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or message)
            code = str(error.get("code") or "")
            error_type = str(error.get("type") or "")
        else:
            message = str(data.get("message") or data.get("detail") or message)
            code = str(data.get("code") or "")
            error_type = str(data.get("type") or "")
    return message.strip(), code.strip(), error_type.strip()


def _is_prompt_policy_error(message: str, code: str = "", error_type: str = "") -> bool:
    text = " ".join([message or "", code or "", error_type or ""]).lower()
    english_markers = (
        "content_policy_violation",
        "policy_violation",
        "content policy",
        "safety policy",
        "safety system",
        "moderation",
        "blocked",
        "unsafe",
        "sensitive",
    )
    chinese_markers = ("违反", "不合规", "防护限制", "内容安全", "安全策略", "敏感", "违规", "审核")
    return any(marker in text for marker in english_markers) or any(marker in message for marker in chinese_markers)


def classify_image_http_error(status_code: int, raw_detail: str) -> ImageError:
    message, code, error_type = _extract_provider_error(raw_detail)
    if _is_prompt_policy_error(message, code, error_type):
        return ImageError(
            f"提示词被内容安全策略拦截：{message}",
            code=code or f"http_{status_code}",
            category="prompt_policy",
            status_code=status_code,
            suggestion=PROMPT_POLICY_SUGGESTION,
        )
    return ImageError(
        f"Image HTTP {status_code}: {message or raw_detail}",
        code=code or f"http_{status_code}",
        category="request",
        status_code=status_code,
    )


@dataclass
class ImageConfig:
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "9:16"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ImageConfig":
        return cls(
            provider=(payload.get("provider") or os.getenv("IMAGE_PROVIDER") or "openai").strip(),
            base_url=(payload.get("base_url") or os.getenv("IMAGE_BASE_URL") or "").strip(),
            api_key=(payload.get("api_key") or os.getenv("IMAGE_API_KEY") or "").strip(),
            model=(payload.get("model") or os.getenv("IMAGE_MODEL") or "").strip(),
            size=(payload.get("size") or os.getenv("IMAGE_SIZE") or "9:16").strip(),
        )


def load_image_prompt() -> str:
    return IMAGE_PROMPT_PATH.read_text(encoding="utf-8")


def _image_ratio_label(size: str) -> str:
    value = str(size or "").strip()
    if value in {"16:9", "16 / 9"}:
        return "横屏16:9"
    if value in {"1:1", "1 / 1"}:
        return "正方形1:1"
    return "竖屏9:16"


def build_shot_image_prompt(
    story: dict[str, Any],
    shot: dict[str, Any],
    fixed_prompt: str | None = None,
    size: str = "9:16",
) -> str:
    base = fixed_prompt or load_image_prompt()
    ratio_label = _image_ratio_label(size or shot.get("image_size") or story.get("image_size") or "9:16")
    return "\n\n".join([
        base,
        "当前故事整体风格补充：",
        str(story.get("style_preset") or ""),
        "当前分镜信息：",
        f"口播：{shot.get('voiceover', '')}",
        f"画面描述：{shot.get('visual', '')}",
        f"补充提示词：{shot.get('image_prompt', '')}",
        f"请生成一张{ratio_label}分镜图。画面中不要出现可读文字、字幕、Logo、水印、二维码、品牌名或界面文字。",
    ])


def _workspace_project_id(value: Any) -> str:
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw or raw == "images":
        return ""
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} or ":" in part for part in parts):
        return ""
    return "/".join(parts)


def _endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1/images/generations") or clean.endswith("/images/generations"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/images/generations"
    return f"{clean}/v1/images/generations"


def _download(url: str, out_path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "RenshengFuben/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        out_path.write_bytes(resp.read())


def _openai_image_response(prompt: str, cfg: ImageConfig, timeout: int = 180) -> dict[str, Any]:
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:1000]
        raise classify_image_http_error(exc.code, detail) from exc
    except Exception as exc:
        raise ImageError(f"Image request failed: {exc}", category="network") from exc


def _openai_image(prompt: str, cfg: ImageConfig, out_path: Path) -> None:
    data = _openai_image_response(prompt, cfg)
    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        out_path.write_bytes(base64.b64decode(item["b64_json"]))
        return
    if item.get("url"):
        _download(item["url"], out_path)
        return
    raise ImageError(f"Unexpected image response: {str(data)[:1000]}")


def generate_image(prompt: str, cfg: ImageConfig, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    provider = (cfg.provider or "openai").lower()
    if provider in {"openai", "openai_compatible", "compatible"}:
        _openai_image(prompt, cfg, out_path)
    else:
        raise ImageError(f"Unsupported image provider: {cfg.provider}")


def generate_story_images(story: dict[str, Any], cfg: ImageConfig, fixed_prompt: str | None = None) -> dict[str, Any]:
    project_id = _workspace_project_id(story.get("project_id"))
    if not project_id:
        project_id = time.strftime("img_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    image_dir = WORKSPACE / project_id / "images"
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise ImageError("story.shots must be a non-empty array")

    updated = json.loads(json.dumps(story, ensure_ascii=False))
    updated.setdefault("project_id", project_id)
    updated["image_size"] = cfg.size
    updated_shots = updated["shots"]
    for idx, shot in enumerate(updated_shots, 1):
        shot["image_size"] = cfg.size
        prompt = build_shot_image_prompt(updated, shot, fixed_prompt, cfg.size)
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

    project_id = _workspace_project_id(story.get("project_id"))
    if not project_id:
        project_id = time.strftime("img_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    image_dir = WORKSPACE / project_id / "images"

    updated = json.loads(json.dumps(story, ensure_ascii=False))
    updated["project_id"] = project_id
    updated["image_size"] = cfg.size
    shot = updated["shots"][shot_index]
    shot["image_size"] = cfg.size
    prompt = build_shot_image_prompt(updated, shot, fixed_prompt, cfg.size)
    out_path = image_dir / f"shot_{shot_index + 1:02d}.png"
    generate_image(prompt, cfg, out_path)
    shot["image_path"] = str(out_path.resolve())
    shot["image_url"] = f"/workspace/{project_id}/images/shot_{shot_index + 1:02d}.png"
    shot["resolved_image_prompt"] = prompt
    return updated


def test_image_connection(cfg: ImageConfig) -> dict[str, Any]:
    provider = (cfg.provider or "openai").lower()
    if provider not in {"openai", "openai_compatible", "compatible"}:
        raise ImageError(f"Unsupported image provider: {cfg.provider}")
    data = _openai_image_response(
        "连接测试：一张极简白底蓝色圆点图，不要文字、Logo、水印。",
        cfg,
        timeout=90,
    )
    item = (data.get("data") or [{}])[0]
    if not (item.get("b64_json") or item.get("url")):
        raise ImageError(f"Unexpected image response: {str(data)[:1000]}")
    return {
        "ok": True,
        "provider": cfg.provider,
        "model": cfg.model,
        "returned": "b64_json" if item.get("b64_json") else "url",
    }
