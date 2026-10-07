# Analysis round 1 — consolidated results

*Supervisor's summary of the ten pre-registered hypotheses (`docs/analysis/HYPOTHESES_ROUND1.md`),
tested by seven agents on 2026-10-07. Every number here was re-run independently by the supervisor,
and the participant data was checked against an off-repo SHA-256 backup after every agent (unchanged
throughout). The per-hypothesis reports in this folder have the full detail; `SUPERVISOR_LOG.md` has
every check and caveat in the order they came in.*

## The short version

**No pre-registered primary test survives correction across the ten.** That is not the same as
"nothing was found": three results change how the existing findings should be read, and two
hypotheses produce informative nulls with good power. The most useful outcomes are:

1. **Recovery (H3):** within the same person, pressing Suggest on a fixable failure goes with far
   fewer abandoned missions — but the effect is *attempting* a fix versus giving up, not Suggest
   versus fixing by hand. Closest to surviving correction (adjusted p = .08).
2. **Momentary workload does not push people onto the assistant (H9):** a well-powered null.
   The "when overloaded I hand over" story in the debriefs is not visible at the moment of decision.
3. **Reliance is one continuous trait, not types (H1):** a single axis — general reliance on the
   assistants across all three tiers — stable from session 1 to 2, but no distinct archetypes.
4. **Better operators rely more; relying more does not make a given operator better (H10).**
5. **Two existing claims in the brief are wrong or overstated** (the benchmark gap, the trust-drop
   framing), and one needs reframing (recovery). See "Changes to the brief" below.

## Terms used in this document

Each term is defined once here, in plain words, with what its number means.

| Term | What it means here |
|---|---|
| **Primary test** | The one test per hypothesis fixed *before* any agent looked at the data. Only these decide a hypothesis's verdict. |
| **Exploratory / post hoc** | Any analysis chosen after seeing data. Useful for ideas, but cannot confirm anything; always labelled as such. |
| **Within-person** | Comparing an operator with *themselves* (e.g. their card missions against their own manual missions). Removes "some people are just better". |
| **Between-person** | Comparing *different* operators (e.g. high-reliance people against low-reliance people). Cannot tell cause from character. |
| **Odds ratio (OR)** | How much an outcome's odds change. OR 1.00 = no change; OR 0.40 = odds cut to 40% of what they were; OR 2.00 = doubled. Odds are not probabilities: going from 50% to 67% is ×2 in odds. |
| **95% interval** | The range of effect sizes consistent with the data. If an OR interval contains 1.00, the effect cannot be told apart from none. |
| **p** | How surprising the result would be if there were truly no effect. p < .05 is the conventional bar for a *single* test. |
| **GEE** | The regression used for decision-level data. It allows for each operator contributing many decisions, so one prolific operator cannot dominate. |
| **Small-sample correction** (bias-reduced / Mancl–DeRouen) | With only ~33 operators, the standard GEE error bars are too narrow: they flag a non-existent effect ~9.5% of the time instead of 5% (measured by simulation in H7). The corrected version widens them. **All p-values below use it where it applies.** |
| **Holm correction / adjusted p** | Running ten tests raises the chance that one passes by luck alone. Holm raises each p-value so that the ten together have only a 5% chance of any false pass. An *adjusted p* below .05 is a result that survives that. |
| **Sensitivity cohort (v1.12+)** | The 24 participants who all played identical game versions. Primary results use all 33; each is re-run on the 24 to check it does not depend on early builds. |
| **Detectable effect** | The smallest true effect the test had an 80% chance of catching. A null only means "no effect this big or bigger", so this number is what makes a null informative. |
| **Spearman ρ** | A correlation between two rankings of people. −1 = opposite order, 0 = unrelated, +1 = same order. |
| **Cohen's κ** | Agreement between two coders beyond what chance would give. 0 = chance, 1 = perfect; ≥ .6 is the usual bar for "reliable". |
| **ΔBIC** | How much better a model with *k* groups fits than one with a single group, penalised for complexity. > 10 is strong evidence for the groups. |
| **Jaccard / ARI** | Stability checks for groups: Jaccard = do the same people group together when the data is resampled (1 = always); ARI = do sessions 1 and 2 produce the same groups (0 = no better than chance, 1 = identical). |
| **Null simulation / calibrated p** | Re-running a test many times on data where we *know* there is no effect, to see what the test produces by itself. A *calibrated p* compares the real result against that, not against the textbook assumption. |
| **Intersection-union test** | A test that needs *all* of several parts to hold; its p is the largest of the parts' p-values. |

