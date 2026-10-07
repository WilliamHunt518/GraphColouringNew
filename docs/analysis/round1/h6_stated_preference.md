# H6 · Is the tactical assistant trusted more in what people say — and does that depend on mission scale?

Script: `scripts/analysis_round1/h6_stated_preference.py`. Helper: `h6_extract_text.py`, which
prints one participant's debrief and interview text and never opens `quotes.json`.

Coding files:
- `docs/analysis/round1/h6_codebook.md`, written before any transcript was read in detail;
- `docs/analysis/round1/h6_codes.csv`, one row per participant with `pref`, `cond`, `cond_load`,
  `cond_tier`, six reason columns marked S/T/ST, `led`, `confidence`, excerpt `refs` and `notes`.

Sources: all 33 participants have material.
- 26 have a recorded debrief (`debrief.txt`).
- 16 have a written post-study interview (`.docx`). 8 have both.
- 7 (P02, P05, P06, P07, P12, P16, P34) have **only** the written interview notes. These are the
  researcher's paraphrases with some verbatim lines, not transcripts.
- PIL03 (pilot) and P09 are not coded.

## 1 · Primary test

Among participants who state a tier preference, the share preferring tactical against 50%, using
an exact two-sided binomial (sign) test:

| | Value |
|---|---|
| Preference stated | **17 tactical vs 6 strategic** (n = 23 of 33) |
| Share tactical | **.74 [.52, .90]** |
| Exact p | **.035** |

The other 10 participants were coded both 4, conditional 4, none 2.

**Cohen's κ against the existing stance codes, primary mapping: κ = .27** (bootstrap 95% CI
[.07, .49]; raw agreement 13 of 26; n = 26 coded by both).

**Verdict: NOT SUPPORTED.**
- The pre-registered criterion needs *both* a significant tactical preference *and* κ ≥ .6.
- The sign test passes at α = .05 before Holm. κ fails clearly: the upper end of its interval is
  .49.
- The direction is not in doubt, though. Both codings put tactical well ahead:
  - this coding: 17 to 6;
  - the existing coding, reduced the same way: 12 to 1, p = .003.

## 2 · v1.12+ sensitivity (n = 24)

13 tactical vs 3 strategic: share .81 [.54, .96], p = .021. κ is not recomputed separately; the
cohort shares the same coder disagreement.

Other robustness checks of the sign test:

| Check | Tactical vs strategic | p |
|---|---|---|
| Low-confidence codes dropped | 16 vs 3 | .004 |
| Recorded-debrief participants only | 15 vs 3 | .008 |
| Written-notes-only participants | 2 vs 3 | — |
| Statements made in answer to a leading researcher question (`led = 1`, 5 people) dropped | 13 vs 6 | .17 |

- The written-notes-only participants lean the other way. The notes are paraphrases and the group
  is small, so this is noted but not interpreted.
- With the led statements dropped, the result is no longer significant. **The spoken tactical
  preference partly depends on assent to the researcher's framing.** In those debriefs the
  researcher several times opened with "I got the impression you were using the tactical a lot".

## 3 · Agreement with the existing codes

**Aggregation.**
- The existing codes are per *quote* and multi-valued: a person can carry several stances. The
  synthesis page's `SR.stance` counts the set of stances on each person's `agent_comparison`
  quotes.
- I fixed the reduction to one stance per person **after seeing that format, before computing any
  agreement**. It mirrors codebook rule 1 (a ranking beats conditionality):
  1. exactly one tier preference → that tier;
  2. otherwise distrusts_both or prefers_neither → neither;
  3. otherwise trusts_both → both;
  4. otherwise conditional;
  5. otherwise none.
- Mapping: one-to-one by name, with `prefers_neither` folded into neither. P18 and P24 have no
  `agent_comparison` stance and count as none.

