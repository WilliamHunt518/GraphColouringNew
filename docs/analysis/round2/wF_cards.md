# Round 2 · Workstream F · How operators handle the strategic cards

Scripts: `scripts/analysis_round2/wF_cards.py` (all tests) and `wF_common.py` (loader). Spec table:
`docs/analysis/round2/wF_specs.csv` (72 rows). P09 is excluded, leaving 33 people and 606 strategic
decisions. The loader reproduces `build_findings_synthesis.load_decisions()` row for row and asserts
this on every run.

How the 606 decisions split by route:

| Route | Decisions |
|---|---|
| Took a card | 397 |
| Manual, committed before the cards loaded ("pre-empted") | 97 |
| Manual, built from scratch after the cards loaded | 75 |
| Manual, edited from a card ("Edit this allocation") | 35 |
| Manual with no switch record | 2 (dropped wherever the route matters) |

Every model is a GEE (exchangeable, clustered on participant) with the small-sample correction
(`cov_type='bias_reduced'`) unless the table says otherwise. Gate columns follow the briefing:
- same direction on session 1 only;
- same direction in both scenario orders;
- whether leaving out any one person flips the sign. The range is in `notes`.

## 1 · Candidates

These are the results I think could pass q < .10 and the gates. The supervisor computes q across
the whole round.

**C1 · Pre-empting the cards is mostly a trait of the person.**

- **Stability.** A person's pre-emption rate in session 1 predicts it in session 2: Spearman
  ρ = .56 [.25, .77], p = .0006, n = 33 (F4.3).
  - S-27: ρ = .72, p < .001. S-v112: ρ = .47, p = .021.
  - The rate stays stable after removing what the mission, the game and the load predict:
    ρ = .38 [.03, .65], p = .027 (F4.4).
- **Variance.** About a quarter of the variance belongs to the person, against about 5% to the mission.
  - Person-intercept share = .24 (F4.1). The ANOVA estimator gives .25, with permutation
    p = .0005 (F4.1p).
  - In session 1 only, the person share is .28.
  - Adding the situation as fixed effects removes all of the mission variance but only 2.5% of the
    person variance (F4.2). The situation explains why missions differ, not why people differ.
- **Concentration.** 15 of 33 people never pre-empted, and 5 people made 48% of all pre-emptions.
- **Gates:** both orders positive (ρ .59 / .69; person share .16 / .31). Leave-one-out ρ ranges from
  .51 to .64, and the person share from .18 to .25. No sign change. (S-s1 does not apply to a
  session-1-vs-2 correlation, but the session-1 variance share is .28.)
- **Mechanism:** some operators have a habit of building the allocation themselves the moment a
  mission looks simple, without waiting for the advice. This fits P11/scenario_comparison/2003 and
  P11/agent_comparison/1781 (P11 is a top-five pre-emptor), and P29/manual_override/1469 (the cards'
  wait is worth it only on complicated missions).
- **Caveat:** F4.1's likelihood-ratio p (≈10⁻⁵⁷) comes from a linear-probability model on a 0/1
  outcome and is far too small. Use the permutation p from F4.1p, or the ρ from F4.3.

**C2 · Within the same person, single-type missions are pre-empted more.**

- OR 2.39 [1.28, 4.47], p = .006 (F4.6). The comparison is within person-session, holding size,
  scenario and run.
- The joint GEE gives OR 2.37, p = .018 (F4.5); with game fixed effects, 2.35, p = .014.
- Samples: S-v112 OR 2.79, p = .015; S-s1 OR 2.50, p = .069; S-27 OR 1.87, p = .075.
- **Gates:** session 1 same direction; both orders same direction; leave-one-out OR range 2.05–2.68.
- Not the cause: load. Queue length has OR 1.07 within person (p = .24), and drones needed,
  time left and reserve are all null.
- **Mechanism:** on a mission that needs one drone type there is nothing for the advice to work out,
  so waiting 4–5 s for it costs more than it can return (P11/agent_comparison/1781).
