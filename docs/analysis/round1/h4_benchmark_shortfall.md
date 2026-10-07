# H4 · Is the larger Strategic Heavy shortfall against the near-perfect operator explained by manual work?

Script: `scripts/analysis_round1/h4_benchmark_shortfall.py` (shared data layer
`scripts/analysis_round1/h4_h10_data.py`). Read-only; writes nothing. Run 2026-10-07.

## 1 · Primary (confirmatory) — NOT SUPPORTED

Specification exactly as pre-registered: per session, `share` = session score ÷ SMART benchmark
score for that game (`docs/reports/smart_benchmark.json`, matched on complexity × `planSeedIndex`,
as `build_findings_synthesis.benchmark()`); MixedLM `share ~ 0 + C(game) + manual_rate` with a
random intercept per participant. `manual_rate` = manual choices ÷ strategic decisions in that session
(all decisions, residual missions included, so 1 − `strategicUse`). The Strategic-vs-Tactical gap is the contrast
½(S1 + S2) − ½(T1 + T2) of the four game means, fitted with and without `manual_rate`. The
shrinkage CI comes from a participant-cluster bootstrap that refits both models in each of 1000
replicates.

| | all 33 (66 sessions) |
|---|---|
| manual-rate coefficient | **b = −0.140** share per unit manual rate, 95% CI [−0.425, +0.144], **p = .334** (bootstrap CI [−0.468, +0.178]) |
| S − T gap, no manual term | −0.142 (SE 0.045) |
| S − T gap, with manual term | −0.124 (SE 0.050) |
| gap shrinkage | **12.8%**, bootstrap 95% CI [−20.8%, 52.6%] |
| verdict | **NOT SUPPORTED.** The coefficient is negative but its interval includes 0, and the shrinkage is well below 50%. |

Detectable effect: SE(b) ≈ 0.145, so at 80% power this test detects |b| ≳ 0.41: going from
all-card to all-manual would have to cost about 41 points of benchmark share. The observed b of
−0.14 would explain about 0.14 × 0.129 (the S − T difference in manual rate) ≈ 1.8 of the 14.2-point gap.
That arithmetic is why the gap barely moves, whatever the p-value.

I read "support = a negative manual-rate coefficient" as requiring the 95% interval to exclude 0.
Under a looser reading (point estimate below 0), H4 still fails on shrinkage.

## 2 · v1.12+ sensitivity (n = 24) — NOT SUPPORTED

b = −0.112 [−0.390, +0.167], p = .432; gap −0.155 → −0.140; shrinkage 9.7% (bootstrap CI
[−37.7%, 41.2%]).

## 3 · Secondary (exploratory)

**3a. The gap belongs to the games, not to the scenario.** This is the main finding. Each
participant plays one of two game pairs:

| pair | Strategic share | Tactical share | T − S (paired) |
|---|---|---|---|
| S1 + T2 (n = 17) | 0.580 | 0.836 | **+0.255, p = .001** |
| S2 + T1 (n = 16) | 0.636 | 0.664 | +0.029, p = .65 |

All of the "61% vs 75%" sits in one pairing, and mostly in T2. The benchmark is weak on that game:
SMART had **12 drone failures** there, against a participant mean of 4.5. Its task completion was
0.78 and its penalty 445, against 108–163 on the other three games. **7 of 17 T2 sessions beat
the benchmark; no session beats it on any other game.** The benchmark's failure draws are not
matched to the participant's (as its own docstring warns), and on T2 that mismatch alone
inflates the Tactical share. On the other pairing the scenario gap is 3 points and not
significant. On `scoreEff` (score ÷ points on offer, no benchmark) the gap is smaller (−0.088), and
the manual term shrinks it by 17.9%, so it is still not explained.

**3b. Where the Strategic Heavy points actually go: missions never allocated.** These are
current-weight sessions only, as session means:

| | on offer | earned | unearned, never allocated | unearned, allocated | penalty | missions never allocated |
|---|---|---|---|---|---|---|
| Strategic Heavy | 2134 | 1312 | **424** | 399 | 268 | **2.4** |
| Tactical Heavy | 2242 | 1665 | 140 | 437 | 389 | 0.5 |

