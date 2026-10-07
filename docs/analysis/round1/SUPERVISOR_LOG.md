# Round 1 · supervisor log

Every agent's result is checked here before it is used: data integrity against the off-repo
SHA-256 manifest (`G:\Files\Code\_backups\GraphColouringNew_data_2026-10-07`), an independent re-run
of its script, and a read for the known traps (plan §2).

## Agent results

| Hyp | Data intact | Re-run reproduces | Primary (all 33) | v1.12+ | Verdict as reported |
|---|---|---|---|---|---|
| H7 | ✓ | ✓ | AIAS-4 OR 0.80/SD [0.50, 1.27], p = .34 (bias-reduced p = .40) | OR 0.72, p = .23 | Not supported |
| H3 | ✓ | ✓ | Suggest within-person OR 0.40 [0.21, 0.76], p = .005, 164 episodes / 32 people | OR 0.29, p = .005 | Supported as specified — but see note |
| H9 | ✓ | ✓ | Queue (within person) OR 1.039/mission [0.947, 1.140], p = .42; 80% power for OR ≥ 1.14 | OR 1.03, p = .60 | Not supported |
| H2 | ✓ | ✓ | Intersection-union of 3 components, p = .019 (A: keep-unmodified ↑ with size OR 1.76; B: inspection/drone ↓; C: size × inspection OR 0.70) | p = .0025 | Supported as specified — fragile, see note |
| H6 | ✓ | ✓ | Tactical preferred 17 vs 6, sign p = .035; κ vs existing codes .27 [.07, .49] (needed ≥ .6) | 13 vs 3, p = .021 | Not supported (fails the reliability bar) |
| H4 | ✓ | ✓ | Manual-rate b = −0.14 [−0.43, +0.14], p = .33; S–T gap shrinks 12.8% (needed ≥ 50%) | b = −0.11, p = .43 | Not supported |
| H10 | ✓ | ✓ | Card vs manual within person OR 0.81 [0.55, 1.18], p = .27, n = 606; detectable ≤ 0.58 / ≥ 1.73 | OR 0.90, p = .67 | Not supported |
| H5 | ✓ | ✓ | ρ(Δ strategic trust, s1 card missions failed/abandoned) = −0.05 [−0.39, +0.30], p = .78, n = 33 | ρ = +0.12, p = .59 | Not supported |
| H8 | ✓ | ✓ | Uptake after vs before detection OR 0.12 [0.03, 0.50], p = .003, 69 decisions / 17 people | OR 0.04 | Passes as specified — INVALID, see note |
| H1 | ✓ | ✓ (full 15-min re-run) | ΔBIC(k=2 vs 1) = 1.9 (needed > 10); Jaccard .76 / .47; session ARI .04 (perm. p = .42) | k = 4 wins but splits 14/8/1/1 | Not supported — continuum |

## Notes and issues raised

