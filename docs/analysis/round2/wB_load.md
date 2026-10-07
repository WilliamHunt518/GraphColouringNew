# Round 2 · Workstream B · Load and pace — does pressure show up somewhere else?

Builds on round-1 H9 (`docs/analysis/round1/h9_workload_speed.md`), which found no effect of queue length
at the moment of a strategic decision across ~20 specifications. This workstream looks for pressure in
other forms. **Everything here is exploratory: a result is at most a candidate to confirm on new data.**

Scripts: `scripts/analysis_round2/wB_main.py` (runs everything), `wB_common.py` (loaders, load measures,
GEE, gates), `wB_load.py` (B1–B5 + extras), `wB_narration.py` (B6). Spec table:
`docs/analysis/round2/wB_specs.csv` (90 rows, every test including nulls). P09 excluded. All raw p-values;
the round-wide Benjamini–Hochberg correction is the supervisor's.

**Terms.** *OR* (odds ratio): how much the odds of an outcome change per unit of the predictor; 1 = no
change. *Within person*: each load measure is centred on the operator's own average, so the estimate
compares an operator with themselves under more vs less load. *GEE*: regression that allows for each
operator contributing many decisions; all fits here use the small-sample (bias-reduced) error correction.
*Game fixed effect*: a separate baseline for each of the four games (scenario × game index), so a game
that is simply harder cannot pose as a load effect. *Null simulation*: repeating the same measurement at
random moments to see what it produces by chance. *Exogenous load*: mission arrivals in the previous 60 s,
fixed by the seeded game, so an operator's own slowness cannot create it (queue length can).

## 1 · Candidates

**One weak candidate, with an explicit caveat. Nothing else.**

**B4a — Suggest is consulted more when strategic decisions are waiting at the moment the operator starts
on the plan.** Within person, each extra mission awaiting a strategic decision at the first planner action
(Suggest press or first drag) raises the odds of consulting Suggest: **OR 1.20 [1.08, 1.34], p = .001**
(630 plans, 33 people; controls: log plan size, drone types, game, run).

| Gate | Result |
|---|---|
| S-s1 (session 1 only) | same direction: OR 1.23 [1.07, 1.41], p = .004 |
| Both scenario orders | same direction in both |
| S-v112 / S-27 ("order + pairing") | 1.18 [1.05, 1.33] p = .006 / 1.13 [1.03, 1.25] p = .013 |
| Leave-one-person-out | OR 1.17 – 1.23; no single person flips the sign |
| Three-type missions only (B4g) | 1.23 [1.04, 1.45], p = .016 |
| First action within 10 s of opening (no deferral; B4a-r1) | 1.26 [1.10, 1.45], p = .001 |

**Caveat — why it is weak.** It is a sharper timing of the tactical-consult signal round-1 H9 already
reported post hoc (H9's measure, re-fitted here with game FE and bias-reduced errors: OR 1.15, p = .008,
B4a-r2), and it carries the same two weaknesses: **adding elapsed session time shrinks it to OR 1.13
[0.99, 1.29], p = .074** (B4a-el; consulting rises over a session, and so does the queue), and **the
exogenous version is not significant** (arrivals in the 60 s before the first action, OR 1.08
[0.97, 1.20], p = .15, B4c). So it is partly drift over the session; what remains is in the right direction
but not established. Separating the strategic queue from other open tactical plans gives 1.13 (p = .079,
B4a-strat); other tactical plans pending on their own do nothing (0.91, B4b).

