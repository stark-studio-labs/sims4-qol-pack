"""
Shared test fixtures for QoL Pack tests.

Provides clean EventBus/ModRegistry/InjectionManager state for each test
and mock game APIs that the modules depend on.
"""

import sys
import os
import pytest

# Add src to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture(autouse=True)
def clean_framework_state():
    """Reset all framework singletons before each test."""
    from qol_pack._compat import EventBus, ModRegistry, InjectionManager, Diagnostics, LogBuffer

    EventBus.clear()
    EventBus.enable_logging(False)
    ModRegistry.clear()
    InjectionManager.clear()
    Diagnostics.clear()
    LogBuffer.clear()

    yield

    EventBus.clear()
    ModRegistry.clear()
    InjectionManager.clear()
    Diagnostics.clear()
    LogBuffer.clear()


@pytest.fixture
def registered_qol():
    """Register the QoL Pack with ModRegistry (no module init)."""
    from qol_pack._compat import ModRegistry
    ModRegistry.register(
        mod_id="stark_qol_pack",
        name="Stark QoL Pack",
        version="0.1.0",
        author="Stark Labs",
        dependencies=["stark_framework"],
    )


@pytest.fixture
def settings_file(tmp_path):
    """Provide a temp settings file path."""
    return str(tmp_path / "settings.json")


@pytest.fixture
def captured_events():
    """Capture all published events for assertion."""
    from qol_pack._compat import EventBus, Event

    captured = []

    class _CaptureAll(Event):
        pass

    original_publish = EventBus.publish

    @classmethod
    def capturing_publish(cls, event, source_mod=None):
        captured.append(event)
        return original_publish(event, source_mod=source_mod)

    EventBus.publish = capturing_publish
    yield captured
    EventBus.publish = original_publish
