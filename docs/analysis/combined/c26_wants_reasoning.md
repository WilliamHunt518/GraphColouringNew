# C26 "wants the assistant's reasoning": who are they, and why did they score higher?

Script: `scripts/analysis_combined/c26_wants_reasoning.py` (read-only; prints every number below).
Written 2026-10-08.

## The question

Qualitative code **C26** (`wants_explanation`, codebook: "wants the assistant's reasoning,
transparency or auditability") turned up in the combined page's screening table with a striking
score gap: mean session score about 1495 for the coded group against about 1111 for everyone else
(Mann–Whitney p ≈ .010). That table runs 28 codes plus the stated-preference groups against 4
outcomes, uncorrected, so one hit near .01 is roughly what chance alone would produce. This note
asks who the group is, whether the gap survives the known design confounds, and whether they
behave differently in a way that could explain it.

**Terms.** *Score* = the session's net score (completion points minus penalty). *Game* = one of the
four fixed mission streams (scenario × plan index); score depends heavily on the game, so the fair
comparison is *within-game z*: each session's score standardised against everyone else who played
the same game, then averaged per person. *Benchmark share* = score divided by what a near-perfect
automated operator scores on the same game (`docs/reports/smart_benchmark.json`). *Coverage* = the
fraction of a session's original (non-residual) missions the operator allocated at all.

## Who they are

Five participants are coded C26, not four: **P02, P12, P16, P25, P36**. The screening test used
four because P02 (like P01) played on half task weights, so P02's raw score is left out of every
score comparison (`person_summary` in `build_findings_synthesis.py`). Scores exist for 31 people
(33 logged, P09 excluded, P01/P02 out), so the comparison is **4 vs 27**, not 4 vs 31.

| PID | Source of the code | Field / background | Scenario order | Games | Version |
|---|---|---|---|---|---|
| P02 | interview notes | Computing | Strategic first | S1, T2 | v1.2 (half weights) |
| P12 | interview notes | Computing | Strategic first | S1, T2 | v1.12 |
| P16 | interview notes | Computing | Strategic first | S1, T2 | v1.12 |
| P25 | debrief transcript | Computing | Tactical first | T1, S2 | v1.12 |
| P36 | debrief transcript | Defence | Strategic first | S2, T1 (swapped) | v1.13 |

Four of the five have a computing background and one a defence background (field only; ages and roles
omitted so no member is identifiable). Nobody in the group ran with agent failures live.

## What they said

All five were coded from the general "AI in the real world" part of the interview, not from
anything about the task itself. In no case did the remark follow a direct researcher prompt about
explanation (`led = 0` throughout).

- **P02** (notes): "AI tools are fine if they're understandable (deterministic not stochastic)."
- **P12** (notes): "I would want an understanding of how it goes about developing its optimum
  paths", alongside wanting "a better sense of what the system's strengths and weaknesses are".
- **P16** (notes): "I would use them even more if I knew how they worked"; the strategic cards
  should be "more self explanatory/transparent", because "I have an idea of the strategy that
  didn't quite match how the AI was doing it". P16 overrode the cards most of the time.
- **P25** (debrief 0:25:19–0:26:29): working fast, "I just click the buttons … if … I can get a
  summary of the process would be very good"; "Can we just audit them or … have more explainable
  … AI systems? This is very important for us." Also says the second session moved too fast "to
  evaluate each action".
- **P36** (debrief 0:36:43, 0:39:55): trust in a plan depends on "trust in how they've come up with
  those answers"; the risk is AI presenting "the wrong answer with a level of confidence"; wants
  "an agent whose only job is to go and red team all of your outputs". This is mostly about
  military staff process, not this interface.

So the shared idea is real but thin: a general wish to understand or audit AI, voiced as a
condition for *future, real-world* use. Only P16 tied it to something the cards actually did.

## Is the score gap a design artefact?

**No design confound found.** Checked one by one (n = 4 vs 27 unless stated):

- **Game.** Two members (P12, P16) played the easy game T2 (game mean 1576 vs 960–1089 for the
  others), which inflates raw score. But within-game z removes this and the gap *widens*:
  mean z **+0.93 vs −0.14**. Every member is above their game's mean in every session (z from
  +0.19 to +1.71).
- **Benchmark share.** 0.93 vs 0.69. Same picture.
- **Scenario order.** 4 of 5 coded played Strategic first, against 13 of 28 others; but within-game
  z barely differs by order across the whole sample (+0.07 vs −0.08).
- **Swapped games (P31–P36).** Only P36. Swapped participants do average a little higher (+0.37 vs
  −0.09, n = 6 vs 25), but leaving out any single member leaves the gap at +0.84 to +0.99 vs about
  −0.10.
- **Version.** Three are v1.12, one v1.13. Restricting to v1.12+ (n = 24) changes nothing (+0.93
  vs −0.07).
- **Half weights.** P02 is out of the score test, correctly. But note what P02 does to the story:
  on score efficiency (unaffected by the weights) P02 is at the very bottom of all 33 (0.07, 3rd percentile), with 59%
  task completion. **With all five coded people, the pattern is four near the top and one near
  the bottom.**

Where they rank by within-game z (1 = best of 31): **P12 1st, P16 2nd, P36 5th, P25 6th.** The
chance that four people picked at random all land in the top 6 is about 1 in 2,100, and the rank
test on z gives p = .0008. That looks decisive, but it is not independent evidence: C26 was picked
*because* it was the most extreme of ~124 screened groups, and re-testing the same group on a
cleaner version of the same outcome mostly confirms that it was extreme, not why.

