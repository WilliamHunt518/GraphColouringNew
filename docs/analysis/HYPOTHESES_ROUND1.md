# Analysis round 1 — hypotheses to agree before any agent runs

**Status: DRAFT for sign-off.** Nothing here has been run. Once agreed, this file is frozen: each
hypothesis's *primary test* is the confirmatory one, and everything else an agent finds is reported
as exploratory. Changes after sign-off go in a dated "Amendments" section at the bottom, never by
editing a test in place.

**How it runs.** One Claude agent per work package (§3), all launched from this repo so they can read the
code and the raw logs. Each writes its analysis as a script under `scripts/analysis_round1/`, runs
it, and reports in the fixed format of §4. A supervising agent re-runs every script, checks each
result against the known traps (§2), applies the correction across the confirmatory family, and
writes the surviving results into the findings brief, marked strong/moderate/suggestive as now.

---

## 1 · Ground rules every agent gets

| Rule | Setting |
|---|---|
| **Data** | `Results/Participants/P*.json`. Debriefs: `Results/Narration/*_s1/` (coded quotes, segments, debrief text) and `Results/Interviews/*.docx`. Identifiable — read locally, never sent anywhere else, no verbatim quotes in any committed output except by quote ID. |
| **Exclusions** | P09 everywhere (faults on, ε = 0.2, did not follow the task). Residual missions (`-R`, `isResidual`) excluded from any analysis that uses mission **category**. |
| **Cohort** | **DECISION A — see §5.** Primary: all 33 participants; sensitivity re-run on the `study-v1.12+` cohort (n = 24, identical games). |
| **Unit of analysis** | Decision-level models use GEE (binomial for yes/no outcomes) clustered on participant, as `build_findings_synthesis.gee()`. Person-level tests use Spearman ρ; scenario/run contrasts use `study_analysis.crossover`. Reuse these helpers — do not reimplement them. |
| **Game** | Scenario is confounded with which of the four fixed games was played (`planSeedIndex`). Any performance outcome must control for game, not just scenario (`docs/STUDY_BUILD.md` §20). |
| **Correction** | **DECISION B — see §5.** One primary test per hypothesis forms the confirmatory family, Holm-corrected together. |
| **Effect sizes** | Every result gives an effect size with a 95% interval, not just p. A null must state what effect size it could have detected. |

## 2 · Known traps (every agent's briefing includes these)

1. **No failures were injected.** `agentFailuresEnabled` was off and both ε = 0 in every session
   analysed. The only assistant "errors" are side effects of the simple rules: the Conservative
   card's ungated 15% top-up (`scripts/check_conservative_topup.py`) and recovery Suggest's blind
   spot for drones busy elsewhere.
2. **Illogical cards are nested in mission size.** An illogical card needs an unused drone type, so it
   can only occur on a single-type mission (0 of 413 three-type decisions). Any odd-vs-clean contrast
   must be made within single-type missions.
3. **"Drone types needed" is effectively binary**: 181 single-type, 413 three-type, 12 two-type decisions.
4. **Residual missions** keep their parent's category with fewer tasks (an E residual averages 2.6
   tasks against 6).
5. **Decision time includes a forced wait.** The cards are unreadable for 4–5 s, so `latencyMs` on
   a card choice includes that wait; manual can be chosen during it (`manualBeforeCardsLoaded`).
6. **Manual is not one behaviour.** It covers choices made before the cards loaded, allocations
   between or below the two cards, and edited cards (`scripts/manual_choice_analysis.py`).
7. **Before/after an event is not a baseline.** The first illogical card can only appear on a
   single-type mission, so "before" is filtered towards three-type missions. Match on composition
   (see the event-study section of the synthesis page).
8. **Quotes are from the post-session debrief**, coded once by one coder, and are not aligned to
   in-session decisions.
9. **n = 33.** Person-level correlations can detect ρ ≥ ~.48 at 80% power. Clustering 33 people into
   more than two or three groups is not defensible.

## 3 · The hypotheses

