# H2 · Does the cost of checking explain the trust gap between the tiers?

Scripts: `scripts/analysis_round1/h2_verification_cost.py` (primary, robustness, secondaries),
`scripts/analysis_round1/h2_fragility.py` (post-hoc fragility checks). Data read-only; P09 excluded.

## 1 · Primary test

**Operationalisation.** The pre-registered text asks for keep-unmodified to rise with plan size,
inspection time per drone to fall with plan size, "with the interaction significant", but does not
name the interacting terms. I fixed the following before fitting any model (each GEE exchangeable,
clustered on participant, controlling for `C(scenario) + C(run)`, plan size z-scored):

| Component | Model | Sample | Predicted |
|---|---|---|---|
| A | keep-unmodified ~ size | all 630 confirmed tactical plans | OR > 1 |
| B | net inspection s per drone ~ size | 486 consulted plans | b < 0 |
| C | keep ~ size × inspection-per-drone | 486 consulted plans | interaction OR < 1 |

- *keep-unmodified* = consulted via Suggest **and** deployed unmodified — the definition of
  `accept` in `load_people()`, which the brief quotes as "kept it unmodified".
- *size* = distinct drones in the agent plan × tasks.
- *net inspection* = last non-recovery `tactical_suggest_used` → `tactical_confirmed`, **minus the
  forced Suggest reveal**. `MapDisplay.tsx` adds one (task, drone) pair per 1000 ms. Deploy is
  disabled until the reveal finishes (`disabled={!canDeploy || isSuggestLoading}`), so the raw
  interval contains `entries × 1 s` of unavoidable wait. This is the tactical equivalent of trap 5.
  Only 1 of 486 intervals came out below the reveal time, and it was clipped to 0.
- Support requires all three components to be significant in the predicted direction. The p
  handed to the Holm family is therefore the intersection–union p = max(pA, pB, pC).

**Result (all 33):**

| Component | Effect per SD of size | 95% CI | p |
|---|---|---|---|
| A (keep, all plans) | OR 1.76 | [1.27, 2.44] | .0008 |
| B (inspection per drone) | −0.26 s/drone | [−0.41, −0.11] | .0006 |
| C (size × inspection) | interaction OR 0.70 | [0.52, 0.94] | .019 |

n = 630 / 486 plans, 33 people.

- **Primary p (intersection–union) = .019.**
- **Verdict: SUPPORTED as pre-specified — but the support is fragile and the mechanism reading
  does not hold (see §3).** If the supervisor reads the hypothesis as "keep among consulted plans",
  component A reverses (OR 0.67, p = .010) and the verdict becomes NOT SUPPORTED. I flag this for
  the supervisor's decision.

## 2 · v1.12+ sensitivity (n = 24)

| Component | Effect | 95% CI | p |
|---|---|---|---|
| A | OR 1.89 | [1.25, 2.86] | .0025 |
| B | −0.26 s/drone | [−0.43, −0.10] | .002 |
| C | interaction OR 0.63 | [0.48, 0.84] | .0017 |

- Intersection–union p = .0025, **SUPPORTED**, with the same caveats.
- Component A among consulted plans only: OR 0.41 [0.30, 0.56]. That is the reverse direction.

## 3 · Secondary results (exploratory)

**What actually drives component A.**
- Larger plans are **consulted** more: Suggest pressed, OR 2.52 per SD [1.89, 3.35]. Within
  person, the consult rate is higher on above-median plans for 22 of 33 people.
- Once consulted, larger plans are **modified more, not less**: keep | consulted OR 0.67 [0.50, 0.91].
- Almost everything consulted is kept (468 / 486 = 96.3%). Only 18 consulted plans were edited,
  by 8 people, and P04 alone accounts for 6 of them.
- So "more deference on big plans" is a consult-or-build-by-hand effect, not a lighter check
  before keeping.

**Component B is mostly a ratio artefact of near-constant checking.**
- Absolute net inspection hardly moves with size: +0.62 s per SD [−0.14, 1.38], p = .11.
- Median net inspection is 2.7 s (IQR 1.3–8.0) whatever the plan size.
- Elasticity of log(1 + net) on log(size) = 0.17 [0.07, 0.27]. Checking is roughly flat, so it is
  *proportionally* much less on big plans. That is the substantive version of "bigger plans get
  proportionally less checking", and it holds.
