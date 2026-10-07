# Round 2 · supervisor log

Same checks as round 1: data integrity against the off-repo SHA-256 manifest
(`G:\Files\Code\_backups\GraphColouringNew_data_2026-10-07`), an independent re-run of each script, and
a read for the known traps and the round-2 rules (`BRIEFING.md`). q-values are computed only once all
seven spec tables are in, by one Benjamini–Hochberg correction across the round.

## Workstreams

| WS | Data intact | Re-run reproduces | Spec rows (extras) | Agent's candidates | Supervisor note |
|---|---|---|---|---|---|
| D · trust | ✓ | ✓ | 125 (11 rows = 2 declared extra variants) | Strategic trust falls run 1 → 2: b = −0.78 [−1.24, −0.32], p = .0009; with game fixed: −1.23, p = .005; both orders; LOO −0.84 to −0.66 | A replication of round 1's crossover run effect (already in the brief) — **not new**. What is new is the attribution, below. |

## Notes

- **D · the trust drop is run (+ scenario), not game.** Round 1 framed it as "lower after a Strategic
  Heavy session"; with game as a fixed effect the run effect is *larger* (−1.23), and in the six swapped
  people Strategic Heavy played second is rated lower for **both** games (S1: 3.00 vs 4.64; S2: 4.05 vs
  6.00), while S2 is rated higher than S1 in both positions — so it is not game S2. Read: two penalties
  stack — a second-session penalty and a small Strategic Heavy penalty (+0.48 for Tactical Heavy,
  p ≈ .04; same direction but +0.23, p = .57 on session 1 alone). The cells of three are direction only.
  This *reverses* round 1's reframing proposal for brief Finding 5: keep "fell between sessions", add
  that Strategic Heavy adds a smaller penalty on top. Mechanism offered (debriefs: P15, P33, P32): more
  spare attention in session 2 to notice the cards' flaws.
- **D · exclude from the BH pool:** D2d, D2e, D2h (descriptive cells of three; their p-values are
  meaningless). Also do not count X1.M4 / D4c.M4 / D4d.M4 as new candidates (they repeat round-1 H1's
  between-person trust–reliance link).
- **D · cohort caution:** the six swapped people are also the newest cohort (v1.13), so anything that
  rests on them (e.g. D1b.idx, p = .043) may be a cohort effect.
- **D · nulls worth keeping:** session-1 trust does not predict the change in session-2 uptake (trust
  does not lead behaviour); with game fixed, nothing measured in a session predicts its trust rating;
  tactical trust tracks tactical behaviour between people but not within.

## G · learning (verified: data intact, re-run reproduces)
- Agent's candidate: strategic decisions get faster within a session, net of the forced waits —
  b = −0.046 log-seconds per minute [−0.070, −0.023], p = .0001 (about −31% over 8 min), controlling for
  run, card taken, mission type, drones needed and scenario. Passes S-s1, both orders, LOO. Holds with the
  final 90 s removed (p = .048, which guards against end-of-session cut-off) and in session 2 alone
  (p = .050). Session 2 is faster than session 1 too (strategic p = .003, weakens to .16 with game fixed;
  tactical p = .002, holds at .046 with game fixed). A warm-up/practice effect; modest interest.
- Strongest null: calibration does NOT improve with experience (composition × run OR 0.55–0.86, all
  p > .12; confounded with game). Operators do not learn to avoid dominated cards.
- **Page error flagged:** the synthesis page's learning caption "This is where the learning effect shows
  up" is not supported once game is fixed (driven by the unreliable Tactical game 2 benchmark). Fix later.

## E · stated preference (NOT YET RE-RUN by supervisor — usage limit)
- Agent reports no candidate likely to reach q < .10. Closest: people who mention a specific card error
  go manual more on single-type missions (OR 2.72 [1.02, 7.30], p = .046; passes gates; between-person).
- κ vs round-1 second coding .96 — but same AI model and near-identical codebook, so closer to
  test–retest than independent coders; agent saw a few round-1 lines. **A human second coder is still
  needed for reliability.** Sign test on this coding 17 vs 7, p = .064.

## Pooling rule for the false-discovery correction (written BEFORE any q-value was computed)

