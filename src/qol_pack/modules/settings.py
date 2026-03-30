"""
Settings Manager -- unified settings panel with presets, search, and visual UI.

All QoL Pack modules read their configuration from SettingsManager. Settings
are persisted to JSON and loaded at startup. Every change publishes a
SettingsChangedEvent so modules react immediately.

Presets:
- Beginner: Safe defaults, minimal features enabled
- Advanced: All features enabled with full control
- Streamer: Performance-first, disable UI overlays

Settings are organized by category matching the module names:
  ui_tweaks.*, build_tools.*, performance.*, diagnostics.*, auto_updater.*
"""

import os
import json
import copy

from qol_pack._compat import EventBus, get_logger

from qol_pack.events import SettingsChangedEvent, PresetAppliedEvent

log = get_logger("qol.settings")

MOD_ID = "stark_qol_pack.settings"

# Default settings -- every valid key must be defined here
DEFAULTS = {
    # UI Tweaks
    "ui_tweaks.enabled": True,
    "ui_tweaks.categories": ["needs", "skills", "household", "relationships", "career"],

    # Build Tools
    "build_tools.enabled": True,
    "build_tools.precision": 0.01,
    "build_tools.off_lot": True,
    "build_tools.scale": True,
    "build_tools.free_rotation": True,

    # Performance
    "performance.enabled": True,
    "performance.target_fps": 30.0,
    "performance.throttle_level": 0,

    # Diagnostics
    "diagnostics.detail_level": "full",

    # Auto Updater
    "auto_updater.enabled": True,
    "auto_updater.check_frequency": "daily",  # "daily", "weekly", "off"
    "auto_updater.auto_download": False,
    "auto_updater.channel": "stable",  # "stable", "beta"
}

# Presets -- each overrides specific settings
PRESETS = {
    "beginner": {
        "ui_tweaks.enabled": True,
        "ui_tweaks.categories": ["needs"],
        "build_tools.enabled": True,
        "build_tools.precision": 0.1,
        "build_tools.off_lot": False,
        "build_tools.scale": False,
        "build_tools.free_rotation": False,
        "performance.enabled": True,
        "performance.throttle_level": 1,
        "diagnostics.detail_level": "simple",
        "auto_updater.check_frequency": "weekly",
    },
    "advanced": {
        "ui_tweaks.enabled": True,
        "ui_tweaks.categories": ["needs", "skills", "household", "relationships", "career"],
        "build_tools.enabled": True,
        "build_tools.precision": 0.01,
        "build_tools.off_lot": True,
        "build_tools.scale": True,
        "build_tools.free_rotation": True,
        "performance.enabled": True,
        "performance.throttle_level": 0,
        "diagnostics.detail_level": "full",
        "auto_updater.check_frequency": "daily",
    },
    "streamer": {
        "ui_tweaks.enabled": False,
        "ui_tweaks.categories": [],
        "build_tools.enabled": True,
        "build_tools.precision": 0.1,
        "build_tools.off_lot": False,
        "build_tools.scale": False,
        "build_tools.free_rotation": False,
        "performance.enabled": True,
        "performance.throttle_level": 3,
        "diagnostics.detail_level": "simple",
        "auto_updater.check_frequency": "off",
    },
}

