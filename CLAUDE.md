# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A **web-based human-subjects study platform** for research on trust in hierarchical autonomous AI systems. Operators manage a reserve of heterogeneous drone assets and allocate them to incoming search-and-rescue missions. Two AI assistants operate at different decision tiers:

- **Strategic Assistant** — fires when the operator initiates allocation of a queued mission. Presents two pre-computed strategy cards (Aggressive / Conservative) showing the **bundle of drone counts** to commit to that mission, projected ETA, speed score, and reserve score. The operator picks one, or dismisses and allocates manually.
- **Tactical Assistant** — fires immediately after strategic allocation is accepted. Presents a **within-mission drone→task assignment plan**: which specific drone IDs are assigned to which tasks, in which execution order. Shown in the tactical planner on the map window. The operator confirms the plan or drag-drops to modify individual assignments.

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

**Study builder (per-session complexity):** `StudyConfig.sessionComplexities?: Complexity[]` lets a single
participant run chain different presets session-to-session (e.g. Strategic Heavy → Tactical Heavy), each
still followed by the normal survey/between-session flow. `complexityForSession(config, sessionNumber)` in
`gameReducer.ts` resolves the complexity for a given session, falling back to the single `complexity` field
when `sessionComplexities` isn't set. StartScreen.tsx shows one complexity picker per session slot once
"Sessions" > 1.

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
                         # NOTE: there is no separate scoring.ts — computeScore/computeCompletionPoints/
                         # computePenaltyAccrued/computeGreenEfficiency/computeMeanMissionTime all live
                         # inline in gameReducer.ts
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

All events logged in-memory, append-only. At study end, "Download Data" button exports (also autosaved to localStorage after each session):
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

Every event carries a `BaseEvent` envelope: a study-wide monotonic `seq`, a
session-relative `timestamp` (ms), a real `wallClock` (ISO-8601), a deterministic
`sessionId`, plus `sessionNumber`/`elapsed`/`reserveState`. The first event of every
session is `session_start`, which dumps every parameter needed to reproduce that
session from the log alone (seed, complexity, fleet, task compositions/timings,
penalty rates, failure schedule, agent ε values, etc).

### Event Types Logged

**Full schema, file:line locations, RQ mapping, and known gaps/discrepancies are
documented in [`docs/EVENT_LOGGING.md`](docs/EVENT_LOGGING.md) — read that before
adding or modifying any event.** Quick summary of event types:

| Event | When fired |
|-------|-----------|
| `session_start` | First tick of a session — full parameter dump for reproducibility |
| `phase_change` | Any `GamePhase` transition (playing/survey/between/done) |
| `mission_arrived` | Mission spawns from blueprint |
| `mission_completed` | Mission's last task finishes (completed or failed) |
| `strategic_modal_opened` | Strategic Agent modal opens; logs full strategy cards shown to user, including true (never-displayed) asset counts |
| `strategic_dismissed` | Operator closes the Strategic Agent modal without picking a card |
| `strategic_choice` | Operator picks Aggressive/Conservative/Manual |
| `tactical_opened` | Tactical planner becomes available after a strategic choice; logs the agent's suggested plan |
| `tactical_confirmed` | Operator confirms drone→task plan (tactical planner); `modifiedFromAgentPlan` flag + `agentPlan`/`finalPlan` triples record whether/how they changed the suggestion |
| `drone_failure` | In-mission drone fails |
| `failure_recovery` | Recovery option chosen (covers agent-suggested, redistribute, and manual recovery flows) |
| `task_completed` / `task_failed` | Task state transition |
| `asset_recalled` | Operator manually recalls a drone |
| `task_reprioritised` | Operator reorders task queue |
| `mission_abandoned` | Operator abandons a mission with no feasible recovery |
| `trust_probe` / `trust_probe_dismissed` | Periodic trust/workload probe answered or dismissed |
| `session_ended` | Session summary metrics, including `reason` (timer/forced) and `tacticalFollowRate` |
| `survey_response` | NASA-TLX / trust / TAM survey page submitted |

### Mission Generation

Poisson inter-arrivals: Easy λ=120s, Medium λ=75s, Hard λ=45s.
Zone: circle r=80, ≥150 units from hub (500,400), ≥200 units from other active zones.
Tasks execute greedily (T5 first → most constrained).

### Asset Speeds (units/second)

UI naming: operators see drone types by function, not colour — Blue is shown as "Fast", Red as "Lifter",
Green as "Camera" (still coloured blue/red/green text). Internal `AssetType` values, event-log fields,
and code stay `'Blue' | 'Red' | 'Green'` — only the display layer changed (see `ASSET_TYPE_LABEL` and
`droneLabel()` in `missionGen.ts`). Individual drone IDs (e.g. `B07`) display as `Fast-7` / `Lifter-7` /
`Camera-7`; composition shorthand uses `F`/`L`/`C` (e.g. `2F + 1L`) instead of `B`/`R`/`G`.

| Type  | Speed | Notes |
|-------|-------|-------|
| Blue ("Fast")    | 9.0   | Fastest, recce-only |
| Red ("Lifter")   | 6.8   | Standard, supply + extract |
| Green ("Camera") | 5.4   | Slowest type — required by T3/T4/T5, same task-type count as Blue (T1/T2/T5) and Red (T3/T4/T5); not specially "most constrained," just slowest to arrive |

## Development Guidelines

### Adding task types or asset types
Edit `src/types/index.ts` first, then update `missionGen.ts` and `copilot.ts`.

### Changing accuracy
Edit `conditionToEpsilons()` in `src/utils/config.ts`.

### Modifying the Strategic Agent
`src/utils/copilot.ts` — `generateStrategies()`. Generates Aggressive/Conservative drone-count bundles for a specific mission. ε_S noise perturbs the *displayed* asset counts (not the true values used at deploy).

### Modifying the Tactical Agent
Tactical suggestions are currently generated inline in `src/store/gameReducer.ts` via `greedyAssign()` during `APPLY_STRATEGIC`. The `metacopilot.ts` file is a stub for when this logic is extracted into its own module. ε_T **is** wired to noise injection: in `APPLY_STRATEGIC`, with probability `epsilonTactical` one task is silently dropped from the suggested plan (`hasTacticalError`/`suppressedTaskId` on `PendingAllocation`) — the UI still shows it as allocated, but no drone is actually assigned, and the task fails via tactical lockout once every other task in the mission completes.

## Critical Constraints

1. **All randomness seeded** — pass `SeededRNG` instances everywhere, never call `Math.random()` in game logic
2. **No backend** — all state in-memory; export is a client-side JSON download
3. **UI language** — use "Strategic Assistant" / "Tactical Assistant" (operator-facing UI only — internal identifiers, action types, and logged event fields like `isAgentSuggested`/`wasAgentSuggested`/`modifiedFromAgentPlan` keep "Agent" and are unaffected), never "Co-Pilot", "Meta-Co-Pilot", "AI", or "algorithm"
4. **Events logged immediately** — every operator action and agent recommendation must be logged with ms timestamp; see [`docs/EVENT_LOGGING.md`](docs/EVENT_LOGGING.md) for the full event schema, envelope fields, and rules for adding new events
5. **BroadcastChannel host/client** — primary window is host; map window subscribes only; never let client mutate state