One Benjamini–Hochberg correction over every spec-table row with a numeric p, from all seven
workstreams, **except**:
1. rows on the `S-6` sample (the six swapped people) — declared descriptive-only in the briefing;
2. D2d, D2e, D2h — descriptive cells of three people (agent D's flag);
3. F4.1 — a likelihood-ratio p from a model that treats a yes/no outcome as continuous (agent F's flag;
   its valid versions F4.1p / F4.3 stay in);
4. rows without an estimate (models that could not be fitted).

Rows the agents themselves identified as artefacts (A1a/b/c and A8a time-left; B2d / B2d-r1 final-90 s
trend; B's X3) **stay in the pool** — removing tests after seeing them would bias the correction — and
are vetoed at the review stage if they pass. A row becomes a **candidate** only if: q < .10, AND every
applicable gate passes (S-s1 direction, both-orders direction, no leave-one-out sign flip — `na` counts
as not applicable), AND the supervisor's review finds no artefact and a stated mechanism.

## All seven verified

A, B, C, E, F re-run by the supervisor: every spec table reproduced **byte-identical**. Data matched the
backup before and after. (D and G verified earlier.)

## Pooled correction (`scripts/analysis_round2/supervisor_merge.py` → `round2_pooled.csv`)

817 tests; 716 pooled under the rule above; **34 reach q < .10; 33 also pass the gates; 32 after the
pre-declared artefacts are removed.** (A first run of the merge matched excluded/artefact ids exactly
and so let `D2e.first`, `D2h.S2` and `A1a-pool` through; ids carry suffixes, so the rule is now applied
by prefix. That implements the rule as written; it does not change it.) The three p = 0 rows are genuine
(intervals far from zero; p below print precision).

## Review: the 32 rows grouped into findings

| Finding | Rows (q) | Verdict | Why |
|---|---|---|---|
| **R2-1 · Pre-empting the cards is a stable personal trait** | F4.3 ρ = .56 (q .035), .72 on S-27 (q .003); F4.1p person share .25 (q .030) | **Promote — strong** | Operator behaviour; passes all gates; 15 of 33 never pre-empt. |
| **R2-2 · Bigger jobs go to the assistant on both tiers, within person** | B5a Suggest ~ plan size OR 2.57 (q < .001); B5d card ~ three-type OR 1.84 (q .096); C·D2 uptake scenario effect with game fixed (q .039) | **Promote — strong** (tactical half new; strategic half replicates Finding 2, now with game controlled) | |
| **R2-3 · Cards save decision time, mostly on three-type missions** | C3 card vs manual on three-type −0.42 log-s; card × three-type −0.81 (both q ≈ 0) | **Promote — strong** (round-1 H9's exploratory speed result, now confirmed) | |
| **R2-4 · Practice: decisions speed up within and across sessions** | G4.5 within session (q .009); G4.4 (q .006), G4.1 (q .072), G4.6 tactical (q .058), G4.7 S-27 (q .038); C·D2 tactical consulting rises in session 2 (q .093) | **Promote — strong for within-session; moderate across sessions** | Across-session strategic speed-up weakens to p = .16 with game fixed (game not ruled out); within-session effect cannot be game or scenario. |
| **R2-5 · Reliance pays through throughput, within person** | C2 a higher-reliance session leaves fewer missions never allocated, −0.78/SD (q .038) | **Promote — moderate** | Card uptake alone is null within person; score does not rise; mediation shares partly accounting. |
| **R2-6 · Low-reliance operators attempt recovery less** | A4c ρ = .54 (q .041), X1c .51 (q .072), S-27 .54 (q .081) | **Promote — suggestive** | Between people only; carried by 4 never-attempters; episode-level GEE p ≈ .056. |
| **R2-7 · Strategic trust falls from session 1 to 2** | D2a.run2 −0.78 (q .038) | **Replication** of round 1 / brief | Attribution (not game) is the new part, see D notes. |
| Missions never allocated: Tactical − Strategic Heavy | C·D2, D4, D5 (q ≤ .099) | **Context, not a finding** | A property of the scenario design (Strategic Heavy sends more missions). |
| Benchmark share: scenario effect with game fixed | C·D2, D4 (q ≈ .07–.08) | **Veto** | Rests on the unreliable Tactical game 2 benchmark. |
| Suggest use when a strategic backlog is waiting | B4a (q .040), B4a-r1, B4a S-s1 | **Demote — suggestive** | Gone once time-in-session is controlled (B4a-el q .33): practice, not pressure. |
| Strategic uptake → trust between people | D·X1.M4 (q .012) | **Known** | Repeats round 1 H1. |
| Abandonment when Suggest could not cover the task | A5-exact (q .072) | **Context** | Mostly about the assistant's limit; harder failures by construction. |
| Card-mission failures fall in session 2, SF order | D3d.M5SF (q .078) | **Veto** | Single-order descriptive side product, no hypothesis or mechanism. |
| Manual drones track the Conservative total | F1.2 (q .004) | **Excluded (gate fail)** | Mixes anchoring with the reserve limit; the clean anchoring row fails the session-1 gate. |
| Suggest use in the final 90 s | B2d-r1 (q .041) | **Artefact** (pre-declared) | Straight-line trend artefact; placebo windows null. |

**Result: 6 findings promoted (2 strong, 1 strong-with-a-moderate-half, 2 moderate, 1 suggestive) + 1
replication**, all exploratory candidates to confirm on new data.

## Status
- Round complete and verified. Participant logs set writable again at the end of the round.


## Erratum, 2026-10-07 (after the round closed)

Workstream A imports round 1's `h3_recovery.parse_session`, which had a bug (round-1 SUPERVISOR_LOG,
"Erratum"): tasks cut short by abandonment were not counted as executing, so Suggest's blind spot was
undercounted. Re-running `wA_recovery.py` and `supervisor_merge.py` with the fix:

- **A4c (R2-6) unchanged** (rho .54, p .0012). Attempt definitions do not use the press rebuild.
- **A5** (no clean Suggest fix at the failure): 10 fixable failures, **9 abandoned**, vs 39 of 154
  (Fisher p .0001; was 6/7 vs 42/157). Still too few to fit the PC1 interaction.
- **A6** (abandoning a working Suggest plan): **3** of 50 solved-press episodes, not 11 of 58. Its
  "who / when / what it was worth" models now rest on 3 events and are not interpretable.
- **A7** exposure groups grow (any refusal 13 -> 18 people; blind spot 8 -> 14); still null.
- Pooled table: 722 pooled (was 716), q < .10: 37 (was 34), passing gates 36, non-artefact 35. The
  three new rows are A4c on v1.12+ (already promoted as R2-6), D2b.run2 (already promoted as R2-7's
  replication) and A6b on S-27 (3 abandoned events -- not promotable). **No promoted finding changes.**

The as-run tables are kept unchanged as the round-2 record (`wA_specs.csv`, `round2_pooled.csv`);
the corrected ones sit beside them (`*_corrected_2026-10-07.csv`, plus
`wA_recovery_corrected_output_2026-10-07.txt`). The round-2 report text for A5-A7 describes the as-run
numbers.
