"""Compatibility shim. Prefer importing from `app.core.errors`."""

from importlib import import_module
import sys

_impl = import_module("app.core.errors")
sys.modules[__name__] = _impl
