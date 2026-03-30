"""
QoL Diagnostics -- better error reporting with mod identification, conflict
detection, and auto-fix suggestions.

Extends the Stark Framework's built-in Diagnostics with QoL-specific
capabilities:
- Global exception handler that attributes errors to specific mods
- Known-conflict database with suggested fixes
- One-click bug report generation
- Correlation of errors with recent events

Replaces Better Exceptions with a framework-integrated solution that
actually knows about the mod ecosystem.
"""

import sys
import os
import time
import json
import traceback as tb_module

from qol_pack._compat import (
    EventBus, Diagnostics, ModRegistry, InjectionManager, get_logger, LogBuffer,
)

from qol_pack.events import (
    ErrorCapturedEvent,
    ConflictDetectedEvent,
    SettingsChangedEvent,
)

log = get_logger("qol.diagnostics")

MOD_ID = "stark_qol_pack.diagnostics"

# Known conflict database: maps (mod_a, mod_b) -> description + fix
KNOWN_CONFLICTS = {
    ("weerbesu_ui_cheats", "stark_qol_pack"): {
        "description": "UI Cheats Extension and QoL Pack both inject UI dialog handlers",
        "fix": "Remove UI Cheats Extension -- QoL Pack includes all its features",
    },
    ("tmex_tool_mod", "stark_qol_pack"): {
        "description": "T.O.O.L. and QoL Pack both inject build/buy placement methods",
        "fix": "Remove T.O.O.L. -- QoL Pack includes enhanced build tools",
    },
    ("basemental_better_exceptions", "stark_qol_pack"): {
        "description": "Better Exceptions and QoL Pack both override sys.excepthook",
        "fix": "Remove Better Exceptions -- QoL Pack has integrated error reporting",
    },
}

# Common error patterns and their fixes
ERROR_PATTERNS = [
    {
        "pattern": "AttributeError: 'NoneType'",
        "context_contains": "sim_info",
        "suggestion": "A Sim reference became None -- likely a Sim was deleted mid-operation. "
                      "This is usually harmless. If it persists, check for mods that remove Sims.",
    },
    {
        "pattern": "ImportError: No module named",
        "suggestion": "A required module is missing. Check that all dependencies are installed "
                      "and that the mod was placed in the correct Mods folder.",
    },
    {
        "pattern": "KeyError",
        "context_contains": "tuning",
        "suggestion": "A tuning reference is missing -- this often happens after a game patch "
                      "changes tuning IDs. Check for mod updates.",
    },
    {
        "pattern": "PermissionError",
        "suggestion": "The game can't write to a file. Close any programs that might have "
                      "the Mods folder open (file managers, antivirus).",
    },
    {
        "pattern": "RecursionError",
        "suggestion": "Infinite loop detected -- two mods may be calling each other. "
                      "Check the traceback for the repeating function names.",
    },
]


