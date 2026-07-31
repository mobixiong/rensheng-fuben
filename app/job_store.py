"""Compatibility shim. Prefer importing from `app.jobs.store`."""

from importlib import import_module
import sys

_impl = import_module("app.jobs.store")
sys.modules[__name__] = _impl
