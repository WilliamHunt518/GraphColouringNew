# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A **web-based human-subjects study platform** for research on trust in hierarchical autonomous AI systems. Operators manage a reserve of heterogeneous drone assets and allocate them to incoming search-and-rescue missions. Two AI assistants operate at different decision tiers:

- **Strategic Assistant** — fires when the operator initiates allocation of a queued mission. Presents two pre-computed strategy cards (Aggressive / Conservative) showing the **bundle of drone counts** to commit to that mission, projected ETA, speed score, and reserve score. The operator picks one, or dismisses and allocates manually.
- **Tactical Assistant** — fires immediately after strategic allocation is accepted. Presents a **within-mission drone→task assignment plan**: which specific drone IDs are assigned to which tasks, in which execution order. Shown in the tactical planner on the map window. The operator confirms the plan or drag-drops to modify individual assignments.

**Workflow note (v2.1):** on strategic allocation the committed team **sets off toward the mission zone immediately** and loiters at the zone edge until the tactical plan is confirmed (drones are then assigned to tasks from their current position). So the tactical step can be done at leisure while the drones are already en route; if they arrive first they wait for instructions. Committed drones leave the reserve the moment they are allocated (`launchToLoiter` in `gameReducer.ts`).

These are genuinely different decision levels:
- **Strategic** = cross-mission resource commitment (how many of each drone type to send)
- **Tactical** = within-mission execution planning (which specific drones do which tasks)

**IMPORTANT — do not reintroduce old concepts:**
There is NO "reserve posture widget", NO "preserve/maintain/spend down" recommendation, and NO "Meta-Co-Pilot". Those ideas were considered and removed. The tactical tier is purely the within-mission drone→task assignment planner.

Study uses a **2×2 between-subjects design** manipulating the accuracy of each assistant independently (conditions HH / LH / HL / LL).

## Tech Stack

- **React 18 + Vite 5 + TypeScript** — SPA, no backend
- **Tailwind CSS v3** — layout and styling
- **SVG** — strategic map (asset animation, mission zones, routes)
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

Three 8-minute (480 s) sessions. Asset pool: 11 Blue, 11 Red, 11 Green (33 total), **uniform across all study scenarios** — only the tactical/strategic weighting (mission size via `CATEGORY_WEIGHTS` + arrival rate via `LAMBDA`) differs between presets. See `FLEET` in `missionGen.ts`.

**Scenario tuning versions and participant associations are tracked in
[`docs/SCENARIOS.md`](docs/SCENARIOS.md)** — read/update it whenever the speeds, fleet, failure
rate, arrival rates, or mission-size mix change, so collected data is never pooled across
incompatible parameter sets.

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
    MapDisplay.tsx       # SVG strategic map + tactical planner
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
| `tactical_confirmed` | Operator confirms drone→task plan (tactical planner); `modifiedFromAgentPlan` flag + `agentPlan`/`finalPlan` triples record whether/how they changed the suggestion; `suggestUsedCount` records whether the agent plan was ever consulted (planner starts empty) |
| `tactical_suggest_used` | Operator clicks "Suggest" in the tactical planner to pull in the agent's plan (consultation signal, distinct from following) |
| `strategic_card_previewed` | Operator highlights an Aggressive/Conservative card in the strategic modal before applying (deliberation/dwell signal) |
| `manual_allocation_edited` | Operator adjusts a manual drone count in the strategic modal (manual-build effort/path signal) |
| `tactical_assignment_changed` | Each drone→task drag while building/editing a tactical (or recovery) plan — assign/chain/remove/unassign; full path-construction signal |
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

Poisson inter-arrivals; mean `LAMBDA` per complexity (v2.1): balanced 62s, strategic 37s,
tactical 75s, full 48s (see `missionGen.ts` / `docs/SCENARIOS.md`).
Zone: circle r=80, ≥150 units from hub (500,400), ≥200 units from other active zones.
Tasks execute greedily (T5 first → most constrained).

### Asset Speeds (units/second)

UI naming: operators see drone types by function, not colour — Blue is shown as "Fast", Red as "Lifter",
Green as "Camera" (still coloured blue/red/green text). Internal `AssetType` values, event-log fields,
and code stay `'Blue' | 'Red' | 'Green'` — only the display layer changed (see `ASSET_TYPE_LABEL` and
`droneLabel()` in `missionGen.ts`). Individual drone IDs (e.g. `B07`) display as `Fast-7` / `Lifter-7` /
`Camera-7`; composition shorthand uses `F`/`L`/`C` (e.g. `2F + 1L`) instead of `B`/`R`/`G`.

Speeds are **v2** (compressed spread 1.22×, faster overall — see `docs/SCENARIOS.md`). Raw speed
numbers are no longer shown to participants (the tutorial says only fastest/standard/slowest).

