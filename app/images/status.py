"""Compatibility shim. Prefer importing from `app.core.image_status`."""

from importlib import import_module
import sys

_impl = import_module("app.core.image_status")
sys.modules[__name__] = _impl
