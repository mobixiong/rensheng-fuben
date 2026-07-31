from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from app.media.audio.assets import resolve_bgm_path, resolve_intro_sfx_path
from app.core.errors import RenderError
from app.media.render.pipeline import render_story
from app.projects.service import project_dir
from app.media.render.constants import FPS, render_size
from app.media.render.validation import validate_ready_for_render
from app.providers.tts.adapter import TtsConfig

DRAFTS_DIR_NAME = "jianying_drafts"

DRAFT_ASSETS_DIR_NAME = "assets"

VIDEO_TRACK_NAME = "画面"

VOICE_TRACK_NAME = "配音"

BGM_TRACK_NAME = "BGM"

SFX_TRACK_NAME = "开头音效"

SUBTITLE_TRACK_NAME = "字幕"

