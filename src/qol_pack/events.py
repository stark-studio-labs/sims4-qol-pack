"""
QoL Pack Events -- typed event definitions for cross-module communication.

Every event in the QoL Pack is a dataclass extending Event from the Stark
Framework event bus. Modules publish and subscribe to these to coordinate
without direct imports.

Usage:
    from qol_pack.events import UIValueChangedEvent, SettingsChangedEvent
    from stark_framework.core.events import EventBus

    @EventBus.on(UIValueChangedEvent)
    def on_value_changed(event):
        print(f"Sim {event.sim_id}: {event.field} changed to {event.new_value}")
"""

from dataclasses import dataclass, field
from stark_framework.core.events import Event


# ── UI Tweaks Events ────────────────────────────────────────────────

@dataclass
class UIEditRequestedEvent(Event):
    """Published when a player clicks a UI element to edit it.

    Cancellable -- a handler can call event.cancel() to block the edit
    (e.g., if the Sim is in a restricted state).
    """
    sim_id: int = 0
    field_name: str = ""  # "need_hunger", "skill_cooking", "money", etc.

    def __post_init__(self):
        super().__init__()


@dataclass
class UIValueChangedEvent(Event):
    """Published after a UI value edit is applied."""
    sim_id: int = 0
    field_name: str = ""
    old_value: float = 0.0
    new_value: float = 0.0

    def __post_init__(self):
        super().__init__()


# ── Build Tools Events ──────────────────────────────────────────────

@dataclass
class ObjectMovedEvent(Event):
    """Published after an object is repositioned via enhanced build tools."""
    object_id: int = 0
    old_position: tuple = (0.0, 0.0, 0.0)
    new_position: tuple = (0.0, 0.0, 0.0)

    def __post_init__(self):
        super().__init__()


@dataclass
class ObjectScaledEvent(Event):
    """Published after an object is scaled."""
    object_id: int = 0
    old_scale: tuple = (1.0, 1.0, 1.0)
    new_scale: tuple = (1.0, 1.0, 1.0)

    def __post_init__(self):
        super().__init__()


@dataclass
class ObjectRotatedEvent(Event):
    """Published after an object is rotated on any axis."""
    object_id: int = 0
    old_rotation: tuple = (0.0, 0.0, 0.0)
    new_rotation: tuple = (0.0, 0.0, 0.0)

    def __post_init__(self):
        super().__init__()


@dataclass
class BuildModeEnteredEvent(Event):
    """Published when the player enters build/buy mode."""

    def __post_init__(self):
        super().__init__()


@dataclass
class BuildModeExitedEvent(Event):
    """Published when the player exits build/buy mode."""

    def __post_init__(self):
        super().__init__()


# ── Performance Events ──────────────────────────────────────────────

@dataclass
class PerformanceReportEvent(Event):
    """Periodic performance health snapshot."""
    fps: float = 0.0
    sim_count: int = 0
    throttle_level: int = 0  # 0=none, 1=light, 2=moderate, 3=aggressive
    active_autonomy_sims: int = 0

    def __post_init__(self):
        super().__init__()


@dataclass
class ThrottleLevelChangedEvent(Event):
    """Published when auto-tuning adjusts the throttle level."""
    old_level: int = 0
    new_level: int = 0
    reason: str = ""

    def __post_init__(self):
        super().__init__()


# ── Diagnostics Events ──────────────────────────────────────────────

@dataclass
class ErrorCapturedEvent(Event):
    """Published when an exception is caught and attributed."""
    mod_id: str = ""
    error_type: str = ""
    message: str = ""
    traceback_text: str = ""
    suggested_fix: str = ""

    def __post_init__(self):
        super().__init__()


@dataclass
class ConflictDetectedEvent(Event):
    """Published when a mod conflict is identified."""
    mod_a: str = ""
    mod_b: str = ""
    conflict_type: str = ""  # "injection_overlap", "resource_conflict", "version"
    description: str = ""

    def __post_init__(self):
        super().__init__()


# ── Settings Events ─────────────────────────────────────────────────

@dataclass
class SettingsChangedEvent(Event):
    """Published when any setting is modified."""
    key: str = ""
    old_value: object = None
    new_value: object = None

    def __post_init__(self):
        super().__init__()


@dataclass
class PresetAppliedEvent(Event):
    """Published when a settings preset is loaded."""
    preset_name: str = ""  # "beginner", "advanced", "streamer"

    def __post_init__(self):
        super().__init__()


# ── Auto-Updater Events ────────────────────────────────────────────

@dataclass
class UpdateAvailableEvent(Event):
    """Published when a newer version is found."""
    current_version: str = ""
    new_version: str = ""
    changelog: str = ""
    download_url: str = ""

    def __post_init__(self):
        super().__init__()


@dataclass
class UpdateInstalledEvent(Event):
    """Published after an update is applied."""
    version: str = ""
    restart_required: bool = True

    def __post_init__(self):
        super().__init__()
