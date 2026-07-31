"""Compatibility shim. Prefer importing from `app.media.audio.upload`."""

from importlib import import_module
import sys

_impl = import_module("app.media.audio.upload")
sys.modules[__name__] = _impl
