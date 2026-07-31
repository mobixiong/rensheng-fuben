"""Compatibility shim. Prefer importing from `app.core.paths`."""

from importlib import import_module
import sys

_impl = import_module("app.core.paths")
sys.modules[__name__] = _impl
