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
- **Next step for Claude:** when the researcher says pass 1 is done, `responses.json` will be in this folder
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
