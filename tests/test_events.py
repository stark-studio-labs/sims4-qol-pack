"""Tests for QoL Pack event definitions."""

from stark_framework.core.events import EventBus

from qol_pack.events import (
    UIEditRequestedEvent,
    UIValueChangedEvent,
    ObjectMovedEvent,
    ObjectScaledEvent,
    ObjectRotatedEvent,
    BuildModeEnteredEvent,
    BuildModeExitedEvent,
    PerformanceReportEvent,
    ThrottleLevelChangedEvent,
    ErrorCapturedEvent,
    ConflictDetectedEvent,
    SettingsChangedEvent,
    PresetAppliedEvent,
    UpdateAvailableEvent,
    UpdateInstalledEvent,
)


class TestEventConstruction:
    """Verify all events can be constructed with defaults and custom values."""

    def test_ui_edit_requested_defaults(self):
        e = UIEditRequestedEvent()
        assert e.sim_id == 0
        assert e.field_name == ""
        assert not e.cancelled

    def test_ui_edit_requested_custom(self):
        e = UIEditRequestedEvent(sim_id=42, field_name="need_hunger")
        assert e.sim_id == 42
        assert e.field_name == "need_hunger"

    def test_ui_value_changed(self):
        e = UIValueChangedEvent(sim_id=1, field_name="money", old_value=100, new_value=999)
        assert e.old_value == 100
        assert e.new_value == 999

    def test_object_moved(self):
        e = ObjectMovedEvent(
            object_id=10,
            old_position=(1.0, 2.0, 3.0),
            new_position=(4.0, 5.0, 6.0),
        )
        assert e.new_position == (4.0, 5.0, 6.0)

    def test_object_scaled(self):
        e = ObjectScaledEvent(object_id=10, new_scale=(2.0, 2.0, 2.0))
        assert e.new_scale == (2.0, 2.0, 2.0)

    def test_object_rotated(self):
        e = ObjectRotatedEvent(object_id=10, new_rotation=(0, 90, 0))
        assert e.new_rotation == (0, 90, 0)

    def test_build_mode_events(self):
        entered = BuildModeEnteredEvent()
        exited = BuildModeExitedEvent()
        assert not entered.cancelled
        assert not exited.cancelled

    def test_performance_report(self):
        e = PerformanceReportEvent(fps=59.5, sim_count=8, throttle_level=1)
        assert e.fps == 59.5
        assert e.sim_count == 8

    def test_throttle_level_changed(self):
        e = ThrottleLevelChangedEvent(old_level=0, new_level=2, reason="low fps")
        assert e.reason == "low fps"

    def test_error_captured(self):
        e = ErrorCapturedEvent(
            mod_id="test_mod",
            error_type="ValueError",
            message="bad value",
            suggested_fix="Fix it",
        )
        assert e.mod_id == "test_mod"
        assert e.suggested_fix == "Fix it"

    def test_conflict_detected(self):
        e = ConflictDetectedEvent(
            mod_a="mod1", mod_b="mod2",
            conflict_type="injection_overlap",
        )
        assert e.conflict_type == "injection_overlap"

    def test_settings_changed(self):
        e = SettingsChangedEvent(key="ui_tweaks.enabled", old_value=True, new_value=False)
        assert e.key == "ui_tweaks.enabled"
        assert e.old_value is True
        assert e.new_value is False

    def test_preset_applied(self):
        e = PresetAppliedEvent(preset_name="streamer")
        assert e.preset_name == "streamer"

    def test_update_available(self):
        e = UpdateAvailableEvent(
            current_version="0.1.0",
            new_version="0.2.0",
            changelog="Bug fixes",
        )
        assert e.new_version == "0.2.0"

    def test_update_installed(self):
        e = UpdateInstalledEvent(version="0.2.0", restart_required=True)
        assert e.restart_required is True


class TestEventCancellation:
    """Verify cancellation works on cancellable events."""

    def test_cancel_ui_edit_request(self):
        e = UIEditRequestedEvent(sim_id=1, field_name="need_hunger")
        assert not e.cancelled
        e.cancel()
        assert e.cancelled

    def test_cancelled_event_stops_handler_chain(self):
        results = []

        @EventBus.on(UIEditRequestedEvent, priority=1)
        def first(event):
            results.append("first")
            event.cancel()

        @EventBus.on(UIEditRequestedEvent, priority=2)
        def second(event):
            results.append("second")

        EventBus.publish(UIEditRequestedEvent(sim_id=1, field_name="test"))
        assert results == ["first"]


class TestEventBusIntegration:
    """Verify events work with the Stark Framework EventBus."""

    def test_subscribe_and_publish(self):
        received = []

        @EventBus.on(SettingsChangedEvent)
        def handler(event):
            received.append(event.key)

        EventBus.publish(SettingsChangedEvent(key="test.key", old_value=1, new_value=2))
        assert received == ["test.key"]

    def test_source_mod_tracking(self):
        received_source = []

        @EventBus.on(BuildModeEnteredEvent)
        def handler(event):
            received_source.append(event.source_mod)

        EventBus.publish(BuildModeEnteredEvent(), source_mod="my_mod")
        assert received_source == ["my_mod"]
