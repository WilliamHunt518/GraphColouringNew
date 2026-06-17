# Event Logging Architecture

This file documents the data-logging system that records every operator action and
agent recommendation during a study session. It exists so that a future engineer (human
or Claude) can extend the event log correctly without re-deriving the design decisions
behind it.

Read this alongside `CLAUDE.md` (architecture overview) and `docs/paper/` (the
study design write-up — see "Known code-vs-paper discrepancies" below, some of it is stale).

## Why this exists

This system was built out from a research audit (2026) that checked whether the
event log was sufficient to answer the study's research questions (RQ1 performance
benefit, RQ2 selective use of agents, RQ3 deferral by tier×complexity, RQ4 observation
of failures/override quality/automation bias) and to fully reproduce any session from
its logged parameters alone. The sections below are organized around what that audit
found missing and how it was fixed — keep that framing if you add new events: **ask
"what RQ or reproducibility need does this serve" before adding a field.**

## Non-negotiables (do not regress these)

1. **Monotonic ordering** — every event has a strictly increasing `seq` (across the
   whole study, never resets between sessions) plus a session-relative `timestamp` (ms).
   `seq` is the tie-breaker when two events land in the same tick/ms.
2. **Wall-clock anchor** — every event also carries `wallClock` (ISO-8601, real time),
   so logs can be cross-referenced against screen recordings / external timers.
3. **Stable session identity** — `sessionId` is deterministic:
   `` `${participantId}_${seed}_s${sessionNumber}` ``. Not a random UUID — this means
   the same participant + seed + session number always produces the same ID, which is
   useful for re-running/debugging a session, but it is **not unique across
   re-runs of the same session** (a known, accepted limitation — see Known gaps).
4. **Append-only** — `logEvent()` only ever appends; nothing is mutated or removed
   from `state.events[sessionIdx]` after the fact.
5. **Full reproducibility from `session_start`** — a single `session_start` event
   contains every parameter needed to regenerate that session's mission stream and
   scoring deterministically (seed, complexity, fleet, task compositions/timings,
   penalty rates, failure schedule constants, arrival lambda, category weights, agent
   ε values, conservative-strategy tuning constants). If you add a new tunable constant
   that affects mission generation, scoring, or agent behavior, **add it to
   `SessionStartEvent` too** — this is the master parameter dump.
6. **Agent proposals are logged even when rejected** — `strategic_modal_opened` logs
   the full Aggressive/Conservative cards (including `trueAssets`, never shown to the
   operator) regardless of what the operator picks; `strategic_dismissed` and
   `tactical_opened` exist specifically so a "shown but not followed" interaction still
   leaves a record. Never gate a proposal log behind "only if accepted."

## Where things live

- `src/types/index.ts` — `BaseEvent` + all `GameEvent` subtypes (the schema).
- `src/store/gameReducer.ts` — `logEvent()` (the envelope-stamping helper, ~line 98)
  and every `logEvent(...)` call site (the actual instrumentation).
- `src/components/GameShell.tsx` — `downloadData()` builds the final exported JSON
  (`{ participantId, condition, mode, ..., sessions: state.events }`). No event
  filtering happens here — whatever's in `state.events` is exported verbatim.

## Event envelope (`BaseEvent`)

Every event has these fields, populated automatically by `logEvent()` — never set
them yourself in a call site:

| Field | Type | Source |
|---|---|---|
| `seq` | `number` | `state.eventSeq`, incremented every call |
| `timestamp` | `number` | `Math.round(state.elapsed * 1000)` — ms since session start |
| `wallClock` | `string` | `new Date().toISOString()` at log time |
| `sessionId` | `string` | derived, see above |
| `sessionNumber` | `number` | `state.sessionNumber` |
| `elapsed` | `number` | `state.elapsed` (seconds) |
| `reserveState` | `AssetRequirement` | snapshot of available drones by type at log time |

`logEvent(state, payload)` takes a payload that **omits** these envelope fields (see
the `EventPayload` distributive-omit type just above it) and returns a new `GameState`
with the event appended to `events[state.sessionNumber - 1]` and `eventSeq` bumped.

## Event inventory

