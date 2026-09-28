# Results — all participant data

Everything collected from a real person lives here, so the whole folder can be moved to another
machine for processing in one go. Every file is keyed by anonymous ID (P01…, PIL01…). The name↔ID
key is `docs/Participants.xlsx`. It is deliberately **not** in this folder, so a copy of `Results/`
on its own does not identify anyone by name. Recordings and interviews still contain voices and
faces, though, so handle the folder as identifiable data.

| Folder | Contents | In git? |
|---|---|---|
| `Participants/` | One study export per participant (`P01.json` …), read by `scripts/study_analysis.py` and friends | yes |
| `Pilots/` | Real human pilot runs (`PIL01`–`PIL03`) — not study participants | yes |
| `Recordings/` | Screen + mic recordings (`P05.mp4` …) | **no** (gitignored) |
| `Interviews/` | Post-study interview transcripts | **no** (gitignored) |
| `Narration/` | `scripts/narration_pipeline.py` output (audio, transcripts, clips, `decision-cards.html`) | **no** (gitignored) |
| `Supplements/` | Filled-in supplementary questionnaires | **no** (gitignored) |

Dev/test fixtures that are not people (`logs/Pilots/auto`, `M`, `W`, `W2`, `newPilot.json`,
`logs/debug`, `logs/manualAddOnline`) stay in `logs/`.

## Hand corrections to exported data

A hand-edited response carries a `manualCorrection` object on its `survey_response` event with
the date, the original values, and the reason. See `docs/EVENT_LOGGING.md`.

- **P18**, session 1, `nasa_tlx`: the participant skipped the questionnaire and left every slider
  at 10. The researcher administered it manually and those answers were entered (2026-09-28).
- **P36**, session 1, `trust_strategic`: the participant could not go back and asked for
  `strat_follow` to be recorded as 3, not the 1 they submitted (2026-09-28).
