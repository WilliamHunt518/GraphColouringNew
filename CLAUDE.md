# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

This is a **research-grade prototype** for studying **trust and collaboration with autonomous AI agents** via a graph-colouring task. The application is used in a human-subjects study with a **2×2 within-subjects design**.

## Running the Code

### Standard Entry Point

```bash
python launch_menu.py
```

This opens a simple launcher to configure participant ID, mode, graph preset, and seed, then spawns the experiment window.

### Direct Entry Point (for testing)

```bash
python run_experiment.py --participant P01 --mode mode1 --graph study_12
python run_experiment.py --participant P01 --mode mode2a --graph study_12
python run_experiment.py --participant P01 --mode mode2b --graph study_12
```

### Python Environment

The project uses system Python. Ensure Tkinter is available.

```bash
python -m tkinter   # should open a test window
```

## Architecture

### Study Design

- **Mode 1 — Manual Collaborative**: At each node (in fixed sequential order), AI agents propose a colour with rationale. The human makes the final choice.
- **Mode 2A — Autonomous (High Quality)**: A multi-agent deliberation pre-plans a full solution (~80% optimal choices). The human reviews and accepts/modifies each step.
- **Mode 2B — Autonomous (Low Quality)**: Same as 2A but with ~30% optimal choices. Visually identical to 2A.

### Sequential Colouring

Nodes are coloured **one at a time in a fixed order** (no skipping or reordering). This forces path dependency and suboptimal local decisions — the study variable.

### Scoring

- Each participant (Human, AgentA, AgentB) earns points when a node is coloured with their assigned colour
- All colourings are valid — no adjacency penalty
- **Shared score** = sum of all individual scores
- Defaults: Human earns 3/1 pts for Red/Blue; AgentA earns 1/4 for Red/Blue; AgentB earns 2/2
- Blue is globally optimal (7 pts/node) but Human individually prefers Red (3 pts personal)

### Key Components

```
launch_menu.py         # GUI launcher
run_experiment.py      # CLI entry point
simulation.py          # ColourSession orchestrator (attempt loop)

study/
  config.py            # StudyConfig + dataclasses
  graphs.py            # Graph presets (study_12, study_15)
  session.py           # SessionManager — tracks in-progress attempt
  logger.py            # StudyLogger — writes JSONL events

problems/
  graph_coloring.py    # GraphColoring (topology only — KEEP UNCHANGED)
  scoring.py           # PointsScorer, ScoringResult

agents/
  proposal_agent.py    # Mode 1: per-node proposals with template rationales
  planning_agent.py    # Mode 2: full-plan deliberation with quality bias

ui/
  graph_canvas.py      # GraphCanvas widget (pan/zoom graph display)
  scoring_hud.py       # ScoringHUD widget (shared + individual scores)
  colouring_ui.py      # ColourStudyWindow (main experiment window)
  results_panel.py     # AttemptResultsWindow (end-of-attempt summary)
  node_layouts.json    # Fractional node positions per preset
```

### Data Logging

All events written to `results/participants/<pid>_<timestamp>/events.jsonl`.

Key logged events:
- `colour_chosen` — node, colour, source (`human`/`accepted_plan`/`modified_plan`), `decision_time_s`, `agents_agreed`
- `explanation_click` — tracks when user expands agent rationale
- `plan_modified` — tracks overrides in Mode 2 (plan_colour vs chosen_colour)
- `attempt_complete` — final assignment, score breakdown, elapsed time
- `session_end` — score trajectory across all attempts

## Development Guidelines

### Adding a New Graph Preset

1. Add a `GraphDef` entry to `study/graphs.py`
2. Add node coordinates to `ui/node_layouts.json` (fractional 0–1 range, keyed by preset name)
3. Add to `GRAPH_CONFIGS` and `NODE_REGIONS` dicts in `study/graphs.py`

### Changing Scoring Weights

Edit `DEFAULT_POINTS` in `study/config.py`. All values are per-node, per-colour.

### Modifying Agent Logic

- **Mode 1 proposals**: `agents/proposal_agent.py` — `propose_for_node()` method
- **Mode 2 plan**: `agents/planning_agent.py` — `_deliberate_node()` method; quality bias is in `generate_plan()`

### Never Modify

- `problems/graph_coloring.py` — used as-is for graph topology; do not change
- `ui/node_layouts.json` node positions for existing presets (break existing studies)

## Critical Constraints

1. **No LLMs** — all agent logic is deterministic and rule-based
2. **Determinism** — seeded `random.Random` ensures reproducibility across sessions
3. **No auto-termination** — user always explicitly finishes via the results window
4. **Logging fidelity** — all decisions must be logged with timestamps
5. **UI language** — use "agent" or "assistant", never "AI" or "LLM"

## Legacy Files

The following files are from the previous implementation and are **not imported** by the new code. They are kept for reference but should be ignored:

- `cluster_simulation.py` — old orchestration layer
- `study_launcher.py` — old multi-condition launcher
- `agents/cluster_agent.py` and variants
- `comm/` — LLM communication layers
- `docs/` — old architecture docs

## Project Structure

```
.
├── agents/                # Agent implementations (new: proposal_agent, planning_agent)
├── comm/                  # Legacy (unused)
├── docs/                  # Legacy docs (unused)
├── problems/              # Problem definitions
├── study/                 # Study management (config, session, logger, graphs)
├── ui/                    # Tkinter UI components
├── results/               # Experimental outputs (gitignored)
├── launch_menu.py         # Main launcher
├── run_experiment.py      # CLI entry point
└── simulation.py          # Session orchestrator
```
