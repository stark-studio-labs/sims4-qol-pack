"""Tests for the Settings Manager module."""

import json

from qol_pack.events import SettingsChangedEvent, PresetAppliedEvent
from qol_pack._compat import EventBus
from qol_pack.modules.settings import (
    SettingsManager,
    DEFAULTS,
    PRESETS,
    SETTING_METADATA,
)


class TestSettingsLoad:
    def test_load_defaults(self, settings_file):
        SettingsManager.load(path=settings_file)
        for key, default_value in DEFAULTS.items():
            assert SettingsManager.get(key) == default_value

    def test_load_from_file(self, settings_file):
        # Write a partial settings file
        with open(settings_file, "w") as f:
            json.dump({"ui_tweaks.enabled": False}, f)

        SettingsManager.load(path=settings_file)
        assert SettingsManager.get("ui_tweaks.enabled") is False
        # Other settings should be defaults
        assert SettingsManager.get("build_tools.enabled") is True

    def test_load_ignores_unknown_keys(self, settings_file):
        with open(settings_file, "w") as f:
            json.dump({"unknown_key": "should_be_ignored"}, f)

        SettingsManager.load(path=settings_file)
        assert SettingsManager.get("unknown_key") is None

    def test_load_corrupted_file(self, settings_file):
        with open(settings_file, "w") as f:
            f.write("not valid json{{{")

        SettingsManager.load(path=settings_file)
        # Should fall back to defaults without crashing
        assert SettingsManager.get("ui_tweaks.enabled") is True


class TestSettingsGetSet:
    def setup_method(self):
        SettingsManager._settings = dict(DEFAULTS)
        SettingsManager._settings_path = None

    def test_get_existing_key(self):
        assert SettingsManager.get("ui_tweaks.enabled") is True

    def test_get_missing_key(self):
        assert SettingsManager.get("nonexistent") is None

    def test_get_missing_key_with_default(self):
        assert SettingsManager.get("nonexistent", "fallback") == "fallback"

    def test_set_valid_key(self, settings_file):
        SettingsManager._settings_path = settings_file
        changed = SettingsManager.set("ui_tweaks.enabled", False)
        assert changed is True
        assert SettingsManager.get("ui_tweaks.enabled") is False

    def test_set_same_value_returns_false(self, settings_file):
        SettingsManager._settings_path = settings_file
        changed = SettingsManager.set("ui_tweaks.enabled", True)
        assert changed is False

    def test_set_unknown_key_rejected(self, settings_file):
        SettingsManager._settings_path = settings_file
        changed = SettingsManager.set("fake.key", "value")
        assert changed is False

    def test_set_publishes_event(self, settings_file):
        SettingsManager._settings_path = settings_file
        events = []

        @EventBus.on(SettingsChangedEvent)
        def capture(event):
            events.append(event)

        SettingsManager.set("performance.target_fps", 60.0)
        assert len(events) == 1
        assert events[0].key == "performance.target_fps"
        assert events[0].old_value == 30.0
        assert events[0].new_value == 60.0


class TestSettingsSave:
    def test_save_creates_file(self, settings_file):
        SettingsManager._settings = dict(DEFAULTS)
        SettingsManager._settings_path = settings_file
        SettingsManager.save()

        with open(settings_file) as f:
            saved = json.load(f)
        assert saved["ui_tweaks.enabled"] is True

    def test_roundtrip(self, settings_file):
        SettingsManager._settings_path = settings_file
        SettingsManager._settings = dict(DEFAULTS)
        SettingsManager._settings["performance.target_fps"] = 120.0
        SettingsManager.save()

        SettingsManager._settings = {}
        SettingsManager.load(path=settings_file)
        assert SettingsManager.get("performance.target_fps") == 120.0


