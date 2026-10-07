# wE codebook — stated tier preference, third independent coding (round 2, workstream E)

Written **before** any transcript was read for this pass, starting from the round-1 codebook
(`docs/analysis/round1/h6_codebook.md`). The coder (round-2 agent E) has **not** opened
`docs/analysis/round1/h6_codes.csv`, `Results/Narration/*_s1/quotes.json`, or the synthesis page's
`SR.stance`. The round-1 report was read with every participant ID masked, so no per-person code from
either earlier coding is known to this coder. Frozen once coding starts; later changes go under
"Changes after coding began" with the reason.

What changes against round 1: the researcher's ruling on "conditional" is written in (§2), and every
ambiguous case that round 1 left to judgement gets an explicit decision rule (§3–§5). Fields 1, 2, 3
and 4 keep round-1 names and values so that κ is computed like for like.

## 1 · Unit and sources

- **Unit:** one participant (P09 excluded; PIL03 pilot not coded). One row each in `wE_codes.csv`.
- **Sources, read in full:** `Results/Narration/<PID>_s1/debrief.txt` (recorded post-session debrief)
  and `Results/Interviews/<PID>.docx` (written post-study interview notes), extracted with
  `scripts/analysis_round1/h6_extract_text.py`. Both read together when both exist. In-session
  think-aloud narration is not a source.
- Only the **participant's** turns are evidence. Researcher turns are context (see §4 for assents).
- **Refs:** `debrief@[h:mm:ss]` or `interview@paraN` (0-based, non-empty paragraphs), strongest first,
  one to three. No verbatim text in the CSV.

## 2 · The researcher's ruling (2026-10-07), written in

> "I use the assistant more when missions are complex" counts as a **conditional** preference.

Round 1 had two coders who read "conditional" differently: one as a competing *stance* label, one as
a separate *dimension* recorded beside a tier ranking. This codebook records both, deterministically,
so neither reading is lost:

- Field 1 `pref` is **ranking-first** (round-1 rule 1 unchanged): a clear ranking of the two tiers
  wins; `conditional` only when a situational rule is given *instead of* a ranking.
- Field 2 `cond` records any situational rule, whether or not a ranking is also present.
- Field 5 `stance` is the **ruling-applied** single label, computed mechanically, never judged:
  `stance = conditional` if `cond != none`, else `stance = pref`. Under the ruling, anyone who states
  that their use of an assistant depends on mission size / complexity / load is conditional.

## 3 · What counts as a situational rule (Field 2), decision rules

`cond` ∈ {`none`, `more_assist_when_complex`, `more_assist_when_simple`, `other_situational`};
`cond_load` 0/1; `cond_tier` ∈ {`strategic`, `tactical`, `both`, `unspecified`, `na`}.

