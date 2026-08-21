# Study build `study-v1.0` — what it is, and every decision baked into it

**Git tag: `study-v1.0`.** `git show study-v1.0` is the exact code any such session ran.
**In the data:** every session's first event is `session_start`, and it carries
`appVersion: "study-v1.0"`.

> Not to be confused with the **scenario parameter-set** versions (v1 / v2 / v2.1) in
> [`SCENARIOS.md`](SCENARIOS.md) — those version the numbers (speeds, fleet, arrival rates), this
> versions the whole build. `study-v1.0` ships scenario set **v2.1**.

This file exists so that months from now a question like *"did the build we used for these runs have
lockouts?"* has a definitive answer instead of an inference. Each decision below says what the build
does, why, and **how to confirm it from a log file alone** — the log is the authority, this file is
the explanation. If you change any of these, tag a new version and add a section here; do not edit
the `study-v1.0` section, or logs will start disagreeing with it.

Related: [`SCENARIOS.md`](SCENARIOS.md) for the scenario parameter set and its tuning history,
[`EVENT_LOGGING.md`](EVENT_LOGGING.md) for the full event schema, `CLAUDE.md` for the mechanics.

---

## The short answers

| Question | `study-v1.0` answer | Check in the log |
|---|---|---|
| Could a participant hit a scheduling deadlock (lockout)? | **No.** Auto-rerouted silently; every task still completes. | `session_start.fixLockouts === true`; any `lockout_detected` has `resolution: "rerouted"` |
| Were the assistants ever wrong? | **No.** Both run at ε = 0 — every card and plan is optimal. | `session_start.epsilonStrategic === 0` and `epsilonTactical === 0` |
| So what goes wrong during a session? | **Drone failures only** (plus whatever the operator does). | `drone_failure` events; `recovery_opened` |
| Was the 2×2 accuracy manipulation running? | **No.** Single condition, logged as `none`. | `session_start.condition === "none"` |
| In-session trust/workload probes? | **No.** The modal is not mounted anywhere, so none is ever shown. | no `trust_probe` events exist |
| How many sessions, how long? | **2 × 8 min** (480 s) on the participant-study path. | `session_start.numSessions`, `sessionDuration` |
| Which scenarios? | Session 1 **Strategic Heavy**, session 2 **Tactical Heavy** (defaults; changeable on the start screen). | `session_start.complexity` per session |
| Tactical planner style? | **plan-all** (confirm the whole sequence once). | `session_start.tacticalMode === "plan-all"` |
| Did the tutorial teach any of this? | 48 steps, manual workflow first, both assistants after. No lockout lesson. | tutorial runs under `participantId: "DEMO"`, `tutorialMode` |
| If a mission is abandoned, is its work lost? | **No** (build ≥ `study-v1.2`). The remainder is re-queued as a residual mission and is usually finished. | `task_requeued` events + a `mission_arrived` with `isResidual: true`; **not** `task_failed` |
| How many points is a completed task worth? | **Build ≥ `study-v1.3`: double `study-v1.0`–`v1.2`** (20/40/60/80/100 by task type, not 10/20/30/40/50). Penalty-per-second is unchanged. | `session_start.taskWeight` |
| How are drone failures generated? | **Build ≥ `study-v1.3`:** a live per-tick hazard, uniform per second per deployed drone, regardless of type or mission. **`study-v1.0`–`v1.2`:** a per-mission precomputed schedule whose selection RNG was Blue-biased. | `session_start.failureRatePerDroneSecond` (v1.3+) vs `failureCount`/`failureGap`/`failureJitter`/`failureProb` (pre-v1.3) |
| Is there a pre-study AI-attitude survey? | **Yes, build ≥ `study-v1.3`:** AIAS-4 + two bespoke Likert blocks, before session 1. | `demographics` keys prefixed `aias_`/`verif_`/`deleg_`; absent entirely pre-`v1.3` |

---

## Decisions in full

### 1. Lockouts are auto-fixed and cannot be encountered

A chained plan *can* deadlock (Fast chained task1→task2 while Lifter is chained task2→task1: each
task waits on a drone waiting on the other task). Only the **operator** can build one — the agent
routes every drone in a single global task order, so its plans are acyclic by construction.

`fixLockouts` defaults to **true** in this build: the live detector reroutes the conflicting chains onto
one canonical order, every task still completes, **nothing fails and nothing is surfaced**. The
participant never sees a "Lockout — help needed" state, so recovering from a lockout is *not* an
operator decision this build measures.

