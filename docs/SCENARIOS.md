# Scenario Parameter Versions

> Looking for "what was true of the build we ran the study on" (lockouts, assistant accuracy,
> session flow)? That is [`STUDY_BUILD.md`](STUDY_BUILD.md), tagged `study-v1.0` in git. **This**
> file versions only the scenario *numbers* — speeds, fleet, arrival rates, mission mix. The
> `study-v1.0` build ships scenario set **v2.1**.
>
> **Drone failures stopped being a per-version scenario constant at `study-v1.3`.** Every version
> below (v1/v2/v2.1) used a per-mission precomputed schedule (`FAILURE_COUNT/GAP/JITTER/PROB_CONST`,
> same global constants across every scenario within a version) — `study-v1.3` replaced that
> mechanism entirely with a live per-tick, per-deployed-drone hazard (`FAILURE_RATE_PER_DRONE_SECOND`,
> also global across scenarios, currently 1/900). It's a build-level mechanism change (fixed a
> Blue-bias bug in the old schedule's selection RNG), not a scenario-tuning change, so it's tracked
> in [`STUDY_BUILD.md`](STUDY_BUILD.md) §10, not versioned here.

This file is the human-readable record of the scenario tuning constants used to collect study
data. Every session also embeds these values in its `session_start` event (see
[`EVENT_LOGGING.md`](EVENT_LOGGING.md)), so any log is self-describing; this file exists to make
the version boundaries and their participant associations explicit, and to explain *why* each
version changed.

All constants live in `src/utils/missionGen.ts` unless noted. Difficulty was tuned with the
`sim/*.mts` harnesses (`achievability.mts`, `engine.mts`, `whatif.mts`, `demand.mts`).

---

## v1 (pilot)

> **Participant P-1333** (`logs/Study_1/study_P-1333_none_42.json`, condition `none`, seed 42,
> sessions `strategic` → `tactical`) was collected under **v1**. **Do not pool P-1333 with v2+
> data** — the fleet speeds, failure rate, arrival rates and mission-size mix all differ.

### Fleet & speeds
| Type | Speed (units/s) | Study fleet | Tutorial fleet |
|------|-----------------|-------------|----------------|
| Blue ("Fast")   | 9.0 | 11 | 6 |
| Red ("Lifter")  | 6.8 | 11 | 6 |
| Green ("Camera")| 5.4 | 11 | 6 |

Blue/Green speed spread: **1.67×**. Tutorial exposed raw `units/s` numbers to participants.

### Failure schedule
`FAILURE_COUNT_CONST = 2`, `FAILURE_GAP_CONST = 60`, `FAILURE_JITTER_CONST = 30`.
**All scheduled failures fire** (no inclusion gate) → **2.0 failures/mission**. Failure 1 ≈ 30–60 s
after arrival, failure 2 ≈ 90–120 s.

### Arrivals & mission mix
Mean inter-arrival `LAMBDA` (s) and category weights `[A,B,C,D,E]`:

| Complexity | LAMBDA | CATEGORY_WEIGHTS |
|------------|--------|------------------|
| balanced   | 65 | `[20,30,28,17,5]` |
| strategic  | 38 | `[40,38,16,5,1]` |
| tactical   | 90 | `[5,13,28,38,16]` |
| full       | 50 | `[5,15,28,32,20]` |
| quick      | 42 | `[35,30,20,12,3]` |

Archetype weights `[blue,red,green,mixed] = [35,28,22,15]`. Session duration 480 s (arrivals stop
at 420 s).

### Task rules (unchanged in v2)
- `TASK_PRIMARY`: T1 `1B` · T2 `2B` · T3 `2R+1G` · T4 `1R+2G` · T5 `1B+1R+1G`
- `TASK_SUBSTITUTE`: T1 `null` · T2 `1B` · T3 `1R+1G` · T4 `1R+1G` · T5 `null`
- `TASK_BASE_TIME` (s): `{1:10, 2:15, 3:25, 4:30, 5:45}`
- `TASK_SUB_BASE_TIME` (s): `{1:10, 2:38, 3:62, 4:75, 5:45}`
- `TASK_WEIGHT`: `{1:10, 2:20, 3:30, 4:40, 5:50}`
- `CATEGORY_PENALTY_RATE`: `{A:0.05, B:0.10, C:0.15, D:0.25, E:0.40}`

### Measured v1 load (analytic demand model, drone-seconds demand ÷ supply)
Travel is ~77% of all demand in every scenario.

| Scenario  | Blue util | Red util | Green util | Total |
|-----------|-----------|----------|------------|-------|
| tactical  | 31% | 40% | 44% | 38% |
| balanced  | 34% | 43% | 47% | 41% |
| strategic | 48% | 58% | 64% | 57% |
| full      | 57% | 71% | 79% | 69% |

**Known problems (motivating v2):** per-colour demand runs Green > Red > Blue everywhere (Blues
idle, Green the bottleneck), and Strategic carries ~1.5× the total load of Tactical rather than
matching it.

---

