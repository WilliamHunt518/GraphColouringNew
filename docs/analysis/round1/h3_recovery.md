# H3 · Recovery: does Suggest predict fewer abandonments within a person, and what happens when Suggest fails?

Script: `scripts/analysis_round1/h3_recovery.py` (prints every number below; writes nothing).
Data: `Results/Participants/P*.json`, P09 excluded → 33 participants, 194 recovery episodes (all
`recoveryReason = drone_failure`: `fixLockouts` was on in every session, so lockouts never opened a recovery).

## 1 · Primary test (confirmatory)

GEE logit, binomial, exchangeable within participant (`build_findings_synthesis.gee`):
`abandoned ~ usedSuggest + personMean(usedSuggest)`. Sample: recovery episodes that were **fixable with
drones already on the mission** and ended in recovery or abandonment. *usedSuggest* = Suggest pressed
(`tactical_suggest_used`, `recoveryMode: true`) at any point in the episode.

| Cohort | Within-person OR (usedSuggest) | 95% CI | p | n episodes / people |
|---|---|---|---|---|
| **All 33 (primary)** | **0.40** | **0.21 – 0.76** | **0.005** | 164 / 32 |

Between-person term (person-mean Suggest use): OR 1.05 (0.20–5.39), p = .96. The association is
within a person. People who use Suggest more do not abandon less overall; the same person abandons
less on the failures where they press it.

**Verdict: SUPPORTED** under the pre-registered criterion (within-person OR < 1, interval excludes 1).
Holm correction across the 10 primaries is the supervisor's job. Raw p = .005.

Power: SE(log OR) = 0.32, so the smallest protective OR detectable at 80% power is about 0.40. The
estimate sits right at that boundary.

**Before relying on this, see R13 in §3. It changes the interpretation.**

