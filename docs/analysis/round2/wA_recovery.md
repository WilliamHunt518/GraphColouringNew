# Round 2 · Workstream A · Recovery: what makes operators attempt a fix?

Scripts: `scripts/analysis_round2/wA_common.py` (loader, PC1, model helpers) and
`scripts/analysis_round2/wA_recovery.py` (every test; prints every number below, writes only
`docs/analysis/round2/wA_specs.csv`, 197 rows). Builds on round-1 H3: its episode reconstruction, its
**corrected** time-local fixability check (`fixAll`, not `study_analysis.read_session`'s buggy
`feasibleWithBusy`), its attempt classification and its reconstruction of what each Suggest press produced
are reused unchanged by importing `h3_recovery.parse_session`.

**Data.** 194 recovery episodes from 33 people (P09 excluded): 116 recovered, 67 abandoned, 11 left open
at the buzzer. **173 were fixable** with drones already on the mission. Of those, 137 were *attempted*
(a drag or a Suggest press in the recovery planner) and 36 were not (27 abandoned, 9 left open).

**Terms.** *Attempted* = the operator did anything in the recovery planner. *Odds ratio (OR)*: how the odds
of the outcome change per unit of the predictor (1 = no change; 1.26 = odds up 26%). *Within-person*: the
predictor is centred on each operator's own average, so the estimate compares an operator's failures with
their other failures. *GEE* with *bias-reduced* errors: the regression for many episodes per person, with
the small-sample correction (all p-values here use it). *Conditional logit*: a purely within-person model
that only uses people who both attempted and did not attempt. *Spearman ρ*: rank correlation between
people. *Censoring*: an outcome cannot be observed because time ran out, not because of a choice.

## 1 · Candidates

**One candidate, between people — and a weak one: operators lower on the reliance axis are less likely
to attempt a fix at all.**

| Test | Estimate | p | Gates |
|---|---|---|---|
| A4c · person's share of fixable failures attempted vs PC1 (Spearman) | ρ = 0.54 | .0012 | session 1: ρ .51 ✓ · Strategic-first .64 / Tactical-first .55 ✓ · leave-one-out .51–.61, no flip ✓ |
| X1c · same, PC1 rebuilt **without** the recovery-Suggest feature (removes overlap with the outcome) | ρ = 0.51 | .0024 | s1 .50 ✓ · orders .59 / .58 ✓ · LOO .48–.58, no flip ✓ |
| A4a · episode-level GEE, attempted ~ PC1 | OR 1.54 [0.99, 2.41] | .056 | s1 ✓ · orders ✓ · LOO 1.49–1.94 (A4a-game), no flip |
| X1 · same, PC1 without recSug | OR 1.45 [0.99, 2.13] | .057 | s1 ✓ · orders ✓ · LOO no flip |

Also v1.12+ (ρ .55, p .005) and S-27 (ρ .54, p .003). Every PC1 → attempted estimate in the table
(A4a, A4a-game, A8d, X1, all samples) is positive, OR 1.4–1.6.

Why I call it weak:

- **It is carried by the extremes.** 19 of 33 people attempted every fixable failure (tied at the top).
  Four people never attempted one: P15 (0 of 8), P24 (0/5), P29 (0/3) and P30 (0/1). All four sit below
  the median on PC1 (−1.50, −1.44, −0.84, −1.12, against a median of −0.09 for everyone else). The
  episode-level GEEs, which weight episodes rather than people, only reach p ≈ .06.
- **It is about attempting, not succeeding.** Once you condition on the outcome of resolved episodes,
  PC1 does not predict abandonment (A4b OR 0.84 [0.56, 1.26], p .40; X1b 0.85).
- **It is between-person.** It says who never engages with a broken mission, not what makes a given
  operator engage.

**Mechanism (one sentence).** Low-reliance operators engage less with every assistant-mediated planner,
the recovery planner included, and treat a broken mission as something to abort and re-send rather than
to repair. Debrief support is thin. P29, a never-attempter, describes failures as missions that "would
sometimes have to abort" (P29/agent_comparison/1720). P24, another, describes the urge to "click that
ASAP" rather than deliberate (P24/verification/1689). No quote speaks to recovery directly.

**Not a candidate, although it passes the gates nominally: time left in the session (A1).** See §2.A1. The
effect is produced by failures that land in the last few seconds, where no attempt can be observed.

## 2 · Everything else, by variant

### A1 · Time left in the session at the failure

**What the scoring rules imply (`gameReducer.ts`).** This decides what "late abandonment" means:

