from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .image_adapter import ImageConfig, ImageError, generate_one_story_image, generate_story_images, test_image_connection
from .llm_adapter import LLMConfig, LLMError, generate_story, generate_story_from_copy, generate_text, test_text_connection
from .pipeline import ROOT, WORKSPACE, RenderError, render_story


STATIC = ROOT / "static"
EXAMPLES = ROOT / "examples"
COPY_PROMPT = ROOT / "prompt.txt"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=1)
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.8
    system_prompt: str | None = None


class CopyToStoryRequest(GenerateRequest):
    copy_text: str = Field(min_length=1)


class TextConnectionRequest(BaseModel):
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0


class ImageGenerateRequest(BaseModel):
    story: dict[str, Any]
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "1024x1792"
    fixed_prompt: str | None = None


class ImageRegenerateRequest(ImageGenerateRequest):
    shot_index: int = Field(ge=0)


class ImageConnectionRequest(BaseModel):
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "1024x1792"


class RenderRequest(BaseModel):
    story: dict[str, Any]
    voice: str = "zh-CN-YunxiNeural"
    rate: str = "+12%"


app = FastAPI(title="人生副本工作台", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/api/example")
def example() -> dict[str, Any]:
    import json

    return json.loads((EXAMPLES / "buffet_story.json").read_text(encoding="utf-8"))


@app.get("/api/prompt/default")
def default_prompt() -> dict[str, str]:
    return {"prompt": COPY_PROMPT.read_text(encoding="utf-8")}


@app.get("/api/prompt/image")
def image_prompt() -> dict[str, str]:
    from .image_adapter import load_image_prompt

    return {"prompt": load_image_prompt()}


@app.post("/api/text/generate-copy")
def text_generate_copy(req: GenerateRequest) -> dict[str, str]:
    try:
        text = generate_text(req.topic, LLMConfig.from_payload(req.model_dump()), req.system_prompt)
        return {"topic": req.topic, "text": text}
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/test-text")
def settings_test_text(req: TextConnectionRequest) -> dict[str, Any]:
    try:
        return test_text_connection(LLMConfig.from_payload(req.model_dump()))
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/test-image")
def settings_test_image(req: ImageConnectionRequest) -> dict[str, Any]:
    try:
        return test_image_connection(ImageConfig.from_payload(req.model_dump()))
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/text/copy-to-story")
def text_copy_to_story(req: CopyToStoryRequest) -> dict[str, Any]:
    try:
        return generate_story_from_copy(req.topic, req.copy_text, LLMConfig.from_payload(req.model_dump()), req.system_prompt)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/text/generate")
def text_generate(req: GenerateRequest) -> dict[str, Any]:
    try:
        return generate_story(req.topic, LLMConfig.from_payload(req.model_dump()), req.system_prompt)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/llm/generate")
def llm_generate(req: GenerateRequest) -> dict[str, Any]:
    return text_generate(req)


@app.post("/api/image/generate-story")
def image_generate_story(req: ImageGenerateRequest) -> dict[str, Any]:
    try:
        return generate_story_images(req.story, ImageConfig.from_payload(req.model_dump()), req.fixed_prompt)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/image/regenerate-shot")
def image_regenerate_shot(req: ImageRegenerateRequest) -> dict[str, Any]:
    try:
        return generate_one_story_image(req.story, req.shot_index, ImageConfig.from_payload(req.model_dump()), req.fixed_prompt)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/render")
def render(req: RenderRequest) -> dict[str, Any]:
    try:
        return render_story(req.story, req.voice, req.rate)
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


app.mount("/static", StaticFiles(directory=STATIC), name="static")
WORKSPACE.mkdir(parents=True, exist_ok=True)
app.mount("/workspace", StaticFiles(directory=WORKSPACE), name="workspace")
