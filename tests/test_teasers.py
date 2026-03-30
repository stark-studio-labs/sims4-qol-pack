"""Tests for the freemium teaser system."""

import pytest
from stark_framework.core.registry import ModRegistry

from qol_pack.teasers import (
    TeaserManager,
    TeaserShownEvent,
    TeaserDismissedEvent,
    TEASER_CATALOG,
)
from qol_pack.events import SettingsChangedEvent


@pytest.fixture(autouse=True)
def reset_teasers():
    """Reset teaser state before each test."""
    TeaserManager.reset()
    yield
    TeaserManager.reset()


# ── Eligibility ────────────────────────────────────────────────────

class TestEligibility:
    """Tests for teaser eligibility logic."""

    def test_all_eligible_when_no_stark_mods_installed(self):
        TeaserManager.install()
        eligible = TeaserManager.get_eligible_teasers()
        assert set(eligible) == set(TEASER_CATALOG.keys())

    def test_installed_mod_excluded_from_eligible(self):
        ModRegistry.register(
            mod_id="stark_economy_sim",
            name="Stark Economy",
            version="0.1.0",
            author="Stark Labs",
        )
        TeaserManager.install()
        eligible = TeaserManager.get_eligible_teasers()
        assert "economy" not in eligible
        assert "social" in eligible

    def test_all_mods_installed_means_no_eligible(self):
        for teaser in TEASER_CATALOG.values():
            ModRegistry.register(
                mod_id=teaser["mod_id"],
                name=teaser["title"],
                version="0.1.0",
                author="Stark Labs",
            )
        TeaserManager.install()
        assert TeaserManager.get_eligible_teasers() == []

    def test_dismissed_teaser_excluded(self):
        TeaserManager.install()
        TeaserManager.dismiss("drama", permanently=True)
        eligible = TeaserManager.get_eligible_teasers()
        assert "drama" not in eligible

    def test_non_permanent_dismiss_does_not_exclude(self):
        TeaserManager.install()
        TeaserManager.dismiss("drama", permanently=False)
        eligible = TeaserManager.get_eligible_teasers()
        assert "drama" in eligible

    def test_load_dismissed_from_settings(self):
        TeaserManager.install()
        TeaserManager.load_dismissed(["economy", "political"])
        eligible = TeaserManager.get_eligible_teasers()
        assert "economy" not in eligible
        assert "political" not in eligible
        assert "social" in eligible


# ── Rate Limiting ──────────────────────────────────────────────────

class TestRateLimiting:
    """Tests for session-level rate limiting (max 1 per session)."""

    def test_can_show_when_fresh(self):
        TeaserManager.install()
        assert TeaserManager.can_show_teaser() is True

    def test_cannot_show_after_one_shown(self):
        TeaserManager.install()
        TeaserManager.try_show("economy")
        assert TeaserManager.can_show_teaser() is False

    def test_second_try_show_returns_none(self):
        TeaserManager.install()
        first = TeaserManager.try_show("economy")
        second = TeaserManager.try_show("social")
        assert first is not None
        assert second is None

    def test_different_context_blocked_after_first(self):
        TeaserManager.install()
        TeaserManager.try_show("social")
        result = TeaserManager.try_show("drama")
        assert result is None

    def test_cannot_show_when_disabled(self):
        TeaserManager.install()
        TeaserManager._enabled = False
        assert TeaserManager.can_show_teaser() is False

    def test_try_show_returns_none_when_disabled(self):
        TeaserManager.install()
        TeaserManager._enabled = False
        result = TeaserManager.try_show("economy")
        assert result is None


# ── try_show Behavior ──────────────────────────────────────────────

class TestTryShow:
    """Tests for try_show() return values and side effects."""

    def test_returns_teaser_dict_on_success(self):
        TeaserManager.install()
        result = TeaserManager.try_show("economy")
        assert result is not None
        assert result["mod_id"] == "stark_economy_sim"
        assert result["title"] == "Stark Economy"

    def test_returns_none_for_installed_mod(self):
        ModRegistry.register(
            mod_id="stark_economy_sim",
            name="Stark Economy",
            version="0.1.0",
            author="Stark Labs",
        )
        TeaserManager.install()
        result = TeaserManager.try_show("economy")
        assert result is None

    def test_returns_none_for_dismissed_teaser(self):
        TeaserManager.install()
        TeaserManager.dismiss("social", permanently=True)
        result = TeaserManager.try_show("social")
        assert result is None

    def test_returns_none_for_unknown_context(self):
        TeaserManager.install()
        result = TeaserManager.try_show("nonexistent_mod")
        assert result is None

    def test_marks_session_shown(self):
        TeaserManager.install()
        assert TeaserManager._shown_this_session is False
        TeaserManager.try_show("political")
        assert TeaserManager._shown_this_session is True
        assert TeaserManager._session_teaser_key == "political"

    def test_all_five_teasers_have_valid_catalog_entries(self):
        for key in ["economy", "social", "political", "drama", "smart_sims"]:
            assert key in TEASER_CATALOG
            entry = TEASER_CATALOG[key]
            assert "mod_id" in entry
            assert "title" in entry
            assert "message" in entry
            assert "url" in entry

    def test_each_teaser_showable_individually(self):
        for key in TEASER_CATALOG:
            TeaserManager.reset()
            TeaserManager.install()
            result = TeaserManager.try_show(key)
            assert result is not None, f"Teaser '{key}' should be showable"
            assert result["title"] == TEASER_CATALOG[key]["title"]