Each entry gives the question, the **primary test** (confirmatory), secondary analyses
(exploratory), what would count as support, and the **head start**: what already exists, so the
agent extends it rather than starting over.

### H1 · Are there operator archetypes?
*Your hypothesis, extended.* Reliance is a stable trait of the person (brief Finding 1:
session-to-session ρ = .64; person identity explains ~24% of card-taking against ~4% for the mission).
Can that style be described, and does it fall into distinct types rather than a continuum?

- **Features (per person):**
  - card uptake, share of manual choices made before the cards loaded, edited-card rate;
  - tactical consult and keep-unmodified rates, recovery Suggest rate;
  - median decision time with the forced wait removed;
  - manual drones vs the Conservative card on small and on large missions;
  - card-preview toggling (`strategic_card_previewed`).
  - All standardised; outcomes (score) are held out, not clustered on.
- **Primary test:** a Gaussian mixture / latent profile model with k = 1–4, chosen by BIC.
  **Support** = k ≥ 2 beats k = 1 by ΔBIC > 10 **and** the clusters are stable: bootstrap Jaccard
  ≥ .75, and the same people group together when sessions 1 and 2 are clustered separately.
- **Secondary:**
  - describe each archetype;
  - test whether archetypes differ on score efficiency, trust and disposition;
  - check which archetype each of the six debrief stance codes falls in.
- **Fallback:** if k = 1 wins, report the continuum and its principal axes (PCA), which is still
  a result: one dimension or two?
- **Head start:**
  - `individual()` in `build_findings_synthesis.py` (stability and pseudo-R²);
  - the per-participant "reliance signature" in `scripts/decision_features.py` (needs re-pointing
    at `Results/Participants` and the anonymous IDs);
  - `learning.perPerson` in the page payload.

### H2 · Does the cost of checking explain the trust gap between the tiers?
*Yours.* Tactical is trusted more (5.44 vs 4.61) and its plans are kept unmodified more often. The
debriefs offer a mechanism: a strategy card is three numbers and costs a glance to check, while a
tactical plan has to be read drone by drone, so operators defer to it when there is no time.

- **Measures:**
  - strategic checking time: card-preview dwell and toggling (`strategic_card_previewed.latencyMs`
    sequence), and decision time with the forced wait removed;
  - tactical checking time: last `tactical_suggest_used` to `tactical_confirmed`, i.e. inspection
    after the plan appeared;
  - plan size: drones × tasks.
- **Primary test:** within the tactical tier, the probability of keeping the plan unmodified rises
  with plan size while inspection time per drone falls (GEE, person-clustered, controlling for
  scenario and run). **Support** = both effects in the predicted direction with the interaction
  significant: bigger plans get proportionally less checking and more deference.
- **Secondary:**
  - per person, does relative checking cost (tactical inspection per drone ÷ strategic dwell)
    predict the person's trust gap?
  - does tactical inspection time fall from session 1 to session 2 while keep-unmodified rises?
- **Limit:** this cannot separate checking cost from how visible the flaws are, because the
  strategic card's top-up is visible and the tactical plan has no planted flaw. H6 and H8 cover
  the visibility side; the write-up must say so.
- **Head start:**
  - brief Finding 4 and its quote lists (`NOCHECK`, `OVERALLOC` in `findings_brief_template.html`);
  - the verification section of the synthesis page;
  - the timing fields in `docs/EVENT_LOGGING.md`.

### H3 · Recovery: does Suggest still predict fewer abandonments within person, on fixable failures — and what happens when Suggest fails?
*Yours.* In the v1.12+ cohort, 18% of recoveries where Suggest was used were abandoned, against
51% where it wasn't. That comparison is observational.

- **Primary test:** a GEE logit of abandonment on Suggest use, restricted to failures the logs show
  were fixable with drones already on the mission (`coverable()` in `study_analysis.py`), clustered
  on person, with person-mean Suggest use as a covariate so the Suggest term is the within-person
  effect. **Support** = within-person odds ratio < 1 with its interval excluding 1.