- Only *completed* tasks earn points. At the buzzer, every unfinished task of a non-abandoned mission is
  failed and earns 0. A fix that cannot finish earns nothing.
- Penalty runs per task until the task completes. An abandoned mission's clock stops at `abandonedAt`,
  but its residual starts accruing from the same instant. So **abandoning saves no penalty**.
- `ABANDON_MISSION` flies **every** mission drone home, including drones executing other tasks. Their
  work moves to a queued residual that has to be allocated and planned from scratch.

So late in a session, abandoning is never better than leaving the mission open: it costs the in-progress
tasks and gains nothing. "Rational triage" predicts *leaving open* late, not *abandoning* late. Checked
against the data: 0 of 7 recovered episodes whose fix could not finish in time completed the repaired
task, against 67% of the rest. My "could finish" flag (time left > the affected task's base time + 15 s
travel) therefore tracks what the engine did.

**Results.**

| Spec | Estimate | p | Note |
|---|---|---|---|
| A1a · attempted ~ minutes left (within-person) | OR 1.26 [1.02, 1.56] per min | .031 | s1 1.48, S-27 1.28 (.06), S-6 1.18; v1.12+ did not fit (separation: too few non-attempts) |
| A1a-game · + game + run | 1.25 [0.99, 1.57] | .059 | |
| A1a-pool · total association | 1.28 [1.07, 1.54] | .008 | |
| A1a-cl · conditional logit | 1.58 [1.07, 2.32] | .021 | 10 informative people |
| A1b · attempted ~ fix could finish | OR 3.33 [1.17, 9.44] | .024 | Strategic-first order: 0/4 vs 92% (separation, model cannot fit; same direction) |
| A1c · attempted ~ final 90 s | OR 0.40 [0.18, 0.90] | .028 | |
| A1d · abandoned vs recovered ~ minutes left | OR 1.06 [0.89, 1.26] | .52 | Triage predicts < 1; it is ≥ 1 in every sample except S-6 |
| X2 · abandoned (left-open = not abandoned) ~ final 90 s | OR 0.38 [0.10, 1.41] | .15 | Late failures are abandoned *less* (4/27 in the final 90 s vs 27–34% earlier) |
| **X3-31s** · A1a without failures with < 31 s left | **OR 1.12 [0.94, 1.34]** | **.20** | 162 episodes; only 2 left open remain |
| X3-60s · without failures with < 60 s left | OR 1.04 [0.90, 1.20] | .62 | s1 0.93; LOO flips (P11) |

**Reading.** The A1 association is real in the data but mechanical. 8 of the 9 left-open episodes
began with 12 s or less on the clock. Failures are seeded, so a failure at 468 s recurs across people. The
median operator needs 14 s to make a first move in the planner (90th percentile 31 s), so these episodes
cannot show an attempt. Remove them (X3) and the time effect shrinks to OR 1.12 (p .20), and to 1.04 at
60 s. Beyond the last half-minute, the attempt rate does not track time left: 69% / 85% / 78% / 96% in
the 31–90 s / 90–180 s / 180–300 s / 300 s+ bins.

There is **no sign of "late failures abandoned more"**. Abandonment among resolved episodes is flat in
time (A1d), and late failures are abandoned *less* (X2, ns). Operators facing a hopeless late failure
leave it, which the scoring makes correct. The one place time plausibly matters is the 7 recovered
episodes that could not finish. Those operators fixed them anyway, at no cost.

### A2 · Reward at stake, mission size, drones left on the mission

All null, all OR close to 1:

| Spec | OR | p |
|---|---|---|
| reward still at stake (per 100 points; P01/P02 rescaled ×2) | 1.13 [0.80, 1.60] | .48 |
| tasks left | 1.08 [0.81, 1.43] | .61 |
| drones left on the mission | 1.05 [0.95, 1.16] | .32 |
| abandoned vs recovered ~ reward | 1.02 [0.83, 1.26] | .82 |

The joint model with game fixed effects (A2e) also gives nothing: reward 0.90, drones 1.11, time 1.27
(p .056, the same censoring as A1). The orders disagree on reward and tasks left, and the leave-one-out
check flips on P02/P35. How much a mission is worth does not decide whether people try.

### A3 · Recent failures

| Spec | OR | p |
|---|---|---|
| other failures in the previous 60 s | 1.25 [0.69, 2.26] | .46 |
| another recovery open at the time | 0.84 [0.32, 2.19] | .71 (15 episodes) |
| second failure on the same mission | 0.55 [0.09, 3.59] | .53 (11 episodes) |
| abandoned vs recovered ~ previous-60-s failures | 0.90 [0.54, 1.50] | .70 |