| Variant | κ | 95% CI | Raw agreement |
|---|---|---|---|
| **Primary** (agent_comparison quotes, ranking-first) | **.27** | [.07, .49] | .50 |
| All quote themes, ranking-first | .37 | [.15, .59] | .58 |
| Secondary mapping (my `cond ≠ none` → conditional; existing conditional-first) | −.04 | | .35 |
| Same, all themes | .00 | | .54 |

Other agreement measures:
- Binary "prefers tactical or not": κ = .47, agreement .73.
- My code is one of the person's existing stances for 13 of 26.

Where the coders disagree (13 people):
- **Existing `conditional` vs my ranking or both (P11, P17, P25, P31).** The existing coder uses
  `conditional` on most quotes (it is the modal stance for 23 of 26 people across all themes). I
  coded conditionality separately and only used `pref = conditional` when there was no ranking.
- **Existing `distrusts_both` vs my tactical (P03, P21).** Both people criticise both assistants,
  but end up clearly favouring tactical. P21, for example, explicitly lost trust in strategic over
  the wrong drone types and calls tactical "reliable … with a grain of salt".
- **P10.** I coded strategic from the written note "Trusted strategic agent more" plus "I think I
  trusted the strategic … the tactical one in both rounds I had fairly high trust too". The
  existing coding gives tactical and trusts_both.
- **P36.** The researcher asserts that P36 automated tactical, and P36 answers "horses for courses".
  I coded none; the existing coding gives prefers_tactical.