| `type` | Fired when | Key fields beyond the envelope | Logged in |
|---|---|---|---|
| `session_start` | First tick of a session (`sessionStartMs` transitions null→set) | Full parameter dump: condition/seed/fleet/task tables/penalty rates/category weights/arrival λ/failure schedule constants/conservative-strategy constants — see `SessionStartEvent` | `gameReducer.ts:825` (TICK) |
| `phase_change` | Any `GamePhase` transition (`playing`↔`survey`↔`between`↔`done`) | `fromPhase`, `toPhase` | `FINISH_SURVEYS` (2121), `NEXT_SESSION` (2130), `END_STUDY` (2151), `endSession()` (2399, → `'survey'`) |
| `mission_arrived` | Mission spawns (real spawn in TICK, or `FORCE_MISSION_ARRIVAL` in testing mode) | `taskCompositions` (primary+substitute comp/baseTime per task), `scheduledFailureTimes`, `penaltyRate`, `maxReward` | `gameReducer.ts:867` (TICK spawn loop), `:2167` (`FORCE_MISSION_ARRIVAL`) |
| `mission_completed` | Mission's last task transitions to completed/failed in the same tick | `tasksCompleted`, `tasksFailed`, `rewardEarned`, `penaltyAccrued` (computed for that mission only) | `gameReducer.ts:1052` (TICK, before `updatedMissions` is committed to state) |
| `strategic_modal_opened` | `OPEN_STRATEGIC` or `OVERRIDE_TACTICAL` (re-opens the modal) | Full `strategiesPresented[]` (displayed AND true asset counts, scores incl. `redundancyScore`, bad-suggestion flags), `activeMissions`, `currentPenaltyAccrued` | `gameReducer.ts:1278` (`OPEN_STRATEGIC`), `:1618` (`OVERRIDE_TACTICAL`) |
| `strategic_dismissed` | `CLOSE_STRATEGIC` (operator closes the modal without picking) | `latencyMs` (open→dismiss) | `gameReducer.ts:1307` |
| `strategic_choice` | `APPLY_STRATEGIC` (operator picks Aggressive/Conservative/Manual) | `latencyMs`, `deltaVsAggressive`/`deltaVsConservative` (chosen minus each card's true assets), `agentSuggestionWasBad`/`badSuggestionType` | `gameReducer.ts:1470` |
| `tactical_opened` | Immediately after `strategic_choice`, when the tactical planner becomes available | `strategyChosen`, `agentPlan[]` (taskId/taskType/assetIds/order as suggested) | `gameReducer.ts:1493` |
| `tactical_confirmed` | `CONFIRM_TACTICAL` | `latencyMs` (tactical-open→confirm), `agentPlan[]` vs `finalPlan[]` triples, `modifiedFromAgentPlan`, `changedTaskIds`, `chainingUsed` | `gameReducer.ts:579` (inside `applyTacticalAllocation()`) |
| `drone_failure` | Scheduled in-mission failure fires | `droneId`, `droneType`, `taskId`, `taskType` | `gameReducer.ts:959` (TICK), `:2273`/`:2324` (testing-mode forced failures) |
| `failure_recovery` | `ACCEPT_RECOVERY`, `APPLY_MANUAL_RECOVERY`, or `CONFIRM_FAILURE_RECOVERY` | `recoveryType` (`reserve`/`redistribute`/`manual`), `wasAgentSuggested` | `gameReducer.ts:1649`, `:1716`, `:1806` |
| `task_completed` | Task's `completionTime` is reached | `taskType`, `assetsUsed`, `completionTime` | `gameReducer.ts:1035` |
| `task_failed` | Task fails (section-deadline miss, recall, abandon, session end, tactical lockout) | `reason` | `gameReducer.ts:1084`, `:1917`, `:1981` |
| `asset_recalled` | Operator manually recalls a drone | `assetId`, `missionId`, `taskId` | `gameReducer.ts:1960` |
| `task_reprioritised` | Operator reorders the task queue | `taskId`, `newPosition` | `gameReducer.ts:2067`, `:2089` |
| `mission_abandoned` | `ABANDON_MISSION` | `completedTaskCount`, `remainingTaskCount` | `gameReducer.ts:1925` |
| `trust_probe` / `trust_probe_dismissed` | Periodic trust/workload probe answered or dismissed | `trust`, `workload` | `gameReducer.ts:2099`, `:2105` |
| `survey_response` | Any NASA-TLX / trust / TAM survey page submitted | `surveyName`, `responses` (raw Likert/slider values) | `gameReducer.ts:2112` |
| `session_ended` | Session timer expires, or `FORCE_SESSION_END` (testing/tutorial) | `score`, `penaltyAccrued`, `completionPoints`, `greenEfficiency`, `meanMissionTime`, `agentFollowRate`, `tacticalFollowRate`, `reason` (`'timer'`\|`'forced'`), `inFlightMissionIds` | `gameReducer.ts:2387` inside `endSession(s, reason)` |

`agentFollowRate` = fraction of `strategic_choice` events with `wasAgentSuggestion: true`
out of all `strategic_choice` events that session. `tacticalFollowRate` = fraction of
agent-suggested `tactical_confirmed` events with `modifiedFromAgentPlan: false`.

## Mapping to research questions

- **RQ1 (performance benefit)** — `session_ended` (score/penalty/completion/green
  efficiency/mean mission time) compared across condition (HH/LH/HL/LL), joined with
  `session_start.epsilonStrategic/epsilonTactical` to confirm the realised condition.
- **RQ2 (selective use)** — `strategic_choice.wasAgentSuggestion` /
  `agentSuggestionWasBad` vs `strategic_modal_opened.strategiesPresented[].isBadSuggestion`
  lets you check whether operators selectively reject bad suggestions specifically (not
  just suggestions in general). `tactical_confirmed.modifiedFromAgentPlan` is the
  tactical-tier analogue.
- **RQ3 (deferral by tier × complexity)** — join `strategic_choice`/`tactical_confirmed`
  `latencyMs` and follow/override behavior against `session_start.complexity` and
  `mission_arrived.category` (mission size proxy).
- **RQ4 (observation of failures / override quality / automation bias)** —
  `drone_failure` → `failure_recovery` pairs (`wasAgentSuggested` flags whether the
  recovery option taken was the agent-suggested one) plus `mission_abandoned` for cases
  where no recovery was feasible. `strategic_modal_opened.strategiesPresented[].trueAssets`
  vs `displayedAssets` lets you compute whether an operator's choice tracked the *true*
  (correct) allocation or the *displayed* (possibly perturbed) one — the key signal for
  automation bias.

## Known gaps (scoped out, flagged for future work)

These were identified during the audit and deliberately **not** implemented in this
pass — either because they need new UI instrumentation, cross-window architecture
changes, or are a larger feature than a logging fix. Flagging them here so they aren't
silently forgotten:

- **Pre-study demographics survey** and **post-study open-response survey** — not built.
- **Cross-window attention/focus tracking** (`panel_focus_change` or similar) — blocked
  by the architectural rule that the map window (`?view=map`) is a BroadcastChannel
  *client* and must never mutate shared state (see `CLAUDE.md` constraint #5). Doing
  this properly needs a new BroadcastChannel message type for the map window to report
  focus/visibility changes back to the host, which then logs it — not just a reducer change.
- **Accountability / reliability score system** — entirely unimplemented feature, not
  just a missing log.
- **`infeasibleAttempted` flag** (operator attempts an allocation that's infeasible) —
  needs UI instrumentation in `PrimaryDisplay.tsx`/`MapDisplay.tsx`, not just a reducer event.
- **Standalone `recovery_opened` event** — currently `failure_recovery` only fires on
  the *resolution* of a recovery, not when the options are first presented. Low priority
  since `drone_failure` already timestamps when recovery became necessary.
- **Git/build provenance in the export** — the downloaded JSON doesn't embed a commit
  hash or build identifier. Useful for "which code version produced this data" audits.
- **True random UUIDs for `sessionId`** — currently deterministic
  (`participantId_seed_sN`), which means re-running the exact same participant/seed/session
  combination (e.g., a researcher testing the same URL twice) produces a colliding
  `sessionId`. Acceptable for now since real participants get unique IDs, but would
  break if two test runs' exports were ever merged.

## Known code-vs-paper discrepancies (still true as of this writing)

The original audit also flagged places where the codebase and `docs/paper/` disagree.
These are **not** logging gaps — they're real behavioral differences worth knowing about
before trusting the paper's description of the system:

- `src/utils/copilot.ts` (`generateStrategies()` → `applyBadAgent()`) still actively
  perturbs the *displayed* Strategic Agent card values via ε_Strategic. The paper's
  claim (if it says ε-injection was removed) is stale.
  `strategic_modal_opened.strategiesPresented[].trueAssets` vs `.displayedAssets` is
  exactly the field pair that lets you reconstruct what was shown vs what would actually
  deploy.
- `src/store/gameReducer.ts` (`APPLY_STRATEGIC`, tactical error injection block) still
  actively suppresses one tactical task with probability ε_Tactical
  (`hasTacticalError`/`suppressedTaskId` on `PendingAllocation`).
- `src/utils/config.ts` `parseURLConfig()` always sets `condition: 'none'` — there is
  no URL-param-driven mapping from a condition code (HH/LH/HL/LL) to ε values; the
  researcher must set epsilons some other way (or the start screen handles it — check
  `StartScreen.tsx` before assuming this is broken).
- Penalty growth: confirm against `computePenaltyAccrued()` in `gameReducer.ts` whether
  it's linear or exponential in elapsed time before citing the paper's claim either way.

## How to add a new event

1. Add the interface to `src/types/index.ts` (extends `BaseEvent`, fields beyond the
   envelope only) and add it to the `GameEvent` union at the bottom of that file.
2. Call `logEvent(state, { type: '...', ...fields })` at the point in
   `gameReducer.ts` where the thing actually happens — not in a UI component. The
   reducer is the single source of truth for what happened and when.
3. If the event represents an agent proposal, log it **regardless of whether the
   operator accepts it** (see non-negotiable #6).
4. If the event depends on a tunable constant (a rate, a probability, a duration),
   make sure that constant is also captured in `SessionStartEvent` so sessions remain
   reproducible from the log alone.
5. Run `npx tsc --noEmit -p .` — the `EventPayload` distributive-omit type in
   `gameReducer.ts` will fail to compile if your new event type doesn't extend
   `BaseEvent` correctly, which catches most mistakes here.
