"""Compatibility shim. Prefer importing from `app.media.render.pipeline`."""

from importlib import import_module
import sys

_impl = import_module("app.media.render.pipeline")
sys.modules[__name__] = _impl
