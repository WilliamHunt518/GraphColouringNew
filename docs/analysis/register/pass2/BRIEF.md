# Pass 2 brief — turning pass-1 notes into findings

Shared instructions for every analyst working between pass 1 and pass 2 of the findings review.
Read this whole file before starting. Your own prompt says which AREA you own and which cards.

## Where we are

The researcher (a PhD student; this is their study) reviewed all 79 atomic cards in
`docs/analysis/register/cards.yaml` on the review page. Their notes are frozen in
`docs/analysis/register/passes/pass1.json` (`cards.<id>` → `{verdict, note, links, tags}`).
Read every note for your cards — they drive everything you do. Read `docs/analysis/register/README.md`
for the review loop and `CLAUDE.md` (repo root) for what the study is.

Their overall guidance, in their words, summarised:
- **Graphs are usually the best way to show things.** Numbers are good too, but not normally alone.
- **A lot of "I don't understand how you've done X".** Every statistic needs a plain-language
  explanation of what was measured, on what rows, compared against what, and what the number means
  ("ρ = .64 means…"). Assume a smart reader who did not write the code.
- **Many findings are atomic parts of a bigger picture.** Pass 2 collects atoms into FEWER, RICHER
  findings — one page each, with several sections, many graphs and details on one page. An atom that
  matters in two places may be repeated; mark it as shared.
- Most qualitative cards ("Said: …") were tagged Keep — attach them as supporting evidence to the
  relevant finding; no new qualitative coding is needed now.
- Verdicts: Core / Keep = carry forward; Reframe = restate as the note says; Merge = fold into the
  linked card's finding; Prune = retire (list it under `retire:` with a one-line reason); Needs a check
  = do the check and report what it showed, plainly, even if it kills the card.

## What you produce (only these files — never edit anything else)

AREA is the short key in your prompt (e.g. `style`).

1. `scripts/register/pass2/<AREA>.py` — the analysis. Read-only over `Results/`. Writes
   `docs/analysis/register/pass2/<AREA>.json` and prints the numbers it quotes. Reuse the existing
   loaders rather than re-parsing logs: `scripts/analysis_combined/extras2.py` (`load()` returns
   S = one row per strategic decision, T = one row per tactical plan, eps = recovery episodes, logs),
   `extras.py`, `scripts/build_findings_synthesis.py` (`load_decisions`), `scripts/study_analysis.py`,
   `scripts/analysis_round1/*`, `scripts/analysis_round2/wB_common.py`. Put the repo's script dirs on
   `sys.path` the way extras2.py does. P09 is excluded everywhere (see extras2 `EXCLUDE`). Use the
   seeded RNG pattern for anything random. Run it from the repo root with `python`; it must finish
   cleanly. Keep JSON compact-ish (round floats to 3–4 dp).
2. `scripts/register/pass2/<AREA>.charts.js` — chart functions, registered into the page's chart map:
   ```js
   (() => {
     const D = DATA.pass2.<AREA>;          // your JSON, embedded by the build
     Object.assign(CH, {
       '<AREA>.someKey': (host) => { ... },  // draw into host (a div)
     });
   })();
   ```
   Available globals (from `scripts/findings_common.js`, read it): `h`, `el`, `svgRoot(host,W,H)`,
   `css('--token')`, `hoverable(node, html)`, `legend`, `tableFor`, `tiles`, `btnBar`, `barsH`,
   `barsGrouped`, `barsStacked`, `barsDiverging`, `forest`, `linesAt`, `slopes`, `eventLines`,
   `diffForest`, `nullStrip`, `pct`, `num`, `sgn`, `pval`; `DATA` is the combined page payload
   (`Results/findings_combined.html`) so existing results are reachable as `DATA.extras2…` etc.
   Write any new chart form you need (scatter, heatmap, binned line with error bars, per-person
   small multiples…) as a private helper INSIDE your IIFE. Rules: SVG with a 700-wide viewBox;
   colours only from CSS tokens (`--s-strat` strategic blue, `--s-tac` tactical orange, `--r-cons`,
   `--r-aggr`, `--r-man`, `--good`, `--warn`, `--bad`, `--mark`, `--mark-soft`, `--ink-2/3`, `--grid`,
   `--line`) so light and dark themes both work; label axes and units; direct labels over legends
   where possible; hover tooltips with n on every mark; show uncertainty (CI bars / bands) whenever
   you quote an estimate. A chart may call `tableFor` to put "Show the numbers" under itself.
   Check syntax with `node --check`. You cannot see the page yet — the integrator renders and
   screenshots every chart afterwards, so make the code defensive (missing data → a short text note,
   never a throw).
3. `docs/analysis/register/pass2/<AREA>.findings.yaml` — the content:
   ```yaml
   findings:
     - id: f-<slug>                 # new, stable
       area: "<area heading>"
       title: "<the claim, short>"
       headline: "<2–4 plain sentences: what we found and how sure we are>"
       confidence: strong | moderate | suggestive | null | mixed
       absorbs: [<atomic card ids this finding carries>]
       sections:
         - id: <short>
           title: "<section heading>"
           text: "<what this part shows, plain; <b>/<i> allowed>"
           how: "<HOW IT WAS WORKED OUT: the rows, the comparison, the model/adjustment in words,
                  what each number means. This is the part the researcher keeps asking for.>"
           chart: <AREA>.<key>      # optional; may also be an existing chart key (see below)
           numbers: ["...", "..."]  # the figures, each with its meaning
           atoms: [<card ids this section stands for>]
           sharedWith: [f-<other finding>]   # only if this section is repeated elsewhere
           codes: [C03, C04]        # qualitative codes whose quotes support it (optional)
       replies:                     # one per pass-1 note you acted on — answer their question directly
         - {card: <id>, text: "<what you did and what it showed>"}
       open: ["<anything the researcher must decide, or that you could not resolve>"]
   retire:
     - {card: <id>, why: "<one line>"}
   ```
   Existing chart keys from the pass-1 page (`scripts/register/review_template.html`, `const CH`)
   may be reused if still the best view; prefer new, clearer ones where the note complained.

Every atomic card in your list must end up either in some finding's `absorbs` or in `retire`.
1–3 findings per area is the target; fewer and richer beats many and thin.

## Standards

- Honest above all. If a check weakens or kills a result, say so in the headline. Small n → say n.
  Distinguish "no evidence of an effect" from "evidence of no effect" in plain words. Don't p-hack:
  if you try several specifications, report them all (a robustness strip is a good graph).
- Analyse by GAME (`planSeedIndex` / the `game` column), not by run, where load matters
  (CLAUDE.md "Four fixed games"; `docs/STUDY_BUILD.md` §20). P01/P02 played on half task weights —
  adjust or note it if it touches your numbers.
- Participants are "they". UI words: "Strategic Assistant" / "Tactical Assistant", "strategy cards",
  "Suggest"; the main map is the **strategic map** (never "operational map").
- Quotes: never put participant speech in your JSON beyond what `DATA.qual`/`DATA.extras` already
  carry (codes are enough; the page pulls excerpts by code).
- Do not commit, do not touch `cards.yaml`, the template, the build scripts, or other areas' files.

## When done

Reply with: the findings you made (id + one-line claim), what each pass-1 "check"/question turned up
(one line each), anything you think the researcher must decide, and the list of files written.
