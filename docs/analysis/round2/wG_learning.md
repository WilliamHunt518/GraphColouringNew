# Round 2 · G · Learning and calibration across the sessions

Scripts: `scripts/analysis_round2/wG_common.py` (data + model helpers, reusing round-1 loaders) and
`scripts/analysis_round2/wG_learning.py` (every variant; prints all numbers, writes `wG_specs.csv`,
54 rows). P09 excluded. All GEEs are clustered on participant with the small-sample
(`bias_reduced`) errors. Quotes by ID only. Everything here is exploratory: candidates, not claims.

**Terms.** *Card uptake* = a strategy card taken as-is. *Composition* = whether the mission needs one
drone type or several (`multi`; in practice 1 vs 3 types). *Calibration* = relying on the card where
it helps (multi-type, large missions) and going manual where it does not — measured as the gap in
uptake between multi- and single-type missions. *run2* = the participant's second session. *Net
decision time* = seconds from opening the strategic panel to choosing, minus the forced card reveal
for card choices (round-1 H9); tactical time is net of Suggest's 1-entry-per-second reveal. *OR* =
odds ratio (1 = no change); *b* on a log-time outcome ≈ proportional change (−0.22 ≈ 20% faster).
*Gate columns*: S-s1 = same direction in session 1 only; orders = same direction inside both
scenario orders; LOO = whether dropping any one person flips the sign.

## 1 · Candidates

Only one family of results looks strong enough to pass q < .10 and the gates: **operators decide
faster with experience, net of the forced waits.** Nothing about *calibration* qualifies.

| id | result | estimate [95% CI] | p | S-s1 | orders | LOO |
|---|---|---|---|---|---|---|
| **G4.5** | Within a session, each minute → net strategic decision time falls (composition, route, run, scenario held) | b = −0.046 / min [−0.070, −0.023] (≈ −31% over 8 min) | .0001 | 1 | 1 (−.052 / −.042) | no flip (−.052 to −.042) |
| G4.1 | Session 2 vs 1, net strategic decision time | b = −0.22 [−0.37, −0.08] (≈ −20%) | .003 | na | 1 (−.25 / −.09) | no flip |
| G4.4 | same, manual choices only (no reveal involved) | b = −0.27 [−0.41, −0.14] | .0001 | na | 1 | no flip |
| G4.6 | Session 2 vs 1, tactical planner time net of Suggest reveal | b = −0.28 [−0.45, −0.10] | .002 | na | 1 (−.15 / −.29) | no flip |

- **Why G4.5 is the cleanest:** inside one session scenario and game do not change, so a within-session
  speed-up cannot be a scenario or game effect. It holds in session 1 alone (the S-s1 gate), in both
  orders, in session 2 alone (G4.5s, b = −0.039, p = .050), and with the final 90 s removed (G4.5r,
  b = −0.032, p = .048 — so it is not just end-of-session haste, though that halves its precision).
  The shape is a warm-up repeated in each session: median net time by third 12.5 → 8.8 → 8.5 s in
  session 1, 10.7 → 7.5 → 6.5 s in session 2.
- **Across sessions (G4.1/G4.4/G4.6)** the speed-up is the same sign in both scenario orders — i.e.
  both when the second session is Tactical Heavy and when it is Strategic Heavy — so it is not a
  scenario effect. It *could* still be game pairing: with game as a fixed effect run is identified only
  by the six swapped people, and the strategic estimate shrinks to b = −0.16 [−0.39, 0.07], p = .16
  (G4.2); the tactical one survives (G4.10, b = −0.37, p = .046). Read: **learning, most likely; game
  pairing not excluded for the strategic tier.** S-s1 is not applicable to a run contrast; G4.5
  serves that role.
- **Mechanism (one sentence):** practice with the interface and the mission types shortens the time
  people need to read a mission and commit, within each session and carried over into the next.
  Consistent with `P10/overall_experience/1359` (a felt learning effect through session 1 and into
  session 2) and `P18/scenario_comparison/1545` (knew what to expect the second time). Note the
  speed-up is in decision *speed*, not reliance: uptake does not rise with it.

## 2 · Everything else

### G1 · Calibration (composition × run on card uptake) — no evidence of better targeting

