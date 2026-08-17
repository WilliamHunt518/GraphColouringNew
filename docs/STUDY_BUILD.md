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

---

## Reproducing a session from its log

`session_start` is a full parameter dump: seed, complexity, fleet, speeds, task compositions and
timings, task weights, penalty rates, category weights, arrival λ, failure-schedule constants,
assistant ε values, `fixLockouts`, `tacticalMode`, plus `appVersion`, `userAgent` and viewport.
Same seed + same `appVersion` ⇒ same session. Every event also carries a study-wide `seq`, a
session-relative `timestamp`, a real `wallClock`, and a `sessionId`.

## If you change something

1. Bump `APP_VERSION` in `src/store/gameReducer.ts` (e.g. `study-v1.1`).
2. Add a section here describing what changed and what it means for pooling old data.
3. Commit, then `git tag -a study-v1.1 -m "..."` so the tag and `appVersion` agree.

Existing tags: `git tag -l` · what a tag means: `git show study-v1.0 --stat` (the annotation
summarises the build) · what changed since: `git log study-v1.0..HEAD --oneline`.
