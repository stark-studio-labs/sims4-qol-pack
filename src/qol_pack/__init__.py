"""
QoL Pack -- Unified quality-of-life mod for The Sims 4.

Combines UI Cheats, T.O.O.L., Better Exceptions, and Sim Lag Fix into one
integrated system built on the Stark Framework event bus.

Boot sequence:
1. Register with ModRegistry
2. Load saved settings
3. Initialize each module (order matters: settings first, diagnostics early)
4. Check for updates (non-blocking)
"""

__version__ = "0.1.0"
__author__ = "Stark Labs"
__mod_id__ = "stark_qol_pack"

from stark_framework.core.registry import ModRegistry
from stark_framework.utils.logging import get_logger

log = get_logger("qol_pack")


def bootstrap():
    """Initialize the QoL Pack. Called once at mod load time.

    Registers with ModRegistry, loads settings, and initializes all modules
    in dependency order. Each module is isolated -- if one fails, the rest
    still load.
    """
    # Step 1: Register with the framework
    ModRegistry.register(
        mod_id=__mod_id__,
        name="Stark QoL Pack",
        version=__version__,
        author=__author__,
        dependencies=["stark_framework"],
        conflicts=[
            "weerbesu_ui_cheats",     # UI Cheats Extension
            "tmex_tool_mod",          # T.O.O.L.
            "basemental_better_exceptions",  # Better Exceptions
        ],
        metadata={
            "description": "Unified quality-of-life mod pack",
            "url": "https://github.com/stark-studio-labs/sims4-qol-pack",
        },
    )
    log.info("Registered with ModRegistry", version=__version__)

    # Step 2: Initialize modules in dependency order
    _init_modules()

    log.info("QoL Pack bootstrap complete")


def _init_modules():
    """Load each module, catching failures individually."""
    modules = [
        ("settings", _init_settings),
        ("diagnostics", _init_diagnostics),
        ("ui_tweaks", _init_ui_tweaks),
        ("build_tools", _init_build_tools),
        ("performance", _init_performance),
        ("auto_updater", _init_auto_updater),
    ]

    for name, init_fn in modules:
        try:
            init_fn()
            log.info(f"Module initialized: {name}")
        except Exception as exc:
            log.error(f"Failed to initialize module: {name}", error=str(exc))
            # Record with framework diagnostics so it shows in health reports
            from stark_framework.core.diagnostics import Diagnostics
            Diagnostics.record_error(
                mod_id=__mod_id__,
                error=exc,
                context=f"Initializing module: {name}",
            )


def _init_settings():
    from qol_pack.modules.settings import SettingsManager
    SettingsManager.load()


def _init_diagnostics():
    from qol_pack.modules.diagnostics import QoLDiagnostics
    QoLDiagnostics.install()


def _init_ui_tweaks():
    from qol_pack.modules.ui_tweaks import UITweaks
    UITweaks.install()


def _init_build_tools():
    from qol_pack.modules.build_tools import BuildTools
    BuildTools.install()


def _init_performance():
    from qol_pack.modules.performance import PerformanceOptimizer
    PerformanceOptimizer.install()


def _init_auto_updater():
    from qol_pack.modules.auto_updater import AutoUpdater
    AutoUpdater.install()
