# Workstream D · Trust — separating order from game

Scripts: `scripts/analysis_round2/wD_trust.py` (all tests) and `wD_common.py` (session table, built
on round-1 `h5_h8_common.py` / `h5_trust_drop.py` and `study_analysis.load`). Every test is a row in
`docs/analysis/round2/wD_specs.csv` (125 rows, 11 of them extras). P09 excluded; n = 33 people,
66 sessions; S-v112 = 24 people. Trust = mean of the six 1–7 items of the post-session survey
(`trust_strategic` / `trust_tactical`). All GEEs use the small-sample (bias-reduced) errors; all
person-level OLS uses HC3 robust errors.

**The design in one table.** Strategic trust (mean, n) by the game played and when it was played:

| Game | Played first | Played second |
|---|---|---|
| Strategic Heavy, game 1 (S1) | 4.64 (14) | **3.00 (3, swapped)** |
| Strategic Heavy, game 2 (S2) | **6.00 (3, swapped)** | 4.05 (13) |
| Tactical Heavy, game 1 (T1) | 5.04 (13) | 4.56 (3, swapped) |
| Tactical Heavy, game 2 (T2) | 5.44 (3, swapped) | 4.60 (14) |

The bold cells are the six swapped participants — the only place where order and game come apart.

## 1 · Candidates

**One, and it is a replication rather than a new finding.**

**Strategic trust falls from the first session to the second, in both scenario orders (D2a.run2).**
GEE, trust_s ~ scenario + run: run 2 vs run 1 b = −0.78 [−1.24, −0.32], p = .0009, 66 sessions / 33
people. With game as a fixed effect (D2b.run2) it is larger, −1.23 [−2.09, −0.37], p = .005.
- *Gates:* S-s1 not applicable (a run effect cannot exist in session 1); mean change is negative in
  **both** orders (Strategic Heavy first −0.29, Tactical Heavy first −1.26); leave-one-person-out
  range −0.84 to −0.66 (game-adjusted −1.45 to −0.98); nobody flips the sign.
- *Mechanism:* with a session's experience behind them, operators have the time and familiarity to
  check the cards, and checking turns up the over-allocation. Quotes: `P15/trust_trajectory/1985`
  ("in the second round … now I can check … I can find that it makes mistakes"),
  `P33/trust_trajectory/1785` ("in the first test, I don't have enough time to notice it"),
  `P32/scenario_comparison/1497` (in the second session "I had more time to be checking" — P32 is a
  swapped participant whose second session was *Tactical* Heavy, and still fell 3.5 points).
- *Caveat:* round 1 (H5 §3h) already reported this run effect; it is in the brief. What round 2 adds
  is that it survives game fixed effects, and that the swapped six do not overturn it.
- Tactical trust shows no fall (D4a.run2 +0.16, p = .25; game-adjusted +0.26, p = .056, the other way).

**Borderline — probably will not survive the round-wide correction:** the scenario effect. Strategic
trust is about half a point lower after a Strategic Heavy session than after a Tactical Heavy one,
within person: +0.48 [+0.02, +0.94], p = .039 (D2a.tac); with game fixed effects +0.48 [+0.03, +0.92],
p = .036 (D2b.tac_c). Same direction in session 1 alone but small and null (D1a: +0.23 [−0.60, +1.07],
p = .57); same direction on S-v112 but null (+0.41, p = .17); no one flips its sign (LOO +0.36 to +0.58).
Mechanism: Strategic Heavy is full of single-type missions, where the Conservative card visibly pads an
unused drone type (`P19/trust_trajectory/1907`: "over-assigning blue drones to blue-only missions").
But see D3: the *amount* of such exposure does not predict trust once the scenario is accounted for.

## 2 · Everything else

### D1 · Session 1 only (between-person; no order, no carry-over)

- Strategic trust after a Tactical Heavy first session minus after a Strategic Heavy one:
  **+0.23 [−0.60, +1.07], p = .57** (D1a; 5.11 vs 4.88). Adjusting for game index: +0.22, p = .59
  (D1b). v1.12+: +0.07, p = .89 (D1c). Without the swapped six: +0.40, p = .40 (D1e).
  **So on its own, a single Strategic Heavy session leaves strategic trust only slightly lower — the
  round-1 "drop" is not visible as a between-person scenario difference after one session.**
- Tactical trust in session 1 does not differ by scenario: −0.12, p = .75 (D1d).
- Odd by-product: the six swapped people, who played game 2 first, rated strategic trust higher after
  session 1 (+0.88 [+0.03, +1.74], p = .043, D1b.idx). Six people from the latest cohort (v1.13); a
  game effect and a cohort effect cannot be told apart here. Not interpreted.

### D2 · Scenario vs game vs order

*Definitions.* **Scenario** = Strategic Heavy vs Tactical Heavy. **Game** = one of the four fixed
mission streams (S1, S2, T1, T2). **Order** = which scenario came first. **Run** = first vs second
session. A **fixed effect** for game means comparing sessions only within the same game.

