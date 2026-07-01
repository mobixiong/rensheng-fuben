from fastapi import APIRouter

from .image_adapter import load_image_prompt
from .llm_adapter import load_copy_to_story_prompt, load_improve_image_prompt, load_theme_prompt
from .paths import ROOT


router = APIRouter()

COPY_PROMPT = ROOT / "prompt.txt"
COPY_XIANXIA_PROMPT = ROOT / "prompts" / "copy_xianxia.md"


@router.get("/api/prompt/default")
def default_prompt() -> dict[str, str]:
    return {"prompt": COPY_PROMPT.read_text(encoding="utf-8")}


@router.get("/api/prompt/copy-xianxia")
def copy_xianxia_prompt() -> dict[str, str]:
    return {"prompt": COPY_XIANXIA_PROMPT.read_text(encoding="utf-8")}


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
