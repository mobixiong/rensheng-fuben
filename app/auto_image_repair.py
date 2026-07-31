"""Compatibility shim. Prefer importing from `app.images.repair`."""

from importlib import import_module
import sys

_impl = import_module("app.images.repair")
sys.modules[__name__] = _impl
