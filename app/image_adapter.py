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

from .paths import PROJECTS_DIR, ROOT, WORKSPACE


IMAGE_PROMPT_PATH = ROOT / "prompts" / "image_style.md"
DEFAULT_LLM_BASE_URL = "http://43.131.249.187:3000/v1"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
MISSING_API_KEY_MESSAGE = "密钥未填写，密钥是群号"


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
IMAGE_QUOTA_SUGGESTION = "图片接口额度不足或触发限流，请更换可用 Key、降低并发，或等待额度恢复后重试。"


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
    quota_text = " ".join([message or "", code or "", error_type or ""]).lower()
    if status_code == 429 or "quota" in quota_text or "rate limit" in quota_text or "too many requests" in quota_text:
        return ImageError(
            f"图片接口额度不足或限流：{message or raw_detail}",
            code=code or f"http_{status_code}",
            category="quota",
            status_code=status_code,
            suggestion=IMAGE_QUOTA_SUGGESTION,
        )
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
            base_url=(payload.get("base_url") or os.getenv("IMAGE_BASE_URL") or DEFAULT_LLM_BASE_URL).strip(),
            api_key=(payload.get("api_key") or os.getenv("IMAGE_API_KEY") or "").strip(),
            model=(payload.get("model") or os.getenv("IMAGE_MODEL") or DEFAULT_IMAGE_MODEL).strip(),
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
    shot_prompt = str(shot.get("image_prompt") or "").strip()
    parts = [
        base,
        "当前故事整体风格补充：",
        str(story.get("style_preset") or ""),
    ]
    if shot_prompt:
        parts.extend([
            "图片提示词（最高优先级，生图唯一画面内容来源）：",
            shot_prompt,
            "请以这条图片提示词为准，不扩写未提供的画面内容。",
        ])
    else:
        parts.extend([
            "当前分镜信息：",
            f"口播：{shot.get('voiceover', '')}",
            f"画面描述：{shot.get('visual', '')}",
        ])
    reference_asset = shot.get("primary_reference_asset")
    if isinstance(reference_asset, dict) and reference_asset.get("name"):
        tags = reference_asset.get("tags") if isinstance(reference_asset.get("tags"), list) else []
        reference_lines = [
            f"主参考图：{reference_asset.get('name')}",
            f"类型：{reference_asset.get('type') or 'other'}",
        ]
        if reference_asset.get("description"):
            reference_lines.append(f"参考图描述：{reference_asset.get('description')}")
        if tags:
            reference_lines.append(f"标签：{'，'.join(str(tag) for tag in tags if str(tag).strip())}")
        reference_lines.append("请优先参考这张图的核心人物/主体外观，不要把参考图中的无关背景强行带入当前镜头。")
        parts.extend([
            "单主参考图锚定：",
            "\n".join(reference_lines),
        ])
    parts.append(f"请生成一张{ratio_label}分镜图。画面中不要出现可读文字、字幕、Logo、水印、二维码、品牌名或界面文字。")
    return "\n\n".join(parts)



def _workspace_project_id(value: Any) -> str:
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw or raw == "images":
        return ""
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} or ":" in part for part in parts):
        return ""
    return "/".join(parts)


def _workspace_project_ref(project_id: str) -> str:
    if project_id.startswith("projects/"):
        return project_id
    if (PROJECTS_DIR / project_id).exists():
        return f"projects/{project_id}"
    return project_id


def _public_project_id(project_ref: str) -> str:
    if project_ref.startswith("projects/"):
        return project_ref[len("projects/"):]
    return project_ref



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
    if not cfg.api_key:
        raise ImageError(
            MISSING_API_KEY_MESSAGE,
            code="missing_api_key",
            category="auth",
        )
    if not cfg.base_url or not cfg.model:
        raise ImageError("Image base_url/model is required", code="missing_config", category="config")
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
    project_ref = _workspace_project_ref(project_id)
    public_project_id = _public_project_id(project_ref)
    image_dir = WORKSPACE / project_ref / "images"
    workspace_url = f"/workspace/{project_ref}"
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise ImageError("story.shots must be a non-empty array")

    updated = json.loads(json.dumps(story, ensure_ascii=False))
    updated["project_id"] = public_project_id
    updated["image_size"] = cfg.size
    updated_shots = updated["shots"]
    for idx, shot in enumerate(updated_shots, 1):
        shot["image_size"] = cfg.size
        prompt = build_shot_image_prompt(updated, shot, fixed_prompt, cfg.size)
        out_path = image_dir / f"shot_{idx:02d}.png"
        generate_image(prompt, cfg, out_path)
        shot["image_path"] = str(out_path.resolve())
        shot["image_url"] = f"{workspace_url}/images/shot_{idx:02d}.png"
        shot["resolved_image_prompt"] = prompt
    return updated


def _safe_filename_suffix(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    safe = "".join(char if char in allowed else "_" for char in raw)
    if safe and not safe.startswith("_"):
        safe = f"_{safe}"
    return safe[:80]


def generate_one_story_image(
    story: dict[str, Any],
    shot_index: int,
    cfg: ImageConfig,
    fixed_prompt: str | None = None,
    *,
    filename_suffix: str = "",
) -> dict[str, Any]:
    shots = story.get("shots") or []
    if not isinstance(shots, list) or not shots:
        raise ImageError("story.shots must be a non-empty array")
    if shot_index < 0 or shot_index >= len(shots):
        raise ImageError("shot_index out of range")

    project_id = _workspace_project_id(story.get("project_id"))
    if not project_id:
        project_id = time.strftime("img_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    project_ref = _workspace_project_ref(project_id)
    public_project_id = _public_project_id(project_ref)
    image_dir = WORKSPACE / project_ref / "images"
    workspace_url = f"/workspace/{project_ref}"

    updated = json.loads(json.dumps(story, ensure_ascii=False))
    updated["project_id"] = public_project_id
    updated["image_size"] = cfg.size
    shot = updated["shots"][shot_index]
    shot["image_size"] = cfg.size
    prompt = build_shot_image_prompt(updated, shot, fixed_prompt, cfg.size)
    filename = f"shot_{shot_index + 1:02d}{_safe_filename_suffix(filename_suffix)}.png"
    out_path = image_dir / filename
    generate_image(prompt, cfg, out_path)
    shot["image_path"] = str(out_path.resolve())
    shot["image_url"] = f"{workspace_url}/images/{filename}"
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