## Do they behave differently?

Thirty permutation tests were run in total (group label shuffled, 20,000 shuffles, two-sided,
uncorrected): 3 on score, 21 on behaviour/self-report, 1 on the reliance axis, 5 on dispositions.
**Only the 3 score tests came out below .05** (raw p = .042, z p = .018, share p = .033). Behaviour
below includes P02 (n = 5 vs 28).

**Reliance: no difference.** Card uptake 67% vs 64% (p = .84); Suggest consulted 72% vs 76%
(p = .77); Suggest plan kept unmodified 88% vs 95%; position on the study's reliance axis +0.20 vs
−0.04 (p = .75). Members span the whole range: P12 and P25 are among the heaviest relyers, P16 and
P02 among the lightest. Reliance is not the route to their score.

**Scrutiny: no sign of it.** If wanting reasoning meant checking more, we would expect more card
previews, more toggling between cards, more card edits, or longer looks at plans. None of that
appears: previews per decision 0.73 vs 0.76 (p = .85), toggles 0.03 vs 0.04, card edits 1% vs 7%,
tactical confirm time no different. The pre-study item "I want to see the reasoning before I rely
on an AI" (verif_want_reasoning, 1–7) does not separate them either: 5.2 vs 5.5 (p = .69), and it
does not track score (ρ = .08). What they said in the interview is not visible in how they played.

**Speed, workload, throughput: this is where they differ (all trends, none significant alone).**

| Measure | C26 (n=5) | Rest (n=28) | p |
|---|---|---|---|
| Time spent on a strategic decision beyond the forced card delay (median s) | 4.3 | 9.2 | .087 |
| Recovery episodes where Suggest was tried | 76% | 43% | .088 |
| NASA-TLX workload (0–20) | 6.3 | 9.1 | .052 |
| Missions allocated per mission arrived | 1.04 | 0.92 | .18 |

The clearest account of the score is **coverage**: the four score-eligible members allocated 99%
of their original missions (three of four allocated every single one) against 86% for the rest,
where only 11% of people allocated everything. Coverage alone correlates ρ = .81 with within-game
z across all 31, and adding missions-allocated-per-arrived to a regression takes the C26
coefficient from +1.06 to +0.44 (R² .18 → .74). Their advantage is earned on both sides of the
ledger: completion points z +0.93 and penalty z −0.73 versus about zero for the rest. In short,
they decided fast, reported low effort, got to every mission, and tried Suggest when a drone
failed. That is a description of skilled operators, not of explanation-seekers.

But coverage does not single them out either. The top 12 by z also includes P31, P30, P28, P34,
P15, P27 with similar coverage (0.88–1.00). C26 picks four of the six best operators; it does not
pick out a distinctive way of playing.

## Is C26 under-coded? (And what the near-misses show)

Several people not coded C26 said related things, mostly in interview notes:

- **P05** (notes): "Automate the levels you can understand, otherwise you are at the mercy of it
  when it fails" (and the tactical tier "was easier to check").
- **P03** (notes): AI should do it "if you understand the best way to do it, the failure modes".
- **P04** (notes): wants deterministic algorithms (coded out: reliability, not explanation).
- **P06** (notes): the strategic assistant was "maybe less transparent", then "it became clear how
  it was working" (coded out as hedged).
- **P13** (debrief 0:23:00): "I'm not so sure how it works, so I can't exactly comment on that."
- **P20** (debrief 0:32:24): "some way of verifying that the AI system…" (breaks off).
- P28 was asked about explainability by the researcher (debrief 0:35:32) and answered about
  something else; correctly not coded.

The exclusions follow the codebook ("a statement, not a request"; hedged; reliability not
explanation) and are documented in `docs/analysis/qual/coding_notes.md`. P05 is the most arguable
miss. The decisive point is what these six scored: mean within-game z **−0.97** (P03 −2.05,
P20 −2.16, P13 −0.97, P04 −0.91, P06 −0.10, P05 +0.41). Fold them into the group and the score
difference disappears entirely (p = .88). So the *theme* of wanting to understand the assistant
does not go with high scores; only the exact four who cleared the coding line do. A real
attitude–performance link should not be that sensitive to where a borderline line is drawn.

## Verdict

- **Confounded?** Not by game, scenario order, swap, version or half weights. Within-game
  normalisation makes the gap bigger, not smaller.
- **Real behavioural difference?** Yes, but it is the ordinary profile of a strong operator (fast
  strategic decisions, low workload, allocates every mission, attempts recovery with Suggest),
  shared with several uncoded top scorers. Nothing links it to wanting explanations: no extra
  scrutiny, no difference in reliance, no difference on the pre-study "want reasoning" item.
- **Why the overlap, then?** Most likely chance under a 124-test screen, helped by who reaches
  the general "AI in the real world" question with something articulate to say: four of five
  members have a computing background and one a defence background, and the code was
  assigned from that part of the interview. The fifth coded person (P02) is near the bottom on
  efficiency, and the six people who said similar things just below the line score below average.

**Confidence:** high that it is not a design artefact; moderate-to-high that C26 itself has no
causal or diagnostic link to performance (chance selection of four strong operators). Treat the
screening hit as a curiosity; do not report "people who want explanations perform better".
