"""Compatibility shim. Prefer importing from `app.media.jianying.open`."""

from importlib import import_module
import sys

_impl = import_module("app.media.jianying.open")
sys.modules[__name__] = _impl