## v2 (current)

Goals: equal per-colour demand within each scenario; equal total demand across Tactical and
Strategic (identities preserved); ~25% fewer failures; faster + compressed travel; no raw speed
units in the tutorial; a competent operator still meaningfully challenged.

### What changed vs v1
| Parameter | v1 | v2 |
|-----------|----|----|
| `ASSET_SPEED` | 9.0 / 6.8 / 5.4 (spread 1.67×) | **11.0 / 10.0 / 9.0** (spread 1.22×) |
| Archetype weights `[blue,red,green,mixed]` | `[35,28,22,15]` | **`[38,26,21,15]`** |
| `LAMBDA.tactical` | 90 | **78** (strategic 38, balanced 65, full 50 unchanged) |
| Failures | 2.0/mission (all fire) | **E[1.5]/mission** via `FAILURE_PROB_CONST = 0.75` gate |
| Tutorial | showed `9.0 units/s` etc. | qualitative "fastest / standard / slowest" only |
| Fleet | 11/11/11 | 11/11/11 (unchanged) |
| `TASK_*`, `CATEGORY_WEIGHTS`, penalties | — | unchanged |

The compressed speed spread removes Green's travel penalty (travel drops from 77% to ~70% of
demand), which alone collapsed the old Green > Red > Blue imbalance; the small blue archetype bump
finishes flattening it; the `LAMBDA.tactical` cut raises Tactical's (previously lighter) load to
match Strategic.

### Achieved metrics
Failure gate: **1.50 scheduled failures/mission** (6% of missions 0 / ~38% one / ~56% two).

Per-colour demand (`sim/demand.mts`, 400 seeds) — spread ≤ ~2 pts, parity ✅:

| Scenario  | Blue | Red | Green | spread | total | missions | tasks |
|-----------|------|-----|-------|--------|-------|----------|-------|
| tactical  | 44% | 46% | 46% | 1.9 pts | 46% | 7.3 | 32.6 |
| strategic | 49% | 49% | 48% | 1.3 pts | 49% | 12.7 | 37.0 |
| balanced  | 40% | 39% | 39% | 0.7 pts | 39% | 8.2 | 29.2 |
| full      | 60% | 61% | 61% | 0.9 pts | 61% | 9.7 | 43.6 |

Tactical/Strategic total-demand ratio = **0.93** (within ±10%). Tactical stays "few, big" (4.5
tasks/mission, λ 78) vs Strategic "many, small" (2.9 tasks/mission, λ 38) — identities intact.

Difficulty (`sim/engine.mts`, 80 seeds; `sim/achievability.mts`, 200 seeds):

| Scenario  | SMART completion | LEAN | greedy DES | per-colour ρ (balanced) |
|-----------|------------------|------|------------|--------------------------|
| tactical  | **84%** | 72% | 73% | ~0.42 |
| strategic | **83%** | 76% | 64% | ~0.46 |

A competent operator finds Tactical and Strategic **equally hard (~83–84%)** — the target
"appropriately difficult, between the v1 levels." They still *fail differently* for weak play:
Strategic overwhelms a naive operator via arrival queueing (max queue 3.1, p95 wait 108 s), while
Tactical punishes poor within-mission redundancy/planning — preserving the two decision-tier
identities. (Note: average ρ ≈ 0.42–0.46 reads "comfortable," but peak fleet use is 93–100% during
clusters, which is where the difficulty actually lives — SMART completion, not mean ρ, is the
governing difficulty measure here.)

### Re-tuning
`npx tsx sim/demand.mts` (fast colour-balance + parity loop) → `npx tsx sim/achievability.mts` and
`npx tsx sim/engine.mts --seeds=80` (difficulty). Adjust speeds/archetype for colour balance,
`LAMBDA`/`CATEGORY_WEIGHTS` for level + parity.

---

## Build tag `study-v1.0` (was `v2.1-logging4`) — tutorial + clock fixes (no scenario parameters changed)

`APP_VERSION` bump only; **no** scenario parameter moved, so all v2.1 calibration below still
stands and data collected under `v2.1-logging3` remains poolable. The build was renamed from
`v2.1-logging4` to `study-v1.0` when it was declared the study build — same numbers, and the
per-build decisions now live in [`STUDY_BUILD.md`](STUDY_BUILD.md). Recorded here because these
changes touch the reducer:

- **`MAX_TICK_GAP_MS` (2000 ms).** `elapsed` is wall-clock derived and the tick loop is driven by
  `requestAnimationFrame`, which the browser suspends when the primary window is hidden. The first
  frame back used to apply the whole gap at once, teleporting drones and completing tasks unseen.
  A single TICK now advances at most 2 s of simulated time and `sessionStartMs` absorbs the rest.
  The cap sits above every harness step size (250/500/1000 ms), and `sim/pilot-run.mts` reproduces
  its previous scores exactly.
- **`fixLockouts` is now one helper, `isFixLockouts()`, read everywhere.** It previously meant
  auto-fix inside the reducer while `Tutorial.tsx` read it the other way, and `session_start` logged
  the reducer's reading — so the log could contradict the behaviour.
