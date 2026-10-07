# Workstream C · The reliance trait and its payoff (+ game difficulty and order)

Scripts: `scripts/analysis_round2/wC_common.py` (data layer: round-1 `h4_h10_data` loaders + the round-1 PC1
recomputed from `h1_archetypes` features without the bootstrap) and `scripts/analysis_round2/wC_analysis.py`
(every test). Spec table: `docs/analysis/round2/wC_specs.csv` (178 rows; 11 marked `extra=1`). Read-only;
P09 excluded; n = 33 people, 66 sessions, 606 strategic decisions. PC1 reproduces round 1 exactly
(30.7% of variance; loadings took .92, previews .88, consult .62 …).

**Terms.** *PC1 / reliance axis*: each person's score on round 1's single "uses the assistants" dimension, in
SD units. *Session PC1*: the same axis computed from one session's behaviour. *Within person*: a session (or
decision) compared with the same person's other session(s); *between person*: people compared with each
other. *b*: regression slope. *Game*: one of the four fixed mission streams (Strategic 1/2, Tactical 1/2).
*Run*: first or second session played (order / practice). *Gates*: the briefing's checks — same direction in
session 1 only (`s1`), in both scenario orders (`orders`), and no single person flipping the sign (`LOO`).
Performance metrics: **eff** (score ÷ points on offer), **z** (score standardised within game), **bshare**
(share of the near-perfect benchmark — unreliable on Tactical game 2), **best** (share of the best human score
on that game). **P01/P02 are rescaled** to current task weights (2 × points − penalty), not excluded.

## 1 · Candidates

Judged on my own reading (the supervisor computes q across the round). With 178 tests here, the rows below
are the ones with p ≤ .006 and clean gates; anything weaker is unlikely to reach q < .10.

| # | Result | Estimate [95% CI], p | Gates | Kind |
|---|---|---|---|---|
| 1 | **Within a person, a session with higher reliance leaves fewer missions never allocated** (C2, session PC1) | −0.78 missions per SD [−1.24, −0.32], p = .001; game + run fixed | s1 na (within-person needs two sessions); between-person term same sign in session 1; orders SF −0.92 / TF −0.77; LOO range [−0.88, −0.70], no flip | Throughput |
| 2 | **Between people, higher reliance goes with shorter queue time** (C2) | −21.9 s per SD [−37.3, −6.4], p = .006 | s1 ✓; orders ✓ (SF −7.6, TF −28.7); LOO [−23.8, −15.7], no flip | Throughput |
| 3 | **Practice, not game: missions wait ~18 s less in the second session** (D2) | −18.4 s [−31.4, −5.3], p = .006; v1.12+ −19.2, p = .017 | s1 na; same direction within each scenario (S −11.5, T −25.2); LOO no flip; S-6 (where run and game separate) −24.2 s | Order |
| 4 | **Practice, not game: tactical Suggest consulting rises in the second session** (D2) | +0.126 [0.040, 0.213], p = .004; v1.12+ +0.113, p = .027 | s1 na; within each scenario ✓; LOO no flip; S-6 +0.197; but S-27 only +0.057 (p = .20) | Order |
| 5 | **Reliance is higher in Tactical Heavy — a scenario effect, not a game one** (D2) | card uptake +0.130 [0.053, 0.207], p = .001; session reliance score +0.50 SD, p = .001 | s1 ✓ (+0.22, p = .06); both orders ✓; LOO no flip; game-index terms ≈ 0; S-6 T − S uptake +0.28 | Scenario |

Two further rows pass p < .001 with clean gates but are **replications, not new**: the card cuts net decision
time on three-type missions (log b −0.42, ≈ 34% faster; card × three-type interaction −0.81, p < .001),
which is round-1 H9's speed finding; and Strategic Heavy leaves ~1.9 more missions never allocated
(p < .001, also in session 1: −1.83, p = .005), which is round-1 H4 §3b and largely a design property
(13–14 missions arrive in a Strategic Heavy game against 6–9 in Tactical Heavy).

