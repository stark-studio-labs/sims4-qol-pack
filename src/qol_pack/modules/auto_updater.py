"""
Auto Updater -- check for mod updates, notify the user, and support one-click updates.

Polls GitHub Releases API for new versions of the QoL Pack. When a newer
version is found, publishes an UpdateAvailableEvent so the UI can show a
notification. Optionally downloads the update to a staging folder.

Does NOT auto-install without user confirmation -- the player must approve.

Rate-limited: checks at most once per session, respecting the configured
frequency (daily/weekly/off).
"""

import os
import sys
import json
import time
import hashlib

from stark_framework.core.events import EventBus
from stark_framework.utils.logging import get_logger

from qol_pack.events import (
    UpdateAvailableEvent,
    UpdateInstalledEvent,
    SettingsChangedEvent,
)

log = get_logger("qol.auto_updater")

MOD_ID = "stark_qol_pack.auto_updater"

# GitHub Releases API endpoint
RELEASES_URL = "https://api.github.com/repos/stark-studio-labs/sims4-qol-pack/releases/latest"

# How often to check (in seconds)
CHECK_INTERVALS = {
    "daily": 86400,
    "weekly": 604800,
    "off": float("inf"),
}


class AutoUpdater:
    """Mod update checker and installer.

    Checks GitHub Releases for new versions, stages downloads, and
    coordinates the update flow through events.
    """

    _enabled = True
    _check_frequency = "daily"
    _auto_download = False
    _channel = "stable"
    _last_check_time = 0.0
    _last_check_file = None
    _update_available = None  # Dict with version info if update found
    _staging_dir = None

    @classmethod
    def install(cls):
        """Register event handlers and determine check timing."""
        EventBus.subscribe(
            SettingsChangedEvent,
            cls._on_settings_changed,
            priority=50,
            mod_id=MOD_ID,
        )

        cls._last_check_file = _get_check_timestamp_path()
        cls._staging_dir = _get_staging_dir()
        cls._last_check_time = _read_last_check_time(cls._last_check_file)

        log.info(
            "Auto Updater installed",
            frequency=cls._check_frequency,
            auto_download=cls._auto_download,
        )

    @classmethod
    def _on_settings_changed(cls, event):
        """React to settings changes."""
        if event.key == "auto_updater.enabled":
            cls._enabled = bool(event.new_value)
        elif event.key == "auto_updater.check_frequency":
            cls._check_frequency = str(event.new_value)
        elif event.key == "auto_updater.auto_download":
            cls._auto_download = bool(event.new_value)
        elif event.key == "auto_updater.channel":
            cls._channel = str(event.new_value)

    @classmethod
    def check_for_updates(cls, force=False):
        """Check if a newer version is available.

        Respects the check frequency setting unless force=True.

        Args:
            force: If True, ignore the frequency check.

        Returns:
            Dict with update info if available, None if up-to-date or skipped.
        """
        if not cls._enabled and not force:
            return None

        # Rate limit
        if not force:
            interval = CHECK_INTERVALS.get(cls._check_frequency, float("inf"))
            if time.time() - cls._last_check_time < interval:
                log.debug("Skipping update check -- too recent")
                return None

        log.info("Checking for updates...")

        try:
            release_info = _fetch_latest_release()
        except Exception as exc:
            log.warn("Update check failed", error=str(exc))
            return None

        cls._last_check_time = time.time()
        _write_last_check_time(cls._last_check_file, cls._last_check_time)

        if release_info is None:
            return None

        current_version = _get_current_version()
        latest_version = release_info.get("tag_name", "").lstrip("v")

        if not _is_newer(current_version, latest_version):
            log.info("Already up to date", current=current_version)
            return None

        # Filter by channel
        is_prerelease = release_info.get("prerelease", False)
        if cls._channel == "stable" and is_prerelease:
            log.debug("Skipping pre-release", version=latest_version)
            return None

        # Find the download asset
        download_url = ""
        for asset in release_info.get("assets", []):
            if asset["name"].endswith(".ts4script"):
                download_url = asset["browser_download_url"]
                break

        changelog = release_info.get("body", "No changelog provided.")

        update_info = {
            "current_version": current_version,
            "new_version": latest_version,
            "changelog": changelog,
            "download_url": download_url,
            "is_prerelease": is_prerelease,
        }

        cls._update_available = update_info

        EventBus.publish(
            UpdateAvailableEvent(
                current_version=current_version,
                new_version=latest_version,
                changelog=changelog,
                download_url=download_url,
            ),
            source_mod=MOD_ID,
        )

        log.info(
            "Update available",
            current=current_version,
            new=latest_version,
        )

        # Auto-download if enabled
        if cls._auto_download and download_url:
            cls.download_update(download_url)

        return update_info

    @classmethod
    def download_update(cls, url=None):
        """Download an update to the staging directory.

        Args:
            url: Download URL. If None, uses the URL from the last check.

        Returns:
            Path to the downloaded file, or None on failure.
        """
        if url is None and cls._update_available:
            url = cls._update_available.get("download_url")

        if not url:
            log.warn("No download URL available")
            return None

        try:
            staging_path = _download_file(url, cls._staging_dir)
            log.info("Update downloaded", path=staging_path)
            return staging_path
        except Exception as exc:
            log.error("Download failed", error=str(exc))
            return None

    @classmethod
    def apply_update(cls, staged_file_path):
        """Apply a staged update by swapping the mod files.

        This copies the new .ts4script into the Mods folder and renames
        the old one as a backup. The game must be restarted for the
        update to take effect.

        Args:
            staged_file_path: Path to the downloaded .ts4script file.

        Returns:
            True if the update was applied.
        """
        if not os.path.exists(staged_file_path):
            log.error("Staged file not found", path=staged_file_path)
            return False

        mods_dir = _get_mods_dir()
        current_mod_path = os.path.join(mods_dir, "StarkQoLPack.ts4script")
        backup_path = os.path.join(mods_dir, "StarkQoLPack.ts4script.backup")

        try:
            # Backup current version
            if os.path.exists(current_mod_path):
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(current_mod_path, backup_path)

            # Install new version
            import shutil
            shutil.copy2(staged_file_path, current_mod_path)

            new_version = ""
            if cls._update_available:
                new_version = cls._update_available.get("new_version", "")

            EventBus.publish(
                UpdateInstalledEvent(
                    version=new_version,
                    restart_required=True,
                ),
                source_mod=MOD_ID,
            )

            log.info("Update applied -- restart required", version=new_version)
            return True

        except OSError as exc:
            log.error("Failed to apply update", error=str(exc))
            # Attempt to restore backup
            if os.path.exists(backup_path) and not os.path.exists(current_mod_path):
                try:
                    os.rename(backup_path, current_mod_path)
                    log.info("Restored backup after failed update")
                except OSError:
                    pass
            return False

    @classmethod
    def get_status(cls):
        """Return the current update check status.

        Returns:
            Dict with status information.
        """
        return {
            "enabled": cls._enabled,
            "frequency": cls._check_frequency,
            "channel": cls._channel,
            "last_check": cls._last_check_time,
            "update_available": cls._update_available,
        }


