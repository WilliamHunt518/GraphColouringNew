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
- **2026-10-16 — pass 5, second batch of notes**: acted on in `pass2/notes5.pass5c.yaml` (P30's continuity quote, an
  'Overall average' marker on the tactical-tier chart, `f-size-decides#route-people` = is the card→Suggest link a few
  people?, and `f-practice#speed` by minute / pair / third). New: **On screen** — short muted clips from the recordings
  that show what the findings' terms look like (a card then Suggest, hand then hand, the illogical card, editing a card,
  parallel work, a refusal, the queue). The list is `demos.yaml`; `scripts/register/build_demos.py` cuts them into
  `Results/review_media/` (gitignored, like the recordings; `review.bat` runs it). Each clip shows under the sections it
  explains and in the page's *On screen* tab. The review server now answers byte-range requests, so clips can seek.
- **2026-10-16 — pass 5, third batch**: **notes Claude has acted on are now cleared** (the researcher's rule: an
  enacted note must not trigger the work again next time). `scripts/register/clear_acted.py <keys>` (or `--done`) moves
  each such note to `acted.json` and empties its box in `responses.json`; the page shows it as "Your note this pass" with
  the `done` reply; `review_server.py` drops any acted note a stale open tab pushes back. **Always run it right after
  merging a `done`.** Also new: the **Start here** card (`f-about`, `kind: intro`: no verdict, not counted in progress)
  explaining the study, the two screens, tasks, the two decisions, what goes wrong, the procedure and the findings'
  vocabulary; clips now come in three views (both screens / strategic / tactical, full height) with per-moment
  'left screen' / 'right screen' jumps; `f-practice#speed` can order session 1 then session 2.
