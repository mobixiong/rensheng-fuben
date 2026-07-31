"""Compatibility shim. Prefer importing from `app.media.audio.assets`."""

from importlib import import_module
import sys

_impl = import_module("app.media.audio.assets")
sys.modules[__name__] = _impl
