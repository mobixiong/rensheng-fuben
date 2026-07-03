from fastapi import APIRouter

from .image_adapter import load_image_prompt
from .llm_adapter import load_copy_to_story_prompt, load_improve_image_prompt, load_theme_ideas_prompt, load_theme_prompt
from .paths import ROOT


router = APIRouter()

COPY_PROMPT = ROOT / "prompt.txt"
COPY_REALITY_BREAKOUT_PROMPT = ROOT / "prompts" / "copy_reality_breakout.md"
COPY_REALITY_STOP_LOSS_PROMPT = ROOT / "prompts" / "copy_reality_stop_loss.md"
COPY_REALITY_BURNOUT_SUPPORT_PROMPT = ROOT / "prompts" / "copy_reality_burnout_support.md"
COPY_XIANXIA_PROMPT = ROOT / "prompts" / "copy_xianxia.md"
COPY_FANTASY_WUXIA_PROMPT = ROOT / "prompts" / "copy_fantasy_wuxia.md"
COPY_FANTASY_ZOMBIE_PROMPT = ROOT / "prompts" / "copy_fantasy_zombie.md"
COPY_FANTASY_OTHERWORLD_PROMPT = ROOT / "prompts" / "copy_fantasy_otherworld.md"
COPY_FANTASY_CYBERPUNK_PROMPT = ROOT / "prompts" / "copy_fantasy_cyberpunk.md"
COPY_FANTASY_WEIRD_RULES_PROMPT = ROOT / "prompts" / "copy_fantasy_weird_rules.md"


@router.get("/api/prompt/default")
def default_prompt() -> dict[str, str]:
    return {"prompt": COPY_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-xianxia")
def copy_xianxia_prompt() -> dict[str, str]:
    return {"prompt": COPY_XIANXIA_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-reality-breakout")
def copy_reality_breakout_prompt() -> dict[str, str]:
    return {"prompt": COPY_REALITY_BREAKOUT_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-reality-stop-loss")
def copy_reality_stop_loss_prompt() -> dict[str, str]:
    return {"prompt": COPY_REALITY_STOP_LOSS_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-reality-burnout-support")
def copy_reality_burnout_support_prompt() -> dict[str, str]:
    return {"prompt": COPY_REALITY_BURNOUT_SUPPORT_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-fantasy-wuxia")
def copy_fantasy_wuxia_prompt() -> dict[str, str]:
    return {"prompt": COPY_FANTASY_WUXIA_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-fantasy-zombie")
def copy_fantasy_zombie_prompt() -> dict[str, str]:
    return {"prompt": COPY_FANTASY_ZOMBIE_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-fantasy-otherworld")
def copy_fantasy_otherworld_prompt() -> dict[str, str]:
    return {"prompt": COPY_FANTASY_OTHERWORLD_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-fantasy-cyberpunk")
def copy_fantasy_cyberpunk_prompt() -> dict[str, str]:
    return {"prompt": COPY_FANTASY_CYBERPUNK_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-fantasy-weird-rules")
def copy_fantasy_weird_rules_prompt() -> dict[str, str]:
    return {"prompt": COPY_FANTASY_WEIRD_RULES_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/image")
def image_prompt() -> dict[str, str]:
    return {"prompt": load_image_prompt()}


@router.get("/api/prompt/improve-image")
def improve_image_prompt() -> dict[str, str]:
    return {"prompt": load_improve_image_prompt()}


@router.get("/api/prompt/copy-to-story")
def copy_to_story_prompt() -> dict[str, str]:
    return {"prompt": load_copy_to_story_prompt()}


@router.get("/api/prompt/theme")
def theme_prompt() -> dict[str, str]:
    return {"prompt": load_theme_prompt()}


@router.get("/api/prompt/theme-ideas")
def theme_ideas_prompt() -> dict[str, str]:
    return {"prompt": load_theme_ideas_prompt()}