The composition effect is clear from the start — session 1 only, multi-type missions get a card at
OR 2.44 [1.21, 4.91], p = .013 (G1.12) — and is, if anything, **weaker** in session 2: OR 1.54
[0.93, 2.55] (G1.13). Every composition × run interaction is below 1, against the calibration
prediction, and none is distinguishable from no change:

| id | variant | OR [95% CI] | p |
|---|---|---|---|
| G1.1 | S-all, scenario adjusted | 0.69 [0.33, 1.42] | .31 |
| G1.2 | game fixed effect | 0.72 [0.34, 1.52] | .39 |
| G1.3 | Strategic Heavy only, game-specific slopes (separated by S-6 only) | 0.58 [0.25, 1.38] | .22 |
| G1.4 | within person (conditional logit, game dummies) | 0.64 [0.36, 1.13] | .12 |
| G1.5 | S-v112 | 0.77 [0.30, 1.93] | .57 |
| G1.6 | S-27 (order + pairing) | 0.86 [0.37, 2.01] | .73 |
| G1.7 | S-6, raw gap run 1 → 2 | gap .40 → .24 (diff −.17) | — |
| G1.8 | within Strategic Heavy (S-first vs S-second people) | 0.71 [0.30, 1.72] | .45 |
| G1.9 | within Tactical Heavy | 1.43 [0.06, 37] | .83 (14 single-type decisions — uninformative) |
| G1.10 | drone count instead of types | 0.95 [0.45, 2.01] | .90 |
| G1.11 | drone count, three-type missions only | 1.56 [0.45, 5.37] | .48 (both orders > 1) |
| G1.14 | per-person change in the gap (14 people with both kinds in both sessions) | +0.06 [−0.15, 0.28] | .37 (Wilcoxon) |

**Like with like.** Single-type missions almost only occur in Strategic Heavy (167 of 181), so the
composition slope can only really be measured in Strategic Heavy sessions — and across runs that is a
*between-person* comparison of people who played Strategic Heavy first (game S1) against people who
played it second (mostly game S2). There, the multi-vs-single gap narrows (0.435 → 0.670 in run 1;
0.541 → 0.694 in run 2) because **single-type uptake rises** in the second-run group, not because
multi-type uptake changes. Whether that is experience or game S2's missions cannot be told: the
game-specific-slopes version (G1.3, separated only by the six swapped) points the same way and is
equally uncertain, and S-6 is in the same direction (G1.7). By order the interaction has opposite
signs (S-first 0.48, T-first 1.21 in G1.1), which is what a scenario/game artefact looks like, not
learning. Verdict: **calibration does not improve between sessions; the apparent loosening is
scenario/game-confounded and not significant.**

Within session (extra **X1**) — where scenario and game are fixed — the composition slope steepens
slightly over the minutes of session 1 (OR 1.22 per minute [0.93, 1.60], p = .15) and over both
sessions (X1b, 1.11 [0.95, 1.30], p = .19, both orders > 1), but drone count within three-type
missions does not (X1c, 0.83, p = .41). A weak, non-significant hint of within-session sharpening only.

Extra **X2** (pre-empting the card reveal on single-type missions, where the card saves no time):
pre-emption there is flat across sessions (29% → 29% in Strategic Heavy; X2a OR 1.24, p = .78; game FE
1.20, p = .86), rises non-significantly within session 1 (X2c, 1.20/min, p = .32), and does not become
more targeted at single-type missions (X2d, 1.21, p = .68, opposite to expected). Operators do not
learn to skip the wait where the card does not help.

### G2 · The session-2 dip in card uptake — real once composition is held, but not shown to be specific to session 2

The first third of session 2 has lower uptake than the rest with composition and drone count held
(G2.1, OR 0.58 [0.34, 0.995], p = .048), with game fixed (G2.2, 0.57, p = .049), and on three-type
missions alone (G2.4, 0.49 [0.26, 0.96], p = .036) — so it is **not** a composition artefact (the
first third of session 2 does have slightly fewer multi-type missions, .66 vs .74 late, but holding
that fixed leaves the dip). It holds in both orders (0.45 / 0.67), so it is not tied to which scenario
came second, and no single person flips it. Because "first third" is a fixed share of each session's
decisions rather than an event, it is not self-selecting, but a null simulation was run anyway
(shuffle the third labels within each person-session, 300 times): null OR median 1.01, 95% range
0.66–1.46, **calibrated p = .017**. The climb after it is weak (G2.5, OR 1.06 per minute, p = .23).

