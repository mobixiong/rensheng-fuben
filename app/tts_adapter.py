"""Compatibility shim. Prefer importing from `app.providers.tts.adapter`."""

from importlib import import_module
import sys

_impl = import_module("app.providers.tts.adapter")
sys.modules[__name__] = _impl