- **Secondary — the unplanned agent failure:**
  - Suggest has a blind spot: it only draws on mission drones not currently executing a task.
    Classify every Suggest press in recovery as solved / partial / failed.
  - The existing episode patterns already show 7 "fix needed a busy drone" and 9 "abandoned right
    after Suggest, though fixable".
  - Then ask:
    - After Suggest fails, do operators fix it by hand, or abandon?
    - Does a failed Suggest change their later use of Suggest in recovery (a genuine agent error,
      the only one in the dataset)?
    - Does it change their tactical keep-unmodified rate or tactical trust?
- **Head start:**
  - `study_analysis.failure_analysis()`, `episode_pattern()` and `coverable()`;
  - `S.patterns` and `S.suggestSplit` in the page payload;
  - `computeRecoverySuggestion` in `src/utils/tacticalSuggest.ts`, which documents the blind spot.

### H4 · Is the larger shortfall against the near-perfect operator in Strategic Heavy explained by manual work?
*Yours.* Operators reach 61% of the benchmark score in Strategic Heavy and 75% in Tactical Heavy.

- **Primary test:** across sessions, the share of the benchmark score achieved, regressed on the
  session's manual rate, with game as a fixed effect and person as a random intercept (or within-
  person differencing). **Support** = a negative manual-rate coefficient, and the
  Strategic-vs-Tactical gap shrinks by ≥ 50% when manual rate is added.
- **Secondary:**
  - per mission, compare how manually built missions do against card missions on completion,
    time to complete and penalty, matched on composition and person;
  - separate pre-emptive manual choices from manual choices made after the cards loaded;
  - check whether trimming drones on small missions leaves a larger reserve that helps the
    missions that follow.
- **Head start:**
  - `benchmark()` in `build_findings_synthesis.py`;
  - `docs/reports/smart_benchmark.json`;
  - `C.outcome` (descriptive completion by route);
  - `useVsPerf` in `study_analysis.json` (see H10).

### H5 · Does the drop in strategic trust follow the operator's own session-1 experience?
*Yours.* Strategic trust fell from 4.99 to 4.23 between sessions (it fell for 20 of 33), while
behaviour barely moved. The number of illogical cards seen does not explain it (ρ = −.07).

- **Session-1 predictors:**
  - drone failures experienced and missions abandoned;
  - missions that failed or were abandoned after a card was taken, vs after a manual choice;
  - score efficiency.
- **Primary test:** Spearman ρ between the change in strategic trust and the number of session-1
  missions that failed or were abandoned *after the operator took a card* (the experience that
  should cost the card credibility). **Support** = ρ < 0, interval excluding 0.
- **Secondary:**
  - the same predictor against the change in tactical trust (it should *not* predict it, which
    is a discriminant check);
  - a regression with all the session-1 predictors;
  - whether the debriefs of people whose trust fell most name a cause, tested via the
    `trust_trajectory` quotes.
- **Head start:**
  - `individual().trustChange` and `trustPairs`;
  - brief Finding 5;
  - `SR.crossover` for trust by run.

### H6 · Is the tactical assistant trusted more in what people say, not just on the scale — and does that depend on mission scale?
*Yours.* The trust gap is clear on the questionnaire. Does open-ended talk show the same, and is
the preference conditional on scale ("simple missions myself, complex ones to the assistant")?

- **Method:** an independent second coding pass over the full debriefs and interviews, not just
  the 141 already-extracted quotes. For each participant, code:
  - overall tier preference: strategic / tactical / both / neither / conditional;
  - whether the preference is conditional on mission size or complexity, and in which direction;
  - why: speed, accuracy, can't check, visible errors, autonomy, or other.

  The coder works from a fixed codebook written before reading. The agreement with the existing
  stance codes (`SR.stance`: prefers tactical 12, conditional 14, distrusts both 5, trusts both 2,
  prefers strategic 1) is reported as Cohen's κ, which gives the existing single-coder coding the
  second rater it lacks.
- **Primary test:** among participants who state a preference, the share preferring tactical
  against 50% (sign test). **Support** = significant preference for tactical, with κ ≥ .6 against
  the existing codes.