- **P04** (tactical vs trusts_both), **P14** (both vs distrusts_both), **P18** (conditional vs none),
  **P24** (tactical vs none — the existing coder gave P24's tier-relevant quotes a different theme),
  **P28** (none vs conditional).

The low κ is mostly a **construct difference about what "conditional" means**, not random noise.
The existing scheme treats it as a stance competing with tier preference; this codebook treats it
as a separate dimension. The pre-registered κ ≥ .6 cannot be met without reconciling the two
codebooks.

## 4 · Secondary results (exploratory)

**Scale-conditionality.**
- 16 of 33 say they hand *more* to an assistant as missions get bigger or more complex, or under
  load. 8 of the 16 frame it as workload rather than mission size.
- 3 say the reverse (P03 and P04 about strategic; P10 about tactical: "if there is really only one
  logical way … hit suggest").
- 14 state no rule.
- The rule is about the tactical tier for 6, strategic 4, both 3, unspecified 6.

**Does the stated rule match behaviour?**
- *Tactical.* People who say "more assist when complex" show a larger within-person rise in Suggest
  use from small to large plans (above vs below the median of drones × tasks): median +.21 against
  .00. MWU p = .022, rank-biserial .47. Restricting to rules about tactical, both or unspecified
  tiers: p = .039.
- *Strategic.* The same people show **no** difference in the card-taking composition effect
  (three-type minus single-type missions): .19 against .21, p = .61. Overall, card uptake is higher
  on three-type missions for 21 of 33 (median +.21) whether or not people say so.
- So what people say about scale tracks their tactical behaviour, but not their strategic
  behaviour.

**Stated preference vs the questionnaire.**
- Tactical-preferring people have a larger trust gap (T − S): median 1.58 against 0.46. p = .069,
  rank-biserial .52.
- 15 of 17 tactical-preferrers have a positive gap. So do 4 of 6 strategic-preferrers.
- The questionnaire puts 26 of 33 higher for tactical (sign test p = .0005). Talk is less one-sided
  than the scale: 17 to 6 among those who rank, and 10 who do not rank at all.

**Stated preference vs behaviour.**
- Tactical-preferrers take strategy cards somewhat less: .56 against .75. p = .086.
- They consult and keep tactical plans at the same rate: .85 against .82, p = .97.
- Stated tier preference shows up in strategic uptake, if anywhere, not in tactical reliance.
  Tactical reliance is near ceiling for everyone.

**Reasons, coded per tier** (number of people giving the reason about that tier):

| Reason | About strategic | About tactical |
|---|---|---|
| Speed | 11 | 20 |
| Accuracy | 10 | 11 |
| Cannot / did not check | 4 | 9 |
| Visible error | 12 | 1 (P31, task ordering) |
| Autonomy / own judgement | 8 | 4 |

Speed is the commonest reason for relying on the tactical assistant. Visible error is almost
entirely a strategic-tier reason.

**Where the two streams disagree:**
- Four stated strategic-preferrers (P06, P07, P10, P20) still rate tactical higher on the
  questionnaire. Their preference statements are all low or medium confidence, and they rest on
  usefulness or time saving rather than trust.
- One stated tactical-preferrer (P26) rates strategic higher on the questionnaire (gap −1.5).

## 5 · Analysis log (in order)

1. **Codebook written** (`h6_codebook.md`) before reading transcripts, and frozen. No changes were
   made during coding. The judgement calls are recorded in `notes`: P06, P11, P15, P20, P36.
2. **Transcripts read** for all 33 participants via `h6_extract_text.py` (debrief.txt plus the docx
   via stdlib zipfile). Codes saved to `h6_codes.csv`.
3. **Existing codes opened** only after step 2 was saved. Their quote-level, multi-label format
   needed an aggregation rule, which I fixed before computing κ (see §3).
4. **Primary sign test and κ.**
5. **Robustness:** confidence, led statements, source type, v1.12+.
6. **Alternative κ aggregations and mappings**, including the pre-declared secondary mapping. The
   all-themes conditional-first variant is degenerate (existing = conditional for almost everyone),
   giving κ = 0.
7. **Secondary:** scale-conditionality vs behaviour, preference vs questionnaire and behaviour,
   disagreements.

I did not try to recode toward the existing scheme to raise κ; that would defeat the purpose of an
independent second rater.

## 6 · Traps that applied

- **8 (debrief quotes are post-session, single coder, not aligned to decisions).** This pass is the
  second coder; κ = .27 is the calibration the first coding lacked.
  - All codes are person-level, so nothing is aligned to individual decisions.
  - In three participants (P19, P21, P27) the debrief material is talk during the session-2
    questionnaire. It reflects session 2 most.
- **Leading questions** (not in §2, but material). 5 of 33 key statements were assents to a
  researcher framing, almost all of it "you were using the tactical a lot". Dropping them removes
  significance.
- **Written notes are paraphrase** for 7 participants. Reported separately.
- **9 (n = 33):** the person-level secondaries are exploratory and underpowered. MWU group sizes are
  as low as 6.
- **2, 3:** the strategic composition effect uses single- vs three-type missions, with residuals
  excluded.

## 7 · Agreement with H2 and with the current brief

**Brief, Finding 4** ("tactical trusted more").
- Agreed: stated preferences favour tactical, as the questionnaire and behaviour do.
- Differences:
  - Talk is less lopsided than the questionnaire. Many people do not rank the tiers at all.
  - The spoken preference is fragile to leading questions.
  - The brief's `SR.stance` counts should be presented as single-coder and uncalibrated (κ = .27
    against a second coder). Its "conditional 14" category means something different from
    "conditional on scale".
- The brief's two candidate explanations, flaw visibility and checking cost, are both voiced.
  - Visible errors are cited for the strategic tier by 12 people.
  - Inability to check the tactical tier is cited by 9.
  - The commonest reason given for the tactical tier is neither of them: it is **speed** (20).

**H2.**
- The behavioural side shows checking of tactical plans is brief (~3 s after the reveal) and does
  not scale with plan size.
- The 9 who *say* they could not check do check slightly less (p = .055), but they do not keep
  more or trust more.
- Two people (P05, P14) explicitly argue that the tactical plan is easier to check, or that they
  checked it *more*, which cuts against the checking-cost mechanism.
- Both streams agree that the size effect lives in *whether* operators hand over a big plan, not in
  how lightly they check it: the H2 consult OR is 2.5 per SD, and the H6 stated rule matches the
  tactical size effect.

## 7b · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h6_stated_preference.py
# to re-read any participant's material (local only, identifiable):
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h6_extract_text.py P22
```