- **Caveat:** this sharpens a pattern the synthesis page already shows descriptively. What is new is
  that it holds within person and with game fixed effects, and that the person trait in C1 sits on
  top of it.

Nothing else is a candidate. The closest misses are F1.1 (anchoring) and F2.2 (edits); see below.

## 2 · Everything else

### F1 · Anchoring: do manual allocations follow the card numbers?

**Design.** Everyone who played a given game saw the same 42 missions, so a mission fixed effect
holds the drones needed and the mix of drone types constant. (In practice this means subtracting
each mission's average.) Within one mission, the card numbers still vary from person to person,
because the cards are sized partly on whatever reserve was left at the time. The Conservative card
on needed colours varies by about 0.7 drones within a mission (SD), and it correlates .75 with the
reserve.

This sets up a **difference-in-differences**: does the link between card size and drones committed
appear only for operators who saw the cards?
- The comparison group is operators who went manual *before* the cards loaded. They faced the same
  reserve but never saw the numbers.
- The reserve is a reverse path: a fuller reserve raises the card *and* lets the operator commit
  more. That path shows up in this comparison group.

**Result.** Taken alone the result is positive, but it fails the session-1 gate.

| Variant | Estimate (drones per card drone) | p |
|---|---|---|
| F1.1 primary DiD (S-all) | +0.76 [0.11, 1.41] | .022 |
| F1.1 S-v112 | +1.29 | .012 |
| F1.1 S-27 | +0.75 | .051 |
| **F1.1 S-s1** | **−0.20 [−1.63, 1.22]** | .78 |
| F1.1 with game fixed effects | +0.74 | .026 |
| F1.2 saw the cards, alone | +0.90 | <.001 |
| F1.3 never saw the cards (the reverse path) | +0.05 | .60 |
| F1.4 + reserve controls | +0.53 | .11 |
| F1.5 Aggressive card as the anchor | +0.45 | .049 |
| F1.6 midpoint of the two cards | +0.75 | .021 |
| F1.7 raw totals, unused-colour padding included | +0.41 | .12 |
| F1.8 per colour | +0.28 | .43 |
| F1.9 reserve could never bind | +1.01 | .026 |
| F1.10 edits counted as "saw the cards" | +0.53 | .16 |
| F1.11 closer to the cards if seen (expected −) | +0.20 | .19 |

- **Reverse path.** It is small: operators who never saw the cards commit about the same however
  full the reserve is (F1.3).
- **Where the effect comes from.** It sits entirely in session 2.
  - Exposed slope: session 1 −0.53 (p = .39); session 2 +0.99 (p < .001).
  - Order: TH-first +1.10; SH-first +0.20.
  - Those operators' session 2 is the Strategic Heavy game S2, so I cannot tell learning, game and
    order apart here.
- **What does not support it.**
  - Per colour (F1.8) and proximity (F1.11) do not back it up.
  - Controlling for reserve directly (F1.4) roughly halves it.
- **Reading.** Suggestive at best. Anchoring, if it is real, appears only after experience, and the
  pre-registered gates reject it.
- **Debriefs:** "somewhere between those two levels" (P17/manual_override/1418, also
  P22/manual_override/1708) describes interpolation. That is a statement about where manual sits
  relative to the cards, which round 1 already shows. It is not evidence for this within-mission
  slope.

### F2 · Sensible edits

Only 35 decisions, by 10 people, are edits of a card, and P24 (13) and P04 (8) dominate them. Every
F2 result is therefore about a handful of people.

- **F2.1 · Unneeded colours.** Only one edited card carried an unneeded colour (P33), and both
  unneeded slots were removed. Not testable.
- **F2.2 · Trimming over-provisioned colours.** A needed colour is cut far more often when the card
  gives more of it than the task badges ask for: OR 3.41 [1.26, 9.22], p = .015 (89 colour-slots, 10
  people).
  - Session-1 same direction; leave-one-out OR range 2.4–4.4.
  - The order gate cannot be computed: Tactical-first people made only 5 edits.
  - In plain terms, edits remove the padding rather than cutting at random.
- **F2.3 · Excess over the minimum that can finish.** Reductions rise with the card's excess over the
  sequential floor, but not significantly: OR 1.23 per drone, p = .28.
- **F2.4 · Net change.** Edits from Aggressive trim −0.76 drones (p = .068). Edits from Conservative
  trim −0.49 (p = .53).
- **F2.5 · Cutting below the minimum.** Allocations below the minimum are rare on every route: 1/34
  edited, 3/74 from scratch, 0/86 pre-empted. No difference (OR 0.96, p = .98).
- **F2.6 · Unused colours in manual builds.** Of 84 manual builds on missions with an unused colour,
  an unused colour was ever added in only 3, and kept at deploy in only 1. Operators building by hand
  essentially never consider the unused types.

### F3 · Discrimination in the moment

Trap 2 applies: an illogical card exists only on single-type missions, so F3.1–F3.8 use single-type
missions after the cards loaded. That is 127 decisions from 32 people: 94 with an illogical card
and only 33 clean.

| Choice share | Aggressive | Conservative | Manual |
|---|---|---|---|
| Clean card | 33% | 48% | 18% |
| Illogical card | 36% | 32% | 32% |

- **Illogical card.** The direction is consistent: less Conservative and more manual. Nothing is
  significant.
  - F3.1 Conservative: OR 0.50 [0.18, 1.42], p = .19.
  - Samples: S-v112 0.29 (p = .07); S-s1 0.52; S-27 0.59; game fixed effects 0.50.
  - Gates: session 1 and both orders same direction; no leave-one-out flip. (S-6 is not estimable.)
  - Other variants: Aggressive (F3.2) OR 1.20; manual (F3.3) 1.78; with reserve held (F3.4) 0.68;
    within person (F3.5) 0.57; Conservative given a card was taken (F3.6) 0.57. All p > .25.
- **Dominated card, single-type.** F3.7 OR 0.36 [0.14, 0.92], p = .033. But the scenario orders
  disagree in sign, and with illogical held fixed it falls to 0.42, p = .12 (F3.8). On single-type
  missions, dominated and illogical largely overlap (109 of 129 illogical cards are also dominated).
- **Dominated card, three-type — the strongest null in this workstream.**
  - Here dominance arises without any odd colour, and operators do not react to it at all: OR 1.10
    [0.47, 2.55], p = .82, n = 349 decisions from 33 people (F3.9).
  - Uptake of Conservative is 42% when it is not dominated and 33% when it is, which the model
    attributes to composition.
  - Samples: S-v112 1.29; S-s1 0.93; S-27 0.77. With reserve held, 1.07. Given a card was taken
    (F3.10), 1.14.
  - The estimate's sign moves around, and leaving out single people flips it.
  - A Conservative card that is slower and no smaller than Aggressive is taken about as often as one
    that is not, so long as nothing on it looks odd.
- **Previewing.** Operators almost never highlight both cards: 19 of 606 decisions. Highlighting a
  card *is* selecting it, and every card choice involves exactly that.
  - F3.11: highlighting both does not rise with a bad card (OR 0.49, p = .43).
  - F3.12: of 209 decisions where the Conservative card was highlighted, the operator moved off it
    in 15.7% of bad-card cases and 9.5% of clean ones. The GEE (OR 0.64, p = .33) and the stratified
    permutation null (F3.12n: the observed +6 pp difference equals the null mean, calibrated p = 1.0)
    agree that composition fully explains it.
  - F3.13 cannot be told apart from noise: OR 2.07 [0.16, 27], from only 19 decisions.
  - **Previewing is not a measurable route to avoiding the bad card in this data.**

### F4 · Pre-emption

See C1 and C2. Also:
- **Load.** Queue length (F4.5 OR 1.03; within person OR 1.07) does not predict pre-emption.
  Operators do not pre-empt *more* under load. This agrees with H9's null and is the opposite of the
  "no time to wait" idea (workstream B3 tests that directly).
- **Other null predictors:** drones needed, time left, reserve and session (run).
- **Among manual choices only (F4.7):** single-type OR 2.03, p = .052.

### Extras

- **X1 · Hesitation.** For single-type card-takers, time beyond the forced reveal does not differ
  between illogical and clean cards (b = 0.01 on log seconds, p = .97). There is no hesitation
  signal.
- **X2 · After an illogical card.** The next decision is pre-empted *less*, not more: OR 0.47
  [0.21, 1.08], p = .077. The within-person permutation null gives p = .07.
  - Gates: session 1, both orders and leave-one-out all keep this (negative) direction.
  - It is the opposite of the expected direction and not significant. Reported, not promoted.
  - A possible reading is that a bad card makes the operator look at the next card instead of
    skipping it. That is post hoc.

## 3 · Analysis log (in the order run)

The variants, their expected directions and the two extras were written into this file **before**
the script first ran. They are reproduced unchanged.

- **F1 · Anchoring.**
  - **Design.** The same 42 missions recur for everyone who played that game, so mission fixed
    effects (within-mission demeaning) hold need and composition fixed. Within a mission, the
    cards' drone counts vary only because the reserve differed.
  - **Groups.** Exposed = manual allocations built from scratch after the cards loaded. Control =
    manual allocations committed before the cards loaded: they never saw the numbers but share the
    reserve → commitment path.
  - **Estimate.** The anchoring estimate is the card × exposed interaction.
  - **Variants:**
    - F1.1 primary: needed colours, Conservative card (+). Run on S-all, S-v112, S-s1, S-27 and
      S-6, and with game FE.
    - F1.2 exposed only (+). F1.3 control only (none: the reverse path).
    - F1.4 + reserve controls (+). F1.5 Aggressive card as anchor (+). F1.6 card midpoint (+).
    - F1.7 raw totals incl. padding (none). F1.8 per colour (+).
    - F1.9 reserve never binding (+). F1.10 edits counted as exposed (+).
    - F1.11 proximity to the cards (−).
- **F2 · Edits.**
  - F2.1 removal of an unneeded colour on an edited card (+; descriptive if too few).
  - F2.2 a needed colour is reduced when the card exceeds the badge need (+).
  - F2.3 reduction rises with the card's excess over the sequential floor (+).
  - F2.4 change in total when editing from Aggressive (−) and from Conservative (none).
  - F2.5 edited allocations fall below the floor less often than scratch or pre-empted ones (−).
  - F2.6 unused colours in manual edit trails (descriptive).
- **F3 · Discrimination.**
  - **Single-type missions, cards loaded:**
    - F3.1 Conservative ~ illogical (−), on all samples and with game FE.
    - F3.2 Aggressive (+). F3.3 manual after reveal (+). F3.4 + reserve (−). F3.5 within person (−).
    - F3.6 Conservative given a card (−). F3.7 dominated (−). F3.8 dominated with illogical held (−).
  - **Three-type missions (dominance without the odd colour):** F3.9 (−) on all samples; F3.9r
    + reserve (−); F3.10 given a card (−).
  - **Previewing:**
    - F3.11 highlighting both cards ~ bad card (+).
    - F3.12 leaving a highlighted Conservative card ~ bad card (+), with a within-person permutation
      null (F3.12n) because it conditions on a within-decision event.
    - F3.13 avoided Conservative ~ highlighted both (+; mechanically biased).
- **F4 · Pre-emption.**
  - F4.1 crossed person × mission variance partition (+ person share), also on S-s1.
  - F4.2 person variance left after situational fixed effects (descriptive).
  - F4.3 session-1 vs session-2 person rate (+). F4.4 the same on situation-adjusted residuals (+).
  - F4.5 joint situational GEE, with game-FE and sample variants: single-type (+), size (−),
    queue (+), time left / reserve / run (none).
  - F4.6 within person-session (Mundlak): single-type (+) and queue (+).
  - F4.7 among manual choices only (+).
- **Extras (reasons pre-stated):**
  - **X1 · Hesitation.** Among single-type card takers, is time spent beyond the forced reveal
    longer when the Conservative card is illogical (+)? Reason: discrimination in the moment may
    show as a pause even when the final choice does not change. It is the only within-decision trace
    besides the choice itself.
  - **X2 · Pre-emption after a bad card.** Is the next decision more often pre-empted after an
    illogical Conservative card (+), within person, holding previous and current composition?
    Reason: menu item 4 asks person vs situation, and a recent bad card is a situational cause that
    is about the operator's reaction (in scope). It is lag-defined, so it gets a within-person
    permutation null (X2n).

**Changes made after the first run** (implementation only; no variant was added or dropped):
- Renamed a module-level variable that shadowed patsy's `C()`. It made the F4 mixed models crash
  before they produced anything.
- Gate refits now drop terms that are constant in the subsample (`run` in session-1 refits). This
  fixed the X2 session-1 gate, which had returned NaN. Every other estimate was unchanged to the
  third decimal.
- Added gates (orders, leave-one-out) to F4.1/F4.3/F4.4, and the permutation version F4.1p. I added
  these because the LR p in F4.1 is anti-conservative, as noted.

## 4 · Traps and confounds, and how each was handled

- **No injected failures (trap 1).** The illogical and dominated cards are side effects of the
  Conservative top-up. Only operators' reactions to them are analysed here.
- **Illogical cards exist only on single-type missions (trap 2).** F3.1–F3.8 are restricted to
  single-type missions. Dominance is tested separately on three-type missions (F3.9), where it is
  not tied to the odd colour.
- **Drone types needed is effectively binary (trap 3).** Entered as single-type yes/no plus drones
  needed.
- **Residual missions (trap 4).** Excluded throughout F1, F3 and F4. They are not the same mission
  as their parent, so they would break the mission fixed effect.
- **Forced reveal wait (trap 5).** Pre-empted manual choices never saw the cards. They are the
  control group in F1, excluded from F3, and the outcome in F4. X1 subtracts the logged reveal
  delay.
- **Manual is not one behaviour (trap 6).** Manual is split into four routes (pre-empted, scratch,
  edited, unflagged) and each is analysed in its own place.
- **Before/after an event (trap 7, round-1 H8).**
  - No before/after windows are used.
  - The two event-conditioned tests each got a within-person stratified permutation null:
    - F3.12 is conditioned on the Conservative card being highlighted (null: F3.12n);
    - X2 is lag-defined (null: X2n).
  - F3.12's raw difference turns out to be pure composition.
- **Reverse path in anchoring.** Reserve raises the card and the feasible commitment together.
  Handled four ways:
  - the comparison group who never saw the cards (F1.3);
  - explicit reserve controls (F1.4);
  - excluding every decision where the picker or a card could be capped by the reserve (F1.9);
  - the mission fixed effect.
- **Order and game are confounded.** Game FE plus order are in F1.1g, F3.1g and F4.5g. S-27 and S-6
  are reported. F1's effect sits in session 2 and the TH-first order (whose session 2 is game S2),
  so I cannot tell learning, game and order apart.
- **Previewing is endogenous.** Highlighting a card is how it is selected. Choosing a card requires
  highlighting it, so F3.13 is flagged as mechanically biased.
- **Performance metrics.** Not applicable: no test in F has a performance outcome.
- **Small numbers.**
  - F2 rests on 10 people, two of whom make 60% of the edits.
  - The clean single-type cell has 33 decisions.
  - Both-cards previews number 19.
  - S-6 single-type models are not estimable (separation).

## 5 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wF_cards.py
```

Runtime is about 1.5 minutes. It writes `docs/analysis/round2/wF_specs.csv` and nothing else; every
number above is printed by the script. Permutations are seeded (20261007, +1, +2).
