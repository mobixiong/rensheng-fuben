import asyncio
import json
import math
import os
import shutil
import subprocess
import textwrap
from dataclasses import dataclass, asdict
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
ASSETS = OUT / "assets"
CLIPS = OUT / "clips"
W, H = 1080, 1920
FPS = 30


STYLE_PRESET = (
    "中国网络科普动画风格，赛璐璐着色，粗黑描边，干净利落的矢量线条，"
    "2D平面动画，高对比阴影，高饱和色调，少量关键词花字。主角是无脸圆形白色光头角色，"
    "极简点状眼睛，夸张眉毛，表情包风格，穿连帽衫或制服，Q版但不过度幼稚。"
)


@dataclass
class Shot:
    id: int
    voiceover: str
    visual: str
    punch: str
    palette: tuple[str, str, str]
    image_prompt: str
    video_prompt: str
    start: float = 0.0
    end: float = 0.0


def build_story() -> list[Shot]:
    base = "2D Chinese internet explainer animation, thick black outline, faceless white round head character"
    return [
        Shot(1, "今天体验的人生副本是：自助餐成瘾者回本哥的人生。", "他站在自助餐门口，像要参加一场命运审判。", "副本开启", ("#ffcc33", "#30c5ff", "#ff5a5f"), base + ", buffet entrance", "dramatic push in"),
        Shot(2, "他的天赋很简单：看一眼价格，就能自动换算成多少只虾。", "价格牌变成巨大的虾子计数器，数字疯狂跳动。", "价格=虾", ("#62d26f", "#fff176", "#1e88e5"), base + ", price tag turns into shrimp counter", "numbers pop up"),
        Shot(3, "别人进店先找座位，他进店先扫描蛋白质密度。", "主角拿着雷达一样的餐盘，锁定牛排、三文鱼和烤生蚝。", "密度扫描", ("#f06292", "#4dd0e1", "#ffd54f"), base + ", buffet radar, steak salmon oysters", "radar sweep"),
        Shot(4, "第一轮，他假装优雅。第二轮，他开始战术夹菜。", "餐盘堆成小山，旁边出现作战路线图。", "战术夹菜", ("#7e57c2", "#ff7043", "#80cbc4"), base + ", tactical buffet plate mountain", "fast montage"),
        Shot(5, "第三轮，他已经不是在吃饭，而是在和店家的成本模型对抗。", "餐厅老板的成本公式浮在空中，主角举叉冲锋。", "成本对抗", ("#ff8a65", "#81c784", "#4fc3f7"), base + ", cost formula battle", "comic battle"),
        Shot(6, "他的胃发出警报，但他的大脑只显示四个字：还没回本。", "胃部警报灯闪烁，脑袋上弹出红色提示框。", "还没回本", ("#ef5350", "#ffee58", "#42a5f5"), base + ", stomach alarm, warning text", "warning flash"),
        Shot(7, "他开始研究饮料陷阱，宣布所有碳酸饮料都是资本的泡沫攻击。", "汽水泡泡变成攻击弹幕，主角用水杯盾牌格挡。", "泡沫攻击", ("#26c6da", "#ab47bc", "#ffee58"), base + ", soda bubbles attack", "bubble barrage"),
        Shot(8, "服务员问他要不要甜品，他沉默三秒，说：甜品不算食物，算结算漏洞。", "甜品区像游戏漏洞入口一样发光。", "结算漏洞", ("#ec407a", "#ffee58", "#66bb6a"), base + ", dessert portal glitch", "glitch glow"),
        Shot(9, "当他终于觉得自己赚了，手机健康软件弹出本日账单。", "手机屏幕展示热量、血糖和步数欠款。", "健康账单", ("#42a5f5", "#ffca28", "#ef5350"), base + ", phone health bill", "screen zoom"),
        Shot(10, "他回本了二十八块，却透支了未来三天的精神状态。", "主角瘫在椅子上，灵魂从身体里飘出一点点。", "赚28 亏3天", ("#bdbdbd", "#ff7043", "#26a69a"), base + ", exhausted character, soul leaving body", "slow drift"),
        Shot(11, "但第二天，他路过另一家自助餐，副本提示再次亮起。", "街角新自助餐招牌亮起，主角眼神重新坚定。", "再次进入", ("#ffa726", "#29b6f6", "#66bb6a"), base + ", new buffet sign lights up", "sign flicker"),
        Shot(12, "系统评价：你没有战胜自助餐，你只是成为了它的复购用户。", "结算面板打出评级，主角被会员卡光环笼罩。", "复购用户", ("#5c6bc0", "#ffca28", "#ef5350"), base + ", game result panel, membership card halo", "final title card"),
    ]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDERR:\n{proc.stderr[-3000:]}")


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return float(proc.stdout.strip())