**Mechanism (one sentence).** When strategic decisions are waiting, operators press Suggest so the plan
fills in while they go back to the queue: among consulted plans, another strategic panel was opened before
confirming in **52%** of plans when ≥ 1 decision was waiting at the first action vs **16%** when none was
(descriptive). Debriefs say exactly this: `P15/agent_comparison/1812` (uses it so "in the other screen I
have something to do"), `P18/scenario_comparison/1577` ("to work in parallel"),
`P32/scenario_comparison/1497` (used it "so they won't all back up").

## 2 · Everything else, by variant

### B1 · Other load measures (S-all unless noted; outcome = card taken as-is / Suggest consulted)

| Measure (within person) | Card taken OR | Suggest consulted OR |
|---|---|---|
| B1a · the mission's own wait, arrival → first opened (per 60 s) | 1.15 [0.97, 1.38] p = .11 | 1.12 [0.93, 1.35] p = .23 |
| B1b · age of the oldest other mission still waiting (per 60 s) | 1.10 [0.96, 1.25] p = .16 | 1.12 [0.96, 1.31] p = .16 |
| B1c · missions in flight | 1.02 p = .81 | 1.18 [0.96, 1.46] p = .12 |
| B1d · drone failures in the previous 60 s | 1.17 [0.95, 1.44] p = .13 | 1.06 p = .70 |
| B1e · drones in reserve (per 5; < 1 = depletion → more reliance) | 0.94 p = .36 | 0.93 p = .34 |
| B1f · per-colour reserve slack (min over needed colours, available − needed) | 1.00 p = .94 | — |

All null. All eleven lean the "pressure → reliance" way (B1f only trivially), but the measures are correlated with each other
and with time in the session, so the lean is not independent evidence: with elapsed time added, the oldest
wait goes to 1.06 / 0.90 and failures to 1.11 / 0.89 (B1b-el, B1d-el). On S-v112, S-s1 and S-27 the two
headline measures (B1b, B1d) stay null (ORs 0.97–1.19, smallest p = .084 for B1b card-taking in session 1).

### B2 · The final 90 s (deadline pressure; 76 strategic decisions and 83 confirmed plans fall in it)

- **Card-taking does not change at the end:** OR 1.30 (p = .36) raw, 1.09 (p = .79) net of a linear time
  trend; same on S-v112 / S-s1 / S-27 (0.87–1.25). Raw uptake by window: .64, .68, .64, .68, **.63**.
- **Pre-emptive manual** (manual chosen before the cards were readable) does not rise: 0.80 (p = .56).
- **Strategic decision time**: −6% (p = .42). **Tactical open → confirm**: −15% (b = −0.16 log s, p = .053)
  — not interpretable, because plans opened late and taking long are cut off by the session end (15
  planners opened in the last 90 s were never confirmed), which censors exactly the slow ones.
- **Suggest consulting net of a linear trend looks *lower* at the end** (B2d: OR 0.54 [0.31, 0.95],
  p = .033; v1.12+ 0.41, s1 0.31, S-27 0.63) — the opposite of the deadline hypothesis — **but it is a
  curve-shape artefact, not a deadline effect.** Consulting rises over a session and then flattens
  (.71, .77, .79, .82, .76); a straight-line trend overshoots at both ends. The placebo check (the same
  90-s indicator net of the linear trend, at every position) gives OR 0.61 for 0–90 s, 1.50 for 180–270 s
  and 0.55 for 390–480 s: the end is no more unusual than the start. The local comparison (final 90 s vs
  the 120 s before, no trend) is null: **OR 0.93 [0.50, 1.73], p = .82** (B2d-r2); a quadratic trend gives
  0.51 (p = .089, B2d-r3). Including the 15 cut-off planners makes it look stronger (0.46, p = .001,
  B2d-r1), but those are mostly planners nobody touched before the clock ran out, which count as "not
  consulted" without any decision being made. Not a candidate.

### B3 · Opposite: under load, operators pre-empt more ("no time to wait for the cards")

97 of 606 decisions were pre-emptive manual (18 people). Against four load measures not used in H9, net of
time in session: oldest waiting mission 1.03 (p = .76), missions in flight 0.93 (p = .69), recent failures
1.10 (p = .65), the mission's own wait 1.03 (p = .79); exogenous arrivals on three-type missions 0.99
(p = .90). S-v112 / S-s1 / S-27 for the oldest-wait version: 1.01 / 1.05 / 1.00. **Clean null** — H9's
apparent queue → pre-emption link (which already failed its time control) does not reappear under any
other measure of load.

### B4 · Constrained

- Tactical tier, load at the first planner action: **B4a** (above), B4b null, B4c weak (exogenous).
- Three-type strategic missions only: oldest waiting mission OR 1.16 [0.98, 1.37] p = .079 (B4d); exogenous
  arrivals 0.98 (p = .81, B4e); drone failures in the previous 60 s **1.43 [0.95, 2.15] p = .085** (B4f; all
  three gates pass, LOO 1.37–1.64). The failure result is the largest odds ratio in B1/B4 but rests on few
  decisions with a recent failure (mean 0.4 per decision) and is not significant; worth a look on new data,
  not a candidate.
- Three-type tactical: B4g, 1.23 (p = .016) — the same signal as B4a.

### B5 · Speed as the reason

- Context (operators, within person): Suggest is consulted far more on large plans (OR 2.57 per log unit of
  drones × tasks, B5a) and cards are taken more on three-type missions (OR 1.84, B5d) — exactly where H9
  found the assistant saves time. This is the known composition effect (brief Finding 2).
- **If speed were why people rely, load should push reliance most where the assistant saves most time. It
  does not:** queue × plan size on consulting OR 0.99 (p = .84; v1.12+ 0.96, s1 0.96, S-27 0.99);
  exogenous arrivals × plan size 1.06 (p = .52). Strategic: queue × three-type 1.19 [0.98, 1.44] p = .078
  (B5e) but exogenous arrivals × three-type 0.96 (p = .73, B5f). So reliance tracks *where the assistant is
  faster*, but not *when time is short*. Speed reads as a standing reason to use the assistant on big jobs,
  not a load-triggered one.

### Extras (pre-stated before running; see the analysis log)

- **X1 · Checking a revealed Suggest plan:** time from the end of the forced reveal to Deploy on kept plans
  (median 2.7 s) does not shrink with the queue at the last Suggest press: b = +0.008 log s (p = .82).
  No rubber-stamping under load beyond what is already there.
- **X2 · Comparing both cards:** only 4% of card-takers previewed both cards; queue OR 1.07 (p = .71).
- **X3 · Card deliberation net of the forced reveal** is 8% shorter per extra minute the oldest mission has
  waited (b = −0.086 [−0.150, −0.022], p = .009; v1.12+, S-27 similar) — **but it disappears with elapsed
  time** (−0.024, p = .57, X3-el) and on exogenous arrivals (+0.007, p = .84, X3-ex). Operators get faster
  over a session while the oldest wait grows; this is practice, not pressure.

### B6 · In-session narration (suggestive only)

**Alignment.** 13 sessions have `alignment.json`; PIL03 (2) is a pilot without an event log, leaving 11
sessions from 6 people (P01, P03, P04, P05, P06, P07; one or two sessions each). Re-reading the OCR timer
reads leniently (a leading `m:ss`) gave, for every one of the 11, a single-offset cluster of 16–42 reads
covering 300–439 s of the session with a maximum deviation of 0–2 s, so all 11 passed the pre-set rule
(≥ 8 reads, ≥ 300 s coverage, ≤ 3 s deviation) and none was dropped. **Data issue to note:** the
pipeline's own fitted offset in `alignment.json` is the *session-2* cluster for **P01_s1 (916 vs correct
117), P06_s1 (841 vs 205) and PIL03_s1 (884 vs 214)** — those `_s1` recordings contain the whole sitting
and the median-offset fit picks the later session. Anything that used those three offsets for session 1
is ~640–800 s off. A content check (card names spoken vs the nearest panel open/choice) gave median lags of
0.4–6.5 s in five sessions; two sessions with one or two card mentions had ~40 s lags, consistent with
retrospective remarks rather than misalignment given their clean timer fits. No diarisation: researcher
speech is in the transcripts.

