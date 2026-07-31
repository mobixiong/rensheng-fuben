from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.media.render.constants import H, W, render_size

DEFAULT_STYLE = (
    "中国网络科普动画风格，赛璐璐着色，粗黑描边，干净利落的矢量线条，"
    "2D平面动画，高对比阴影，高饱和色调，少量关键词花字。主角是无脸圆形白色光头角色，"
    "极简点状眼睛，夸张眉毛，表情包风格，穿连帽衫或制服，Q版但不过度幼稚。"
)

def _font_path() -> str:
    for p in [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\Dengb.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    ]:
        if Path(p).exists():
            return p
    return ""

FONT_PATH = _font_path()

def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.truetype(FONT_PATH, size=size) if FONT_PATH else ImageFont.load_default()

def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text:
        test = cur + ch
        box = draw.textbbox((0, 0), test, font=font)
        if box[2] - box[0] > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines

def _palette(idx: int) -> tuple[str, str, str]:
    palettes = [
        ("#ffcc33", "#30c5ff", "#ff5a5f"),
        ("#62d26f", "#fff176", "#1e88e5"),
        ("#f06292", "#4dd0e1", "#ffd54f"),
        ("#7e57c2", "#ff7043", "#80cbc4"),
        ("#ef5350", "#ffee58", "#42a5f5"),
        ("#26c6da", "#ab47bc", "#ffee58"),
    ]
    return palettes[idx % len(palettes)]

def _hex_mix(a: str, b: str, t: float) -> tuple[int, int, int]:
    return tuple(int(int(a[i : i + 2], 16) * (1 - t) + int(b[i : i + 2], 16) * t) for i in (1, 3, 5))

def _draw_character(draw: ImageDraw.ImageDraw, x: int, y: int, accent: str, mood: int) -> None:
    scale = 1.05
    lw = 10
    head_r = int(105 * scale)
    body_w = int(190 * scale)
    body_h = int(245 * scale)
    draw.ellipse((x - head_r, y - head_r, x + head_r, y + head_r), fill="#ffffff", outline="#111111", width=lw)
    eye_y = y - 15
    draw.ellipse((x - 46, eye_y, x - 24, eye_y + 22), fill="#111111")
    draw.ellipse((x + 24, eye_y, x + 46, eye_y + 22), fill="#111111")
    tilt = (mood % 3 - 1) * 12
    draw.line((x - 62, eye_y - 35 + tilt, x - 14, eye_y - 45), fill="#111111", width=lw)
    draw.line((x + 14, eye_y - 45, x + 62, eye_y - 35 - tilt), fill="#111111", width=lw)
    top = y + 105
    draw.rounded_rectangle((x - body_w // 2, top, x + body_w // 2, top + body_h), radius=45, fill=accent, outline="#111111", width=lw)
    draw.line((x - body_w // 2, top + 55, x - 200, top + 170), fill="#111111", width=lw)
    draw.line((x + body_w // 2, top + 55, x + 200, top + 145), fill="#111111", width=lw)
    draw.line((x - 55, top + body_h, x - 100, top + body_h + 170), fill="#111111", width=lw)
    draw.line((x + 55, top + body_h, x + 100, top + body_h + 170), fill="#111111", width=lw)

def render_placeholder_image(
    shot: dict[str, Any],
    out_path: Path,
    idx: int,
    title: str,
    size: tuple[int, int] | None = None,
) -> None:
    W, H = size or render_size()
    a, b, c = _palette(idx)
    img = Image.new("RGB", (W, H), "#f7f8fb")
    draw = ImageDraw.Draw(img)
    for y in range(0, H, 12):
        draw.rectangle((0, y, W, y + 12), fill=_hex_mix(a, b, y / H))
    overlay = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((-200, 160, 450, 820), fill=(255, 255, 255, 55))
    od.ellipse((700, 930, 1280, 1520), fill=(255, 255, 255, 45))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((110, 460, 970, 920), radius=50, fill="#ffffff", outline="#111111", width=9)
    for i in range(4):
        x = 180 + i * 190
        y = 590 - i * 24
        draw.ellipse((x, y, x + 145, y + 120), fill=[a, b, c, "#ffffff"][i], outline="#111111", width=7)
    _draw_character(draw, 540, 1040, c, idx)

    title_font = _font(58)
    punch_font = _font(90)
    body_font = _font(42)
    draw.rounded_rectangle((80, 90, 1000, 282), radius=35, fill="#ffffff", outline="#111111", width=8)
    lines = _wrap(draw, title, title_font, 830)[:2]
    for line_i, line in enumerate(lines):
        draw.text((125, 125 + line_i * 70), line, font=title_font, fill="#111111")

    punch = str(shot.get("punch") or shot.get("keyword") or f"镜头 {idx + 1}")
    box = draw.textbbox((0, 0), punch, font=punch_font, stroke_width=5)
    draw.text(((W - (box[2] - box[0])) // 2, 330), punch, font=punch_font, fill="#ffffff", stroke_fill="#111111", stroke_width=5)

    visual = str(shot.get("visual") or shot.get("image_prompt") or shot.get("voiceover") or "")
    draw.rounded_rectangle((70, 1540, 1010, 1765), radius=30, fill="#ffffff", outline="#111111", width=7)
    y = 1580
    for line in _wrap(draw, visual, body_font, 860)[:3]:
        draw.text((110, y), line, font=body_font, fill="#111111")
        y += 58
    draw.text((72, 1840), f"SHOT {idx + 1:02d}", font=_font(34), fill="#111111")
    img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=105, threshold=3)).save(out_path, quality=95)