- **Order + pairing (S-27, where they coincide):** the change in strategic trust is 0.94 points more
  negative for Tactical-first people (who play S2 second) than for Strategic-first people (D2c,
  −0.94 [−1.75, −0.13], p = .026; −0.99 vs −0.05; LOO −1.06 to −0.73). This is the round-1 pattern.
- **The swapped six (S-6, descriptive only):** Tactical-first swapped people (who play **S1**
  second) also fall more: −2.44 vs −1.44 (D2d; −0.33, −4.83, −2.17 against −3.50, 0.00, −0.83).
  So "Tactical Heavy first → bigger drop" holds whichever Strategic game came second.
- **Game at a fixed position (descriptive, cells of 3):** S2 is rated *higher*, not lower, than S1,
  both when played first (6.00 vs 4.64, D2e.first) and when played second (4.05 vs 3.00, D2e.second).
  **Position at a fixed game:** Strategic Heavy played second is rated lower than played first for
  **both** games (S1: 3.00 vs 4.64, D2h.S1; S2: 4.05 vs 6.00, D2h.S2). The Welch p-values on these
  rows (e.g. .0008 for D2e.first) are not meaningful — three near-identical ratings give a tiny
  variance — and the rows should be read as directions only.
- **Game fixed-effect model (S-all):** scenario +0.48 (p = .036), run −1.23 (p = .005), game 2 vs
  game 1 +0.71 [−0.15, +1.57], p = .10, scenario × game index −0.27, p = .77 (D2b). Adding order as a
  person-level term: −0.56, p = .28 (D2g). The game-index and run terms are separated **only** by the
  six swapped, so their split is fragile; their sum is not.
- **Verdict on the central question:** the drop sits with *order* (the run effect plus the scenario
  effect, which add up to a large fall exactly when Strategic Heavy comes second) and **not with game
  S2** — if anything S2 earns more strategic trust than S1. The evidence that separates them rests on
  six people (three per cell) from one late cohort, so this is a direction, not a result.
- **Tactical trust** has no scenario, game, order or pairing effect (D4a/b/g/f, D4c S-27 +0.34,
  p = .29; S-6 +0.17).

### D3 · What in a session predicts that session's strategic trust (within person)

Each predictor gets: **M1** within-person GEE with run; **M2** the same plus game fixed effects (the
headline); **M3** M2 on v1.12+; **M4** session 1 between-person with game fixed effects; **M5** change
on change within each order. "Within person" means comparing a person's two sessions with each other.

| Predictor (session) | M1 b, p | M2 b, p (game FE) | M4 session 1 b, p |
|---|---|---|---|
| share of single-type missions | −1.19, .040 | −1.99, .51 | +3.11, .43 |
| dominated Conservative cards seen | −0.08, .043 | +0.05, .76 | +0.05, .70 |
| illogical Conservative cards seen | −0.13, .062 | −0.07, .80 | −0.04, .91 |
| card missions failed/abandoned | −0.13, .60 | −0.09, .70 | +0.20, .39 |
| score efficiency | +0.65, .65 | −0.22, .88 | +1.97, .043 |
| per-game z-score | −0.04, .91 | +0.01, .97 | +0.31, .21 |
| share of near-perfect operator | +1.08, .15 | −0.15, .88 | +1.51, .074 |
| share of best human score | −0.21, .88 | −0.09, .94 | +1.41, .096 |

The three exposure measures "work" in M1 only because they *are* the scenario: Strategic Heavy
sessions have more single-type missions and more odd and dominated cards. With game fixed effects
every one is null, the session-1 sign disagrees for single-type share and dominated cards, and the two
orders disagree for all three. **No session feature predicts its trust rating beyond the game it was
played on.** Performance predicts trust weakly *between* people in session 1 (better scorers trust
more), never within a person. Card failures: within the Strategic-first order the change in card
failures goes with a fall in trust (b = −0.48, p = .003, D3d.M5SF), but the Tactical-first order has
the opposite sign (+0.33) — one cut among ~40 and not interpreted (round 1 found the same
opposite-signed split).

**X1 (extra) — strategic uptake → strategic trust:** within person null (M2 +0.19, p = .88); between
people in session 1 strongly positive (+2.29 per unit of uptake [+1.09, +3.49], p = .0002, both
scenarios, no LOO flip) — the round-1 H1 finding that reliance tracks trust *between* people.

### D4 · Tactical tier

- Tactical trust does **not** track tactical behaviour within person: consult rate M2 +0.48, p = .55;
  keep-unmodified rate +0.24, p = .67; recovery Suggest rate −0.23, p = .78 (and v1.12+ all null).
  Several of these have a single person who flips the sign.
