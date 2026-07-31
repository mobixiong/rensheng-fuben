"""Compatibility shim. Prefer importing from `app.jobs.status`."""

from importlib import import_module
import sys

_impl = import_module("app.jobs.status")
sys.modules[__name__] = _impl