- **2026-10-20 — every note, every time**: the researcher expects **every typed request** in the open pass to be acted
  on and cleared, not only the ones raised in chat (a q-hierarchy note asking to lead into P36's view was missed).
  **Before ending any turn that acts on the pass, run `scripts/register/open_notes.py`** and either act on each note
  (reply with `done`, then `clear_acted.py`) or tell the researcher which are left as judgements and why. Also from
  today: **P36 is quoted only in `q-practitioner`**, which comes after all other quote findings
  (`apply_quotes.OWN_FINDING`; `apply_quotes.py` and `add_qual_findings.py` fail on a P36 quote anywhere else). Counts
  that list P36 among others ("8 of 33 … P36") stay; their commentary and quotes were taken out of every other finding.
- **2026-10-20 — P36 one point per passage**: `q-practitioner` is rebuilt from the 19 passages the researcher ticked
  and highlighted (sections `pt-*`, one passage each; the two "whole board" passages share one), each re-read in
  the researcher's trim; every `refs` link on those passages quotes only words the trim keeps (42 links). The first
  section is a typicality chart (`scripts/register/pass2/typical.py` → `pass2/typical.json`, chart
  `typical.p36`): ordinary play, unusual background. Unpicked passages sit in a sidelined `not-picked` section;
  `refs: all` now gathers only featured quotes of main sections. Highlights, trims and ticks were copied to the new
  section keys. **New: a comment box under every highlighted quote**, stored as `cards[key].qnotes[<quote id>]`;
  `open_notes.py` lists them as `<key>@<quote id>` and `clear_acted.py <key>@<quote id>` clears one (carry
  `qnotes` over with `quotes`/`trims`/`checked` at pass close).
- **2026-10-20 — paper draft v3** (`PaperDrafting/v3`, `ScopeOfAutonomy_v3.zip`): built by `scripts/paper/build_paper.py`
  from the register as of the end of pass 5. One page per point (point → figure → numbers → method → quotes →
  `\clearpage`), with the researcher's pass-5 role and notes in blue; the qualitative findings (`qual.tex`) and P36's
  reading (`practitioner.tex`) are new sections. Graph views in `scripts/paper/figviews.json` follow the researcher's
  notes on each graph; where the notes left the choice open, both views are given. See `PaperDrafting/v3/README.md`.
- **2026-10-20 — paper draft v4** (`PaperDrafting/v4`, `ScopeOfAutonomy_v4.zip`): prose in the style of the
  researcher's edit of the first finding (`scripts/paper/prose.yaml`, built by `scripts/paper/build_prose.py`), with
  per-finding options blocks holding whatever the prose leaves out. The researcher's rules for the paper: no lists of
  participant IDs (one or two quotes instead), and one set of terms, graphs included (`scripts/paper/terms.json`):
  a strategy card is *chosen*, a tactical suggestion is *requested*, an allocation is *built by hand*.
- **2026-10-19 — pass 5, fourth batch** (`pass2/notes5.pass5d.yaml`, notes cleared to `acted.json`): `f-personal-style#who-vs-what`
  gets an *In plain terms* view (AUC of telling taken from not-taken, person from their other decisions, session 2 from
  session 1; shuffled-label check on the 24%: `style.py --wvw` patches only that block); `f-manual-cards#position` gets a
  *Balanced* view (standardised for drones, types, card gap, game, session, minute: `handover.py` P5c); `f-size-decides#route-people`
  gets quotes from the atypical people (`qual/qa.yaml`, new `qa-P20-06`) and a check that drone types and tasks do not absorb
  the card → Suggest link (P5d). `handover.py --p5` recomputes only the pass-5 block; earlier p5 numbers verified unchanged.
- **2026-10-20 — pass 5, qualitative passages**: long verbatim passages from the 14 richest participants
  (`passages/<PID>.yaml`, phrases only; `scripts/register/build_passages.py` cuts the text into `passages/built.json`,
  served to the page as quotes `ps:<id>`), and eight new findings in their own area, *In their own words*
  (`passages/themes.yaml`, inserted by `scripts/register/add_qual_findings.py`). Quote cards can now be **trimmed** on the
  page: `responses.json` `cards["<finding>#<section>"].trims[<quote id>]` holds the trimmed text (cuts marked […]), checked
  live against the original and flagged if not verbatim; the paper builder uses it. Carry `trims` over with `quotes`
  when the pass closes. A trim is classed word by word against the original: *trimmed* (only cuts), *adjusted* (cuts
  plus [bracketed] words) or *edited* (unbracketed words not in the original); "Original — compare" marks the
  differences. **▶ Listen** plays the recording of a quote: `scripts/register/build_audio.py` (run by `review.bat`)
  finds each quote in the word-timed transcript and cuts `Results/review_media/audio/` (gitignored, voices — never
  commit). P36's finding (`q-practitioner`) now has 29 passages and per-section `refs` back to the results
  (agrees / qualifies / beyond), gathered in a closing section meant as a possible end to the paper. The links now
  live on each passage (`refs` in `passages/<PID>.yaml`, shown on the quote card). Each quote card also has a
  "Checked against the recording" box: `cards[key].checked[<quote id>]` holds the exact text that was checked, so a
  later edit shows it as stale. Carry `checked` over with `quotes` and `trims` at pass close. q-new-jobs has a
  queue-ordering section (P27, P32; `scripts/register/pass2/queue_order.py` -> `load.json` `queueOrder`).
- **Next step for Claude:** when the researcher says pass 5 is done, archive `responses.json` to `passes/pass5.json`,
  bump `pass:` in `cards.yaml`, fold `acted.json` into `passes/pass5.json` (each key's archived note back as its pass-5 note) and delete it, seed the next `responses.json` with the finding verdicts, carry new role picks into
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
| `demos.yaml` | The on-screen clips: participant, session times, what to look for, and the sections each explains. Cut by `scripts/register/build_demos.py` into `Results/review_media/` (not committed). |
| `acted.json` | Notes from the open pass that Claude has acted on and cleared (`clear_acted.py`); folded into `passes/passN.json` when the pass closes. |
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
