"""Compatibility shim. Prefer importing from `app.media.render.constants`."""

from importlib import import_module
import sys

_impl = import_module("app.media.render.constants")
sys.modules[__name__] = _impl
