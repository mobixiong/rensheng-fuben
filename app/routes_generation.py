"""Compatibility shim. Prefer importing from `app.api.routes.generation`."""

from importlib import import_module
import sys

_impl = import_module("app.api.routes.generation")
sys.modules[__name__] = _impl
