# Drone Channel Assignment — Trust Study

A human-subjects study prototype examining **trust calibration and workload** when working alongside autonomous AI agents on a real-time interference-management task.

> **Note:** The repository is named `GraphColouringNew` for historical reasons. The actual task is drone radio-channel assignment, not graph colouring.

## Quick Start

### Full study session (researcher)

```bash
python study_runner.py
```

Presents a setup window to configure participant ID, monitor layout, trial list, and surveys. Config is saved and restored between launches.

### Single game (developer / testing)

```bash
python launch_menu.py
```

## Task Overview

Participants manage a swarm of moving drones in a 2D arena. Each drone is assigned a radio channel (red, green, or blue). When two drones on the **same channel** come within interference range, a **clash** occurs — accumulating penalty time for as long as they remain in range. The goal is to minimise total clash time over a fixed-duration trial.

### Interaction Modes

Three modes are available simultaneously:

| Mode | How it works |
|---|---|
| **M1 — Manual** | Click a drone → pick a channel from a popup menu |
| **M2 — Suggest & Review** | Select a group, request a suggestion, review and optionally edit the proposal in the side panel, then apply |
| **M3 — Auto-assign** | Select a group and apply the agent's recommendation instantly without review |

In **flexible agent mode**, individual drones can be placed under autonomous monitoring:
- **Watch:Suggest** — agent raises a suggestion panel when that drone's cluster clashes
- **Watch:Auto** — agent applies fixes automatically without user input

### Agent

The AI assistant uses a greedy graph-colouring algorithm with configurable noise (`epsilon`). At `epsilon=0.30` the agent is correct ~70% of the time per drone — good but imperfect, requiring human oversight.

## Study Conditions

Default trial sequence (configurable in the setup window):

| Trial | Scenario | Drones | Duration | Agent accuracy |
|---|---|---|---|---|
| 1 | Flexible Tutorial | — | until complete | perfect |
| 2 | Easy | 8, slow | 90 s | 70% |
| 3 | Medium | 12, slow | 120 s | 70% |
| 4 | Hard | 16, fast | 150 s | 70% |

All non-tutorial trials use **flexible agent mode** and include post-trial surveys (NASA-TLX workload, trust items, technology acceptance items) and screen recording.

## Data Collected

All in-game events are written to `results/participants_study/<pid>_<timestamp>/`:

- **JSONL event log** per trial — every channel switch, suggestion request/apply/cancel, clash start/end, and mode interaction with millisecond timestamps
- **Surveys** — pre-study demographics, post-trial workload/trust/TAM, post-study summary
- **Screen recordings** (mp4) — one per trial when recording is enabled

## Analysis

```bash
python analysis/run_analysis.py
```

Produces per-participant and aggregate metrics, plots, and statistical test outputs from the collected JSONL logs.

## Requirements

- Python 3.10+
- `pygame` (`pip install pygame`)
- Tkinter (bundled with standard Python)
- `pygame._sdl2` for detached panel window on a second monitor (included in modern pygame)

## Developer Notes

See `CLAUDE.md` for full architecture documentation, file map, and development guidelines.
