import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from .paths import REFERENCE_COLLECTIONS_DIR


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_REFERENCE_IMAGE_BYTES = 30 * 1024 * 1024
REFERENCE_ASSET_TYPES = {"character", "scene", "prop", "costume", "style", "other"}


class ReferenceAssetError(ValueError):
    pass


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _slug(value: str, fallback: str = "asset") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", str(value or "")).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:48] or fallback


def safe_collection_id(value: Any, name: str = "") -> str:
    raw = str(value or "").strip()
    if raw and not re.search(r'[<>:"/\\|?*\x00-\x1f]', raw) and ".." not in raw:
        return raw[:120]
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{_slug(name, 'collection')}_{uuid.uuid4().hex[:6]}"


def _collection_dir(collection_id: str) -> Path:
    return REFERENCE_COLLECTIONS_DIR / safe_collection_id(collection_id)


def _metadata_path(collection_id: str) -> Path:
    return _collection_dir(collection_id) / "metadata.json"


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _public_collection(data: dict[str, Any]) -> dict[str, Any]:
    public = json.loads(json.dumps(data, ensure_ascii=False))
    for asset in public.get("assets", []):
        asset.pop("image_path", None)
    return public


def _read_collection(collection_id: str) -> dict[str, Any]:
    path = _metadata_path(collection_id)
    if not path.exists():
        raise FileNotFoundError(collection_id)
    return json.loads(path.read_text(encoding="utf-8"))


def get_collection(collection_id: str) -> dict[str, Any]:
    return _public_collection(_read_collection(collection_id))


def list_collections() -> list[dict[str, Any]]:
    REFERENCE_COLLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(REFERENCE_COLLECTIONS_DIR.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_dir():
            continue
        metadata = path / "metadata.json"
        if not metadata.exists():
            continue
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
        except Exception:
            continue
        public = _public_collection(data)
        public["asset_count"] = len(public.get("assets") or [])
        items.append(public)
    return items


def create_collection(name: str, description: str = "") -> dict[str, Any]:
    collection_id = safe_collection_id("", name)
    now = _now()
    data = {
        "collection_id": collection_id,
        "name": str(name or "").strip() or "未命名集合",
        "description": str(description or "").strip(),
        "created_at": now,
        "updated_at": now,
        "assets": [],
    }
    _write_json_atomic(_metadata_path(collection_id), data)
    return _public_collection(data)


def _parse_tags(value: str) -> list[str]:
    raw = re.split(r"[,，\n]+", str(value or ""))
    return [item.strip() for item in raw if item.strip()][:12]


def _safe_image_filename(filename: str, asset_name: str) -> str:
    raw = Path(str(filename or "image")).name
    suffix = Path(raw).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise ReferenceAssetError("只支持 png、jpg、jpeg、webp 图片")
    stem = _slug(asset_name or Path(raw).stem, "reference")
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}_{stem}{suffix}"


def _save_image(source: BinaryIO, target: Path) -> None:
    total = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_REFERENCE_IMAGE_BYTES:
                    raise ReferenceAssetError("参考图不能超过 30MB")
                out.write(chunk)
        if total <= 0:
            raise ReferenceAssetError("上传的参考图为空")
    except Exception:
        target.unlink(missing_ok=True)
        raise


def add_asset(
    collection_id: str,
    *,
    filename: str,
    source: BinaryIO,
    name: str,
    asset_type: str = "character",
    description: str = "",
    tags: str = "",
) -> dict[str, Any]:
    data = _read_collection(collection_id)
    collection_id = data["collection_id"]
    target_dir = _collection_dir(collection_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_image_filename(filename, name)
    target = (target_dir / safe_name).resolve()
    try:
        target.relative_to(target_dir.resolve())
    except ValueError as exc:
        raise ReferenceAssetError("Invalid reference image path") from exc
    _save_image(source, target)

    asset_id = f"asset_{uuid.uuid4().hex[:10]}"
    normalized_type = str(asset_type or "character").strip()
    if normalized_type not in REFERENCE_ASSET_TYPES:
        normalized_type = "other"
    asset = {
        "id": asset_id,
        "name": str(name or "").strip() or Path(filename or "参考图").stem,
        "type": normalized_type,
        "description": str(description or "").strip(),
        "tags": _parse_tags(tags),
        "filename": safe_name,
        "image_path": str(target),
        "image_url": f"/workspace/reference_collections/{collection_id}/{safe_name}",
        "created_at": _now(),
    }
    data.setdefault("assets", []).append(asset)
    data["updated_at"] = _now()
    _write_json_atomic(_metadata_path(collection_id), data)
    return {"collection": _public_collection(data), "asset": _public_collection({"assets": [asset]})["assets"][0]}


def delete_asset(collection_id: str, asset_id: str) -> dict[str, Any]:
    data = _read_collection(collection_id)
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    kept = []
    removed: dict[str, Any] | None = None
    for asset in assets:
        if isinstance(asset, dict) and asset.get("id") == asset_id:
            removed = asset
            continue
        kept.append(asset)
    if removed is None:
        raise FileNotFoundError(asset_id)
    data["assets"] = kept
    data["updated_at"] = _now()
    _write_json_atomic(_metadata_path(data["collection_id"]), data)
    image_path = Path(str(removed.get("image_path") or ""))
    if image_path.exists():
        try:
            image_path.relative_to(_collection_dir(data["collection_id"]).resolve())
            image_path.unlink(missing_ok=True)
        except Exception:
            pass
    return _public_collection(data)


def delete_collection(collection_id: str) -> dict[str, Any]:
    safe_id = safe_collection_id(collection_id)
    target = _collection_dir(safe_id).resolve()
    root = REFERENCE_COLLECTIONS_DIR.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ReferenceAssetError("Invalid collection path") from exc
    if not target.exists():
        raise FileNotFoundError(safe_id)
    shutil.rmtree(target)
    return {"ok": True, "collection_id": safe_id}


def assets_for_llm(collection_id: str) -> list[dict[str, Any]]:
    data = _read_collection(collection_id)
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    result: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        result.append({
            "id": asset.get("id") or "",
            "name": asset.get("name") or "",
            "type": asset.get("type") or "other",
            "description": asset.get("description") or "",
            "tags": asset.get("tags") if isinstance(asset.get("tags"), list) else [],
            "image_url": asset.get("image_url") or "",
        })
    return [asset for asset in result if asset["id"] and asset["name"]]


def resolve_asset(collection_id: str, asset_id: str) -> dict[str, Any] | None:
    data = _read_collection(collection_id)
    for asset in data.get("assets") or []:
        if isinstance(asset, dict) and asset.get("id") == asset_id:
            return asset
    return None
