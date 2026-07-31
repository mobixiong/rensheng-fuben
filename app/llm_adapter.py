"""Compatibility shim. Prefer importing from `app.providers.llm.adapter`."""

from importlib import import_module
import sys

_impl = import_module("app.providers.llm.adapter")
sys.modules[__name__] = _impl
