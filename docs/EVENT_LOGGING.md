# Event Logging Architecture

This file documents the data-logging system that records every operator action and
agent recommendation during a study session. It exists so that a future engineer (human
or Claude) can extend the event log correctly without re-deriving the design decisions
behind it.

Read this alongside `CLAUDE.md` (architecture overview). (An earlier study-design write-up
lived in `docs/paper/`; it has been archived to `docs/OLD-DRAFTS-DO-NOT-USE/paper/` and is
**deprecated** — ignore it unless specifically revisiting old drafts. Newer drafts will be
added separately when ready.)

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
| `reserveState` | `AssetRequirement` | RAW hub inventory — every asset with `status === 'available'` |
| `reserveStateAvailable` | `AssetRequirement` | reserve as DISPLAYED to the operator: hub-available minus drones committed to other missions' pending tactical plans. Same call the UI makes (`reserveCount(assets, missions)`). Usually equals `reserveState`, because `launchToLoiter` flies committed drones out immediately; they diverge only for a pool drone that becomes available again while its mission is still tactical-pending |
| `context` | `EventContext` | world state at log time — see below |

### `context` (envelope)

Stamped on every event so **"how many X were there when Y happened?" is answerable from the
event alone**, without replaying the session. Counts are the operator's load at the moment of
the decision — the covariate RQ3 wants, and the "what else was competing for attention"
qualifier RQ2/RQ4 want.

`score`, `penaltyAccrued`, `missionsQueued/Active/Completed/Failed/Abandoned`,
`tasksPending/Traveling/Executing/CompletedTotal/FailedTotal`,
`dronesAvailable/Deployed/Returning/Failed`, `tacticalPendingMissionIds[]`,
`recoveryPendingMissionIds[]`, `strategicModalMissionId`.

Invariants worth asserting in analysis: the four drone counts sum to the fleet size, and
`dronesAvailable === reserveState.Blue + .Red + .Green`.

`logEvent(state, payload)` takes a payload that **omits** these envelope fields (see
the `EventPayload` distributive-omit type just above it) and returns a new `GameState`
with the event appended to `events[state.sessionNumber - 1]` and `eventSeq` bumped.

## Event inventory