A within-person permutation null for A3a (failure counts shuffled among each person's own episodes,
300 simulations) gives a calibrated p of .48. A burst of failures does not make people give up. The
direction is, if anything, the opposite.

### A4 · Reliance axis (PC1)

See §1. PC1 was recomputed from `h1_archetypes.py`'s ten features with no bootstrap. It explains 30.7%
of variation, with loadings `took` .92, `previews` .88, `consult` .62, `recSug` .46, matching round 1.
Without `recSug` it correlates .988 with the full PC1.

### A5 · Opposite: do high-reliance operators abandon more when Suggest has no clean fix?

**Untestable.** Only 8 fixable failures (7 resolved) had no Suggest fix at the moment of failure: the fix
needed a drone executing another task, Suggest's blind spot. The PC1 × not-clean model cannot be fitted
(A5a).

Descriptively, those failures were abandoned far more often: 6 of 7 vs 42 of 157 (A5-exact, Fisher
p .003, ignoring clustering). But the people who abandoned them were mostly **low**-reliance: P03
(PC1 −3.6), P11 (−0.8) and P35 (−1.2, twice), all without an attempt. Two mid-to-high operators (P04, P10)
attempted and then abandoned. The highest, P28 (1.36), fixed it. That runs against the "opposite"
hypothesis. On the press-based definition (a failed or partial press in the episode, 11 episodes), the
interaction is OR 0.70 [0.15, 3.27], p .65 (A5b).

### A6 · Abandoning a working Suggest plan

58 resolved fixable episodes had a press that returned a complete plan. 11 were abandoned anyway, by 9
people: P06, P11, P12, P19, P26 ×2, P32, P33, P34, P35 ×2. The abandonment came quickly, a median of 5.6 s
after the press. Eight of the nine fixed another solved-press episode on other occasions.

| Question | Spec | Result |
|---|---|---|
| Who | A6a · PC1 | OR 0.87 [0.55, 1.39], p .56 |
| When | A6b · minutes left | OR 1.04, p .79 |
| What it was worth | A6c · reward at stake | OR 1.48 [0.96, 2.29] per 100 points, p .075 (S-27 1.66, p .011) |

