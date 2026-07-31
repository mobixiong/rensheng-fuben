"""Compatibility shim. Prefer importing from `app.media.render.subtitle_renderer`."""

from importlib import import_module
import sys

_impl = import_module("app.media.render.subtitle_renderer")
sys.modules[__name__] = _impl