How I defined "fixable" (a judgement call): the pre-registration says "fixable with drones already on
the mission (`coverable()`)". `coverable()` appears in `study_analysis.py` only in the busy-inclusive
check (`feasibleWithBusy`). I therefore used coverable over **every live mission drone at the failure,
idle or executing**. That check turned out to have a bug (see §6), so I used a corrected, time-local
version that rebuilds drone membership from `state_snapshot` and `task_completed` intervals. The
logged idle-only flag (`feasibleWithOnMissionDrones`, the one behind the page's 9/49 vs 23/45 split)
is robustness check R1. It gives the same answer.

## 2 · Sensitivity: v1.12+ (n = 24 people)

| Cohort | OR | 95% CI | p | n |
|---|---|---|---|---|
| v1.12+ | 0.29 | 0.12 – 0.68 | 0.005 | 99 episodes / 23 people |

Descriptives on the primary sample:

| Sample | Suggest used: abandoned | Not used: abandoned |
|---|---|---|
| All 33 | 14/70 (20%) | 34/94 (36%) |
| v1.12+ | 11/52 (21%) | 25/47 (53%) |

On the logged idle-only flag, v1.12+ reproduces the page's 9/49 vs 23/45 exactly. On all 33 it gives
11/66 vs 29/89.

Only 17 of 32 people (8 of 23 in v1.12+) have fixable episodes both with and without Suggest. The
within-person estimate rests on them.

## 3 · Secondary results (exploratory)

### 3a · Robustness of the primary

| # | Specification | OR (95% CI), p, n |
|---|---|---|
| R1 | fixable = logged idle-only flag | 0.42 (0.20–0.89), .024, 155 |
| R1b | same, v1.12+ | 0.23 (0.10–0.55), .001, 94 |
| R2 | fixable = original `feasibleWithBusy` | 0.36 (0.20–0.64), .001, 164 |
| R3 | unresolved episodes counted as not recovered | 0.32 (0.17–0.57), <.001, 173 |
| R4 | + run, scenario | 0.43 (0.22–0.82), .011 |
| R5 | + run, scenario, time left, idle-fixable, category | 0.46 (0.22–0.97), .040 |
| R6 | v1.5+ builds only (current Suggest pool) | 0.43 (0.22–0.86), .016, 131 |
| R7 | pooled (no person mean): total association | 0.41 (0.23–0.72), .002 |
| R9 | conditional (fixed-effect) logit, all | 0.32 (0.09–1.11), .073, 83 episodes / 13 informative people |
| R9 | conditional logit, v1.12+ | 0.14 (0.02–1.20), .072, 5 people |
| R16 | bias-reduced (Mancl–DeRouen) SE, all / v1.12+ | 0.40 (0.21–0.79), .008 / 0.29 (0.11–0.77), .013 |
| R17 | person-level paired (17 people with both kinds of episode) | lower with Suggest 10, higher 3, equal 4; Wilcoxon p = .030 (v1.12+: 5/0/3, p = .042) |
| R12 | Suggest **gave a plan** vs pressed but **gave nothing** | gave a plan: OR 0.29 (0.11–0.79), .015 (11/59 abandoned); gave nothing: OR 0.90 (0.24–3.39), .87 (3/11) |
| **R13** | **only episodes with any attempt (a drag or a Suggest press)** | **0.94 (0.27–3.22), .92, 137** · v1.12+ 0.74 (0.09–5.86) |
| R15 | Suggest as the *first* move (before any drag) | 0.64 (0.29–1.44), .28 |

**R13 is the important one.** Attempt type × outcome on the primary sample:

| Attempt | Recovered | Abandoned |
|---|---|---|
| Suggest only | 42 | 14 |
| Suggest + drags | 14 | 0 |
| Drags only | 60 | 7 |
| Nothing | 0 | 27 |

A recovery cannot be deployed without putting a drone on the broken task (the failed task is emptied
at the failure), so all 27 no-attempt episodes are abandonments, and all of them fall in the
"no Suggest" arm.

Against operators who fixed failures **by hand**, Suggest users abandon no less: 14/70 (20%) vs
7/67 (10%), within-person OR 0.94. The Suggest effect is therefore an effect of **trying versus not
trying**. Suggest is the most common way of trying, and the episodes where it produced a plan carry
the effect (R12).

The primary is supported as specified. It should not be read as "Suggest makes recoveries succeed
compared with doing them by hand". The supportable reading is "pressing Suggest marks the operator
engaging with the failure rather than abandoning it untried".

### 3b · Every recovery Suggest press, classified

Suggest's output is not logged, so I rebuilt it per press from the code. `computeRecoverySuggestion`
plans, without consume-once, from mission drones not executing a task (from v1.5; before v1.5 it used
idle drones only). It fills only the pending tasks the live planner leaves short, so it covers a short
task if and only if `coverable(task, pool)`. Membership and executing status at each press come from
the latest `state_snapshot` plus exact `task_completed`/`task_failed` execution intervals. Planner
state comes from the recovery drags.

Validation:

- The rebuilt idle pool matches the logged `onMissionDroneIds` in 184/194 episodes.
- The rebuilt idle-fixable flag matches the logged flag in 190/194.
- In v1.6+ recovered episodes with a press, `wasAgentSuggested` agrees with "Suggest returned a plan"
  in 51/53. In the other 2 it was rebuilt as non-empty but the flag was false: P19, where Suggest and
  the deploy happened in the same tick, and P20, a possible Reset.
- There is no case of the flag being true while the rebuild says Suggest returned nothing.

97 recovery Suggest presses from 26 people, in 79 episodes:

| Result | n | Next action | Episode outcome |
|---|---|---|---|
| solved (every short task covered) | 58 | deploy 41, retry 8, abandon 7, edit 2 | 47 recovered / 11 abandoned |
| partial | 3 | deploy 1, retry 1, abandon 1 | 1 / 2 |
| failed ("No workable plan") | 24 | abandon 11, edit by hand 7, retry 6 | 9 / 15 |
| no-op (plan already covered) | 12 | – | – |

Of the 27 failed or partial presses:

- **16 were correct.** Not even the busy drones could have covered the task, and all 16 episodes
  ended abandoned.
- **11 were genuine agent errors (the blind spot).** The fix needed a drone that was executing another
  task at the moment of the press. These 11 presses came from 9 episodes and 8 people: P01, P02, P05,
  P06, P10, P11, P16 and P28. Four of the presses (P01, P02) were pre-v1.5, where the pool was
  idle-only by design. Only 2 people are in v1.12+ (P16, P28).

**What operators did after a blind-spot failure:** they fixed it by hand. After 7 of the 11 presses the
next action was a manual edit, after 2 a retry, after 1 a deploy (the partial case), and after 1 an
abandonment. Episode outcomes: 8 of 9 recovered (7 by hand, 1 with the partial agent plan) and 1
abandoned (P16, 1.6 s after the press).

The blind spot is real but cost almost nothing in this dataset. Operators who met it chained the busy
drone themselves.

**The page's "suggest-then-abandon" pattern is not a Suggest failure.** In 9 of its 11 episodes (7 of
the 9 in v1.12+), Suggest returned a **complete** plan and the operator abandoned anyway, with a median
of 6.7 s between press and abandonment. Only 2 of the 11 had a failed press. That makes it an
operator choice (perhaps the chained plan looked too slow), not the agent saying nothing.