**Rule (fixed before looking at behaviour):** a fixed phrase list (`STRICT`: e.g. "too many", "too much",
"overwhelm", "keep up", "stress", "struggl", "no time", "oh no", "oh my god"; `BROAD` adds pace and
frustration words such as "quick", "hurry", "busy", expletives), moments merged within 20 s; behaviour in
a ±60 s window; null = the same number of moments per session drawn from all in-session utterances
(5,000 draws), with a uniform-time null alongside.

**Result.** Spoken overload is rare: **10 strict moments in 11 sessions** (6 sessions, 4 people), and on
reading them only about half express stress or time pressure — the rest are judgements ("too many drones"
on a card) or researcher speech. Around those moments:

| Measure | strict: observed − null | p | broad (20 moments): observed − null | p |
|---|---|---|---|---|
| Strategic queue at the moment | −0.08 missions | .87 | +0.25 | .39 |
| Drone failures in the previous 60 s | +0.15 | .56 | +0.31 | .076 |
| Card uptake, choices within ±60 s | +0.16 | .10 | +0.10 | .093 |
| Suggest consulted, plans within ±60 s | +0.03 | .88 | +0.01 | .85 |

The logged queue is **no higher** when people say they are overloaded than at any random utterance — so
whatever they experience as overload is not queue length, which fits H9's null. The hints (more card
uptake and more recent failures around overload talk) are in the expected direction but rest on 6–20
moments from 4–6 people, a phrase list with ~50% precision, and no diarisation. Suggestive at most.

## 3 · Analysis log (in order)

1. Read the briefing, HYPOTHESES_ROUND2 (§2, §4 B, amendment), ROUND1_SUMMARY, H9 report and script,
   HYPOTHESES_ROUND1 §2 traps, NARRATION.md.