| Type  | Speed | Notes |
|-------|-------|-------|
| Blue ("Fast")    | 11.0  | Fastest, recce-only |
| Red ("Lifter")   | 10.0  | Standard, supply + extract |
| Green ("Camera") | 9.0   | Slowest type — required by T3/T4/T5, same task-type count as Blue (T1/T2/T5) and Red (T3/T4/T5); the compressed spread means Green is no longer the demand bottleneck |

## Development Guidelines

### Adding task types or asset types
Edit `src/types/index.ts` first, then update `missionGen.ts` and `copilot.ts`.

### Changing accuracy
Edit `conditionToEpsilons()` in `src/utils/config.ts`.

### Modifying the Strategic Agent
`src/utils/copilot.ts` — `generateStrategies()`. Generates Aggressive/Conservative drone-count bundles for a specific mission. ε_S noise perturbs the *displayed* asset counts (not the true values used at deploy).

### Modifying the Tactical Agent
Tactical suggestions are currently generated inline in `src/store/gameReducer.ts` via `greedyAssign()` during `APPLY_STRATEGIC`. The `metacopilot.ts` file is a stub for when this logic is extracted into its own module. ε_T **is** wired to noise injection: in `APPLY_STRATEGIC`, with probability `epsilonTactical` one task is silently dropped from the suggested plan (`hasTacticalError`/`suppressedTaskId` on `PendingAllocation`) — the UI still shows it as allocated, but no drone is actually assigned, and the task fails via tactical lockout once every other task in the mission completes.

### Scheduling deadlocks (cross-drone chain cycles)
A chained tactical plan can deadlock: e.g. Fast is chained task1→task2 while Lifter is chained task2→task1, so each task waits on a drone that is itself waiting on the other task. The operator/agent is **not** prevented from building such a plan (no build-time validation blocks it). Instead the drones fly out, and a **live** detector in `gameReducer.ts` TICK (step 3c, `findSchedulingCycle` in `src/utils/scheduling.ts`) waits until the cycle's drones have physically arrived and are sitting idle (genuinely stuck) before acting. This is distinct from the ε_T `tactical_lockout` mechanism above.

`StudyConfig.fixLockouts` (default **false** = help-needed; StartScreen "Fix lockouts" checkbox, **unticked** by default, or `?fixLockouts=1` for auto-fix) chooses the response. (The default tactical mode is also **plan-all**, `?tacticalMode=greedy` to override.) Either way a `lockout_detected` event is logged (with `resolution`):
- **true (auto-fix)** — the agent repairs it silently with **zero failures**: `rerouteDeadlock` reorders the conflicting drones' visit order over the cyclic tasks onto one canonical order (most-constrained first), making the dependency graph acyclic, then reschedules the not-yet-started tasks and redirects the freed drones. `resolution: 'rerouted'`.
- **false (help needed, DEFAULT)** — surfaced to the operator like a drone failure (a lockout is the same class of event: "something's wrong, the operator must deal with it"). The stuck drones are freed (`currentTaskId` cleared) but **left parked at the task waypoint they deadlocked on** (not flown back to a loiter slot) so the operator can see which drones physically reached which task — the recovery planner shows a per-task **"Present: …"** line (both in the right panel and, in lockout recovery only, a **"now X/Y"** line under the planned composition on the strategic-map task badge), computed by matching drone positions to the nearest task waypoint (`computePresentByTask`), making the deadlock's real state legible. The deadlocked tasks revert to `pending` **but keep their `assignedAssetIds`** and the mission's **cyclic `droneSequences` are left intact**; the recovery planner **loads that current (deadlocked) plan including its cyclic chain order** (`buildInitialChainOrder` seeds `droneChainOrder` from the sequences) so the operator sees and edits exactly what deadlocked. Critically, the planner re-runs `tasksInCycles` on the live plan and **blocks Deploy/Reassign while any dependency cycle remains** (`hasUnresolvedDeadlock` = `cycleTasks.size > 0` → `canDeploy` false, red "Still deadlocked" banner + "Reassign (still deadlocked)"). This is what stops a lockout reading as "already fixed": the operator must actually break the cycle — drag drones into a consistent order, or click **Suggest** — before it will deploy. Because the flags are derived from the *live* plan, breaking the cycle clears them **immediately** (no need to physically move drones first).

Per-task cues on the strategic-map badge:
- The **red "!" badge** (and red circle, and suppressed green ✓) goes ONLY on tasks that are genuinely *mutually blocking* — i.e. on a dependency cycle per `tasksInCycles` (`isBlocking`). A task merely *starved* of drones stuck upstream (e.g. an S&S waiting on drones held by two deadlocked Supply Drops) is **not** flagged — it frees up once the real cycle breaks.
- A **"now" present line** under the plan shows what's physically at each pending task, each type in its **own drone colour** (F=blue, L=red, C=green) with a **"!" prefix on any understocked type** so the missing drones are obvious. The substitute ("OR …") line is hidden during lockout recovery. The right panel mirrors this ("Present now:" + red "!"/"blocking" pill on cycle tasks).

