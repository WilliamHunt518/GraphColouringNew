# H6 codebook — stated tier preference (second, independent coding pass)

Written **before** reading any debrief or interview in detail, and before looking at the existing
`stance` codes in `Results/Narration/*_s1/quotes.json` or `SR.stance` in the synthesis payload.
Frozen once coding starts; any later change is listed under "Changes after coding began" at the
bottom, with the reason.

## Unit and sources

- **Unit:** one participant (P09 excluded). Each participant gets exactly one row in `h6_codes.csv`.
- **Sources, all read in full:** the post-session debrief `Results/Narration/<PID>_s1/debrief.txt`
  where it exists, and the post-study interview `Results/Interviews/<PID>.docx` where it exists
  (text extracted from `word/document.xml` with stdlib `zipfile`). If both exist, both are read and
  coded together as one body of talk. `PIL03` is a pilot and is not coded. In-session think-aloud
  narration is **not** a source (it is reactive to the moment; H6 is about considered, stated
  preference).
- Only the **participant's** turns count. Researcher prompts are context, never evidence ("so you
  preferred the tactical one?" answered "yeah" counts — the "yeah" is the participant's assent —
  but is flagged `led = 1`).
- **Excerpt reference:** `debrief@[h:mm:ss]` (the line's timestamp in `debrief.txt`) or
  `interview@para<N>` (0-based paragraph index in the docx, non-empty paragraphs only). One to three
  references per participant, the strongest first. No verbatim text in the CSV.

## Field 1 — `pref`: overall tier preference (exactly one value)

The participant's comparative stance about the two assistants — Strategic Assistant (the two
strategy cards / "how many drones") vs Tactical Assistant (the Suggest plan / "which drone does
which task"). Trust, reliance, liking, usefulness and "would use more" all count as preference
when they are stated comparatively or when the person evaluates both assistants and one clearly
comes out better.

| Code | Rule |
|---|---|
| `tactical` | Says, or clearly implies by evaluating both, that the tactical assistant is better / more trusted / relied on more / more useful. Includes "I used the strategic one less" + positive on tactical. |
| `strategic` | Mirror image for the strategic assistant. |
| `both` | Positive about both, with no clear ranking ("both were helpful", "trusted them both"). |
| `neither` | Negative about both / preferred to do it all themselves, with no clear ranking. |
| `conditional` | The person's main stance is that which assistant (or whether to use an assistant) depends on the situation — mission size, complexity, workload, time pressure — **and** they give no clear overall ranking of the tiers. |
| `none` | No usable comparative or evaluative statement about the tiers (topic not raised, or only one tier discussed without a judgement that ranks it against the other). |

Decision rules:
1. **A clear ranking beats conditionality.** If someone ranks the tiers clearly *and* states a
   situational rule, `pref` is the ranked tier and the rule goes in Field 2. `conditional` is only
   for people who give the rule *instead of* a ranking.
2. **Talk about one tier only.** Strongly positive on one tier and silent on the other → `none`
   unless the context makes the comparison explicit. Negative on one tier + positive on the other,
   even in separate places, → the positive tier.
3. **Mixed or reversed within the talk.** Use the participant's final / summarising statement; if
   none, the statement they elaborate most. If still balanced → `both` (if both positive) or
   `neither` (if both negative).
4. **"Used it more" vs "trusted it more".** Both count; if they conflict (used the strategic cards
   more but trusts tactical more), trust/preference wins over usage, and `notes` records it.
5. A preference for doing it **manually** is not a tier preference; it informs `neither` only if it
   applies to both tiers.

## Field 2 — scale conditionality

- `cond` ∈ {`none`, `more_assist_when_complex`, `more_assist_when_simple`, `other_situational`}
  - `more_assist_when_complex`: hands more to an assistant as missions get larger / more complex /
    when overloaded / when many missions are queued ("small ones myself, big ones to the assistant").
  - `more_assist_when_simple`: the reverse (trusts the assistant on easy missions, does big/complex
    ones by hand).
  - `other_situational`: depends on something other than scale/complexity/load (e.g. reserve
    level, whether a failure happened, early vs late in the session) — named in `notes`.
  - Workload / time pressure counts as scale here (more queued missions = bigger problem), but is
    flagged `cond_load = 1` so it can be separated from per-mission size.
- `cond_tier` ∈ {`strategic`, `tactical`, `both`, `unspecified`, `na`}: which assistant the rule is
  about (`na` when `cond = none`).

## Field 3 — stated reasons (multi-label, 0/1 each, with the tier they attach to)

Each reason column takes `S` (said about the strategic assistant), `T` (tactical), `ST` (both), or
empty. Only reasons the participant gives for trusting/distrusting/using/not using an assistant.

| Column | Rule |
|---|---|
| `r_speed` | Saves time / faster than doing it by hand / used it when rushed. |
| `r_accuracy` | Its recommendations were (in)correct, (sub)optimal, made sense / didn't, matched what they would have done. |
| `r_cantcheck` | Could not (or did not have time to) check / verify it, so deferred; or too complex to second-guess. |
| `r_visible_err` | Saw a specific error or flaw (e.g. over-allocation, unneeded drone type, bad ordering). |
| `r_autonomy` | Wants control / prefers own judgement / understanding the situation themselves. |
| `r_other` | Any other reason (named in `notes`). |

## Field 4 — bookkeeping

`source` (`debrief`, `interview`, `both`), `led` (0/1, the key statement was a yes to a leading
question), `confidence` (`high`, `medium`, `low`), `refs`, `notes`.

## Mapping to the existing stance codes (for κ) — fixed in advance

The existing codes (`SR.stance`) use five labels: prefers tactical, conditional, distrusts both,
trusts both, prefers strategic. **Primary mapping** (one-to-one, by name):

| this codebook `pref` | existing stance |
|---|---|
| `tactical` | prefers tactical |
| `strategic` | prefers strategic |
| `both` | trusts both |
| `neither` | distrusts both |
| `conditional` | conditional |
| `none` | (no stance) — kept as its own category in κ if the existing coding also has uncoded people; participants missing from either coding are dropped from κ and counted |

**Secondary mapping** (in case the existing "conditional" means *reliance* is conditional rather
than *tier* preference): any participant with `cond != none` is mapped to `conditional`
regardless of `pref`. Both κ values are reported; the primary one is the one-to-one mapping.

How the existing codes are aggregated to one per participant is decided when they are first
opened, before any comparison is computed, and recorded in the H6 report.

## Primary test (from HYPOTHESES_ROUND1.md, unchanged)

Among participants with `pref ∈ {tactical, strategic}`, the share `tactical`, exact two-sided
binomial (sign) test against 0.5. Support = significant preference for tactical **and** κ ≥ .6.

## Changes after coding began

(none yet)
