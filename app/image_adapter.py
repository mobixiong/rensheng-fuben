"""Compatibility shim. Prefer importing from `app.providers.image.adapter`."""

from importlib import import_module
import sys

_impl = import_module("app.providers.image.adapter")
sys.modules[__name__] = _impl