C1. **A rule needs a generalisation**, in the participant's words or as an assent to one (§4): it
    links using / trusting / relying on an assistant to a property of the situation ("when there
    were lots of drones I just hit suggest", "for the small ones I did it myself"). A single
    anecdote about one mission with no generalisation ("on that last one I took the card") is not
    a rule.
C2. **Scale** = mission size, number of drones, number of tasks, number of drone types, "complex",
    "complicated", "big". → `more_assist_when_complex` / `more_assist_when_simple`.
C3. **Load** = being busy, time pressure, many missions queued, rushing, "when it got hectic". Counts
    as scale for `cond` (`more_assist_when_complex`), with `cond_load = 1`. If the person states both
    a size rule and a load rule, `cond_load = 0` (size is the more specific one) and notes say both.
C4. **Direction**: "I did the simple/single-type ones myself" alone implies the assistant was used on
    the rest → `more_assist_when_complex`. "If there's only one obvious way, I just hit Suggest" →
    `more_assist_when_simple`.
C5. **Other situational** = anything else (reserve level, after a failure, early vs late, "once I
    trusted it", "when the card matched my own count"). Named in notes. Learning over time
    ("I used it more in round 2") is **not** a situational rule; it goes in notes only.
C6. **Both directions stated for different tiers** (e.g. cards on simple ones, Suggest on big ones):
    record the one the participant elaborates more; notes record the other.
C7. `cond_tier`: the tier the rule is about; `unspecified` when they say "the assistant"/"it" and the
    context does not fix the tier; `both` when they say both or name both.

## 4 · Leading questions and assents

L1. An assent (yes / yeah / mm / definitely) to a researcher framing **counts** as the participant's
    statement, and `led = 1` is set if that assent is the key evidence for `pref` or `cond`.
L2. A **bare** assent (no elaboration of the participant's own) is `confidence = low`. An assent
    followed by the participant's own elaboration in the same direction (a reason, an example) is at
    most `medium`, and is `led = 1` only if nothing unprompted supports it.
L3. A qualification after an assent wins ("yeah, but actually for the cards …"): code the
    qualification.
L4. An assent to a description of **behaviour** ("you used the tactical one a lot") is a usage
    statement (rule P4), not a trust statement.
L5. An answer to a neutral comparative question ("which did you trust more?") is **not** led.

## 5 · Field 1 `pref`, decision rules (round-1 rules kept, ambiguities resolved)

Values: `tactical`, `strategic`, `both`, `neither`, `conditional`, `none` (definitions as round 1).

P1. **A clear ranking beats conditionality** (round-1 rule 1). `pref = conditional` only when the
    person gives a situational rule and no ranking.
P2. **One tier only.** Strongly positive on one, silent on the other → `none` unless the context makes
    the comparison explicit (e.g. answering "which did you prefer?"). Negative on one + positive on the
    other, even in separate places → the positive tier.
P3. **Mixed or reversed statements.** (a) An explicit comparative ("trusted X more", "X was more
    useful") beats non-comparative evaluations. (b) Among comparatives, the final / summarising one
    wins; if none, the most elaborated. (c) A positive statement with a reservation ("reliable, with a
    grain of salt") is still positive. (d) Criticism of both, with one explicitly preferred or trusted
    more → that tier, not `neither`. (e) Still balanced → `both` if both positive, `neither` if both
    negative.
P4. **Usage vs trust.** Both count as preference; if they conflict, trust/preference wins and notes
    record the conflict. "Used X more" + positive on X with nothing on trust → X.
P5. **Manual preference** is not a tier preference; it gives `neither` only if it applies to both
    tiers and no ranking is given.
P6. **Tier identification.** Strategic = the cards / "options" / Aggressive-Conservative / "how many
    drones to send" / the allocation pop-up. Tactical = Suggest / the planner / "which drone goes
    where" / the map-side planning; recovery Suggest counts as tactical. If a statement cannot be
    tied to a tier, it does not count for `pref`.
P7. **Written interview notes** (researcher paraphrase) count as the participant's statements, but a
    code resting only on paraphrase is at most `medium` confidence.
P8. **"Both were useful but X more"** → X (comparative beats balanced). "Horses for courses" / "each
    for its own job" with no ranking → `both` if positive about both, else `conditional` only if a
    situational rule is attached.

## 6 · Field 3 reasons (unchanged from round 1)

Each column `S`, `T`, `ST` or empty; reasons the participant gives for trusting / distrusting / using
/ not using an assistant: `r_speed`, `r_accuracy`, `r_cantcheck`, `r_visible_err`, `r_autonomy`,
`r_other` (named in notes). Decision rules added:
- R1. `r_visible_err` needs a **specific** flaw seen (wrong type, too many drones, unneeded colour,
  bad order); a vague "it was sometimes wrong" is `r_accuracy`. A specific flaw can carry both.
- R2. `r_cantcheck` covers "didn't have time to check", "too complex to verify", "just trusted it
  without looking". Saying it was **easy** to check is `r_other` (notes: easy-to-check).
- R3. `r_speed` covers saving time and "quicker than doing it myself"; being rushed so used it is
  speed (and also a load rule under §3).

## 7 · Field 4 bookkeeping

`source` (`debrief`, `interview`, `both`), `led` 0/1, `confidence` (`high`, `medium`, `low`), `refs`,
`notes`. Confidence: high = explicit unprompted comparative; medium = clear but inferred from
evaluations of both, or paraphrase only, or assent + own elaboration; low = bare assent, or the code
rests on a single weak or indirect statement.

## 8 · Agreement analysis (fixed now, before coding)

- **κ1 (primary, like for like):** this `pref` vs round-1 `h6_codes.csv` `pref`.
- **κ2 (ruling-applied):** this `stance` vs round-1 secondary mapping (`cond != none → conditional`).
- **κ3:** this `pref` vs the original quote-level stance codes reduced ranking-first exactly as in
  round 1 (`h6_stated_preference.reduce`, `agent_comparison` quotes).
- **κ4:** this `stance` vs the original codes reduced conditional-first (agent_comparison quotes).
- Also: binary "prefers tactical" κ against both, and κ on `cond != none` (has a rule) against
  round 1. Bootstrap 95% intervals over participants (4000 resamples, seed 42).
- Disagreements tabulated by category (confusion matrix), and listed by participant ID.
- I will not recode after seeing either earlier coding.

## Changes after coding began

Both were added while coding (before either earlier coding was opened), because a case arose that the
rules above did not settle. Every participant already coded was re-checked against them.

- **C1a (added at P25).** A session-level statement linking use to that session's pace or difficulty
  ("in the harder / faster session I used it a lot, because of the pace") counts as a scale/load rule.
  It generalises over the many missions of that session, unlike a single-mission anecdote (C1).
  Applied to P25 and P33; P11 already had a size rule.
- **P9 (added at P29/P34).** When a person is positive about both tiers *and* states a situational
  rule, `pref = both` only if there is an explicit statement valuing both ("both were helpful",
  "agents were helpful" with both named). Otherwise, if the tier talk is structured as a usage rule,
  `pref = conditional` (P1: a rule given instead of a ranking). Applied: P25, P34 → both; P02, P29 →
  conditional.