**Suggest builds on the existing allocation when it can:** if every pending task is already fully staffed (the usual deadlock shape — staffed but cyclically ordered), Suggest just *untangles the order in place* (clears the chain order → canonical → acyclic), preserving the operator's drone→task assignment rather than reassigning from scratch; it only falls back to a full re-plan (`computeRecoverySuggestion`) when the current allocation is incomplete. **Crucially, every other not-yet-finished, non-executing task that shares a freed cycle drone is ALSO reverted to pending and its drones parked** — a lockout's drones are usually chained across several tasks, so freeing them would otherwise orphan a still-"traveling" task (its drones no longer heading there, and Suggest unable to fill it because they looked busy). This was a real shipped bug (recovery Suggest left a shared task unstaffed → forced abandon). The operator builds a fix by hand or clicks **Suggest** (the recovery suggestion always chains/plan-all so the shared drones cover every task — `computeRecoverySuggestion` in `src/utils/tacticalSuggest.ts`). The mission is flagged `failureRecoveryPending` with `recoveryReason: 'lockout'` (red "⚠ Lockout — help needed" banner). The operator re-plans a workable allocation via the **same recovery planner** as a drone failure (`CONFIRM_FAILURE_RECOVERY`), or abandons. The recovery planner's **Suggest** button is available in both recovery flows (lockout and drone-failure) — the agent proposes a fix using the idle on-mission drones; using it sets `wasAgentSuggested` on the `failure_recovery` event. The planner builds each recovered task's drone→task sequence in canonical (most-constrained-first) order, so any plan it (or the operator) confirms is acyclic and breaks the cycle. Greedy replan is paused for the mission (`applyGreedyReplan` skips `recoveryReason === 'lockout'`) so the operator — not the agent — resolves it. `resolution: 'help_needed'`. The mission only fails if the operator abandons it or the session ends unresolved.

**Greedy vs plan-all:** in **greedy** `tacticalMode` the AGENT's baseline is committed one step at a time (collapsed in `APPLY_STRATEGIC`) and greedy replan fills tasks the operator left unassigned; but an operator-drawn path longer than one hop is **preserved** by `CONFIRM_TACTICAL` (not trimmed). So a deadlock can form in either mode whenever the operator explicitly chains drones into a cycle.

**Dispatch order matters:** a drone flies to the **first task in its own chain sequence** (`pickFirstAssignment`), not the earliest-start-time task. This is essential for deadlocks to be physically real: two drones chained into a cycle must set off to *different* tasks. (Earlier code used lowest start time, which for a cyclic plan's inconsistent start times sent both shared drones to the *same* task, silently dissolving the deadlock so it could spuriously complete.)

**The agent never deadlocks (by construction):** `greedyAssign` routes every drone from the hub in one global task order, so its plans are always acyclic — only the *operator* can build a lockout today. (An earlier, **abandoned** idea to make the Tactical Assistant deadlock *organically* via an ordering-blind planner is archived and **not** being pursued — see `docs/OLD-DRAFTS-DO-NOT-USE/FUTURE_NAIVE_TACTICAL_AGENT.md`, which should be ignored unless you are specifically revisiting that old proposal.)

**Signalling:** a lockout-abandoned mission sets `Mission.abandonedReason = 'lockout'` and the mission card shows a red "✕ failed · lockout"; an operator `ABANDON_MISSION` sets `'operator'` and shows a muted amber "abandoned". Without this, `abandoned` missions had no status label and read like a quiet completion.

## Critical Constraints

1. **All randomness seeded** — pass `SeededRNG` instances everywhere, never call `Math.random()` in game logic
2. **No backend** — all state in-memory; export is a client-side JSON download
3. **UI language** — use "Strategic Assistant" / "Tactical Assistant" (operator-facing UI only — internal identifiers, action types, and logged event fields like `isAgentSuggested`/`wasAgentSuggested`/`modifiedFromAgentPlan` keep "Agent" and are unaffected), never "Co-Pilot", "Meta-Co-Pilot", "AI", or "algorithm". **Never call the main map "operational map"** (anywhere — UI, comments, docs, code identifiers): it is the **strategic map**; the only map/planner terms are "strategic" and "tactical".
4. **Events logged immediately** — every operator action and agent recommendation must be logged with ms timestamp; see [`docs/EVENT_LOGGING.md`](docs/EVENT_LOGGING.md) for the full event schema, envelope fields, and rules for adding new events
5. **BroadcastChannel host/client** — primary window is host; map window subscribes only; never let client mutate state
