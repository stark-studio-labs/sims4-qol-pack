"""Tests for the Auto Updater module."""

import json
import os
import time

from stark_framework.core.events import EventBus

from qol_pack.events import UpdateAvailableEvent, SettingsChangedEvent
from qol_pack.modules.auto_updater import (
    AutoUpdater,
    _is_newer,
    _read_last_check_time,
    _write_last_check_time,
    CHECK_INTERVALS,
)


class TestVersionComparison:
    def test_newer_patch(self):
        assert _is_newer("0.1.0", "0.1.1") is True

    def test_newer_minor(self):
        assert _is_newer("0.1.0", "0.2.0") is True

    def test_newer_major(self):
        assert _is_newer("0.1.0", "1.0.0") is True

    def test_same_version(self):
        assert _is_newer("0.1.0", "0.1.0") is False

    def test_older_version(self):
        assert _is_newer("0.2.0", "0.1.0") is False

    def test_short_version_string(self):
        assert _is_newer("1.0", "1.1") is True

    def test_single_digit_version(self):
        assert _is_newer("1", "2") is True


class TestCheckTimestamp:
    def test_write_and_read(self, tmp_path):
        path = str(tmp_path / "check.json")
        ts = time.time()
        _write_last_check_time(path, ts)
        result = _read_last_check_time(path)
        assert result == ts

    def test_read_missing_file(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        result = _read_last_check_time(path)
        assert result == 0.0

    def test_read_corrupted_file(self, tmp_path):
        path = str(tmp_path / "bad.json")
        with open(path, "w") as f:
            f.write("not json{{{")
        result = _read_last_check_time(path)
        assert result == 0.0


class TestAutoUpdaterInstall:
    def test_install_subscribes_to_settings(self):
        AutoUpdater._last_check_file = "/tmp/test_check.json"
        AutoUpdater._staging_dir = "/tmp/test_staging"
        AutoUpdater.install()
        subs = EventBus.get_subscribers(SettingsChangedEvent)
        mod_ids = [s.mod_id for s in subs]
        assert "stark_qol_pack.auto_updater" in mod_ids


class TestAutoUpdaterSettings:
    def test_settings_toggle_enabled(self):
        AutoUpdater._last_check_file = "/tmp/test_check.json"
        AutoUpdater._staging_dir = "/tmp/test_staging"
        AutoUpdater.install()
        AutoUpdater._enabled = True

        EventBus.publish(SettingsChangedEvent(
            key="auto_updater.enabled",
            old_value=True,
            new_value=False,
        ))
        assert AutoUpdater._enabled is False

    def test_settings_change_frequency(self):
        AutoUpdater._last_check_file = "/tmp/test_check.json"
        AutoUpdater._staging_dir = "/tmp/test_staging"
        AutoUpdater.install()

        EventBus.publish(SettingsChangedEvent(
            key="auto_updater.check_frequency",
            old_value="daily",
            new_value="weekly",
        ))
        assert AutoUpdater._check_frequency == "weekly"

    def test_settings_change_channel(self):
        AutoUpdater._last_check_file = "/tmp/test_check.json"
        AutoUpdater._staging_dir = "/tmp/test_staging"
        AutoUpdater.install()

        EventBus.publish(SettingsChangedEvent(
            key="auto_updater.channel",
            old_value="stable",
            new_value="beta",
        ))
        assert AutoUpdater._channel == "beta"


class TestCheckForUpdates:
    def test_disabled_returns_none(self):
        AutoUpdater._enabled = False
        result = AutoUpdater.check_for_updates()
        assert result is None

    def test_rate_limited(self):
        AutoUpdater._enabled = True
        AutoUpdater._check_frequency = "daily"
        AutoUpdater._last_check_time = time.time()  # Just checked
        result = AutoUpdater.check_for_updates()
        assert result is None

    def test_force_ignores_rate_limit(self, monkeypatch):
        AutoUpdater._enabled = True
        AutoUpdater._last_check_time = time.time()
        AutoUpdater._last_check_file = "/tmp/test_check.json"

        # Mock the network call to return no update
        monkeypatch.setattr(
            "qol_pack.modules.auto_updater._fetch_latest_release",
            lambda: None,
        )

        result = AutoUpdater.check_for_updates(force=True)
        assert result is None  # No update, but the check ran


class TestCheckIntervals:
    def test_daily_interval(self):
        assert CHECK_INTERVALS["daily"] == 86400

    def test_weekly_interval(self):
        assert CHECK_INTERVALS["weekly"] == 604800

    def test_off_interval(self):
        assert CHECK_INTERVALS["off"] == float("inf")


class TestApplyUpdate:
    def test_apply_missing_file(self):
        result = AutoUpdater.apply_update("/nonexistent/path.ts4script")
        assert result is False

    def test_apply_creates_backup(self, tmp_path):
        # Create a fake staged file
        staged = tmp_path / "new.ts4script"
        staged.write_text("new version data")

        # Create a fake mods dir with current mod
        mods_dir = tmp_path / "Mods"
        mods_dir.mkdir()
        current = mods_dir / "StarkQoLPack.ts4script"
        current.write_text("old version data")

        import qol_pack.modules.auto_updater as updater_mod
        original_get_mods_dir = updater_mod._get_mods_dir

        try:
            updater_mod._get_mods_dir = lambda: str(mods_dir)
            AutoUpdater._update_available = {"new_version": "0.2.0"}

            events = []

            @EventBus.on(updater_mod.UpdateInstalledEvent)
            def capture(event):
                events.append(event)

            result = AutoUpdater.apply_update(str(staged))
            assert result is True

            # Backup should exist
            backup = mods_dir / "StarkQoLPack.ts4script.backup"
            assert backup.exists()
            assert backup.read_text() == "old version data"

            # New version should be installed
            assert current.read_text() == "new version data"
            assert len(events) == 1
        finally:
            updater_mod._get_mods_dir = original_get_mods_dir


class TestGetStatus:
    def test_status_dict(self):
        status = AutoUpdater.get_status()
        assert "enabled" in status
        assert "frequency" in status
        assert "channel" in status
        assert "last_check" in status
        assert "update_available" in status
