"""Compatibility shim. Prefer importing from `app.workflow.auto_pipeline`."""

from importlib import import_module
import sys

_impl = import_module("app.workflow.auto_pipeline")
sys.modules[__name__] = _impl
