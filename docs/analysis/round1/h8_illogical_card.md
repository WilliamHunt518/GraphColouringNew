# H8 · How does an illogical card affect use of the strategic assistant, on the spot and after the operator realises it can happen?

Script: `scripts/analysis_round1/h8_illogical_card.py` (shared loader `h5_h8_common.py`). Every
number below is printed by the script. P09 is excluded, leaving 33 participants and 606 strategic
decisions; v1.12+ has 24.

No failures were injected. The "illogical card" is the Conservative card's ungated 15% top-up,
which pads a drone type the mission does not use. It appears in 132 decisions: 129 on single-type
missions, 3 on two-type missions and none on three-type missions. The Aggressive card never pads an
unused type (0 decisions).

## 1 · Primary test

### Detection marker

The marker is the first decision, ordered across both sessions, that meets two conditions:

1. **The operator was shown an illogical Conservative card.** The card has `trueAssets > 0` for a
   type the mission needs 0 of, and the cards had loaded. Decisions with
   `manualBeforeCardsLoaded = True` are excluded, because a manual choice made during the 4–5 s
   reveal never saw the card.
2. **The operator chose manual with zero of every unneeded type the card carried.**

**How choices on illogical cards break down (n = 132).**

| Route | Decisions |
|---|---|
| Aggressive | 35 |
| Manual before the cards loaded | 35 |
| Conservative | 32 |
| Manual from scratch after the reveal | 24 |
| Manual, edited from the Aggressive card | 5 |
| Manual, edited from the Conservative card | 1 |

No manual choice ever kept the unneeded type.

**People with a detection point.** 30 decisions qualify, giving 17 people a detection point: 10 in
run 1 and 7 whose first detection is in run 2.

### Model

- **Sample:** single-type missions only (trap 2).
- **Windows:** before vs after each person's detection point. The detection decision is excluded
  from both windows.
- **Model:** binomial GEE, exchangeable, clustered on participant: `took ~ after + idx + C(scenario)`.

Raw uptake was 77.8% before (n = 18) and 41.2% after (n = 51). Of the 17 people, 9 have decisions
on both sides.

| | OR | 95% CI | p | n |
|---|---|---|---|---|
| **Primary, all** | **0.12** | [0.03, 0.50] | 0.003 | 69 decisions / 17 people |

**Verdict:** SUPPORTED by the letter of the pre-registered threshold, but NOT SUPPORTED once the
selection built into the marker is accounted for. I recommend the supervisor treat H8 as not
supported. The reasons follow, and the pre-registered test itself is reported unaltered above.

**Why the pre-registered test is biased.** The marker is the *first* post-reveal manual choice on an
illogical card. Every earlier post-reveal illogical-card decision by that person is therefore a card
take by construction. 13 of the 18 before-window decisions are such forced card takes (100% uptake).
The after window is not selected this way. That manufactures a drop even if behaviour never changes
(a cousin of trap 7 and of the regression-to-the-mean warning). Three checks show it.

1. **Null calibration.** I ran 1000 simulations. In each, every person's choices on few-type
   missions were redrawn from their own constant uptake rate (and their own pre-emptive-manual
   share), the marker was re-applied, and the same GEE was refitted.
   - **Null distribution:** mean OR is already **0.37**.
   - **Observed against the null (log-OR):** calibrated one-sided p = 0.112 and bias-corrected
     OR = 0.33. This statistic is anti-conservative: 41% of the simulated fits separate, and
     dropping them pulls the null towards 0.
   - **Observed against the null (risk difference):** the risk difference is robust to separation.
     Observed −36.6 pp against a null mean of −26.5 pp gives a calibrated p of 0.297 and a
     bias-corrected effect of **−10 pp**.
