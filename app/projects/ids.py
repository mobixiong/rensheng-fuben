"""Compatibility shim. Prefer importing from `app.core.project_ids`."""

from importlib import import_module
import sys

_impl = import_module("app.core.project_ids")
sys.modules[__name__] = _impl