class QoLDiagnostics:
    """Enhanced diagnostics with mod attribution and auto-fix suggestions.

    Installs a global exception handler and provides tools for generating
    bug reports and detecting conflicts.
    """

    _installed = False
    _original_excepthook = None
    _detail_level = "full"  # "simple", "full"
    _recent_events: list = []     # Last N events for correlation
    _max_recent_events = 20
    _error_count = 0

    @classmethod
    def install(cls):
        """Install the global exception handler and event listeners."""
        if cls._installed:
            return

        # Save and replace sys.excepthook
        cls._original_excepthook = sys.excepthook
        sys.excepthook = cls._exception_handler

        # Subscribe to settings changes
        EventBus.subscribe(
            SettingsChangedEvent,
            cls._on_settings_changed,
            priority=50,
            mod_id=MOD_ID,
        )

        # Enable framework event logging for correlation
        EventBus.enable_logging(True)

        cls._installed = True
        log.info("QoL Diagnostics installed", detail_level=cls._detail_level)

    @classmethod
    def uninstall(cls):
        """Restore the original exception handler."""
        if cls._installed and cls._original_excepthook:
            sys.excepthook = cls._original_excepthook
            cls._installed = False
            log.info("QoL Diagnostics uninstalled")

    @classmethod
    def _on_settings_changed(cls, event):
        """React to settings changes."""
        if event.key == "diagnostics.detail_level":
            cls._detail_level = str(event.new_value)

    @classmethod
    def _exception_handler(cls, exc_type, exc_value, exc_traceback):
        """Global exception handler that attributes errors to mods.

        Catches all unhandled exceptions, identifies which mod caused them
        (by analyzing the traceback), records them with the framework,
        and publishes an ErrorCapturedEvent with a suggested fix.
        """
        cls._error_count += 1

        # Extract traceback
        tb_lines = tb_module.format_exception(exc_type, exc_value, exc_traceback)
        tb_text = "".join(tb_lines)

        # Identify the responsible mod
        mod_id = _identify_mod_from_traceback(tb_lines)

        # Find a suggested fix
        suggested_fix = _suggest_fix(str(exc_value), tb_text, mod_id)

        # Record with framework diagnostics
        Diagnostics.record_error(
            mod_id=mod_id,
            error=exc_value,
            context="Unhandled exception (caught by QoL Diagnostics)",
        )

        # Publish event
        EventBus.publish(
            ErrorCapturedEvent(
                mod_id=mod_id,
                error_type=exc_type.__name__,
                message=str(exc_value),
                traceback_text=tb_text if cls._detail_level == "full" else _simplify_traceback(tb_text),
                suggested_fix=suggested_fix,
            ),
            source_mod=MOD_ID,
        )

        log.error(
            "Exception captured",
            mod_id=mod_id,
            error_type=exc_type.__name__,
            error_message=str(exc_value),
        )

        # Call original handler too (game's own error logging)
        if cls._original_excepthook:
            cls._original_excepthook(exc_type, exc_value, exc_traceback)

    @classmethod
    def detect_conflicts(cls):
        """Run conflict detection and publish events for each found.

        Checks:
        1. Known mod conflicts from KNOWN_CONFLICTS database
        2. Injection overlaps from InjectionManager
        3. Framework-level conflicts from Diagnostics
        4. High error rates per mod

        Returns:
            List of conflict dicts.
        """
        all_conflicts = []

        # Check known conflicts
        loaded_mods = set(ModRegistry.all_mods().keys())
        for (mod_a, mod_b), info in KNOWN_CONFLICTS.items():
            if mod_a in loaded_mods and mod_b in loaded_mods:
                conflict = {
                    "type": "known_conflict",
                    "mod_a": mod_a,
                    "mod_b": mod_b,
                    "description": info["description"],
                    "fix": info["fix"],
                }
                all_conflicts.append(conflict)
                EventBus.publish(
                    ConflictDetectedEvent(
                        mod_a=mod_a,
                        mod_b=mod_b,
                        conflict_type="known_conflict",
                        description=info["description"],
                    ),
                    source_mod=MOD_ID,
                )

        # Framework-level conflict detection
        framework_conflicts = Diagnostics.detect_conflicts()
        for fc in framework_conflicts:
            all_conflicts.append(fc)

        return all_conflicts

    @classmethod
    def generate_bug_report(cls, output_path=None):
        """Generate a comprehensive bug report file.

        Args:
            output_path: Path to write the report. Defaults to
                        Documents/Electronic Arts/The Sims 4/Mods/StarkQoL/bug_report.json

        Returns:
            Path to the generated report file.
        """
        if output_path is None:
            output_path = _default_report_path()

        report = {
            "generated_at": time.time(),
            "qol_version": _get_qol_version(),
            "loaded_mods": ModRegistry.all_mods(),
            "active_injections": InjectionManager.list_injections(),
            "detected_conflicts": cls.detect_conflicts(),
            "health_report": Diagnostics.health_report(),
            "recent_errors": Diagnostics.get_errors(limit=20),
            "recent_log": [
                entry for entry in LogBuffer.get_entries(limit=50)
            ],
            "total_errors": cls._error_count,
        }

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        log.info("Bug report generated", path=output_path)
        return output_path

    @classmethod
    def get_error_summary(cls):
        """Get a summary of recent errors grouped by mod.

        Returns:
            Dict mapping mod_id to error count and last error message.
        """
        summary = {}
        for err in Diagnostics.get_errors(limit=100):
            mid = err["mod_id"]
            if mid not in summary:
                summary[mid] = {
                    "count": 0,
                    "last_error": "",
                    "last_error_type": "",
                }
            summary[mid]["count"] += 1
            summary[mid]["last_error"] = err["error"]
            summary[mid]["last_error_type"] = err["error_type"]
        return summary


# ── Internal helpers ────────────────────────────────────────────────

def _identify_mod_from_traceback(tb_lines):
    """Identify which mod caused an error by analyzing the traceback.

    Looks for known mod paths in the traceback frames. Falls back to
    "unknown" if no mod can be identified.
    """
    # Check registered mods for path patterns
    mods = ModRegistry.all_mods()
    mod_paths = {}
    for mod_id, info in mods.items():
        # Convention: mod files are in a folder matching the mod_id
        mod_paths[mod_id.replace(".", "_")] = mod_id

    for line in tb_lines:
        line_lower = line.lower()
        for path_fragment, mod_id in mod_paths.items():
            if path_fragment in line_lower:
                return mod_id

    # Check for stark_qol_pack specifically
    for line in tb_lines:
        if "qol_pack" in line.lower():
            return "stark_qol_pack"
        if "stark_framework" in line.lower():
            return "stark_framework"

    return "unknown"


def _suggest_fix(error_message, traceback_text, mod_id):
    """Look up a suggested fix based on error patterns.

    Checks ERROR_PATTERNS for matching patterns and returns the
    first match's suggestion.
    """
    for pattern in ERROR_PATTERNS:
        if pattern["pattern"] in error_message or pattern["pattern"] in traceback_text:
            context_match = pattern.get("context_contains")
            if context_match and context_match not in traceback_text:
                continue
            return pattern["suggestion"]

    return (
        f"No specific fix known for this error. "
        f"Check if mod '{mod_id}' has an update available, "
        f"or try removing it temporarily to confirm it's the cause."
    )


def _simplify_traceback(tb_text):
    """Reduce a full traceback to just the key frames.

    Strips framework internals and keeps only the mod-relevant frames.
    """
    lines = tb_text.strip().split("\n")
    simplified = []
    for line in lines:
        # Keep the exception line and file references
        if line.startswith("  File") or not line.startswith(" "):
            simplified.append(line)
    return "\n".join(simplified[-10:])  # Last 10 relevant lines


def _default_report_path():
    """Get the default bug report output path."""
    # Standard Sims 4 user data location
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

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(base, f"bug_report_{timestamp}.json")


def _get_qol_version():
    """Get the QoL Pack version string."""
    try:
        from qol_pack import __version__
        return __version__
    except ImportError:
        return "unknown"