- Set by: `isFixLockouts()` in `src/utils/config.ts` (`fixLockouts !== false`), the start screen's
  "Fix lockouts" checkbox (ticked by default), `?fixLockouts=0` to opt out.
- Still fully implemented and tested: `scripts/test-scheduling-deadlock.ts` covers both branches.
- **Consequence for the tutorial:** the `lockout-explain` step was removed — warning participants
  about a state they cannot reach is noise. If a future arm turns the flag off, put it back.
- **Consequence for the data:** a participant who builds a cycle is still visible
  (`lockout_detected`, `resolution: "rerouted"`), but their mission completes rather than stalling.
  Sessions recorded *before* this flip are not comparable on that axis — check `fixLockouts`.

### 2. Both assistants are perfect (ε_S = ε_T = 0)

The start screen's accuracy pickers default to 100 % / 100 %. Nothing in a `study-v1.0` session is
deliberately wrong: strategy cards show exactly the team that gets deployed, and the tactical plan
covers every task.

The noise machinery still exists — `conditionToEpsilons()`, the ε_S perturbation of *displayed*
counts in `copilot.ts`, and the ε_T "silently drop one task" path in `APPLY_STRATEGIC` — it is
simply never triggered at ε = 0. The tutorial runs at 0 too, deliberately: priors form during
training, so a 10 %-wrong assistant there would confound the manipulation.

Verify: `scripts/test-strategy-deploys-what-it-shows.ts` pins card == true == deployed at ε = 0.

### 3. Drone failures are the only scripted adversity

Per mission the generator schedules up to `FAILURE_COUNT_CONST = 2` failures, each included with
probability `FAILURE_PROB_CONST = 0.75` (≈ 1.5 expected), at least `FAILURE_GAP_CONST = 60 s` apart
with `FAILURE_JITTER_CONST = 30 s` of jitter. A failure whose colour-section deadline has already
passed is a graceful exit; otherwise the task reverts to pending and the mission asks for help.
Recovery may draw **only** on drones already on that mission, never the hub reserve — which is what
makes "abandon" a real option.

### 4. Scenario parameters: set v2.1

Uniform **11 Fast / 11 Lifter / 11 Camera** fleet in every study scenario — difficulty comes only
from mission size (`CATEGORY_WEIGHTS`) and arrival rate (`LAMBDA`: strategic 37 s, tactical 75 s,
balanced 62 s, full 48 s). Speeds 11 / 10 / 9. Task rewards 10–50, penalty 0.05–0.40 per second by
category, charged every 15 s. Full tuning history and the achievability evidence are in
[`SCENARIOS.md`](SCENARIOS.md); the whole set is dumped into every `session_start`, so a log can be
replayed without this repo.

### 5. Session flow

Participant-study button → demographics → session 1 (Strategic Heavy) → survey → 30 s between-screen
→ session 2 (Tactical Heavy) → survey → done → download JSON.

Surveys are **NASA-TLX + trust (strategic) + trust (tactical)** after each session. The TAM scales
are configured for session 3 only, so **the 2-session flow never collects them** — deliberate, but
worth remembering before looking for TAM data that isn't there.

### 6. Clock and timing

`elapsed` is wall-clock derived, and the tick loop is `requestAnimationFrame`, which the browser
suspends when the primary window is hidden. `MAX_TICK_GAP_MS = 2000` caps how much simulated time
one tick may advance, and `sessionStartMs` absorbs the remainder — so hiding the window **pauses**
the session instead of fast-forwarding it. The primary window must still stay visible; the map
window may be on a second screen.

### 7. Tutorial

48 steps (`src/utils/tutorialSteps.ts`), 45-minute clock so it cannot outlast itself. It teaches the
manual workflow first — allocate, plan, chain, deploy, recover from a failure by hand — and only
then introduces the assistants; the planner's "Suggest" button is hidden until that lesson. Two
scripted failures: one the operator can recover from, one they cannot (so the abort lesson is
truthful). Fleet is 6/6/6 rather than 11/11/11, to be easier to count while learning.

### 8. `study-v1.1` — even failure targeting, and strategic commitments actually deploy in full

Found while auditing a pilot log (`Ramis` / P-1622) where drone failures looked Blue-heavy and a
strategic card's promised drone count didn't match what showed up in the tactical planner. Both
were real, reproducible bugs in `APPLY_STRATEGIC`/TICK, not artifacts of that session:

