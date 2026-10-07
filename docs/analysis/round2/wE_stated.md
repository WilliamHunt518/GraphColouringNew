# Workstream E · What people say, done reliably

*Round 2, exploratory. Builds on round-1 H6 (`docs/analysis/round1/h6_stated_preference.md`). Every
number below is a candidate for confirmation on new data, not a claim.*

Files:
- codebook `docs/analysis/round2/wE_codebook.md` (written before coding; two rules added during
  coding, listed at its foot);
- codes `docs/analysis/round2/wE_codes.csv` (one row per participant);
- spec table `docs/analysis/round2/wE_specs.csv` (101 rows, 21 marked `extra=1`);
- scripts `scripts/analysis_round2/wE_common.py`, `wE_kappa.py`, `wE_behaviour.py`, `wE_main.py`.

## 1 · Candidates

**None that I expect to reach q < .10.** The strongest result is below. It passes every gate, but
its p = .046 sits among 101 tests in this workstream alone.

**Closest: people who cite a visible strategic error allocate by hand more often on single-type
missions (E2b1).**

| | |
|---|---|
| Estimate | OR 2.72 [1.02, 7.30], p = .046 (S-all, 175 single-type decisions, 33 people) |
| With game fixed effect | OR 2.93 [1.03, 8.35], p = .044 |
| S-v112 / S-27 / S-s1 | 3.33 (p = .043) / 2.69 (p = .097) / 1.60 (p = .44) |
| Gates | same direction in S-s1 ✓; same direction in both scenario orders ✓; leave-one-person-out OR 2.33–3.32, no sign flip ✓ |

- **Mechanism.** The visible error people name is almost always the same one: the card adds drone
  types a single-type mission does not use. That error appears mostly on single-type missions, so
  people who noticed it stop trusting the cards there and allocate by hand. Quote IDs: P13
  debrief@[0:29:55] ("in conservator you don't need camera or lifters, yet it adds it as reserve"),
  P21 debrief@[0:35:03] ("it required only blue drones and kept giving me red and green ones"), P20
  debrief@[0:25:51], P33 debrief@[0:28:11], P35 debrief@[0:29:53].
- **Why it is weak.**
  - It compares people with other people, so it cannot separate "noticing the error causes manual
    allocation" from "people who allocate by hand look more closely and so notice it".
  - The interaction form is weaker: manual on single-type *relative to* three-type missions gives
    OR 1.93 [0.84, 4.41], p = .12 (E2b2). On the round-1 codes it is 1.73, p = .18 (X2-E2b2).

## 2 · Everything else

