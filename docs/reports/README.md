# Aggregate reports

## `findings_synthesis.html` — built into `Results/Narration/`, not into this folder

The narrative results page: what the study found, argued in order, with the behavioural numbers and
the debrief quotes on the same page. The other two pages each answer half the question —
`two-tiers-two-scenarios.html` is log-only and `Results/Narration/decision-cards.html` is narration-
only — and most of what the study found lives in the join between them, where a behavioural
regularity sits next to the sentence that explains it, or contradicts it.

```bash
python scripts/build_findings_synthesis.py          # needs numpy/scipy/pandas/statsmodels
python scripts/build_findings_synthesis.py --print  # also dump the computed numbers
```

> **The page is written to `Results/Narration/findings_synthesis.html`, not to `docs/reports/`.**
> It embeds verbatim participant speech alongside the pooled numbers, so it is identifiable data
> under the same terms as the recordings and interviews, and it sits in the same gitignored tree
> as `decision-cards.html` and the audio it came from — moved between machines by hand, like
> the rest of `Results/`. Do not paste it into a hosted tool.
>
> Everything needed to rebuild it is committed, so the page is reproducible from the repo plus a
> copy of `Results/`. Only the rendered artefact stays out.

Sections: the argument in one page · who the operators were · what they said between the scenarios
(NASA-TLX and the two trust scales) · what they brought with them (the AI-disposition batteries and
prior experience) · what drives reliance · "Manual" is four different acts ·
manual is slower and what it actually buys · when simple rules look wrong · the dominated
Conservative card · does an illogical card change anything afterwards · verification as a price ·
where the two streams disagree · failure recovery · performance · learning · performance against a
near-perfect operator · what operators asked for · limitations · every coded quote by theme.

Three conventions worth knowing before reading it:

- **Mission load is reported two ways every time** — drone colours needed, and mission category
  A→E. Category is the designed proxy (excluding residuals it *is* the task count, A = 2 … E = 6,
  and it sets the penalty rate); colours is the stronger statistical signal because uptake turns
  over at category E. **Residual missions are excluded from every category view**: a mission
  abandoned in flight re-enters as `<id>-R` carrying its parent's category with only the leftover
  tasks, so category-E residuals average 2.6 tasks against 6.0 for a genuine E.
- **Every quote is from the post-session debrief**, not from during the task. The tag on a quote is
  the coder's topic label plus what the researcher had just asked — it is not a record of what the
  operator was doing at that moment. In-session speech is transcribed but **not yet aligned to
  individual decisions**; that needs the per-session timer alignment described in
  `docs/NARRATION.md`.
- **The questionnaire sections are exploratory and say so.** The scenario and run contrasts on the
  post-session surveys are experimental (a 2×2 crossover, the same `study_analysis.crossover`
  estimator used on every performance measure). Everything relating a questionnaire to behaviour is
  correlational, and the whole disposition family is Holm-corrected together with both the raw and
  adjusted p shown — at n = 32 across 40 tests, an uncorrected table would be guaranteed to display
  two or three "findings". Battery scoring is imported from `agent_scenario_stats.score_attitudes`
  (the reverse-keying that `docs/STUDY_BUILD.md` §10 specifies), never reimplemented.

Three sources, kept distinct so any figure can be audited:

| Source | What it supplies | Recomputed? |
|---|---|---|
| `Results/Participants/*.json` | every decision-level analysis (composition, pre-emption, timing, the card artefacts), plus both questionnaire streams — the post-session NASA-TLX and trust scales from `survey_response`, and the pre-study demographics / prior-experience / AI-disposition batteries from the `demographics` block | yes, on every build |
| `docs/reports/study_analysis.json` | crossover performance, reliance ladders, failure-recovery episodes | no — read, so the two pages cannot disagree |
| `Results/Narration/*_s1/quotes.json` | coded debrief quotes, single-coder and uncalibrated | yes |
| `docs/reports/smart_benchmark.json` | score a near-perfect automated operator achieves on the four fixed games | no — regenerate with `npx tsx sim/engine.mts --games --reps=5` |

Edit `scripts/findings_synthesis_template.html`, never the generated page. P09 is excluded
throughout. The tier palette and reliance ladder are inherited from `study_analysis_template.html`;
the route palette (Aggressive / Conservative / Manual) is new and was validated for colour-vision
separation, chroma, lightness and surface contrast in both light and dark mode.


## `two-tiers-two-scenarios.html` (rebuilt 2026-09-25)

Log-only analysis of the participant study, organised around the design that was actually run: a
**2×2 crossover** (every participant plays Strategic Heavy and Tactical Heavy, in counterbalanced
order). Surveys and recordings are deliberately left out. Sections:

1. **Design** — the four games (see below) and what n can detect.
2. **Performance** — score per point on offer as the primary outcome, completion alongside;
   crossover estimates for scenario, run and interaction, plus a run-2-only check.
3. **Reliance over time** — the reliance ladder per tier, drift within each 8-minute run, and
   run 1 vs run 2.