- **Failure targeting was implicitly biased toward Blue.** The scheduled-failure picker
  (`gameReducer.ts` TICK step 1b) drew uniformly from drones that were already `executing` a task,
  excluding anything still `traveling`. Blue is the fastest type and is the sole/primary type on
  the short T1/T2 tasks, so it reached "executing" well before the 30–60s failure-check window
  while slower Red/Green (assigned to longer-travel T3/T4) were often still in transit and
  therefore ineligible. Net effect in one pilot session: 11 of 13 failures were Blue against a
  uniform 11/11/11 fleet. **Fixed:** the pool is now every drone with `status === 'deployed'` on
  the mission — loitering, travelling, or executing all count equally, so failure chance is
  uniform per drone and proportionate only to the number currently committed. A drone that fails
  before ever being dispatched to a task (still loitering, e.g. an unused Aggressive/Conservative
  buffer spare) logs `drone_failure` with `taskId`/`taskType` both `null` and needs no recovery —
  see `EVENT_LOGGING.md`. Also fixed in the same pass: the "release co-assigned drones back to
  loitering" step (same TICK block) used the stale `asset.position` snapshot instead of
  `interpolateAssetPosition`, which only happened to be correct before because a released drone was
  always one that had already physically arrived at the task; now that a still-travelling drone's
  co-assignee can be released too, the live interpolated position is required.
- **A strategy card's promised team didn't fully deploy.** `APPLY_STRATEGIC` (agent branch) built
  `dronePool` — the set of drones that actually launch and become assignable in the tactical
  planner — from `assignments.flatMap(a => a.assetIds)`, i.e. only drones `greedyAssign` put on a
  task. But `greedyAssign` reuses a drone across tasks as it frees up, so a composition's "spare
  per type" buffer (Aggressive's card literally says "at least one spare drone per type deployed as
  a failure buffer") could go entirely unused by any task and silently never make it into
  `dronePool` — never launched, never shown in the tactical planner, contradicting both the card
  and `reserveAfter`. Confirmed in the pilot log: 9 of 14 agent-suggested strategic choices in one
  session under-delivered by exactly the unused buffer drone(s) (mostly the second committed Blue).
  **Fixed:** the agent branch now always unions in the full committed composition, the same thing
  the manual branch already did correctly (manual choices in the log never showed this mismatch).
  Pinned by `scripts/test-strategy-deploys-what-it-shows.ts`.
- **Consequence for the data:** both bugs were present in every `study-v1.0` session, so real
  redundancy delivered was sometimes less than what the strategy card/UI claimed, and failures
  under-sampled Red/Green. `sim/engine.mts` (20 seeds/scenario) shows the fix is a net positive for
  achievable score/completion (e.g. balanced SMART 514→554, strategic SMART 542→630) — expected,
  since previously-phantom buffer drones now actually provide cover. **Do not pool `study-v1.0` and
  `study-v1.1` sessions on redundancy-use or per-colour-failure axes without accounting for this;
  check `session_start.appVersion` before pooling.**

### 9. `study-v1.2` — abandonment is logged as a transfer, not a loss

Found by auditing logs against the reducer's own final state (`sim/log-audit.mts`, added in this
pass). The event stream systematically over-reported failure around **abandonment**, which is the
one operator action whose whole point is that the work survives.

- **Re-queued tasks were logged as failures.** `ABANDON_MISSION` fired a `task_failed`
  (`reason: 'mission_abandoned'`) for every incomplete task — but those tasks are precisely the
  ones copied into the residual mission (`<parent>-R`) and re-queued, and they are usually
  completed later. A live session showed three tasks logged failed for 130 "forgone" points, then
  all three completing under the residual two minutes later. **Fixed:** carried work now emits
  `task_requeued` (naming the `residualTaskId` that inherits it) and `task_failed` fires only for
  work with no residual copy — which, under current residual rules, is never.
- **The residual mission was never announced.** It was appended to `state.missions` with no
  `mission_arrived`, so its `strategic_choice` / `tactical_confirmed` / `task_completed` events
  referenced a mission the log never introduced, and any denominator built from `mission_arrived`
  omitted it. **Fixed:** residuals are announced through the same `missionArrivedPayload()` as
  every other arrival, flagged `isResidual: true` with `parentMissionId`. **Analysis must exclude
  residual arrivals from "what arrived"** — their reward was already counted under the parent.
  `scripts/study_report.py` does this.
- **Both copies of the same outstanding work accrued penalty.** The abandoned parent kept billing
  its carried tasks against live `elapsed` while the residual billed its copies too. **Fixed:** an
  abandoned mission stops accruing at `abandonedAt`; the residual takes over from that instant.
