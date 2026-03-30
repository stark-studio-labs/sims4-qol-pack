"""
Compatibility shim for stark_framework imports.

When stark_framework is installed (normal runtime inside The Sims 4), this
module re-exports the real implementations. When it is NOT installed (standalone
testing, CI, IDE analysis), it provides no-op stubs so qol_pack can still be
imported and inspected without crashing.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging as _logging
from typing import Any, Callable, Dict, List

_HAS_FRAMEWORK = False


@dataclass
class _Subscription:
    event_type: Any
    handler: Callable[..., Any]
    priority: int = 0
    mod_id: str = ""


# ── Stub classes (used when stark_framework is unavailable) ────────────

class _StubEvent:
    """No-op Event base class."""

    def __init__(self) -> None:
        self.cancelled = False
        self.source_mod = ""

    def cancel(self) -> None:
        self.cancelled = True


class _StubEventBus:
    """In-memory EventBus fallback used when stark_framework is unavailable."""

    _subscribers: List[_Subscription] = []
    _logging_enabled = False

    @classmethod
    def subscribe(
        cls,
        event_type: Any,
        handler: Callable[..., Any],
        priority: int = 0,
        mod_id: str = "",
    ) -> None:
        cls._subscribers.append(
            _Subscription(event_type=event_type, handler=handler, priority=priority, mod_id=mod_id)
        )
        cls._subscribers.sort(key=lambda item: item.priority)

    @classmethod
    def publish(cls, event: Any, source_mod: str = "") -> None:
        if hasattr(event, "source_mod"):
            event.source_mod = source_mod

        for sub in list(cls._subscribers):
            if isinstance(event, sub.event_type):
                sub.handler(event)
                if getattr(event, "cancelled", False):
                    break

    @classmethod
    def on(cls, event_type: Any) -> Any:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            cls.subscribe(event_type, fn)
            return fn

        return decorator

    @classmethod
    def enable_logging(cls, enabled: bool) -> None:
        cls._logging_enabled = enabled

    @classmethod
    def get_subscribers(cls, event_type: Any) -> List[_Subscription]:
        return [sub for sub in cls._subscribers if sub.event_type is event_type]

    @classmethod
    def clear(cls) -> None:
        cls._subscribers = []


class _StubModRegistry:
    """In-memory ModRegistry fallback."""

    _mods: Dict[str, Any] = {}

    @classmethod
    def register(cls, **kwargs: Any) -> None:
        cls._mods[kwargs.get("mod_id", "")] = kwargs

    @classmethod
    def all_mods(cls) -> Dict[str, Any]:
        return dict(cls._mods)

    @classmethod
    def clear(cls) -> None:
        cls._mods = {}


class _StubDiagnostics:
    """In-memory Diagnostics fallback."""

    _errors: List[Dict[str, Any]] = []

    @classmethod
    def record_error(
        cls,
        mod_id: str = "",
        error: Any = None,
        context: str = "",
    ) -> None:
        cls._errors.append(
            {
                "mod_id": mod_id,
                "error": str(error) if error is not None else "",
                "error_type": type(error).__name__ if error is not None else "NoneType",
                "context": context,
            }
        )

    @classmethod
    def detect_conflicts(cls) -> List[Any]:
        return []

    @classmethod
    def health_report(cls) -> Dict[str, Any]:
        return {
            "error_count": len(cls._errors),
            "mod_count": len(_StubModRegistry._mods),
        }

    @classmethod
    def get_errors(cls, limit: int = 10) -> List[Any]:
        if limit <= 0:
            return []
        return list(cls._errors[-limit:])

    @classmethod
    def clear(cls) -> None:
        cls._errors = []


class _StubInjectionManager:
    """In-memory InjectionManager fallback."""

    @classmethod
    def list_injections(cls) -> List[Any]:
        return []

    @classmethod
    def clear(cls) -> None:
        pass


class _StubLogBuffer:
    """In-memory LogBuffer fallback."""

    _entries: List[Any] = []

    @classmethod
    def get_entries(cls, limit: int = 50) -> List[Any]:
        if limit <= 0:
            return []
        return list(cls._entries[-limit:])

    @classmethod
    def clear(cls) -> None:
        cls._entries = []


def _stub_get_logger(name: str) -> _logging.Logger:
    """Return a stdlib logger when stark_framework is unavailable."""
    return _logging.getLogger(name)


# ── Resolve real or stub implementations ───────────────────────────────

try:
    from stark_framework.core.events import Event as Event  # type: ignore
    from stark_framework.core.events import EventBus as EventBus  # type: ignore
    from stark_framework.core.registry import ModRegistry as ModRegistry  # type: ignore
    from stark_framework.core.diagnostics import Diagnostics as Diagnostics  # type: ignore
    from stark_framework.core.injection import InjectionManager as InjectionManager  # type: ignore
    from stark_framework.utils.logging import get_logger as get_logger  # type: ignore
    from stark_framework.utils.logging import LogBuffer as LogBuffer  # type: ignore
    _HAS_FRAMEWORK = True
except ImportError:
    Event = _StubEvent  # type: ignore[misc,assignment]
    EventBus = _StubEventBus  # type: ignore[misc,assignment]
    ModRegistry = _StubModRegistry  # type: ignore[misc,assignment]
    Diagnostics = _StubDiagnostics  # type: ignore[misc,assignment]
    InjectionManager = _StubInjectionManager  # type: ignore[misc,assignment]
    LogBuffer = _StubLogBuffer  # type: ignore[misc,assignment]
    get_logger = _stub_get_logger  # type: ignore[misc,assignment]