4. **Mission size** — assistant use by category A–E, with a GEE controlling scenario and run.
5. **Drone failures** — every recovery episode classified (recovered with Suggest / by hand /
   abandoned when unfixable / abandoned without trying / abandoned right after Suggest), and its
   relation to how much each person relies on the assistants.
6. **Reliance vs performance.**
7. **Outliers** — robust-z screen within game; a toggle reruns everything without flagged people.

Controls at the top switch build window (`study-v1.12` only, or `v1.4`+) and outlier exclusion.

**Four games, not two.** Everyone played seed 42 and the mission stream is seeded by
`seed ^ sessionNumber`, so each scenario × run cell is one fixed game played by only one order
group (points on offer: Strategic 2260 / 2000, Tactical 1540 / 2900 for run 1 / run 2). Raw score
is therefore not comparable across runs, and learning cannot be separated from game difficulty
from the logs alone. The page uses score ÷ points on offer throughout.

```bash
python scripts/study_analysis.py           # writes the page + study_analysis.json
python scripts/study_analysis.py --print   # also prints a text summary
```

Pipeline: `scripts/study_analysis.py` (needs numpy, scipy, statsmodels, pandas) injects its
result into `scripts/study_analysis_template.html`. Edit the **template**, never the generated
HTML. Reads only `Results/Participants/`; participant ids are file names (some logs still carry an
un-anonymised in-app id). P09 is always excluded (ε = 0.2 fault test; participant did not follow
the task).

## `two-tiers-two-scenarios-legacy.html`

The previous cohort-window page (built by `scripts/build_agent_report.py`, writes `aggregate.json`
too). Kept because it is still the only page with the post-session trust and AI-attitude figures.
Its text and numbers below are from that older version.

### Legacy page notes

A single self-contained page pooling **every complete session collected so far**, to answer the
questions the per-participant reports cannot:

1. Do operators treat the **Strategic Assistant** and the **Tactical Assistant** differently?
2. Does that change between the **Strategic Heavy** and **Tactical Heavy** scenarios?
3. Does pre-study **AI attitude** predict which assistant a person leans on, or how much they trust
   each?

Every figure is scoped to a **build window** you pick at the top of the page, because the build
changed underneath the data several times and not every window is poolable (see
[`../STUDY_BUILD.md`](../STUDY_BUILD.md) and [`../SCENARIOS.md`](../SCENARIOS.md)). The windows are
nested: `All` ⊇ `Pilot` ⊎ `v1.0+` ⊇ `v1.2+` ⊇ `v1.4+` ⊇ `v1.5+`.

**Open it by double-clicking the file.** It is one HTML file with the data embedded — no server,
no build step, no network. Offline the page falls back from IBM Plex to Georgia / system sans /
Consolas; online it pulls the Plex faces from Google Fonts. Nothing else is ever fetched.

`aggregate.json` beside it is the same computed numbers plus the raw per-session rows, for checking
a figure or re-plotting elsewhere.

## Regenerating

```bash
python scripts/build_agent_report.py     # no arguments, standard library only
```

Re-run it whenever a participant is added. Nothing in the output is hand-written: every number,
caption figure and verdict sentence is computed from the logs.

The pipeline is three files, each of which also runs standalone:

| File | Does |
|---|---|
| `scripts/agent_scenario_stats.py` | One row per completed session, straight from the event logs. Also scores the pre-study AI-attitude battery per `STUDY_BUILD.md` §10 (reverse-keyed items are flipped here, at analysis time — logs store raw). |
| `scripts/agent_scenario_aggregate.py` | Cohort × scenario × tier rollups, Wilson intervals, within-participant contrasts, order effects, attitude/trust correlations. |
| `scripts/build_agent_report.py` | Injects the result into `scripts/agent_report_template.html` and writes this directory. |

Edit the **template**, never the generated HTML — the next build overwrites it.

## What the data currently supports

At the time of writing: **15 sessions from 8 participants**, all at ε = 0.

- Behavioural measures (uptake, acceptance, latency, completion) exist for everyone, subject to the
  per-build field availability the page annotates.
- **Post-session trust** in each assistant exists for everyone; two participants (`P-6921`,
  `P-8561`) left every trust and workload slider on its default and are flagged as straight-lined
  and excluded from the survey figures only.
- The **pre-study AI-attitude battery** (AIAS-4, verification propensity, delegation boundary)
  arrived in `study-v1.3`, so it covers **2 participants**. That is not enough to relate AI
  scepticism to anything; the page says so plainly and shows the individual profiles instead. The
  correlations are already wired and will populate as participants are added — expect roughly
  15–20 on `study-v1.3`+ before even a descriptive correlation is worth reading.

## Excluded from every figure

- `logs/Pilots/auto/` — synthetic sessions from the headless harness, not people.
- `sar_snapshot_*.json` — partial mid-session dumps.
- Sessions with no `session_ended` event (abandoned mid-run).