2. **Placebo marker.** I used the same definition, with "illogical" replaced by "clean": the first
   post-reveal manual choice on a card that was *not* illogical. It produces a drop of the same
   kind, OR = 0.22 [0.06, 0.84], p = 0.027 (67.6% to 29.9%, 23 people). So the "drop after
   detection" is a property of "the first time I went manual after seeing the cards", not of the
   illogical card.
3. **Restricting to clean single-type cards,** where the marker cannot fire and so cannot select
   either window, is **not estimable**. No person has clean single-type decisions on both sides of
   their detection point.

## 2 · v1.12+ sensitivity

| | Result | n |
|---|---|---|
| Primary | OR = 0.04 [0.01, 0.25], p < 0.001 | 44 decisions / 11 people |
| Null calibration, log-OR | null mean OR 0.49; calibrated p = 0.034; bias-corrected OR 0.09 | |
| Null calibration, risk difference (robust) | observed −46.9 pp vs null −19.8 pp; calibrated p = 0.130; bias-corrected **−27 pp** | |

The log-OR calibration is anti-conservative, as above. This cohort shows a somewhat stronger
residual signal than the full sample, but it is not significant on the robust statistic.

## 3 · Other specifications

All of these inherit the selection bias unless they are calibrated.

| Specification | OR [95% CI] | p | n |
|---|---|---|---|
| + run | 0.09 [0.02, 0.44] | 0.003 | 69 / 17 |
| residual missions excluded | 0.13 [0.03, 0.56] | 0.006 | 67 / 17 |
| within-person (Mundlak, + person-mean of `after`) | 0.12 [0.02, 0.64] | 0.013 | 69 / 17 |
| only people with decisions on both sides | 0.29 [0.07, 1.23] | 0.094 | 41 / 9 |
| per-session detection point (clock restarts each session, + run) | 0.13 [0.03, 0.58] | 0.007 | 64 / 17 |
| marker D_incl (pre-emptive manuals also count) | 0.07 [0.01, 0.31] | 0.001 | 112 / 26 |
| PLACEBO (clean-card manual) | 0.22 [0.06, 0.84] | 0.027 | 121 / 23 |

- **D_incl null calibration:** the null mean OR is already 0.10. Calibrated p is 0.34 on log-OR and
  0.32 on the risk difference, and the bias-corrected risk difference is −5 pp.
- **Strict "edited it out" marker** (D_edit: edited the Conservative card, or added the unneeded
  type and then removed it): only 2 people (P06 and P33), so it is **not testable**.

## 4 · Secondary (exploratory)

**(a) On the spot, within single-type missions: illogical vs clean card.** The model is the GEE with
idx, scenario and run.

| Outcome | Clean | Illogical | OR [95% CI], p |
|---|---|---|---|
| took a card | 55.8% | 50.4% | 0.61 [0.30, 1.25], 0.18 |
| took Aggressive | 23.1% | 26.4% | 0.83 [0.39, 1.77], 0.63 |
| took Conservative | 32.7% | 24.0% | 0.57 [0.24, 1.35], 0.20 |
| manual after the cards loaded | 13.5% | 23.3% | 1.23 [0.45, 3.41], 0.69 |
| manual before the cards loaded (negative control) | 30.8% | 26.4% | 1.63 [0.81, 3.28], 0.17 |
| Conservative, given a card was taken | 58.6% | 47.7% | 0.84 [0.35, 2.00], 0.70 |

n = 52 clean and 129 illogical decisions. In v1.12+, "took a card" gives OR = 0.40 [0.15, 1.05],
p = 0.062.

The direction is consistent: less Conservative and more post-reveal manual on illogical cards. None
of it is significant. One caveat about what "clean" means: a single-type card is clean only when
both unused types have a reserve of 6 or fewer (floor(0.15 × r) = 0), which happens at high-load
moments. So clean against illogical is also partly a reserve-depletion contrast (see H9).

**(b) After detection: do operators switch to Aggressive, or leave the card system?** Neither
pattern is cleanly identifiable, because the before window has the same selection as the primary.

