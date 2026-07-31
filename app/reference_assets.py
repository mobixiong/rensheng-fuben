"""Compatibility shim. Prefer importing from `app.projects.reference_assets`."""

from importlib import import_module
import sys

_impl = import_module("app.projects.reference_assets")
sys.modules[__name__] = _impl
