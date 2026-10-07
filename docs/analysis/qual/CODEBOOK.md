# Qualitative codebook · mapped to the quantitative findings

Written before coding. Each code is **present (1) or absent (0) per participant**, across all of that
person's material: the post-session debrief (`Results/Narration/<PID>_s1/debrief.txt`) and/or the
post-study interview (`Results/Interviews/<PID>.docx`). All 33 analysed participants have at least one.
P09 is excluded (and has no material); the pilot PIL03 is not a participant. Counts are reported as
"X of 33".

**Coding rules**
- Code what the person **says about themselves or the assistants**, not what the researcher says. A bare
  "yes" to a leading question counts only if they then elaborate in their own words; otherwise record the
  code as present but **led = 1** in the evidence file.
- A code needs at least one clear statement. Hedged or ambiguous mentions are 0, with a note.
- Several codes can apply to one statement.
- Record every piece of evidence (§ output), not only the first.

## Codes

| Code | Theme | Present when the participant… |
|---|---|---|
| C01 `personal_strategy` | Person | describes a consistent personal strategy or style that governed how they used (or did not use) the assistants |
| C02 `wants_control` | Person | wants to do it themselves for control, ownership, pride or satisfaction, or resists being reduced to clicking |
| C03 `small_myself_big_assistant` | Job size | does simple / small / single-type missions or plans themselves and hands complex / large / many-drone ones to the assistant |
| C04 `assistant_faster` | Speed | values the assistant mainly because it is faster or saves time (not because it is better) |
| C05 `parallel_work` | Speed | uses the assistant's time to do something else, or to keep several missions moving at once |
| C06 `assistant_slow` | Speed | complains that the assistant is slow or that waiting for it costs time (card reveal, Suggest filling in) |
| C07 `reserve_keeping` | Manual | holds drones back for missions that have not arrived yet, or allocates fewer to save reserve |
| C08 `middle_ground` | Manual | wanted an allocation between the two cards, more options, or to customise the recommendation |
| C09 `card_as_draft` | Manual | starts from a card and edits it, treating it as a first draft |
| C10 `testing_the_assistant` | Manual | deliberately did some by hand to compare against, test or benchmark the assistant |
| C11 `hand_over_when_overloaded` | Load | uses the assistant more when busy, overwhelmed, rushed or under time pressure |
| C12 `strategic_overallocation` | Tiers | notices the strategic cards over-allocating, sending unneeded drone types, or wasting drones |
| C13 `tactical_flaw` | Tiers | notices a flaw or mistake in a tactical plan (e.g. task order, missing redundancy) |
| C14 `cant_check_tactical` | Tiers | accepts the tactical plan because it is too complex or too fast to check |
| C15 `noticed_more_later` | Trust over time | says they noticed the assistant's errors more, or became more careful, in the later / second session |
| C16 `trust_grew` | Trust over time | says their trust grew with experience or success |
| C17 `check_depends_on_cost` | Verification | describes checking as depending on time or effort — checks when cheap, skips under pressure |
| C18 `always_checks` | Verification | says they checked (nearly) every recommendation |
| C19 `blames_self_for_failure` | Recovery | attributes mission failures to their own choices (e.g. too few drones) |
| C20 `blames_assistant_for_failure` | Recovery | attributes mission failures to the assistant's recommendation |
| C21 `abort_rather_than_fix` | Recovery | describes abandoning or re-sending a mission rather than repairing it after a failure |
| C22 `learning_effect` | Learning | says they got better, faster or more confident with practice |
| C23 `assistant_improved_outcome` | Performance | believes using the assistant improved their results |
| C24 `manual_did_better` | Performance | believes they did better by hand than the assistant would have |
| C25 `human_final_say` | AI attitudes | says a human should keep the final decision / stay in the loop |
| C26 `wants_explanation` | AI attitudes | wants the assistant's reasoning, transparency or auditability |
| C27 `wants_failure_data` | Design asks | wants failure probabilities, performance analytics or outcome data to decide with |
| C28 `wants_more_automation` | Design asks | wants more automation or less work for the operator |

Tier **preference** is not recoded here: it reuses the round-2 coding (`docs/analysis/round2/wE_codes.csv`).

## Output

- `docs/analysis/qual/codes_matrix.csv` — one row per participant: `pid, sources, C01 … C28`.
- `docs/analysis/qual/evidence.csv` — one row per piece of evidence: `pid, code, source (debrief|interview),
  location (timestamp or paragraph), led (0/1), excerpt` — excerpt verbatim, ≤ 40 words, any name or
  identifying detail replaced with `[…]`.
- `docs/analysis/qual/coding_notes.md` — ambiguous calls, rules added during coding (dated), and the
  count per code.
