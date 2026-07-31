"""Compatibility shim. Prefer importing from `app.core.schemas`."""

from importlib import import_module
import sys

_impl = import_module("app.core.schemas")
sys.modules[__name__] = _impl
