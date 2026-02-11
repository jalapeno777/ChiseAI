from __future__ import annotations

import builtins
import importlib
import sys


def test_dashboard_import_does_not_import_streamlit(monkeypatch) -> None:
    """Guard against eager Streamlit imports from the core dashboard package.

    Streamlit is an optional (currently deprecated) dependency; CI does not install it.
    """

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "streamlit" or name.startswith("streamlit."):
            raise AssertionError("dashboard import attempted to import streamlit")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    sys.modules.pop("dashboard", None)
    importlib.import_module("dashboard")