### 3c · Did experiencing a failed Suggest change later behaviour?

"Exposed" means having at least one blind-spot press. There are 8 exposed people among 26 recovery
Suggest users: 6 in v1.5+, 2 in v1.12+. Exposure is not simply opportunity. Exposed people pressed
Suggest less often than unexposed users (3.1 vs 4.0 presses per person; v1.5+: 3.5 vs 4.1).

- **Later recovery Suggest use.** Comparing episodes after a person's first failure with users'
  episodes with no prior failure: 8/38 vs 43/61 used Suggest. GEE (+ run): OR 0.14 (0.03–0.83),
  p = .03. This is driven by P01 and P02 (pre-v1.5, where recovery Suggest usually failed): 0 of 20
  later episodes. In v1.5+ it is OR 0.21 (0.04–1.18), p = .076 (8/18 vs 43/58). In v1.12+ it is
  OR 0.32 (0.07–1.61), p = .17. It is mostly between-person, and the direction is consistent with
  people giving up on recovery Suggest after it fails. That is suggestive at best.
- **Tactical keep-unmodified rate.** This is a difference-in-differences on tactical decisions before
  and after the event: the first failure for exposed people, the first recovery press for unexposed
  users, with run and scenario as covariates.
  - Unexposed users rose from 66% to 83%, which is learning.
  - Exposed users stayed flat at 73% → 74%.
  - Interaction OR 0.54 (0.26–1.14), p = .11.
  - Among consulted plans only: OR 0.94, p = .81.
  - Consult rate: OR 0.45 (0.20–1.03), p = .059.
  - v1.5+: OR 0.54 (0.16–1.83). v1.12+ (2 exposed people): uninformative.
  - Not supported. Any spill-over would be into *consulting* the tactical assistant, not into
    accepting its plans.
- **Tactical trust (post-session).**
  - Sessions with a failure vs sessions with presses and no failure: 5.44 (n = 9) vs 5.52 (n = 30).
    GEE b = −0.70 (−3.21 to 1.81), p = .59.
  - Change in trust from s1 to s2: +0.50 (exposed in s1, n = 3) vs +0.10 (pressed in s1 without a
    failure, n = 15). Mann–Whitney p = .72.
  - Person level: 5.53 (exposed, n = 8) vs 5.40 (unexposed users, n = 18), p = .68.
  - No effect. With n ≤ 9 exposed sessions only very large effects could have shown up. One
    v1.12+ "all sessions" GEE gives p = .006 on 3 exposed sessions. That is an unstable artefact,
    not a result.

## 4 · Analysis log (in order)

1. Ran `study_analysis.load()` to establish the all-33 episode set: 194 episodes, 116 recovered,
   67 abandoned, 11 unresolved.
2. Compared the logged idle-only `feasible` flag with `feasibleWithBusy`. They disagreed in 4
   episodes where the flag said feasible but busy-inclusive said not, which should be impossible.
   Diagnosed two bugs in `feasibleWithBusy`:
   - its `dead` set never forgets a failed drone, but failed drones are replaced and the IDs reused
     (P27 s2: B03 fails twice);
   - its `deployed` set keeps drones that finished their last task and flew home (P13 s2 M004: G06
     finished 0.6 s before the failure and left; P28 s2 M005: G03 left 35 s earlier).
3. Wrote a time-local reconstruction (snapshot + execution intervals). Validated it against the
   logged pool: 184/194 exact, idle-fixable 190/194.
4. Primary on all 33 and on v1.12+, as specified.
5. R1–R9: alternative fixability definitions, outcome coding, covariates, build windows, pooled and
   fixed-effect estimators. All agree in direction. The conditional logit, which uses only the 13
   informative people, is not significant (p = .07).
6. R11 latency check: episodes with and without Suggest take similar times. Median 21.8 s
   (Suggest, recovered) vs 18.7 s (no Suggest, recovered).
