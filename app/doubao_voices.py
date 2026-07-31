"""Compatibility shim. Prefer importing from `app.providers.tts.doubao_voices`."""

from importlib import import_module
import sys

_impl = import_module("app.providers.tts.doubao_voices")
sys.modules[__name__] = _impl