- **Shift towards Conservative, not Aggressive.** Card takes after detection are 61.9% Conservative
  (n = 21) against 0% before (n = 14). On illogical cards only, the figures are 72.7% against 0%.
- **The before-window takes were all Aggressive.** All 13 before-window card takes on illogical
  cards were Aggressive. Eventual detectors take Aggressive on 67% of their illogical-card takes
  (n = 24), against 44% for people who never detect (n = 41).
- **Reading.** Detectors may already have been steering around the illogical Conservative card
  before their first manual rejection, which the marker cannot see. There is no evidence of a
  switch *to* Aggressive after detection.

**(c) Is detection earlier in session 2 than session 1?** Not testable. Only 1 person detected in
both sessions. Of the 10 people exposed in both runs:

| Pattern | People |
|---|---|
| Detected in session 1 only | 0 |
| Detected in session 2 only | 2 |
| Detected in both | 1 |
| Detected in neither | 7 |

Descriptively, detection happens at the first post-reveal exposure in most detecting sessions
(median 0 prior exposures in both runs), and it is almost entirely a Strategic Heavy event: 17 of
the 18 detecting sessions. Median time to detection was 187 s in run 1 and 95 s in run 2, but these
are unpaired and confounded with scenario.

**(d) Link to H5: do people who noticed show a larger drop in strategic trust?** All comparisons are
Mann–Whitney.

| Group | Δ strategic trust, yes vs no | p | rank-biserial |
|---|---|---|---|
| behavioural detector, ever (17 vs 16) | −0.96 vs −0.55 | 0.21 | −0.26 |
| **first detection in run 2, i.e. between the two surveys (7 vs 26)** | **−2.05 vs −0.42** | **0.008** | **−0.67** |
| any detection in run 2 (8 vs 25) | −1.83 vs −0.42 | 0.014 | −0.59 |
| same, tactical-first group only (8 vs 8) | −1.83 vs −0.69 | 0.083 | −0.53 |
| over-allocation mention in debrief (`OVERALLOC`, coded debriefs, 10 vs 16) | −1.40 vs −0.51 | 0.12 | −0.38 |

Two dose measures point the same way, and both vanish once order is held constant:

- **Number of run-2 detections:** ρ = −0.405 [−0.665, −0.057], p = 0.019. Partialling out scenario
  order gives ρ = −0.24, p = 0.18; within the tactical-first group alone, ρ = −0.31, p = 0.24.
- **Change in illogical cards seen:** ρ = −0.32 (p = 0.067). Partialling out order gives +0.03.

The detection result is the pattern H8 predicts, but it is confounded with scenario order. A first
detection in run 2 only happens to tactical-first people (run 2 = Strategic Heavy), and that group's
trust drops more anyway (H5 §3h). Within that group the effect keeps a moderate size
(rank-biserial −0.53) but is not significant at n = 16.

**(e) Validating the behavioural marker against the debriefs.** This uses only the 26 participants
with coded debriefs.

| | Mentions over-allocation | Silent |
|---|---|---|
| Detector | 8 | 6 |
| Non-detector | 2 | 10 |

The mention rate is 57% for detectors against 17% for non-detectors (Fisher OR = 6.7, p = 0.051).
8 of the 10 `OVERALLOC` people are behavioural detectors; P13 and P20 are not. The marker is
plausibly tracking real noticing, though the two markers are far from identical.

## 5 · Analysis log (in order)

1. **Built the decision table** with unneeded types, the chosen allocation, `editedFromStrategy`,
   the `manual_allocation_edited` trail and `manualBeforeCardsLoaded`. It is asserted identical to
   the builder's table.
2. **Tabulated routes on illogical cards.** No manual choice ever kept the unneeded type, and only 1
   edit-from-Conservative exists. The strict edit marker is therefore untestable, and the main
   marker is "post-reveal manual dropping the type".
