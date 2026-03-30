"""
Affordance Injector -- universal interaction injection for all game objects.

Centralizes the T.O.O.L.-style pattern of appending SuperInteraction subclasses
to object tuning `_super_affordances` tuples. Instead of each module patching
objects independently, all interaction injections flow through this single registry.

On zone load the injector iterates loaded object tuning, matches against registered
targets, and appends interaction classes to `_super_affordances`. Frozen tuples are
converted to lists, extended, and written back via `setattr()`.

All injections are tracked in an internal registry for conflict detection and
diagnostics. Successful injections publish `AffordanceInjectedEvent`.
"""

from dataclasses import dataclass
from qol_pack._compat import Event, EventBus, Diagnostics, get_logger

# Game engine imports -- graceful degradation outside the Sims 4 runtime
try:
    import services  # type: ignore[import-not-found]
    import sims4.resources  # type: ignore[import-not-found]
    from sims4.resources import Types  # type: ignore[import-not-found]
    from interactions.base.super_interaction import SuperInteraction  # type: ignore[import-not-found]
    _GAME_AVAILABLE = True
except ImportError:
    services = None
    sims4 = None
    Types = None
    SuperInteraction = None
    _GAME_AVAILABLE = False

log = get_logger("qol.affordance_injector")

MOD_ID = "stark_qol_pack.affordance_injector"

# Recognized target type constants
TARGET_ALL_OBJECTS = "all_objects"
TARGET_SIM = "sim"
TARGET_TERRAIN = "terrain"

_BUILTIN_TARGETS = {TARGET_ALL_OBJECTS, TARGET_SIM, TARGET_TERRAIN}


# ── Events ─────────────────────────────────────────────────────────

@dataclass
class AffordanceInjectedEvent(Event):
    """Published after an interaction is successfully injected into object tuning."""
    target_type: str = ""
    interaction_name: str = ""
    source_mod: str = ""
    tuning_id: int = 0

    def __post_init__(self):
        super().__init__()


# ── Core Class ─────────────────────────────────────────────────────