- **Between** people in session 1 it does: consult +1.68 [+0.32, +3.04], p = .015; keep-unmodified
  +1.70 [+0.37, +3.03], p = .013 (both scenarios same sign, no LOO flip). Recovery Suggest: none.
- So both tiers show the same shape: trust and use go together **across people** (a trait), not
  **across a person's sessions**. Between-person rows cannot separate cause from character and are
  not offered as candidates; they repeat round-1 H1.

### D5 · Does trust lead behaviour? (opposite direction)

- Session-1 strategic trust vs the change in card uptake: Spearman ρ = +0.07 [−0.28, +0.40],
  p = .71 (D5a). Adjusting for session-1 uptake (regression to the mean) and session-1 game:
  +0.05 per scale point [−0.05, +0.15], p = .33 (D5b); v1.12+ +0.02, p = .78; S-27 +0.04, p = .43.
  Within Strategic-first only +0.11, p = .044; Tactical-first +0.02, p = .84.
- Tactical: session-1 tactical trust vs change in consult rate +0.04, p = .43; vs change in
  keep-unmodified +0.02, p = .68.
- **X2 (extra)**, uptake on three-type missions only: +0.03, p = .67.
- **Trust after session 1 does not predict how use changes in session 2.** Combined with round 1
  (change in trust does not track change in uptake, ρ = +.16), trust and use move separately within a
  person in both directions.

## 3 · Analysis log (order run)

Extras were declared in this file before any variant ran:

- **X1 (extra).** Strategic card uptake → that session's strategic trust, within person, with the same
  battery as D4. Reason: D4 asks whether *tactical* trust tracks tactical behaviour; without the same
  model on the strategic tier there is nothing to compare the tactical answer with.
- **X2 (extra).** D5 repeated with card uptake on **three-type missions only**. Reason: the scenario
  switch between sessions changes the mission mix (Strategic Heavy has far more single-type missions,
  where uptake is lower), so raw change in uptake is mostly the scenario switch; uptake within a fixed
  composition is the cleaner behaviour to ask trust to predict.

Run order:
1. Built the session table (`wD_common.build`): asserts 33 people / 66 sessions, no missing trust,
   and that the swapped set is exactly those whose game index ≠ run. Decision table re-asserted
   row-identical with the builder (round-1 check).
2. D1a–e (session 1). 3. D2a, D2b, D2g, D2f and D4a/b/g/f (crossover and game-FE models on both
   trust scales). 4. D2c/D4c (S-27), D2d/D4d (S-6). 5. D2e/D2h (game at fixed position, position at
   fixed game; descriptive). 6. D3a–e4 batteries, then X1. 7. D4c–e batteries. 8. D5, D5t, D5u, X2.
9. Quote check. 10. After the first run I added gate values to the D2 crossover rows (they had been
   left as na) and leave-one-out / within-order checks to the session-1 M4 rows; no estimate changed.
   A naming clash (`C` module vs patsy `C()`) crashed the very first run before any output.
11. Re-ran: the CSV is byte-identical across runs.

No variant here is event-defined, so no null simulation was needed.

## 4 · Traps and confounds

- **Order = game pairing (round-2 §1).** Handled with S-27 ("order + pairing"), S-6 (descriptive),
  game fixed effects, and the 2 × 2 cell table above. Game index and run are separable only through
  the six swapped, who are also the latest cohort (v1.13) — so any "game" effect from them may be a
  cohort effect.
- **Scenario sets exposure.** Single-type share, odd and dominated cards are largely fixed by the game
  (trap 2): the within-person exposure tests are only meaningful with game fixed effects (M2).
- **Trust timing (round-1 H5 §3d).** Trust is surveyed after each session, so each session is
  matched with its own trust rating (D3/D4); D5 uses session-1 trust before session-2 behaviour.
- **Regression to the mean in change scores:** D5 adjusts for session-1 behaviour.
- **P01/P02 half weights:** raw score rescaled ×2 for z-score, near-perfect share and best-human
  share; score efficiency needs no rescale. Near-perfect share is flagged unreliable on game T2.
- **No injected failures (trap 1):** "bad experience" is ordinary mission failure.
- **n = 33 (trap 9):** person-level tests detect only |ρ| ≳ .47; within-person estimates with game
  fixed effects use little variation and have wide intervals (e.g. single-type share ±6).
- **Descriptive rows (D2d, D2e, D2h)** use cells of three; their p-values are reported for
  completeness but should not enter the correction as if they were tests. Flagged in `notes`.
- Traps 3–8 (residuals, forced wait, manual heterogeneity, debrief timing) do not bear on
  session-level trust; quotes are from the post-session debrief (trap 8).

## 5 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wD_trust.py
```

About 30 s; deterministic. Reads `Results/Participants/*.json`, `Results/Narration/*_s1/quotes.json`
and `docs/reports/smart_benchmark.json`; writes only `docs/analysis/round2/wD_specs.csv`.
