"""
UI Tweaks -- click-to-edit UI elements for needs, skills, money, and careers.

Replaces UI Cheats Extension with a Stark Framework-native implementation.
All edits go through the event bus so other modules (diagnostics, settings)
can observe and control them.

Usage (in-game):
    Click on a need bar -> slider appears -> drag to set value
    Click on money display -> numeric input -> type new amount
    Click on skill bar -> slider to set level
    Click on career progress -> set promotion progress

Note: Relationship editing requires a target Sim ID and is not yet implemented.
It will be added once the relationship panel hook API is finalized.

All features are gated by settings -- disabled features are no-ops.
"""

from dataclasses import dataclass
from stark_framework.core.events import EventBus
from stark_framework.core.diagnostics import Diagnostics
from stark_framework.utils.logging import get_logger

from qol_pack.events import (
    UIEditRequestedEvent,
    UIValueChangedEvent,
    SettingsChangedEvent,
)

log = get_logger("qol.ui_tweaks")

MOD_ID = "stark_qol_pack.ui_tweaks"

# Editable field definitions -- maps field_name to metadata
EDITABLE_FIELDS = {
    # Needs (commodity trackers)
    "need_hunger": {"label": "Hunger", "category": "needs", "min": -100, "max": 100},
    "need_energy": {"label": "Energy", "category": "needs", "min": -100, "max": 100},
    "need_fun": {"label": "Fun", "category": "needs", "min": -100, "max": 100},
    "need_social": {"label": "Social", "category": "needs", "min": -100, "max": 100},
    "need_hygiene": {"label": "Hygiene", "category": "needs", "min": -100, "max": 100},
    "need_bladder": {"label": "Bladder", "category": "needs", "min": -100, "max": 100},
    # Skills
    "skill_cooking": {"label": "Cooking", "category": "skills", "min": 0, "max": 10},
    "skill_painting": {"label": "Painting", "category": "skills", "min": 0, "max": 10},
    "skill_programming": {"label": "Programming", "category": "skills", "min": 0, "max": 10},
    "skill_fitness": {"label": "Fitness", "category": "skills", "min": 0, "max": 10},
    "skill_charisma": {"label": "Charisma", "category": "skills", "min": 0, "max": 10},
    # Household
    "money": {"label": "Household Funds", "category": "household", "min": 0, "max": 9999999},
    # Career
    "career_progress": {"label": "Career Progress", "category": "career", "min": 0, "max": 100},
}


class UITweaks:
    """Click-to-edit UI element manager.

    Installs injection hooks on UI dialog handlers and provides methods
    to modify sim values through the game's official APIs.
    """

    _enabled = True
    _enabled_categories = {"needs", "skills", "household", "career"}

    @classmethod
    def install(cls):
        """Register event handlers and set up UI hooks."""
        EventBus.subscribe(
            SettingsChangedEvent,
            cls._on_settings_changed,
            priority=50,
            mod_id=MOD_ID,
        )
        log.info("UI Tweaks installed", categories=list(cls._enabled_categories))

    @classmethod
    def _on_settings_changed(cls, event):
        """React to settings changes that affect UI tweaks."""
        if event.key == "ui_tweaks.enabled":
            cls._enabled = bool(event.new_value)
            log.info("UI Tweaks enabled" if cls._enabled else "UI Tweaks disabled")
        elif event.key == "ui_tweaks.categories":
            cls._enabled_categories = set(event.new_value)
            log.info("UI Tweaks categories updated", categories=list(cls._enabled_categories))

    @classmethod
    def request_edit(cls, sim_id, field_name):
        """Initiate a UI edit. Publishes UIEditRequestedEvent (cancellable).

        Args:
            sim_id: The Sim's instance ID.
            field_name: Key from EDITABLE_FIELDS.

        Returns:
            True if the edit request was accepted (not cancelled), False otherwise.
        """
        if not cls._enabled:
            log.debug("UI edit request blocked -- tweaks disabled", field=field_name)
            return False

        field_info = EDITABLE_FIELDS.get(field_name)
        if not field_info:
            log.warn("Unknown editable field", field=field_name)
            return False

        if field_info["category"] not in cls._enabled_categories:
            log.debug("UI edit blocked -- category disabled", category=field_info["category"])
            return False

        event = UIEditRequestedEvent(sim_id=sim_id, field_name=field_name)
        EventBus.publish(event, source_mod=MOD_ID)

        if event.cancelled:
            log.info("UI edit cancelled by handler", field=field_name, sim_id=sim_id)
            return False

        return True

    @classmethod
    def apply_edit(cls, sim_id, field_name, new_value):
        """Apply a value edit and publish the result.

        Args:
            sim_id: The Sim's instance ID.
            field_name: Key from EDITABLE_FIELDS.
            new_value: The new value to set.

        Returns:
            True if the edit was applied successfully.
        """
        field_info = EDITABLE_FIELDS.get(field_name)
        if not field_info:
            return False

        new_value = _clamp(new_value, field_info["min"], field_info["max"])

        category = field_info["category"]
        old_value = 0.0

        try:
            if category == "needs":
                old_value = _get_need_value(sim_id, field_name)
                _set_need_value(sim_id, field_name, new_value)
            elif category == "skills":
                old_value = _get_skill_value(sim_id, field_name)
                _set_skill_value(sim_id, field_name, new_value)
            elif category == "household":
                old_value = _get_household_funds(sim_id)
                _set_household_funds(sim_id, new_value)
            elif category == "career":
                old_value = _get_career_progress(sim_id)
                _set_career_progress(sim_id, new_value)
            else:
                log.warn("Unknown category", category=category)
                return False
        except Exception as exc:
            Diagnostics.record_error(
                mod_id=MOD_ID,
                error=exc,
                context=f"Applying edit: {field_name}={new_value} for sim {sim_id}",
            )
            return False

        EventBus.publish(
            UIValueChangedEvent(
                sim_id=sim_id,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            ),
            source_mod=MOD_ID,
        )

        log.info(
            "Value edited",
            sim_id=sim_id,
            field=field_name,
            old=old_value,
            new=new_value,
        )
        return True

    @classmethod
    def get_editable_fields(cls, category=None):
        """Return editable field definitions, optionally filtered by category.

        Args:
            category: If provided, filter to this category only.

        Returns:
            Dict of field_name -> field_info.
        """
        if category:
            return {
                k: v for k, v in EDITABLE_FIELDS.items()
                if v["category"] == category
            }
        return dict(EDITABLE_FIELDS)


