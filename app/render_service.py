"""Compatibility shim. Prefer importing from `app.media.render.service`."""

from importlib import import_module
import sys

_impl = import_module("app.media.render.service")
sys.modules[__name__] = _impl