2. Wrote `wB_common.py`: reuses `h9.load_all()` (its cross-check against `load_decisions()` passes, 606 rows
   identical) and adds a per-session timeline giving the game state at any moment (last logged context;
   snapshots every 10 s), failures in a trailing window, oldest waiting mission, per-colour slack, the
   first planner action time, and the queue at the last Suggest press. Wrote the GEE with
   `cov_type='bias_reduced'` and gate code (S-s1 direction, each order's direction, LOO when p < .10).
3. Wrote the B1–B5 menu and the three extras **before running anything**. Extras and reasons (also in the
   `wB_load.py` docstring): **X1** checking time after the Suggest reveal vs queue — pressure may show as
   rubber-stamping rather than more uptake; **X2** previewing both cards vs queue — pressure may narrow the
   comparison of the cards; **X3** card deliberation net of the reveal vs oldest waiting mission — the
   cleanest "rushing" measure, with a load measure H9 did not use.
4. First run. Found NA rows: in S-27 and within one scenario order, game determines run, so
   `C(game) + C(run)` is collinear and the bias-reduced covariance fails. Fixed by dropping `C(run)` where
   each game has a single run (it is then redundant). Rerun.
5. **Added after seeing B2d** (consult lower in the final 90 s net of a linear trend): checked that unconfirmed
   plans were not the cause (B2d-r1, including the 15 cut-off planners), a local comparison without any
   trend (B2d-r2), a quadratic trend (B2d-r3) and a placebo of the same window indicator at every position.
   Conclusion: trend-shape artefact.
6. **Added after seeing B4a**: elapsed-time control (B4a-el), strategic queue separated from tactical
   pending (B4a-strat), plans started within 10 s of opening (B4a-r1), H9's measure for comparison
   (B4a-r2), and a descriptive interleaving check for the mechanism.
7. **Added after seeing X3**: elapsed-time control (X3-el) and exogenous arrivals (X3-ex); X3 on S-v112 /
   S-s1 / S-27. Conclusion: practice effect.
8. B6: inspected only `alignment.json` reads and transcript metadata, then fixed the alignment rule, the
   phrase lists, window, merge rule and null in the `wB_narration.py` docstring before computing any
   behaviour around the moments. Removed one pattern ("help", ambiguous with asking the assistant for help)
   before the first run. Ran once. Read the 10 strict matches afterwards to judge precision; the lists were
   not changed after that.

## 4 · Traps and confounds

1. **No failures injected** (ε = 0) — the assistants never erred on purpose; nothing here concerns error
   detection.
2. **Illogical cards nested in single-type missions** — not a predictor here; composition is controlled and
   three-type-only variants are reported.
3. **Drone types effectively binary** — three-type strata (B4d–g, B5d–f) instead of a linear "types" effect.
4. **Residual missions** — kept, as in H9's primary; they are genuine queue items. Exogenous arrivals count
   non-residual arrivals only.
5. **Forced waits** — strategic times are reported net of `deployEnabledAtMs` where it matters (X3), route
   is controlled in B2f, and X1 measures checking time only after the 1 entry/s Suggest reveal ends.
6. **Manual is not one behaviour** — B3 looks at pre-emptive manual specifically.
7. **Before/after is not a baseline** — B2 (a fixed-time window) got a placebo over all window positions;
   B6 (event-defined) uses a null simulation over random utterances in the same sessions, so the null also
   samples only moments when someone was talking.
8. **Quotes are post-session** — used only for the mechanism, by quote ID; in-session utterances are not
   quoted (identifiable, gitignored).
9. **n = 33** — all GEEs use the bias-reduced correction; B6 has 6 people.

Also: **queue length is endogenous** (slow operators build their own queues), so every load measure is
within person, and exogenous arrivals are reported wherever a result looked positive. **Time in session**
is the main confound in this workstream: queue, oldest wait and consulting all grow over a session, and it
is what removed X3 and weakened B4a. **Order and game**: game fixed effects are in every model; S-27 is
"order + pairing" together; S-6 (six swapped people) was not modelled separately — too few decisions per
load level for a direction estimate to mean anything. **Performance metrics** do not apply: no outcome here
is a score, so the P01/P02 half-weight issue does not arise.

## 5 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wB_main.py
```

Deterministic (the narration null is seeded); about 1.5 minutes. Read-only on `Results/`; writes only
`docs/analysis/round2/wB_specs.csv`. The narration part reads `Results/Narration/<PID>_s<N>/alignment.json`
and `transcript.raw.json`.
