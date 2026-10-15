# Qualitative pass — brief for the quote analysts

The researcher is happy with the quantitative findings but "not massively in touch with" the qualitative side.
They want, in **every main section** of every finding, what people said in open-ended material, shown as 3–4
quote cards (click for more), so they can "look again and see what people basically thought". And the
discussion finding (`f-operator-wants`) should become a set of **mini sections for everything else said** that
is useful but fits no main section. Goal: all useful quotes end up somewhere — in a main section, or a
discussion mini section.

Read first: `CLAUDE.md` (briefly), `docs/analysis/register/README.md`, `docs/analysis/register/findings.yaml`
(the findings; `tier: main` sections are the ones that matter; each has a `codes:` list already in some cases),
`docs/analysis/qual/CODEBOOK.md` and `coding_notes.md`.

## The material (all identifiable — never copy it anywhere except your output yaml)

- `docs/analysis/qual/evidence.csv` — 255 coded excerpts (debrief + interview), verbatim, ≤ 40 words. Refer to
  one by **`ev<N>`**, N = its 0-based row number in the CSV (pandas `read_csv` index). Prefer these when they fit.
- `Results/Narration/<PID>_s<N>/debrief.txt` — full post-session debrief transcripts (auto-transcribed, no
  speaker labels; researcher and participant run together — see coding_notes.md for how to tell them apart).
- `Results/Narration/<PID>_s<N>/quotes.json` — an earlier per-debrief quote pass (theme, stance, note).
- `Results/Narration/<PID>_s<N>/segments.json`, `segments/*.txt|jsonl`, `alignment.json` — the **in-play
  think-aloud** (what they said while playing), aligned to the game clock. `scripts/register/pass2/flaw.py` and
  `load.py` already read in-play remarks — reuse their loaders.
- `Results/Interviews/<PID>.docx` — post-study interview notes (researcher's notes; text in quotation marks is
  the participant's words, unquoted text is the researcher's summary — mark summaries
  `paraphrase: true`).
- P09 is excluded. PIL03 is a pilot, not a participant.

## What you produce — only `docs/analysis/register/qual/<your-name>.yaml`

```yaml
quotes:                 # NEW quotes only (coded excerpts are referenced as ev<N>, not copied)
  - id: q-P05-01        # q-<pid>-<nn>, unique within your file; prefix with your name if you like (qa-, qb-, qc-)
    pid: P05
    source: think-aloud # think-aloud | debrief | interview
    at: "s1 05:32"      # session + video time, or "para 4" for interviews
    led: 0              # 1 if it answers a leading question (include the researcher's words then)
    paraphrase: false   # true for unquoted interview notes (researcher's summary)
    text: "..."         # VERBATIM, ≤ 40 words, " […] " for omissions, names/identifying details → […]
    codes: [C05]        # codebook codes it fits, may be empty
    context: "..."      # optional, your words: what was on screen / what they were doing
sections:
  "<finding-id>#<section-id>":
    summary: "..."      # 1–3 plain sentences: what people said on this point, with counts (X of 33 said…),
                        # including dissent. Honest: if nobody spoke to it, say so in one line and leave lists empty.
    featured: [ev12, q-P05-01, ...]   # 3–4, the clearest; different people; prefer unled, own words
    more: [...]         # the rest worth reading on this point (any number)
    codes: [C03, C05]   # the codes relevant here (the page also offers "all coded excerpts" for these)
```

Verify every new quote is verbatim in its source (normalise whitespace, curly quotes, strip timestamps — see
`scripts/qual/coding_helper.py`) with a small script before you finish; report the check. No quote longer than
40 words. Choose quotes that **show what people thought**, including views that cut against the finding.

## When done

Reply (under 300 words): the sections covered with how many featured/more each, anything surprising in what
people said that the findings miss, and the verification result.