| `type` | Fired when | Key fields beyond the envelope | Logged in |
|---|---|---|---|
| `session_start` | First tick of a session (`sessionStartMs` transitions null→set) | Full parameter dump: condition/seed/fleet/task tables/penalty rates/category weights/arrival λ/`failureRatePerDroneSecond` (`study-v1.3`+; live per-drone-second hazard, replaces the pre-v1.3 `failureCount`/`failureGap`/`failureJitter`/`failureProb` schedule constants) + `failureRollIntervalSec` (`study-v1.4`+; the simulated-time cadence that hazard is rolled on — **its absence marks a `v1.3` log, whose realized failure rate depended on the machine's refresh rate, see STUDY_BUILD.md § 11**) + `failureGraceSeconds` (`study-v1.5`+; seconds a mission is exempt from further failures after its recovery is resolved — **absent ⇒ no grace, so pre-`v1.5` drone-failure counts run slightly higher, see STUDY_BUILD.md § 12**)/conservative-strategy constants — see `SessionStartEvent` | `gameReducer.ts:825` (TICK) |
| `phase_change` | Any `GamePhase` transition (`playing`↔`survey`↔`between`↔`done`) | `fromPhase`, `toPhase` | `FINISH_SURVEYS` (2121), `NEXT_SESSION` (2130), `END_STUDY` (2151), `endSession()` (2399, → `'survey'`) |
| `mission_arrived` | Mission spawns (real spawn in TICK, `FORCE_MISSION_ARRIVAL` in testing mode, **or a residual mission re-queued by `ABANDON_MISSION`**) | `taskCompositions` (primary+substitute comp/baseTime per task), `penaltyRate`, `maxReward`, `isResidual`/`parentMissionId` (**a residual is not new demand — exclude it from arrival denominators, see § Abandonment**). `study-v1.3`+ dropped `scheduledFailureTimes` — failures are no longer scheduled per mission, see `session_start.failureRatePerDroneSecond` | all three sites share `missionArrivedPayload()` — TICK spawn loop, `FORCE_MISSION_ARRIVAL`, `ABANDON_MISSION` |
| `mission_completed` | Mission's last task transitions to completed/failed in the same tick | `tasksCompleted`, `tasksFailed`, `rewardEarned`, `penaltyAccrued` (that mission only), `outcome` (`all_completed`/`partial`/`none_completed` — **a mission reaches this event once every task is completed OR failed, so `completed` alone does not mean it went well**), plus the decisions that produced it: `arrivalTime`, `allocationTime`, `timeToAllocate`, `durationFromAllocation`, `maxReward`, `chosenStrategyName`, `agentInteraction`, `hadTacticalError`, `suppressedTaskId`, `droneFailureCount` | `gameReducer.ts` TICK step 3a (before `updatedMissions` is committed to state) |
| `strategic_modal_opened` | `OPEN_STRATEGIC` or `OVERRIDE_TACTICAL` (re-opens the modal) | Full `strategiesPresented[]` (displayed AND true asset counts, scores incl. `redundancyScore`, bad-suggestion flags), `activeMissions`, `currentPenaltyAccrued` | `gameReducer.ts:1278` (`OPEN_STRATEGIC`), `:1618` (`OVERRIDE_TACTICAL`) |
| `strategic_dismissed` | `CLOSE_STRATEGIC` (operator closes the modal without picking) | `latencyMs` (open→dismiss) | `gameReducer.ts:1307` |
| `strategic_choice` | `APPLY_STRATEGIC` (operator picks Aggressive/Conservative/Manual) | `latencyMs`, `deltaVsAggressive`/`deltaVsConservative` (chosen minus each card's true assets), `agentSuggestionWasBad`/`badSuggestionType`, `strategyCardCount`, `manualBeforeCardsLoaded`/`cardsLoadedAtManualSwitch` (manual chosen before the 3–5 s card reveal finished = a clue the operator declined the agent) | `gameReducer.ts:1470` |
| `tactical_opened` | Immediately after `strategic_choice`, when the tactical planner becomes available | `strategyChosen`, `agentPlan[]` (taskId/taskType/assetIds/order as suggested), **`hasTacticalError`/`suppressedTaskId` (the ε_T draw for this mission — logged whether or not it ever manifests)**, `dronePool`, `agentProjectedCompletion`, `unassignedTaskIds` | `gameReducer.ts` (`APPLY_STRATEGIC`) |
| `tactical_confirmed` | `CONFIRM_TACTICAL` | `latencyMs` (tactical-open→confirm), `suggestUsedCount`, `agentPlan[]` vs `finalPlan[]` triples, `modifiedFromAgentPlan`, `changedTaskIds`, `chainingUsed`, plus override-quality fields: `agentProjectedCompletion` vs `finalProjectedCompletion` (directly comparable — same scheduler, same units), `plannedTasks[]` (per-task start/base/substitute), `unassignedTaskIds` (**committed with no drones ⇒ can never complete**), `substituteTaskIds`, `chainedDroneIds` | `gameReducer.ts` (inside `applyTacticalAllocation()`) |
| `tactical_suggest_used` | `TACTICAL_SUGGEST` (operator clicks "Suggest" in the tactical **or recovery** planner) | `suggestCountThisMission` (1-based click index this allocation), `recoveryMode` | `gameReducer.ts` (`TACTICAL_SUGGEST` case) |
| `strategic_card_previewed` | `PICK_STRATEGY` (operator highlights an Aggressive/Conservative card in the strategic modal, before applying) | `strategyIndex`, `strategyName`, `latencyMs` (since modal opened) | `gameReducer.ts` (`PICK_STRATEGY` case) |
| `manual_allocation_edited` | `EDIT_MANUAL` (operator adjusts a manual drone count in the strategic modal) | `allocation` (running counts after this edit), `latencyMs` (since modal opened) | `gameReducer.ts` (`EDIT_MANUAL` case) |
| `tactical_assignment_changed` | `TACTICAL_ASSIGN_CHANGED` (each drone→task drag while building/editing a tactical or recovery plan; relayed from the map window via `_mapAction`) | `op` (`assign`/`chain`/`remove`/`unassign`), `droneId`, `droneType`, `taskId`, `taskType`, `recoveryMode` | `gameReducer.ts` (`TACTICAL_ASSIGN_CHANGED` case) |
| `drone_failure` | Scheduled in-mission failure fires | `droneId`, `droneType`, `taskId`, `taskType` — **both null** when the failed drone hadn't reached (or been dispatched to) a task yet, i.e. it was still loitering | `gameReducer.ts:959` (TICK), `:2273`/`:2324` (testing-mode forced failures) |
| `failure_recovery` | `ACCEPT_RECOVERY`, `APPLY_MANUAL_RECOVERY`, or `CONFIRM_FAILURE_RECOVERY` | `recoveryType` (`reserve`/`redistribute`/`manual`), `wasAgentSuggested`, `recoveryReason`, `latencyMs` (paired back to `recovery_opened`), `repairedTaskIds`, `repairedAssignments[]`, `tasksStillUnassigned` (**pending tasks the fix leaves with nobody on them** — an incomplete recovery) | `gameReducer.ts` (three recovery cases) |
| `task_completed` | Task's `completionTime` is reached | `taskType`, `assetsUsed`, `completionTime` (**the task's own completion time — what scoring charges against**, not the tick that noticed it), `detectedAtElapsed` (the tick that noticed; equal to within a frame unless the sim clock was throttled), `startTime`, `travelTime`, `baseTime`, `useSubstitute`, `rewardEarned`, `waitFromMissionArrival` | `gameReducer.ts` TICK step 3 |
| `task_failed` | Task is genuinely lost (section safety net, recall, session end, tactical lockout) | `reason` (`asset_recalled`/`session_ended`/`drone_failure`/`tactical_lockout`/`scheduling_deadlock`/`mission_abandoned`), `taskType`, `statusBefore` (what it was doing when it died — `pending` means never dispatched), `assignedAssetIds`, `startTime`, `rewardForgone`, `waitFromMissionArrival`, `missionWasAllocated` (**false ⇒ the operator never took this mission on; this is the dominant shape of `session_ended` failures**), `missionStatusBefore`. All sites go through `taskFailedPayload()` so they log identically | `gameReducer.ts` (TICK step 3 / 3b, `RECALL_ASSET`, `endSession`; `ABANDON_MISSION` only for work with no residual copy) |
| `task_requeued` | `ABANDON_MISSION` — an incomplete task moves to the residual mission | `residualMissionId`/`residualTaskId` (**join key: a later `task_completed` uses the residual id**), `statusBefore`, `assignedAssetIds`, `rewardDeferred`, `executionProgress` (seconds already executed, preserved), `remainingBaseTime`, `waitFromMissionArrival`. **Not a failure** — see § Abandonment | `gameReducer.ts` (`ABANDON_MISSION`) |
| `lockout_detected` | Live cross-drone scheduling deadlock detected + acted on (TICK step 3c) | `taskIds`, `droneIds`, `resolution` (`rerouted` when `fixLockouts` on = agent auto-fix; `help_needed` when off = surfaced to operator for recovery) | `gameReducer.ts` step 3c |
| `asset_recalled` | Operator manually recalls a drone | `assetId`, `missionId`, `taskId` | `gameReducer.ts:1960` |
| `task_reprioritised` | Operator reorders the task queue | `taskId`, `newPosition` | `gameReducer.ts:2067`, `:2089` |
| `mission_abandoned` | `ABANDON_MISSION`, or a stuck scheduling deadlock when `fixLockouts` is off (TICK step 3c) | `completedTaskCount`, `remainingTaskCount`, `residualMissionId`, `carriedTaskIds`, `rewardCarriedOver` (**still winnable via the residual**), `rewardLost` (genuinely forgone — normally 0) | `gameReducer.ts` (`ABANDON_MISSION`), step 3c |
| `state_snapshot` | Every `STATE_SNAPSHOT_INTERVAL` (10 s) of elapsed time, on a fixed grid | Full dump: every mission (status/times/strategy/interaction/recovery flags/per-mission penalty so far/all tasks with status+drones+times/`droneSequences`) and every drone (status/mission/task/interpolated x,y). Emitted on an elapsed-time grid so a coarse or throttled tick can't skip one, and a long tick emits at most one catch-up rather than a burst | `gameReducer.ts` TICK step 5b |
| `recovery_opened` | A mission enters "help needed" — drone failure (non-graceful) or a surfaced lockout | `recoveryReason`, `failedDroneId`/`failedDroneType`, `affectedTaskIds`/`affectedTaskTypes`, `onMissionDroneIds` (what the recovery planner offers), `reserveAvailable`, `feasibleWithOnMissionDrones`, `tasksRemaining` | TICK failure handler, TICK step 3c (lockout), `FORCE_DRONE_FAILURE` |
| `trust_probe` / `trust_probe_dismissed` | Periodic trust/workload probe answered or dismissed | `trust`, `workload` | `gameReducer.ts:2099`, `:2105` — **NOTE: currently unreachable, see Known gaps** |
| `survey_response` | Any NASA-TLX / trust / TAM survey page submitted | `surveyName`, `responses` (raw Likert/slider values) | `gameReducer.ts:2112` |
| `session_ended` | Session timer expires, or `FORCE_SESSION_END` (testing/tutorial) | `score`, `penaltyAccrued`, `completionPoints`, `greenEfficiency`, `meanMissionTime`, `agentFollowRate`, `tacticalFollowRate`, `reason` (`'timer'`\|`'forced'`), `inFlightMissionIds`, `taskOutcomes` (`completed`/`failed`/`requeued`/`failuresByReason`/`failedOnNeverAllocatedMissions` — the headline ledger, so nobody has to re-derive it) | `gameReducer.ts` inside `endSession(s, reason)` |

`agentFollowRate` = fraction of `strategic_choice` events with `wasAgentSuggestion: true`
out of all `strategic_choice` events that session. `tacticalFollowRate` = fraction of
agent-suggested `tactical_confirmed` events with `modifiedFromAgentPlan: false`.

## Abandonment: re-queued work is not lost work

**Read this before counting failures.** Abandoning a mission does not destroy its outstanding
work. Every task that is still `pending`/`traveling`/`executing` is copied into a **residual
mission** (`<parent>-R`, with partial execution progress preserved) which re-enters the queue and
can be allocated and completed like any other. In practice most residuals do get finished.

The log therefore records an abandonment as a **transfer**, not a loss:

| What happened | Event |
|---|---|
| Task moves to the residual | `task_requeued` (`taskId` → `residualTaskId`) |
| Task had no residual copy — genuinely gone | `task_failed` with `reason: 'mission_abandoned'` |
| The mission itself | `mission_abandoned` with `carriedTaskIds`, `rewardCarriedOver`, `rewardLost` |
| The residual joins the queue | `mission_arrived` with `isResidual: true`, `parentMissionId` |

Rules that follow from this, and that `sim/log-audit.mts` enforces:

- **Never count `task_requeued` as a failure.** It was logged as `task_failed` until
  2026-08-21, which made every abandonment read as mass task loss — a log would show three
  tasks "failed" for 130 forgone points while those same three completed under the residual two
  minutes later. If you are reading logs collected before that date, subtract them by hand.
- **Follow the work by `residualTaskId`.** Task ids change at the boundary
  (`M002-T2` → `M002-R-T1`), so per-task-id joins across an abandonment need this hop.
- **Exclude residual arrivals from "what arrived".** Their tasks and reward were already
  counted under the parent, so including them double-counts demand and makes
  `reward_capture`/`task_rate` wrong. `scripts/study_report.py` filters on `isResidual`.
  Their *completions* do belong in the numerator — that is the same original work getting done.
- **The parent stops accruing penalty at `abandonedAt`**; the residual accrues from its own
  `arrivalTime` (the same instant). Charging both double-billed one piece of outstanding work.
- **An abandoned mission keeps `status: 'abandoned'` to the end of the session**, and its tasks
  are not swept into failures by `endSession` — their resolution is the `task_requeued`.

## Reading `task_failed` without over-reading it

**`reason: 'drone_failure'` does not always mean a drone failed.** Two caveats, one historical and
one permanent:

- **Before `study-v1.4`**, the sections-by-colour safety net failed every task staffed with its
  *substitute* composition the moment it started executing, and logged it under this reason with
  nothing actually broken (STUDY_BUILD.md § 11). The signature in a `v1.0`–`v1.3` log is specific:
  `statusBefore: 'executing'` **and `elapsed − startTime ≈ 0`** (sub-second — the task died on its
  first executing tick), with no `drone_failure` event at that instant. Those are the engine killing
  legitimate work, not adversity the participant faced. Fixed from `v1.4`.
- **In every version**, a task can carry this reason with no `drone_failure` alongside it because it
  is *downstream* of an earlier failure: while a mission sits in `failureRecoveryPending` and the
  operator has not repaired it, drones released by the original failure are no longer covering the
  tasks they were assigned to, so those tasks fail their section check seconds or minutes later.
  These are genuine losses — read them together with the `recovery_opened` that preceded them, not
  as separate incidents. Verified live: one failure at 337 s produced three such failures between
  408 s and 444 s while the mission was left unrepaired.


Two structural sources produce most failures, and neither means the operator lost live work:

1. **`reason: 'session_ended'` on a mission that was never allocated.** At the buzzer every
   unfinished task of every unfinished mission is failed, including missions still sitting in
   the queue untouched. `missionWasAllocated: false` marks these; `session_ended.taskOutcomes
   .failedOnNeverAllocatedMissions` totals them. This is a *throughput/triage* signal (the
   operator could not get to it), not an execution failure.
2. **`reason: 'drone_failure'`** covers the section safety-net: a task whose required drone type
   is no longer present for its section window. It fires for the drone that failed *and* for any
   task that lost a chained drone as a knock-on.

A mission still in flight when the timer ran out is relabelled `completed` in the final state if
any of its tasks finished, but fires **no** `mission_completed` event. That pair — status
`completed`, no event — is legitimate only for missions listed in
`session_ended.inFlightMissionIds`; the audit harness checks exactly that.

## Mapping to research questions

- **RQ1 (performance benefit)** — `session_ended` (score/penalty/completion/green
  efficiency/mean mission time) compared across condition (HH/LH/HL/LL), joined with
  `session_start.epsilonStrategic/epsilonTactical` to confirm the realised condition.
  At mission granularity, `mission_completed` now carries its own outcome AND the decisions that
  produced it (`chosenStrategyName`, `agentInteraction`, `outcome`, `timeToAllocate`,
  `durationFromAllocation`, `rewardEarned` vs `maxReward`), so "did agent-followed allocations
  outperform manual ones?" is a single-event query rather than a multi-event join. Scoring is
  exactly reconstructible from the log: penalty accrues to `task_completed.completionTime` for
  completed tasks and to `session_ended.elapsed` for anything still unfinished.
- **RQ2 (selective use)** — `strategic_choice.wasAgentSuggestion` /
  `agentSuggestionWasBad` vs `strategic_modal_opened.strategiesPresented[].isBadSuggestion`
  lets you check whether operators selectively reject bad suggestions specifically (not
  just suggestions in general). `tactical_confirmed.modifiedFromAgentPlan` is the
  tactical-tier analogue: it is **true only when the operator changed the drones on a task the
  agent actually suggested** (compared over `pending.taskAssignments` keys). In **greedy** mode
  the agent commits only the first step, so filling in the remaining steps does NOT flip this
  flag — only altering the agent's committed step does. `changedTaskIds` lists exactly those
  altered agent tasks; anything the operator adds beyond the agent's suggestion is visible by
  diffing `agentPlan[]` vs `finalPlan[]`. **Consultation vs. follow are distinct** — the tactical planner
  starts empty, so an operator can confirm a plan without ever consulting the agent.
  `tactical_confirmed.suggestUsedCount` (and the `tactical_suggest_used` events) measure
  whether the agent's tactical plan was ever pulled in (`0` = never consulted), which
  `modifiedFromAgentPlan`/`wasAgentSuggested` do *not* capture — the latter only reflects
  whether the *strategic* card was agent-sourced. On the strategic tier,
  `strategic_choice.manualBeforeCardsLoaded` flags operators who bailed to manual before the
  cards finished their reveal delay — declining the agent without evaluating it. Finer-grained
  deliberation is captured by `strategic_card_previewed` (each Aggressive/Conservative highlight,
  with `latencyMs` → per-card dwell time and A↔C toggling = engagement with both options) and
  `manual_allocation_edited` (each manual count adjustment → manual-build effort and time), so the
  *path* to a choice is recoverable, not just the final `strategic_choice`. On the tactical tier,
  `tactical_assignment_changed` does the same for within-mission planning — every drone→task drag
  (assign/chain/remove/unassign), timestamped, so the order of construction, backtracking, and
  chaining behaviour are fully replayable, not just the `tactical_confirmed` end state.
- **RQ3 (deferral by tier × complexity)** — join `strategic_choice`/`tactical_confirmed`
  `latencyMs` and follow/override behavior against `session_start.complexity` and
  `mission_arrived.category` (mission size proxy).
- **RQ4 (observation of failures / override quality / automation bias)** —
  the failure loop is now logged in three parts: `drone_failure`/`lockout_detected` (it happened)
  → `recovery_opened` (**what the operator was shown**: affected tasks, the drones the planner
  offered, reserve, and `feasibleWithOnMissionDrones` — which separates "failed to fix a fixable
  problem" from "nothing could be done") → `failure_recovery` (what they did, with `latencyMs`
  from the opening and `tasksStillUnassigned` for an incomplete fix). Override *quality* at the
  tactical tier is `tactical_confirmed.agentProjectedCompletion` vs `finalProjectedCompletion`
  (was the override actually better?) plus `unassignedTaskIds` (did the override strand a task?).
  `tactical_opened.hasTacticalError` records the ε_T draw per mission **whether or not it ever
  manifests**, which is what separates agent accuracy from operator detection — previously an
  injected error was only visible if it happened to surface as a later `task_failed`.
  Original pairing detail:
  `drone_failure` → `failure_recovery` pairs (`wasAgentSuggested` flags whether the
  recovery used the agent's plan — either a pre-computed `ACCEPT_RECOVERY` option, or the
  recovery planner's "Suggest" button in a `CONFIRM_FAILURE_RECOVERY`; also set on
  `lockout_detected` → `failure_recovery` pairs when `fixLockouts` is off) plus `mission_abandoned` for cases
  where no recovery was feasible. `strategic_modal_opened.strategiesPresented[].trueAssets`
  vs `displayedAssets` lets you compute whether an operator's choice tracked the *true*
  (correct) allocation or the *displayed* (possibly perturbed) one — the key signal for
  automation bias.

## Known gaps (scoped out, flagged for future work)

These were identified during the audit and deliberately **not** implemented in this
pass — either because they need new UI instrumentation, cross-window architecture
changes, or are a larger feature than a logging fix. Flagging them here so they aren't
silently forgotten:

- **Pre-study demographics** — now IMPLEMENTED (`SUBMIT_DEMOGRAPHICS` logs a timestamped event and
  sets `state.demographics`). **`study-v1.3`+** also folds in a pre-study AI-attitude survey
  (AIAS-4 + two bespoke Likert blocks) into the same form/event — see `demographics` keys prefixed
  `aias_`/`verif_`/`deleg_`, raw (not reverse-scored) responses, full item text and reverse-key list
  in `docs/STUDY_BUILD.md` §10. **Post-study open-response survey** — still not built.
- **Tactical planner intermediate drags** — now IMPLEMENTED as `tactical_assignment_changed`: each
  drone→task manipulation is relayed from the map window over the existing `_mapAction` channel
  (the map window stays a pure client — it sends an intent, the host reducer logs it, no client
  state mutation, so CLAUDE.md #5 holds). Replays the full build path; `tactical_confirmed` still
  records the final plan.
- **Per-card reveal timestamps** — now IMPLEMENTED. The 4–5 s reveal delay is drawn from the seeded
  RNG (`drawCardRevealDelays`, seeded per mission id) and logged per card as
  `strategic_modal_opened.strategiesPresented[].revealDelayMs`, with
  `strategic_choice.cardRevealDelaysMs` + `deployEnabledAtMs` recording the gate. So
  `latencyMs − deployEnabledAtMs` = operator deliberation, net of the forced wait.
  `deployEnabledAtMs` is 0 for a manual choice (manual allocation was never gated).
- **Cross-window attention/focus tracking** (`panel_focus_change` or similar) — blocked
  by the architectural rule that the map window (`?view=map`) is a BroadcastChannel
  *client* and must never mutate shared state (see `CLAUDE.md` constraint #5). Doing
  this properly needs a new BroadcastChannel message type for the map window to report
  focus/visibility changes back to the host, which then logs it — not just a reducer change.
- **Accountability / reliability score system** — entirely unimplemented feature, not
  just a missing log.
- **`infeasibleAttempted` flag** (operator attempts an allocation that's infeasible) —
  needs UI instrumentation in `PrimaryDisplay.tsx`/`MapDisplay.tsx`, not just a reducer event.
- **Standalone `recovery_opened` event** — now IMPLEMENTED (see the inventory). Fires for both
  the drone-failure and surfaced-lockout paths, and `failure_recovery.latencyMs` pairs back to it.
- **Git/build provenance in the export** — mostly addressed: `session_start` carries `appVersion`
  (a hand-maintained constant, `APP_VERSION` in `gameReducer.ts`), `userAgent`, and `viewport`.
  `appVersion` is kept **identical to a git tag** (`study-v1.0`), so `git show <appVersion>` gives
  the exact code — see [`STUDY_BUILD.md`](STUDY_BUILD.md), which also records what each build
  decided (lockouts, ε, session flow). Bump both together. A true commit hash would still need a
  Vite `define` injection at build time; outstanding, but the tag makes it largely redundant.

### Reachable-but-dead instrumentation (declared, never fires)

These event types and enum members exist in the schema but no UI path dispatches them. They are
**not** logging bugs — each needs a UI/design decision, so they are listed rather than silently
"fixed" with logging that could never fire:

- **`trust_probe` / `trust_probe_dismissed`** — the reducer schedules the probe on a 90 s cadence
  (`TRUST_PROBE_INTERVAL`, `state.trustProbeActive`) but `TrustProbeModal.tsx` is never imported or
  rendered, so no probe is ever shown or answered. This is the study's only *in-session* trust
  measure; mounting it is a study-design decision (it interrupts the operator, which also feeds
  into the NASA-TLX workload rating), not a logging change.
- **`asset_recalled`** and `task_failed`/`'asset_recalled'` — `RECALL_ASSET` is fully implemented in
  the reducer but dispatched from nowhere.
- **`task_reprioritised`** — `REPRIORITISE_TASK` is implemented and `GameShell` relays a
  `REPRIORITISE_TOP` map action, but `MapDisplay` binds the prop as `_onReprioritiseTop` and never
  calls it.
- **`failure_recovery.recoveryType` `'reserve'` / `'redistribute'`**, and `RecoveryOption.type
  'reserve'` — `ACCEPT_RECOVERY`/`APPLY_MANUAL_RECOVERY` are only reachable via BroadcastChannel
  messages the map window never posts, so in practice every recovery logs `'manual'`.
  (`ACCEPT_RECOVERY` used to log its `failure_recovery` *before* the composition guard that can
  reject the redistribution, so a rejected click still produced a "repaired" record while the
  mission stayed in help-needed — and the operator could click again, and again. It now logs only
  when the redistribution is actually applied, and `buildRecoveryOptions` marks an option
  `feasible` only if the resulting composition satisfies the task, i.e. only if that guard will
  accept it. Dead in the shipped UI, but `sim/engine.mts` drives this path, where the old shape
  emitted **1310 phantom recoveries for 7 real failures** in one seed.)
- **`task_failed`/`'mission_abandoned'`** — now fires only for work an abandonment leaves with no
  residual copy. Under current residual rules every incomplete task carries over, so this reason
  is effectively unreachable; the branch is kept so the log stays correct if those rules change.
- **`task_failed`/`'scheduling_deadlock'`** — the lockout path logs `lockout_detected` plus
  `'session_ended'` failures (and `task_requeued` if the operator abandons) instead.
- **True random UUIDs for `sessionId`** — currently deterministic
  (`participantId_seed_sN`), which means re-running the exact same participant/seed/session
  combination (e.g., a researcher testing the same URL twice) produces a colliding
  `sessionId`. Acceptable for now since real participants get unique IDs, but would
  break if two test runs' exports were ever merged.

## Known code-vs-paper discrepancies (still true as of this writing)

The original audit also flagged places where the codebase and the (now-archived,
deprecated) `docs/OLD-DRAFTS-DO-NOT-USE/paper/` draft disagree.
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
   `BaseEvent` correctly, which catches most mistakes here. If you add an envelope field, add it
   to that `Omit<...>` list too, or every call site will demand it.
6. Prefer logging a **fact at the moment it happens** over deriving it later from component
   state. Recovery-planner "Suggest" consultation was originally carried only as
   `wasAgentSuggested` on the resolution event — React state that gets reset whenever the
   mission's pending pool changes (another task completing mid-recovery), which silently lost the
   consultation. It now emits `tactical_suggest_used` with `recoveryMode: true` on the click.
7. **Log the event only once the state change has actually been applied**, on the far side of any
   guard that can reject it. Optimistically logging first produces records of things that never
   happened (`ACCEPT_RECOVERY`, above) — the worst kind of log error, because it is invisible
   until someone diffs the log against the state.
8. **Name the event after what happened, not after the code path that emitted it.** Re-queued
   work was logged as `task_failed` because the abandon handler was the failure handler; the
   schema then asserted something false about the world. When a new situation is not really an
   instance of an existing event, add a type.
9. Verify with `npx tsx sim/log-audit.mts --seeds=10 --complexity=<preset>` — it drives the real
   reducer headlessly and diffs the emitted log against the reducer's own final state (one
   resolution event per task, event counts vs state counts, score/penalty reconciliation,
   monotonic `seq`). It should report `ISSUES: 0` on every preset.

## Log volume

With `state_snapshot` at 10 s, expect roughly **0.5–1 MB per 8-minute session** (an observed
3-minute single-mission session was 79 KB; it scales with concurrent missions). Two consequences:

- The end-of-session `localStorage` autosave in `GameShell.tsx` is wrapped in a `try/catch` that
  silently ignores quota errors. Three large sessions plus the ~5 MB origin quota is not a
  comfortable margin — if you raise the snapshot rate or session length, verify the backup still
  writes rather than assuming it did.
- The export is a client-side JSON download, so file size itself is not a constraint.

Snapshots are emitted on an **elapsed-time grid**, not per tick: a coarse or throttled tick
(a backgrounded primary window throttles `requestAnimationFrame`, which pauses the sim clock)
emits at most one catch-up snapshot rather than a burst.
