# Analysis round 2 — structured exploration (plan for sign-off)

**Status: DRAFT.** Round 1 tested ten pre-registered hypotheses; none survived correction across all
ten (`docs/analysis/round1/ROUND1_SUMMARY.md`, `Results/analysis_round1.html`). Round 2 deliberately
widens the search: alternative versions, opposite hypotheses, constrained situations and new questions
drawn from the synthesis page. That makes it **exploratory by design**. Its output is *candidate*
findings to confirm on new data, not confirmed claims. The rules in §2 stop that exploration from
becoming p-hacking.

## 1 · A confound found while planning

Up to P30 the game was set by session number, so **scenario order and game pairing are almost the
same split**:

| | Game pairing S1 + T2 | Game pairing S2 + T1 |
|---|---|---|
| Strategic Heavy first | 14 (P02–P30, even) | 3 (P32, P34, P36 — swapped) |
| Tactical Heavy first | 3 (P31, P33, P35 — swapped) | 13 (P01–P29, odd) |

So any "order" effect — including round 1's strategic trust drop after a Strategic Heavy session (H5) —
could equally be a *game* effect. Only the six swapped participants separate the two. Every round-2
workstream that touches order, scenario or performance must check its result against this.

## 2 · Rules that keep this from becoming p-hacking

1. **A fixed menu of variants per workstream** (§4), written here before anything runs. An agent may add
   at most **three** extra variants of its own, each logged with the reason *before* it is run.
2. **Every variant is reported** in a specification table: estimate, interval, p, n, sample — including
   every null. A result is read off the *pattern across variants* (how many agree in direction, how many
   pass), never off the best one.
3. **One false-discovery correction across the whole round.** Every test from every workstream goes into
   a single Benjamini–Hochberg correction (q-values). A candidate needs **q < .10**.
4. **Robustness gates.** On top of q < .10, a candidate must:
   - **hold in direction** on the session-1-only sample (no order or carry-over) and in both scenario orders;
   - **survive leave-one-person-out:** no single participant flips its sign;
   - use the **small-sample-corrected** GEE errors throughout (round-1 lesson);
   - if it is defined around an event (before/after something), **pass a null simulation** first
     (round-1 H8 lesson).
5. **A stated mechanism.** Each candidate comes with a one-sentence account of *why*, checked against the
   debriefs where possible. A pattern with no plausible mechanism is reported but not promoted.
6. **Focus on operators, not on how the assistants were built.** Results that only describe the
   assistants' own rules (e.g. how often the Conservative card pads unused drones) are context, not
   findings. Operators' *reactions* to those rules are in scope.

**Sample variants, applied in every workstream** (your point 1):

| Code | Sample | Why |
|---|---|---|
| S-all | All 33 | Most power |
| S-v112 | The 24 with identical game versions | Removes early-build differences |
| S-s1 | Session 1 only, all 33 | A clean between-person comparison: no order, carry-over or learning |
| S-bal | 12 people: the 6 swapped + 3 seeded-random unswapped from each order | Order and game pairing fully crossed. Low power, so a direction check only |

## 3 · What is dropped, and why

| Round-1 hypothesis | Decision | Reason |
|---|---|---|
| H2 · checking cost | **Drop** | Without eye tracking, checking time is just the gap between clicks; no variant fixes the measurement. |
| H4 · benchmark shortfall | **Close** | Explained: one unlucky benchmark game. Its by-product (missions never allocated) moves into workstream C. |
| H7 · attitude to AI | **Drop** | The sample has almost no sceptics (average 8/10). No variant can create variation that is not there. |
| H8 · illogical card over time | **Close** | Four earlier nulls plus a calibrated null. Operators' *in-the-moment* reaction to it moves into workstream F. |

## 4 · The seven workstreams (one agent each)

### A · Recovery — what makes operators attempt a fix? *(from H3)*
H3's real finding is "attempting beats giving up". So what decides whether someone attempts?
1. Time left in the session at the failure (late failures abandoned more = rational triage?).
2. Mission size / reward at stake, and how many drones are left on the mission.
3. Recent failures (a second failure soon after the first).
4. The person's position on the round-1 reliance axis (PC1).
5. *Opposite:* do high-reliance operators abandon *more* when Suggest is not offered a clean fix?
6. Abandoning a **working** Suggest plan (9 of 11 cases): who does it, and when?
7. After a Suggest failure: within-person change in later attempt rates.
8. *Constrained:* fixable failures on three-type missions only.

### B · Load and pace — does pressure show up somewhere else? *(from H9)*
H9 found no effect of queue length at the moment of decision. Does pressure show up in another form?
1. Other load measures:
   - how long missions waited before being opened;
   - missions in flight;
   - drone failures in the last 60 s;
   - reserve depletion.
2. The final 90 s of a session (deadline pressure).
3. *Opposite:* under load, operators pre-empt *more* (decide before the cards load) — "no time to wait".
4. *Constrained:* tactical tier only (Suggest use under load), and three-type missions only.
5. Speed as the reason: within-person, does reliance rise on missions where the assistant saves the
   most time (large plans)?
