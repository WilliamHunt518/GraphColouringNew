# H10 · Does relying on the assistants pay off?

Script: `scripts/analysis_round1/h10_reliance_payoff.py` (shared data layer
`scripts/analysis_round1/h4_h10_data.py`). Read-only; writes nothing. Run 2026-10-07.

## 1 · Primary (confirmatory) — NOT SUPPORTED (an informative null)

The test is decision-level: every strategic decision (n = 606, 33 people), modelled with
`build_findings_synthesis.gee` (binomial, exchangeable, clustered on participant):

`full ~ took + ncolours + ndrones + C(game) + took_pm`

- `full` is 1 if the decision's mission completed in full (`mission_completed.outcome ==
  all_completed`). Abandoned, partial, none-completed and still-in-flight-at-the-buzzer all
  count as 0.
- `took` is a card taken as-is. Its reference is manual, including edited cards.
- `took_pm` is the person's mean uptake (a Mundlak term), so `took` is the **within-person** route
  effect.
- The composition terms are the house terms (`ncolours`, `ndrones`).
- Residual decisions are included: each is its own allocation decision, with its composition taken
  from its own remaining tasks.

| | all 33 |
|---|---|
| card vs manual, within person | **OR = 0.81, 95% CI [0.55, 1.18], p = .272**, n = 606 |
| raw full-completion rate | card 60.2% · manual 61.7% |
| person-mean uptake (between person) | OR 3.06 per unit, p = .004 |
| detectable at 80% power | OR ≤ 0.58 or ≥ 1.73 |
| verdict | **NOT SUPPORTED**: the interval includes 1 |

Within the same person, whether a mission is built from a card or by hand makes no detectable
difference to whether it completes. The test could have seen an effect of roughly ±1.7× in odds,
so it rules out a large payoff in either direction, but not a modest one. The strong term is
between people: people who take the cards more often complete more of their missions.

## 2 · v1.12+ sensitivity (n = 24, 449 decisions) — NOT SUPPORTED

OR = 0.90 [0.57, 1.43], p = .667. Person-mean uptake OR 3.61, p < .001.

## 3 · Secondary (exploratory)

**3a. Robustness of the route term.** Every row except one has an interval that includes 1:

| specification | OR (card vs manual) | p |
|---|---|---|
| + time left at decision (buzzer censoring) | 0.94 [0.67, 1.33] | .74 |
| decisions with ≥ 150 s left | 0.64 [0.36, 1.13] | .12 |
| resolved missions only (in-flight dropped) | 0.69 [0.48, 1.00] | .048 |
| outcome follows abandoned work into its residual | 0.83 [0.55, 1.23] | .35 |
| genuine (non-residual) decisions only | 0.83 [0.57, 1.22] | .34 |
| + task count | 0.81 [0.55, 1.19] | .29 |
| + run | 0.80 [0.55, 1.18] | .26 |
| person × exact task-composition strata (conditional logit, + time left), all | 1.73 [0.58, 5.15] | .33 |
| same, genuine only | 1.03 [0.28, 3.82] | .96 |

Two cautions on these:

- The one nominally significant row ("resolved only") conditions on a post-decision outcome.
  Missions still in flight at the buzzer are dropped, and that is not random with respect to
  route, so I do not read it as evidence that cards hurt.
- The point estimates sit mostly below 1 with loose composition control and move to about 1 under
  exact-composition matching. That is the reverse-selection pattern the brief warned about.
  Manual is used more on single-type missions (48% of them, against 28% of three-type missions),
  which complete more often (74% vs 56%). The crude ncolours/ndrones adjustment removes most of
  this, and exact matching the rest.

**3b. Which card, which manual.** Reference: post-reveal, unedited manual (n = 77), adjusted for
time left:

| route | OR | 95% CI | p |
|---|---|---|---|
| Aggressive card | 1.61 | [1.02, 2.56] | .043 |
| Conservative card | 1.32 | [0.81, 2.14] | .26 |
| pre-emptive manual | 1.81 | [1.10, 2.99] | .019 |
| edited card | 3.54 | [0.92, 13.7] | .066 |

The weakest route is **manual chosen after reading the cards without editing one**, the "anchored"
manual of brief Finding 3. Pre-emptive manual does as well as the cards. This was found after the
fact and is one of several contrasts, so it is suggestive only. It matches H4 §3d at session level
(post-reveal unedited manual b = −0.41, p = .05).

Separately, more drones committed goes with completion (OR 1.16 per drone, p = .041, holding route
fixed), and it explains none of the route term (OR stays 0.82).

**3c. Penalty, net value and time.** These are within-person card − manual differences, adjusted
for composition, game and time left:

- penalty: −1.5 points [−5.1, 2.0], p = .40;
- net value ÷ points on offer: +0.000 [−0.037, 0.038], p = .98;
- time to complete for missions that completed: −8.7 s from arrival [−22.5, 5.1], p = .22, and
  −5.5 s from allocation [−13.0, 1.9], p = .15. The direction is faster for cards, but not
  significantly;
- drone failures per mission: +0.006, p = .91, although cards commit more drones (7.7 vs 5.9).

Cards are not cheaper, more valuable or slower, mission for mission.

**3d. Session level, between vs within person, game controlled** (MixedLM, person random
intercept):

| outcome ~ reliance | within | between |
|---|---|---|
| benchmark share ~ card uptake | −0.10 [−0.52, 0.33], p = .66 | +0.31 [−0.05, 0.66], p = .094 |
| benchmark share ~ tactical keep-unmodified | +0.14 [−0.26, 0.53], p = .49 | **+0.51 [+0.23, +0.79], p < .001** |
| scoreEff ~ card uptake | −0.08, p = .64 | +0.25, p = .060 |
| scoreEff ~ tactical keep-unmodified | +0.11, p = .49 | **+0.38 [+0.17, +0.58], p < .001** |

v1.12+ gives the same picture. Tactical keep-unmodified is between-person +0.49 (p = .002) on
share and +0.39 (p = .001) on scoreEff, and the within-person terms are about 0.

Person-level Spearman, uptake vs scoreEff:

- all 33: ρ = .32, p = .067;
- v1.4+ cohort, the existing `useVsPerf` set: ρ = .36, p = .048 (the brief's figure is .38 on 31);
- v1.12+: ρ = .28, p = .18.

Tactical keep-unmodified vs share: ρ = .32 (p = .073) on all 33.

**3e. Tactical: kept unmodified vs edited vs built from scratch.**

- Counts: 438 unmodified, 17 edited (8 people, 5 of them P04's), and 139 built without ever
  pressing Suggest.
- **Trap found:** `agentProjectedCompletion` is computed when the planner opens, but
  `finalProjectedCompletion` is computed at confirm. For **unmodified** plans, which are identical
  to the agent's, the difference still correlates r = .71 with the confirm delay. The raw
  difference is therefore partly waiting time, and I adjust for delay throughout.
- **Plans built from scratch project 54 s later** than the agent's plan for the same pool and
  mission. That is a delay-adjusted, within-person difference: +53.6 s [19.7, 87.5], p = .002
  (log scale +0.68, p < .001). Yet their missions complete about as often (OR 0.80 [0.50, 1.27],
  p = .35).
- Edited plans: projected +62 s (p = .14, n.s.), and **3 of 17 left a task unassigned**. Their
  missions completed far less often (OR 0.12 [0.04, 0.32]). With 17 plans, 8 people and edits
  probably made on missions already in trouble, I do not read this as a causal effect.
- The strategic and tactical routes are linked. After a manual strategic choice, 38% of plans are
  built from scratch, against 16% after a card. Holding the tactical route fixed, the strategic
  card OR is 0.92 (p = .62).

## 4 · Analysis log (in order)

1. Shared data layer (see the H4 report, log step 1). It reproduces `load_decisions()` row for row,
   reconstructs per-mission penalty (exact in 65/66 sessions), and adds mission status including
   abandoned and in-flight. `load_decisions().outcome` leaves abandoned and in-flight missions as
   None. I recomputed `C.outcome` (card 91.0% / manual 95.7% on fewer-than-three-colour missions)
   and confirmed it covers resolved missions only. 23% of decisions are still in flight at the
   buzzer, which is why the primary codes them as not completed.
2. Primary GEE: OR 0.81, n.s. I added a detectable OR from the model's SE.
3. v1.12+: n.s.
4. Censoring checks: time-left covariate, a ≥ 150 s subset, resolved-only.
5. Residual handling: `chain_full` outcome, then genuine-only.
6. Composition: task count, then exact composition × person conditional logit.
7. Run added.
8. Route split (Aggressive / Conservative / pre-emptive / edited / post-reveal manual) and a took ×
   three-colour interaction. The interaction is OR 1.65, p = .20, n.s.
9. Penalty, net value, points, time to complete, drone failures, drones committed.
10. Session-level within/between for uptake and tactical keep-unmodified, on share and scoreEff,
    for both cohorts. I recomputed the `useVsPerf` Spearman for all three cohorts.
11. Tactical projected completion. The first raw comparison looked dramatic (median +11 s for
    scratch-built plans, +41 s for edited). I then found the delay artefact on unmodified plans and
    re-ran with a delay covariate, and the scratch effect survives.

## 5 · Traps from §2

- **Reverse selection, trap 2/3.** Composition is controlled three ways: house terms, plus task
  count, plus exact person × composition strata. The route OR moves from 0.81 to about 1.0 as
  matching tightens, so the slight negative is composition, not route.
- **Censoring by the buzzer** is not in §2 but is essential: 23% in flight. I handled it with a
  time-left covariate and subsets.
- **Trap 4 (residuals).** Decisions on residuals are their own units in the primary. Abandoned work
  is followed into the residual as a robustness check. Genuine-only is also run.
- **Trap 6.** Manual is split into pre-emptive, edited and post-reveal (§3b).
- **Trap 1.** There are no injected errors, so "relying" means relying on rule-based advice that is
  usually sound. The question is "does this advice beat the operator's own call", not "does trust
  calibration pay".
- **Game confound.** Game fixed effects are used everywhere. In H4 the benchmark share is shown to
  be game-distorted (T2), which is why the session-level analysis reports scoreEff alongside it.
- **Trap 9.** Detectable OR stated.
- **What remains confounded:** who chooses manual, and when. Person-mean uptake removes stable
  person differences. It cannot remove moment-to-moment reasons for going manual (fatigue, a
  mission the operator judged easy). Matching on exact composition shrinks the sample to 130–147
  decisions in 27 people.

## 6 · H4 vs H10, and the brief

- **Agreement.** Both hypotheses find that **reliance goes with performance between people and not
  within them**. H4 has a between-person manual term of −0.31 and within +0.10. H10 has
  person-mean uptake OR 3.1 at decision level, a session-level between-person term of +0.31, and
  a within-person term of about 0. H4's matched per-mission OR (1.01) and the H10 primary (0.81,
  n.s.) agree. Both single out post-reveal unedited manual as the weakest route (H4 §3d, H10 §3b).
  Both are exploratory and fragile.
- **Refinement of the existing `useVsPerf` (ρ = .38).** It replicates on its own cohort (ρ = .36
  here; small differences come from how sessions are averaged). It weakens on all 33 (ρ = .32,
  p = .07) and on v1.12+ (ρ = .28, n.s.). Within person it is null at both levels. A reader should
  be told that **people who rely more do better, but relying more does not make a given person do
  better**, so it is a trait association and not evidence of the assistant's value.
- **Tactical keep-unmodified** is the stronger between-person correlate of performance (share
  +0.51, p < .001). This is new. It probably reflects a general competence or engagement style:
  hand-built tactical plans project 54 s slower but complete no less often.
- **Brief "Context" ("Causal claims about the assistant's value" are unsupported).** This is
  confirmed and now quantified: within-person route OR 0.81 [0.55, 1.18].
- **Brief Finding 3.** Consistent. Pre-emptive manual performs like the cards (OR 1.81 vs the
  anchored manual, and similar to Aggressive at 1.61), so "manual is mostly not a rejection" also
  holds on outcomes: it is not a worse decision either. The synthesis page's `C.outcome` (manual
  95.7% vs card 91.0%) drops abandoned and in-flight missions and does not adjust for anything. On
  every decision with adjustment, the difference vanishes. The page should say so.

## 7 · Reproduce

```
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h10_reliance_payoff.py
```
This takes about 30 s and has no randomness.
