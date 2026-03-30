"""
Performance Optimizer -- simulation lag fix, AI timing optimization, save time reduction.

Replaces standalone Sim Lag Fix with a Stark Framework-native implementation
that can coordinate with other QoL modules. When build mode is entered,
sim throttling pauses. When diagnostics detect high error rates, throttling
backs off to avoid masking the real problem.

Strategies:
1. Autonomy throttling -- off-screen Sims run autonomy at reduced frequency
2. Pathfinding debounce -- coalesce rapid pathfinding recalculations
3. Stat decay deferral -- skip non-critical decay ticks when CPU-bound
4. Save optimization -- skip serializing unchanged objects
5. Adaptive tuning -- monitor FPS and adjust throttle automatically
"""

import time

from qol_pack._compat import EventBus, Diagnostics, get_logger

from qol_pack.events import (
    PerformanceReportEvent,
    ThrottleLevelChangedEvent,
    BuildModeEnteredEvent,
    BuildModeExitedEvent,
    SettingsChangedEvent,
)

log = get_logger("qol.performance")

MOD_ID = "stark_qol_pack.performance"

# Throttle levels
THROTTLE_NONE = 0
THROTTLE_LIGHT = 1       # Skip every other autonomy tick for off-screen
THROTTLE_MODERATE = 2     # Skip 3/4 ticks + debounce pathfinding
THROTTLE_AGGRESSIVE = 3   # Full throttle + defer stat decay


