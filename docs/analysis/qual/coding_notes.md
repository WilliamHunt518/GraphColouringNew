# Qualitative coding · notes, decision rules and counts

Coded 2026-10-07 against `CODEBOOK.md` (codes unchanged). One coder, every transcript read in full;
keyword search was used only as a final completeness check. Outputs: `codes_matrix.csv`
(33 rows) and `evidence.csv` (255 rows). `scripts/qual/coding_helper.py` checks that every
excerpt occurs verbatim in that participant's source (timestamps stripped, whitespace and curly
quotes normalised) and is ≤ 40 words, then builds both CSVs; " […] " marks an omission inside an
excerpt. Locations are video timestamps (debrief) or 0-based non-empty paragraph numbers
(interview), matching `scripts/analysis_round1/h6_extract_text.py`.

## How the material was read

- **Debriefs** are automatic transcripts with no speaker labels; researcher and participant turns
  run together, sometimes inside one timestamped line. Only text judged to be the participant's was
  coded. Where a researcher statement is answered with a bare "yes", the excerpt includes the
  researcher's words so the lead is visible, and `led = 1`.
- **Interview `.docx` files are the researcher's written notes**, not transcripts. Text in quotation
  marks is treated as the participant's words; unquoted notes are treated as the researcher's
  summary of what the participant said and coded (`led = 0`) unless the note itself shows a lead.
  Bracketed researcher annotations (e.g. P10 para2 "[Noticed how conservative worked – wasted
  redundancy]") were not coded on their own.
- `led` follows the codebook literally: a bare yes to a leading question → present with `led = 1`;
  if the participant elaborates in their own words, `led = 0`. A code is "led-only" when every piece
  of its evidence for that person is `led = 1`: C04 (P33, P35), C05 (P24), C09 (P24), C17 (P26,
  P29), C25 (P26). They are counted as present; subtract them for a conservative count.

## Decision rules (all dated 2026-10-07, applied to all 33)