**Terms.**
- *κ (Cohen's kappa)*: agreement between two coders beyond chance. 0 = chance, 1 = perfect; .60 is
  the usual bar for "reliable".
- *OR (odds ratio)*: how much the odds of a behaviour change. 1 = no change.
- *Interaction OR*: how much *more* the behaviour rises on large missions for the people who give the
  reason than for those who do not.
- *GEE*: the regression for decision-level data, with each person as a cluster. All GEEs use the
  small-sample (bias-reduced) errors.
- *LOO*: leave one person out.

### E1 · Can the coding reach reliability now the definition is fixed?

The third coding agrees almost perfectly with the round-1 second coding. Agreement with the original
single-coder codes is unchanged and stays low.

| Variant | κ | 95% CI | Raw agreement | n |
|---|---|---|---|---|
| E1a `pref` (ranking-first) vs round-1 `pref` | **.96** | [.85, 1.00] | .97 | 33 |
| E1b ruling-applied `stance` vs round-1, same mapping | 1.00 | [1, 1] | 1.00 | 33 |
| E1c `pref` vs original codes (ranking-first) | **.27** | [.07, .49] | .50 | 26 |
| E1d ruling-applied `stance` vs original codes (conditional-first) | −.04 | [−.27, .20] | .35 | 26 |
| E1e / E1f binary "prefers tactical": vs round-1 / vs original | 1.00 / .47 | — / [.12, .77] | 1.00 / .73 | 33 / 26 |
| E1g / E1h states a rule, and rule category, vs round-1 | 1.00 / 1.00 | | 1.00 | 33 |
| E1i v1.12+ cohort; E1j non-low-confidence and not led; E1k recorded debrief only | 1.00; 1.00; .94 | | | 24; 19; 26 |
| X1 (extra) reason codes vs round-1: speed-S, speed-T, visible error-S, can't check-T | .81, .87, .87, .85 | lower bounds .59–.68 | .91–.94 | 33 |
| X3 (extra) Fleiss κ across all three codings (`pref`) | .47 | [.29, .64] | | 26 |

**Where the codings disagree.**

Against round 1, there is one disagreement: P11.
- My code is `strategic`; round 1 coded `both`.
- P11 says they would "miss both equally", but "would probably use the strategic one more".
- My codebook rule P3a (an explicit comparative beats a balanced statement) sends this to
  strategic. A tie reading is just as defensible. It is a low-confidence code either way.

Against the original codes, 13 of 26 disagree. The disagreements fall into four categories:
1. **The original `conditional` against a ranking or `both`** (P11, P17, P25, P31, P28).
2. **The original `neither` (distrusts both) against `tactical` or `both`** (P03, P14, P21). These
   people criticise both assistants but come out on one side.
3. **`none` against a code.** The original is `none` for P18 and P24. P36 is the reverse: `none` in
   my coding, `tactical` in the original.
4. **Different ranking or tie** (P04: tactical vs the original's both; P10: strategic vs tactical).

Per category, κ against the original is:

| Category | κ |
|---|---|
| tactical | .47 |
| strategic | .36 |
| conditional | .28 |
| both | ≈ 0 |
| neither | ≈ 0 |
| none | ≈ 0 |

**What the ruling does.**
- Applying the researcher's ruling (complexity-dependent use counts as `conditional`) makes 19 of 33
  people "conditional": 16 say "more assistance when complex" and 3 say the reverse.
- It makes agreement with the original codes *worse*, not better (E1d κ −.04, against .27 for
  ranking-first).
- So the original coder's "conditional" is neither "states a scale rule" nor "gives no ranking". It
  is narrower and quote-based. The ruling settles the definition for future coding, but it does not
  reconcile the original codes.

**How independent this coding is, and why the agreement may be overstated.** Read κ = .96 with
these four caveats:

1. **Same coder type.** The second and third coders are both instances of the same AI model, working
   from nearly the same codebook. Agreement between two runs of one model is closer to *test–retest*
   reliability than to agreement between two independent human raters.
2. **Partial exposure to round-1 codes.** I read the round-1 report as instructed, with participant
   IDs masked. But it quotes or paraphrases statements I could later recognise in about five
   transcripts: "horses for courses", "reliable … with a grain of salt", "trusted strategic agent
   more", "only one logical way … hit Suggest", and the three people who stated the reverse rule.
3. **What I did not open.** I did not open `h6_codes.csv` or any `quotes.json` until all 33 codes were
   saved. I then saw two rows of `h6_codes.csv` (P01, P02) while checking its column names.
4. **Next step.** A human second coder is still needed before stated preference can be called
   reliable.

**Sign test on this coding.**
- 17 tactical vs 7 strategic, p = .064. Round 1 had 17 vs 6, p = .035; the difference is P11.
- Excluding led and low-confidence codes: 13 vs 3, p = .021.
- All three codings give the same label for 13 of 26 people: tactical 10, conditional 2, strategic 1.

### E2a · Speed: do people who cite speed rely more on the assistant for large missions?

Not detectably. Every estimate points the predicted way, but every interval is wide and includes 1.

| Variant | Interaction OR | 95% CI | p |
|---|---|---|---|
| E2a1 · speed (strategic) × three-type → card taken | 1.37 | [0.54, 3.45] | .51 |
| E2a2 · × drones needed (z) | 1.00 | [0.60, 1.69] | .99 |
| E2a3 · speed (tactical) × big plan → Suggest consulted | 1.73 | [0.62, 4.85] | .29 |
| E2a4 · × log plan size | 1.20 | [0.65, 2.19] | .56 |
| E2a5 / E2a6 · any-tier speed, strategic / tactical | 1.28 / 2.21 | | .60 / .13 |

- Game fixed effects change nothing.
- E2a3 reverses on the v1.12+ cohort (0.59). E2a4 reverses there too (0.62).
- On the round-1 codes: 1.58 and 1.42 (X2).
- Median person-level size effects lean the predicted way: cards +.27 vs +.13; Suggest +.18 vs +.11.
- 22 of 33 cite speed for the tactical tier, so there are few comparison people.

### E2b · Visible errors: more manual allocation on single-type missions

- E2b1 is reported above.
- E2b2, the interaction (single- vs three-type): OR 1.93, p = .12.
- E2b3, manual allocation on all missions: OR 1.74, p = .15.
- Same direction across samples, except S-s1 for E2b2 (1.07) and S-6 (0.83).
- The game-FE version of E2b2 flips direction in session 1 (s1 gate 0).

### E2c · Can't check: do these people keep tactical plans unmodified more?

Direction as predicted, nowhere near significant.

| Variant | OR | p |
|---|---|---|
| E2c1 · all plans | 1.56 | .39 |
| E2c2 · consulted plans only (LOO flips sign; 0.85 on v1.12+) | 1.59 | .65 |
| E2c4 · size-adjusted | 1.61 | .39 |

- E2c3 duplicates E2c1: everyone coded "can't check" said it about the tactical tier.
- Round-1 codes: OR 1.92, p = .22.
- Keeping is near ceiling (median .80 vs .84), which leaves little room for an effect.

### E3 · Stated scale rule against each person's own composition effect

| Variant | Estimate | p |
|---|---|---|
| E3a · "more when complex" × three-type → card | OR 1.27 | .61 |
| E3b · tier-matched rule (strategic/both/unspecified) | OR 0.50 (wrong direction) | .19 |
| E3c · "more when complex" × big plan → Suggest | OR 1.10 | .84 |
| E3d · tier-matched tactical rule | OR 1.03 | .95 |
| E3e · size-only rules (load-framed excluded) | OR 0.74 | .56 |
| E3f · person level, strategic: rule (+1/0/−1) vs own card composition effect | ρ .12 | .52 |
| E3g · person level, tactical: rule vs own Suggest size effect | **ρ .37 [.01, .69]** | **.034** (no LOO flip) |

- **Strategic tier.** What people say about scale does not track their card behaviour. Round 1 found
  the same.
- **Tactical tier.** The person-level correlation replicates round 1's MWU result (p = .022). It
  disappears in the plan-level GEE (E3c), which weights each person by the number of plans they
  made. So the agreement rests on a few people's big-minus-small differences, not on plan-level
  behaviour. Treat it as fragile.

## 3 · Analysis log (in order)

1. Read the briefing, the round-2 plan and its amendment, the round-1 summary, the round-1 H6
   codebook, and the supervisor log's H6 entries. Read the round-1 H6 report with all participant
   IDs masked (`sed 's/P[0-9]{2}/Pxx/'`).
2. Wrote `wE_codebook.md`. It covers:
   - the ruling (§2), recorded as a mechanical `stance` field next to the ranking-first `pref`;
   - decision rules for situational rules (C1–C7), leading-question assents (L1–L5) and mixed
     statements (P1–P8);
   - the fixed κ plan (§8).
3. Coded all 33 participants from `h6_extract_text.py` output, in ID order. Two rules were added
   mid-coding and logged in the codebook:
   - C1a, at P25;
   - P9, at P29/P34.

   Earlier codes were re-checked against both. Saved `wE_codes.csv`.
4. Opened the round-1 codes and the original stances (via `h6_stated_preference.existing/reduce`).
   Computed E1a–E1k.
5. **Extras, stated before running:**
   - **X1 · κ on the reason codes** (`r_speed`, `r_visible_err`, `r_cantcheck`). E2 rests on these
     codes, so their reliability matters as much as `pref`'s.
   - **X2 · E2/E3 headline links re-run on the round-1 coder's codes.** Shows whether a link depends
     on which coder's reasons are used.
   - **X3 · Fleiss κ across all three codings.** A single summary of three-way reliability.
6. E2a–E2c and E3a–E3g. Each was run on S-all, S-v112, S-s1, S-27 and S-6, plus a game-fixed-effect
   version; tier variants on S-all only. The S-all fits carry the s1, order and LOO gates.
7. Changed one thing after a first run: models with a coefficient > 8 on the log scale are marked
   not estimable. This was S-6 complete separation in E2c2, which had produced OR ≈ 3×10⁹. No other
   estimate changed.

## 4 · Traps and confounds

- **Debriefs are post-session, single-occasion talk** (round-1 trap 8). All codes are person-level
  and never aligned to decisions. Some debriefs are talk during the session-2 questionnaire (P03,
  P19, P21, P27), which reflects session 2 most.
- **Written interview notes are researcher paraphrase** (7 participants with notes only). Codebook
  rule P7 caps those codes at medium confidence.
- **Leading questions.** 6 codes rest on an assent and are flagged `led`. Dropping them and the
  low-confidence codes leaves κ against round 1 at 1.00 and the sign test at p = .021.
- **Order and game are confounded.** Every E2/E3 model has a game-fixed-effect version, and an
  order-split gate. None of the reason or rule predictors are about order, and game FE moves no
  OR by more than about 0.2. So no result here is an order or game effect.
- **Between-person design.** Every E2/E3 predictor is a trait of the person (what they said). So
  even the interaction tests cannot show that the reason causes the behaviour.
- **Ceiling.** Tactical consulting and keeping are near ceiling, which limits E2a3/4, E2c and E3c/d.
- **Residual missions** are excluded. The composition contrast is three-type vs single-type; the 12
  two-type decisions are dropped from the interaction models.
- **Performance metrics** are not used: no test here has a performance outcome. So the P01/P02
  half-weight issue does not arise.
- **P09** is excluded everywhere.
- **Operators, not assistants.** That the Conservative card pads unused colours is context. The
  finding is about operators' reaction to it (E2b).

## 5 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wE_main.py      # writes wE_specs.csv (~1.5 min)
C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wE_kappa.py     # E1 detail: confusion matrices, disagreements
C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wE_behaviour.py # E2/E3 detail and descriptives
```
