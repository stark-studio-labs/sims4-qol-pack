# Stark QoL Pack

Unified quality-of-life mod for The Sims 4. Replaces UI Cheats Extension, T.O.O.L., Better Exceptions, and Sim Lag Fix with one integrated system built on the [Stark Framework](https://github.com/stark-studio-labs/sims4-stark-framework) event bus.

## Why one pack instead of four mods?

Players currently install 4+ separate QoL mods that conflict after patches, have overlapping injection targets, ship independent error handling that points blame at each other, and require separate update checks. This pack eliminates all of that.

## Modules

| Module | Replaces | What it does |
|--------|----------|-------------|
| **UI Tweaks** | UI Cheats Extension | Click-to-edit needs, skills, money, relationships, careers. Value-clamped, event-driven, zero tick cost. |
| **Build Tools** | T.O.O.L. | Precision XYZ positioning (0.01 grid), free 3-axis rotation, per-axis scaling, off-lot placement, 50-step undo. |
| **Performance** | Sim Lag Fix | Adaptive autonomy throttling, pathfinding debounce, stat decay deferral, save optimization. Auto-tunes based on FPS. |
| **Diagnostics** | Better Exceptions | Global exception handler with mod attribution, known-conflict database, auto-fix suggestions, one-click bug reports. |
| **Settings** | (new) | Unified visual settings panel. Three presets: Beginner (safe), Advanced (everything), Streamer (max perf). Import/export. |
| **Auto Updater** | (new) | Checks GitHub Releases for new versions. Notify, download, one-click install with backup. |

## Architecture

```
src/qol_pack/
  __init__.py           # Bootstrap: register with ModRegistry, init modules
  events.py             # 15 typed event dataclasses for cross-module communication
  modules/
    ui_tweaks.py        # Scaleform bridge pattern (UI Cheats architecture)
    build_tools.py      # Affordance injection pattern (TOOL architecture)
    performance.py      # Adaptive tuning + XML overrides (Sim Lag Fix architecture)
    diagnostics.py      # Exception interception + mod attribution
    settings.py         # Unified settings with presets and search
    auto_updater.py     # GitHub Releases polling + staged updates

tuning/
  autonomy_timing.xml   # Extend autonomy re-evaluation intervals
  time_scale.xml        # Adjust clock speed at Speed 2/3 to prevent desync
  routing_optimization.xml  # Reduce pathfinding recalculation frequency
```

### Design principles

1. **Zero idle cost** -- event-driven only, no per-tick polling (learned from all four reference mods)
2. **Native system piggybacking** -- use sentiments, affordances, tuning; no parallel data stores
3. **Tuning-first when possible** -- if it can be done via XML override, do it there (Sim Lag Fix pattern)
4. **Graceful degradation** -- each module works independently; if one fails, the rest continue
5. **Settings-driven** -- every tunable parameter lives in `settings.py` with a unified panel

### Event flow

```
Game starts
  -> qol_pack registers with ModRegistry
  -> Each module subscribes to EventBus
  -> settings.py loads saved settings, publishes SettingsChangedEvent per module
  -> auto_updater checks for updates (if due)

Player clicks a need bar
  -> UIEditRequestedEvent (cancellable)
  -> Value applied through game APIs
  -> UIValueChangedEvent published

FPS drops below target
  -> PerformanceOptimizer increases throttle level
  -> ThrottleLevelChangedEvent published
  -> Off-screen Sims run autonomy at reduced frequency
```

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
| Auto-update check | Weekly | Daily | Off |
| Error detail level | Simple | Full traceback | Simple |

## License

MIT
