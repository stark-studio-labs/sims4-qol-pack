"""Tests for the compatibility shim."""

import builtins
import importlib.util
from pathlib import Path
import sys


def test_compat_fallback_works_without_framework(monkeypatch):
    compat_path = Path(__file__).resolve().parents[1] / "src" / "qol_pack" / "_compat.py"
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "stark_framework" or name.startswith("stark_framework."):
            raise ImportError("forced missing framework")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    spec = importlib.util.spec_from_file_location("qol_pack._compat_fallback_test", compat_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    assert module._HAS_FRAMEWORK is False

    class DummyEvent(module.Event):
        pass

    seen = []

    @module.EventBus.on(DummyEvent)
    def handle(event):
        seen.append(event.source_mod)
        event.cancel()

    module.ModRegistry.register(mod_id="test_mod", name="Test Mod", version="1.0.0")
    module.Diagnostics.record_error("test_mod", ValueError("boom"), "context")

    event = DummyEvent()
    module.EventBus.publish(event, source_mod="source_mod")

    assert seen == ["source_mod"]
    assert event.cancelled is True
    assert module.ModRegistry.all_mods()["test_mod"]["name"] == "Test Mod"
    assert module.Diagnostics.get_errors()[0]["error"] == "boom"
