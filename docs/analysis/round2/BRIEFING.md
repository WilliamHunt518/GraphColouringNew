# Round 2 · briefing every agent reads first

You are one of seven agents in **round 2: structured exploration** of a human-subjects study on trust in
a two-tier AI assistant for drone search-and-rescue allocation. Round 1 tested ten pre-registered
hypotheses and none survived correction across all ten. Round 2 widens the search on purpose: alternative
versions, opposite hypotheses, constrained situations, and new questions. Because it is exploratory,
everything it produces is a **candidate** to be confirmed on new data later, not a confirmed claim. The
rules below are what keep it honest. A supervising agent will re-run your work and apply them.

## Read, in order

1. `docs/analysis/HYPOTHESES_ROUND2.md` — the round-2 plan, including the 2026-10-07 amendment. Your
   workstream's variant menu is in §4; the rules in §2; dropped ideas in §3. The amendment overrides
   anything it changes.
2. `docs/analysis/round1/ROUND1_SUMMARY.md` — what round 1 found, its terms, and its lessons.
3. The round-1 report(s) your workstream builds on (named in your instructions), in
   `docs/analysis/round1/`, and their scripts in `scripts/analysis_round1/`. **Reuse their loaders and
   features** rather than re-parsing logs; extend them.
4. `docs/analysis/HYPOTHESES_ROUND1.md` §2 — the nine known data traps. They all still apply.
5. `CLAUDE.md` (what the study is) and `docs/EVENT_LOGGING.md` (event fields) as needed.

## Hard rules

- **Data is read-only.** Never write, move, rename or modify anything under `Results/` or `docs/reports/`.
  Never edit `src/`, any existing script (round-1 scripts included), templates or the builder. The data is
  checksummed against an off-repo backup and verified after you finish. If data looks wrong, report it.
- Write only:
  - scripts in `scripts/analysis_round2/` with your prefix (`wA_` … `wG_`);
  - your report `docs/analysis/round2/w<X>_<slug>.md`;
  - your specification table `docs/analysis/round2/w<X>_specs.csv`.
- Python: `C:/Users/Work/anaconda3/python.exe` (numpy, pandas, scipy, statsmodels 0.14, scikit-learn
  1.2). The plain `python` lacks them. Run from the repo root `G:/Files/Code/GraphColouringNew`. Import
  round-1 code with `sys.path.insert(0, 'scripts')` and `sys.path.insert(0, 'scripts/analysis_round1')`.
- Exclude P09 everywhere. Participants by ID only. Do not commit. Do not spawn agents.
- Keep scripts reasonably fast (aim < 5 minutes). If you need the round-1 reliance axis (PC1), recompute
  it from `h1_archetypes.py`'s feature code **without** its bootstrap.

## Rules for exploration (from the plan, §2)

1. **Run your whole variant menu.** You may add at most **three** variants of your own; write each one
   and its reason into your report's analysis log *before* you run it, and mark it `extra=1`.
2. **Report every test** in the spec table — nulls included. Judge results on the pattern across
   variants, never on the best one.
3. **Small-sample correction everywhere:** fit GEEs with `.fit(cov_type='bias_reduced')`. With about 33
   clusters the default robust errors give ~9.5% false positives instead of 5%.
4. **Event-defined comparisons** (before/after a moment) need a null simulation before you interpret
   them. Round-1 H8 failed exactly this way: its marker selected its own "before" window.
5. **Robustness gates** for anything you think is a candidate (q itself is computed by the supervisor
   across the whole round):
   - same direction on **S-s1** (session 1 only) and in **both scenario orders**;
   - **leave-one-person-out:** report the range of the estimate and whether any single person flips
     its sign;
   - a one-sentence **mechanism**, checked against debrief quotes where possible (by quote ID).
6. **Operators, not assistants.** Facts about how the assistants were built (e.g. how often the
   Conservative card pads unused drones) are context, not findings. Operators' *reactions* are in scope.

## Samples (use these codes in the spec table)

| Code | Sample |
|---|---|
| `S-all` | All 33 participants |
| `S-v112` | The 24 on identical game versions (`session_start.appVersion` ≥ study-v1.12) |
| `S-s1` | Session 1 only, all 33 — between-person, no order or carry-over |
| `S-27` | All except the six game-swapped participants (P31–P36). Order and game pairing coincide here, so call an effect "order + pairing" |
| `S-6` | The six swapped participants alone (P31–P36). Descriptive only |

**Order and game are confounded.** Up to P30 the game was set by session number, so players of
Strategic Heavy first almost all got games S1 + T2, and players of Tactical Heavy first got S2 + T1.
Game = (`session_start.complexity`, `session_start.planSeedIndex`; when that is missing, the session
number). Wherever order, scenario or performance is involved, include **game as a fixed effect** in at
least one variant, and say whether a result is about scenario, game, order, or cannot tell.

**Performance metrics** — report all that apply:
- score efficiency (score ÷ points available);
- per-game z-score (score standardised within each of the four games);
- share of the near-perfect operator's score (`docs/reports/smart_benchmark.json`), flagged unreliable
  on Tactical game 2;
- share of the best human score on that game.
- **P01 and P02 ran on half task weights** (10–50 points): rescale ×2 or exclude, and say which.

## Spec table format (`w<X>_specs.csv`, one row per test)

`workstream, variant_id, extra, description, sample, outcome, predictor, model, estimate, ci_lo, ci_hi,
estimate_scale, p, n_obs, n_people, expected_direction, s1_same_direction, both_orders_same_direction,
loo_sign_flip, notes`

- `estimate_scale`: `OR`, `b`, `rho`, `diff` or `kappa`.
- `expected_direction`: `+`, `-` or `none`, written before running.
- Gate columns: `1`, `0` or `na`.

## Report format (`docs/analysis/round2/w<X>_<slug>.md`)

1. **Candidates:** results you think pass q < .10 and the gates — estimate, interval, p, the gate
   results, the mechanism, and supporting quote IDs. Say plainly if there are none.
2. **Everything else**, grouped by variant, in plain words (define any term a non-statistician might
   not know, where you first use it).
3. **Analysis log:** every variant in the order run, including extras with their pre-stated reasons.
4. The traps and confounds that applied, and how you handled each.
5. The exact command to reproduce.

**Final message:** ≤ 250 words — candidates (or none), the strongest null, and anything the supervisor
should double-check.
