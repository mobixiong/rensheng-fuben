import sys
from pathlib import Path


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()
    return Path(__file__).resolve().parents[1]


def _user_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _resource_root()


ROOT = _resource_root()
APP_DIR = _user_root()
ENV_PATH = APP_DIR / ".env"
STATIC = ROOT / "static"
EXAMPLES = ROOT / "examples"
WORKSPACE = APP_DIR / "workspace"
PROJECTS_DIR = WORKSPACE / "projects"
REFERENCE_COLLECTIONS_DIR = WORKSPACE / "reference_collections"
ACTIVE_PROJECT = WORKSPACE / "active_project.json"
LEGACY_PROJECT_STATE = WORKSPACE / "current_project.json"