6. **In-session narration:** in the 13 sessions aligned to the game clock, find moments of spoken
   overload, then compare queue, uptake and Suggest use around them against a null simulation.

### C · The reliance trait and its payoff *(from H1 + H10, and H4's by-product)*
1. What predicts someone's position on the reliance axis? Gaming frequency, prior experience, first-two-minutes performance, session-1 failures.
2. **Throughput, not success:** does reliance pay by getting more missions allocated (fewer never allocated, faster arrival-to-allocation) rather than by making each mission succeed?
3. *Constrained:* the payoff on three-type missions (where cards save time) vs single-type.
4. *Opposite:* on single-type missions, does manual do *better*?
5. Penalty accrued per mission, card vs manual, within person.

### D · Trust — separating order from game *(from H5)*
1. **Session 1 only:** strategic trust after a Strategic Heavy vs a Tactical Heavy first session, a clean between-person comparison.
2. The 6 swapped vs the matched 6 unswapped (S-bal): is the drop tied to the scenario or to game S2?
3. What in a session predicts that session's trust rating, within person:
   - share of single-type missions;
   - dominated or illogical cards *seen*;
   - card missions failed;
   - score.
4. The tactical tier: does tactical trust track tactical behaviour within person?
5. *Opposite:* does trust lead behaviour (session-1 trust predicts the change in session-2 uptake)?

### E · What people say, done reliably *(from H6)*
1. A **third independent coding** using the agreed codebook (with your "conditional" ruling written in), and κ against the second coding. Can the coding reach reliability now the definition is fixed?
2. Link stated *reasons* to behaviour:
   - those who cite **speed** should show reliance rising most on large missions;
   - those who cite **visible errors** should go manual more on single-type missions;
   - those who say they **can't check** should keep tactical plans unmodified more.
3. Stated scale-conditional preference against each person's own composition effect.

### F · How operators handle the strategic cards *(new — from the synthesis page)*
1. **Anchoring:** do manual allocations track the card totals beyond what the mission needs? The card totals vary with reserve state, so at a fixed need they act as a natural experiment.
2. **Sensible edits:** when operators edit a card, do they remove the drone types the mission does not use?
3. **Discrimination:** facing a dominated or illogical Conservative card, do operators *in the moment* choose Aggressive or manual — and does previewing both cards (`strategic_card_previewed`) make that more likely?
4. Pre-emption (deciding before the cards load): person trait or situation?

### G · Learning and calibration across the sessions *(new — from the synthesis page)*
1. **Calibration:** does reliance become *better targeted* with experience? Test whether the composition effect (cards on big missions, manual on small) is stronger in session 2 (composition × run interaction), and on the session-1-only vs session-2-only samples.
2. Within-session learning curves: the session-2 dip-then-recovery in card uptake. Is it real once composition is held fixed?
3. Do operators learn to avoid dominated cards over the two sessions?
4. Faster decisions over time: decision speed by run, net of the forced waits.

## 5 · Output

As round 1:
- scripts in `scripts/analysis_round2/` (prefix `wA_` … `wG_`);
- reports in `docs/analysis/round2/`;
- no edits to data, app or pages;
- data checked against the same backup after every agent.

**New:** each report ends with its full specification table as CSV (`wX_specs.csv`). The supervisor
merges them for the single Benjamini–Hochberg correction, applies the §2 gates, re-runs every
candidate, and adds a round-2 section to the results page.

## 6 · Decisions for you

- **A · Bar for a candidate:** q < .10 plus the §2 gates (proposed), or stricter (q < .05)?
- **B · Workstreams:** all seven, or drop any? (B6, the narration, is the most speculative; F and G are new.)
- **C · Balanced subset:** seeded random choice of the 6 unswapped participants, or matched on something (e.g. card uptake in session 1)?

## Amendments

### 2026-10-07 · Signed off, with these decisions

- **A · Bar:** q < .10 (Benjamini–Hochberg across the whole round) plus the §2 gates.
- **B · Workstreams:** all seven.
- **C · Balanced subset dropped.** At 12 people it is too small to be useful. Instead, every workstream
  handles game difficulty and order **explicitly**, as information rather than something to ignore.
  - **Samples** (these replace S-bal):
    - **S-27:** all except the six swapped participants. Order and game pairing are then
      perfectly aligned, so an effect here is "order + pairing" together; report it that way.
    - **S-6:** the six swapped participants alone. Descriptive only — the one place order and game
      separate.
    - **Game-adjusted models:** game (scenario × game index) as a fixed effect alongside order, on S-all.
  - **Performance metrics.** Anything about performance reports at least these, so no conclusion rests
    on one game's quirks:
    - score efficiency (score ÷ points available);
    - a per-game z-score (score standardised within each of the four games);
    - share of the near-perfect operator's score, flagged as unreliable on Tactical game 2 (round-1 H4);
    - share of the best human score on that game.
    - P01 and P02 are on half task weights: rescale or exclude them, and say which.
  - **Difficulty and order as a question in their own right** (folded into workstream C): how hard was
    each of the four games for people, and does performance depend on game, order, or their
    combination once both are in one model?
