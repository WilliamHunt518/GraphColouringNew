# Graph Colouring Trust Study

An interactive graph-colouring application for a human-subjects study on **trust and collaboration with autonomous AI agents**.

## Quick Start

```bash
python launch_menu.py
```

## Overview

Participants colour a graph node-by-node (in a fixed sequential order) in collaboration with AI agents. The goal is to maximise a shared score — each participant earns points when nodes are assigned their preferred colour.

The study uses a **2×2 within-subjects design**:

| Condition | Session 1 | Session 2 |
|---|---|---|
| A | Mode 1 | Mode 2A |
| B | Mode 2A | Mode 1 |
| C | Mode 1 | Mode 2B |
| D | Mode 2B | Mode 1 |

### Mode 1 — Manual Collaborative

At each node, agents each propose a colour with a brief rationale. The human makes the final choice. Proposals can be expanded for fuller reasoning (tracked for analysis).

### Mode 2A — Autonomous Planning (High Quality)

Before colouring begins, the autonomous agent system runs a multi-agent deliberation to produce a complete proposed solution. The plan is presented step-by-step — the human can accept, request an explanation, or modify each step. Mode 2A produces near-optimal plans (~80% of the time).

### Mode 2B — Autonomous Planning (Low Quality)

Identical UI to Mode 2A, but the underlying plan is frequently suboptimal (~30% optimal choices). Designed to measure overtrust.

## Scoring

- **Human**: earns 3 pts per Red node, 1 pt per Blue node
- **AgentA**: earns 1 pt per Red node, 4 pts per Blue node
- **AgentB**: earns 2 pts per Red or Blue node
- **Shared score** (displayed prominently): sum of all individual scores
- Blue gives 7 pts/node total; Red gives 6 pts/node — but Human individually prefers Red

Participants can attempt the same graph up to 3 times, with the expectation of improving over iterations.

## Data Collected

All events are logged to `results/participants/<pid>_<timestamp>/events.jsonl`:

- Per-node decision time
- Explanation click-throughs
- Override rate (Mode 2: how often human modifies the agent's plan)
- Score trajectory across 3 attempts
- Agent agreement patterns

## Configuration

All parameters (graph topology, score weights, quality ratios, number of attempts) are configurable in `study/config.py` and `study/graphs.py`.

See `CLAUDE.md` for developer documentation.
