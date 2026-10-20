# Paper draft v2

`main.tex` is the paper. Introduction and Related Work are the old draft's (`../ScopeOfAutonomy(1).zip`), unchanged
except for the design paragraph and the research-question note at the end of the Introduction, which now match the
study as it was run. Everything from Section 3 on is new.

| File | What it is |
|---|---|
| `main.tex` | The paper. Methods (Sections 3–6) written by hand from the code, the logs and `docs/STUDY_BUILD.md`. |
| `results.tex` | **Generated**: one subsection per finding, from the analysis register. `\input` by main.tex. |
| `supplement.tex` | **Generated**: the register's sidelined analyses, in Appendix D. |
| `tables/` | **Generated**: descriptive tables by scenario and by game (`scripts/paper/descriptives.py`). |
| `figs/interface/` | Screenshots of the platform (from `presentation/01_interface`). |
| `figs/results/` | **Generated**: every result chart, rendered from the review page (`findings_review.html`). |
| `refs.bib` | The old draft's bibliography, unchanged. |

In the PDF, **grey text** is the analysis register's own wording (`\regtext`). It is accurate but written for the
review page, so rewrite it. **Red text** marks notes for the authors (`\todo`). To typeset the grey text as normal, set
`\definecolor{regtext}{gray}{0}` in the preamble.

## Rebuilding after the findings change

From the repo root, with the review page served (`scripts\register\review.bat`, port 8766):

```
python scripts/paper/build_paper.py jobs PaperDrafting/v2/figs/results/jobs.json
node scripts/paper/capture_figs.mjs PaperDrafting/v2/figs/results/jobs.json PaperDrafting/v2/figs/results
C:/Users/Work/anaconda3/python.exe scripts/paper/descriptives.py PaperDrafting/v2/tables
python scripts/paper/build_paper.py tex PaperDrafting/v2
cd PaperDrafting/v2 && latexmk -pdf main.tex
```

`capture_figs.mjs` needs `playwright-core` resolvable from where it runs (it is not a repo dependency) and a local
Chrome. Run it from a folder with `npm i playwright-core`, or copy it there. Set `SKIP_EXISTING=1` to keep figures that
are already rendered.

Which views of each chart become panels is set in `scripts/paper/figviews.json`. Literal rewrites of register text for
the paper (for wording that only makes sense on the review page) go in `scripts/paper/paper_text.json`.
