# Paper draft v3

Same pipeline and prose as v2 (`../v2/README.md`). What changed is how the results are laid out, and that the
qualitative findings and P36's reading are now in the paper.

- **One page per point.** Every analysis in the results is its own page, in the order *point → figure → key numbers →
  method → what participants said → quotes*, then a page break, so a point can be cut by deleting its page.
- **Your pass-5 verdicts and notes are on the page, in blue.** Each section starts with your role for it ("for the
  paper", "extra: may make it in", "numbers only") and your note, if you left one. Your per-quote comments sit under
  their quote.
- **Every section that is not archived is included,** including those you marked extra or numbers only. Where your
  notes across the passes left the choice of graph open, both views are given as panels (`scripts/paper/figviews.json`
  lists each choice and the note behind it).
- **Quotes are the ones you highlighted, as you trimmed them.** A dagger (†) after a quote means it has not yet been
  ticked as checked against the recording.
- **New sections:**
  - Section 8, *In Their Own Words*, holds the qualitative findings. The two you pruned are left out.
  - Section 9, *A Practitioner's Reading*, is P36's finding. It opens with the typicality chart, then has one page
    per picked passage, each listing its links back to the results as cross-references. The last subsection gathers
    every link, grouped as agrees / qualifies / goes beyond. In the paper, describe P36 only as "a participant with
    operational military experience".
- **Notes in the Discussion and Limitations.** Your pass-5 notes that belong there (the branching failure space as
  future work; "never without a reserve" and training; the real-operations limitations) are added as red notes.

| File | What it is |
|---|---|
| `main.tex` | The paper. Unchanged from v2 apart from the new sections, the drafting macros and the notes above. |
| `results.tex`, `qual.tex`, `practitioner.tex` | **Generated**, from the analysis register. |
| `supplement.tex` | **Generated**: the sidelined analyses, in the appendix. |
| `tables/` | **Generated** descriptive tables (unchanged from v2: the data did not change). |
| `figs/results/` | **Generated**: every chart, rendered from the review page. |
| `figs/interface/` | Platform screenshots (as v2). |

## Rebuilding

From the repo root, with the review page served (`scripts\register\review.bat`, port 8766, or
`python -m http.server 8797` in `Results/`):

```
python scripts/paper/build_paper.py jobs PaperDrafting/v3/figs/results/jobs.json
node scripts/paper/capture_figs.mjs PaperDrafting/v3/figs/results/jobs.json PaperDrafting/v3/figs/results [url]
python scripts/paper/descriptives.py PaperDrafting/v3/tables
python scripts/paper/build_paper.py tex PaperDrafting/v3
cd PaperDrafting/v3 && latexmk -pdf main.tex
```

The rendered figures and the PDF contain no participant audio or video, but the quotes are verbatim participant
speech: share the PDF only as you would the review page.
