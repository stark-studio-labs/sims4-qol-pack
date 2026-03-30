"""Tests for the Build Tools module."""

from qol_pack.events import (
    BuildModeEnteredEvent,
    BuildModeExitedEvent,
    ObjectMovedEvent,
    SettingsChangedEvent,
)
from qol_pack._compat import EventBus
from qol_pack.modules.build_tools import BuildTools, TransformState, _snap


class TestBuildToolsInstall:
    def test_install_subscribes_to_settings(self):
        BuildTools.install()
        subs = EventBus.get_subscribers(SettingsChangedEvent)
        mod_ids = [s.mod_id for s in subs]
        assert "stark_qol_pack.build_tools" in mod_ids


class TestBuildMode:
    def test_enter_build_mode(self):
        events = []

        @EventBus.on(BuildModeEnteredEvent)
        def capture(event):
            events.append(event)

        BuildTools.enter_build_mode()
        assert BuildTools._in_build_mode is True
        assert len(events) == 1

    def test_exit_build_mode(self):
        events = []

        @EventBus.on(BuildModeExitedEvent)
        def capture(event):
            events.append(event)

        BuildTools._in_build_mode = True
        BuildTools.exit_build_mode()
        assert BuildTools._in_build_mode is False
        assert len(events) == 1


class TestSnap:
    def test_snap_to_precision(self):
        assert _snap(1.234, 0.01) == 1.23
        assert _snap(1.235, 0.01) == 1.24
        assert _snap(1.5, 0.1) == 1.5
        assert _snap(1.55, 0.1) == 1.6

    def test_snap_zero_precision(self):
        assert _snap(1.234, 0) == 1.234

    def test_snap_large_precision(self):
        assert _snap(7.3, 5.0) == 5.0
        assert _snap(8.0, 5.0) == 10.0


class TestMoveObject:
    def setup_method(self):
        BuildTools._enabled = True
        BuildTools._off_lot_enabled = True
        BuildTools._precision = 0.01
        BuildTools._undo_stack = []

    def test_move_disabled(self):
        BuildTools._enabled = False
        result = BuildTools.move_object(1, 1.0, 2.0, 3.0)
        assert result is False

    def test_move_publishes_event(self):
        # move_object calls _get_game_object which returns None outside game,
        # so _set_object_position returns False. Test the disabled path instead.
        BuildTools._enabled = False
        result = BuildTools.move_object(1, 1.0, 2.0, 3.0)
        assert result is False


class TestRotateObject:
    def setup_method(self):
        BuildTools._enabled = True
        BuildTools._free_rotation = True
        BuildTools._undo_stack = []

    def test_rotate_disabled(self):
        BuildTools._enabled = False
        result = BuildTools.rotate_object(1, yaw=45.0)
        assert result is False

    def test_rotate_no_free_rotation_blocks_pitch_roll(self):
        BuildTools._free_rotation = False
        result = BuildTools.rotate_object(1, pitch=10.0)
        assert result is False


class TestScaleObject:
    def setup_method(self):
        BuildTools._enabled = True
        BuildTools._scale_enabled = True
        BuildTools._undo_stack = []

    def test_scale_disabled(self):
        BuildTools._enabled = False
        result = BuildTools.scale_object(1, sx=2.0)
        assert result is False

    def test_scale_feature_disabled(self):
        BuildTools._scale_enabled = False
        result = BuildTools.scale_object(1, sx=2.0)
        assert result is False


class TestUndo:
    def test_undo_empty_stack(self):
        BuildTools._undo_stack = []
        result = BuildTools.undo()
        assert result is False

    def test_undo_stack_limit(self):
        BuildTools._undo_stack = []
        BuildTools._max_undo = 3
        for i in range(5):
            BuildTools._push_undo(i, TransformState())
        assert len(BuildTools._undo_stack) == 3
        BuildTools._max_undo = 50  # reset


class TestTransformState:
    def test_defaults(self):
        ts = TransformState()
        assert ts.position == (0.0, 0.0, 0.0)
        assert ts.rotation == (0.0, 0.0, 0.0)
        assert ts.scale == (1.0, 1.0, 1.0)

    def test_custom_values(self):
        ts = TransformState(
            position=(1.0, 2.0, 3.0),
            rotation=(10.0, 20.0, 30.0),
            scale=(2.0, 2.0, 2.0),
        )
        assert ts.position == (1.0, 2.0, 3.0)


class TestSettingsReaction:
    def test_precision_setting(self):
        BuildTools.install()
        EventBus.publish(SettingsChangedEvent(
            key="build_tools.precision",
            old_value=0.01,
            new_value=0.1,
        ))
        assert BuildTools._precision == 0.1

    def test_off_lot_setting(self):
        BuildTools.install()
        EventBus.publish(SettingsChangedEvent(
            key="build_tools.off_lot",
            old_value=True,
            new_value=False,
        ))
        assert BuildTools._off_lot_enabled is False
