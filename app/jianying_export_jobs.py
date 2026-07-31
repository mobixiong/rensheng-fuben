"""Compatibility shim. Prefer importing from `app.media.jianying.export_jobs`."""

from importlib import import_module
import sys

_impl = import_module("app.media.jianying.export_jobs")
sys.modules[__name__] = _impl