- The per-drone fall is driven by the drone count (b = −0.30, p = .0001). It does not depend on
  the task count (b = 0.02, p = .82).

**Component C does not survive removing editing time.**
- Modifying a plan takes time: median net time 5.7 s for modified plans against 2.7 s for kept
  ones, with a median of 3 edits. So "inspection" and "not keeping" are mechanically linked.
- Re-measuring checking as the time from the end of the reveal to the operator's *first* act (an
  edit or Deploy) gives an interaction OR of 0.54 [0.09, 3.13], p = .49.
- Leave-one-person-out: dropping P13 (one 78 s, 10-edit plan) gives p = .22, and dropping P21
  gives p = .08.
- C rests on 18 events in 8 clusters, where sandwich standard errors are unreliable.

**Relative checking cost vs the person's trust gap** (person level, n = 33, ρ needs ≳ .48 for 80%
power):
- ρ(tactical net inspection per drone ÷ strategic net card-decision time, trust gap T−S) = **−.51**,
  p = .002. That is the **opposite** sign to the mechanism, which predicts that people for whom
  tactical checking is relatively costly trust tactical relatively more.
- The correlation comes from the strategic side: ρ(strategic net card-decision time, gap) = +.45,
  p = .009, against ρ = −.03 for tactical inspection per drone.
- People who deliberate longer over strategy cards trust the strategic assistant less relative to
  tactical. Slow card decisions look like a *symptom* of distrust, not a cause of it.
- Card-preview dwell (ρ = .09) and A↔C toggling are uninformative. Toggling is almost absent: a
  mean of 0.04 toggles per decision.

**The premise's timing.**
- After the forced waits, operators spend *less* time on a tactical plan (median 2.85 s per person)
  than on a strategy card (6.0 s). Wilcoxon p < .0001.
- The tactical figure excludes the reveal, which lasts about 9 s on average. Operators may watch
  the plan fill in during that time, or, as P10, P15, P24 and P30 describe, go back to the primary
  window.
- So the logs cannot say how much of the reveal was spent inspecting. They can only say that, once
  Deploy is available, checking is brief and does not scale with the plan.

**Session 1 → 2** (crossover, n = 31 with consulted plans in both runs):
- Net inspection per drone fell, run effect −0.38 s/drone [−0.60, −0.16], p = .002. It fell for 25
  of 31 people.
- Net inspection in seconds fell by 2.5 s [−4.2, −0.8], p = .007.
- Keep-unmodified rose by 6.5 points [−1.3, +14.2], p = .10. It rose for 17 and fell for 9.
- The direction is as predicted, but only the checking side is clear. The scenario had no effect
  on inspection (p = .97).

**Link to H6 codes:**
- The 9 people who *say* they could not (or chose not to) check the tactical plan have shorter
  net inspection: median 2.25 s against 3.33 s, MWU p = .055.
- They keep plans at a similar rate: .85 against .79, p = .35.
- Their questionnaire trust gap is no larger: .25 against .83, p = .54.

**What H2 cannot separate.** This analysis cannot distinguish the *cost of checking* from the
*visibility of flaws*.
- The strategic card has a visible flaw: the Conservative card's ungated 15% top-up, which adds
  drone types the mission does not use. The tactical plan has no planted flaw (ε = 0 everywhere:
  509 of 509 logged `tacticalFailureFired` are false, and 0 of 649 `agentSuggestionWasBad`).
- Short checking of tactical plans is equally consistent with three explanations:
  - checking is costly, so it is skipped;
  - nothing visibly wrong ever turns up, so checking is learned to be unnecessary (the
    session-1→2 drop fits this too);
  - plans are trusted, so they are not checked.
- The timing data cannot separate these. H6 (stated reasons) and H8 (detection of the illogical
  card) bear on the visibility side.

## 4 · Analysis log (in order)

1. **Exploration** (scratch script, before any model).
   - Counted confirmed and consulted plans and edits after the last Suggest.
   - Found the 96% keep rate among consulted plans, and that raw suggest→confirm time minus the
     reveal is rarely negative.
   - **Disclosure:** I saw the near-ceiling keep | consulted rate *before* fixing the definition
     of A. I chose the all-plans definition because it is the brief's `accept`. The alternative
     is reported (§3), and it reverses the sign.