- **Abandoned missions lost their status at the buzzer.** `endSession` overwrote them to
  `completed`/`failed` (and swept their carried tasks into `session_ended` failures), so the final
  state contradicted the `mission_abandoned` event. **Fixed:** abandoned missions are left alone.
- **`ACCEPT_RECOVERY` logged recoveries that never happened** — the `failure_recovery` event was
  emitted before the composition guard that can reject the redistribution, and
  `buildRecoveryOptions` marked an option `feasible` on a weaker test than that guard, so a
  rejected click still produced a "repaired" record and the operator could click again. Dead in
  the shipped UI (no component posts that action), but **`sim/engine.mts` drives it** — one seed
  emitted 1310 phantom `failure_recovery` events for 7 real failures, so treat pre-v1.2 harness
  recovery counts as unusable. **Fixed:** log only on the far side of the guard; `feasible` now
  uses the same predicate.
- **Interpretability, not a bug:** `task_failed` gained `missionWasAllocated` /
  `missionStatusBefore`, and `session_ended` gained a `taskOutcomes` ledger
  (`completed`/`failed`/`requeued`/`failuresByReason`/`failedOnNeverAllocatedMissions`). The
  largest bucket of failures in any session is tasks of missions the operator never allocated,
  failed en masse at the buzzer; that is a triage signal, not lost execution, and it no longer
  needs a join against `strategic_choice` to see.
- **Consequence for the data:** `study-v1.0`/`v1.1` logs **over-count `task_failed`** by one per
  re-queued task and **under-count `mission_arrived`** by one per abandonment; their penalty (and
  therefore score) is inflated for any session containing an abandonment, by the parent's rate
  from `abandonedAt` to the buzzer. Sessions without an abandonment are unaffected on every axis.
  To pool old sessions, drop `task_failed` with `reason: 'mission_abandoned'` and treat any
  `<id>-R` mission as an unannounced arrival; the penalty difference cannot be recovered from the
  log alone — re-run the seed under v1.2 if you need it.
- Pinned by `scripts/test-abandon-logging.ts`; `sim/log-audit.mts` reports `ISSUES: 0` across
  balanced/tactical/strategic/full at 10 seeds each.

### 10. `study-v1.3` — friendlier scores, an honest failure model, and a pre-study AI-attitude survey

Found while auditing a pilot log (`SamHJ` / P-6155): scores clamp to 0 whenever penalty outruns
completion points (session 2 did), and drone failures were still heavily Blue-biased (17/21 across
both sessions, vs. a 33–48% Blue share of committed drones) despite `study-v1.1` claiming to fix
exactly this. Three changes:

- **Doubled `TASK_WEIGHT`** (`missionGen.ts`: 10/20/30/40/50 → 20/40/60/80/100) so completed-task
  points, and therefore score headroom, roughly double. Safe because `computePenaltyAccrued()`
  charges each task a *ratio* of `TASK_WEIGHT[type]/totalWeight` against a fixed
  `CATEGORY_PENALTY_RATE` — scaling every weight by the same factor leaves that ratio, and so
  penalty-per-second, unchanged. Confirmed via `sim/engine.mts`: SMART-operator task-completion %
  is unchanged (strategic/tactical both still land at 83%, matching pre-v1.3 runs) — only the
  score numbers moved. **Consequence for the data:** don't compare raw `score`/`completionPoints`
  across the `study-v1.2`/`v1.3` boundary; percentages (`tasksCompleted/tasksTotal`,
  `reward_capture`) are fine to pool.
