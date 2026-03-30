"""
Autonomy Throttle -- game-engine hooks for autonomy evaluation frequency,
multitasking break intervals, and time scale synchronization.

This is the low-level engine that performance.py's adaptive throttling drives.
It implements three strategies derived from decompilation analysis of how the
Simulation Lag Fix mod works:

1. Autonomy frequency throttling (Pattern C: runtime injection)
   -- Wraps AutonomyComponent._run_full_autonomy_gen() to skip ticks for
   off-screen Sims based on a configurable skip ratio.

2. Multitasking break interval extension (Pattern B: tuning modification)
   -- Monkey-patches InstanceManager.load_data_into_class_instances to
   multiply break interval tuning values, reducing autonomy re-evaluation
   frequency and lowering request volume.

3. Time scale synchronization (core Sim Lag Fix pattern)
   -- Monitors tick processing time and adjusts the game clock increment to
   prevent desync between simulation time and wall clock time.

All hooks are reversible via uninstall() which restores original methods.
"""

import time
from dataclasses import dataclass, field

from qol_pack._compat import Event, EventBus, get_logger

log = get_logger("qol.autonomy_throttle")

MOD_ID = "stark_qol_pack.autonomy_throttle"

# ── Game API imports (deferred, may not be available outside game) ──────

try:
    import services
except ImportError:
    services = None

try:
    from autonomy.autonomy_component import AutonomyComponent
except ImportError:
    AutonomyComponent = None

try:
    from sims4.tuning.instance_manager import InstanceManager
except ImportError:
    InstanceManager = None

try:
    from clock import GameClock
except ImportError:
    GameClock = None


# ── Events ─────────────────────────────────────────────────────────────

@dataclass
class AutonomyThrottleAdjustedEvent(Event):
    """Published when the throttle configuration changes at runtime."""
    skip_ratio: int = 2
    break_multiplier: float = 1.5
    sync_enabled: bool = True
    reason: str = ""

    def __post_init__(self):
        super().__init__()


# ── Constants ──────────────────────────────────────────────────────────

DEFAULT_SKIP_RATIO = 2          # Skip every other tick for off-screen Sims
DEFAULT_BREAK_MULTIPLIER = 1.5  # 50% longer between autonomy re-evaluations
DEFAULT_SYNC_ENABLED = True

# Time scale sync thresholds (milliseconds)
TICK_TARGET_MS = 33.3           # ~30 FPS target
TICK_SLOW_THRESHOLD_MS = 50.0   # If a tick takes longer, adjust clock
SYNC_HISTORY_SIZE = 30          # Rolling window for avg tick time


# ── Core Engine ────────────────────────────────────────────────────────