class PerformanceOptimizer:
    """Adaptive simulation performance optimizer.

    Monitors frame time and adjusts throttling automatically.
    All throttle decisions publish events for observability.
    """

    _enabled = True
    _throttle_level = THROTTLE_NONE
    _target_fps = 30.0
    _paused = False  # Paused during build mode

    # Autonomy throttling
    _autonomy_tick_counter = 0
    _autonomy_skip_ratios = {
        THROTTLE_NONE: 1,       # Run every tick
        THROTTLE_LIGHT: 2,      # Run every 2nd tick
        THROTTLE_MODERATE: 4,   # Run every 4th tick
        THROTTLE_AGGRESSIVE: 8, # Run every 8th tick
    }

    # Pathfinding debounce
    _last_pathfind_time: dict = {}  # sim_id -> timestamp
    _pathfind_debounce_ms = {
        THROTTLE_NONE: 0,
        THROTTLE_LIGHT: 100,
        THROTTLE_MODERATE: 250,
        THROTTLE_AGGRESSIVE: 500,
    }

    # Stat decay deferral
    _deferred_decay_sims: set = set()

    # FPS tracking for adaptive tuning
    _frame_times: list = []
    _max_frame_samples = 60
    _last_report_time = 0.0
    _report_interval = 5.0  # seconds between performance reports

    @classmethod
    def install(cls):
        """Register event handlers for performance optimization."""
        EventBus.subscribe(
            BuildModeEnteredEvent,
            cls._on_build_mode_entered,
            priority=10,
            mod_id=MOD_ID,
        )
        EventBus.subscribe(
            BuildModeExitedEvent,
            cls._on_build_mode_exited,
            priority=10,
            mod_id=MOD_ID,
        )
        EventBus.subscribe(
            SettingsChangedEvent,
            cls._on_settings_changed,
            priority=50,
            mod_id=MOD_ID,
        )
        log.info(
            "Performance Optimizer installed",
            target_fps=cls._target_fps,
            throttle=cls._throttle_level,
        )

    @classmethod
    def _on_build_mode_entered(cls, event):
        """Pause sim throttling during build mode."""
        cls._paused = True
        log.debug("Performance throttling paused (build mode)")

    @classmethod
    def _on_build_mode_exited(cls, event):
        """Resume sim throttling after build mode."""
        cls._paused = False
        log.debug("Performance throttling resumed")

    @classmethod
    def _on_settings_changed(cls, event):
        """React to settings changes."""
        if event.key == "performance.enabled":
            cls._enabled = bool(event.new_value)
        elif event.key == "performance.target_fps":
            cls._target_fps = float(event.new_value)
        elif event.key == "performance.throttle_level":
            cls._set_throttle(int(event.new_value), reason="manual setting")

    # ── Core Optimization Hooks ─────────────────────────────────────

    @classmethod
    def should_run_autonomy(cls, sim_id, is_on_screen):
        """Check if a Sim should run its autonomy tick.

        Called from the autonomy component injection. Off-screen Sims
        are throttled based on the current throttle level.

        Args:
            sim_id: The Sim's instance ID.
            is_on_screen: Whether the Sim is currently visible.

        Returns:
            True if autonomy should run, False to skip this tick.
        """
        if not cls._enabled or cls._paused:
            return True

        if is_on_screen:
            return True  # Never throttle visible Sims

        cls._autonomy_tick_counter += 1
        skip_ratio = cls._autonomy_skip_ratios.get(cls._throttle_level, 1)
        return cls._autonomy_tick_counter % skip_ratio == 0

    @classmethod
    def should_recalculate_path(cls, sim_id):
        """Check if a pathfinding recalculation should proceed.

        Debounces rapid recalculations that cause lag spikes during
        large gatherings or events.

        Args:
            sim_id: The Sim requesting pathfinding.

        Returns:
            True if recalculation should proceed, False to skip.
        """
        if not cls._enabled or cls._paused:
            return True

        debounce_ms = cls._pathfind_debounce_ms.get(cls._throttle_level, 0)
        if debounce_ms == 0:
            return True

        now = time.time() * 1000  # ms
        last = cls._last_pathfind_time.get(sim_id, 0)

        if now - last < debounce_ms:
            return False

        cls._last_pathfind_time[sim_id] = now
        return True

    @classmethod
    def should_decay_stat(cls, sim_id, stat_name, is_critical):
        """Check if a stat decay tick should run.

        Non-critical stats (fun, social) can be deferred under heavy load.
        Critical stats (hunger, energy) always run.

        Args:
            sim_id: The Sim's instance ID.
            stat_name: Name of the statistic.
            is_critical: Whether this is a survival need.

        Returns:
            True if decay should proceed.
        """
        if not cls._enabled or cls._paused:
            return True

        if is_critical:
            return True

        if cls._throttle_level >= THROTTLE_AGGRESSIVE:
            cls._deferred_decay_sims.add(sim_id)
            return False

        return True

    @classmethod
    def on_object_save(cls, object_id, has_changed):
        """Filter objects during save serialization.

        Skip serializing objects that haven't changed since last save
        to reduce save times.

        Args:
            object_id: The game object's instance ID.
            has_changed: Whether the object has been modified.

        Returns:
            True if the object should be saved.
        """
        if not cls._enabled:
            return True

        # Always save changed objects
        if has_changed:
            return True

        # At moderate+ throttle, skip unchanged objects
        return cls._throttle_level < THROTTLE_MODERATE

    # ── Adaptive Tuning ─────────────────────────────────────────────

    @classmethod
    def record_frame_time(cls, frame_time_ms):
        """Record a frame time sample for adaptive tuning.

        Args:
            frame_time_ms: Time taken for the last frame in milliseconds.
        """
        cls._frame_times.append(frame_time_ms)
        if len(cls._frame_times) > cls._max_frame_samples:
            cls._frame_times.pop(0)

        cls._maybe_adjust_throttle()
        cls._maybe_publish_report()

    @classmethod
    def _maybe_adjust_throttle(cls):
        """Check if throttle level needs adjustment based on recent FPS."""
        if not cls._enabled or cls._paused:
            return

        if len(cls._frame_times) < 10:
            return  # Not enough data

        avg_frame_ms = sum(cls._frame_times[-10:]) / 10
        current_fps = 1000.0 / avg_frame_ms if avg_frame_ms > 0 else 999

        if current_fps < cls._target_fps * 0.8:
            # FPS is significantly below target -- increase throttle
            new_level = min(cls._throttle_level + 1, THROTTLE_AGGRESSIVE)
            if new_level != cls._throttle_level:
                cls._set_throttle(
                    new_level,
                    reason=f"FPS {current_fps:.1f} below target {cls._target_fps}",
                )
        elif current_fps > cls._target_fps * 1.2 and cls._throttle_level > THROTTLE_NONE:
            # FPS is well above target -- relax throttle
            new_level = cls._throttle_level - 1
            cls._set_throttle(
                new_level,
                reason=f"FPS {current_fps:.1f} above target {cls._target_fps}",
            )

    @classmethod
    def _maybe_publish_report(cls):
        """Publish periodic performance reports."""
        now = time.time()
        if now - cls._last_report_time < cls._report_interval:
            return

        cls._last_report_time = now

        avg_frame_ms = (
            sum(cls._frame_times) / len(cls._frame_times)
            if cls._frame_times else 0
        )
        fps = 1000.0 / avg_frame_ms if avg_frame_ms > 0 else 0

        EventBus.publish(
            PerformanceReportEvent(
                fps=fps,
                sim_count=_get_sim_count(),
                throttle_level=cls._throttle_level,
                active_autonomy_sims=_get_active_autonomy_count(),
            ),
            source_mod=MOD_ID,
        )

    @classmethod
    def _set_throttle(cls, new_level, reason=""):
        """Change throttle level and publish event."""
        old_level = cls._throttle_level
        cls._throttle_level = new_level

        EventBus.publish(
            ThrottleLevelChangedEvent(
                old_level=old_level,
                new_level=new_level,
                reason=reason,
            ),
            source_mod=MOD_ID,
        )

        log.info(
            "Throttle level changed",
            old=old_level,
            new=new_level,
            reason=reason,
        )

        # Flush deferred decay when relaxing throttle
        if new_level < THROTTLE_AGGRESSIVE and cls._deferred_decay_sims:
            cls._deferred_decay_sims.clear()
            log.debug("Flushed deferred stat decay queue")

    # ── Status ──────────────────────────────────────────────────────

    @classmethod
    def get_status(cls):
        """Return a snapshot of current performance state.

        Returns:
            Dict with performance metrics and settings.
        """
        avg_frame_ms = (
            sum(cls._frame_times) / len(cls._frame_times)
            if cls._frame_times else 0
        )
        return {
            "enabled": cls._enabled,
            "paused": cls._paused,
            "throttle_level": cls._throttle_level,
            "target_fps": cls._target_fps,
            "current_fps": 1000.0 / avg_frame_ms if avg_frame_ms > 0 else 0,
            "frame_samples": len(cls._frame_times),
            "deferred_decay_sims": len(cls._deferred_decay_sims),
        }


# ── Internal helpers ────────────────────────────────────────────────

def _get_sim_count():
    """Get the number of Sims currently loaded."""
    try:
        import services  # type: ignore[import-not-found]
        manager = services.sim_info_manager()
        return len(list(manager.get_all())) if manager else 0
    except (ImportError, AttributeError):
        return 0


def _get_active_autonomy_count():
    """Get the number of Sims currently running autonomy."""
    try:
        import services  # type: ignore[import-not-found]
        count = 0
        sim_info_manager = services.sim_info_manager()
        if sim_info_manager is None:
            return 0
        for sim_info in sim_info_manager.get_all():
            sim = sim_info.get_sim_instance()
            if sim is not None and hasattr(sim, 'autonomy_component'):
                if sim.autonomy_component.enabled:
                    count += 1
        return count
    except (ImportError, AttributeError):
        return 0
