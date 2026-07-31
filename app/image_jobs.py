"""Compatibility shim. Prefer importing from `app.images.jobs`."""

from importlib import import_module
import sys

_impl = import_module("app.images.jobs")
sys.modules[__name__] = _impl
