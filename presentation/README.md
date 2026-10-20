# Presentation material

Images of the study platform and every chart produced so far, for slides and write-ups.
Generated 2026-10-18 from build `study-v1.13` and the analysis pages as they stood that day.
Nothing here is source data; it can all be regenerated (see `_capture_scripts/`).

## 01_interface — the study platform (1920×1080, as on the study monitors)

Captured from a scripted demo run (`?pid=DEMO&complexity=tactical&seed=42`). The researcher-only
test controls and "TEST" badges were hidden before each shot, so the screens look like what a participant saw.

| Folder | What's in it |
|---|---|
| `01_setup_and_onboarding` | Researcher start screen; pre-study background + AI-attitude questionnaire (top, full-length, and scrolled parts) |
| `02_strategic_window` | Primary (strategic) window: empty, mission queue, after allocation, missions in progress, map detail levels; `crop_` = reserve strip, mission queue, strategic map on their own |
| `03_strategic_assistant` | Strategic Assistant panel: cards loading → loaded, Aggressive/Conservative selected, editing a card's allocation, going manual before the cards load; `crop_` = the panel alone |
| `04_tactical_planner` | Map (tactical) window: idle, mission pending, empty planner, Tactical Assistant suggesting → plan ready, manual drag-and-drop plans, missions in progress; `crop_` = schedule panel / tactical map alone |
| `05_failure_recovery` | Drone-failure alert on both windows, the recovery planner, recovery with the assistant's Suggest |
| `06_surveys_and_session_flow` | Post-session surveys (NASA-TLX, trust in each assistant; top and scrolled), the between-session break, and the end screen |
| `07_tutorial` | All 48 guided-tutorial steps, named `stepNN_<title>_<window>`. From step 15 on, both windows are included for each step |
| `08_dual_monitor_side_by_side` | Strategic and tactical windows stitched side by side, the way the two-monitor setup looks |

The in-session trust probe (`TrustProbeModal`) is not captured because the app never renders it.

## 02_charts — every chart, one PNG each (2× resolution)

`light/` and `dark/` hold the same charts in the pages' light and dark themes. Pick whichever suits the slide background.
Each chart is cropped with its title and caption card; the filenames come from those titles.

| Folder | Source page |
|---|---|
| `01_findings_review_current_pass` | `Results/findings_review.html`, the current (pass 5) distilled findings. One subfolder per finding, in page order |
| `02_findings_combined` | `Results/findings_combined.html` |
| `03_findings_synthesis` | `Results/findings_synthesis.html` |
| `04_findings_brief` | `Results/findings_brief.html` |
| `05_analysis_round1` / `06_analysis_round2` | `Results/analysis_round1.html` / `analysis_round2.html` |
| `07_report_two_tiers_two_scenarios` | `docs/reports/two-tiers-two-scenarios.html` |
| `08_report_two_tiers_legacy` | `docs/reports/two-tiers-two-scenarios-legacy.html` (older version of the same report) |

If the findings move on, the review page is the one to use. The older pages hold earlier versions of some of the same findings.

## 03_full_pages

A full-length screenshot of every analysis page in the light theme, for context or a quick visual index.
`01_findings_review_current_pass/` has one image per finding.

## 04_study_recordings

`stills/` and `clips/` are copied from `Results/img/` and `Results/review_media/`. They are crops of
participants' screen recordings (screen only: no faces, no audio). They show real sessions, so check
they suit the audience before showing them outside the group.

## 05_assets

The drone, task-type and mission-category icons used in the UI (`icons/` as SVG, `icons_png/` at 512 px),
plus the map background `map-bg.jpg`.

## Caveats

- `findings_synthesis.html` and `findings_brief.html` embed participant quotes and are marked "do not
  circulate". The chart crops here hold no quotes, but some full-page captures in `03_full_pages` do.
  Don't hand those out.
- The interface shots come from a demo seed, not a participant's game, so the scores, missions and
  timings on screen are illustrative.

## Regenerating

`_capture_scripts/` holds the Playwright scripts that made all of this. They need `npm i playwright-core`
somewhere, system Chrome, `npm run dev` on port 5199 (`npx vite --port 5199`), and for the review page a
static server on `Results/` (`python -m http.server 8799`). Run `charts.mjs`, `ui.mjs`, `flow.mjs`,
`tut.mjs`, then `comp.mjs` (which stitches the side-by-side images and the icon PNGs).
