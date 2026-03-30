"""Tests for the Performance Optimizer module."""

from stark_framework.core.events import EventBus

from qol_pack.events import (
    BuildModeEnteredEvent,
    BuildModeExitedEvent,
    ThrottleLevelChangedEvent,
    SettingsChangedEvent,
)
from qol_pack.modules.performance import (
    PerformanceOptimizer,
    THROTTLE_NONE,
    THROTTLE_LIGHT,
    THROTTLE_MODERATE,
    THROTTLE_AGGRESSIVE,
)


class TestPerformanceInstall:
    def test_install_subscribes_to_events(self):
        PerformanceOptimizer.install()
        build_subs = EventBus.get_subscribers(BuildModeEnteredEvent)
        settings_subs = EventBus.get_subscribers(SettingsChangedEvent)
        assert any(s.mod_id == "stark_qol_pack.performance" for s in build_subs)
        assert any(s.mod_id == "stark_qol_pack.performance" for s in settings_subs)


class TestAutonomyThrottling:
    def setup_method(self):
        PerformanceOptimizer._enabled = True
        PerformanceOptimizer._paused = False
        PerformanceOptimizer._autonomy_tick_counter = 0

    def test_on_screen_sim_always_runs(self):
        PerformanceOptimizer._throttle_level = THROTTLE_AGGRESSIVE
        assert PerformanceOptimizer.should_run_autonomy(1, is_on_screen=True)

    def test_disabled_always_runs(self):
        PerformanceOptimizer._enabled = False
        assert PerformanceOptimizer.should_run_autonomy(1, is_on_screen=False)

    def test_paused_always_runs(self):
        PerformanceOptimizer._paused = True
        PerformanceOptimizer._throttle_level = THROTTLE_AGGRESSIVE
        assert PerformanceOptimizer.should_run_autonomy(1, is_on_screen=False)

    def test_no_throttle_always_runs(self):
        PerformanceOptimizer._throttle_level = THROTTLE_NONE
        for _ in range(10):
            assert PerformanceOptimizer.should_run_autonomy(1, is_on_screen=False)

    def test_light_throttle_skips_half(self):
        PerformanceOptimizer._throttle_level = THROTTLE_LIGHT
        results = []
        for _ in range(10):
            results.append(
                PerformanceOptimizer.should_run_autonomy(1, is_on_screen=False)
            )
        # Every other tick should run (skip ratio = 2)
        assert results.count(True) == 5

    def test_aggressive_throttle_skips_most(self):
        PerformanceOptimizer._throttle_level = THROTTLE_AGGRESSIVE
        results = []
        for _ in range(16):
            results.append(
                PerformanceOptimizer.should_run_autonomy(1, is_on_screen=False)
            )
        # Skip ratio = 8, so 2 out of 16 should run
        assert results.count(True) == 2


class TestPathfindingDebounce:
    def setup_method(self):
        PerformanceOptimizer._enabled = True
        PerformanceOptimizer._paused = False
        PerformanceOptimizer._last_pathfind_time = {}

    def test_no_throttle_no_debounce(self):
        PerformanceOptimizer._throttle_level = THROTTLE_NONE
        assert PerformanceOptimizer.should_recalculate_path(1)
        assert PerformanceOptimizer.should_recalculate_path(1)

    def test_disabled_no_debounce(self):
        PerformanceOptimizer._enabled = False
        PerformanceOptimizer._throttle_level = THROTTLE_AGGRESSIVE
        assert PerformanceOptimizer.should_recalculate_path(1)


class TestStatDecay:
    def setup_method(self):
        PerformanceOptimizer._enabled = True
        PerformanceOptimizer._paused = False
        PerformanceOptimizer._deferred_decay_sims = set()

    def test_critical_stats_always_decay(self):
        PerformanceOptimizer._throttle_level = THROTTLE_AGGRESSIVE
        assert PerformanceOptimizer.should_decay_stat(1, "hunger", is_critical=True)

    def test_non_critical_deferred_at_aggressive(self):
        PerformanceOptimizer._throttle_level = THROTTLE_AGGRESSIVE
        assert not PerformanceOptimizer.should_decay_stat(1, "fun", is_critical=False)
        assert 1 in PerformanceOptimizer._deferred_decay_sims

    def test_non_critical_runs_at_moderate(self):
        PerformanceOptimizer._throttle_level = THROTTLE_MODERATE
        assert PerformanceOptimizer.should_decay_stat(1, "fun", is_critical=False)


class TestSaveOptimization:
    def setup_method(self):
        PerformanceOptimizer._enabled = True

    def test_changed_objects_always_saved(self):
        PerformanceOptimizer._throttle_level = THROTTLE_AGGRESSIVE
        assert PerformanceOptimizer.on_object_save(1, has_changed=True)

    def test_unchanged_saved_at_none(self):
        PerformanceOptimizer._throttle_level = THROTTLE_NONE
        assert PerformanceOptimizer.on_object_save(1, has_changed=False)

    def test_unchanged_skipped_at_moderate(self):
        PerformanceOptimizer._throttle_level = THROTTLE_MODERATE
        assert not PerformanceOptimizer.on_object_save(1, has_changed=False)


class TestBuildModePause:
    def test_build_mode_pauses_throttling(self):
        PerformanceOptimizer.install()
        PerformanceOptimizer._paused = False

        EventBus.publish(BuildModeEnteredEvent())
        assert PerformanceOptimizer._paused is True

        EventBus.publish(BuildModeExitedEvent())
        assert PerformanceOptimizer._paused is False


class TestAdaptiveTuning:
    def setup_method(self):
        PerformanceOptimizer._enabled = True
        PerformanceOptimizer._paused = False
        PerformanceOptimizer._frame_times = []
        PerformanceOptimizer._throttle_level = THROTTLE_NONE
        PerformanceOptimizer._target_fps = 30.0
        PerformanceOptimizer._last_report_time = 0.0

    def test_throttle_increases_on_low_fps(self):
        events = []

        @EventBus.on(ThrottleLevelChangedEvent)
        def capture(event):
            events.append(event)

        # Simulate 10 frames at ~15 FPS (66ms per frame)
        for _ in range(10):
            PerformanceOptimizer.record_frame_time(66.0)

        assert PerformanceOptimizer._throttle_level > THROTTLE_NONE
        assert len(events) >= 1

    def test_throttle_decreases_on_high_fps(self):
        PerformanceOptimizer._throttle_level = THROTTLE_MODERATE

        events = []

        @EventBus.on(ThrottleLevelChangedEvent)
        def capture(event):
            events.append(event)

        # Simulate 10 frames at ~60 FPS (16ms per frame)
        for _ in range(10):
            PerformanceOptimizer.record_frame_time(16.0)

        assert PerformanceOptimizer._throttle_level < THROTTLE_MODERATE
        assert len(events) >= 1

    def test_no_adjustment_with_insufficient_data(self):
        PerformanceOptimizer.record_frame_time(100.0)
        assert PerformanceOptimizer._throttle_level == THROTTLE_NONE


class TestGetStatus:
    def test_status_dict_keys(self):
        status = PerformanceOptimizer.get_status()
        expected_keys = {
            "enabled", "paused", "throttle_level", "target_fps",
            "current_fps", "frame_samples", "deferred_decay_sims",
        }
        assert set(status.keys()) == expected_keys
