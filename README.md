# Stark QoL Pack

Unified quality-of-life mod for The Sims 4. Replaces UI Cheats Extension, T.O.O.L., Better Exceptions, and Sim Lag Fix with one integrated system built on the [Stark Framework](https://github.com/stark-studio-labs/sims4-stark-framework) event bus.

## Why one pack instead of four mods?

Players currently install 4+ separate QoL mods that conflict after patches, have overlapping injection targets, ship independent error handling that points blame at each other, and require separate update checks. This pack eliminates all of that.

## Comparison: QoL Pack vs Individual Mods

| Capability | UI Cheats | T.O.O.L. | Better Exceptions | Sim Lag Fix | **QoL Pack** |
|-----------|-----------|----------|-------------------|-------------|-------------|
| Click-to-edit UI elements | Yes | -- | -- | -- | **Yes** |
| Precision object placement | -- | Yes (numeric) | -- | -- | **Yes (numeric + snap)** |
| Free 3-axis rotation | -- | Yes (Y primary) | -- | -- | **Yes (full XYZ)** |
| Per-axis scaling | -- | No (uniform only) | -- | -- | **Yes** |
| Undo stack | -- | No | -- | -- | **Yes (50 steps)** |
| Exception attribution | -- | -- | Yes (heuristic) | -- | **Yes (registry-informed)** |
| Proactive conflict scan | -- | -- | No (reactive only) | -- | **Yes** |
| Autonomy throttling | -- | -- | -- | Tuning override | **Adaptive + tuning** |
| Pathfinding debounce | -- | -- | -- | No | **Yes** |
| Save optimization | -- | -- | -- | No | **Yes** |
| Settings presets | No config | No config | No config | No config | **3 presets** |
| Unified settings panel | -- | -- | -- | -- | **Yes (search, categories)** |
| Auto-update checking | -- | -- | -- | -- | **Yes** |
| Event bus integration | No | No | No | No | **Yes** |
| Open source | No | No | No | No | **MIT** |
| Single install | 1 mod | 1 mod (+BBB) | 1 mod | 1 mod | **1 mod replaces all** |
| Scaleform bridge API | Internal | -- | -- | -- | **Shared registry** |
| Affordance injection API | -- | Internal | -- | -- | **Shared registry** |
| Autonomy throttle API | -- | -- | -- | Internal | **Shared + adaptive** |

## Core Architecture (v0.2.0)

The QoL Pack is built on three core infrastructure layers extracted from decompilation analysis of the reference mods:

```
src/qol_pack/
  __init__.py              # Bootstrap: core -> modules in dependency order
  events.py                # 15+ typed event dataclasses

  core/                    # Infrastructure extracted from reference mods
    scaleform_bridge.py    # UI Cheats pattern: Flash ExternalInterface abstraction
    affordance_injector.py # TOOL pattern: universal SuperInteraction injection
    autonomy_throttle.py   # Sim Lag Fix pattern: autonomy skip + time scale sync

  modules/                 # Feature modules built on core infrastructure
    ui_tweaks.py           # Click-to-edit (uses scaleform_bridge)
    build_tools.py         # Precision placement (uses affordance_injector)
    performance.py         # Adaptive FPS optimization (uses autonomy_throttle)
    diagnostics.py         # Exception handling + mod attribution
    settings.py            # Unified settings with presets and search
    auto_updater.py        # GitHub Releases polling + staged updates

tuning/                    # XML tuning overrides (Sim Lag Fix pattern)
  autonomy_timing.xml      # Extend autonomy re-evaluation intervals
  time_scale.xml           # Adjust clock speed at Speed 2/3
  routing_optimization.xml # Reduce pathfinding recalculation frequency
```

### Core Infrastructure (NEW in v0.2.0)

| Core System | Pattern Source | What It Provides |
|-------------|---------------|-----------------|
| **ScaleformBridge** | UI Cheats Extension | Shared click-handler registry for the Flash ExternalInterface. Any module can register UI click actions. |
| **AffordanceInjector** | T.O.O.L. | Universal interaction injection via `_super_affordances`. Register once, inject to all objects on zone load. |
| **AutonomyThrottle** | Sim Lag Fix | Hooks into autonomy evaluation pipeline. Skip-ratio for off-screen Sims, multitasking break extension, time scale synchronization. |

### Design Principles

1. **Zero idle cost** -- event-driven only, no per-tick polling (all four reference mods share this)
2. **Native system piggybacking** -- use sentiments, affordances, tuning; no parallel data stores
3. **Tuning-first when possible** -- if it can be done via XML override, do it there (Sim Lag Fix pattern)
4. **Graceful degradation** -- each module works independently; if one fails, the rest continue
5. **Settings-driven** -- every tunable parameter lives in `settings.py` with a unified panel
6. **Shared infrastructure** -- core systems are available to all modules AND to third-party mods via public API

### Event Flow

```
Game starts
  -> Core infrastructure loads (Scaleform bridge, affordance injector, autonomy throttle)
  -> qol_pack registers with ModRegistry
  -> Each module subscribes to EventBus
  -> AffordanceInjector hooks into InstanceManager.add_on_load_complete()
  -> settings.py loads saved settings, publishes SettingsChangedEvent per module
  -> auto_updater checks for updates (if due)

Zone loads (entering household)
  -> AffordanceInjector runs: injects registered interactions into object affordances
  -> AutonomyThrottle activates: begins monitoring tick times

Player clicks a need bar
  -> ScaleformBridge intercepts Flash ExternalInterface message
  -> Routes to registered click handler in UITweaks
  -> UIEditRequestedEvent (cancellable)
  -> Value applied through game APIs
  -> UIValueChangedEvent published

FPS drops below target
  -> AutonomyThrottle increases skip ratio for off-screen Sims
  -> PerformanceOptimizer publishes ThrottleLevelChangedEvent
  -> Time scale sync prevents clock desync
```

## Modules

| Module | Replaces | What it does |
|--------|----------|-------------|
| **UI Tweaks** | UI Cheats Extension | Click-to-edit needs, skills, money, relationships, careers. Value-clamped, event-driven, zero tick cost. |
| **Build Tools** | T.O.O.L. | Precision XYZ positioning (0.01 grid), free 3-axis rotation, per-axis scaling, off-lot placement, 50-step undo. |
| **Performance** | Sim Lag Fix | Adaptive autonomy throttling, pathfinding debounce, stat decay deferral, save optimization. Auto-tunes based on FPS. |
| **Diagnostics** | Better Exceptions | Global exception handler with mod attribution, known-conflict database, auto-fix suggestions, one-click bug reports. |
| **Settings** | (new) | Unified visual settings panel. Three presets: Beginner (safe), Advanced (everything), Streamer (max perf). Import/export. |
| **Auto Updater** | (new) | Checks GitHub Releases for new versions. Notify, download, one-click install with backup. |

## Roadmap

### v0.1.0 (Done)
- 6 modules: UI Tweaks, Build Tools, Performance, Diagnostics, Settings, Auto Updater
- 15 typed events for cross-module communication
- 3 tuning override files (autonomy timing, time scale, routing)
- 161 tests passing

### v0.2.0 (Current)
- Core infrastructure extracted from reference mod decompilation
- `ScaleformBridge`: shared click-handler registry (UI Cheats pattern)
- `AffordanceInjector`: universal interaction injection (TOOL pattern)
- `AutonomyThrottle`: autonomy skip + time scale sync (Sim Lag Fix pattern)
- Comparison table vs individual mods
- Boot sequence: core infrastructure loads before modules

### v0.3.0 (Planned)
- In-game settings UI via pie menu (shift-click on Sim or mailbox)
- Preset selector accessible from settings panel
- Notification overlay for errors and updates
- CurseForge distribution

### v0.4.0 (Planned)
- Third-party mod API: other mods can register click handlers, affordance injections, and autonomy hooks
- Plugin system for community extensions
- Mod compatibility database (crowdsourced conflict data)
- Integration with Stark Mod Manager for one-click install

### v1.0.0 (Target)
- Feature parity with all four reference mods
- Full Scaleform UI panel integration (not just click handlers)
- Automated patch compatibility testing
- Comprehensive documentation for third-party developers

## Installation

1. Install the [Stark Framework](https://github.com/stark-studio-labs/sims4-stark-framework) (dependency)
2. Download `StarkQoLPack.ts4script` and `StarkQoLPack.package` from [Releases](https://github.com/stark-studio-labs/sims4-qol-pack/releases)
3. Place both files in `Documents/Electronic Arts/The Sims 4/Mods/`
4. **Remove** conflicting mods: UI Cheats Extension, T.O.O.L., Better Exceptions, Sim Lag Fix

## Compatibility

| Mod | Status | Notes |
|-----|--------|-------|
| UI Cheats Extension | **Remove** | QoL Pack includes all its features |
| T.O.O.L. | **Remove** | QoL Pack includes enhanced build tools |
| Better Exceptions | **Remove** | QoL Pack has integrated error reporting |
| Sim Lag Fix | **Remove** | QoL Pack includes performance tuning |
| MCCC | Compatible | Do not change MCCC's "Game Time Speed" or "Autonomy Scan Interval" |
| Simulation Unclogger | Compatible | Complementary (kills stuck actions; QoL Pack prevents desync) |
| Wicked Whims | Compatible | No overlapping hooks |
| LittleMsSam mods | Compatible | No overlapping hooks |

## Development

```bash
# Clone
git clone https://github.com/stark-studio-labs/sims4-qol-pack.git
cd sims4-qol-pack

# Run tests (requires sims4-stark-framework sibling directory)
python3 -m pytest tests/ -q

# Build .ts4script (compile to .pyc and zip)
python3 -m compileall src/qol_pack/ -b
cd src && zip -r ../StarkQoLPack.ts4script qol_pack/**/*.pyc && cd ..
```

## Presets

| Setting | Beginner | Advanced | Streamer |
|---------|----------|----------|----------|
| UI click-to-edit | Needs only | All fields | Disabled |
| Build precision | 0.1 | 0.01 | 0.1 |
| Off-lot placement | Off | On | Off |
| Performance throttle | Light | None (adaptive) | Aggressive |
| Autonomy skip ratio | 2 (light) | 1 (none) | 8 (aggressive) |
| Auto-update check | Weekly | Daily | Off |
| Error detail level | Simple | Full traceback | Simple |

## License

MIT
