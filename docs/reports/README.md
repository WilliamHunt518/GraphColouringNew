# Aggregate reports

## `two-tiers-two-scenarios.html`

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
