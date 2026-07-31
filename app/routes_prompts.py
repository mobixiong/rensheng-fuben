"""Compatibility shim. Prefer importing from `app.api.routes.prompts`."""

from importlib import import_module
import sys

_impl = import_module("app.api.routes.prompts")
sys.modules[__name__] = _impl