**Mechanisms (one sentence each), with debrief quotes:**
1–2. Leaning on the assistants turns each mission over faster, so fewer missions are still waiting when the
buzzer goes — *"I was using it more because it was quicker, and I thought then they won't all back up"*
(P32/scenario_comparison/1497); *"I probably would have gained more points from the time saved running another
mission"* (P11/verification/1811); *"The top advantage … was the speed of response … you'd get massively
overwhelmed with the number of missions"* (P31/overall_experience/1750). **Caveat:** result 1 holds when
decision speed (`netSecs`) is removed from the axis (X3: −0.58, p = .011), but **card uptake alone does not
show it within person** (−1.11, p = .32). So it is carried by the tactical/recovery side and card previews of
the axis as much as by taking cards. And the same within-person shift does **not** raise the score (C2:
uptake within b ≈ −0.07 on eff; round-1 H1 PC1 within b = .006). Fewer missions left queued, but no
detectable gain in points — plausibly the extra missions are low-value or late.
3–4. Operators get faster and more willing to press Suggest with practice — *"I mostly trusted it, although I
did kind of want to test it more at the beginning"* (P29/verification/1559); *"In the first test, I don't have
enough time to [notice] it"* (P33/trust_trajectory/1785).
5. Tactical Heavy missions are mostly large three-type jobs, where the card saves the most time (C3), so
people take it more. This is composition, not the scenario label — trap 2/3 — *"If the task is too complicated,
I will rely more on AI"* (P35/verification/1729); *"in the tactical, sometimes it's very complicated, and at
this time I prefer to use the suggest"* (P26/agent_comparison/1717).

## 2 · Everything else, by variant

### C1 · What predicts position on the reliance axis? (person level, Spearman ρ, n = 33)
Nothing measured before the study does:
- gaming frequency: ρ = .16 (p = .39);
- prior experience: ρ = .21 (p = .25). It is .45 (p = .03) on v1.12+, but .07 on session 1 only;
- session-1 score at 120 s: ρ = .10 (p = .57). This measure is weak: it is exactly 0 in 15 of 33 sessions,
  because few tasks can finish in two minutes.

A joint OLS of all four explains R² = .14 (adjusted .01, F p = .42).

**Session-1 bad luck leans negative, but no test reaches significance:**
- session-1 drone failures (game z): ρ = −.32 (p = .066);
- session-1 abandonments: ρ = −.34 (p = .052).

Both hold in both orders with no LOO flip. In session 1 alone they weaken (−.20, −.15).

**X1 (extra):** holding session-1 reliance fixed, each session-1 abandonment goes with −0.29 SD of
session-2 reliance [−0.54, −0.05] (p = .020; both orders ✓, LOO no flip). Failures themselves do not
(−0.13, p = .50). This is suggestive: "I abandoned a mission, so I relied less afterwards". But the
abandonments are themselves partly behaviour.

**X2 (extra):** the early allocation share predicts PC1, ρ = .44 (p = .010). It is circular, as stated in
advance: cards are a fast way to allocate. In session 1 alone it is .21 (p = .25).

### C2 · Does reliance pay through throughput?

Session means:

| | arrived | allocated | never allocated | queue time (s) |
|---|---|---|---|---|
| Strategic Heavy | 13.5 | 11.1 | 2.4 | 104 |
| Tactical Heavy | 7.6 | 7.0 | 0.5 | 93 |

There were 67 abandonments, and 142 tasks were re-queued into `<id>-R` residuals. These count as
transferred, not lost: residuals are never counted as new arrivals, and an abandoned parent counts as
allocated.

**Card uptake.**
- Throughput, within person: every term points the expected way, but none is significant
  (never allocated −1.11, queue +3 s, unallocated points share −0.11, p = .14).
- Throughput, between person: queue −67 s per unit uptake (p = .069); unallocated points share −0.19 (p = .099).
- Same on S-27 and v1.12+.

**Session PC1** (result 1 above):
- within person, unallocated points share −0.048 per SD (p = .022);
- between person, unallocated points share −0.058 per SD (p = .034).

Without decision speed (X3), the within-person missions term is −0.58 (p = .011) and the between-person
queue term −18.5 s (p = .028). The within-person queue term is null (+4 s).

**Payoff, all four metrics** (uptake, game + run fixed):

| | eff | z | bshare | best |
|---|---|---|---|---|
| within person | −0.07 (p = .71) | −0.39 (p = .61) | −0.09 (p = .70) | −0.09 (p = .67) |
| between person | +0.25 (p = .11) | +1.03 (p = .15) | +0.31 (p = .10) | +0.30 (p = .13) |

Between person every metric agrees in direction, and every within-person term is about 0. That is round 1's
pattern again, slightly weaker here because of the game + run adjustment.

**Is the between-person payoff carried by throughput?** Adding the session's unallocated-points share
shrinks the between-person term by 84–105% on every metric (eff 0.25 → 0.04; z 1.03 → −0.05). But the
bootstrap intervals are very wide (eff [−1.0, 2.5]; bootstrap p .09–.11), and the two orders disagree:
SF ≈ 0, TF ≈ 1. Unallocated points are also part of the score by definition, so some of this is
accounting rather than mechanism. Read it as *consistent with* "reliance pays between people by
clearing the queue", not as shown.

### C3 · Three-type vs single-type missions (within person, decision level)

