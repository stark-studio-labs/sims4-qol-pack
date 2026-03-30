# QoL Layer Decompilation Analysis
## UI Cheats Extension | TOOL | Simulation Lag Fix | First Impressions

**Date:** 2026-03-30
**Purpose:** Reverse-engineer the architecture of four best-in-class Sims 4 QoL mods to extract patterns for the Stark Pack unified QoL layer.

---

## Table of Contents

1. [Sims 4 Modding Architecture Primer](#1-sims-4-modding-architecture-primer)
2. [UI Cheats Extension (Weerbesu)](#2-ui-cheats-extension-weerbesu)
3. [T.O.O.L. (TwistedMexi)](#3-tool-twistedmexi)
4. [Simulation Lag Fix (SrslySims)](#4-simulation-lag-fix-srslysims)
5. [First Impressions (Lumpinou)](#5-first-impressions-lumpinou)
6. [Cross-Mod Pattern Analysis](#6-cross-mod-pattern-analysis)
7. [Unified QoL Layer Design](#7-unified-qol-layer-design)

---

## 1. Sims 4 Modding Architecture Primer

Before dissecting each mod, the foundational architecture must be understood. The Sims 4 exposes two modding surfaces: **tuning overrides** (XML) and **script injection** (Python). All four QoL mods under analysis are primarily script mods.

### 1.1 Script Mod Loading Pipeline

```
Mods/
  MyMod.ts4script          # Renamed .zip containing compiled .pyc files
  MyMod.package            # Optional: UI assets, tuning overrides, Scaleform GFx
```

- `.ts4script` = renamed `.zip` archive containing Python 3.7 compiled bytecode (`.pyc`)
- Game recursively scans `Mods/` but only **one subfolder deep** for `.ts4script` files
- `.pyc` files are loaded directly; `.py` files are fallback only if `.pyc` version mismatch
- A `Scripts/` dev folder exists for unpackaged `.py` development (recursive scan)

### 1.2 Injection Patterns

The game's Python layer uses **InstanceManagers** to load tuning data into class instances. Three canonical injection patterns:

**Pattern A: InstanceManager.add_on_load_complete()**
```python
# Register callback that fires after all instances of a type load
services.affordance_manager().add_on_load_complete(do_injections)

def do_injections(manager):
    # Modify loaded tuning at runtime
    key = sims4.resources.get_resource_key(interaction_id, Types.INTERACTION)
    sa_tuning = manager.get(key)
    obj_tuning._super_affordances += (sa_tuning,)
```

**Pattern B: Monkey-patching InstanceManager.load_data_into_class_instances()**
```python
from sims4.tuning.instance_manager import InstanceManager

_orig = InstanceManager.load_data_into_class_instances
def _patched(self):
    _orig(self)
    if self.TYPE == Types.OBJECT:
        # inject custom affordances into objects
InstanceManager.load_data_into_class_instances = _patched
```

**Pattern C: CommonInjectionUtils decorator (S4CL pattern)**
```python
@CommonInjectionUtils.inject_safely_into(mod_identity, TargetClass, 'target_method')
def _wrapped(original, self, *args, **kwargs):
    # Pre-processing
    result = original(self, *args, **kwargs)
    # Post-processing
    return result
```

### 1.3 Tuning Mutability

All tunables load as **immutable** (frozendict, frozen tuples). To modify:
1. Convert immutable container to mutable form
2. Apply modifications
3. Convert back and assign via `setattr()`

### 1.4 UI Layer (Scaleform GFx)

The Sims 4 UI runs on **Autodesk Scaleform GFx** -- a Flash/ActionScript runtime embedded in the game engine. Key architectural details:

- UI elements are compiled `.swf` (Flash) files stored in `.package` resources
- Python communicates with Flash via **ExternalInterface** bridge (ActionScript `call()` <-> Python handler)
- Script mods can intercept UI messages between the Python backend and Flash frontend
- `.package` files can contain modified Scaleform GFx assets alongside tuning overrides

---

## 2. UI Cheats Extension (Weerbesu)

**Downloads:** 10M+ (most downloaded Sims 4 mod ever)
**Mod Type:** Script + Package (dual-file)
**Current Version:** v1.53

### 2.1 Architecture Overview

UI Cheats Extension is a **UI-layer interception mod** that adds click-to-edit functionality to every major game panel. It operates through a two-file architecture:

| File | Purpose |
|------|---------|
| `UI_Cheats_Extension.package` | Modified Scaleform GFx assets -- adds visual affordances (clickable zones, context menus) to UI panels |
| `UI_Cheats_Extension_Scripts.ts4script` | Python script handlers that intercept clicks and execute cheat commands |

### 2.2 Game Systems Hooked

The mod intercepts the **Python-to-Flash message bridge**, adding click handlers to existing UI elements. Hooked systems:

| UI Panel | Left-Click Action | Right-Click Action |
|----------|-------------------|-------------------|
| **Simoleon Counter** | +1,000 Simoleons | Open value setter dialog |
| **Need Bars** (hunger, energy, etc.) | Set need to clicked position | Maximize/minimize need |
| **Skill Meters** | Increment skill level | Set arbitrary level |
| **Relationship Panel** | +10 relationship | Open value setter (-100 to 100) |
| **Career Panel** | Promote | Demote / change career branch |
| **Aspiration Tracker** | Complete milestone | Add satisfaction points |
| **Clock/Calendar** | Advance time | Change season / weather |
| **Household Management** | Add Sim to household | Remove Sim |
| **Pregnancy Status** | Advance trimester | Set father / trigger labor |
| **Character Values** (parenthood) | +/- value | Set arbitrary value |
| **Fame/Reputation** | Increment | Set level directly |

### 2.3 Technical Implementation Pattern

```
User Click on UI Element
  -> Scaleform GFx captures click event (modified .swf in .package)
  -> Flash ExternalInterface.call() sends message to Python
  -> ts4script handler receives click coordinates + UI element ID
  -> Handler maps (element_id, click_type) -> cheat_command
  -> Executes game state modification via:
     - sims.sim_info.SimInfo property setters (needs, skills)
     - household.funds modification (money)
     - relationship_tracker methods (relationship scores)
     - career_tracker methods (promotions/demotions)
  -> Game state change propagates to UI automatically
```

### 2.4 Key Design Patterns

1. **Dual-surface mod**: Package modifies the UI presentation layer (Scaleform), script handles logic. Neither works alone.
2. **Command mapping table**: Each UI element maps to a specific game state setter. The mod is essentially a visual cheat console.
3. **Range-clamped values**: All numeric inputs are validated against game-legal ranges (-100 to 100 for needs/relationships, 0-10 for skills, etc.).
4. **Zero overhead**: No polling, no tick processing. Only fires on user click events. CPU cost is effectively zero during normal gameplay.
5. **Defensive updates**: Weerbesu maintains the mod actively (v1.53 as of March 2026) because every EA patch can shift UI element IDs and break the Scaleform hooks.

### 2.5 Patterns Worth Replicating

- **Click-to-modify paradigm**: Map existing UI elements to direct state modifications. Users expect instant feedback.
- **Dual-file architecture**: Separate UI presentation mods (.package) from logic (.ts4script) for independent updates.
- **Value validation layer**: Always clamp inputs to game-legal ranges to prevent corruption.
- **Minimal footprint**: Event-driven, not poll-driven. No per-tick cost.

### 2.6 QoL Layer Integration Notes

For a unified QoL layer, this mod demonstrates that the **UI-to-state bridge** is the most user-valued hook point. Players want to modify game state through the UI they already understand, not through console commands. The Stark Pack QoL layer should:
- Provide a unified click-handler registration system
- Abstract the Scaleform ExternalInterface bridge so other modules can register their own click actions
- Maintain a central command mapping registry (UI_element_id -> handler_function)

---

## 3. T.O.O.L. (TwistedMexi)

**Downloads:** 1.3M+
**Mod Type:** Script + Package
**Current Version:** v3.2
**Full Name:** Takes Objects Off Lot

### 3.1 Architecture Overview

TOOL is an **object transform manipulation mod** that provides builder-grade control over position, rotation, elevation, and scale of any placeable object. It operates primarily through the **pie menu interaction system** in Live Mode, with Build Mode support via Better BuildBuy integration.

### 3.2 Game Systems Hooked

| System | Hook Method | Purpose |
|--------|------------|---------|
| **Pie Menu (Shift-Click)** | SuperInteraction injection into object affordances | Adds TOOL submenu to all objects |
| **Object Transform** | Direct manipulation of object Location/Transform | Position, elevation changes |
| **Object Scale** | Scale factor modification on client objects | Resize objects (0.01x to 25x) |
| **Object Rotation** | Quaternion/Euler rotation on all 3 axes | Full 360-degree rotation |
| **Input System** | Custom input handlers for point-and-click mode | Click-to-place targeting |
| **Build/Buy Mode Bridge** | Integration with Better BuildBuy mod | Enables TOOL in Build Mode |

### 3.3 Technical Implementation Pattern

```
Shift-Click on Object
  -> Game triggers shift-click affordance check
  -> TOOL's injected SuperInteraction appears in pie menu
  -> User selects action (Move / Elevate / Rotate / Scale)
  -> Dialog box opens for numeric input
  -> TOOL applies transform to object:

  Move:
    object.location = Location(
        Transform(Vector3(x + dx, y, z + dz), orientation),
        routing_surface
    )

  Elevate:
    object.location.transform.translation.y += delta_y
    # Range: -25 to +25 from current position

  Rotate:
    # Applies Euler angles on X, Y, Z axes
    # Range: -360 to 360 degrees per axis
    object.location.transform.orientation = Quaternion(...)

  Scale:
    object.scale = factor  # 0.01 to 25.0 (1.0 = default)
```

### 3.4 Coordinate System Details

- **World Axis**: Default movement uses world X/Z axes (forward/back, left/right)
- **Lot Alignment**: v3.2 added lot-relative axis alignment -- transforms relative to lot rotation instead of world axis
- **Elevation (Y axis)**: Separate from X/Z movement, controlled independently
- **Grid Units**: 1 unit = 1 build-mode grid square; decimals supported for sub-grid precision

### 3.5 Interaction Modes

| Mode | Trigger | Description |
|------|---------|-------------|
| **Numeric Input** | TOOL > Move/Elevate/Rotate/Scale | Enter exact values via dialog |
| **Point & Click** | TOOL > Toggle Active Object, then shift-click destination | Click-to-place object at cursor position |
| **Lot Alignment Toggle** | Option in Rotate/Move dialogs | Switch between world-axis and lot-relative transforms |
| **Rotate Around Center** | Toggle in Rotate dialog | Rotate around object center vs. origin |

### 3.6 Key Design Patterns

1. **Interaction injection via affordance system**: TOOL adds itself to `_super_affordances` of all objects, making it universally accessible.
2. **Numeric precision with dialog input**: Rather than mouse-drag (imprecise), uses typed numeric values for exact placement.
3. **Coordinate system abstraction**: World-axis vs. lot-relative alignment shows importance of abstracting coordinate reference frames.
4. **Live Mode primary, Build Mode secondary**: Operates in Live Mode natively (where object transforms are more accessible to Python), bridges to Build Mode via companion mod.
5. **Incremental transform**: All operations are additive (move BY delta, not move TO absolute position), preserving context.
6. **Active object pattern**: Toggle-based selection model where one object is "active" and subsequent clicks affect it.

### 3.7 Patterns Worth Replicating

- **Universal affordance injection**: Register interactions on ALL objects of a type via `_super_affordances` tuple extension.
- **Numeric dialog abstraction**: Build a reusable `NumericInputDialog` component for any mod needing precise numeric input.
- **Coordinate frame abstraction**: Any spatial manipulation needs world-relative vs. lot-relative toggle.
- **Active selection state**: A global "currently selected object" pattern for multi-step operations.

### 3.8 QoL Layer Integration Notes

For the Stark Pack QoL layer, TOOL demonstrates the power of the **affordance injection pattern** -- adding interactions to every object without overriding individual tuning files. The QoL layer should:
- Provide a universal interaction registry that injects into all objects, sims, or terrain
- Abstract the pie menu system so multiple QoL modules can register submenus cleanly
- Include a shared `TransformManager` utility for any module needing object manipulation
- Support both numeric-input and point-and-click modes as first-class interaction paradigms

---

## 4. Simulation Lag Fix (SrslySims)

**Downloads:** 387K+
**Mod Type:** Package (tuning override) -- NOT a script mod
**Current Version:** Definitive Edition (March 2026)
**Companion:** TurboDriver's Simulation Unclogger (complementary, not conflicting)

### 4.1 Architecture Overview

The Simulation Lag Fix is fundamentally different from the other three mods analyzed here. It is a **tuning override mod** that modifies the game's time speed parameters to prevent autonomy-induced simulation desynchronization. It contains NO Python scripts -- it works entirely through XML tuning overrides packaged in a `.package` file.

### 4.2 The Simulation Lag Problem (Technical Root Cause)

The Sims 4 simulation loop operates on a **tick-based Timeline Heap**:

```
Simulation Tick (target: <50ms)
  -> Process Active Tasks (autonomy requests, interactions, routing)
  -> Process Alarm Elements (scheduled future tasks)
  -> Garbage collect (when GC elements > 50% of heap)
  -> Advance game clock by Time Scale increment
```

**The lag cycle:**
1. Sims complete an action and enter **idle state**
2. Idle Sims generate **Autonomy Requests** -- evaluating every possible interaction with every available object
3. Processing time for each Autonomy Request scales with: `O(active_sims * active_objects * available_interactions)`
4. When processing takes longer than one tick, the simulation falls behind real time
5. The game enters **Low-Performance Mode** when desync exceeds 10,000ms
6. Visible symptoms: Sims standing idle, head bobbing, clock rewinding, Speed 3 running at Speed 1

### 4.3 Game Systems Modified

| Tuning Parameter | Default | Modified | Effect |
|-----------------|---------|----------|--------|
| **Time Scale** (game clock speed) | 25ms per tick | Adjusted dynamically | Prevents clock from racing ahead of simulation |
| **Multitasking break intervals** | Default | Extended | Reduces how often Sims interrupt current tasks to re-evaluate autonomy |
| **Autonomy request frequency** | Per-idle-tick | Throttled | Fewer autonomy evaluations per unit of game time |

### 4.4 Technical Implementation

```
Game Tick Processing:
  [VANILLA]
  Time Scale = 25ms (fixed)
  Sims evaluate autonomy every idle tick
  Clock advances regardless of simulation backlog
  -> Result: Clock outruns simulation, desync accumulates

  [WITH SIM LAG FIX]
  Time Scale = dynamically adjusted based on tick load
  Multitasking break frequency reduced
  Autonomy re-evaluation intervals extended
  -> Result: Clock stays synchronized with actual simulation progress
```

### 4.5 Compatibility Architecture

- **Compatible WITH** TurboDriver's Simulation Unclogger (different approach: Unclogger kills stuck actions, Lag Fix prevents desync)
- **INCOMPATIBLE WITH** MCCC game time speed override (both modify the same Time Scale tuning -- if both active, values fight)
- **Pure override mod**: No script injection means no Python-level conflicts, but direct tuning file conflicts with any mod overriding the same XML resources

### 4.6 Key Design Patterns

1. **Tuning override vs. script injection**: This mod proves that some problems are better solved at the tuning layer, not the script layer. No Python needed.
2. **Dynamic parameter adjustment**: The Definitive Edition adjusts time speed based on simulation load rather than using a fixed override.
3. **Complementary architecture**: Designed to work alongside Simulation Unclogger -- each addresses different failure modes (prevention vs. recovery).
4. **MCCC conflict awareness**: Explicitly documents which other mods' settings must remain at defaults, showing the importance of inter-mod coordination.

### 4.7 Patterns Worth Replicating

- **Tuning-first approach**: If a QoL improvement can be achieved via tuning override rather than script injection, prefer tuning. Simpler, more compatible, less breakable.
- **Dynamic adjustment**: Rather than static overrides, monitor simulation performance and adjust parameters dynamically.
- **Complementary mod design**: Design each module to address one failure mode, and document how it coexists with other modules addressing related failure modes.
- **Conflict documentation**: For any tuning override, document exactly which tuning resources are modified and which other mods will conflict.

### 4.8 QoL Layer Integration Notes

For the Stark Pack QoL layer, the Simulation Lag Fix teaches us about the **tuning layer** as a modding surface. The QoL layer should:
- Include a `TuningOverrideManager` that documents all tuning modifications and detects conflicts
- Provide both tuning-level (XML override) and script-level (Python injection) tools
- Include simulation performance monitoring (tick time, autonomy queue depth) as a diagnostic tool
- Ship with sensible autonomy timing defaults that can be toggled by the user

---

## 5. First Impressions (Lumpinou)

**Downloads:** 200K+ estimated
**Mod Type:** Script (.ts4script) + Package
**Dependencies:** Lumpinou's Toolbox (shared script library), Mood Pack Mod
**Current Status:** Actively maintained

### 5.1 Architecture Overview

First Impressions is a **relationship system extension mod** that adds a trait-compatibility evaluation pipeline to Sim introductions. It intercepts the introduction interaction, evaluates trait compatibility between two Sims, and generates sentiment-based first impressions that influence future relationship development.

The mod demonstrates a mature **library-dependent architecture** -- it depends on Lumpinou's Toolbox (a shared `.ts4script` library used across multiple Lumpinou mods) and the Mood Pack Mod (custom moodlet infrastructure).

### 5.2 Game Systems Hooked

| System | Hook Point | Purpose |
|--------|-----------|---------|
| **Introduction Interactions** | Intercepts "Nice to meet you" and similar introduction affordances | Triggers evaluation pipeline on first meeting |
| **Trait System** | Reads CAS personality traits from both Sims | Input to compatibility algorithm |
| **Sentiment System** | Creates/removes sentiments on relationship tracker | Output of evaluation (Crush, Anti-Crush, Appreciation, Dislike, Interesting) |
| **Moodlet/Buff System** | Applies proximity and interaction buffs | Emotional feedback reinforcing impressions |
| **Autonomy Modifiers** | Modifies autonomous interaction weights | 4x more likely to autonomously interact with crushes |
| **Relationship Bit System** | Monitors relationship bit changes | Sentiment decay/replacement logic |

### 5.3 Evaluation Pipeline

```
Sim A uses Introduction Interaction on Sim B
  -> First Impressions intercepts (post-interaction hook)
  -> TRAIT EVALUATION:
     1. Read Sim B's CAS personality traits
     2. Select one "dominant characteristic" (probabilistic selection)
     3. Read Sim A's traits
     4. Identify if Sim A has a "modifier trait" that changes the outcome
     5. Evaluate compatibility: (dominant_trait, modifier_trait) -> impression_type
  -> SENTIMENT APPLICATION:
     6. Determine impression type: Crush | Anti-Crush | Interesting | Appreciation | Dislike
     7. Check existing sentiments (Major: max 1, Minor: max 4)
     8. Apply sentiment to relationship tracker
     9. Apply associated moodlet/buff
  -> AUTONOMY MODIFICATION:
     10. If Crush: +400% autonomous interaction weight toward target
     11. If Anti-Crush: reduced autonomous interaction weight
  -> DECAY RULES:
     12. Opposite-polarity sentiment added -> removes first impression
     13. Same-polarity sentiment added (optional DiminishAtSimilarSentimentAdd module) -> removes impression (deeper knowledge replaces surface judgment)
```

### 5.4 Trait Compatibility Matrix (Reconstructed)

The mod evaluates traits through a compatibility lookup. Key patterns:

- **Complementary traits**: Romantic + Outgoing -> higher Crush probability
- **Conflicting traits**: Neat + Slob -> Anti-Crush / Dislike probability
- **Neutral baseline**: If no readable traits or only unrecognized traits -> random selection from {Crush, Anti-Crush, Interesting}
- **Excluded traits**: Foodie, Glutton, Dog Lover, Cat Lover are not evaluated (likely due to low personality signal)
- **Custom trait support**: Not automatic, but Lumpinou offers integration for third-party trait mod authors

### 5.5 Shared Library Architecture (Lumpinou's Toolbox)

```
Lumpinou's Toolbox (.ts4script)
  |-- Shared utilities used by First Impressions, RPO, and other Lumpinou mods
  |-- Single script file across multiple mods (DRY principle)
  |-- Likely contains:
  |   |-- Trait reading utilities
  |   |-- Sentiment creation/management helpers
  |   |-- Buff/moodlet application wrappers
  |   |-- Relationship tracker access patterns
  |   |-- Event interception decorators
  |-- Required: game crashes (UI) without Toolbox installed
```

### 5.6 Key Design Patterns

1. **Probabilistic evaluation, not deterministic**: The "dominant characteristic" is selected probabilistically, creating variety in repeat meetings.
2. **Sentiment layering**: Uses the game's native sentiment system (Snowy Escape+) rather than inventing a custom data store. Piggybacks on existing infrastructure.
3. **Tiered sentiment capacity**: Respects game rules (1 major, 4 minor) rather than overriding them.
4. **Decay through replacement**: Impressions naturally fade as deeper sentiments develop -- elegant use of the game's own sentiment conflict resolution.
5. **Autonomy weight modification**: Rather than forcing actions, adjusts probability weights. Sims "tend toward" crushes without being forced.
6. **Shared library pattern**: Lumpinou's Toolbox is the closest thing to a utility library in the Sims 4 mod ecosystem. Multiple mods share one dependency.
7. **Dependency chain management**: Toolbox -> Mood Pack -> First Impressions. Clear dependency documentation prevents install failures.

### 5.7 Patterns Worth Replicating

- **Piggyback on native systems**: Use sentiments, buffs, relationship bits -- don't create parallel data stores.
- **Probabilistic personality modeling**: Trait evaluation with weighted randomness creates emergent behavior.
- **Shared utility library**: A single `.ts4script` dependency for common operations across multiple modules.
- **Autonomy weight tuning, not action forcing**: Modify probabilities, let the simulation decide. Feels organic, not scripted.
- **Graceful degradation**: Unknown/custom traits fall back to random impressions rather than failing.

### 5.8 QoL Layer Integration Notes

For the Stark Pack QoL layer, First Impressions demonstrates the **relationship system extension pattern**. The QoL layer should:
- Provide trait evaluation utilities as a shared service
- Abstract sentiment creation/management into a `SentimentManager` utility
- Include an autonomy weight modifier system that multiple modules can contribute to (additive, not conflicting)
- Ship a trait compatibility framework that mods can register custom trait pairings into
- Support dependency chaining with clear initialization order

---

## 6. Cross-Mod Pattern Analysis

### 6.1 Architecture Taxonomy

| Mod | Primary Surface | Injection Method | Tick Cost | File Structure |
|-----|----------------|-----------------|-----------|---------------|
| UI Cheats Extension | UI Layer (Scaleform) | Flash ExternalInterface + Python handlers | Zero (event-driven) | .package + .ts4script |
| T.O.O.L. | Interaction System (Affordances) | SuperInteraction injection via affordance_manager | Zero (on-demand) | .package + .ts4script |
| Simulation Lag Fix | Tuning Layer (XML) | Tuning override (no Python) | Zero (passive) | .package only |
| First Impressions | Relationship System (Sentiments) | Interaction hook + sentiment injection | Minimal (per-introduction only) | .ts4script + dependency chain |

### 6.2 Common Patterns Across All Four

1. **Zero idle cost**: None of these mods run per-tick logic during normal gameplay. They fire on events (clicks, interactions, introductions) or modify static parameters. This is a hard requirement for QoL mods.

2. **Native system piggybacking**: All four mods extend existing game systems rather than creating parallel infrastructure. UI Cheats uses the existing UI panels. TOOL uses the existing pie menu. Lag Fix uses existing tuning parameters. First Impressions uses the existing sentiment system.

3. **No external executables**: Pure in-process modification via Python bytecode injection or XML tuning override. No DLL injection, no memory hacking, no external tools at runtime.

4. **One subfolder depth**: All respect the Sims 4 mod loading constraint -- `.ts4script` files cannot be nested more than one folder deep in `Mods/`.

5. **Version fragility**: All four mods break on EA patches that change tuning IDs, UI element IDs, or Python API surfaces. Active maintenance is a survival requirement.

### 6.3 Architectural Layers Used

```
Layer 4: UI (Scaleform GFx)        <- UI Cheats Extension
Layer 3: Interactions (Affordances)  <- T.O.O.L., First Impressions
Layer 2: Game State (Python Objects) <- UI Cheats (setters), TOOL (transforms), First Impressions (sentiments)
Layer 1: Tuning (XML)               <- Simulation Lag Fix
Layer 0: Engine (C++)               <- Not accessible to any mod
```

### 6.4 Conflict Risk Matrix

| | UI Cheats | TOOL | Lag Fix | First Impressions |
|--|-----------|------|---------|-------------------|
| **UI Cheats** | -- | No conflict | No conflict | No conflict |
| **TOOL** | No conflict | -- | No conflict | No conflict |
| **Lag Fix** | No conflict | No conflict | -- (conflicts with MCCC time speed) | No conflict |
| **First Impressions** | No conflict | No conflict | No conflict | -- (needs Toolbox + Mood Pack) |

All four mods are mutually compatible because they operate on different game systems. This validates the "one concern per module" architectural principle.

---

## 7. Unified QoL Layer Design

### 7.1 Proposed Architecture

Based on the patterns extracted from all four mods, the Stark Pack QoL layer should be structured as:

```
stark_pack/
  qol/
    __init__.py
    core/
      injection_registry.py      # Central registry for all injection hooks
      tuning_override_manager.py  # Manages XML tuning overrides, detects conflicts
      interaction_registry.py     # Universal affordance injection for pie menus
      ui_bridge.py                # Scaleform ExternalInterface abstraction
      transform_manager.py        # Object position/rotation/scale utilities
      sentiment_manager.py        # Relationship sentiment creation/management
      autonomy_tuner.py           # Autonomy weight modification system
      trait_evaluator.py          # Trait compatibility framework
      numeric_input.py            # Reusable numeric input dialog component
    modules/
      quick_edit/                 # UI Cheats pattern: click-to-modify game state
        __init__.py
        click_handlers.py         # Per-panel click handler registrations
        value_validators.py       # Range-clamped input validation
      builder_tools/              # TOOL pattern: object transform manipulation
        __init__.py
        move.py
        elevate.py
        rotate.py
        scale.py
        selection.py              # Active object selection state
      performance/                # Sim Lag Fix pattern: simulation optimization
        __init__.py
        tuning_overrides/         # XML overrides for time scale, autonomy intervals
        diagnostics.py            # Tick time monitoring, autonomy queue depth
      social/                     # First Impressions pattern: relationship extensions
        __init__.py
        first_meeting.py          # Introduction interception + trait evaluation
        trait_compat.py           # Trait compatibility matrix
        impression_types.py       # Sentiment/buff definitions
    lib/
      stark_toolbox.py            # Shared utility library (Lumpinou's Toolbox pattern)
```

### 7.2 Core Design Principles (Extracted from Analysis)

| Principle | Source Mod | Implementation |
|-----------|-----------|---------------|
| **Zero idle cost** | All four | Event-driven only. No per-tick polling. |
| **Native system piggybacking** | All four | Use sentiments, affordances, tuning. No parallel data stores. |
| **Dual-surface mods** | UI Cheats, TOOL | Separate .package (UI) from .ts4script (logic) |
| **Tuning-first when possible** | Lag Fix | If it can be done via XML override, do it there |
| **Shared library dependency** | First Impressions | `stark_toolbox.py` provides common utilities |
| **Universal interaction injection** | TOOL | Single registration point for all pie menu additions |
| **Value validation** | UI Cheats | All user inputs clamped to game-legal ranges |
| **Probabilistic, not deterministic** | First Impressions | Personality evaluation uses weighted randomness |
| **Complementary modules** | Lag Fix + Unclogger | Each module addresses one concern, documents coexistence |
| **Graceful degradation** | First Impressions | Unknown inputs get sensible defaults, not crashes |

### 7.3 Integration Points for Stark Pack

The QoL layer serves as the **infrastructure foundation** for the larger Stark Pack. Other pack modules (gameplay, narrative, world) can:

1. **Register click handlers** via `ui_bridge.py` for custom UI interactions
2. **Add pie menu interactions** via `interaction_registry.py` for custom object/sim interactions
3. **Modify autonomy weights** via `autonomy_tuner.py` for behavior tuning
4. **Create relationship dynamics** via `sentiment_manager.py` + `trait_evaluator.py`
5. **Override tuning safely** via `tuning_override_manager.py` with conflict detection
6. **Manipulate objects** via `transform_manager.py` for spatial gameplay features

### 7.4 Anti-Patterns to Avoid

| Anti-Pattern | Why | Source Evidence |
|-------------|-----|-----------------|
| Per-tick polling loops | Destroys performance at scale | Lag Fix analysis: each tick must complete in <50ms |
| Custom data stores | Fragile, not saved properly, conflicts with game save system | First Impressions uses native sentiments instead |
| Direct tuning file replacement | Breaks mod compatibility | All four use injection/override, not replacement |
| Mouse-drag for precision | Imprecise, frustrating | TOOL uses numeric input for exact values |
| Hard-coded trait lists | Breaks with new packs | First Impressions falls back gracefully for unknown traits |
| Monolithic script file | Hard to maintain, hard to update per-patch | All four mods are modular within their scope |

### 7.5 Next Steps

1. **Prototype `injection_registry.py`** using CommonInjectionUtils patterns from S4CL
2. **Prototype `interaction_registry.py`** using TOOL's universal affordance injection
3. **Build `stark_toolbox.py`** with trait reading, sentiment management, and transform utilities
4. **Create tuning override package** for performance defaults (Lag Fix pattern)
5. **Test mod loading** with all four analyzed mods installed simultaneously to verify no conflicts

---

## Sources

- [Sims 4 Modding Wiki - Injection](https://sims-4-modding.fandom.com/wiki/Injection)
- [Sims 4 Modding Wiki - Python Scripting](https://sims-4-modding.fandom.com/wiki/Python_Scripting)
- [Sims 4 Tuning Deep Dive (Dominic M)](https://leroidetout.medium.com/sims-4-tuning-101-a-deep-dive-into-how-tuning-is-generated-from-python-part-4-df60bbd7c67f)
- [Modern Python Modding Part 6 - Adding Interactions (June Hanabi)](https://medium.com/@junebug12851/the-sims-4-modern-python-modding-part-6-adding-interactions-a2cedcdb81e2)
- [Modern Python Modding Part 2 - Hello World (June Hanabi)](https://medium.com/analytics-vidhya/the-sims-4-modern-python-modding-part-2-hello-world-77c5bfd3ce4e)
- [Sims4CommunityLibrary - CommonInjectionUtils](https://github.com/ColonolNutty/Sims4CommunityLibrary/blob/master/Scripts/sims4communitylib/utils/common_injection_utils.py)
- [Sims4CommunityLibrary - GitHub](https://github.com/ColonolNutty/Sims4CommunityLibrary)
- [TurboDriver - Sims 4 Simulation Technical Analysis](https://turbodriver.io/simulation)
- [Simulation Lag Fix - CurseForge](https://www.curseforge.com/sims4/mods/simulation-lag-fix)
- [First Impressions Mod - Lumpinou](https://lumpinoumods.com/2020/12/08/first-impressions-mod/)
- [Lumpinou's Toolbox Library](https://www.patreon.com/posts/mod-lumpinous-4-86658397)
- [Custom Sentiments Analysis - SimsCommunity](https://simscommunity.info/2020/11/28/custom-sentiments-proven-as-possible-for-the-sims-4/)
- [UI Cheats Extension - SimsCommunity](https://simscommunity.info/2023/09/05/the-sims-4-ui-cheats-extension/)
- [UI Cheats Extension v1.53 - Weerbesu Patreon](https://www.patreon.com/posts/ui-cheats-v1-16-26240068)
- [T.O.O.L. - CurseForge](https://www.curseforge.com/sims4/mods/t-o-o-l)
- [T.O.O.L. Public Release - TwistedMexi Patreon](https://www.patreon.com/posts/t-o-o-l-public-28887948)
- [XML Injector - Scumbumbo](https://scumbumbomods.com/xml-injector)
- [Sims 4 File Types Reference](https://thesims4moddersreference.org/reference/file-types/)
