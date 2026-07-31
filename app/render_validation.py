"""Compatibility shim. Prefer importing from `app.media.render.validation`."""

from importlib import import_module
import sys

_impl = import_module("app.media.render.validation")
sys.modules[__name__] = _impl
