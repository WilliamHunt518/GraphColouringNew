"""Main entry point for the revised clustered graph colouring study.

Run from the repository root with:

    python3 code/run_experiment.py

This script always sets up **1 human cluster + 1 agent cluster**, with
5 nodes each and 2 cross-cluster connections, matching the planned study.

Toggle the METHOD below to run one of the four conditions:

    RB     : rule-based deliberation baseline
    LLM_U  : utility-oriented messages
    LLM_C  : constraint-oriented messages
    LLM_F  : free-form messages

By default, the human is *you* (interactive prompts). You can also enable
the Tkinter GUI by setting USE_UI=True.
"""

from __future__ import annotations

import os
from pathlib import Path


# -----------------
# CONFIGURE HERE
# -----------------

METHOD = "LLM_U"   # one of: "RB", "LLM_U", "LLM_C", "LLM_F"
USE_UI = True  # True => Tkinter UI for the human turn
MANUAL_MODE = False  # True => do NOT call an external LLM API
MAX_ITERS = 10


def main() -> None:
    # Ensure outputs are written under repo/results
    repo_root = Path(__file__).resolve().parents[1]
    results_dir = repo_root / "results" / METHOD.lower()
    results_dir.mkdir(parents=True, exist_ok=True)

    # Import *from the code package* explicitly (avoid accidentally importing
    # similarly named modules from the repo root).
    from cluster_simulation import run_clustered_simulation

    # --- Clustered topology (5 nodes per cluster) ---
    human_nodes = ["h1", "h2", "h3", "h4", "h5"]
    agent_nodes = ["a1", "a2", "a3", "a4", "a5"]
    node_names = human_nodes + agent_nodes

    clusters = {
        "Human": human_nodes,
        "Agent": agent_nodes,
    }

    # Internal edges: small cycles + chords (keeps local reasoning non-trivial)
    adjacency = {
        # Human cluster
        "h1": ["h2", "h5"],
        "h2": ["h1", "h3", "h5"],
        "h3": ["h2", "h4"],
        "h4": ["h3", "h5"],
        "h5": ["h1", "h2", "h4"],
        # Agent cluster
        "a1": ["a2", "a5"],
        "a2": ["a1", "a3", "a5"],
        "a3": ["a2", "a4"],
        "a4": ["a3", "a5"],
        "a5": ["a1", "a2", "a4"],
    }

    # Cross-cluster edges (1-2 as requested)
    adjacency["h1"].append("a2")
    adjacency["h4"].append("a4")
    adjacency["a2"].append("h1")
    adjacency["a4"].append("h4")

    owners = {n: "Human" for n in human_nodes} | {n: "Agent" for n in agent_nodes}

    # Algorithms per cluster (you can vary this later)
    cluster_algorithms = {"Human": "greedy", "Agent": "greedy"}

    # Message type per cluster. Human's message type doesn't matter (human is interactive);
    # Agent's message type determines the condition.
    if METHOD == "RB":
        cluster_message_types = {"Human": "free_text", "Agent": "rule_based"}
    elif METHOD == "LLM_U":
        cluster_message_types = {"Human": "free_text", "Agent": "cost_list"}
    elif METHOD == "LLM_C":
        cluster_message_types = {"Human": "free_text", "Agent": "constraints"}
    elif METHOD == "LLM_F":
        cluster_message_types = {"Human": "free_text", "Agent": "free_text"}
    else:
        raise ValueError(f"Unknown METHOD: {METHOD}")

    domain = ["red", "green", "blue"]

    run_clustered_simulation(
        node_names=node_names,
        clusters=clusters,
        adjacency=adjacency,
        owners=owners,
        cluster_algorithms=cluster_algorithms,
        cluster_message_types=cluster_message_types,
        domain=domain,
        max_iterations=MAX_ITERS,
        interactive=True,
        manual_mode=MANUAL_MODE,
        human_owners=["Human"],
        use_ui=USE_UI,
        ui_title=f"{METHOD} — Human Turn",
        output_dir=str(results_dir),
    )


if __name__ == "__main__":
    main()
