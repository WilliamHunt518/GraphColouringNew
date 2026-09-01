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

The platform supports a **2×2 between-subjects design** manipulating the accuracy of each assistant independently (conditions HH / LH / HL / LL) — but the **shipped study build runs a single condition at ε = 0** (both assistants perfect), so that machinery is dormant. **What the study build actually does, and every decision behind it, is [`docs/STUDY_BUILD.md`](docs/STUDY_BUILD.md)** (currently `study-v1.6` — the doc has one numbered section per build version, and the version matches the `appVersion` in every session's `session_start`). Read it before answering any "was X on when we collected that data?" question, and add a section + a new tag whenever one of those decisions changes.

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

**Note:** the primary window drives the simulation clock from `requestAnimationFrame`, so it must
stay **visible**. If it is minimised or hidden behind another window the browser suspends rAF and
the session pauses (the map window keeps its last broadcast state and looks frozen). On a single
screen, put the two windows side by side rather than tabbed.

`elapsed` is derived from the wall clock, so a suspended tick loop used to replay the whole gap in
a single frame when the window came back — drones teleported, tasks completed and penalty accrued
unseen. `MAX_TICK_GAP_MS` in `gameReducer.ts` now caps how much simulated time one TICK may
advance and pushes `sessionStartMs` forward by the remainder, turning a stall into a genuine pause.
The cap sits above every step size the headless harnesses use, so they are unaffected.

## Screen + mic recording

`scripts\record-screens.bat` records all monitors + cursor + mic to one MP4. Geometry and mic are
auto-detected; `-Mic "<substring>"` forces a device, `-Mic none` records video only. Press `q` to
stop cleanly.

**It is environment-dependent and was developed on a different machine than the study is run on
(desktop w/ HyperX mic + NVIDIA GPU vs laptop).** If it fails on the study machine, read
[`docs/RECORDING.md`](docs/RECORDING.md) — it has the three diagnostic commands, the ranked failure
modes with `file:line` references, and a ready-to-paste patch for the most likely one (no NVIDIA
GPU ⇒ the hard-coded NVENC encoder fails and needs a fallback). Do not diagnose the encoder with
`ffmpeg -encoders`; it lists compiled support, not usable hardware.

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

**Pre-study AI-attitude survey (`study-v1.3`+):** `DemographicsForm.tsx` runs before session 1 and
now includes, alongside the existing "About you"/comprehension sections, three Likert blocks on AI
disposition — AIAS-4 (validated, verbatim, 10-point), a bespoke verification-propensity scale
(7-point, 3 reverse-keyed items), and a bespoke delegation-boundary scale (7-point, 1 reverse-keyed
item). Responses are logged raw (not reverse-scored) under `demographics` keys prefixed
`aias_`/`verif_`/`deleg_`. Full item text, scoring notes, and provenance are in
[`docs/STUDY_BUILD.md`](docs/STUDY_BUILD.md) §10.

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
| `task_completed` / `task_failed` | Task state transition. `task_failed` carries `missionWasAllocated` — most `session_ended` failures are tasks of missions the operator never took on |
| `task_requeued` | A task moved to the residual mission when its parent was abandoned — **work transferred, not lost**; join `residualTaskId` to follow it |
| `asset_recalled` | Operator manually recalls a drone |
| `task_reprioritised` | Operator reorders task queue |
| `mission_abandoned` | Operator abandons a mission with no feasible recovery. The remainder is re-queued as a residual mission (`<id>-R`), which gets its own `mission_arrived` flagged `isResidual` — exclude residuals from arrival denominators, and never read an abandonment as lost reward (`rewardCarriedOver` vs `rewardLost`) |
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

### Drone failures and the recovery planner
A failure reverts the affected task to `pending` and flags the mission `failureRecoveryPending`; the
operator fixes it in the recovery planner (same UI as the tactical planner, `CONFIRM_FAILURE_RECOVERY`).
Four rules matter (`study-v1.5`–`v1.6`):

- **Recovery re-commits every UNSTARTED task**, not just the pending one — so chaining a drone off a
  still-`traveling` task onto the broken one (shift+drag, or the agent's Suggest) rebuilds the task it
  came from too instead of stalling it. Tasks already `executing` are never re-planned, and a drone the
  revision pulls off a task is parked on-mission.
- **Suggest** (`computeRecoverySuggestion` in `src/utils/tacticalSuggest.ts`) draws on every mission
  drone not executing a task, and re-plans only the pending tasks the operator's *live* plan leaves
  short. When it can propose nothing the planner says so rather than appearing dead.
- **Post-failure grace** (`FAILURE_GRACE_SECONDS`, default 30 s): a mission that opens a recovery takes
  no further failure rolls until that long **after** the operator resolves it, so a second drone can
  never die mid-repair. Set via `StudyConfig.failureGraceSeconds` / StartScreen "Failure grace" /
  `?failureGrace=`; `0` disables it. Read it through `failureGraceSeconds()` in `utils/config`, never
  inline. Only failures that open a recovery arm the window — a loitering-drone death or a graceful
  section exit leaves the hazard alone, or the realized failure rate would halve.
- **The planner's in-progress plan is PRUNED, never rebuilt** (`prunePlan` in
  `src/utils/planPrune.ts`, `study-v1.6`). Its task list is the mission's *unfinished* tasks, so a task
  completing mid-recovery used to change the reset key and wipe everything the operator had dragged.
  Now a vanished task loses its entry, a departed drone is stripped everywhere, and the rest — chains
  included — survives untouched. A clean slate comes from remounting instead: `TacticalPlannerView`
  is keyed on mission id + planner mode, so only a genuine mission/mode change rebuilds. Don't
  reintroduce a `taskOrder`-sensitive reset.

### Modifying the Tactical Agent
Tactical suggestions are currently generated inline in `src/store/gameReducer.ts` via `greedyAssign()` during `APPLY_STRATEGIC`. The `metacopilot.ts` file is a stub for when this logic is extracted into its own module. ε_T **is** wired to noise injection: in `APPLY_STRATEGIC`, with probability `epsilonTactical` one task is silently dropped from the suggested plan (`hasTacticalError`/`suppressedTaskId` on `PendingAllocation`) — the UI still shows it as allocated, but no drone is actually assigned, and the task fails via tactical lockout once every other task in the mission completes.

### Scheduling deadlocks (cross-drone chain cycles)
A chained tactical plan can deadlock: e.g. Fast is chained task1→task2 while Lifter is chained task2→task1, so each task waits on a drone that is itself waiting on the other task. The operator/agent is **not** prevented from building such a plan (no build-time validation blocks it). Instead the drones fly out, and a **live** detector in `gameReducer.ts` TICK (step 3c, `findSchedulingCycle` in `src/utils/scheduling.ts`) waits until the cycle's drones have physically arrived and are sitting idle (genuinely stuck) before acting. This is distinct from the ε_T `tactical_lockout` mechanism above.

`StudyConfig.fixLockouts` (default **true** = auto-fix; StartScreen "Fix lockouts" checkbox, **ticked** by default, or `?fixLockouts=0` for help-needed) chooses the response. (The default tactical mode is also **plan-all**, `?tacticalMode=greedy` to override.) Either way a `lockout_detected` event is logged (with `resolution`):
- **true (auto-fix, DEFAULT — what the study runs)** — the agent repairs it silently with **zero failures**: `rerouteDeadlock` reorders the conflicting drones' visit order over the cyclic tasks onto one canonical order (most-constrained first), making the dependency graph acyclic, then reschedules the not-yet-started tasks and redirects the freed drones. `resolution: 'rerouted'`. **Because this is the default, a participant can never reach a stuck deadlock — which is why the tutorial has no lockout lesson** (there was a `lockout-explain` step; it was removed rather than warn people about a state they cannot encounter). Everything below about the help-needed branch is still live code, still tested, but off the study path — restore the lesson if a study arm ever turns the flag off.
- **false (help needed, `?fixLockouts=0`)** — surfaced to the operator like a drone failure (a lockout is the same class of event: "something's wrong, the operator must deal with it"). The stuck drones are freed (`currentTaskId` cleared) but **left parked at the task waypoint they deadlocked on** (not flown back to a loiter slot) so the operator can see which drones physically reached which task — the recovery planner shows a per-task **"Present: …"** line (both in the right panel and, in lockout recovery only, a **"now X/Y"** line under the planned composition on the strategic-map task badge), computed by matching drone positions to the nearest task waypoint (`computePresentByTask`), making the deadlock's real state legible. The deadlocked tasks revert to `pending` **but keep their `assignedAssetIds`** and the mission's **cyclic `droneSequences` are left intact**; the recovery planner **loads that current (deadlocked) plan including its cyclic chain order** (`buildInitialChainOrder` seeds `droneChainOrder` from the sequences) so the operator sees and edits exactly what deadlocked. Critically, the planner re-runs `tasksInCycles` on the live plan and **blocks Deploy/Reassign while any dependency cycle remains** (`hasUnresolvedDeadlock` = `cycleTasks.size > 0` → `canDeploy` false, red "Still deadlocked" banner + "Reassign (still deadlocked)"). This is what stops a lockout reading as "already fixed": the operator must actually break the cycle — drag drones into a consistent order, or click **Suggest** — before it will deploy. Because the flags are derived from the *live* plan, breaking the cycle clears them **immediately** (no need to physically move drones first).

Per-task cues on the strategic-map badge:
- The **red "!" badge** (and red circle, and suppressed green ✓) goes ONLY on tasks that are genuinely *mutually blocking* — i.e. on a dependency cycle per `tasksInCycles` (`isBlocking`). A task merely *starved* of drones stuck upstream (e.g. an S&S waiting on drones held by two deadlocked Supply Drops) is **not** flagged — it frees up once the real cycle breaks.
- A **"now" present line** under the plan shows what's physically at each pending task, each type in its **own drone colour** (F=blue, L=red, C=green) with a **"!" prefix on any understocked type** so the missing drones are obvious. The substitute ("OR …") line is hidden during lockout recovery. The right panel mirrors this ("Present now:" + red "!"/"blocking" pill on cycle tasks).

**Suggest builds on the existing allocation when it can:** if every pending task is already fully staffed (the usual deadlock shape — staffed but cyclically ordered), Suggest just *untangles the order in place* (clears the chain order → canonical → acyclic), preserving the operator's drone→task assignment rather than reassigning from scratch; it only falls back to a full re-plan (`computeRecoverySuggestion`) when the current allocation is incomplete. **Crucially, every other not-yet-finished, non-executing task that shares a freed cycle drone is ALSO reverted to pending and its drones parked** — a lockout's drones are usually chained across several tasks, so freeing them would otherwise orphan a still-"traveling" task (its drones no longer heading there, and Suggest unable to fill it because they looked busy). This was a real shipped bug (recovery Suggest left a shared task unstaffed → forced abandon). The operator builds a fix by hand or clicks **Suggest** (the recovery suggestion always chains/plan-all so the shared drones cover every task — `computeRecoverySuggestion` in `src/utils/tacticalSuggest.ts`). The mission is flagged `failureRecoveryPending` with `recoveryReason: 'lockout'` (red "⚠ Lockout — help needed" banner). The operator re-plans a workable allocation via the **same recovery planner** as a drone failure (`CONFIRM_FAILURE_RECOVERY`), or abandons. The recovery planner's **Suggest** button is available in both recovery flows (lockout and drone-failure) — the agent proposes a fix using the idle on-mission drones; using it sets `wasAgentSuggested` on the `failure_recovery` event. The planner builds each recovered task's drone→task sequence in canonical (most-constrained-first) order, so any plan it (or the operator) confirms is acyclic and breaks the cycle. Greedy replan is paused for the mission (`applyGreedyReplan` skips `recoveryReason === 'lockout'`) so the operator — not the agent — resolves it. `resolution: 'help_needed'`. The mission only fails if the operator abandons it or the session ends unresolved.

**Greedy vs plan-all:** in **greedy** `tacticalMode` the AGENT's baseline is committed one step at a time (collapsed in `APPLY_STRATEGIC`) and greedy replan fills tasks the operator left unassigned; but an operator-drawn path longer than one hop is **preserved** by `CONFIRM_TACTICAL` (not trimmed). So a deadlock can form in either mode whenever the operator explicitly chains drones into a cycle.

**Dispatch order matters:** a drone flies to the **first task in its own chain sequence** (`pickFirstAssignment`), not the earliest-start-time task. This is essential for deadlocks to be physically real: two drones chained into a cycle must set off to *different* tasks. (Earlier code used lowest start time, which for a cyclic plan's inconsistent start times sent both shared drones to the *same* task, silently dissolving the deadlock so it could spuriously complete.)

**The agent never deadlocks (by construction):** `greedyAssign` routes every drone from the hub in one global task order, so its plans are always acyclic — only the *operator* can build a lockout today. (An earlier, **abandoned** idea to make the Tactical Assistant deadlock *organically* via an ordering-blind planner is archived and **not** being pursued — see `docs/OLD-DRAFTS-DO-NOT-USE/FUTURE_NAIVE_TACTICAL_AGENT.md`, which should be ignored unless you are specifically revisiting that old proposal.)

**Signalling:** a lockout-abandoned mission sets `Mission.abandonedReason = 'lockout'` and the mission card shows a red "✕ failed · lockout"; an operator `ABANDON_MISSION` sets `'operator'` and shows a muted amber "abandoned". Without this, `abandoned` missions had no status label and read like a quiet completion.

## Tutorial (guided walkthrough)

48 steps in `src/utils/tutorialSteps.ts`, rendered by `Tutorial.tsx` (primary window) and
`TacticalTutorial.tsx` (map window). It teaches the **manual workflow first** — allocate, plan,
deploy, recover from a failure by hand — and only then the two assistants. Accordingly the tactical
planner **hides its "Suggest" button** until `TACTICAL_AGENT_STEP` (the `tac-suggest-intro` step),
so the manual lessons can't be short-circuited.

Every step index other modules key off (`AGENT_INTRO_STEP`, `FAILURE_DEMO_STEP`,
`TACTICAL_AGENT_STEP`, …) is **derived from the step list by id** at the foot of the file — never
hardcode one. They used to be literal numbers and silently desynced whenever a step moved.

The failure demo is scripted in two acts, and each act's lesson card asserts something about the
state, so the reducer has to guarantee it (`scripts/test-tutorial-failure-demo.ts` pins both):

- `TUTORIAL_FORCE_FAILURE` (`failure-recovery-do`, "Reassign Now") fails a drone whose loss leaves
  **every** remaining task coverable by the surviving subswarm — so "Reassign ✓" is genuinely
  reachable. Not `FORCE_DRONE_FAILURE`, which takes the first executing drone and could take the
  training team's only Lifter.
- `TUTORIAL_FORCE_ABANDON_SCENARIO` (`abort-do`, "Abort the Mission") fails a drone whose loss leaves
  some remaining task **uncoverable**, so "Reassign" really is disabled and abandoning is the only
  way out. If no such drone exists it declines to fire and the step's `unsatisfiableWhen` offers
  Next rather than staging a dead end the operator could trivially fix.

Coverage is decided by `src/utils/coverage.ts`, which mirrors the planner's Deploy/Reassign gate
(primary or substitute composition) — the same predicate backs the `unsatisfiableWhen` gates, so a
step never demands an action the UI won't allow.

## Critical Constraints

1. **All randomness seeded** — pass `SeededRNG` instances everywhere, never call `Math.random()` in game logic
2. **No backend** — all state in-memory; export is a client-side JSON download
3. **UI language** — use "Strategic Assistant" / "Tactical Assistant" (operator-facing UI only — internal identifiers, action types, and logged event fields like `isAgentSuggested`/`wasAgentSuggested`/`modifiedFromAgentPlan` keep "Agent" and are unaffected), never "Co-Pilot", "Meta-Co-Pilot", "AI", or "algorithm". **Never call the main map "operational map"** (anywhere — UI, comments, docs, code identifiers): it is the **strategic map**; the only map/planner terms are "strategic" and "tactical".
4. **Events logged immediately** — every operator action and agent recommendation must be logged with ms timestamp; see [`docs/EVENT_LOGGING.md`](docs/EVENT_LOGGING.md) for the full event schema, envelope fields, and rules for adding new events
5. **BroadcastChannel host/client** — primary window is host; map window subscribes only; never let client mutate state