class TestPresets:
    def setup_method(self):
        SettingsManager._settings = dict(DEFAULTS)
        SettingsManager._settings_path = None

    def test_apply_beginner_preset(self, settings_file):
        SettingsManager._settings_path = settings_file
        result = SettingsManager.apply_preset("beginner")
        assert result is True
        assert SettingsManager.get("ui_tweaks.categories") == ["needs"]
        assert SettingsManager.get("build_tools.precision") == 0.1
        assert SettingsManager.get("build_tools.off_lot") is False

    def test_apply_advanced_preset(self, settings_file):
        SettingsManager._settings_path = settings_file
        result = SettingsManager.apply_preset("advanced")
        assert result is True
        assert SettingsManager.get("build_tools.off_lot") is True
        assert SettingsManager.get("build_tools.precision") == 0.01

    def test_apply_streamer_preset(self, settings_file):
        SettingsManager._settings_path = settings_file
        result = SettingsManager.apply_preset("streamer")
        assert result is True
        assert SettingsManager.get("ui_tweaks.enabled") is False
        assert SettingsManager.get("performance.throttle_level") == 3

    def test_apply_unknown_preset(self):
        result = SettingsManager.apply_preset("nonexistent")
        assert result is False

    def test_preset_publishes_event(self, settings_file):
        SettingsManager._settings_path = settings_file
        events = []

        @EventBus.on(PresetAppliedEvent)
        def capture(event):
            events.append(event)

        SettingsManager.apply_preset("beginner")
        assert len(events) == 1
        assert events[0].preset_name == "beginner"


class TestSettingsCategories:
    def test_get_categories(self):
        SettingsManager._settings = dict(DEFAULTS)
        categories = SettingsManager.get_categories()
        assert "UI Tweaks" in categories
        assert "Build Tools" in categories
        assert "Performance" in categories

    def test_category_entries_have_key(self):
        SettingsManager._settings = dict(DEFAULTS)
        categories = SettingsManager.get_categories()
        for cat_name, entries in categories.items():
            for entry in entries:
                assert "key" in entry
                assert "value" in entry


class TestSettingsSearch:
    def test_search_by_key(self):
        SettingsManager._settings = dict(DEFAULTS)
        results = SettingsManager.search("precision")
        assert any(r["key"] == "build_tools.precision" for r in results)

    def test_search_by_label(self):
        SettingsManager._settings = dict(DEFAULTS)
        results = SettingsManager.search("Off-Lot")
        assert any(r["key"] == "build_tools.off_lot" for r in results)

    def test_search_no_results(self):
        SettingsManager._settings = dict(DEFAULTS)
        results = SettingsManager.search("zzz_nonexistent_zzz")
        assert results == []


class TestExportImport:
    def test_export(self, tmp_path):
        SettingsManager._settings = dict(DEFAULTS)
        export_path = str(tmp_path / "exported.json")
        SettingsManager.export_settings(export_path)

        with open(export_path) as f:
            exported = json.load(f)
        assert exported["ui_tweaks.enabled"] is True

    def test_import(self, tmp_path, settings_file):
        import_path = str(tmp_path / "import.json")
        with open(import_path, "w") as f:
            json.dump({"performance.target_fps": 144.0}, f)

        SettingsManager._settings = dict(DEFAULTS)
        SettingsManager._settings_path = settings_file
        result = SettingsManager.import_settings(import_path)
        assert result is True
        assert SettingsManager.get("performance.target_fps") == 144.0

    def test_import_invalid_file(self, tmp_path, settings_file):
        bad_path = str(tmp_path / "bad.json")
        with open(bad_path, "w") as f:
            f.write("not json")

        SettingsManager._settings_path = settings_file
        result = SettingsManager.import_settings(bad_path)
        assert result is False


class TestSettingsReset:
    def test_reset_to_defaults(self, settings_file):
        SettingsManager._settings_path = settings_file
        SettingsManager._settings = {"ui_tweaks.enabled": False}
        SettingsManager.reset()
        assert SettingsManager.get("ui_tweaks.enabled") is True


class TestSettingMetadata:
    def test_all_defaults_have_metadata(self):
        for key in DEFAULTS:
            assert key in SETTING_METADATA, f"Missing metadata for {key}"

    def test_metadata_has_label(self):
        for key, meta in SETTING_METADATA.items():
            assert "label" in meta, f"Missing label for {key}"
            assert "type" in meta, f"Missing type for {key}"
            assert "category" in meta, f"Missing category for {key}"
