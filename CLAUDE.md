# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

This is a **research-grade prototype** for a human-subjects study on **trust in autonomous AI agents**, using a **drone radio-channel assignment task**. Participants manage interference between drones by assigning them channels (red/green/blue). The study measures trust calibration and workload across three interaction modes and three difficulty levels.

**The repo name "GraphColouringNew" is a legacy artefact — the actual task is drone channel assignment, not graph colouring.**

## Running the Code

### Full study (researcher entry point)

```bash
python study_runner.py
```

Opens a Tkinter setup window. Configure participant ID, monitors, trials, and surveys, then click Start. Config is auto-saved to `~/.drone_study_config.json` and restored on the next launch.

### Quick single-game launcher (developer / testing)

```bash
python launch_menu.py
```

Runs a single game session with configurable seed, complexity, epsilon, and monitor layout. No surveys.

### Python environment

Requires **pygame** (and optionally `pygame._sdl2` for the detached panel window). Tkinter is used for surveys and setup UIs and is bundled with standard Python.

```bash
pip install pygame
python -m tkinter   # should open a test window
```

## Architecture

### Study Design

Participants see a 2D arena of moving drones. Two drones on the same channel that come within range of each other cause a **clash** — the penalty metric accumulates clash-seconds in real time. The goal is to minimise total clash time over a timed trial.

There are three interaction modes available simultaneously:

| Mode | Label | Description |
|---|---|---|
| M1 | Manual | Click a drone → pick channel from popup |
| M2 | Suggest & Review | Select group → Suggest → review/edit proposal in panel → Apply |
| M3 | Auto-assign | Select group → Auto-assign (apply instantly without review) |

In **flexible agent mode** (`agent_mode="flexible"`), each drone can additionally be "watched":
- **Watch:Suggest** — agent monitors that drone; surfaces a suggestion panel when a clash involves it
- **Watch:Auto** — agent monitors and applies fixes automatically without user involvement
- The autonomous monitor fires every 0.5 s; drones in cooldown (`switch_duration + 0.5 s`) are skipped

### Agent

`agents/channel_agent.py` — `ChannelAdvisor`. Greedy graph-colouring with epsilon-random noise per drone.
- `epsilon=0.0` → perfect agent; `epsilon=0.30` → ~70% optimal (study condition)
- Uses effective channels (`switching_to` if in-flight, else `channel`) to avoid planning against stale state

### Game States

`PAUSED` → `SETUP` (user assigns starting channels) → `PLAYING` (timer runs) → `ENDED`

### Key Files

```
study_runner.py        # Full study orchestrator + Tkinter setup UI (researcher entry point)
launch_menu.py         # Single-game dev launcher

robot_game.py          # Main pygame game loop (~1100 lines)
robot_renderer.py      # All pygame rendering (arena + side panel)
robot_world.py         # Physics: drone movement, channel switching, clash/edge detection
agents/
  channel_agent.py     # ChannelAdvisor — greedy colouring + epsilon noise

tutorial.py            # Guided tutorial (standard 10-step + flexible 16-step variants)
surveys.py             # Tkinter questionnaire windows (demographics, post-trial, summary)
game_logger.py         # JSONL event logger
panel_window.py        # SDL2 detached side-panel window (separate physical monitor)
screen_recorder.py     # mp4 frame capture via pygame

analysis/
  run_analysis.py      # Entry point for post-study analysis
  metrics.py           # Per-trial metric extraction
  data_loader.py       # JSONL → structured data
  plots.py             # Matplotlib visualisations
  stats.py             # Statistical tests

scenario_preview.py    # Standalone tool: preview drone layout for a given seed
auxil/                 # Miscellaneous helper scripts
```

### Data Output

Study data written to:
- **Real runs**: `results/participants_study/<pid>_<timestamp>/`
- **Test runs**: `results/participants_test/<pid>_<timestamp>/` (auto-purges to last 5)

Per-session layout:
```
study_metadata.json          # Config snapshot at start
demographics.json            # Pre-study survey
trial_01_<label>/
  game_events.jsonl          # All in-game events (timestamped)
  recordings/recording_*.mp4 # Optional screen recording
trial_01_<label>_survey.json # Post-trial survey
...
summary_survey.json          # Post-study summary questionnaire
study_summary.json           # Final results (clash_pct per trial)
```

Key JSONL event types:
- `game_start` / `game_end` — trial bookends
- `switch_requested` — drone_id, from_channel, to_channel, mode (M1/M2/M3/flex_auto)
- `suggestion_requested` / `suggestion_shown` / `suggestion_applied` / `suggestion_cancelled`
- `auto_assign_applied` — flex auto mode
- `clash_start` / `clash_end` / `clash_update` — clash pair transitions
- `play_started` — moment SETUP → PLAYING (timer begins)

### Study Configuration (default as of May 2026)

Saved in `~/.drone_study_config.json`. Default on first run:

| # | Trial | Agent mode | Surveys | Record | Seed |
|---|---|---|---|---|---|
| 1 | Flexible Tutorial | flexible | none | yes | 42 |
| 2 | Easy (8dr, slow, 70%) | flexible | TLX + Trust + Accept | yes | 52 |
| 3 | Medium (12dr, slow, 70%) | flexible | TLX + Trust + Accept | yes | 72 |
| 4 | Hard (16dr, fast, 70%) | flexible | TLX + Trust + Accept | yes | 42 |

Arena monitor: 0, Panel monitor: 2 (last available). Both survey types enabled.

## Development Guidelines

### Adding a complexity preset

Add an entry to `COMPLEXITY_PRESETS` in `robot_world.py` and a matching `TrialConfig` in `STUDY_PRESETS` in `study_runner.py`.

### Changing agent accuracy

Edit the `epsilon` field on the relevant `TrialConfig` in `STUDY_PRESETS`. `epsilon=0` = perfect, `epsilon=0.30` = 70% optimal.

### Modifying agent logic

`agents/channel_agent.py` — `ChannelAdvisor.suggest()`. Greedy ordering is by most-constrained-first within the selected subgroup.

### Flexible monitor behaviour

`_flex_tick()` inside `run_game()` in `robot_game.py`. Controls monitor interval (`_MONITOR_INTERVAL`), cooldown (`switch_duration + 0.5`), and re-fire delay for suggest mode (`_SUGGEST_REFIRE_DELAY`).

### Tutorial steps

`tutorial.py` — `_make_steps()` for standard (10 steps) and `_make_flex_steps()` for flexible (16 steps). Each `TutorialStep` has a `setup_fn`, optional `completion_check`, and `disabled_buttons`.

## Critical Constraints

1. **No LLMs** — all agent logic is deterministic and rule-based
2. **Determinism** — `RobotWorld` uses a seeded `random.Random`; same seed → same drone trajectories
3. **Effective channels in planning** — always pass `switching_to or channel` to the advisor, never just `channel`, to avoid planning against stale mid-switch state
4. **Logging fidelity** — every decision must be logged with `world.elapsed` timestamp
5. **UI language** — use "agent" or "assistant", never "AI" or "LLM"
6. **Arena never pre-colours** — the arena always shows actual drone channels; suggestions are displayed only in the panel mini-graph

## Legacy / Unused

The following exist in the repo but are not used by the current study:

- `docs/` — old architecture documents from a previous iteration
- `tests/` — tests written for an earlier LLM-based agent system
- `old_files/` — previous main/simulation scripts
- `auxil/` — miscellaneous helper scripts, not part of the study pipeline
