# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **research-grade prototype** for studying **human–agent coordination via language** in a **clustered graph-colouring** task with **partial observability**. The system is designed for rigorous academic experiments where determinism, logging, and observability constraints are critical.

## Running the Code

### Standard Entry Point

```bash
python launch_menu.py
```

This launches a GUI menu for configuring and running experiments. Defaults are designed to work out of the box.

### Python Environment

The project uses a Python virtual environment (`venv/`). Activate it before running:

```bash
# Windows
venv\Scripts\activate

# Unix/macOS
source venv/bin/activate
```

### Communication Modes

The system supports multiple within-subject conditions:
- `RB` — rule-based argumentation (no LLM)
- `LLM_U` — utility-oriented language
- `LLM_C` — constraint-oriented language
- `LLM_F` — free-form negotiation
- `LLM_RB` (optional) — NL → RB grammar → NL

**Important**: LLMs are used **only as a communication/interpretation layer**. They do **not** solve the optimization problem.

### API Key Configuration

The OpenAI API key is stored in `api_key.txt` at the project root. This file should **never** be committed.

## Architecture

### System Design

The graph is partitioned into 3 clusters in the default experiment:

```
Agent1 ← → Human ← → Agent2
```

Each participant (human or agent) controls one cluster and coordinates through boundary nodes.

### Partial Observability (CRITICAL - DO NOT BREAK)

- Each participant **fully sees** their own cluster (nodes + internal edges)
- Each participant sees **only boundary neighbours** from other clusters
- Neighbour colours are known only via:
  - Explicit reports in messages
  - Boundary-node colours visible through inter-cluster edges in the UI

**Never leak hidden topology**. Neighbour node colours must not be shown unless they are boundary nodes AND the colour is known via assignment or report.

### Termination Semantics

The system does **not** auto-terminate on `penalty==0`. For the async chat UI, the run ends when **consensus** is reached:
- Human ticks "I'm satisfied" in each neighbour chat window
- Agent reports `agent.satisfied == True`

When consensus is reached, UI closes with `ui.end_reason == "consensus"`.

### Key Components

```
launch_menu.py              # GUI launcher for experiments
run_experiment.py           # Entry point for single run with config
cluster_simulation.py       # Main simulation loop + UI wiring
agents/cluster_agent.py     # Per-cluster solver + message generation
agents/rule_based_cluster_agent.py  # RB mode agent
comm/communication_layer.py # Renders structured messages to natural language
ui/human_turn_ui.py         # Tkinter GUI (graph view + 2 async chat panes)
problems/graph_coloring.py  # Graph coloring problem definition
```

### Data Flow (Async UI)

1. Human edits colours by clicking owned nodes
2. Human sends message in chat pane (Agent1 or Agent2)
3. UI invokes `on_send(neigh, msg, current_assignments)` in background thread
4. Simulation routes message to relevant agent controller
5. Agent updates beliefs, runs local solver, responds
6. UI updates: chat transcript, neighbour colours (from `[report: {...}]`), graph rendering

### Agent Architecture

Agents use configurable **local optimization algorithms**:
- `"greedy"` — greedy colouring heuristic (default)
- `"maxsum"` — exhaustive search

Agents support multiple **message formats**:
- `cost_list` — utility messages (Max-Sum style)
- `constraints` — feasible colour sets
- `free_text` — natural language descriptions

The choice of algorithm is **independent** from message format.

### Local Optimality vs Satisfaction

Clusters are small, so agents may "snap" to the best local assignment when greedy search stalls. This is **intentional** and improves stability in experiments.

## Logging

Outputs are written to `results/<mode>_<timestamp>/`:

- `Agent1_log.txt`, `Agent2_log.txt`, `Human_log.txt` — per-participant logs
- `communication_log.txt` — message exchange log
- `iteration_summary.txt` — iteration-by-iteration summary
- `results/llm_trace.jsonl` — LLM prompt/response/parse/render events (when enabled)

Logs are appended incrementally so crashes yield partial traces.

## Development Guidelines

### Key Files to Modify

- **Message style/prompting**: `comm/communication_layer.py`
- **Counterfactual enumeration**: `agents/cluster_agent.py`
- **UI behaviour**: `ui/human_turn_ui.py`
- **Orchestration/logging**: `cluster_simulation.py`

### Adding a New Communication Mode

1. Add mode to launcher dropdown in `launch_menu.py`
2. Implement comm layer in `comm/` directory
3. Wire agent creation to use it in `cluster_simulation.py`
4. Ensure logs include LLM traces if required

### Indentation Hygiene

Python indentation errors have been a recurring integration hazard. When adding helpers:
- Move helpers into a separate module file, OR
- Keep helper functions inside the class with consistent indentation

### Testing

Run each mode from `launch_menu.py` and verify:
- UI renders correctly
- Messaging works bidirectionally
- Neighbour visibility respects partial observability
- Logs are generated correctly

## Critical Constraints

1. **Partial observability**: Never expose hidden topology or non-boundary nodes
2. **Determinism**: System must produce reproducible results for research validity
3. **No auto-termination**: System does not stop on penalty==0; requires consensus
4. **LLM role**: LLMs are communication layers only, not problem solvers
5. **Logging fidelity**: All agent reasoning and messages must be logged

## Common Issues

See `docs/TROUBLESHOOTING.md` for detailed troubleshooting. Quick checks:

- **UI closes instantly**: Check `cluster_simulation.py` UI branch and ensure UI loop blocks
- **No agent replies**: Check `ui/human_turn_ui.py` background thread + `on_send` callback signature
- **Consensus never ends**: Ensure agents update `agent.satisfied` and UI polling is running

## Project Structure

```
.
├── agents/              # Agent implementations
├── comm/                # Communication layer implementations
├── problems/            # Problem definitions (graph coloring)
├── ui/                  # Tkinter UI components
├── docs/                # Additional documentation
├── results/             # Experimental outputs (gitignored)
├── test_output/         # Test run outputs (gitignored)
├── launch_menu.py       # Main launcher
├── run_experiment.py    # Programmatic experiment runner
├── cluster_simulation.py # Simulation orchestrator
└── api_key.txt          # OpenAI API key (gitignored)
```

## Additional Documentation

- `README.md` — High-level overview and quick start
- `docs/ARCHITECTURE.md` — Detailed architecture notes
- `docs/DEVELOPER_GUIDE.md` — Where to change things
- `docs/TROUBLESHOOTING.md` — Common issues and solutions
