# Pass 4 brief — acting on the pass-3 notes

Shared instructions for each analyst working between pass 3 and pass 4. Read all of it, then `BRIEF_PASS3.md` and
`BRIEF.md` in this folder (tooling, chart globals, standards, the update-file format — all still apply).

## Where we are

The researcher reviewed pass 3. Their notes are frozen in `docs/analysis/register/passes/pass3.json`
(`cards["<finding-id>#<section-id>"]`, plus `role` = their paper-role pick). Their verdicts: the personal-style,
size, workload, flaw and tier-trust findings are **Core**; we are close to a near-final set with a narrative.

Structure is already done in `findings.yaml` (do not undo it): their role picks are written in as `role` +
`role_set: true`; sections they picked **Archive** are now `tier: side`; every old `reply` was cleared, so
`reply` now only answers the pass-3 note. Claude already wrote replies for notes that needed no analysis — do not
overwrite a `reply` that is already there unless your work changes its answer.

Write your changes to `docs/analysis/register/pass2/<name>.pass4.yaml` (same format as pass 3; merged with
`scripts/register/apply_updates.py pass4`). Keep each section's `role`/`tier` unless the note asks otherwise.

## The general request: every axis must say what it is

The researcher: "some graphs have unclear axes (e.g. 0–100% but not saying what it's of)". For **every chart your
area's `*.charts.js` draws for a main-tier section** (and sidelined ones if cheap), make sure:
- each axis has a title naming the quantity **and its unit or base**: "% of decisions where Suggest was pressed",
  "seconds from plan opened to deploy", "odds ratio (log scale)", not "%" or "rate";
- legends name what each colour/series is; toggles say what they switch;
- the y-axis label fits (no clipping) and the chart title/caption, if any, matches.
Check visually: the page can be screenshotted headless with
`"C:/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --screenshot=<png> --window-size=1400,4000 "file:///G:/Files/Code/GraphColouringNew/Results/findings_review.html#<finding-id>"`
after `python scripts/register/build_review.py` (plain `python` has PyYAML). View the PNG with your Read tool
(crop with the anaconda python + PIL if large). Note: rebuilding is fine — other analysts rebuild too; it only
reads files. Do not run `apply_updates.py` (the integrator does), so your yaml text changes won't show until then;
check chart rendering only.

## Standards

Same as pass 3: honest above all; bars for categories, lines only for a real continuous x; CIs on every estimate;
tooltips with n; toggles redraw in place, default to the paper view, and the text says what the toggles do;
P09 excluded; analyse by game where load matters; no participant speech in JSON; `node --check` your charts file.
Answer questions in `reply`, first word yes/no where it fits.

## When done

Reply with: each note acted on (key → one line), any answer that changes the story, anything the researcher
must decide, the axis fixes made (chart key → what changed), and the files written. Under 500 words.