However, the matching session-1 estimate is 0.96 and the first-third × run2 interaction is not
significant (G2.3, OR 0.64 [0.28, 1.45], p = .28; within Strategic Heavy only, G2.6, 0.79, p = .68).
Session 1 is flat over time (G2.7, OR 1.00, p = .97). So: a genuine early-session-2 dip, but whether
it is *larger than any session's warm-up* is not established. Plausible reading — people re-test the
assistant on returning — fits `P15/trust_trajectory/1985` (checked more in the second round) and the
"test it at the beginning" pattern in `P29/verification/1559`. The by-scenario table in the script
output shows the dip is sharpest when the second session is Tactical Heavy (0.58 → 0.79), but the
order split above says both directions have it.

### G3 · Dominated cards — operators do not learn to avoid them; if anything the opposite

A *dominated* Conservative card commits at least as many drones as Aggressive and is no faster.
Choosing it is predicted to fall with experience. It does not:

| id | variant | OR [95% CI] | p |
|---|---|---|---|
| G3.1 | Conservative chosen when dominated, run2 | 2.13 [0.95, 4.78] | .066 |
| G3.2 | + game FE | 1.91 [0.66, 5.53] | .23 |
| G3.3 | dominated × run2 (discrimination, all decisions) | 1.98 [0.92, 4.24] | .079 |
| G3.4 | illogical × run2, single-type only | 1.16 [0.25, 5.35] | .85 |
| G3.5 | card-takers only: Conservative vs Aggressive when dominated | 2.66 [1.14, 6.21] | .024 |
| G3.6 | within session 1, per minute | 1.00 [0.84, 1.19] | .97 |
| G3.7 | S-27 | 2.27 [0.83, 6.15] | .11 |
| G3.8 | S-v112 | 2.20 [0.82, 5.92] | .12 |

All run estimates point to *more* dominated-Conservative choices in session 2, consistent in both
orders and robust to dropping anyone — the opposite of the menu's expected direction. But it is
mostly game: within game S1 or S2 the run-1/run-2 shares are close (S2: .25 vs .32), the S1 run-2 cell
is three swapped people (13 of 28 choices), and the game-fixed version is not significant. Read as
**no learning to avoid dominated cards**, with the session-2 increase most likely a property of which
dominated cards game S2 and T2 present. Against expectation; worth the supervisor's eye only as a
two-sided curiosity (G3.5 p = .024), not a candidate.

### G4 · Speed — see Candidates. Remaining rows

Card choices only (G4.3, b = −0.21, p = .018); S-27 (G4.7, −0.26, p = .0008); S-v112 (G4.8, −0.22,
p = .024); raw seconds including the reveal (G4.9, −0.16, p = .006 — smaller than net because the
fixed 4–5 s reveal dilutes a proportional saving). Median net seconds, session 1 → 2: card 6.9 → 5.7,
manual after reveal 19.7 → 17.0, pre-emptive manual 10.7 → 7.2.

### X3 · Performance by run (extra) — the synthesis page's "learning shows up here" is game, not learning

With game fixed (run then identified only by the six swapped people), session 2 is not better on any
metric: score efficiency b = +0.02 [−0.08, 0.12], p = .64; per-game z +0.14 [−0.33, 0.61], p = .56;
share of the near-perfect operator +0.02, p = .72 (Tactical game 2 excluded: −0.002, p = .99); share of
best human +0.03, p = .68. P01/P02 were rescaled ×2 (`score_rescaled`); efficiency is a ratio and
unaffected. The scenario-only version that mirrors the synthesis page gives +0.08 [−0.02, 0.18],
p = .11 — but with **opposite signs by order** (S-first +0.23, T-first −0.07). The S-first people's
second session is Tactical game 2, where the benchmark is unreliable (round-1 H4) and every group
scores ~85% of it; that is what lifts "run 2". S-6: z-score rose for 4 of 6 and fell for 2.
**Recommend the synthesis caption "This is where the learning effect shows up" be withdrawn.**

