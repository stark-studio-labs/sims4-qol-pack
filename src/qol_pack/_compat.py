"""
Compatibility shim for stark_framework imports.

When stark_framework is installed (normal runtime inside The Sims 4), this
module re-exports the real implementations. When it is NOT installed (standalone
testing, CI, IDE analysis), it provides no-op stubs so qol_pack can still be
imported and inspected without crashing.
"""

from __future__ import annotations

import logging as _logging
from typing import Any, Dict, List, Set

_HAS_FRAMEWORK = False


# ── Stub classes (used when stark_framework is unavailable) ────────────

class _StubEvent:
    """No-op Event base class."""
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


class _StubEventBus:
    """No-op EventBus."""

    @classmethod
    def subscribe(cls, event_type: Any, handler: Any, priority: int = 0,
                  mod_id: str = "") -> None:
        pass

    @classmethod
    def publish(cls, event: Any, source_mod: str = "") -> None:
        pass

    @classmethod
    def on(cls, event_type: Any) -> Any:
        def decorator(fn: Any) -> Any:
            return fn
        return decorator

    @classmethod
    def enable_logging(cls, enabled: bool) -> None:
        pass


class _StubModRegistry:
    """No-op ModRegistry."""

    _mods: Dict[str, Any] = {}

    @classmethod
    def register(cls, **kwargs: Any) -> None:
        cls._mods[kwargs.get("mod_id", "")] = kwargs

    @classmethod
    def all_mods(cls) -> Dict[str, Any]:
        return dict(cls._mods)


class _StubDiagnostics:
    """No-op Diagnostics."""

    @classmethod
    def record_error(cls, mod_id: str = "", error: Any = None,
                     context: str = "") -> None:
        pass

    @classmethod
    def detect_conflicts(cls) -> List[Any]:
        return []

    @classmethod
    def health_report(cls) -> Dict[str, Any]:
        return {}

    @classmethod
    def get_errors(cls, limit: int = 10) -> List[Any]:
        return []


class _StubInjectionManager:
    """No-op InjectionManager."""

    @classmethod
    def list_injections(cls) -> List[Any]:
        return []


class _StubLogBuffer:
    """No-op LogBuffer."""

    @classmethod
    def get_entries(cls, limit: int = 50) -> List[Any]:
        return []


def _stub_get_logger(name: str) -> _logging.Logger:
    """Return a stdlib logger when stark_framework is unavailable."""
    return _logging.getLogger(name)


# ── Resolve real or stub implementations ───────────────────────────────

try:
    from stark_framework.core.events import Event as Event  # noqa: F401
    from stark_framework.core.events import EventBus as EventBus  # noqa: F401
    from stark_framework.core.registry import ModRegistry as ModRegistry  # noqa: F401
    from stark_framework.core.diagnostics import Diagnostics as Diagnostics  # noqa: F401
    from stark_framework.core.injection import InjectionManager as InjectionManager  # noqa: F401
    from stark_framework.utils.logging import get_logger as get_logger  # noqa: F401
    from stark_framework.utils.logging import LogBuffer as LogBuffer  # noqa: F401
    _HAS_FRAMEWORK = True
except ImportError:
    Event = _StubEvent  # type: ignore[misc,assignment]
    EventBus = _StubEventBus  # type: ignore[misc,assignment]
    ModRegistry = _StubModRegistry  # type: ignore[misc,assignment]
    Diagnostics = _StubDiagnostics  # type: ignore[misc,assignment]
    InjectionManager = _StubInjectionManager  # type: ignore[misc,assignment]
    LogBuffer = _StubLogBuffer  # type: ignore[misc,assignment]
    get_logger = _stub_get_logger  # type: ignore[misc,assignment]
