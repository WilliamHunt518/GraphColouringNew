# Paper draft v4

v3's content, drafted as prose in the style of the researcher's edit of the first finding (2026-10-20).

- **Prose, not register text.**
  - Each finding is a short run of paragraphs. Each figure comes right after the paragraph that introduces it, and its
    caption starts with the statement it supports.
  - One or two quotes are woven in per point, exactly as trimmed on the review page. There are no lists of
    participant IDs.
  - The prose lives in `scripts/paper/prose.yaml`, keyed by register section, so it can be regenerated. Once you start
    editing the `.tex` directly, stop regenerating.
- **Your edit of the first finding is kept.** The changes are only typos ("change" → "chance", "even through" →
  "even though") and the terms below.
- **Options at the end of each finding,** in blue: everything the prose leaves out.
  - the other views of each graph;
  - the highlighted quotes not woven in;
  - the key numbers;
  - the register's text for sections the prose does not use;
  - your pass-5 roles and notes.

  To hide every block at once, change `\includecomment{options}` to `\excludecomment{options}` in the preamble.
- **One set of terms, graphs included** (`scripts/paper/terms.json`, applied to every chart label as it is rendered and
  to all register text):
  - a strategy card is *chosen* (*used the Strategic Assistant*);
  - a tactical suggestion is *requested* (*used the Tactical Assistant*; the button is still called Suggest);
  - an allocation is *built by hand*.

  The definitions in Section 6.4 (Measures) and the descriptive tables use the same words.
- **Page breaks** come between findings, not between points.

Rebuild, from the repo root, with the review page served (port 8766 or 8797):

```
python scripts/paper/build_paper.py jobs PaperDrafting/v4/figs/results/jobs.json
node scripts/paper/capture_figs.mjs PaperDrafting/v4/figs/results/jobs.json PaperDrafting/v4/figs/results [url]
python scripts/paper/descriptives.py PaperDrafting/v4/tables
python scripts/paper/build_paper.py tex PaperDrafting/v4      # supplement.tex (and the v3 layout, overwritten next)
python scripts/paper/build_prose.py PaperDrafting/v4          # results.tex, qual.tex, practitioner.tex
cd PaperDrafting/v4 && latexmk -pdf main.tex
```

The quotes are verbatim participant speech: share the PDF only as you would the review page.
