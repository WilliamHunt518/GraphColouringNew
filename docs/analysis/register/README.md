# Findings register — the review loop

Everything the analysis found, one card per claim, reviewed by the researcher in passes until what
remains is the curated set of findings and the links between them — the web the paper is written from.

## Status (read this first)

- **2026-10-08** — register built (79 cards from rounds 1–2, the qualitative coding and the combined-page
  follow-ups) and the review page tested.
- **2026-10-09** — **pass 1 in progress on this machine** (18/79 cards answered so far; notes in
  `responses.json`). Fixed: the server 404'd `/api/responses` before the first save, so the page never
  connected and kept notes browser-only; it now pushes browser-held notes to disk on connect. Needs PyYAML
  (`python -m pip install --user pyyaml`).
- **2026-10-12** — **pass 1 closed** (79/79 answered; frozen in `passes/pass1.json`). Between passes the 79 cards
  were collected into **13 findings** in `findings.yaml`: bigger pages, each with several sections that have their own
  chart, a plain "how this was worked out" and the cards they stand for. Cards may appear in more than one finding,
  marked "shared". 9 pruned cards are `status: retired`. Each pass-1 note is answered in its finding's `replies`.
  The work was split by area: for each area `scripts/register/pass2/<area>.py` writes `pass2/<area>.json`,
  `<area>.charts.js` draws it, and `pass2/<area>.findings.yaml` was the draft that `scripts/register/assemble_findings.py`
  combined (`pass2/BRIEF.md` was the analysts' brief). The area scripts need pandas + statsmodels; on this machine
  that is `C:/Users/Work/anaconda3/python.exe`. **Pass 2 is open**: the page now reviews findings (one verdict per
  finding, plus an optional note per section).
- **2026-10-13** — **pass 2 closed** (notes on all 13 findings and nearly every section; frozen in `passes/pass2.json`).
  The researcher's direction: distil. Between passes: sections they called "not a focus" got `tier: side` (a collapsed
  *Sidelined* panel at the bottom of each finding); `f-flaw-visibility` and `f-recovery` were merged into `f-flaw-odd`;
  `f-operator-wants` became the *For the discussion* finding; `f-who-does-better`, `f-triage`, `f-methods` are
  sidelined whole; `f-personal-style` was reordered into the researcher's narrative. New on the page: a per-section
  **paper role** (Paper / Numbers only / Extra / Archive — Claude's suggestion shown dashed until picked, stored as
  `role` in responses), and each section shows the previous pass's note with Claude's `reply`. Analysis changes were
  done per area to `pass2/<area>.pass3.yaml` (brief: `pass2/BRIEF_PASS3.md`) and merged by
  `scripts/register/apply_updates.py pass3`. **Pass 3 is open.**
- **2026-10-14** — **pass 3 closed** (98 notes, frozen in `passes/pass3.json`). Five findings are Core (personal
  style, size decides, workload, flaw, tier trust). Between passes: the researcher's role picks are written into
  `findings.yaml` as `role` + `role_set: true` (shown solid on the page); sections picked *Archive* moved to the
  sidelined panel; `f-who-does-better` is `status: retired` (a *Retired* group at the foot of the list); old replies
  were cleared so `reply` only answers the previous pass. Analysis per area went to `pass2/<name>.pass4.yaml`
  (brief: `pass2/BRIEF_PASS4.md`, which adds a general axis-label audit) and was merged by
  `scripts/register/apply_updates.py pass4`. **Pass 4 is open.**
- **2026-10-14** — **pass 4 closed** (frozen in `passes/pass4.json`): mostly approved; notes on two graphs
  (size#parallel reframed as "close, small edge to Suggest in execution"; flaw#by-index end points dug into,
  `pass2/flaw.pass5.yaml`). `f-tier-trust` is now Keep; `f-who-does-better` marked Keep, so un-retired to sidelined.
  From now on **each finding's verdict carries over**: the new `responses.json` is seeded with last pass's finding
  verdicts (`updated: null`), so the researcher only changes what moved. **Pass 5 is open.**