## Results

"Corrected p" uses the small-sample correction where it applies. "Adjusted p" is after Holm
correction across all ten. Verdicts apply the support threshold fixed in the plan.

| | Question | Primary result | Corrected p | Adjusted p | Verdict |
|---|---|---|---|---|---|
| **H1** | Do operators fall into distinct types? | One group fits about as well as two (ΔBIC 1.9, needed > 10); groups unstable (Jaccard .76 / .47) and different in session 1 vs 2 (ARI .04) | .42 (session agreement) | 1.00 | **Not supported** — a continuum |
| **H2** | Does the cost of checking explain why tactical is trusted more? | Keeping the plan rises with plan size (OR 1.76) and checking per drone falls; all three required parts in the predicted direction | .065 | .52 | **Not supported** after correction (was p = .019 uncorrected); also fragile to how "kept unmodified" is defined |
| **H3** | In recovery, does Suggest go with fewer abandonments, within person, on fixable failures? | OR 0.40 [0.21, 0.79]: abandonment odds cut by 60% when Suggest was pressed | .008 | .08 | **Supported on its own threshold; does not survive the family correction** |
| **H4** | Is Strategic Heavy's bigger shortfall against the near-perfect benchmark explained by manual work? | Manual rate barely moves the gap: it shrinks 13% (needed 50%) | .33 | 1.00 | **Not supported** |
| **H5** | Does a bad session-1 experience with the cards explain the drop in strategic trust? | ρ = −0.05: unrelated | .78 | 1.00 | **Not supported** |
| **H6** | Do people *say* they prefer the tactical assistant? | 17 prefer tactical vs 6 strategic, but coder agreement κ = .27 (needed ≥ .6) | .035 (sign test) | .31 | **Not supported** — fails the reliability bar, not the direction |
| **H7** | Does attitude to AI predict taking the strategic card? | OR 0.80 per SD of AIAS-4: no effect; detectable only at OR ≈ 2 | .40 | 1.00 | **Not supported** |
| **H8** | Does card use fall once an operator notices an illogical card? | Apparent drop (OR 0.12) is produced by how "noticed" was defined; vs a null simulation it disappears | .30 (calibrated) | 1.00 | **Not supported** — the pre-registered test was invalid (supervisor's specification error) |
| **H9** | Does a fuller queue push operators onto the cards? | OR 1.04 per extra queued mission; could detect OR ≥ 1.14 | .44 | 1.00 | **Not supported** — informative null |
| **H10** | Within a person, does taking a card make the mission more likely to complete? | OR 0.81 [0.54, 1.20]; could detect ≤ 0.58 or ≥ 1.73 | .29 | 1.00 | **Not supported** |

Every primary was also re-run on the v1.12+ cohort; none changes direction, and none changes verdict
except H2, which passes uncorrected on the 24 (p = .023) — consistent with an effect too small to
establish here.

## What the round established (with how firmly)

Strength labels follow the brief: *strong* = robust across checks; *moderate* = holds but with a real
caveat; *suggestive* = worth following up, not a claim.

1. **Recovery is about attempting, and Suggest is the cheap way to attempt** — *moderate.* All 27
   fixable failures where the operator tried nothing were abandoned. Among attempted recoveries,
   Suggest and hand-fixing do equally well (OR 0.94). Suggest's own blind spot (it ignores drones
   busy on other tasks) caused 23 refused presses across 14 people and 17 failures, of which only 8
   were then fixed by hand; 9 were abandoned. Only 3 of the 11 cases where someone abandoned right
   after Suggest had a complete working plan. *(Corrected 2026-10-07 -- see SUPERVISOR_LOG.md,
   "Erratum". First version: 11 presses, 8 people, 8 of 9 fixed by hand, 9 of 11 had a working plan.)*