- **Secondary:**
  - does a stated scale-conditional preference match the person's actual within-person composition
    effect (H1/Finding 2)?
  - do stated preferences predict behaviour?
  - the two streams' disagreements, extending the "where the two streams disagree" section.
- **Head start:**
  - `scripts/narration_quotes.py` and its themes;
  - `SR.stance`;
  - the `agent_comparison` and `scenario_comparison` quote themes;
  - `Results/Interviews/*.docx`.

### H7 · Does disposition toward AI affect uptake and trust — for one assistant or both?
*Yours.* The person-level screen was entirely null (0 of 40 tests survive Holm), but it ran 40 tests
at n = 32 and never tested the asymmetry directly.

- **Primary test (one test, to avoid repeating the 40-test problem):** AIAS-4, the only
  reliable scale (α = .80), as a person-level covariate in the decision-level GEE for card-taking,
  controlling for composition. **Support** = AIAS term interval excluding 1.
- **Asymmetry test:** does AIAS-4 predict strategic trust and uptake more than tactical (Steiger's
  test for dependent correlations, and an AIAS × tier interaction in a stacked model)?
- **Secondary:**
  - the bespoke scales, as exploratory only;
  - whether disposition predicts *how much trust changes* (H5) rather than its level.
- **Expectation, stated in advance:** this is likely null. AIAS-4 averages 8.0/10, so there are
  almost no sceptics, and the detectable effect is large. The write-up must report the detectable
  effect size, not just p.
- **Head start:** `analyse_disposition()` (scoring, Holm, detectable ρ) and the disposition section
  of the synthesis page.

### H8 · How does an illogical card affect use of the strategic assistant — on the spot, and after the operator realises it can happen?
*Yours.* Four tests so far find no effect beyond mission composition, but none of them looks at the
moment the operator **noticed**.

- **Detection signal (behavioural):** the first decision where the operator was shown an illogical
  Conservative card and either rejected it for a manual allocation that drops the unneeded drone
  type, or edited that type out. That is evidence they saw the flaw, not merely that it was there.
  A second marker is a debrief mention (`OVERALLOC` list, 10 people).
- **Primary test:** within single-type missions only (trap 2), card uptake before vs after each
  person's detection point, adjusted for position in session and scenario (GEE). **Support** = a
  drop after detection, interval excluding 1.
- **Secondary:**
  - after detection, do operators switch to Aggressive rather than leaving the card system?
  - Is the detection point earlier in session 2 than session 1?
  - Do people who noticed it, by either marker, show a larger strategic trust drop (link to H5)?
- **Head start (most of the groundwork exists):**
  - `scripts/check_conservative_topup.py`;
  - the artefact, dominated-card and over-time sections of the synthesis page;
  - `C.artefact`, `C.carryover` and `C.eventStudy` in the payload.

### H9 · Does momentary workload push operators onto the assistant? *(new — not yet tested)*
Seven debriefs say they hand over when overwhelmed (`SIMPLE_MYSELF` and the `scenario_comparison`
theme). The logs record the state at each decision: missions active, missions queued, tasks pending,
drones available. This was computed once in `decision_features.py` (pooled, older IDs, tercile
splits only) and never modelled or reported.

- **Primary test:** a GEE logit of card-taking on the number of missions queued at the decision,
  centred within person, controlling for composition, scenario and run. **Support** = odds ratio > 1
  per extra queued mission, interval excluding 1.
- **Secondary:**
  - the same for tactical consult and keep-unmodified, and for recovery Suggest;
  - drones available as a separate pressure: does low reserve push towards or away from the cards?
- **Head start:** `context_snapshot()` and `LOAD_VARS` in `scripts/decision_features.py`.

### H10 · Does relying on the assistants pay off? *(new — computed, never reported)*
`study_analysis.json` (`useVsPerf`) already has a modest link between people (strategic uptake vs
score efficiency, ρ = .38, p = .036, n = 31) and nothing within a person. Neither page reports it,
and it is the obvious question a reader asks.