class AffordanceInjector:
    """Centralized affordance injection manager.

    Modules register interactions against target types. On zone load the
    injector patches `_super_affordances` on matching object tuning.
    """

    # {target_type: [(interaction_class, filter_fn, source_mod), ...]}
    _pending: dict = {}

    # {target_type: [{interaction, source_mod, tuning_id, interaction_name}, ...]}
    _injection_registry: dict = {}

    _installed = False

    # ── Public API ─────────────────────────────────────────────────

    @classmethod
    def install(cls):
        """Hook into the object instance manager's load-complete callback."""
        if cls._installed:
            log.debug("AffordanceInjector already installed -- skipping")
            return

        if not _GAME_AVAILABLE:
            log.warn("Game services unavailable -- injection deferred")
            cls._installed = True
            return

        try:
            obj_manager = services.get_instance_manager(Types.OBJECT)
            obj_manager.add_on_load_complete(_on_tuning_loaded)
            log.info("AffordanceInjector installed -- waiting for zone load")
        except Exception as exc:
            Diagnostics.record_error(
                mod_id=MOD_ID,
                error=exc,
                context="Installing affordance injector load-complete hook",
            )
            return

        cls._installed = True

    @classmethod
    def register_interaction(cls, target_type, interaction_class, filter_fn=None,
                             source_mod=MOD_ID):
        """Register an interaction for injection into a target type.

        Args:
            target_type: One of "all_objects", "sim", "terrain", or an integer
                tuning ID for a specific object definition.
            interaction_class: A SuperInteraction subclass to inject.
            filter_fn: Optional callable(tuning) -> bool. If provided, the
                interaction is only injected into tuning for which filter_fn
                returns True. Ignored for integer tuning ID targets.
            source_mod: Mod identifier for diagnostics and conflict tracking.

        Returns:
            True if registration succeeded, False if the interaction was
            already registered for this target.
        """
        target_key = _normalize_target(target_type)

        if target_key not in cls._pending:
            cls._pending[target_key] = []

        # Prevent duplicate registrations
        for existing_cls, _, _ in cls._pending[target_key]:
            if existing_cls is interaction_class:
                log.debug(
                    "Interaction already registered -- skipping",
                    target=target_key,
                    interaction=interaction_class.__name__,
                )
                return False

        cls._pending[target_key].append((interaction_class, filter_fn, source_mod))
        log.info(
            "Interaction registered",
            target=target_key,
            interaction=interaction_class.__name__,
            source_mod=source_mod,
        )
        return True

    @classmethod
    def unregister_interaction(cls, target_type, interaction_class):
        """Remove a previously registered interaction.

        Args:
            target_type: The target type it was registered under.
            interaction_class: The interaction class to remove.

        Returns:
            True if the interaction was found and removed, False otherwise.
        """
        target_key = _normalize_target(target_type)

        entries = cls._pending.get(target_key, [])
        for i, (cls_ref, _, _) in enumerate(entries):
            if cls_ref is interaction_class:
                entries.pop(i)
                log.info(
                    "Interaction unregistered",
                    target=target_key,
                    interaction=interaction_class.__name__,
                )
                # Also clean from the injection registry
                cls._remove_from_registry(target_key, interaction_class)
                return True

        log.debug(
            "Interaction not found for unregistration",
            target=target_key,
            interaction=interaction_class.__name__,
        )
        return False

    @classmethod
    def list_injections(cls):
        """Return a list of all active injections with metadata.

        Returns:
            List of dicts with keys: source_mod, target, interaction,
            interaction_name, tuning_id.
        """
        results = []
        for target_key, entries in cls._injection_registry.items():
            for entry in entries:
                results.append({
                    "source_mod": entry["source_mod"],
                    "target": target_key,
                    "interaction": entry["interaction"],
                    "interaction_name": entry["interaction_name"],
                    "tuning_id": entry["tuning_id"],
                })
        return results

    @classmethod
    def inject_all(cls):
        """Run injection against all currently loaded tuning.

        Called automatically via the on_load_complete hook. Can also be
        called manually for late-registered interactions.
        """
        if not _GAME_AVAILABLE:
            log.warn("Game services unavailable -- cannot inject")
            return

        try:
            obj_manager = services.get_instance_manager(Types.OBJECT)
        except Exception as exc:
            Diagnostics.record_error(
                mod_id=MOD_ID,
                error=exc,
                context="Getting object instance manager for injection",
            )
            return

        injected_count = 0

        for tuning_id, tuning in obj_manager.types.items():
            injected_count += cls._inject_into_tuning(tuning_id, tuning)

        # Handle Sim-specific injections
        injected_count += cls._inject_sim_affordances()

        # Handle terrain-specific injections
        injected_count += cls._inject_terrain_affordances()

        log.info("Injection pass complete", total_injected=injected_count)

    @classmethod
    def reset(cls):
        """Clear all registrations and injection records. For testing."""
        cls._pending.clear()
        cls._injection_registry.clear()
        cls._installed = False
        log.info("AffordanceInjector reset")

    # ── Internal Methods ───────────────────────────────────────────

    @classmethod
    def _inject_into_tuning(cls, tuning_id, tuning):
        """Inject registered interactions into a single tuning definition.

        Returns the number of interactions injected.
        """
        count = 0

        # Collect interactions that target this tuning
        to_inject = []

        # "all_objects" targets apply everywhere
        for interaction_class, filter_fn, source_mod in cls._pending.get(TARGET_ALL_OBJECTS, []):
            if filter_fn is not None and not filter_fn(tuning):
                continue
            to_inject.append((interaction_class, source_mod))

        # Specific tuning ID targets
        for interaction_class, filter_fn, source_mod in cls._pending.get(tuning_id, []):
            to_inject.append((interaction_class, source_mod))

        if not to_inject:
            return 0

        # Patch _super_affordances
        for interaction_class, source_mod in to_inject:
            success = _append_affordance(tuning, interaction_class)
            if success:
                cls._record_injection(
                    target_key=tuning_id,
                    interaction_class=interaction_class,
                    source_mod=source_mod,
                    tuning_id=tuning_id,
                )
                EventBus.publish(
                    AffordanceInjectedEvent(
                        target_type=str(tuning_id),
                        interaction_name=interaction_class.__name__,
                        source_mod=source_mod,
                        tuning_id=tuning_id,
                    ),
                    source_mod=MOD_ID,
                )
                count += 1

        return count

    @classmethod
    def _inject_sim_affordances(cls):
        """Inject interactions registered under TARGET_SIM."""
        entries = cls._pending.get(TARGET_SIM, [])
        if not entries:
            return 0

        try:
            sim_instance_manager = services.get_instance_manager(Types.SIM_INFO)
        except Exception:
            log.debug("SIM_INFO instance manager unavailable")
            return 0

        count = 0
        for tuning_id, tuning in sim_instance_manager.types.items():
            for interaction_class, filter_fn, source_mod in entries:
                if filter_fn is not None and not filter_fn(tuning):
                    continue
                success = _append_affordance(tuning, interaction_class)
                if success:
                    cls._record_injection(
                        target_key=TARGET_SIM,
                        interaction_class=interaction_class,
                        source_mod=source_mod,
                        tuning_id=tuning_id,
                    )
                    EventBus.publish(
                        AffordanceInjectedEvent(
                            target_type=TARGET_SIM,
                            interaction_name=interaction_class.__name__,
                            source_mod=source_mod,
                            tuning_id=tuning_id,
                        ),
                        source_mod=MOD_ID,
                    )
                    count += 1
        return count

    @classmethod
    def _inject_terrain_affordances(cls):
        """Inject interactions registered under TARGET_TERRAIN."""
        entries = cls._pending.get(TARGET_TERRAIN, [])
        if not entries:
            return 0

        try:
            terrain_service = services.terrain_service
            terrain_definition = getattr(terrain_service, 'TERRAIN_DEFINITION', None)
        except (AttributeError, TypeError):
            log.debug("Terrain service unavailable")
            return 0

        if terrain_definition is None:
            return 0

        count = 0
        for interaction_class, filter_fn, source_mod in entries:
            if filter_fn is not None and not filter_fn(terrain_definition):
                continue
            success = _append_affordance(terrain_definition, interaction_class)
            if success:
                cls._record_injection(
                    target_key=TARGET_TERRAIN,
                    interaction_class=interaction_class,
                    source_mod=source_mod,
                    tuning_id=0,
                )
                EventBus.publish(
                    AffordanceInjectedEvent(
                        target_type=TARGET_TERRAIN,
                        interaction_name=interaction_class.__name__,
                        source_mod=source_mod,
                        tuning_id=0,
                    ),
                    source_mod=MOD_ID,
                )
                count += 1
        return count

    @classmethod
    def _record_injection(cls, target_key, interaction_class, source_mod, tuning_id):
        """Track an injection in the registry for diagnostics."""
        if target_key not in cls._injection_registry:
            cls._injection_registry[target_key] = []

        cls._injection_registry[target_key].append({
            "interaction": interaction_class,
            "interaction_name": interaction_class.__name__,
            "source_mod": source_mod,
            "tuning_id": tuning_id,
        })

    @classmethod
    def _remove_from_registry(cls, target_key, interaction_class):
        """Remove all registry entries for an interaction under a target."""
        entries = cls._injection_registry.get(target_key, [])
        cls._injection_registry[target_key] = [
            e for e in entries if e["interaction"] is not interaction_class
        ]