2. **Load at the moment of decision does not drive reliance** — *strong (as a null).* Null across ~20
   specifications, including a measure of load the operator cannot cause by being slow (scheduled
   arrivals). What the assistant does buy is **speed on big jobs**: a card saves ~7 s (net of the
   forced reveal) on three-type missions only, a kept Suggest plan is ~16% faster than hand-building,
   and Suggest users are 4.8× more likely to start the next mission while a plan fills in.
3. **Reliance is one general, stable trait** — *strong.* One axis (31% of variation) loads on strategic
   uptake (.92), tactical consulting (.62) and recovery Suggest (.46); it correlates .65 between
   sessions; it tracks strategic trust (ρ = .54) and score *between* people but not within a person;
   no disposition measure predicts it. Extends brief Finding 1.
4. **Reliance and performance: character, not cause** — *moderate.* People who rely more score higher
   (OR 3.06 between people), but a given person's card missions do no better than their manual ones.
5. **Strategic trust is rated lower after a Strategic Heavy session** — *moderate.* The drop the
   brief attributes to "session 1 → 2" sits mostly with people who played Strategic Heavy *second*
   (13 of 16 fell, mean −1.26, against −0.29 in the other order). Not explained by their own failures.
6. **The tactical preference is real in what people say** — *moderate.* Both codings find it (17 vs 6;
   17 vs 3 without the five low-confidence codes), and people who *say* they hand big missions over
   do consult more on big plans. The coding reliability bar was not met, mainly because the two
   coders defined "conditional" differently (researcher ruling recorded: complexity-dependent use
   counts as conditional).

## Changes to the brief (proposed — not yet made)

| Brief section | Change | Why |
|---|---|---|
| Context · benchmark | Remove the "61% vs 75%" scenario comparison | H4: it comes from one game pairing whose benchmark run had 12 drone failures (participants averaged 4.5); 7 of 17 humans beat it there and nowhere else |
| Finding 3 · manual | Qualify "manual is never faster": true overall after adjustment, but not on single-type missions | H9 |
| Finding 5 · trust drop | Reframe from "fell between sessions" to "lower after a Strategic Heavy session" | H5 |
| Finding 6 · recovery | Reframe from "Suggest goes with fewer abandonments" to "attempting goes with fewer abandonments; Suggest is the cheap way to attempt" | H3 |
| Finding 1 · person | Add: the trait is one axis across all three tiers, not types | H1 |
| New · speed | Add the conditional speed finding and the null on momentary load | H9 |
| Finding 4 · tiers | Keep the confound framing; note checking cost is *not* established (H2 fails after correction) and the stated preference is real but its coding is not yet reliable | H2, H6 |
| Synthesis page · disposition | Soften "not for either assistant" (one nominal exploratory hit among ~45) | H7 |

## Problems found in existing code (to fix after sign-off)

- **`scripts/study_analysis.py` · `feasibleWithBusy`** counts drones that already flew home and never
  clears reused failed-drone IDs, so the "abandoned: fix needed a busy drone" category is overstated
  (12 → 8 overall; 7 → 4 in v1.12+). Feeds `docs/reports/study_analysis.json` and both pages.
- **`src/components/MapDisplay.tsx` ~line 965**: comment says Suggest reveals "one drone every 2 s";
  the timer is 1 s. Comment-only fix; behaviour unchanged.
- **Scoring scale**: P01 (study-v1.0) and P02 (study-v1.2) ran on half task weights (10–50 points vs
  20–100). Any raw-score comparison must rescale or exclude them; score *efficiency* is unaffected.
- **Projected completion** in `tactical_confirmed` compares a value stamped when the planner opened
  with one stamped at confirm, so even unmodified plans differ (r = .71 with confirm delay). Adjust
  for delay in any use of it.

## Lessons for round 2

- **Test the test.** H8's marker selected its own "before" window; a null simulation exposed it only
  after the fact. Any event-defined comparison in round 2 gets a null simulation *before* it is
  signed off.
- **Use the small-sample correction from the start** in every GEE.
- **Fix every component of a compound test in the plan** (H2's agent had to pin them down itself).
- **Candidate follow-up:** the in-session narration (13 sessions already aligned to the game clock)
  for moments of spoken overload, checked against what the logs show around them — the one place
  H9's null could still be wrong.
