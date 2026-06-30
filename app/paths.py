from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
EXAMPLES = ROOT / "examples"
WORKSPACE = ROOT / "workspace"
PROJECTS_DIR = WORKSPACE / "projects"
ACTIVE_PROJECT = WORKSPACE / "active_project.json"
LEGACY_PROJECT_STATE = WORKSPACE / "current_project.json"