async def synthesize_voice(text: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice="zh-CN-YunxiNeural", rate="+12%", volume="+0%")
    await communicate.save(str(out_path))


def font_path() -> str:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\Dengb.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return ""


FONT = font_path()


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if FONT:
        return ImageFont.truetype(FONT, size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text:
        test = cur + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def rounded_rect(draw: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_character(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float, accent: str, mood: int) -> None:
    lw = max(5, int(10 * scale))
    head_r = int(105 * scale)
    body_w = int(190 * scale)
    body_h = int(245 * scale)
    cx = x
    head_cy = y
    body_top = y + int(105 * scale)
    draw.ellipse((cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r), fill="#ffffff", outline="#111111", width=lw)
    eye_y = head_cy - int(15 * scale)
    draw.ellipse((cx - int(42 * scale), eye_y, cx - int(22 * scale), eye_y + int(20 * scale)), fill="#111111")
    draw.ellipse((cx + int(22 * scale), eye_y, cx + int(42 * scale), eye_y + int(20 * scale)), fill="#111111")
    brow_y = eye_y - int(35 * scale)
    tilt = int((mood % 3 - 1) * 12 * scale)
    draw.line((cx - int(58 * scale), brow_y + tilt, cx - int(12 * scale), brow_y - int(8 * scale)), fill="#111111", width=lw)
    draw.line((cx + int(12 * scale), brow_y - int(8 * scale), cx + int(58 * scale), brow_y - tilt), fill="#111111", width=lw)
    draw.rounded_rectangle((cx - body_w // 2, body_top, cx + body_w // 2, body_top + body_h), radius=int(45 * scale), fill=accent, outline="#111111", width=lw)
    draw.line((cx - body_w // 2, body_top + int(50 * scale), cx - int(190 * scale), body_top + int(170 * scale)), fill="#111111", width=lw)
    draw.line((cx + body_w // 2, body_top + int(50 * scale), cx + int(190 * scale), body_top + int(140 * scale)), fill="#111111", width=lw)
    draw.line((cx - int(55 * scale), body_top + body_h, cx - int(95 * scale), body_top + body_h + int(170 * scale)), fill="#111111", width=lw)
    draw.line((cx + int(55 * scale), body_top + body_h, cx + int(105 * scale), body_top + body_h + int(170 * scale)), fill="#111111", width=lw)


def draw_props(draw: ImageDraw.ImageDraw, shot: Shot) -> None:
    a, b, c = shot.palette
    if shot.id in {1, 11}:
        rounded_rect(draw, (130, 440, 950, 620), 35, a, "#111111", 8)
        draw.text((220, 485), "BUFFET", font=get_font(72), fill="#111111")
        draw.rectangle((180, 620, 900, 1040), fill="#f7f7f7", outline="#111111", width=8)
    elif shot.id in {2, 9, 12}:
        rounded_rect(draw, (235, 440, 845, 980), 45, "#ffffff", "#111111", 10)
        for i in range(4):
            draw.rectangle((300, 540 + i * 95, 780, 590 + i * 95), fill=[a, b, c, "#ffffff"][i % 4], outline="#111111", width=5)
    elif shot.id in {3, 4, 5}:
        for i in range(5):
            x = 170 + i * 170
            draw.ellipse((x, 590 - i * 24, x + 135, 720 - i * 24), fill=[a, b, c][i % 3], outline="#111111", width=7)
        draw.arc((170, 360, 910, 1100), 200, 340, fill="#111111", width=9)
    elif shot.id in {6, 10}:
        draw.polygon([(540, 390), (820, 880), (260, 880)], fill=a, outline="#111111")
        draw.line((540, 540, 540, 720), fill="#111111", width=22)
        draw.ellipse((525, 760, 555, 790), fill="#111111")
    elif shot.id == 7:
        for i in range(18):
            x = 105 + (i * 73) % 860
            y = 420 + (i * 109) % 620
            r = 28 + (i % 4) * 11
            draw.ellipse((x, y, x + r, y + r), fill="#ffffff", outline=[a, b, c][i % 3], width=6)
    else:
        rounded_rect(draw, (180, 480, 900, 880), 45, "#ffffff", "#111111", 8)
        draw.line((230, 610, 850, 610), fill=a, width=20)
        draw.line((230, 730, 700, 730), fill=b, width=20)


def render_shot(shot: Shot, out_path: Path) -> None:
    a, b, c = shot.palette
    img = Image.new("RGB", (W, H), "#f6f7fb")
    draw = ImageDraw.Draw(img)
    for y in range(0, H, 12):
        t = y / H
        r = int(int(a[1:3], 16) * (1 - t) + int(b[1:3], 16) * t)
        g = int(int(a[3:5], 16) * (1 - t) + int(b[3:5], 16) * t)
        bl = int(int(a[5:7], 16) * (1 - t) + int(b[5:7], 16) * t)
        draw.rectangle((0, y, W, y + 12), fill=(r, g, bl))

    # Subtle panel, not a card-based layout: it keeps readable visual density.
    overlay = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((-180, 180, 420, 780), fill=(255, 255, 255, 50))
    od.ellipse((720, 920, 1250, 1500), fill=(255, 255, 255, 45))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    draw_props(draw, shot)
    draw_character(draw, 540, 1000, 1.08, c, shot.id)

    title_font = get_font(58)
    punch_font = get_font(98)
    small_font = get_font(42)

    rounded_rect(draw, (80, 90, 1000, 285), 35, "#ffffff", "#111111", 8)
    draw.text((125, 125), "今天体验的人生副本是", font=title_font, fill="#111111")
    draw.text((125, 195), "自助餐成瘾者回本哥", font=title_font, fill="#111111")

    bbox = draw.textbbox((0, 0), shot.punch, font=punch_font, stroke_width=4)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 330), shot.punch, font=punch_font, fill="#ffffff", stroke_fill="#111111", stroke_width=5)

    lines = wrap_text(draw, shot.visual, small_font, 880)
    y = 1540
    rounded_rect(draw, (70, y - 38, 1010, y + 220), 30, "#ffffff", "#111111", 7)
    for line in lines[:4]:
        draw.text((110, y), line, font=small_font, fill="#111111")
        y += 58

    draw.text((72, 1840), f"SHOT {shot.id:02d}", font=get_font(34), fill="#111111")
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=105, threshold=3))
    img.save(out_path, quality=95)


def srt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ass_ts(sec: float) -> str:
    cs = int(round(sec * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_subtitles(shots: list[Shot], srt_path: Path, ass_path: Path) -> None:
    srt_blocks = []
    for idx, shot in enumerate(shots, 1):
        srt_blocks.append(f"{idx}\n{srt_ts(shot.start)} --> {srt_ts(shot.end)}\n{shot.voiceover}\n")
    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")

    font_name = "Microsoft YaHei"
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},54,&H00FFFFFF,&H000000FF,&H00111111,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,2,70,70,150,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for shot in shots:
        text = "\\N".join(textwrap.wrap(shot.voiceover, width=18))
        lines.append(f"Dialogue: 0,{ass_ts(shot.start)},{ass_ts(shot.end)},Default,,0,0,0,,{text}")
    ass_path.write_text("\n".join(lines), encoding="utf-8")


def allocate_timeline(shots: list[Shot], total_duration: float) -> None:
    weights = [max(8, len(s.voiceover)) for s in shots]
    total_weight = sum(weights)
    min_dur = 3.8
    raw = [total_duration * w / total_weight for w in weights]
    durs = [max(min_dur, r) for r in raw]
    scale = total_duration / sum(durs)
    durs = [d * scale for d in durs]
    cursor = 0.0
    for shot, dur in zip(shots, durs):
        shot.start = cursor
        cursor += dur
        shot.end = cursor
    shots[-1].end = total_duration


def make_clip(image_path: Path, out_path: Path, duration: float, idx: int) -> None:
    # Static image plus a tiny scale animation for the local demo render.
    frames = max(1, int(duration * FPS))
    zoom_expr = "1+0.035*on/{frames}".format(frames=frames)
    vf = (
        f"scale={W}:{H},"
        f"zoompan=z='{zoom_expr}':d={frames}:s={W}x{H}:fps={FPS},"
        "format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path)
    ])


def concat_clips(clips: list[Path], out_path: Path) -> Path:
    list_path = OUT / "clips.txt"
    content = "".join(f"file '{p.as_posix()}'\n" for p in clips)
    list_path.write_text(content, encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)])
    return list_path


def burn_final(video_path: Path, audio_path: Path, ass_path: Path, out_path: Path, duration: float) -> None:
    ass_arg = ass_path.resolve().as_posix().replace(":", "\\:")
    run([
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
        "-vf", f"ass='{ass_arg}'",
        "-map", "0:v", "-map", "1:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path)
    ])


def clean_dirs() -> None:
    OUT.mkdir(exist_ok=True)
    for d in (ASSETS, CLIPS):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)


def main() -> None:
    clean_dirs()
    shots = build_story()
    voice_text = "\n".join(s.voiceover for s in shots)
    voice_path = OUT / "voice.mp3"
    asyncio.run(synthesize_voice(voice_text, voice_path))
    audio_duration = probe_duration(voice_path)
    allocate_timeline(shots, audio_duration)

    script_json = {
        "title": "自助餐成瘾者回本哥的人生",
        "style_preset": STYLE_PRESET,
        "audio_duration": audio_duration,
        "shots": [asdict(s) for s in shots],
    }
    (OUT / "script.json").write_text(json.dumps(script_json, ensure_ascii=False, indent=2), encoding="utf-8")
    write_subtitles(shots, OUT / "subtitle.srt", OUT / "subtitle.ass")

    clip_paths: list[Path] = []
    for shot in shots:
        image_path = ASSETS / f"shot_{shot.id:02d}.png"
        clip_path = CLIPS / f"shot_{shot.id:02d}.mp4"
        render_shot(shot, image_path)
        make_clip(image_path, clip_path, shot.end - shot.start, shot.id)
        clip_paths.append(clip_path)

    merged = OUT / "storyboard_merged.mp4"
    concat_clips(clip_paths, merged)
    final = OUT / "rensheng_fuben_demo.mp4"
    burn_final(merged, voice_path, OUT / "subtitle.ass", final, audio_duration)

    print(json.dumps({
        "ok": True,
        "title": script_json["title"],
        "duration_sec": round(audio_duration, 2),
        "shots": len(shots),
        "script_json": str((OUT / "script.json").resolve()),
        "voice": str(voice_path.resolve()),
        "srt": str((OUT / "subtitle.srt").resolve()),
        "final_video": str(final.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
