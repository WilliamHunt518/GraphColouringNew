# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A **web-based human-subjects study platform** for research on trust in hierarchical autonomous AI systems. Operators manage a reserve of heterogeneous drone assets and allocate them to incoming search-and-rescue missions. Two AI assistants operate at different decision tiers:

- **Strategic Agent** — fires when the operator initiates allocation of a queued mission. Presents two pre-computed strategy cards (Aggressive / Conservative) showing the **bundle of drone counts** to commit to that mission, projected ETA, speed score, and reserve score. The operator picks one, or dismisses and allocates manually.
- **Tactical Agent** — fires immediately after strategic allocation is accepted. Presents a **within-mission drone→task assignment plan**: which specific drone IDs are assigned to which tasks, in which execution order. Shown in the tactical planner on the map window. The operator confirms the plan or drag-drops to modify individual assignments.

These are genuinely different decision levels:
- **Strategic** = cross-mission resource commitment (how many of each drone type to send)
- **Tactical** = within-mission execution planning (which specific drones do which tasks)

**IMPORTANT — do not reintroduce old concepts:**
There is NO "reserve posture widget", NO "preserve/maintain/spend down" recommendation, and NO "Meta-Co-Pilot". Those ideas were considered and removed. The tactical tier is purely the within-mission drone→task assignment planner.

Study uses a **2×2 between-subjects design** manipulating the accuracy of each assistant independently (conditions HH / LH / HL / LL).

## Tech Stack

- **React 18 + Vite 5 + TypeScript** — SPA, no backend
- **Tailwind CSS v3** — layout and styling
- **SVG** — operational map (asset animation, mission zones, routes)
- **BroadcastChannel API** — two-window state sync for dual-monitor setup
- All randomness seeded via Mulberry32 PRNG (`src/utils/prng.ts`) — same seed → same session

## Running the App

```bash
npm install       # once
npm run dev       # dev server at http://localhost:5173
```

**URL parameters** pre-fill the start screen (useful for researcher setup):
```
http://localhost:5173/?pid=P001&condition=HH&complexity=standard&seed=42
```

**Two-monitor setup:**
- Primary window: `http://localhost:5173/` (default view)
- Map window: `http://localhost:5173/?view=map` — receives state via BroadcastChannel

## Architecture

### Study Design

Three 8-minute (480 s) sessions. Asset pool: 11 Blue, 11 Red, 12 Green (34 total), **uniform across all study scenarios** — only the tactical/strategic weighting (mission size via `CATEGORY_WEIGHTS` + arrival rate via `LAMBDA`) differs between presets. See `FLEET` in `missionGen.ts`.

| Condition | ε_Strategic | ε_Tactical |
|-----------|------------|------------|
| HH        | 0.10       | 0.10       |
| LH        | 0.40       | 0.10       |
| HL        | 0.10       | 0.40       |
| LL        | 0.40       | 0.40       |

### Key Files

```
index.html               # Vite entry
src/
  main.tsx               # React root mount
  App.tsx                # Top-level: StartScreen → GameShell
  index.css              # Tailwind directives + base styles
  types/
    index.ts             # All TypeScript types (Asset, Task, Mission, GameState, events)
  utils/
    prng.ts              # SeededRNG class (Mulberry32)
    config.ts            # URL param parsing, condition → epsilon mapping
    missionGen.ts        # Seeded mission generator (Poisson arrivals, zone placement)
    copilot.ts           # Strategic Agent — Aggressive/Conservative strategy generator with ε_S noise
    metacopilot.ts       # Tactical Agent stub (not yet implemented as a separate module;
                         #   tactical suggestions currently computed inline in gameReducer via greedyAssign)
    scoring.ts           # Score, green efficiency, follow-rate calculation
  store/
    gameReducer.ts       # useReducer state machine
    actions.ts           # Action type union
  components/
    StartScreen.tsx      # Researcher setup: participantId, condition, complexity, seed
    GameShell.tsx        # Session wrapper, clock, broadcast sync, localStorage autosave
    PrimaryDisplay.tsx   # Reserve panel + mission queue + Strategic Agent modal
    MapDisplay.tsx       # SVG operational map + tactical planner
    SurveyModal.tsx      # NASA-TLX, trust, TAM surveys
    BetweenSession.tsx   # 30s inter-session screen
```

### Data Output

All events logged in-memory. At study end, "Download Data" button exports (also autosaved to localStorage after each session):
```json
{
  "participantId": "P001",
  "condition": "HH",
  "mode": "agent",
  "epsilonStrategic": 0.10,
  "epsilonTactical": 0.10,
  "sessions": [{ ...events }]
}
```

### Event Types Logged

| Event | When fired |
|-------|-----------|
| `mission_arrived` | Mission spawns from blueprint |
| `strategic_modal_opened` | Strategic Agent modal opens; logs full strategy cards shown to user |
| `strategic_choice` | Operator picks Aggressive/Conservative/Manual |
| `tactical_confirmed` | Operator confirms drone→task plan (tactical planner); `modifiedFromAgentPlan` flag records whether they changed the suggestions |
| `drone_failure` | In-mission drone fails |
| `failure_recovery` | Recovery option chosen |
| `task_completed` / `task_failed` | Task state transition |
| `asset_recalled` | Operator manually recalls a drone |
| `task_reprioritised` | Operator reorders task queue |
| `session_ended` | Session summary metrics |
| `survey_response` | Post-session survey submitted |

### Mission Generation

Poisson inter-arrivals: Easy λ=120s, Medium λ=75s, Hard λ=45s.
Zone: circle r=80, ≥150 units from hub (500,400), ≥200 units from other active zones.
Tasks execute greedily (T5 first → most constrained).

### Asset Speeds (units/second)

| Type  | Speed | Notes |
|-------|-------|-------|
| Blue  | 9.0   | Fast, recce-only |
| Red   | 6.8   | Standard, supply + extract |
| Green | 5.4   | Slow specialist, required for T3/T4/T5 |

## Development Guidelines

### Adding task types or asset types
Edit `src/types/index.ts` first, then update `missionGen.ts` and `copilot.ts`.

### Changing accuracy
Edit `conditionToEpsilons()` in `src/utils/config.ts`.

### Modifying the Strategic Agent
`src/utils/copilot.ts` — `generateStrategies()`. Generates Aggressive/Conservative drone-count bundles for a specific mission. ε_S noise perturbs the *displayed* asset counts (not the true values used at deploy).

### Modifying the Tactical Agent
Tactical suggestions are currently generated inline in `src/store/gameReducer.ts` via `greedyAssign()` during `APPLY_STRATEGIC`. The `metacopilot.ts` file is a stub for when this logic is extracted into its own module. ε_T is stored in config but not yet wired to noise injection.

## Critical Constraints

1. **All randomness seeded** — pass `SeededRNG` instances everywhere, never call `Math.random()` in game logic
2. **No backend** — all state in-memory; export is a client-side JSON download
3. **UI language** — use "Strategic Agent" / "Tactical Agent", never "Co-Pilot", "Meta-Co-Pilot", "AI", or "algorithm"
4. **Events logged immediately** — every operator action and agent recommendation must be logged with ms timestamp
5. **BroadcastChannel host/client** — primary window is host; map window subscribes only; never let client mutate state