The Strategic Heavy deficit is throughput: missions still queued at the buzzer. Points lost on
missions that were allocated, and penalty, are no worse than in Tactical Heavy. Manual rate does go
with more unallocated points (b = +266 points per unit, p = .049). Split, that is within-person
+185 (p = .36) and between-person +330 (p = .07). So people who build by hand also leave more work
in the queue, which is the one route by which manual work could matter. It is a between-person
association, and it is too weak to carry the session-level gap (3a).

**3c. Within vs between person.** Split into a person mean and a deviation, the manual effect is
between-person only: within +0.096 [−0.330, 0.522], p = .66; between −0.305 [−0.662, 0.052],
p = .09. On v1.12+ it is within +0.17 (p = .48) and between −0.24 (p = .15). First differences
(Tactical session − Strategic session, game pair effect-coded) give a Δmanual coefficient of
**+0.096** (p = .66). The gap does not shrink (−8.7%) on all 33, nor on v1.12+ (b = +0.17, p = .49).
A person who goes manual more often in one session does not score worse in that session.

**3d. Pre-emptive vs post-reveal manual.** `share ~ game + early_rate + post_rate` gives
pre-emptive −0.015 (p = .94) and post-reveal −0.279 (p = .13), with 10.7% shrinkage. Split three
ways (pre-emptive / edited card / post-reveal unedited), the only term near significance is
**post-reveal unedited manual: −0.406 [−0.811, −0.001], p = .050**, with 15% shrinkage. Split
within/between, none of the four terms is significant. Found after the fact and one of several
splits, so suggestive at best. It is consistent with H10 §3c (the anchored, post-reveal manual
choices do worst at the decision level) and with brief Finding 3 (pre-emptive manual is not
rejection).

**3e. Per mission, manual vs card, matched on person × exact task composition** (genuine
decisions; 130 decisions in 53 strata that contain both routes, 27 people, 65 manual). All
estimates are manual relative to card:

- full completion: conditional-logit OR 1.01 [0.49, 2.09], p = .98;
- with abandoned work followed into its residual: OR 1.01, the same;
- net value ÷ points on offer: −0.024 [−0.137, 0.090], p = .68;
- penalty: +0.8 [−3.9, 5.4], p = .75;
- time to complete: +15 s [−6, 36], p = .16 (fully completed missions only).

Pre-emptive manual vs card: OR 0.85 (p = .78). Post-reveal manual vs card: OR 1.10 (p = .85).
Within a person and an identical mission, hand-built missions do neither better nor worse.

**3f. Does trimming small missions leave reserve that later missions use?**

- 60 of 175 single-type genuine decisions trimmed below the Conservative card, saving 1.9 drones
  on average.
- **The reserve never starved a decision.** At 0 of 606 decisions could a task not be staffed from
  reserve. A needed colour fell below the mission's total need on 20% of Strategic Heavy decisions
  and 43% of Tactical Heavy ones.
- Drones trimmed from missions still running at a later three-type decision (`saved_active`) do
  **not** raise the measured reserve at that decision: within-person b = −0.19 [−0.50, 0.12].
  The first link of the mechanism is not visible. Trimming happens when reserve is already
  under pressure, so the comparison is confounded.
- The same measure shows a small positive association with the later mission's net value
  (+0.018 share per drone, p = .025), but not with its full completion (OR 1.08, p = .27). The
  60 s and 120 s windows give similar, noisier results. Three windows were tried, so treat this
  as fragile.
- Reserve at the moment of a decision does predict that mission's completion, within person: OR
  1.058 per drone [1.028, 1.090]. More reserve means bigger cards, because the 15% top-up scales
  with reserve.
- At session level, drones trimmed on small missions do not predict large-mission completion
  (b = −0.007, p = .54), large-mission net value (p = .72) or share (p = .81; 47 sessions).

Verdict on the mechanism: not supported. Trimming does not demonstrably buy later missions
anything.

## 4 · Analysis log (in order)

1. Built a shared data layer and checked it against `build_findings_synthesis.load_decisions()`:
   606/606 rows, with choice, composition, residual, odd, card totals, pre-emption and outcome
   identical. I reconstructed per-mission penalty with `computePenaltyAccrued` logic. It matches
   `session_ended.penaltyAccrued` to < 1 point in 65/66 sessions. The exception is P01 s2
   (v1.0): abandoned missions there kept accruing under the old rule, so I over-recover 198 points.
   Points reconstruction matched in 66/66.