# ── Internal helpers (game API wrappers) ────────────────────────────

def _normalize_target(target_type):
    """Normalize a target_type to a consistent key.

    Strings are lowered; integers are kept as-is (tuning IDs).
    """
    if isinstance(target_type, int):
        return target_type
    if isinstance(target_type, str):
        lowered = target_type.lower().strip()
        if lowered in _BUILTIN_TARGETS:
            return lowered
        # Try to parse as integer tuning ID
        try:
            return int(lowered)
        except ValueError:
            pass
        return lowered
    return target_type


def _append_affordance(tuning, interaction_class):
    """Append an interaction class to a tuning's _super_affordances.

    Handles tuple immutability by converting to list, appending, and
    writing back as a tuple via setattr().

    Returns:
        True if the affordance was appended, False if it was already
        present or the operation failed.
    """
    try:
        current = getattr(tuning, '_super_affordances', ())

        # Skip if already injected
        if interaction_class in current:
            return False

        # Convert frozen tuple to mutable list, append, convert back
        affordance_list = list(current)
        affordance_list.append(interaction_class)
        setattr(tuning, '_super_affordances', tuple(affordance_list))
        return True
    except Exception as exc:
        Diagnostics.record_error(
            mod_id=MOD_ID,
            error=exc,
            context=f"Appending {interaction_class.__name__} to {tuning}",
        )
        return False


def _on_tuning_loaded(manager):
    """Callback for instance manager on_load_complete.

    Triggers the full injection pass once all object tuning has loaded.
    """
    log.info("Object tuning loaded -- starting injection pass")
    AffordanceInjector.inject_all()