# Setting metadata for UI rendering
SETTING_METADATA = {
    "ui_tweaks.enabled": {
        "label": "Enable UI Click-to-Edit",
        "description": "Click on UI elements (needs, skills, money) to edit their values",
        "type": "bool",
        "category": "UI Tweaks",
    },
    "ui_tweaks.categories": {
        "label": "Editable Categories",
        "description": "Which UI elements can be clicked to edit",
        "type": "multi_select",
        "options": ["needs", "skills", "household", "relationships", "career"],
        "category": "UI Tweaks",
    },
    "build_tools.enabled": {
        "label": "Enable Enhanced Build Tools",
        "description": "Precision positioning, free rotation, scaling in build mode",
        "type": "bool",
        "category": "Build Tools",
    },
    "build_tools.precision": {
        "label": "Position Precision",
        "description": "Step size for object positioning (smaller = more precise)",
        "type": "float",
        "min": 0.001,
        "max": 1.0,
        "step": 0.01,
        "category": "Build Tools",
    },
    "build_tools.off_lot": {
        "label": "Off-Lot Placement",
        "description": "Allow placing objects beyond lot boundaries",
        "type": "bool",
        "category": "Build Tools",
    },
    "build_tools.scale": {
        "label": "Object Scaling",
        "description": "Enable object size scaling",
        "type": "bool",
        "category": "Build Tools",
    },
    "build_tools.free_rotation": {
        "label": "Free Rotation",
        "description": "Rotate objects on all three axes (not just Y)",
        "type": "bool",
        "category": "Build Tools",
    },
    "performance.enabled": {
        "label": "Enable Performance Optimizer",
        "description": "Automatic FPS optimization through autonomy throttling",
        "type": "bool",
        "category": "Performance",
    },
    "performance.target_fps": {
        "label": "Target FPS",
        "description": "FPS target for adaptive throttling",
        "type": "float",
        "min": 15.0,
        "max": 120.0,
        "step": 5.0,
        "category": "Performance",
    },
    "performance.throttle_level": {
        "label": "Throttle Level",
        "description": "0=None, 1=Light, 2=Moderate, 3=Aggressive",
        "type": "int",
        "min": 0,
        "max": 3,
        "category": "Performance",
    },
    "diagnostics.detail_level": {
        "label": "Error Detail Level",
        "description": "How much detail to show in error reports",
        "type": "select",
        "options": ["simple", "full"],
        "category": "Diagnostics",
    },
    "auto_updater.enabled": {
        "label": "Enable Auto-Update Checks",
        "description": "Periodically check for new mod versions",
        "type": "bool",
        "category": "Updates",
    },
    "auto_updater.check_frequency": {
        "label": "Check Frequency",
        "description": "How often to check for updates",
        "type": "select",
        "options": ["daily", "weekly", "off"],
        "category": "Updates",
    },
    "auto_updater.auto_download": {
        "label": "Auto-Download Updates",
        "description": "Download updates automatically (still requires confirmation to install)",
        "type": "bool",
        "category": "Updates",
    },
    "auto_updater.channel": {
        "label": "Update Channel",
        "description": "Which release channel to follow",
        "type": "select",
        "options": ["stable", "beta"],
        "category": "Updates",
    },
}


