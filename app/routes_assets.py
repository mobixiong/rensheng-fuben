"""Compatibility shim. Prefer importing from `app.api.routes.assets`."""

from importlib import import_module
import sys

_impl = import_module("app.api.routes.assets")
sys.modules[__name__] = _impl
