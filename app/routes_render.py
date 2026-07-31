"""Compatibility shim. Prefer importing from `app.api.routes.render`."""

from importlib import import_module
import sys

_impl = import_module("app.api.routes.render")
sys.modules[__name__] = _impl