**Three-type (413 decisions):**
- full completion: OR 1.10 [0.65, 1.86] (p = .72). Following abandoned work into residuals: OR 1.09;
- decision time: **cards much faster** (see the candidates).

**Single-type (181 decisions):**
- full completion: OR 0.43 [0.13, 1.41] (p = .16);
- decision time: cards slightly *slower*, log b +0.34 (p = .16).

Median net decision time:

| | single-type | three-type |
|---|---|---|
| card | 5.2 s | 6.6 s |
| manual | 5.3 s | 12.1 s |

Card × three-type interaction: completion OR 1.61 (p = .26); time −0.81 (p < .001). **The card buys
speed on large missions and nothing on small ones; it buys completion on neither.**

### C4 · Opposite: is manual better on single-type missions?

The direction is consistent, but no S-all test is significant:
- full completion: OR 2.35 [0.71, 7.79] (p = .16). On v1.12+: OR 5.35 [1.30, 22.1] (p = .020);
- completion following residuals: OR 1.94 (p = .30);
- net value share: +0.07 (p = .28).

Both orders and LOO agree in direction (no flip). This is a weak hint, carried by the v1.12+ cohort.

### C5 · Penalty per mission, card vs manual (within person)

- penalty: −1.5 points [−5.3, 2.2] (p = .42);
- penalty ÷ points on offer: +0.003 (p = .78);
- genuine missions only: −1.8 (p = .38);
- v1.12+: the same.

Null. Cards do not reduce the per-mission penalty.

### D · How hard was each game, and is it game, order or scenario?

| game | sessions (run 1) | on offer | arrived | mean score | eff | bshare | best human | best share | never alloc. | queue s | human failures | benchmark failures | uptake |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 | 17 (14) | 2260 | 13 | 978 | .43 | .60 | 1476 | .66 | 2.6 | 116 | 3.2 | 7 | .58 |
| S2 | 16 (3) | 2000 | 14 | 1023 | .51 | .64 | 1568 | .65 | 2.3 | 92 | 4.9 | 9 | .61 |
| T1 | 16 (13) | 1540 | 6 | 940 | .61 | .69 | 1352 | .70 | 0.4 | 87 | 3.1 | 2 | .78 |
| T2 | 17 (3) | 2900 | 9 | 1509 | .52 | .85 | 2275 | .66 | 0.6 | 99 | 4.5 | 12 | .68 |

**For people, S1 was the hardest game and T1 the easiest by score efficiency (.43 vs .61).** Measured
against the best human on each game, the four games look alike (.65–.70). The efficiency gap is
therefore mostly about **how many points each game puts on offer** — Strategic games pour in more missions
than anyone can allocate — and not about how well people played. The benchmark share flatters T2
(benchmark had 12 failures), as round 1 found.

**One model with scenario, game index within scenario, and run** (S-all, GEE):

*Scenario (T − S):*
- eff +0.093 (p = .013) and bshare +0.150 (p = .003). Both orders ✓, LOO no flip, same on S-27 and v1.12+;
- **but in session 1 alone eff is +0.010 (p = .91)**;
- best share +0.021 (p = .65): no difference;
- the per-game z-score has no scenario term by construction.

So the scenario effect on performance depends on the metric. On the human-referenced metric it is absent.
I read it as **a property of the games' points on offer, not of how hard people found the scenario.**

*Game index within scenario (S2 − S1, T2 − T1):* no outcome has a significant game-index term (all
p ≥ .13). These are identified only by the 6 swapped people.

*Run (order / practice):*
- performance: eff +0.02, z +0.14, bshare +0.02, best +0.03, all p ≥ .56. **No detectable practice
  gain in score**;
- queue −18 s (candidate 3) and Suggest consulting +0.13 (candidate 4) do improve;
- card uptake −0.05 (p = .34).

*Scenario × run* (does the practice effect differ by scenario?): null on all nine outcomes (p ≥ .30).

*S-27* (order and pairing coincide, and run = game index): scenario effects as in S-all.
- bshare run2 +0.11 (p = .045). That is "order + pairing", and it is the T2 benchmark artefact: run 2 in
  S-27 includes T2 for the Strategic-first group;
- queue run2 −12 s (p = .15).

*S-6* (descriptive; the one place order and game separate):
- run 2 − run 1: eff +0.04, z +0.23, queue −24 s, consult +0.20, uptake −0.05;
- T − S: eff +0.06, uptake +0.28.

These run in the same direction as the S-all model for queue, consult and uptake.

**Answer to the amendment question.** Once game, order and their combination are in one model:
- *Performance:* what remains of the scenario effect is an efficiency/benchmark difference that is absent on
  the best-human metric and in session 1. That is **game composition** (points on offer and missions
  arriving), not scenario difficulty. There is no order effect on score.
