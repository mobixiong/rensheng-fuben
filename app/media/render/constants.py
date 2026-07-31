W = 1080
H = 1920
FPS = 30


def render_size(value: str | None = None) -> tuple[int, int]:
    ratio = str(value or "").strip()
    if ratio in {"16:9", "16 / 9"}:
        return 1920, 1080
    if ratio in {"1:1", "1 / 1"}:
        return 1440, 1440
    return W, H
