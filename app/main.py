from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.paths import ENV_PATH, STATIC, WORKSPACE
from app.api.routes.assets import router as assets_router
from app.api.routes.auto_pipeline import router as auto_pipeline_router
from app.api.routes.generation import router as generation_router
from app.api.routes.jianying import router as jianying_router
from app.api.routes.project import router as project_router
from app.api.routes.prompts import router as prompts_router
from app.api.routes.render import router as render_router


try:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)
except Exception:
    pass


app = FastAPI(title="人生副本工作台", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project_router)
app.include_router(prompts_router)
app.include_router(assets_router)
app.include_router(auto_pipeline_router)
app.include_router(generation_router)
app.include_router(render_router)
app.include_router(jianying_router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


app.mount("/static", StaticFiles(directory=STATIC), name="static")
WORKSPACE.mkdir(parents=True, exist_ok=True)
app.mount("/workspace", StaticFiles(directory=WORKSPACE), name="workspace")
