"""Compatibility shim. Prefer importing from `app.projects.service`."""

from importlib import import_module
import sys

_impl = import_module("app.projects.service")
sys.modules[__name__] = _impl
