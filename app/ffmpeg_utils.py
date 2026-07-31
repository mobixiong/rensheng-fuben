"""Compatibility shim. Prefer importing from `app.media.render.ffmpeg_utils`."""

from importlib import import_module
import sys

_impl = import_module("app.media.render.ffmpeg_utils")
sys.modules[__name__] = _impl
