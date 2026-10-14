# Pass 3 brief — acting on the pass-2 notes

Shared instructions for each analyst working between pass 2 and pass 3. Read all of it, then `BRIEF.md` in this
folder (the pass-2 brief: tooling, chart globals, standards — all still apply), then `docs/analysis/register/README.md`.

## Where we are

The researcher reviewed the 13 findings of pass 2 on `Results/findings_review.html`. Their notes are frozen in
`docs/analysis/register/passes/pass2.json`: `cards["<finding-id>"]` is the note on a whole finding and
`cards["<finding-id>#<section-id>"]` the note on one section. Read every note for your findings — they drive the work.

Their overall direction: **distil**. Keep everything, but move what they called "not a focus" out of the way, so
each finding reads as a short narrative of the results that matter. That restructure is already done in
`docs/analysis/register/findings.yaml` (read it): each section has `tier: main | side` (side = a collapsed
"Sidelined" panel at the bottom), a suggested `role` (`paper` = in the paper with its graph, `numbers` = values in
the text but no graph, `extra` = keep for a supplement/blog, `archive` = keep but unlikely used), and sometimes
`reply` (the answer the page shows under their pass-2 note) and `was` (where a moved section came from — its
pass-2 note is under that key). `f-flaw-visibility` and `f-recovery` were merged into `f-flaw-odd`;
`f-operator-wants` became a "For the discussion" finding; `f-who-does-better`, `f-triage`, `f-methods` are
sidelined whole. Do not undo any of that; if you think a tier or role is wrong, say so in your report.

Your job is the notes that ask for **more analysis, a new or changed graph, a rewrite, or an answer to a
question**. Sections the notes only sidelined are done — leave them alone.

## Answering questions

Several notes ask "is that right?" / "does this mean…?". Answer each directly in that section's `reply`,
first word yes/no where it fits, then one or two plain sentences. If they misread something, say so kindly
and clearly. If the honest answer needs a check, do the check.

## What you produce

Only these files — never edit `findings.yaml`, `cards.yaml`, the template, build scripts, or another analyst's files:

1. Your area's analysis script(s) `scripts/register/pass2/<area>.py` — extend them; rerun so
   `docs/analysis/register/pass2/<area>.json` holds the new numbers. Keep everything the existing charts need
   (other sections still read the old keys). Run with `C:/Users/Work/anaconda3/python.exe` (pandas, statsmodels).
2. Your area's `scripts/register/pass2/<area>.charts.js` — add or change chart functions. Check with `node --check`.
   - When a note asks for alternative views ("give me every step / every pair / group by three", "all missions vs
     only three-type missions", "version without the low-n cases"), build **one** chart with a small toggle bar
     (`btnBar` from `findings_common.js`, or your own buttons) that redraws in place. Default to the view you
     would put in the paper and say in the text what the toggles do.
   - Bars for categories (not lines — the researcher reads lines as change over time). Lines only for a real
     continuous x (time, size). Error bars / CIs on every estimate; hover tooltip with n on every mark.
   - If you replace a chart, keep the old function under its key unless the section is changing to a new key.
3. `docs/analysis/register/pass2/<area>.pass3.yaml` — the content changes, which the integrator merges into
   `findings.yaml`:
   ```yaml
   findings:
     <finding-id>:
       title: "..."            # optional, replaces
       headline: "..."         # optional, replaces — update it if your results change the story
       reply: "..."            # answer to their note on the WHOLE finding (HTML allowed: <b>, <i>)
       open: ["..."]           # optional, REPLACES the finding's open list (carry over what is still open)
       sections:
         <section-id>:         # any of: title, text, how, numbers, chart, reply, role, tier — each replaces
           chart: <area>.newKey
           reply: "..."        # answer to their note on this section: what you did, what it showed
       new_sections:           # optional
         - {id: ..., title: ..., text: ..., how: ..., chart: ..., numbers: [...], tier: main, role: paper,
            reply: "...", after: <section-id it follows, or null for first>}
   ```
   Every pass-2 note on a section you worked on gets a `reply`. Plain words; the `how` text explains rows,
   comparison, model and what each number means for a reader who did not write the code.

## Standards (in addition to BRIEF.md)

- Honest above all; if the new view weakens a result, say so in the text and the headline.
- Small n: say n, on the chart (tooltips) and in the text.
- Use the existing loaders and the existing area script's helpers rather than re-deriving.
- P09 excluded; analyse by game where load matters.
- No participant speech in your JSON.

## When done

Reply with: each note you acted on (key → one line on what you did/found), any answer that changes the story,
anything the researcher must decide, and the list of files written. Keep it under 500 words.
