# Tuning Overrides

XML tuning files that override vanilla Sims 4 game parameters. These are packaged into the `.package` file at build time and loaded by the game's tuning system at startup.

## Files

| File | What it does | Replaces |
|------|-------------|----------|
| `autonomy_timing.xml` | Extends autonomy re-evaluation intervals, reduces per-tick evaluations | Sim Lag Fix autonomy settings |
| `time_scale.xml` | Adjusts clock speed at Speed 2/3 to prevent simulation desync | Sim Lag Fix time scaling |
| `routing_optimization.xml` | Reduces pathfinding recalculation frequency, caps per-tick calculations | None (novel) |

## How tuning overrides work

The Sims 4 loads tuning from `.package` files at startup. When two packages define the same tuning resource, the last-loaded one wins. Our overrides use unique resource IDs to avoid conflicts with vanilla tuning -- they inject new parameters rather than replacing existing resources.

## Conflict matrix

| Override | Conflicts with | Safe with |
|----------|---------------|-----------|
| autonomy_timing | MCCC "Autonomy Scan Interval" | Everything else |
| time_scale | MCCC "Game Time Speed", SrslySims Sim Lag Fix | Simulation Unclogger |
| routing_optimization | None known | Everything tested |

## Editing guidelines

- Each `<T>` element includes vanilla default, StarkQoL value, and valid ranges
- Changes to these values are live-testable: modify the XML, rebuild the package, restart the game
- Always document conflict implications when changing values
