"""Compatibility shim. Prefer importing from `app.api.routes.jianying`."""

from importlib import import_module
import sys

_impl = import_module("app.api.routes.jianying")
sys.modules[__name__] = _impl
