"""Compatibility shim. Prefer importing from `app.images.status`."""

from importlib import import_module
import sys

_impl = import_module("app.images.status")
sys.modules[__name__] = _impl
