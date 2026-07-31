"""Compatibility shim. Prefer importing from `app.api.routes.auto_pipeline`."""

from importlib import import_module
import sys

_impl = import_module("app.api.routes.auto_pipeline")
sys.modules[__name__] = _impl