- **H7 · few clusters (applies to every round-1 GEE).** With ~32 clusters, the robust sandwich SE
  rejects a true null ~9.5% of the time, not 5% (H7's simulation). At consolidation, every primary
  GEE is re-fitted with the bias-reduced (Mancl–DeRouen) covariance and reported alongside; results
  near p = .05 are judged on that.
- **H7 · wording.** The synthesis page says disposition predicts trust "not for either assistant";
  one exploratory session-level test (AIAS vs tactical trust, p = .046, among ~45) is nominal. Soften
  that wording when the page is next edited.
- **H3 · the effect is trying vs giving up.** All 27 no-attempt episodes are abandonments and all sit
  in the no-Suggest arm. Among attempted episodes, Suggest vs hand-fixing is OR 0.94 [0.27, 3.22].
  The brief's Finding 6 should be reframed: the lever is getting operators to *attempt* recovery,
  with Suggest as the cheap way to attempt. Not "Suggest beats fixing by hand".
- **H3 · Suggest's blind spot is real but small.** 97 recovery presses: 58 solved, 24 failed, 3
  partial, 12 no-op. Only 11 failures were the genuine busy-drone blind spot (8 people); operators
  then mostly fixed it by hand (8 of 9 episodes recovered).
- **H3 · operators abandoned working plans.** In 9 of 11 "suggest-then-abandon" episodes, Suggest had
  returned a complete plan. Worth a look in its own right: a plan offered and refused.
- **H3 · existing bug found (not yet fixed).** `study_analysis.read_session`'s `feasibleWithBusy`
  counts drones that already flew home and never clears reused failed drone IDs, so the existing
  "abandon-busy" pattern is overstated: 12 → 8 overall, 7 → 4 in v1.12+. This feeds
  `docs/reports/study_analysis.json` and both report pages. Fix after the round (scripts are frozen
  while agents run), then rebuild.
- **H9 · no momentary-load effect.** Null across ~20 specifications incl. exogenous arrivals. Two
  apparent effects (tactical consult, pre-emptive manual under load) vanish once time-in-session is
  controlled. Recovery Suggest is used *less* when the hub is depleted (OR 1.08 per available drone).
- **H9 · speed is real but conditional.** A card saves ~7 s net of the reveal on three-type missions
  only; on single-type missions pre-emptive manual is faster. Brief Finding 3's "manual is never
  faster" needs qualifying (true adjusted overall, not on single-type missions). Keeping a Suggest
  plan is ~16% faster than hand-building, mostly on large plans.
- **Code fact confirmed (MapDisplay.tsx ~965):** Suggest reveals its plan at 1 drone per 1000 ms and
  Deploy is locked until it finishes — a forced wait on the tactical tier, like the card reveal on
  the strategic tier. The code comment says "every 2 s"; the timer is 1 s (stale comment). Any
  tactical latency analysis must net this out (H2 and H9 both did).
- **H2 · fragile.** The verdict depends on defining keep-unmodified over all plans (the brief's
  definition, chosen after seeing that 96% of consulted plans are kept). Among consulted plans only,
  component A reverses (OR 0.67). Checking time is flat at ~3 s regardless of size, so B is largely a
  ratio effect; C vanishes once editing time is removed (p = .49) and rests on 18 edits / 8 people.
  Exploratory and opposite to the hypothesis: the person-level tactical/strategic checking-time ratio
  correlates ρ = −.51 (p = .002) with the trust gap, driven by slow strategic deciders having bigger
  gaps. Read as: the checking-cost mechanism is NOT established.
- **H6 · substance holds, reliability does not.** Both codings find tactical preferred (new: 17 vs 6;
  existing: 12 vs 1), and on a binary "prefers tactical" the coders agree moderately (κ = .47). The
  low overall κ is mostly the two coders using "conditional" differently. Dropping 5 assents to
  leading questions gives 13 vs 6, p = .17. Operators who *say* they hand big missions to the
  assistant do consult it more on big plans (p = .022): stated and enacted scale-conditionality agree.
- **H4 · the brief's 61% vs 75% benchmark gap is mostly a benchmark artefact.** It sits in one game
  pairing (players of Strategic game 1 + Tactical game 2: +0.255, p = .001; the other pairing: +0.029,
  p = .65). The benchmark run on Tactical game 2 suffered 12 drone failures (participants averaged
  4.5) and 7 of 17 human sessions beat it — none do on any other game. The brief's Context section
  must not quote that gap as a scenario effect. What Strategic Heavy genuinely loses is missions never
  allocated: 2.4 per session (424 points) vs 0.5 (140). Trimming drones on small missions did not
  measurably help later missions.
- **H4 · scale issue confirmed.** P01 (study-v1.0) and P02 (study-v1.2) ran on half task weights
  (10–50 vs 20–100 points), so their raw scores and benchmark shares are on a different scale. Three
  sessions have score floored at 0. Kept in the primary; handled in robustness. Any score-based
  analysis should use score efficiency or exclude/rescale these two.
- **H10 · reliance goes with performance between people, not within.** Person-mean uptake OR 3.06
  (p = .004), session-level tactical keep-unmodified predicts benchmark share between people (+0.51,
  p < .001) but not within. Better operators rely more; relying more does not make a given operator
  better — consistent with Finding 1 (reliance is a person-level style). Exploratory: manual chosen
  *after* reading the cards, without editing one, is the weakest route.
- **H10 · projected vs actual.** `agentProjectedCompletion` is stamped when the planner opens and
  `finalProjectedCompletion` at confirm, so even unmodified plans differ (r = .71 with confirm delay).
  Projected-completion comparisons must adjust for delay (H9's "45 s projected vs 5 s realised" has
  the same cause).
- **H5 · own experience does not drive the strategic trust drop.** Null on every variant, and its
  premise fails: card missions fail no more often than manual ones (OR 1.22 [0.83, 1.81]).
- **H5 · the trust drop is an order effect, not just a run effect (refines brief Finding 5).** The
  crossover gives strategic trust both a run effect (−0.78) and a scenario effect (+0.48, p = .042).
  The drop sits mostly with people who played **Strategic Heavy second**: 13 of 16 fell, mean −1.26,
  against −0.29 for the other order. Reading: strategic trust is rated lower after a Strategic Heavy
  session (many small missions, where the cards are least useful and the illogical card is
  concentrated), and that lands on the second rating for half the sample. Post hoc only: the primary
  correlation flips sign between the two orders (+.45 vs −.57, interaction p = .003).
- **H8 · the pre-registered test is invalid by construction (supervisor's specification error).**
  The marker is the first manual rejection of an illogical card after the cards loaded, so every
  earlier illogical-card decision is by definition a card take: the "before" window is forced
  towards uptake (13 of 18 before-decisions). A null simulation (constant uptake per person, marker
  re-applied) produces OR 0.37 with no real change; calibrated against it the observed effect is
  p = .30 on the risk difference (bias-corrected −10 pp), and a placebo marker built on clean cards
  shows the same kind of drop (OR 0.22). The plan excluded the detection decision itself but missed
  that the marker's definition selects the before-window. Report H8 as NOT SUPPORTED (no detectable
  post-detection change), consistent with the four earlier carry-over nulls.
- **H5 × H8.** People whose first detection came in session 2 lost more strategic trust (−2.05 vs
  −0.42, p = .008), but all of them played Tactical Heavy first — the same order effect. Within that
  group the gap is −1.83 vs −0.69, p = .08. Suggestive only.

## Researcher decisions during the round

- **2026-10-07 · H6 "conditional".** "I use the assistant more when missions are complex" counts as a
  **conditional** preference (researcher's ruling). This is the H6 agent's reading, so its codes stand;
  the low κ is therefore a genuine definitional difference with the original single-coder codes,
  which used "conditional" more narrowly. Ruling made after κ was seen — label any recomputation that
  uses it as post hoc.
- **2026-10-07 · H6 borderline codes** (P06, P10, P11, P20, P36): the researcher cannot adjudicate from
  memory. Treat as low-confidence; report the sign test with and without them.
- **H6 · sensitivity to the borderline codes (supervisor check).** Sign test, tactical vs strategic
  preference: all coded 17 vs 6 (p = .035); without the 5 borderline participants 17 vs 3
  (p = .003); high/medium-confidence codes only 16 vs 3 (p = .004). Three of the five borderline
  codes were "strategic", so the low-confidence calls work *against* the tactical preference — the
  preference is robust to them. The H6 verdict still fails on κ.

## Consolidation (all seven verified)

Small-sample (bias-reduced) GEE errors applied to every GEE primary by re-running each agent's
script unchanged with GEE defaulting to `cov_type='bias_reduced'`. One verdict changes: **H2
p = .019 → .065, no longer supported.** Holm across all ten primaries: none survives (closest H3,
adjusted p = .08). Full results, term definitions and proposed brief changes:
`ROUND1_SUMMARY.md`.


## Erratum, 2026-10-07 (found while building the combined findings page)

**Bug in the H3 Suggest-press rebuild (`h3_recovery.parse_session`).** Execution intervals were taken
from `task_completed` / `task_failed` only. A task cut short by abandonment is logged as `task_requeued`,
so its drones looked free while it ran. Suggest excludes executing drones, so where the only drone of a
needed type was busy the app showed "No workable plan" while the rebuild scored the press "solved" --
and this happens precisely in the episodes that end in abandonment. **Found because three operators
(P11, P19, P32) read "No workable plan" aloud seconds after presses scored as solved**; P19's log
confirms it (the mission's only Camera drone was executing T4 when Suggest was pressed for T3).

Fix: `task_requeued` with `statusBefore == 'executing'` now adds an interval ending at the abandonment.
Corrected output: `h3_recovery_corrected_output_2026-10-07.txt`.

| | before | after |
|---|---|---|
| recovery Suggest presses: solved / failed / partial / no-op | 58 / 24 / 3 / 12 | 50 / 36 / 3 / 8 |
| blind-spot presses (refused, fixable with a busy drone) | 11 (8 people, 9 failures) | **23 (14 people, 17 failures)** |
| blind-spot failures recovered / abandoned | 8 / 1 | **8 / 9** |
| suggest-then-abandon cases with a complete working plan | 9 of 11 | **3 of 11** |
| later recovery-Suggest use after exposure to a blind spot (GEE) | OR 0.14, p .03 (P01/P02-driven) | OR 0.29 [0.12, 0.73], p .009, 14 exposed people |
| tactical keep-unmodified DiD after exposure | null | null (OR 1.12, p .75) |
| R12: abandoned when Suggest gave a plan / pressed but gave nothing | 11/59 vs 3/11 | **3/51 vs 11/19** |

**Unchanged:** the H3 primary and every robustness row that does not use the press rebuild (the
attempted/used-Suggest split does not depend on it). The verdict on H3 stands. What changes is the
reading of the blind spot: it is **not** rare and **not** costless -- most suggest-then-abandon
episodes are Suggest refusing a fixable failure, not operators discarding a working plan.
`results.json` (recovery block), `ROUND1_SUMMARY.md` item 1 and the round-1 page text are updated.