class AutonomyThrottle:
    """Hooks into the game's autonomy evaluation pipeline.

    Provides three strategies for reducing simulation lag:
    - Autonomy frequency throttling (skip ticks for off-screen Sims)
    - Multitasking break interval extension (reduce re-evaluation frequency)
    - Time scale synchronization (prevent simulation desync)

    All hooks are reversible via uninstall().
    """

    _installed = False

    # Configuration
    _skip_ratio = DEFAULT_SKIP_RATIO
    _break_multiplier = DEFAULT_BREAK_MULTIPLIER
    _sync_enabled = DEFAULT_SYNC_ENABLED

    # Saved originals for uninstall
    _original_run_full_autonomy_gen = None
    _original_load_data_into_class_instances = None
    _original_tick_game_clock = None

    # Runtime state
    _tick_counter = 0
    _skipped_ticks = 0
    _total_ticks = 0
    _tick_times: list = []        # Rolling window of tick durations (ms)
    _autonomy_queue_depth = 0

    @classmethod
    def install(cls, skip_ratio=DEFAULT_SKIP_RATIO,
                break_multiplier=DEFAULT_BREAK_MULTIPLIER,
                sync_enabled=DEFAULT_SYNC_ENABLED):
        """Install all autonomy throttle hooks.

        Args:
            skip_ratio: How many ticks to skip for off-screen Sims. 1 = no
                        skipping, 2 = every other tick, 4 = every 4th tick.
            break_multiplier: Multiplier for multitasking break intervals.
                              1.0 = vanilla, 1.5 = 50% longer, 2.0 = double.
            sync_enabled: Whether to enable time scale synchronization.
        """
        if cls._installed:
            log.warn("AutonomyThrottle already installed, skipping")
            return

        cls._skip_ratio = max(1, int(skip_ratio))
        cls._break_multiplier = max(1.0, float(break_multiplier))
        cls._sync_enabled = bool(sync_enabled)

        # Reset metrics
        cls._tick_counter = 0
        cls._skipped_ticks = 0
        cls._total_ticks = 0
        cls._tick_times = []
        cls._autonomy_queue_depth = 0

        # Pattern C: Runtime injection -- wrap autonomy gen
        cls._install_autonomy_skip_hook()

        # Pattern B: Tuning modification -- patch InstanceManager loader
        cls._install_break_interval_hook()

        # Time scale sync -- wrap game clock tick
        if cls._sync_enabled:
            cls._install_time_sync_hook()

        cls._installed = True
        log.info(
            "AutonomyThrottle installed",
            skip_ratio=cls._skip_ratio,
            break_multiplier=cls._break_multiplier,
            sync_enabled=cls._sync_enabled,
        )

    @classmethod
    def uninstall(cls):
        """Remove all hooks and restore original methods."""
        if not cls._installed:
            return

        # Restore autonomy gen
        if AutonomyComponent is not None and cls._original_run_full_autonomy_gen is not None:
            AutonomyComponent._run_full_autonomy_gen = cls._original_run_full_autonomy_gen
            cls._original_run_full_autonomy_gen = None
            log.debug("Restored AutonomyComponent._run_full_autonomy_gen")

        # Restore instance manager loader
        if InstanceManager is not None and cls._original_load_data_into_class_instances is not None:
            InstanceManager.load_data_into_class_instances = cls._original_load_data_into_class_instances
            cls._original_load_data_into_class_instances = None
            log.debug("Restored InstanceManager.load_data_into_class_instances")

        # Restore game clock tick
        if GameClock is not None and cls._original_tick_game_clock is not None:
            GameClock.tick_game_clock = cls._original_tick_game_clock
            cls._original_tick_game_clock = None
            log.debug("Restored GameClock.tick_game_clock")

        cls._installed = False
        log.info("AutonomyThrottle uninstalled, all hooks restored")

    # ── Public API ─────────────────────────────────────────────────────

    @classmethod
    def set_skip_ratio(cls, ratio):
        """Dynamically change how many ticks to skip for off-screen Sims.

        Args:
            ratio: New skip ratio. 1 = no skipping, 2+ = skip ticks.
        """
        old_ratio = cls._skip_ratio
        cls._skip_ratio = max(1, int(ratio))

        EventBus.publish(
            AutonomyThrottleAdjustedEvent(
                skip_ratio=cls._skip_ratio,
                break_multiplier=cls._break_multiplier,
                sync_enabled=cls._sync_enabled,
                reason=f"skip_ratio changed from {old_ratio} to {cls._skip_ratio}",
            ),
            source_mod=MOD_ID,
        )

        log.info(
            "Skip ratio updated",
            old=old_ratio,
            new=cls._skip_ratio,
        )

    @classmethod
    def get_metrics(cls):
        """Return current throttle performance metrics.

        Returns:
            Dict with avg_tick_ms, autonomy_queue_depth, skipped_ticks,
            total_ticks.
        """
        avg_tick_ms = (
            sum(cls._tick_times) / len(cls._tick_times)
            if cls._tick_times else 0.0
        )
        return {
            "avg_tick_ms": round(avg_tick_ms, 2),
            "autonomy_queue_depth": cls._autonomy_queue_depth,
            "skipped_ticks": cls._skipped_ticks,
            "total_ticks": cls._total_ticks,
        }

    # ── Strategy 1: Autonomy Frequency Throttling (Pattern C) ──────────

    @classmethod
    def _install_autonomy_skip_hook(cls):
        """Wrap AutonomyComponent._run_full_autonomy_gen with skip logic."""
        if AutonomyComponent is None:
            log.warn("AutonomyComponent not available, skipping autonomy hook")
            return

        if not hasattr(AutonomyComponent, '_run_full_autonomy_gen'):
            log.warn("_run_full_autonomy_gen not found on AutonomyComponent")
            return

        cls._original_run_full_autonomy_gen = AutonomyComponent._run_full_autonomy_gen

        def _wrapped_run_full_autonomy_gen(self, *args, **kwargs):
            cls._total_ticks += 1

            # Determine if this Sim is on-screen
            is_on_screen = _is_sim_on_screen(self)

            if not is_on_screen:
                cls._tick_counter += 1
                if cls._tick_counter % cls._skip_ratio != 0:
                    cls._skipped_ticks += 1
                    return  # Skip this tick for off-screen Sim

            # Update queue depth estimate
            cls._autonomy_queue_depth = _get_autonomy_queue_depth()

            return cls._original_run_full_autonomy_gen(self, *args, **kwargs)

        AutonomyComponent._run_full_autonomy_gen = _wrapped_run_full_autonomy_gen
        log.debug("Installed autonomy skip hook on _run_full_autonomy_gen")

    # ── Strategy 2: Multitasking Break Interval Extension (Pattern B) ──

    @classmethod
    def _install_break_interval_hook(cls):
        """Patch InstanceManager.load_data_into_class_instances to modify
        autonomy break interval tuning values at load time."""
        if InstanceManager is None:
            log.warn("InstanceManager not available, skipping tuning hook")
            return

        if not hasattr(InstanceManager, 'load_data_into_class_instances'):
            log.warn("load_data_into_class_instances not found on InstanceManager")
            return

        cls._original_load_data_into_class_instances = InstanceManager.load_data_into_class_instances

        def _wrapped_load_data(self, *args, **kwargs):
            result = cls._original_load_data_into_class_instances(self, *args, **kwargs)

            # After vanilla loading completes, modify break interval tunings
            cls._apply_break_interval_overrides(self)

            return result

        InstanceManager.load_data_into_class_instances = _wrapped_load_data
        log.debug("Installed break interval hook on load_data_into_class_instances")

    @classmethod
    def _apply_break_interval_overrides(cls, instance_manager):
        """Walk loaded tuning instances and multiply break interval values.

        Targets autonomy-related tuning entries that control how often Sims
        interrupt their current task to re-evaluate what to do next. Longer
        intervals mean fewer autonomy requests per unit time.
        """
        if cls._break_multiplier == 1.0:
            return  # No modification needed

        try:
            types = instance_manager.types
            if types is None:
                return

            modified_count = 0
            for inst_id, inst_cls in types.items():
                # Look for autonomy-related break interval attributes
                for attr_name in (
                    'autonomy_modifiers_break_interval',
                    'break_interval',
                    'autonomy_recheck_interval',
                ):
                    if hasattr(inst_cls, attr_name):
                        original_value = getattr(inst_cls, attr_name)
                        if isinstance(original_value, (int, float)) and original_value > 0:
                            new_value = original_value * cls._break_multiplier
                            setattr(inst_cls, attr_name, new_value)
                            modified_count += 1

            if modified_count > 0:
                log.debug(
                    "Applied break interval overrides",
                    modified=modified_count,
                    multiplier=cls._break_multiplier,
                )
        except Exception as exc:
            log.error("Failed to apply break interval overrides", error=str(exc))

    # ── Strategy 3: Time Scale Synchronization ─────────────────────────

    @classmethod
    def _install_time_sync_hook(cls):
        """Wrap GameClock.tick_game_clock to monitor tick timing and adjust
        the clock increment when ticks take too long, preventing desync."""
        if GameClock is None:
            log.warn("GameClock not available, skipping time sync hook")
            return

        if not hasattr(GameClock, 'tick_game_clock'):
            log.warn("tick_game_clock not found on GameClock")
            return

        cls._original_tick_game_clock = GameClock.tick_game_clock

        def _wrapped_tick_game_clock(self, *args, **kwargs):
            tick_start = time.perf_counter()

            result = cls._original_tick_game_clock(self, *args, **kwargs)

            tick_elapsed_ms = (time.perf_counter() - tick_start) * 1000.0
            cls._record_tick_time(tick_elapsed_ms)

            # If tick took too long, adjust clock increment to compensate
            cls._maybe_adjust_clock_increment(self, tick_elapsed_ms)

            return result

        GameClock.tick_game_clock = _wrapped_tick_game_clock
        log.debug("Installed time sync hook on tick_game_clock")

    @classmethod
    def _record_tick_time(cls, tick_ms):
        """Record a tick duration into the rolling window."""
        cls._tick_times.append(tick_ms)
        if len(cls._tick_times) > SYNC_HISTORY_SIZE:
            cls._tick_times.pop(0)

    @classmethod
    def _maybe_adjust_clock_increment(cls, game_clock, tick_elapsed_ms):
        """Adjust the game clock increment if ticks are consistently slow.

        When tick processing takes longer than the target, the game clock
        advances more than real time has elapsed, causing desync. This
        scales the clock increment down proportionally to keep simulation
        time aligned with wall clock time.
        """
        if len(cls._tick_times) < 5:
            return  # Need a few samples before adjusting

        avg_tick_ms = sum(cls._tick_times[-5:]) / 5

        if avg_tick_ms <= TICK_TARGET_MS:
            # Ticks are fast enough, ensure clock runs at normal speed
            _set_clock_multiplier(game_clock, 1.0)
            return

        if avg_tick_ms > TICK_SLOW_THRESHOLD_MS:
            # Scale down: if ticks take 2x target, clock advances at 0.5x
            scale_factor = TICK_TARGET_MS / avg_tick_ms
            # Clamp to avoid freezing the clock entirely
            scale_factor = max(0.25, min(1.0, scale_factor))
            _set_clock_multiplier(game_clock, scale_factor)

            log.debug(
                "Time scale adjusted",
                avg_tick_ms=round(avg_tick_ms, 1),
                scale_factor=round(scale_factor, 3),
            )