## 3 · Analysis log (in order run)

Plan written into this file before any model ran (menu G1–G4 operationalised; extras X1–X3 with
reasons, below). Then:

1. Built the decision table from round-1 `h9_workload_speed.load_all()` (asserted row-for-row equal
   to the builder's `load_decisions()`), adding the builder's `dominated`/`odd`/`elapsed`; tactical
   plans from the same loader; sessions from `h4_h10_data.sessions()`.
2. First run: G1.3 as planned (`multi × C(game)` on all sessions) was rank-deficient — Tactical
   game 2 has no single-type decisions — so the helper silently replaced game with game index.
   Re-specified **before reading on** as game-specific slopes *within Strategic Heavy*, where they are
   estimable (the six swapped separate run from game there). The conditional logit (G1.4) failed
   because game pairing is fixed per person; re-coded as two tactical-game dummies (the within-person
   scenario contrast in each pairing) and dropped people with no variation in uptake (29 informative).
3. Ran G1 → X1 → X2 → G2 → G3 → G4 → X3.
4. After seeing G2.1, added its within-session shuffle null simulation (300 reps) and printed its
   session-1 analogue. After seeing G4.5, added two **post hoc robustness rows** of the same variant
   (G4.5r final 90 s excluded; G4.5s session 2 only) — in the spec table, marked "post hoc" in the
   description, not counted as extras.

Extras, with reasons stated before running:
- **X1** composition × elapsed time within session — inside one session scenario and game are fixed,
  so a steepening composition slope over minutes would be learning, not scenario/game. Expected +.
- **X2** pre-emptive manual on single-type missions ~ run2 (and elapsed) — H9 showed the card saves no
  time on single-type missions, so a calibrated operator would learn to skip the reveal there.
  Expected +.
- **X3** performance by run with game fixed — the synthesis page claims the learning effect shows up in
  benchmark share by run; tested with the four required metrics. Expected +.

## 4 · Traps and confounds

- **Order / game pairing (the main one).** Every run contrast is also scenario, order and game. Handled
  by (a) the order-split gate — for a run effect, same sign in both orders means it is not a scenario
  effect (scenario reverses between the orders); (b) a game-fixed-effect variant for each family,
  noting that there run is separated from game only by S-6; (c) S-27 (order + pairing) and S-6
  (descriptive); (d) within-session tests (X1, G2, G4.5), which no scenario or game can produce.
- **Composition is nested in scenario.** Single-type missions are 167/181 Strategic Heavy, so the
  binary calibration slope is a Strategic-Heavy-only, between-person quantity across runs. Drone-count
  variants (G1.10, G1.11) supply a within-person, within-three-type alternative.
- **Trap 2 (illogical nested in single-type).** G3.4 restricted to single-type missions.
- **Trap 3 (types effectively binary).** `multi` = ≥ 2 types; the 12 two-type decisions are in `multi`.
- **Trap 5 (forced reveal).** All strategic times net of `deployEnabledAtMs` (asserted ≥ 0 for every
  card choice); manual times are raw (never gated); tactical net of the 1 s/entry Suggest reveal.
  Raw time shown once for contrast (G4.9).
- **Trap 7 (before/after).** No event-defined windows; the thirds comparison got a null simulation
  anyway (calibrated p = .017).
- **Residuals** kept (as in the builder's models); composition is read from the residual's own tasks.
- **P01/P02 half weights:** rescaled ×2 in X3; efficiency unaffected.
- **Benchmark unreliable on Tactical game 2:** X3.5 excludes it; it drives X3.6.
- **n = 33.** Person-level G1.14 has only 14 people with both kinds of mission in both sessions.
- **Gates.** S-s1 cannot be applied to a session-2-vs-1 contrast (`na`); the within-session analogue
  is supplied where one exists. Order-subset models drop factors collinear there (scenario, or game →
  game index); the helper logs any reduction in the notes (none occurred in the final run).

## 5 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wG_learning.py
```

Deterministic (seeded null simulation), ~2 minutes. Reads `Results/Participants/*.json` and
`docs/reports/smart_benchmark.json` via the round-1 loaders; writes only
`docs/analysis/round2/wG_specs.csv`.