2. **Read `MapDisplay.tsx`.**
   - Found the 1000 ms per-entry reveal and the Deploy gate.
   - Checked `git log -L`: the step has been 1000 ms since 8332ad1 (June 2026), so it is constant
     across all builds analysed.
   - Defined net inspection on that basis.
3. **Fixed A/B/C and the intersection–union p**, then ran the primary on all 33 and on v1.12+.
4. **Robustness on the components.**
   - A among consulted plans only (reverses).
   - Consult ~ size.
   - Game fixed effects instead of scenario: A holds, OR 1.79.
   - Residuals excluded: A holds, OR 1.86.
   - Elasticity, absolute net time, and raw time with the reveal *not* removed (elasticity 0.47 —
     the reveal alone manufactures size scaling).
   - Pre-action time.
   - Drones vs tasks separately.
   - Decision-level Spearman of size and net time: ρ = .14.
5. **`h2_fragility.py`** (after seeing C).
   - Listed who holds the 18 modified plans.
   - Ran leave-one-person-out on C.
   - Split consult and keep within person.
6. **Secondary 1** (person-level ratio vs trust gap) and its components.
7. **Secondary 2** (crossover on run).
8. **Secondary 3** (H6 stated-reason codes vs behaviour), once the H6 coding was frozen.

Not attempted:
- A model with person-mean-centred size, because the within-person split in step 5 answers the
  same question descriptively.
- Any use of the cursor recordings.

## 5 · Traps that applied

- **1 (no injected failures):** confirmed in the logs (above). It is the reason checking cost and
  flaw visibility cannot be separated.
- **5 (forced wait):**
  - Tactical analogue: the Suggest reveal (1 s per entry, Deploy locked) is removed from
    inspection time.
  - Strategic: card decision time uses `latencyMs − deployEnabledAtMs`, falling back to the
    largest `revealDelayMs` in pre-v1.12 logs that lack the field.
  - Without the correction, inspection appears to scale with size (elasticity 0.47), but that
    scaling is the reveal.
- **4 (residuals):** the result is unchanged with residual missions excluded.
- **Game confound:** the result is unchanged with game fixed effects.
- **9 (n = 33):**
  - The person-level secondaries are underpowered, except the ρ = −.51 result.
  - Component C is effectively 18 events in 8 people.
- **2, 3, 6, 7:** these concern strategic card composition, manual choices and event studies, and
  do not apply to the tactical models.

## 6 · Agreement with H6 and with the current brief

**Brief, Finding 4.**
- Agreed:
  - Tactical plans are consulted and kept far more than cards are taken.
  - Operators spend little time checking them: about 3 s after the reveal, flat across plan size,
    and falling over sessions.
  - The NOCHECK quotes describe real behaviour.
- Contradicted (two points):
  - The brief's framing — "a tactical plan has to be read drone by drone, so operators defer to it
    when there is no time" — implies more drones, more deference *given a plan*. The logs show the
    opposite once a plan is consulted (OR 0.67). The size effect is in *whether* they consult.
  - The person-level link runs the wrong way: relative checking cost does not predict a larger
    trust gap. Slow strategic decisions go with a *larger* gap, which reads as distrust driving
    deliberation.

**H6.**
- Spoken reasons for the tactical tier are mostly **speed** (20 of 33 give it for tactical), not
  inability to check (9 of 33).
- Visible errors are cited almost only about the **strategic** tier (12 against 1).
- Two debriefs argue the *reverse* of H2:
  - P05: tactical trusted *because* it is easier to check.
  - P14: checked the tactical plan *more* because it is drone-by-drone, while cards are checkable
    "in one glance".
- So the spoken evidence leans towards flaw visibility and speed, not checking cost, as the reason
  for the tier gap.
- The checking-cost account is present (P22, P24, P27, P35), but it is a minority account.

## 7 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h2_verification_cost.py
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h2_fragility.py
```
(Secondary 3 reads `docs/analysis/round1/h6_codes.csv`.)
