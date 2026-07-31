"""Compatibility shim. Prefer importing from `app.jobs.health`."""

from importlib import import_module
import sys

_impl = import_module("app.jobs.health")
sys.modules[__name__] = _impl