1. **C01 personal_strategy** needs the approach to be framed as the person's strategy, approach,
   routine, habit or deliberate policy ("my strategy was", "the trade-off that I make", "the way
   I've set up most of them", "put me in a position of overall reviewer"), or to be given as the
   answer to a researcher question explicitly about their strategy/approach (including when the
   researcher names "this strategy/approach" and the participant elaborates). A conditional rule
   offered in answer to some other question (e.g. "did task complexity matter?"), or a bare
   tendency ("more inclined to", "tended to"), is coded under its specific code (C03, C11 …) but not
   C01. Checking everything is C18, not C01, unless it is a routine of how the recommendation is
   used (e.g. "worked it out first and saw if it agreed"). Consequences: P02, P12, P14, P34, P35
   = 0 for C01.
2. **C03 small_myself_big_assistant** is coded when either half is explicitly tied to job size or
   complexity (simple / single-colour → self, or large / complicated / many-drone → assistant), as
   long as nothing contradicts the other half. Reverse statements (P03: trusts it for simple tasks;
   P20: would offload less for very complex work) are 0.
3. **C05 parallel_work** includes "keeping several missions moving at once" without an explicit
   link to the assistant (P21 "able to multitask better"). A wish to work while Suggest fills in
   (P27) is a design ask, not behaviour → 0.
4. **C14 cant_check_tactical** needs a reference to the tactical plan / Suggest / tactical assistant
   and a reason of complexity or time. Non-tier-specific "no time to evaluate each action" goes to
   C17 instead (P25, P35).
5. **C17 check_depends_on_cost** covers any statement that checking happened when there was time or
   it was cheap and was skipped under time pressure, including only one side of that contrast when
   the dependency on time is explicit (P25, P33).
6. **C18 always_checks** is coded when the person says they always / every time checked the
   recommendations of at least one assistant tier (P04 strategic only). "Normally I will have a
   check", contradicted by "if I have enough time … I will have a check" (P33), is 0.
7. **C20 blames_assistant_for_failure** needs the failure to be linked to the assistant or its
   recommendation (P18: missions failed "after having it set to conservative"; P03: "blame the
   strategic for not having redundancy"). Confidence dropping after a failure, with no attribution
   (P07 para11, P03 para1), is 0.
8. **C24 manual_did_better** needs an explicit claim that their own manual work produced better
   results than the assistant's. Conditional or hypothetical claims (P35 "if I have enough time, I
   can do better than AI assistant"; P17 "if I make a manual decision, I can make it better"),
   hedged ones (P22 "I could find maybe some more optimal policies"; P12 "possibly could have been
   quicker … not certain") and criticism of the cards alone (P16) are 0. Result: 0 of 33.
9. **C25 human_final_say** includes "humans at the higher level" / "needs a human element" framing
   (P05, P30) and "AI systems with humans … don't rely on it" (P35). Describing the current set-up as
   human-in-the-loop without saying it should be so (P36), or an accountability concern (P31, who
   also says the human need not be "making the decisions"), is 0.
10. **C27 wants_failure_data** includes wanting analytics on the system's or the operator's
    performance (P12 "strengths and weaknesses", P31 "I have no feedback on that", P32 "analytics on
    … drone utilization and mission success"), not only failure probabilities. Requests for
    operational display data (P27: remaining time, drones about to be released) are 0.
11. **C28 wants_more_automation** needs a wish that this task / these tools be more automated or the
    operator's load reduced (P13, P31; P27 auto-ordering and abort prompts; P30 automatic
    reallocation after failures). General endorsement of AI in search and rescue (P34 para6, P24) is 0.

## Other ambiguous calls

- **P01** C21: "I sent the same mission out like three times and had the exact same failure" read
  as re-sending after failure (coded). C12 not coded: the "three blue … weird number" exchange is
  researcher-led and the participant frames it as a possible bug, not over-allocation. C19 not
  coded: "can't tell if I was just not paying attention" is hedged.
- **P02** C12 from "spares weren't always correct" (spares = the cards' extra drones). "Jumped in if
  could work out before" not coded C06 (racing the reveal, not a complaint).
- **P03** C10/C18 from "Checked always. Worked it out first and saw if it agreed." "As time went on he
  picked it less" (para8) is declining reliance, not C15.
- **P04** C26 not coded: wants deterministic algorithms for reliability, not explanation (contrast
  P02, who says "understandable").
- **P06** C26 not coded: "maybe less transparent" is hedged and immediately qualified.
- **P07** C08 from wanting "a third button for manual allocation" (more options).
- **P10** C10 from "a little bit of experimenting"; C12 not coded — he concluded the cards' redundancy
  was sensible.
- **P13** C26 not coded ("I'm not so sure how it works" is a statement, not a request); C25 not coded
  ("automate that which is not ethically constrained" implies but does not state human final say).
- **P15** C22 coded alongside C15 because he gives learning as the reason he could now spot mistakes.
- **P16** C08 and C12 both from "too extreme (far too aggressive and far too conservative)"; C14 not
  coded — para6 is garbled.
- **P17** C15 from "in the beginning … I didn't [check], but then I slowly got into a habit" plus
  "more misallocations" in the second scenario.
- **P19** C07 not coded: he says he *should* have assigned more conservatively (counterfactual).
- **P20** C26 not coded: "some way of verifying that the AI system…" breaks off. "After that point, I
  started trusting the strategic assistant" is almost certainly a mistranscribed "stopped"; not C16.
- **P21** C23 not coded: "I've done better this time … not sure if it's completely dependent on the
  assistance" is hedged.
- **P22** C09 not coded: "assessing and then overriding" is not clearly editing a card.
- **P24** C11 not coded: "we cannot multitask … we should use AI to help us" is a general view.
- **P26** C16 from both "with more successful … I will trust it more" and "second one, I'm more
  confident" (with the tactical agent).
- **P27** C08 not coded: the "hybrid mode" request is about the tactical planner.
- **P36** (consulted expert) C26 from wanting trust in "how they've come up with those answers" and a
  red-team agent to audit outputs; C01 from his glance-and-go style.

## Thin material

- **P01**: only a short, researcher-dominated exchange mostly about a suspected bug; one code (C21).
- **P14**: interview notes of 5 paragraphs and a short debrief; one code (C18).
- **P07**, **P12**, **P34**: interview notes only (7–12 short paragraphs); 2–3 codes each.

## Counts (X of 33)

| Code | n | | Code | n |
|---|---|---|---|---|
| C01 personal_strategy | 15 | | C15 noticed_more_later | 4 |
| C02 wants_control | 1 | | C16 trust_grew | 4 |
| C03 small_myself_big_assistant | 10 | | C17 check_depends_on_cost | 9 (2 led-only) |
| C04 assistant_faster | 15 (2 led-only) | | C18 always_checks | 5 |
| C05 parallel_work | 8 (1 led-only) | | C19 blames_self_for_failure | 4 |
| C06 assistant_slow | 6 | | C20 blames_assistant_for_failure | 3 |
| C07 reserve_keeping | 6 | | C21 abort_rather_than_fix | 4 |
| C08 middle_ground | 6 | | C22 learning_effect | 6 |
| C09 card_as_draft | 4 (1 led-only) | | C23 assistant_improved_outcome | 3 |
| C10 testing_the_assistant | 5 | | C24 manual_did_better | 0 |
| C11 hand_over_when_overloaded | 9 | | C25 human_final_say | 9 (1 led-only) |
| C12 strategic_overallocation | 12 | | C26 wants_explanation | 5 |
| C13 tactical_flaw | 3 | | C27 wants_failure_data | 6 |
| C14 cant_check_tactical | 3 | | C28 wants_more_automation | 4 |