# ── Events ─────────────────────────────────────────────────────────

class TestEvents:
    """Tests for event publishing."""

    def test_shown_event_published(self, captured_events):
        TeaserManager.install()
        TeaserManager.try_show("economy")
        shown_events = [e for e in captured_events if isinstance(e, TeaserShownEvent)]
        assert len(shown_events) == 1
        assert shown_events[0].teaser_key == "economy"
        assert shown_events[0].title == "Stark Economy"

    def test_no_event_when_blocked(self, captured_events):
        TeaserManager.install()
        TeaserManager._enabled = False
        TeaserManager.try_show("economy")
        shown_events = [e for e in captured_events if isinstance(e, TeaserShownEvent)]
        assert len(shown_events) == 0

    def test_dismiss_event_published(self, captured_events):
        TeaserManager.install()
        TeaserManager.dismiss("drama", permanently=True)
        dismissed_events = [e for e in captured_events if isinstance(e, TeaserDismissedEvent)]
        assert len(dismissed_events) == 1
        assert dismissed_events[0].teaser_key == "drama"
        assert dismissed_events[0].permanently is True

    def test_non_permanent_dismiss_event(self, captured_events):
        TeaserManager.install()
        TeaserManager.dismiss("social", permanently=False)
        dismissed_events = [e for e in captured_events if isinstance(e, TeaserDismissedEvent)]
        assert len(dismissed_events) == 1
        assert dismissed_events[0].permanently is False


# ── Status ─────────────────────────────────────────────────────────

class TestStatus:
    """Tests for get_status() reporting."""

    def test_status_before_any_action(self):
        TeaserManager.install()
        status = TeaserManager.get_status()
        assert status["enabled"] is True
        assert status["shown_this_session"] is False
        assert status["session_teaser_key"] is None
        assert len(status["eligible"]) == len(TEASER_CATALOG)

    def test_status_after_show(self):
        TeaserManager.install()
        TeaserManager.try_show("social")
        status = TeaserManager.get_status()
        assert status["shown_this_session"] is True
        assert status["session_teaser_key"] == "social"

    def test_status_reflects_installed_mods(self):
        ModRegistry.register(
            mod_id="stark_smart_sims",
            name="Smart Sims",
            version="0.1.0",
            author="Stark Labs",
        )
        TeaserManager.install()
        status = TeaserManager.get_status()
        assert "smart_sims" in status["installed_stark_mods"]
        assert "smart_sims" not in status["eligible"]

    def test_status_reflects_dismissed(self):
        TeaserManager.install()
        TeaserManager.dismiss("economy", permanently=True)
        status = TeaserManager.get_status()
        assert "economy" in status["permanently_dismissed"]


# ── Mark Installed Mid-Session ─────────────────────────────────────

class TestMarkInstalled:
    """Tests for marking mods as installed mid-session."""

    def test_mark_installed_suppresses_teaser(self):
        TeaserManager.install()
        TeaserManager.mark_mod_installed("economy")
        result = TeaserManager.try_show("economy")
        assert result is None

    def test_mark_installed_updates_eligible(self):
        TeaserManager.install()
        assert "economy" in TeaserManager.get_eligible_teasers()
        TeaserManager.mark_mod_installed("economy")
        assert "economy" not in TeaserManager.get_eligible_teasers()


# ── Settings Integration ───────────────────────────────────────────

class TestSettingsIntegration:
    """Tests for settings-driven behavior."""

    def test_disable_via_settings_event(self):
        from stark_framework.core.events import EventBus
        TeaserManager.install()
        assert TeaserManager._enabled is True

        EventBus.publish(
            SettingsChangedEvent(
                key="teasers.enabled",
                old_value=True,
                new_value=False,
            ),
            source_mod="test",
        )
        assert TeaserManager._enabled is False

    def test_dismissed_loaded_via_settings_event(self):
        from stark_framework.core.events import EventBus
        TeaserManager.install()

        EventBus.publish(
            SettingsChangedEvent(
                key="teasers.dismissed",
                old_value=[],
                new_value=["economy", "drama"],
            ),
            source_mod="test",
        )
        assert "economy" in TeaserManager._permanently_dismissed
        assert "drama" in TeaserManager._permanently_dismissed
