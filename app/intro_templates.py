"""Compatibility shim. Prefer importing from `app.media.render.intro_templates`."""

from importlib import import_module
import sys

_impl = import_module("app.media.render.intro_templates")
sys.modules[__name__] = _impl