- **Replaced the drone-failure model.** The old scheme precomputed up to `FAILURE_COUNT_CONST=2`
  failure *times* per mission at generation time (`missionGen.ts`), fired by picking a random
  currently-`'deployed'` drone via
  `new SeededRNG(seed ^ mission.id.charCodeAt(1) ^ 0xfa11 ^ droneFailuresFired)`. Root cause of the
  Blue bias: `mission.id.charCodeAt(1)` is the first digit of a 3-digit mission number, which is
  `'0'` for every mission in any realistic session (<100 missions) — the seed barely varied, so the
  "random" pick collapsed to nearly the same draw for every mission's Nth failure, and because Blue
  drones (`B01`–`B11`) sit first in the asset array, a low-index draw reliably landed on Blue.
  **Fixed:** every currently-`'deployed'` drone across every `'active'` mission now independently
  rolls a failure **every tick** with probability `FAILURE_RATE_PER_DRONE_SECOND × dt`
  (`FAILURE_RATE_PER_DRONE_SECOND = 1/900`, i.e. ≈1 failure per continuously-deployed drone every 15
  minutes), seeded per (drone, tick) via `hashId(droneId)` (a real full-string hash, not a single
  `charCodeAt`) combined with the tick timestamp — so there is no schedule and no array-position
  dependency left to bias anything. Total failures now scale with actual drone-seconds deployed
  (utilisation), which is the correct read of "why did session 2 have more failures than session
  1?" — more/longer-deployed drones, not mission count or a broken picker. Calibrated via
  `npx tsx sim/engine.mts --seeds=40`: at this rate the SMART operator completes 83% of tasks in
  both study scenarios (strategic 83%, tactical 83%), matching the pre-existing 83–85% target.
  Colour balance re-checked with a 40-session sweep: Blue/Red/Green failures came out
  709/538/529 — no longer overwhelmingly Blue; the residual lean toward Blue reflects Aggressive/
  Conservative strategies committing more Blue drones on average (more exposure), which is now the
  *correct* thing driving the count, not an RNG artifact. `mission_arrived.scheduledFailureTimes`
  and `session_start.failureCount/failureGap/failureJitter/failureProb` are gone, replaced by
  `session_start.failureRatePerDroneSecond`. The residual mission's separate ad-hoc failure
  scheduler was also removed — a residual is `'active'`/`'queued'` like any other mission, so the
  single ambient per-tick check now covers it for free.
  **Consequence for the data:** don't compare `drone_failure` counts, or failures broken down by
  drone colour, across the `study-v1.2`/`v1.3` boundary — the generating process is entirely
  different, not just re-tuned. `sim/log-audit.mts` reports `ISSUES: 0` (`drone_failure` events ==
  `droneFailuresFired` in state) for both study scenarios at 10 seeds each under the new model.
- **Added a pre-study AI-attitude survey** to the existing demographics questionnaire
  (`DemographicsForm.tsx`), before session 1 alongside the existing "About you" and comprehension-
  check sections:
  - **Block A — AIAS-4** (Grassini, 2023; validated, verbatim, unidimensional, no reverse items),
    10-point scale (`aias_*` keys), preceded by a short neutral "what counts as AI" framing
    paragraph (replicating the original administration, so scores stay comparable to published
    norms — and it doubles as neutral framing that doesn't cue the Strategic/Tactical Assistant
    manipulation).
  - **Block B — Verification propensity** (bespoke), 7-point scale, 6 items (`verif_*`, 3
    reverse-keyed: `verif_comfortable_unreviewed`, `verif_happy_unsupervised`,
    `verif_reliable_no_check`) plus one optional item (`verif_hard_to_detect_errors`) kept out of
    the composite — it measures perceived error-detectability, a moderator, not propensity to check.
  - **Block C — Delegation boundary** (bespoke), 7-point scale, 5 items (`deleg_*`, one
    reverse-keyed: `deleg_urgent_better_than_nothing`). Items 1–2 map onto the Strategic
    (recommend) vs. Tactical (decide) Assistant contrast.
  - All responses are logged **raw** (not reverse-scored at collection time) in
    `demographics`/`SUBMIT_DEMOGRAPHICS`, matching every other event in this build — reverse-key
    and score at analysis time. `demographics.gender` (already collected) is available as the
    AIAS-4 gender covariate the validation paper found significant.
  - **Consequence for the data:** `study-v1.0`–`v1.2` sessions have no `aias_*`/`verif_*`/`deleg_*`
    keys in `demographics` at all — absence, not a null/blank answer.

`git show study-v1.2` is the exact code any pre-`v1.3` participant session ran (the boundary was
tagged retroactively when this work started, since no tag had existed for it before).

---

## Reproducing a session from its log

`session_start` is a full parameter dump: seed, complexity, fleet, speeds, task compositions and
timings, task weights, penalty rates, category weights, arrival λ, failure-schedule constants,
assistant ε values, `fixLockouts`, `tacticalMode`, plus `appVersion`, `userAgent` and viewport.
Same seed + same `appVersion` ⇒ same session. Every event also carries a study-wide `seq`, a
session-relative `timestamp`, a real `wallClock`, and a `sessionId`.

## If you change something

1. Bump `APP_VERSION` in `src/store/gameReducer.ts` (e.g. `study-v1.4`).
2. Add a section here describing what changed and what it means for pooling old data.
3. Commit, then `git tag -a study-v1.4 -m "..."` so the tag and `appVersion` agree.

Existing tags: `git tag -l` · what a tag means: `git show study-v1.0 --stat` (the annotation
summarises the build) · what changed since: `git log study-v1.0..HEAD --oneline`.
