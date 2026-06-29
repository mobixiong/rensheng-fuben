import json
import re
import shutil
import time
import uuid
from pathlib import Path
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
PROJECTS_DIR = WORKSPACE / "projects"
ACTIVE_PROJECT = WORKSPACE / "active_project.json"
LEGACY_PROJECT_STATE = WORKSPACE / "current_project.json"

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
    size: str = "9:16"
    fixed_prompt: str | None = None


class ImageRegenerateRequest(ImageGenerateRequest):
    shot_index: int = Field(ge=0)


class ImageConnectionRequest(BaseModel):
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "9:16"


class RenderRequest(BaseModel):
    story: dict[str, Any]
    voice: str = "zh-CN-YunxiNeural"
    rate: str = "+12%"
    project_id: str | None = None


def _slug(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:42] or "未命名项目"


def _safe_project_id(value: Any, topic: str = "") -> str:
    raw = str(value or "").strip()
    if raw and "/" not in raw and "\\" not in raw and ".." not in raw and ":" not in raw:
        return _slug(raw)
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{_slug(topic)}_{uuid.uuid4().hex[:6]}"


def _project_dir(project_id: str):
    return PROJECTS_DIR / project_id


def _workspace_path_from_url(url: str):
    prefix = "/workspace/"
    if not isinstance(url, str) or not url.startswith(prefix):
        return None
    candidate = (WORKSPACE / url[len(prefix):]).resolve()
    try:
        candidate.relative_to(WORKSPACE.resolve())
    except ValueError:
        return None
    return candidate


def _copy_project_images(state: dict[str, Any], project_dir) -> None:
    story = state.get("story")
    if not isinstance(story, dict):
        return
    shots = story.get("shots")
    if not isinstance(shots, list):
        return

    image_dir = project_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for index, shot in enumerate(shots, 1):
        if not isinstance(shot, dict):
            continue
        source = None
        raw_path = str(shot.get("image_path") or "").strip()
        if raw_path:
            source = Path(raw_path)
        if (not source or not source.exists()) and shot.get("image_url"):
            source = _workspace_path_from_url(str(shot.get("image_url")))
        if not source or not source.exists():
            continue

        target = image_dir / f"shot_{index:02d}{source.suffix or '.png'}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        shot["image_path"] = str(target.resolve())
        shot["image_url"] = f"/workspace/projects/{state['project_id']}/images/{target.name}"


def _write_project_files(state: dict[str, Any]) -> dict[str, Any]:
    project_id = _safe_project_id(state.get("project_id"), str(state.get("topic") or ""))
    project_dir = _project_dir(project_id)
    prompts_dir = project_dir / "prompts"
    project_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        **state,
        "project_id": project_id,
        "project_url": f"/workspace/projects/{project_id}",
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _copy_project_images(payload, project_dir)
    story = payload.get("story")

    (project_dir / "state.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (project_dir / "copy.txt").write_text(str(payload.get("copy_text") or ""), encoding="utf-8")
    (project_dir / "result.txt").write_text(str(payload.get("result_text") or ""), encoding="utf-8")
    (prompts_dir / "copy_prompt.txt").write_text(str(payload.get("copy_prompt") or ""), encoding="utf-8")
    (prompts_dir / "image_prompt.txt").write_text(str(payload.get("image_prompt") or ""), encoding="utf-8")
    if isinstance(story, dict):
        (project_dir / "story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    elif payload.get("story_json"):
        (project_dir / "story.json").write_text(str(payload.get("story_json")), encoding="utf-8")
    (project_dir / "metadata.json").write_text(json.dumps({
        "project_id": project_id,
        "topic": payload.get("topic") or "",
        "saved_at": payload["saved_at"],
        "project_url": payload["project_url"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    ACTIVE_PROJECT.write_text(json.dumps({"project_id": project_id}, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


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
    return json.loads((EXAMPLES / "buffet_story.json").read_text(encoding="utf-8"))


@app.get("/api/project/current")
def project_current() -> dict[str, Any]:
    if not ACTIVE_PROJECT.exists():
        if LEGACY_PROJECT_STATE.exists():
            try:
                return {"exists": True, "state": json.loads(LEGACY_PROJECT_STATE.read_text(encoding="utf-8"))}
            except Exception:
                pass
        return {"exists": False}
    try:
        active = json.loads(ACTIVE_PROJECT.read_text(encoding="utf-8"))
        project_id = _safe_project_id(active.get("project_id"))
        state_path = _project_dir(project_id) / "state.json"
        if not state_path.exists():
            return {"exists": False}
        return {"exists": True, "state": json.loads(state_path.read_text(encoding="utf-8"))}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project state is unreadable: {exc}") from exc


@app.post("/api/project/current")
def project_save(state: dict[str, Any]) -> dict[str, Any]:
    try:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        payload = _write_project_files(state)
        return {
            "ok": True,
            "project_id": payload["project_id"],
            "project_url": payload["project_url"],
            "saved_at": payload["saved_at"],
            "state": payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Project save failed: {exc}") from exc


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
        return render_story(req.story, req.voice, req.rate, req.project_id)
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


app.mount("/static", StaticFiles(directory=STATIC), name="static")
WORKSPACE.mkdir(parents=True, exist_ok=True)
app.mount("/workspace", StaticFiles(directory=WORKSPACE), name="workspace")