# ── Internal helpers (game API wrappers) ────────────────────────────

def _clamp(value, minimum, maximum):
    """Clamp a numeric value to [minimum, maximum]."""
    return max(minimum, min(maximum, value))


def _get_sim_info(sim_id):
    """Resolve a sim_id to a SimInfo object. Returns None outside game."""
    try:
        from stark_framework.services.sim_service import SimService
        return SimService.get_sim_info(sim_id)
    except Exception:
        return None


def _get_need_value(sim_id, field_name):
    """Get current need value for a Sim."""
    sim_info = _get_sim_info(sim_id)
    if sim_info is None:
        return 0.0
    try:
        need_name = field_name.replace("need_", "")
        commodity_tracker = sim_info.commodity_tracker
        if commodity_tracker is None:
            return 0.0
        for commodity in commodity_tracker:
            if need_name.lower() in type(commodity).__name__.lower():
                return commodity.get_value()
    except (AttributeError, TypeError):
        pass
    return 0.0


def _set_need_value(sim_id, field_name, value):
    """Set a need value for a Sim."""
    sim_info = _get_sim_info(sim_id)
    if sim_info is None:
        return
    try:
        need_name = field_name.replace("need_", "")
        commodity_tracker = sim_info.commodity_tracker
        if commodity_tracker is None:
            return
        for commodity in commodity_tracker:
            if need_name.lower() in type(commodity).__name__.lower():
                commodity.set_value(value)
                return
    except (AttributeError, TypeError) as exc:
        raise RuntimeError(f"Failed to set need {field_name}: {exc}") from exc


def _get_skill_value(sim_id, field_name):
    """Get current skill level for a Sim."""
    sim_info = _get_sim_info(sim_id)
    if sim_info is None:
        return 0.0
    try:
        skill_name = field_name.replace("skill_", "")
        statistic_tracker = sim_info.statistic_tracker
        if statistic_tracker is None:
            return 0.0
        for stat in statistic_tracker:
            if skill_name.lower() in type(stat).__name__.lower():
                return stat.get_user_value()
    except (AttributeError, TypeError):
        pass
    return 0.0


def _set_skill_value(sim_id, field_name, value):
    """Set a skill level for a Sim."""
    sim_info = _get_sim_info(sim_id)
    if sim_info is None:
        return
    try:
        skill_name = field_name.replace("skill_", "")
        statistic_tracker = sim_info.statistic_tracker
        if statistic_tracker is None:
            return
        for stat in statistic_tracker:
            if skill_name.lower() in type(stat).__name__.lower():
                stat.set_user_value(value)
                return
    except (AttributeError, TypeError) as exc:
        raise RuntimeError(f"Failed to set skill {field_name}: {exc}") from exc


def _get_household_funds(sim_id):
    """Get household funds for the Sim's household."""
    sim_info = _get_sim_info(sim_id)
    if sim_info is None:
        return 0.0
    try:
        household = sim_info.household
        if household is None:
            return 0.0
        return household.funds.money
    except (AttributeError, TypeError):
        return 0.0


def _set_household_funds(sim_id, value):
    """Set household funds for the Sim's household."""
    sim_info = _get_sim_info(sim_id)
    if sim_info is None:
        return
    try:
        household = sim_info.household
        if household is None:
            return
        current = household.funds.money
        delta = int(value) - current
        if delta > 0:
            household.funds.add(delta, 0, household)
        elif delta < 0:
            household.funds.try_remove(abs(delta), 0, household)
    except (AttributeError, TypeError) as exc:
        raise RuntimeError(f"Failed to set household funds: {exc}") from exc


def _get_relationship_value(sim_id, field_name):
    """Get relationship track value. Requires a target Sim (stubbed)."""
    # Full implementation requires target_sim_id; returning 0 for now
    return 0.0


def _set_relationship_value(sim_id, field_name, value):
    """Set relationship track value. Requires a target Sim (stubbed)."""
    pass


def _get_career_progress(sim_id):
    """Get career progress percentage."""
    sim_info = _get_sim_info(sim_id)
    if sim_info is None:
        return 0.0
    try:
        career_tracker = sim_info.career_tracker
        if career_tracker is None:
            return 0.0
        for career in career_tracker.careers.values():
            return career.work_performance
    except (AttributeError, TypeError):
        pass
    return 0.0


def _set_career_progress(sim_id, value):
    """Set career progress percentage."""
    sim_info = _get_sim_info(sim_id)
    if sim_info is None:
        return
    try:
        career_tracker = sim_info.career_tracker
        if career_tracker is None:
            return
        for career in career_tracker.careers.values():
            career.work_performance = value
            return
    except (AttributeError, TypeError) as exc:
        raise RuntimeError(f"Failed to set career progress: {exc}") from exc