- **Primary test:** at the decision level, does the mission complete in full, comparing card vs manual,
  in a GEE adjusted for composition, game and person-mean uptake (so the route term is within
  person). **Support** = route odds ratio with an interval excluding 1, in either direction; a
  null is informative too.
- **Secondary:**
  - the between/within split at session level, with game controlled;
  - penalty accrued and time to complete as outcomes;
  - tactical keep-unmodified vs edited plans, using `finalProjectedCompletion` vs
    `agentProjectedCompletion` (same scheduler, so directly comparable).
- **Head start:** `reliance_vs_performance()` in `study_analysis.py`, and `C.outcome`.

## 4 · What each agent hands back

1. `scripts/analysis_round1/hN_<slug>.py` — runs from the repo root, prints every number it reports.
2. A short report:
   - the primary test's effect, 95% interval, p and n;
   - the verdict (support / no support / not testable, with reason);
   - secondary results, labelled exploratory;
   - which traps from §2 applied and how each was handled;
   - anything that contradicts the current brief or synthesis page.
3. No edits to `src/`, the pages or the builder. Integration is the supervisor's job.

## 5 · Decisions for you before this runs

- **A · Cohort.** Primary on all 33, with a v1.12+ (n = 24) sensitivity check (recommended — more
  power, and the measures are the same across builds), *or* primary on v1.12+ only (cleanest games,
  less power)?
- **B · Confirmatory family.** One primary test per hypothesis (10 tests, Holm) — recommended. Or
  narrow the confirmatory set to the hypotheses you would put in a paper and leave the rest
  exploratory?
- **C · Debrief access for H6.** H6 needs a second coder reading the full debriefs and
  `Results/Interviews/*.docx`, which are identifiable. They stay local and only quote IDs leave the
  analysis. Is that within the ethics approval?
- **D · Agent grouping.** Ten agents (one each), or seven, grouping the pairs that share data and
  code: H5 + H8 (strategic trust and the illogical card), H3 alone, H2 + H6 (tier gap, behavioural
  and spoken), H4 + H10 (performance), H1, H7, H9? Seven is recommended: less duplicated reading,
  and paired hypotheses get checked against each other.

## Amendments

### 2026-10-07 · Signed off, with these decisions and additions

- **A · Cohort:** primary results on **all 33**; a v1.12+ (n = 24) sensitivity re-run for each primary test.
- **B · Confirmatory family:** all 10 primary tests, Holm-corrected together. If an agent finds a
  subtly different result along the same lines that is better supported, it reports that alongside
  — clearly labelled as found after the fact — and the researcher decides later what goes in the paper.
- **C · Debriefs:** full transcripts and interviews may be read. Outputs refer to participants by
  ID only; quoted text is fine provided it carries nothing clearly identifying (the researcher will
  check).
- **D · Seven agents:** H1 · H2 + H6 · H3 · H4 + H10 · H5 + H8 · H7 · H9.
- **Iteration allowed.** Each agent may reflect on its results and try further specifications or
  new angles. Every attempt goes in an *analysis log* in its report, including the ones that did
  not work, so the garden of forking paths is visible. The primary test stays the primary test.
- **H9 extended — speed vs accuracy.** Many debriefs value the assistant for being *faster*, not
  better. H9 also asks:
  - does using the assistant actually save time (time from the panel opening to deployment,
    tactical latency with vs without Suggest, matched on plan size)?
  - does reported time pressure (NASA-TLX temporal demand) or a fast personal pace go with more
    reliance?
  - is there a speed–quality trade-off between assistant-built and hand-built plans (projected
    completion, completion, penalty)?
- **Data guard.** Before any agent ran, `Results/` (except Recordings) and `docs/reports/` were
  copied to `G:\Files\Code\_backups\GraphColouringNew_data_2026-10-07` with a SHA-256 manifest
  (761 files). `Results/Participants/*` were set read-only for the run. The supervisor verifies the
  manifest after every agent finishes. Agents must never write under `Results/` or `docs/reports/`.