3. **Ran the primary as specified:** OR 0.12, p = 0.003.
4. **Selection check:** 13 of 18 before-window decisions are forced card takes.
5. **First null simulation:** it returned NaN, because separated GEE fits produce non-finite
   coefficients. I fixed this by dropping non-finite or |b| > 10 fits and adding the pooled risk
   difference as a separation-robust statistic. Both are reported.
6. **Calibrated null:** p = 0.11 on log-OR and 0.30 on the risk difference (all participants).
7. **Clean-only restriction:** not estimable (0 people on both sides).
8. **Further specifications:** + run, residuals excluded, Mundlak, both-sides only, per-session
   detection point, D_incl (plus its own null).
9. **Placebo marker** (clean-card manual), added after the fact: it shows the same drop.
10. **Secondary analyses:** on-the-spot contrasts, Aggressive vs Conservative after detection,
    session-2 timing, the H5 link (with order controls added after seeing the order effect in H5),
    and marker validation.

## 6 · Traps from §2

- **Trap 1:** the illogical card is the ungated top-up, not an injected failure.
- **Trap 2:** every contrast is within single-type missions.
- **Trap 3:** the binary "types needed" variable is why single-type is the stratum used.
- **Trap 5:** manual choices made before the cards loaded are excluded from the marker, since the
  operator never saw the card. The D_incl variant shows the effect of including them, and they
  serve as a negative control in 4(a).
- **Trap 6:** the routes within manual (pre-emptive, from scratch, edited) are separated in §1.
- **Trap 7 and regression to the mean:**
  - the detection decision is excluded from both windows;
  - the selection that the marker definition creates is diagnosed and calibrated by simulation, and
    checked with a placebo;
  - composition differs across windows (illogical share 0.89 before vs 0.63 after; run-2 share 0.39
    vs 0.59), and idx, scenario and run are adjusted for.
- **Trap 8:** debrief mentions are used only as a person-level validation.
- **Trap 9:** n = 17 people with a detection point, of whom 9 have decisions on both sides, so
  power is very low.

## 7 · Where H5 and H8 connect, and contradictions or refinements of brief Finding 5 and the synthesis page

- **The two results converge on one picture.** Card *outcomes* in session 1 do not drive the trust
  drop (H5 null). What lines up with the drop is *seeing the flaw in the window between the two
  surveys*, which happens when session 2 is Strategic Heavy. The crossover's scenario term on
  strategic trust (+0.48, p = 0.042) is the aggregate form of this. Neither result can separate
  "noticed the flaw" from "played Strategic Heavy second" with 16 people per order.
- **Brief Finding 5 ("seeing one has no detectable effect on later decisions").** This is upheld.
  The one pre-registered test that appears to contradict it does so through a selection artefact.
  The bias-corrected effect after detection is −10 pp (all) to −27 pp (v1.12+), non-significant, so
  a modest effect cannot be excluded.
- **Synthesis page, "Does an illogical recommendation change anything afterwards?".** Its tests use
  *exposure* (any illogical card shown). This round adds a *detection*-based test, and it should be
  reported with the placebo and the null calibration, or it will read as a strong positive.
- **"The simple rules produce visibly odd cards".** There is a mild, non-significant on-the-spot
  shift away from Conservative and towards post-reveal manual on illogical cards (OR 0.61 for
  taking a card; 0.40, p = 0.062, in v1.12+). It is consistent with the existing "within few-colour
  missions" null.
- **New descriptive points the page does not have:**
  - no operator ever kept the padded type when building manually;
  - detection is almost exclusively a Strategic Heavy event (17 of 18 detecting sessions);
  - people who later detect were already taking Aggressive more often on illogical cards (67% vs
    44%).

## 8 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h8_illogical_card.py
```

The script is deterministic (simulation seed 20261007; 1000 + 500 + 500 null simulations) and takes
about 1.5–2 minutes. It reads `Results/Participants/*.json` and
`Results/Narration/*_s1/quotes.json`, and writes nothing.