The reward result (A6c) **fails the session-1 gate**. What does stand out: both episodes where the fix
needed a drone already heading to another task (so Suggest's plan chains it) were abandoned (P12, P26),
against 9 of 56 others (A6d-exact, Fisher p .033, 2 episodes).

Abandoned working plans also had fewer drones on the mission (5.2 vs 6.5) and more tasks left (4.0 vs
3.3). One reading fits all of this, but it is unconfirmed: a stretched, chained repair plan on a big
mission looks slower than aborting and re-sending a fresh team.

### A7 · After a Suggest failure: later attempt rates within person

Exposure is the person's first failed or partial press (A7a, 13 people) or their first blind-spot press
(A7b, 8 people). Their later fixable failures were attempted *more* often, not less: 87% → 98% (A7a
OR 1.46 [0.17, 12.8], p .74).

The required **null simulation**: put the "exposure" at a random one of the same person's own presses,
323 simulations. The design alone produces OR 0.73 on average, so it is biased towards finding a drop.
The observed 1.46 sits at the top of that null (calibrated one-sided p .98). Later Suggest use also does
not fall (A7a-sug OR 0.83, p .78; A7b-sug 0.90, p .90). A7b's attempt model cannot be fitted: every
post-exposure episode was attempted. So there is no sign that a Suggest failure discourages trying.

### A8 · Constrained: fixable failures on three-type missions only (138 episodes)

| Spec | OR | p | Note |
|---|---|---|---|
| A8a · minutes left | 1.24 [1.04, 1.49] | .020 | The same censoring as A1: 7 of the 11 failures with < 31 s left are three-type |
| A8b · reward | 1.11 | .68 | |
| A8c · recent failures | 1.51 | .30 | |
| A8d · PC1 | 1.50 [0.89, 2.51] | .13 | Same direction as A4 |
| A8e · abandoned vs recovered ~ minutes left | 1.03 | .80 | |

## 3 · Analysis log (in the order run)

Pre-stated before any model was run (2026-10-07):

- Outcomes: **attempted** = a drag or a Suggest press in the episode (H3's classification), on episodes
  fixable with drones already on the mission (H3's corrected time-local `fixAll`, unresolved episodes
  included); **abandoned vs recovered** on the resolved fixable episodes (H3's primary sample).
- Situational predictors are split into a within-person part (centred on the person's own mean in that
  sample) and a between-person part. The within part is the reported estimate.
- **Extra X1** (reason): the reliance axis PC1 contains `recSug` (share of recovery episodes with a
  Suggest press). A Suggest press *is* an attempt, so PC1 → attempted is partly circular. X1 recomputes
  PC1 without `recSug` and repeats A4.
- **Extra X2** (reason): scoring in `gameReducer.ts`. Only completed tasks earn points. Penalty runs
  until completion or abandonment, and the residual of an abandoned mission accrues from the same
  instant, so abandoning saves no penalty. `ABANDON_MISSION` also flies *every* mission drone home,
  including those executing other tasks, whose work then sits in a queued residual that cannot finish
  late. So late in a session abandonment is dominated by leaving the mission open. X2 tests whether
  abandonment (with "left open at the buzzer" counted as not abandoned) falls in the final 90 s.
  Expected direction −.

Run order:

1. Loader built and checked: 194 episodes and 173 fixable, matching H3. PC1 reproduces round 1 (30.7%;
   `took` .92). 10 people vary in whether they attempt; 4 never attempt; 19 always attempt.
2. A1–A8, X1 and X2 run as specified.
3. A3a got its permutation null. A7 got its pseudo-exposure null simulation.
4. **Extra X3**, written into this log before it was run, after seeing the first pass of A1. Reason: 8
   of the 9 "left open" episodes failed with 12 s or less on the clock (a seeded failure at 468 s recurs
   across people), while the median time from failure to an operator's first recovery action is 14 s
   (90th percentile 31 s). Those episodes cannot show an attempt whatever the operator intends, so it is a
   censoring artefact, not a choice. X3 repeats A1a, A1b and A1c excluding failures with less than 31 s
   left, and more strictly less than 60 s. Expected direction as A1 (+ for time left).
5. Added afterwards, within existing variants (not new variants):
   - Fisher exact rows for A5 and A6d, because their models could not be fitted (separation);
   - order-specific raw rates for the A1b/A1c cells whose order gate shows `na`;
   - gates for the person-level Spearman rows (A4c, X1c).
6. A model guard was tightened, and I re-ran. Fits with no predictor variation, an undefined p or an
   unbounded interval are now reported as "did not fit" rather than as OR 1.0 or overflow.

Spec-table rows with an empty estimate are tests that could not be run (separation or no variation).
They are listed for completeness and should not enter the q-value pool as p = 1.

## 4 · Traps and confounds

- **Order and game (§1 of the plan).** Each key spec has a game-fixed-effect version (A1a-game, A1d-game,
  A2e, A4a-game). None changes direction. Failure times are seeded per game (the same elapsed times recur
  across people), so "time left at failure" is partly a property of the game. The game fixed effect
  absorbs that. S-27 results are "order + pairing". S-6 is descriptive only: its six-cluster p-values,
  e.g. A1a p .002 and A3b p .005, should not be read.
- **Censoring at the buzzer.** This is the main trap for this workstream: see A1/X3. Any "late failure"
  contrast needs failures in the final ~30 s removed.
- **Scoring.** In-flight tasks earn 0 at the buzzer, and abandoning saves no penalty (§2.A1). Late
  abandonment would be a mistake, not triage, and it is rare.
- **Structural zeros (H3 R13).** Every non-attempt on a fixable failure ends abandoned or left open,
  because a recovery cannot deploy without a drone on the broken task. That is why the outcome here is
  *attempted*, not abandoned.
- **Within-person power.** Only 10 people vary in whether they attempt. All within-person estimates rest
  on them. v1.12+ models often cannot be fitted (separation).
- **Trap 1 (no injected failures).** The only Suggest "error" is the blind spot (A5/A7). Its 8 fixable
  occurrences are too few for the interaction A5 asked for.
- **Trap 4 (residuals).** Residual missions keep their parent's category and can fail again. They are
  kept, as in H3.
- **Trap 7 (event-defined comparison).** A7 used a calibrated null, which showed a built-in bias towards
  OR < 1. A3a used a within-person permutation null.
- **Trap 8 (quotes).** Single-coder debrief quotes, not aligned to events. They are used only to
  illustrate the mechanism.
- **Builds.** Pre-v1.5 recovery Suggest drew on idle drones only. "Suggest clean" uses the logged idle
  flag for those builds and the not-executing pool afterwards, as in H3.
- **P01/P02 half weights.** Reward at stake is rescaled ×2. No performance metric is used here.

## 5 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wA_recovery.py
```

Takes about 1 minute and is deterministic (seed 20261007). It reads `Results/Participants/` and writes
only `docs/analysis/round2/wA_specs.csv`.
