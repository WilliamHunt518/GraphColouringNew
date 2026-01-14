# GraphColouringNew — Human–Agent Coordination Prototype

This repository implements a **research-grade** prototype for studying **human–agent coordination via language**
in a **clustered graph-colouring** task with **partial observability**.

The system is **not a toy**: determinism, logging, and correctness of observability boundaries are treated as first-class
engineering constraints.

---

## What you can run (normal workflow)

**Run the launcher** (this is the standard entry-point):

```bash
python launch_menu.py
```

Defaults are designed to work. Select a communication mode from the dropdown, then run.

Modes (within-subject conditions):

- `RB` — rule-based argumentation (no LLM)
- `LLM_U` — utility-oriented language
- `LLM_C` — constraint-oriented language
- `LLM_F` — free-form negotiation
- (optional) `LLM_RB` — NL → RB grammar → NL (if enabled in the codebase)

> LLMs are used as a **communication / interpretation layer only**. They do **not** solve the optimisation problem.

---

## Core research assumptions (do not break)

### Partial observability (critical)

- Each participant (human or agent) **fully** sees its **own cluster** (nodes + internal edges).
- Each participant sees **only boundary neighbours** from other clusters.
- A participant may only know neighbour colours via:
  - explicit reports embedded in messages, and/or
  - boundary-node colours implied by the visible inter-cluster edges in the UI.

### Termination semantics

The system does **not** auto-terminate on penalty==0.

For the **async chat UI**, the run ends when **consensus** is reached:

- For each neighbour chat window:
  - the **human** ticks “I’m satisfied”, and
  - the **agent** reports itself satisfied (internally `agent.satisfied == True`)

When consensus is reached, the UI closes and `ui.end_reason == "consensus"`.

---

## Logging (important)

Outputs are written under `results/<mode>_<timestamp>/` and include:

- `Agent1_log.txt`, `Agent2_log.txt`, `Human_log.txt`
- `communication_log.txt`
- `iteration_summary.txt`
- `results/llm_trace.jsonl` (prompt/response/parse/render events where enabled)

The logs are appended incrementally so crashes still yield partial traces.

---

## Code structure (high-level)

- `launch_menu.py` — UI launcher used during development and experiments
- `run_experiment.py` — experiment entry for one run (mode selection, config)
- `cluster_simulation.py` — clustered simulation loop + UI wiring
- `agents/cluster_agent.py` — per-cluster solver + message generation
- `comm/communication_layer.py` — renders structured messages into human-facing text
- `ui/human_turn_ui.py` — Tkinter GUI (graph view + 2 async chat panes + debug window)

Documentation lives in `docs/`.

---

## Development notes

### Avoid indentation drift bugs

Python indentation errors have been a recurring integration hazard.
If you add helpers, prefer:
- moving helpers into a separate module file, or
- keeping helper functions *inside* the class with consistent indentation.

### Local optimality vs satisfaction

Clusters are small, so the agent may “snap” to the best local assignment when greedy search stalls.
This is intentional and improves stability in experiments.

---

## Quick troubleshooting

- **UI closes instantly**: check `cluster_simulation.py` UI branch and ensure the UI loop blocks.
- **No agent replies**: check `ui/human_turn_ui.py` background thread + `on_send` callback signature.
- **Consensus never ends**: ensure agents update `agent.satisfied` and UI polling is running.

See `docs/TROUBLESHOOTING.md` for more.