- **2026-10-14** — **quote pass (during pass 5)**: at the researcher's request every main section now shows *what people
  said*: a summary, 3–4 quote cards and "more quotes", from three quote analysts (`qual/BRIEF_QUAL.md`; their files
  `qual/qa|qb|qc.yaml` hold 306 verbatim-checked quotes from debriefs, interviews and the in-play think-aloud, ids
  namespaced `qa:q-…`; `ev<N>` = row N of `docs/analysis/qual/evidence.csv`). `scripts/register/apply_quotes.py`
  writes each section's `qual: {summary, featured, more}`; `build_review.py` embeds the quotes. `f-operator-wants`
  became the discussion finding with ten themed mini sections. The quote files hold participant speech, like
  evidence.csv: never circulate. **Highlighting is now the researcher's**: every quote starts under "More quotes"
  (the analysts' featured ones tagged "Claude's pick"); clicking Highlight stores the id in `responses.json` as
  `cards["<finding>#<section>"].quotes` (ordered), and a filter bar narrows the list.
- **2026-10-15 — mid pass 5**: the researcher highlights quotes themselves (above). Each section again shows every
  earlier pass's note with what Claude did (`passes/replies.yaml` keeps the replies of closed passes; `reply` in
  `findings.yaml` answers the last pass). Notes made *this* pass that Claude has already acted on are answered in a
  `done` field (shown as "Your note this pass" / "What Claude did"), merged from `pass2/notes5.pass5b.yaml`: the
  waiting-time graph (`f-workload#waited`, `load.waits`), the parallel-work quotes moved to `f-size-decides#parallel-said`,
  P21's continuity quote, and flaw sections 4 and 5 retitled as different events.
- **Next step for Claude:** when the researcher says pass 5 is done, archive `responses.json` to `passes/pass5.json`,
  bump `pass:` in `cards.yaml`, seed the next `responses.json` with the finding verdicts, carry new role picks into
  `findings.yaml` (`role` + `role_set`), carry highlighted quotes over (seed each section's `quotes` in the new
  `responses.json`, so they stay highlighted), copy every `reply` into `passes/replies.yaml` under the
  pass it answered (4), turn each `done` into that section's `reply`, and act on the notes. Sections with `role: paper`
  are the figure list.
- **(pass 1, historical)** when the researcher said pass 1 was done, `responses.json` will be in this folder
  (committed from the other machine, or handed over as an exported `review_pass1_*.json` — if so, save it
  here as `responses.json`). Then follow *Between passes* below. Do not edit cards before reading the
  responses, and never delete or rename a card id.
- The plan, agreed with the researcher: one full pass over every card, then repeated passes over what
  survives (Core / Keep / unsure), ending with a curated register plus the link map — the skeleton for
  writing the paper. The researcher's notes ("maybe people did X; might match Y") drive what gets
  checked, reframed, merged or dropped; Claude does the analysis between passes, the researcher decides.

Update this status block at the end of every pass.

| File | What it is |
|---|---|
| `cards.yaml` | The register: every card, its numbers, chart, suggested links and Claude's reading. Source of truth; edited by Claude between passes. `pass:` at the top is the current pass. |
| `findings.yaml` | From pass 2: the review units. Each finding is a page of sections (chart key, text, `how`, numbers, `atoms`, `sharedWith`, quote `codes`), plus `replies` to the previous pass's notes and `open` questions. |
| `pass2/` | Each area's analysis output (`<area>.json`, embedded as `DATA.pass2.<area>`), the area drafts, and the brief. Charts are in `scripts/register/pass2/<area>.charts.js`. |
| `responses.json` | The researcher's notes for the **current** pass (verdict, note, links, tags per card). Written by the review server as you type. |
| `responses.bak.json` | The previous save, kept by the server so one bad write can be undone. |
| `passes/passN.json` | Notes from finished passes, frozen. Shown on each card as history. |

The page is `Results/findings_review.html`, built by `scripts/register/build_review.py`. It embeds
the combined page's payload, so every chart shows the same numbers as `Results/findings_combined.html`.
It holds verbatim participant speech — do not circulate.

## Reviewing (researcher)

Double-click `scripts/register/review.bat`. It rebuilds the page, opens it in the browser and saves
every note to `responses.json` as you type. Keep its window open while you review.

On each card: pick a verdict, write what it makes you think, add links to other cards (adopt a
suggested one with **+ mine**, or search), add tags. The link map shows the web as it grows. The page
also works opened straight from disk — it then keeps notes in the browser, and **Export notes** hands
them over as a file.

| Verdict | Meaning |
|---|---|
| Core | A finding the paper is built on |
| Keep | Worth keeping, supporting role |
| Reframe | Real, but the claim should be stated differently (say how in the note) |
| Merge | Duplicates or belongs inside another card (link it) |
| Prune | Drop it |
| Needs a check | Something to test before deciding (say what in the note) |

## Between passes (Claude)

1. Read `responses.json`. For each note: run the checks asked for, reword reframed cards, fold merged
   cards into their target (`status: merged:<id>`), retire pruned ones (`status: retired` — cards are
   never deleted, so links and history stay valid), add new cards for new ideas, and turn agreed links
   into card links.
2. Add a `replies:` entry to each card acted on — `{pass: N, text: what was done and what it showed}` —
   which the page shows above the response box in the next pass.
3. Close the pass: move `responses.json` to `passes/passN.json`, set `pass: N+1` in `cards.yaml`, rebuild.
   The build refuses a `responses.json` whose pass does not match `cards.yaml`, so a stale file can
   never be mixed into the next pass.