class SettingsManager:
    """Manages QoL Pack settings with persistence and event notification.

    Settings are stored in-memory and persisted to a JSON file.
    Every change publishes a SettingsChangedEvent so modules can react.
    """

    _settings: dict = {}
    _settings_path = None
    _loaded = False

    @classmethod
    def load(cls, path=None):
        """Load settings from disk. Missing keys get defaults.

        Args:
            path: Path to settings JSON file. If None, uses the default
                 location in the Mods folder.
        """
        cls._settings_path = path or _default_settings_path()
        cls._settings = copy.deepcopy(DEFAULTS)

        if os.path.exists(cls._settings_path):
            try:
                with open(cls._settings_path, "r") as f:
                    saved = json.load(f)
                # Merge saved over defaults (only known keys)
                for key, value in saved.items():
                    if key in DEFAULTS:
                        cls._settings[key] = value
                log.info("Settings loaded", path=cls._settings_path)
            except (json.JSONDecodeError, OSError) as exc:
                log.warn("Failed to load settings, using defaults", error=str(exc))
        else:
            log.info("No saved settings found, using defaults")

        cls._loaded = True

    @classmethod
    def save(cls):
        """Persist current settings to disk."""
        if cls._settings_path is None:
            cls._settings_path = _default_settings_path()

        try:
            os.makedirs(os.path.dirname(cls._settings_path), exist_ok=True)
            with open(cls._settings_path, "w") as f:
                json.dump(cls._settings, f, indent=2)
            log.debug("Settings saved", path=cls._settings_path)
        except OSError as exc:
            log.error("Failed to save settings", error=str(exc))

    @classmethod
    def get(cls, key, default=None):
        """Get a setting value.

        Args:
            key: Setting key (e.g., "ui_tweaks.enabled").
            default: Value to return if key is not found.

        Returns:
            The setting value, or default.
        """
        return cls._settings.get(key, default)

    @classmethod
    def set(cls, key, value, persist=True):
        """Set a setting value and publish a change event.

        Args:
            key: Setting key.
            value: New value.
            persist: If True, save to disk after setting.

        Returns:
            True if the value actually changed.
        """
        if key not in DEFAULTS:
            log.warn("Attempted to set unknown setting", key=key)
            return False

        old_value = cls._settings.get(key)
        if old_value == value:
            return False

        cls._settings[key] = value

        EventBus.publish(
            SettingsChangedEvent(
                key=key,
                old_value=old_value,
                new_value=value,
            ),
            source_mod=MOD_ID,
        )

        if persist:
            cls.save()

        log.info("Setting changed", key=key, old=old_value, new=value)
        return True

    @classmethod
    def apply_preset(cls, preset_name):
        """Apply a settings preset.

        Args:
            preset_name: One of "beginner", "advanced", "streamer".

        Returns:
            True if the preset was applied, False if not found.
        """
        preset = PRESETS.get(preset_name)
        if preset is None:
            log.warn("Unknown preset", preset=preset_name)
            return False

        for key, value in preset.items():
            cls.set(key, value, persist=False)

        cls.save()

        EventBus.publish(
            PresetAppliedEvent(preset_name=preset_name),
            source_mod=MOD_ID,
        )

        log.info("Preset applied", preset=preset_name)
        return True

    @classmethod
    def get_all(cls):
        """Return a copy of all current settings.

        Returns:
            Dict of key -> value.
        """
        return dict(cls._settings)

    @classmethod
    def get_categories(cls):
        """Return settings grouped by category for UI rendering.

        Returns:
            Dict of category_name -> list of {key, value, metadata}.
        """
        categories = {}
        for key, value in cls._settings.items():
            meta = SETTING_METADATA.get(key, {})
            category = meta.get("category", "Other")
            if category not in categories:
                categories[category] = []
            categories[category].append({
                "key": key,
                "value": value,
                **meta,
            })
        return categories

    @classmethod
    def search(cls, query):
        """Search settings by key, label, or description.

        Args:
            query: Search string (case-insensitive).

        Returns:
            List of matching {key, value, metadata} dicts.
        """
        query_lower = query.lower()
        results = []
        for key, value in cls._settings.items():
            meta = SETTING_METADATA.get(key, {})
            searchable = " ".join([
                key,
                meta.get("label", ""),
                meta.get("description", ""),
            ]).lower()
            if query_lower in searchable:
                results.append({
                    "key": key,
                    "value": value,
                    **meta,
                })
        return results

    @classmethod
    def export_settings(cls, path):
        """Export current settings to a file for sharing.

        Args:
            path: Output file path.
        """
        with open(path, "w") as f:
            json.dump(cls._settings, f, indent=2)
        log.info("Settings exported", path=path)

    @classmethod
    def import_settings(cls, path):
        """Import settings from a file.

        Args:
            path: Input file path.

        Returns:
            True if import succeeded.
        """
        try:
            with open(path, "r") as f:
                imported = json.load(f)
            for key, value in imported.items():
                if key in DEFAULTS:
                    cls.set(key, value, persist=False)
            cls.save()
            log.info("Settings imported", path=path)
            return True
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to import settings", error=str(exc))
            return False

    @classmethod
    def reset(cls):
        """Reset all settings to defaults."""
        cls._settings = copy.deepcopy(DEFAULTS)
        cls.save()
        log.info("Settings reset to defaults")


# ── Internal helpers ────────────────────────────────────────────────

def _default_settings_path():
    """Get the default settings file path."""
    import sys
    if sys.platform == "win32":
        base = os.path.expanduser(
            "~/Documents/Electronic Arts/The Sims 4/Mods/StarkQoL"
        )
    elif sys.platform == "darwin":
        base = os.path.expanduser(
            "~/Documents/Electronic Arts/The Sims 4/Mods/StarkQoL"
        )
    else:
        base = "/tmp/StarkQoL"
    return os.path.join(base, "settings.json")
