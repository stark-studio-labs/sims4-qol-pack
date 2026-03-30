"""Tests for the UI Tweaks module."""

from stark_framework.core.events import EventBus

from qol_pack.events import UIEditRequestedEvent, UIValueChangedEvent, SettingsChangedEvent
from qol_pack.modules.ui_tweaks import UITweaks, EDITABLE_FIELDS


class TestUITweaksInstall:
    def test_install_subscribes_to_settings(self):
        UITweaks.install()
        subs = EventBus.get_subscribers(SettingsChangedEvent)
        mod_ids = [s.mod_id for s in subs]
        assert "stark_qol_pack.ui_tweaks" in mod_ids


class TestUITweaksEditRequest:
    def setup_method(self):
        UITweaks._enabled = True
        UITweaks._enabled_categories = {"needs", "skills", "household", "relationships", "career"}

    def test_request_edit_valid_field(self):
        result = UITweaks.request_edit(sim_id=1, field_name="need_hunger")
        assert result is True

    def test_request_edit_unknown_field(self):
        result = UITweaks.request_edit(sim_id=1, field_name="nonexistent_field")
        assert result is False

    def test_request_edit_disabled(self):
        UITweaks._enabled = False
        result = UITweaks.request_edit(sim_id=1, field_name="need_hunger")
        assert result is False

    def test_request_edit_category_disabled(self):
        UITweaks._enabled_categories = {"skills"}  # needs not included
        result = UITweaks.request_edit(sim_id=1, field_name="need_hunger")
        assert result is False

    def test_request_edit_publishes_event(self):
        events = []

        @EventBus.on(UIEditRequestedEvent)
        def capture(event):
            events.append(event)

        UITweaks.request_edit(sim_id=42, field_name="money")
        assert len(events) == 1
        assert events[0].sim_id == 42
        assert events[0].field_name == "money"

    def test_request_edit_cancellable(self):
        @EventBus.on(UIEditRequestedEvent, priority=1)
        def blocker(event):
            event.cancel()

        result = UITweaks.request_edit(sim_id=1, field_name="need_hunger")
        assert result is False


class TestUITweaksSettings:
    def test_settings_toggle_enabled(self):
        UITweaks.install()
        UITweaks._enabled = True

        EventBus.publish(SettingsChangedEvent(
            key="ui_tweaks.enabled", old_value=True, new_value=False,
        ))
        assert UITweaks._enabled is False

    def test_settings_update_categories(self):
        UITweaks.install()

        EventBus.publish(SettingsChangedEvent(
            key="ui_tweaks.categories",
            old_value=["needs"],
            new_value=["needs", "skills"],
        ))
        assert UITweaks._enabled_categories == {"needs", "skills"}


class TestEditableFields:
    def test_all_fields_have_required_keys(self):
        for name, info in EDITABLE_FIELDS.items():
            assert "label" in info, f"{name} missing label"
            assert "category" in info, f"{name} missing category"
            assert "min" in info, f"{name} missing min"
            assert "max" in info, f"{name} missing max"

    def test_get_editable_fields_all(self):
        fields = UITweaks.get_editable_fields()
        assert len(fields) == len(EDITABLE_FIELDS)

    def test_get_editable_fields_by_category(self):
        needs = UITweaks.get_editable_fields(category="needs")
        assert all(v["category"] == "needs" for v in needs.values())
        assert len(needs) > 0

    def test_get_editable_fields_empty_category(self):
        result = UITweaks.get_editable_fields(category="nonexistent")
        assert result == {}
