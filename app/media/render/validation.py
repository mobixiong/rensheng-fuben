from typing import Any

from app.core.errors import RenderError


def _has_image(shot: Any) -> bool:
    return isinstance(shot, dict) and bool(str(shot.get("image_url") or shot.get("image_path") or "").strip())


def validate_ready_for_render(story: dict[str, Any]) -> None:
    shots = story.get("shots") if isinstance(story, dict) else None
    if not isinstance(shots, list) or not shots:
        raise RenderError("请先完成分镜，再渲染 MP4。")

    missing = [index + 1 for index, shot in enumerate(shots) if not _has_image(shot)]
    if missing:
        preview = "、".join(str(index) for index in missing[:8])
        suffix = " 等" if len(missing) > 8 else ""
        raise RenderError(f"还有 {len(missing)} 个分镜图片未生成：第 {preview}{suffix} 个。请先生成完所有分镜图片。")

    cover = story.get("cover") if isinstance(story.get("cover"), dict) else None
    if not cover:
        raise RenderError("请先在分镜工作台选择一张图片作为封面，再渲染 MP4。")

    try:
        source_index = int(cover.get("source_shot_index"))
    except (TypeError, ValueError):
        raise RenderError("封面未正确选择，请先在分镜工作台重新选择封面。") from None

    if source_index < 0 or source_index >= len(shots):
        raise RenderError("封面对应的分镜不存在，请先重新选择封面。")

    if not _has_image(cover) and not _has_image(shots[source_index]):
        raise RenderError("封面图片未生成，请先选择一张已生成的分镜图片作为封面。")
