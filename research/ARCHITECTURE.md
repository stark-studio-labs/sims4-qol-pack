# sims4-qol-pack Architecture

## Overview

A unified quality-of-life mod pack for The Sims 4 that integrates capabilities currently spread across UI Cheats Extension, T.O.O.L. Mod, Better Exceptions, and Sim Lag Fix into one cohesive system built on the Stark Framework event bus.

## Problem Statement

Players install 4+ separate QoL mods that:
- Conflict with each other after patches
- Have overlapping injection targets
- Ship independent error handling that points blame at each other
- Require separate update checks on different schedules
- Cannot share state (e.g., diagnostics module can't see what UI tweaks module injected)

## Design Principles

1. **Single event bus** -- all modules communicate via `stark_framework.core.events.EventBus`
2. **Registry-first** -- every module registers with `ModRegistry` at load time
3. **Declarative injection** -- all game method hooks go through `InjectionManager`, making them visible to diagnostics
4. **Graceful degradation** -- each module works independently; if one fails, others continue
5. **Settings-driven** -- every tunable parameter lives in `settings.py` with a unified panel

## Module Map

```
qol_pack/
  __init__.py          -- Package init, registers with ModRegistry, bootstraps all modules
  events.py            -- All QoL Pack event types (dataclasses extending Event)
  modules/
    __init__.py
    ui_tweaks.py       -- Click-to-edit UI elements
    build_tools.py     -- Enhanced build/buy manipulation
    performance.py     -- Simulation performance optimization
    diagnostics.py     -- Error reporting + conflict detection
    settings.py        -- Unified settings panel + presets
    auto_updater.py    -- Version check + update notification
```

## Module Details

### 1. ui_tweaks.py -- Click-to-Edit UI Elements

**Replaces:** UI Cheats Extension

**What it does:**
- Intercepts clicks on UI elements (need bars, skill bars, money display, relationship panel, career panel)
- Opens an inline editor on click (slider or numeric input)
- Applies the change through game APIs (not raw memory writes)

**Key injections:**
- `ui.ui_dialog.UiDialog` -- intercept dialog responses for need/skill editing
- `sims.sim_info.SimInfo` -- need modification via commodity tracker
- `statistics.skill.Skill` -- skill level manipulation
- `sims.household.Household` -- funds manipulation

**Events published:**
- `UIValueChangedEvent(sim_id, field, old_value, new_value)` -- after any edit
- `UIEditRequestedEvent(sim_id, field)` -- before edit (cancellable)

**Events consumed:**
- `SettingsChangedEvent` -- to check if UI tweaks are enabled/disabled

### 2. build_tools.py -- Enhanced Object Positioning

**Replaces:** T.O.O.L. Mod

**What it does:**
- Fine-grained object positioning (XYZ coordinates with 0.01 precision)
- Free rotation on all 3 axes (not just Y-axis snapping)
- Object scaling (uniform and per-axis)
- Off-lot placement (place objects beyond lot boundaries)
- Object cloning/mirroring

**Key injections:**
- `objects.game_object.GameObject` -- position/rotation/scale overrides
- `build_buy` module -- lot boundary bypass
- `placement` module -- custom placement validation

**Events published:**
- `ObjectMovedEvent(object_id, old_pos, new_pos)` -- after repositioning
- `ObjectScaledEvent(object_id, old_scale, new_scale)` -- after scaling
- `BuildModeEnteredEvent` / `BuildModeExitedEvent` -- mode transitions

**Events consumed:**
- `SettingsChangedEvent` -- precision settings, axis lock toggles

### 3. performance.py -- Simulation Lag Fix

**Replaces:** Sim Lag Fix + general performance tweaks

**What it does:**
- Throttles autonomy ticks for off-screen Sims (run at 1/4 rate)
- Reduces pathfinding recalculation frequency
- Defers non-critical stat decay when many Sims are active
- Optimizes save serialization (skip unchanged objects)
- Monitors frame time and auto-adjusts throttling

**Key injections:**
- `autonomy.autonomy_component.AutonomyComponent` -- tick throttling
- `routing.route_events` -- pathfinding debounce
- `persistence_service` -- save optimization

**Events published:**
- `PerformanceReportEvent(fps, sim_count, throttle_level)` -- periodic health
- `ThrottleLevelChangedEvent(old_level, new_level)` -- when auto-tuning adjusts

**Events consumed:**
- `SettingsChangedEvent` -- min FPS target, throttle aggressiveness
- `BuildModeEnteredEvent` -- pause sim throttling in build mode

### 4. diagnostics.py -- Better Error Reporting

**Replaces:** Better Exceptions + MC Command Center's error logging

**What it does:**
- Extends `stark_framework.core.diagnostics.Diagnostics` with QoL-specific checks
- Catches and formats all Python exceptions with full mod attribution
- Cross-references errors against known mod conflicts
- Generates one-click bug report files
- Suggests fixes for common issues (missing dependencies, version mismatches)

**Key injections:**
- `sys.excepthook` -- global exception handler override
- `zone.Zone` -- zone load/unload error boundaries

**Events published:**
- `ErrorCapturedEvent(mod_id, error_type, message, traceback, suggested_fix)`
- `ConflictDetectedEvent(mod_a, mod_b, conflict_type, description)`

**Events consumed:**
- All framework events (for correlation: "error happened right after X event")

### 5. settings.py -- Unified Settings Panel

**What it does:**
- Single settings panel accessible from game menu
- Visual UI with categories, search, tooltips
- Presets: Beginner (safe defaults), Advanced (all features), Streamer (performance-first)
- Import/export settings as JSON
- Per-Sim overrides for UI tweaks

**Storage:** JSON file in `Mods/StarkQoL/settings.json`

**Events published:**
- `SettingsChangedEvent(key, old_value, new_value)` -- on any setting change
- `PresetAppliedEvent(preset_name)` -- when a preset is loaded

**Presets:**
| Setting | Beginner | Advanced | Streamer |
|---------|----------|----------|----------|
| UI click-to-edit | Needs only | All fields | Disabled |
| Build precision | 0.1 | 0.01 | 0.1 |
| Off-lot placement | Off | On | Off |
| Perf throttle | Conservative | Aggressive | Maximum |
| Auto-update check | Weekly | Daily | Off |
| Error detail level | Simple | Full traceback | Simple |

### 6. auto_updater.py -- Mod Update System

**What it does:**
- Checks a manifest URL for new versions (GitHub Releases API)
- Shows in-game notification when update available
- Downloads update to staging folder
- User confirms to apply (swap .ts4script files)
- Tracks update history

**Events published:**
- `UpdateAvailableEvent(current_version, new_version, changelog)`
- `UpdateInstalledEvent(version, restart_required)`

**Events consumed:**
- `SettingsChangedEvent` -- update check frequency

## Event Flow Diagram

```
Game starts
  -> qol_pack.__init__ registers with ModRegistry
  -> Each module subscribes to EventBus
  -> settings.py loads saved settings, publishes SettingsChangedEvent
  -> auto_updater checks for updates (if due)

Player clicks a need bar
  -> ui_tweaks publishes UIEditRequestedEvent
  -> (no cancellation)
  -> ui_tweaks modifies the value
  -> ui_tweaks publishes UIValueChangedEvent
  -> diagnostics logs the change for correlation

Python exception occurs
  -> diagnostics.py catches via sys.excepthook
  -> Parses traceback, identifies originating mod
  -> Publishes ErrorCapturedEvent
  -> Checks against known conflicts -> ConflictDetectedEvent if match
  -> Shows notification to player with suggested fix

Player enters build mode
  -> build_tools publishes BuildModeEnteredEvent
  -> performance.py receives it, pauses sim throttling
  -> build_tools enables enhanced placement controls
```

## Stark Framework Integration

All modules depend on `stark_framework >= 0.1.0`:

- **EventBus** (`stark_framework.core.events`) -- all inter-module communication
- **ModRegistry** (`stark_framework.core.registry`) -- mod registration + conflict detection
- **InjectionManager** (`stark_framework.core.injection`) -- all game method hooks
- **Diagnostics** (`stark_framework.core.diagnostics`) -- error tracking foundation
- **Logger** (`stark_framework.utils.logging`) -- structured logging throughout
- **TuningHelper** (`stark_framework.utils.tuning`) -- XML tuning lookups for UI tweaks

## File Layout (Final)

```
sims4-qol-pack/
  research/
    ARCHITECTURE.md          <- You are here
  src/
    qol_pack/
      __init__.py            <- ModRegistry registration, module bootstrap
      events.py              <- All event dataclasses
      modules/
        __init__.py
        ui_tweaks.py         <- Click-to-edit UI elements
        build_tools.py       <- Enhanced build/buy tools
        performance.py       <- Sim lag fix + optimization
        diagnostics.py       <- Error reporting + conflict detection
        settings.py          <- Unified settings panel + presets
        auto_updater.py      <- Version check + update system
  tests/
    test_events.py
    test_ui_tweaks.py
    test_build_tools.py
    test_performance.py
    test_diagnostics.py
    test_settings.py
    test_auto_updater.py
    conftest.py              <- Shared fixtures (mock game APIs)
  .gitignore
  README.md
```