2. Replicated the brief: shares of 0.607 (S) and 0.753 (T).
3. Data check found that **P01 and P02 (v1.0–v1.2) ran on half task weights** (T1 = 10 … T5 = 50).
   Their benchmark share is therefore not on the benchmark's scale. Three sessions are floored at
   score 0 (P01 s2, P02 s2, P03 s1). These were kept in the primary, as pre-registered, and handled
   in robustness checks.
4. Primary MixedLM + bootstrap: not supported.
5. v1.12+: not supported.
6. Robustness (none changes the verdict):
   - excluding P01/P02: b = −0.226, p = .072, shrinkage 19%;
   - unfloored net score: 12%;
   - P01/P02 rescaled to current weights (2 × points − penalty; penalty rates do not depend on
     weights): b = −0.175, p = .20, shrinkage 15%;
   - manual rate over genuine decisions only: 15%;
   - `scoreEff` outcome: 18%;
   - adding run: 14%;
   - first differences: −9%.
7. Within/between decomposition. The negative coefficient is entirely between-person.
8. Pre-emptive / post-reveal / edited splits (§3d).
9. Game-pair breakdown (§3a). This showed the gap is one pairing, which led to step 10.
10. Benchmark diagnostics per game: failures, task completion, and sessions above 100%.
11. Shortfall decomposition into unallocated points, lost allocated points and penalty (§3b), then
    regressed on manual rate.
12. Per-mission matched comparison (§3e). Exact-composition strata are sparse: 130 of 564 genuine
    decisions are usable.
13. Trimming → reserve → later missions (§3f). First tried trims within the previous 60 s and
    120 s. Then switched to `saved_active` (trims on missions still running), because that is the
    only count of drones trimming could actually have kept in reserve. I report all three.

## 5 · Traps from §2

- **Game confound.** I used game fixed effects throughout, and the analysis showed the gap is
  itself game-specific (§3a).
- **Trap 3 (binary composition) and trap 2.** The per-mission comparison matches on the exact task
  multiset within person, which is stricter than `ncolours`.
- **Trap 4 (residuals).** Residuals are excluded from the matched per-mission analysis and the
  trimming analysis. Abandoned work is followed into its residual (`chain_full`) rather than
  counted as lost. Primary manual rate uses all decisions, with genuine-only as a robustness check.
- **Trap 5 (forced wait).** No latency measures are used.
- **Trap 6 (manual is not one behaviour).** Pre-emptive, post-reveal and edited are split (§3d, §3e).
- **Trap 1.** No injected failures, so "manual" is never a response to a planted error.
- **Trap 9 (n = 33).** Detectable effect stated in §1.
- **Not in §2:** the half-weight early builds, the score floor at 0, and the unmatched benchmark
  failure draws (§3a).

## 6 · H4 vs H10, and the brief

- **They agree.** Both find reliance associated with performance **between people** only. Here the
  between-person manual term is −0.31 (p = .09). In H10 the session-level between-person uptake
  term is +0.31 (the same model mirrored), and person-mean uptake predicts decision-level completion
  (OR 3.06, p = .004). Within a person, neither the session-level manual rate nor the
  decision-level route changes the outcome. H4 §3e (matched, OR 1.01) and the H10 primary
  (OR 0.81, n.s.) are the same answer from two angles.
- **Brief "Context".** "61% in Strategic Heavy and 75% in Tactical Heavy … whether that is the extra
  manual work is not tested". This can now be answered: it is not the manual work. Most of the
  difference comes from one game pairing, where the benchmark itself had an unlucky failure draw
  on T2. The brief should not present 61 vs 75 as a scenario effect. Of what Strategic Heavy
  genuinely does lose, most is missions never allocated. Two further caveats belong with the
  figure: P01/P02's shares are on a different points scale, and three sessions are floored at 0.
- **Brief Finding 3.** Its caveat says "whether trimming actually paid off later is not tested
  here". That has now been tested: trimming does not raise the reserve later decisions see, the
  reserve was never binding, and the session-level link is null. "Holding drones back for later
  missions" is the operators' stated reason, but in these logs it did not demonstrably pay.
  Finding 3's main claim is untouched and consistent with §3d/§3e: pre-emptive manual does not
  perform worse.

## 7 · Reproduce

```
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h4_benchmark_shortfall.py
```
This takes about 3 minutes, mostly the 2 × 1000 bootstrap. `H4_NBOOT=20` gives a quick run with
identical point estimates. The bootstrap is seeded: 11 for all 33, 12 for v1.12+.