- Tutorial session length is now 45 min (`TUTORIAL_SESSION_DURATION`) so the walkthrough cannot
  outlast its own clock. Study sessions are untouched.

### `fixLockouts` default → auto-fix (study decision, same build tag)

An omitted flag, the StartScreen checkbox, and a URL with no `fixLockouts` param now all mean
**auto-fix**: a scheduling deadlock is silently rerouted by the agent, every task still completes,
and the operator is never shown the "help needed" state. `?fixLockouts=0` opts back into it.

Rationale: only the operator can build a deadlock (agent plans are acyclic by construction), and
leaving it surfaced meant a participant could land in a red recovery state that the tutorial had to
spend a step warning them about. With auto-fix on, they cannot reach it, so the `lockout-explain`
step was removed. Recovery-from-lockout is therefore **not** an operator decision the study
measures; `lockout_detected` still logs (with `resolution: 'rerouted'`) so a participant who built
one is still identifiable in the data.

Scoring impact: none for any plan without a cycle, which is every plan the harnesses build —
`sim/pilot-run.mts` reproduces its previous scores exactly after being switched to `true`. For a
participant who does build a cycle the mission now completes instead of stalling, which is a
*difficulty* change relative to data collected before this flip; check the flag in `session_start`
before pooling such a session.

---

## v2.1 (current)

Two coupled changes: a workflow change that made missions slightly *easier*, and a small arrival-rate
bump to compensate. Task rules, speeds, fleet, failures, archetype/category weights are all unchanged
from v2 — **only `LAMBDA` changed** — so v2 and v2.1 remain broadly comparable, but the version bump is
recorded here for provenance.

### What changed vs v2
| Parameter | v2 | v2.1 |
|-----------|----|------|
| Workflow (`gameReducer.ts`) | Committed team waited at the hub until the tactical plan was confirmed, then flew out. | **On strategic allocation the committed team sets off toward the mission zone immediately** and loiters at the zone edge until a tactical plan is confirmed (drones assigned from their current position). Reserve drops the moment they are committed. |
| `LAMBDA` | balanced 65 · strategic 38 · tactical 78 · full 50 | **balanced 62 · strategic 37 · tactical 75 · full 48** (≈5% more arrivals) |

Rationale: pre-positioning the drones during the tactical-planning window removes the post-confirm
hub→zone travel from the critical path, shortening completion times and freeing drones sooner — a
throughput easing not captured by the auto-operator harnesses (they confirm tactical instantly). The
uniform-ish `LAMBDA` cut restores the intended load. A larger (~8%) cut was rejected because strategic
is far more arrival-sensitive than tactical and it broke the tac≈strat difficulty parity.

### Achieved metrics (with the v2.1 workflow active in the harnesses)
Per-colour demand (`sim/demand.mts`, 300 seeds) — spread ≤ ~3 pts, parity ✅:

| Scenario  | Blue | Red | Green | spread | total | missions | tasks |
|-----------|------|-----|-------|--------|-------|----------|-------|
| tactical  | 45% | 47% | 47% | 2.9 pts | 46% | 7.3 | 32.9 |
| strategic | 51% | 52% | 50% | 1.5 pts | 51% | 13.1 | 38.1 |
| balanced  | 41% | 41% | 41% | 0.3 pts | 41% | 8.5 | 30.0 |
| full      | 61% | 64% | 62% | 2.3 pts | 62% | 9.9 | 44.4 |

Tactical/Strategic total-demand ratio = **0.91** (within ±10%).

Difficulty (`sim/engine.mts`, 80 seeds), SMART (redundant/Aggressive) completion. The numbers below
are **after the failure-freeze bug fix** (see note): a mid-mission drone failure used to leave the
task half-staffed with its remaining drones stuck on it forever (greedy replan only fills empty
tasks) and the manual recovery planner offered on-mission drones that the confirm handler then
rejected — both froze missions and depressed completion. With that fixed, missions no longer stall:

| Scenario  | v2.1 SMART | mean completion |
|-----------|-----------|-----------------|
| tactical  | **89%** | 103 s |
| strategic | **87%** | 95 s |
| balanced  | 88% | 95 s |
| full      | **80%** | 120 s |

Tactical ≈ Strategic parity preserved (~87–89%). Completion sits a little higher than the old
~83% target because that figure was measured with the freeze bug artificially failing ~1 mission in
6; the SMART auto-operator also over-allocates and recovers perfectly, so real operators land lower.

**Failure-freeze fix (`gameReducer.ts`):** on a non-graceful drone failure the task's *remaining*
drones are now released back to loitering and the task's `assignedAssetIds` cleared, so it is cleanly
re-coverable (greedy replan re-covers it; a half-staffed pending task no longer freezes). And
`CONFIRM_FAILURE_RECOVERY` now accepts the mission's own deployed (loitering) drones — the exact pool
the recovery planner offers — instead of only hub-reserve `available` drones.