- *Throughput:* Strategic Heavy's extra unallocated missions remain, and are present in session 1 too:
  **scenario, by design.**
- *Reliance:* card uptake and the session reliance score remain higher in Tactical Heavy: **scenario,
  via mission composition.**
- *Operating speed and tactical consulting:* both improve with **order (practice)**, not game.
- Game index within scenario explains nothing detectable. **The six swapped people are the only source of
  that separation, so "game" vs "order" is weakly identified throughout.**

## 3 · Analysis log (in order)

Pre-run plan (written 2026-10-07 before fitting anything):
- **C1** predictors of PC1. Expected directions: gaming none, experience none, early performance +,
  session-1 failures/abandonments −.
- **C2** throughput:
  - unallocated missions, queue time and unallocated points share ~ uptake and ~ session PC1, within and
    between person, game + run fixed;
  - payoff on all four metrics;
  - attenuation of the between-person payoff by unallocated points (person-cluster bootstrap, 1000, seeded).
- **C3** three-type vs single-type, card vs manual: completion and net decision time.
- **C4** single-type, manual vs card.
- **C5** penalty per mission.
- **D** difficulty/order:
  - per-game descriptives;
  - scenario + game index + run GEE (S-all, v1.12+);
  - scenario × run;
  - S-27 (scenario + run);
  - S-s1 (scenario + game index);
  - S-6 descriptive.

Extras, each written before it was run:
- **X1** session-2 PC1 ~ session-1 failures/abandonments | session-1 PC1. Reason: the pooled PC1 contains
  session-1 behaviour.
- **X2** early allocation share as the first-two-minutes measure. Reason: the 120-s score is zero-inflated.
  Flagged in advance as circular.
- **X3** (logged after run 1 showed session PC1, but not uptake, predicting fewer unallocated missions)
  session PC1 without `netSecs`. Reason: decision speed mechanically shortens the queue.

Runs:
1. First full run. The order-split gate refits were rank-deficient: within one order group, scenario ≡ run
   and `C(game)` spans scenario, so the subgroup estimates were arbitrary (one was 1.8e14). **Fixed:**
   `gee_term` now drops the redundant nuisance term (`run2`, else `tact_c`) when the design is rank
   deficient and refuses to fit otherwise. Main estimates were unchanged; only gate columns changed.
2. Added X3 and re-ran. This is the reported output.

Nothing else was tried and dropped.

## 4 · Traps and confounds

- **Order ≡ game pairing (amendment):**
  - game (scenario + game index) is a fixed effect in every session model, with run beside it;
  - S-27 rows are labelled "order + pairing" (there run = game index);
  - S-6 is descriptive with no p-values;
  - every order/game statement says which of the two it is.
- **Small-sample correction:** every GEE uses `cov_type='bias_reduced'`. Person-level tests use Spearman or
  OLS with HC3 errors.
- **Trap 2/3 (composition):** C3/C4 are split by single- vs three-type missions. Decision models carry
  `ndrones` + game. Candidate 5 is attributed to composition.
- **Trap 4 (residuals):**
  - abandoned work → `<id>-R` is counted as transferred: residuals are excluded from arrivals and
    never-allocated counts, and `chain_full` follows work into residuals;
  - C5 is re-run on genuine missions.
- **Trap 5 (forced wait):** decision time is net of each decision's logged reveal delay (`h1_archetypes.parse`).
- **Trap 6 (manual not one behaviour):** not split further here. Round-1 H10 §3b did it.
- **Trap 1:** no injected failures. "Relying" means taking rule-based advice.
- **Buzzer censoring:** queue time treats a never-allocated mission as waiting until the end. Decision
  models carry `time_left`/`elapsed`.
- **Half-weight builds:** P01/P02 rescaled (2 × points − penalty). Their 120-s score is rescaled
  approximately, and only ranks within game are used.
- **Benchmark on T2:** flagged in every `bshare` row. Conclusions rest on eff/z/best agreeing.
- **Mechanical links:**
  - `netSecs` inside the reliance axis (handled by X3);
  - unallocated points inside the score (the mediation caveat);
  - early allocation inside reliance (X2 caveat).
- **Gate notation:** the `notes` column for odds-ratio rows reports subgroup and LOO estimates on the
  log-odds scale.

## 5 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe -u scripts/analysis_round2/wC_analysis.py
```
About 4 minutes, mostly the leave-one-person-out refits. The seeded bootstrap (`SEED = 20261007`) means
the output is identical on a rerun. It writes only `docs/analysis/round2/wC_specs.csv`.