# ── Internal helpers ────────────────────────────────────────────────

def _get_current_version():
    """Get the current QoL Pack version."""
    try:
        from qol_pack import __version__
        return __version__
    except ImportError:
        return "0.0.0"


def _is_newer(current, candidate):
    """Compare two semantic version strings.

    Returns True if candidate is strictly newer than current.
    """
    def parse(v):
        parts = v.split(".")
        result = []
        for p in parts:
            try:
                result.append(int(p))
            except ValueError:
                result.append(0)
        while len(result) < 3:
            result.append(0)
        return tuple(result)

    return parse(candidate) > parse(current)


def _fetch_latest_release():
    """Fetch the latest release info from GitHub.

    Uses urllib to avoid external dependencies.

    Returns:
        Dict with release info, or None on failure.
    """
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        RELEASES_URL,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "StarkQoLPack-AutoUpdater",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def _download_file(url, target_dir):
    """Download a file from URL to target directory.

    Returns the path to the downloaded file.
    """
    import urllib.request

    os.makedirs(target_dir, exist_ok=True)

    filename = url.rsplit("/", 1)[-1]
    target_path = os.path.join(target_dir, filename)

    urllib.request.urlretrieve(url, target_path)
    return target_path


def _get_check_timestamp_path():
    """Path to the file that stores the last check timestamp."""
    return os.path.join(_get_data_dir(), "last_update_check.json")


def _read_last_check_time(path):
    """Read the last check timestamp from disk."""
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
                return data.get("timestamp", 0.0)
    except (json.JSONDecodeError, OSError):
        pass
    return 0.0


def _write_last_check_time(path, timestamp):
    """Write the last check timestamp to disk."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"timestamp": timestamp}, f)
    except OSError:
        pass


def _get_data_dir():
    """Get the QoL Pack data directory."""
    if sys.platform in ("win32", "darwin"):
        return os.path.expanduser(
            "~/Documents/Electronic Arts/The Sims 4/Mods/StarkQoL"
        )
    return "/tmp/StarkQoL"


def _get_staging_dir():
    """Get the directory for staged downloads."""
    return os.path.join(_get_data_dir(), "staging")


def _get_mods_dir():
    """Get the Sims 4 Mods directory."""
    if sys.platform in ("win32", "darwin"):
        return os.path.expanduser(
            "~/Documents/Electronic Arts/The Sims 4/Mods"
        )
    return "/tmp/Mods"