7. R12: split Suggest into "gave a plan" vs "gave nothing". The effect sits entirely in "gave a plan".
8. R13/R14: noticed that no-attempt episodes are structurally all abandonments and all in the
   no-Suggest arm. Restricting to attempted episodes removes the effect (OR 0.94). Found after the
   fact. It changes the interpretation, not the registered verdict.
9. R15 (Suggest as the first move): ns. R16 (bias-reduced SE) and R17 (paired person-level
   Wilcoxon): primary holds.
10. Press classification. Validated against `wasAgentSuggested` (51/53). Tabulated next actions,
    blind-spot cases and the suggest-then-abandon pattern.
11. Exposure analyses on all 33, v1.5+ and v1.12+. The later-use effect shrinks once the pre-v1.5
    builds, where Suggest was broken, are dropped.

Not attempted: a matched comparison of operators' projected completion times after a solved press,
to explain the abandonments that followed a solved press. The planner's timing is not logged in
recovery.

## 5 · Traps from HYPOTHESES §2

- **Trap 1 (no injected failures):** applies directly. The only genuine assistant error here is the
  blind spot. I separated it from Suggest correctly reporting "no workable plan" (16 of the 27
  failed or partial presses).
- **Traps 2, 3, 6, 7 (card and manual nuances, composition, before/after):** not about the cards, so
  traps 2, 3 and 6 do not apply. For trap 7, the exposure analysis uses a difference-in-differences
  with an event time for unexposed users (their first recovery press) rather than a naive
  before/after. Exposed and unexposed users still differ between persons.
- **Trap 4 (residuals):** residual missions can fail and are kept. No analysis uses category as a
  main term; R5 uses it as a covariate only.
- **Trap 5 (forced wait):** not applicable. Recovery has no card wait.
- **Trap 8 (quotes):** none used.
- **Trap 9 (n = 33):** the within-person effect rests on 17 people (8 in v1.12+). Exposure analyses
  have 8 exposed people (2 in v1.12+). I report the detectable OR (0.40) and the small-sample SE.
- **Build differences:**
  - pre-v1.5 (P01–P03, 41 episodes): recovery Suggest drew on idle drones only and usually returned
    nothing. Kept in the primary per the cohort rule. R6 drops them and the result holds
    (OR 0.43). Press reconstruction uses the idle-only pool for these builds.
  - v1.0–v1.5 `wasAgentSuggested` under-counts. It is never used as the predictor, only as
    validation, and only on v1.6+.
  - Post-failure grace (v1.5+): it lowers failure counts but does not change the episode logic.

## 6 · Contradictions and refinements of the brief (Finding 6)

1. **The direction holds and is within-person.** The OR is 0.40, and the between-person term is
   null. The brief's "observational" caveat about people differing is less of a worry than it looked.
2. **The comparison it implies is misleading.** "Suggest 18% vs not 51%" sets Suggest against a group
   that includes 27 episodes abandoned with no attempt at all. Against hand-fixed recoveries, Suggest
   is no better (20% vs 10% abandoned, within-person OR 0.94). The finding is about **engaging versus
   giving up**. "Prompt Suggest on failure" might still help by turning non-attempts into attempts,
   but any prompt to try (a plain "Fix" nudge, for example) is the matching control.
3. **"abandon-busy" (Suggest blind spot) is over-counted.** The pattern shows 12 (all 33) and 7
   (v1.12+). With time-local drone membership it is 8 and 4, because `feasibleWithBusy` counts drones
   that had already flown home. Only 3 of those 8 involved a Suggest press. The bug is in
   `study_analysis.py` `read_session()` (`dead`/`deployed` sets). I have not edited it.
4. **"suggest-then-abandon" ("abandoned right after Suggest, though fixable") is not the blind spot.**
   In 9 of 11 episodes Suggest returned a complete plan and the operator abandoned it within seconds.
   The pattern label should not be read as an agent failure.
5. **The genuine agent failure was mostly harmless.** After a blind-spot failure operators fixed the
   mission by hand in 7 of 9 episodes, and only 1 was abandoned. There may be some reduction in later
   recovery Suggest use (suggestive, carried by the pre-v1.5 builds). No detectable change in
   tactical keep-unmodified rate or tactical trust.

## 7 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h3_recovery.py
```
Runs in about 20 s and is deterministic. It reads `Results/Participants/` and writes nothing.