# ── Internal helpers ────────────────────────────────────────────────────

def _is_sim_on_screen(autonomy_component):
    """Check if the Sim owning this autonomy component is on-screen.

    Uses the camera service if available, falls back to active household
    check.
    """
    try:
        owner = autonomy_component.owner
        if owner is None:
            return False

        # Active Sim is always considered on-screen
        if services is not None:
            client = services.client_manager().get_first_client()
            if client is not None:
                active_sim = client.active_sim
                if active_sim is not None and active_sim.id == owner.id:
                    return True

        # Check if the Sim is visible to the camera
        if hasattr(owner, 'is_on_active_lot'):
            return owner.is_on_active_lot()

        return False
    except (AttributeError, TypeError):
        return True  # Assume on-screen if we can't determine


def _get_autonomy_queue_depth():
    """Estimate the current autonomy request queue depth."""
    try:
        if services is None:
            return 0
        sim_info_manager = services.sim_info_manager()
        if sim_info_manager is None:
            return 0

        depth = 0
        for sim_info in sim_info_manager.get_all():
            sim = sim_info.get_sim_instance()
            if sim is not None and hasattr(sim, 'autonomy_component'):
                if sim.autonomy_component.enabled:
                    depth += 1
        return depth
    except (AttributeError, TypeError):
        return 0


def _set_clock_multiplier(game_clock, multiplier):
    """Apply a multiplier to the game clock's tick increment.

    Modifies the clock speed multiplier attribute if present on the
    GameClock instance.
    """
    try:
        if hasattr(game_clock, '_clock_speed_multiplier'):
            game_clock._clock_speed_multiplier = multiplier
        elif hasattr(game_clock, 'clock_speed_multiplier'):
            game_clock.clock_speed_multiplier = multiplier
    except (AttributeError, TypeError):
        pass
