"""Compatibility shim. Prefer importing from `app.api.routes.project`."""

from importlib import import_module
import sys

_impl = import_module("app.api.routes.project")
sys.modules[__name__] = _impl
