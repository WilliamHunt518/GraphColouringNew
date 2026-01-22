"""Main entry point for the revised clustered graph colouring study.

Run from the repository root with:

    python3 code/run_experiment.py

This script sets up **1 human cluster + 2 agent clusters**, with 5 nodes
each. The human cluster sits between the two agents and shares 1--2
boundary edges with each agent.

Toggle the METHOD below to run one of the four conditions:

    RB      : rule-based deliberation baseline
    LLM_API : constraint-oriented messages with LLM API
    LLM_F   : free-form messages
    LLM_RB  : natural language to rule-based grammar

By default, the human is *you* (interactive prompts). You can also enable
the Tkinter GUI by setting USE_UI=True.
"""

from __future__ import annotations

import os
from pathlib import Path


# -----------------
# CONFIGURE HERE
# -----------------

METHOD = "RB"   # one of: "RB", "LLM_API", "LLM_F", "LLM_RB"
USE_UI = True  # True => Tkinter UI for the human turn
MANUAL_MODE = False  # True => do NOT call an external LLM API
MAX_ITERS = 10
AGENT_ALG = "greedy"  # "greedy" or "maxsum" (exhaustive)
CONVERGENCE_K = 2
STOP_ON_SOFT = True
STOP_ON_HARD = True
COUNTERFACTUAL_UTILS = True
FIXED_CONSTRAINTS = True  # True => 1 fixed node per cluster to force negotiation


def run_experiment(
    *,
    method: str,
    use_ui: bool,
    manual_mode: bool,
    max_iters: int,
    agent_algorithm: str = "greedy",
    convergence_k: int = 2,
    stop_on_soft: bool = True,
    # Study default: do not auto-stop purely on hard convergence.
    stop_on_hard: bool = False,
    counterfactual_utils: bool = True,
    fixed_constraints: bool = True,
    num_fixed_nodes: int = 1,
) -> None:
    # Ensure outputs are written under the *project root* (i.e., the directory
    # you opened in your IDE / run from). This avoids writing results one level
    # above the project when the code directory sits inside a larger repository.
    cwd = Path.cwd()
    if (cwd / "code").exists() or (cwd / "run_experiment.py").exists():
        project_root = cwd
    else:
        # Fallback: treat the parent of this file as the project root.
        project_root = Path(__file__).resolve().parent

    results_dir = project_root / "results" / method.lower()
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"[run_experiment] Writing results to: {results_dir}")

    # Import *from the code package* explicitly (avoid accidentally importing
    # similarly named modules from the repo root).
    from cluster_simulation import run_clustered_simulation

    # --- Clustered topology (5 nodes per cluster) ---
    human_nodes = ["h1", "h2", "h3", "h4", "h5"]
    agent1_nodes = ["a1", "a2", "a3", "a4", "a5"]
    agent2_nodes = ["b1", "b2", "b3", "b4", "b5"]
    node_names = human_nodes + agent1_nodes + agent2_nodes

    clusters = {
        "Human": human_nodes,
        "Agent1": agent1_nodes,
        "Agent2": agent2_nodes,
    }

    # Internal edges: small cycles + chords (keeps local reasoning non-trivial)
    adjacency = {
        # Human cluster
        "h1": ["h2", "h5"],
        "h2": ["h1", "h3", "h5"],
        "h3": ["h2", "h4"],
        "h4": ["h3", "h5"],
        "h5": ["h1", "h2", "h4"],
        # Agent1 cluster
        "a1": ["a2", "a5"],
        "a2": ["a1", "a3", "a5"],
        "a3": ["a2", "a4"],
        "a4": ["a3", "a5"],
        "a5": ["a1", "a2", "a4"],
        # Agent2 cluster
        "b1": ["b2", "b5"],
        "b2": ["b1", "b3", "b5"],
        "b3": ["b2", "b4"],
        "b4": ["b3", "b5"],
        "b5": ["b1", "b2", "b4"],
    }

    # Cross-cluster edges (harder boundary structure)
    #  - One-to-many: a single human boundary node connects to *two* nodes in Agent1.
    #  - Many-to-one: two human boundary nodes connect to the *same* node in Agent2.
    #
    # Human <-> Agent1
    #   h1 -- a2
    #   h4 -- a4 and h4 -- a5   (double connection)
    adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
    adjacency["h4"].append("a4"); adjacency["a4"].append("h4")
    adjacency["h4"].append("a5"); adjacency["a5"].append("h4")

    # Human <-> Agent2
    #   h2 -- b2 and h5 -- b2  (many-to-one)
    adjacency["h2"].append("b2"); adjacency["b2"].append("h2")
    adjacency["h5"].append("b2"); adjacency["b2"].append("h5")

    owners = (
        {n: "Human" for n in human_nodes}
        | {n: "Agent1" for n in agent1_nodes}
        | {n: "Agent2" for n in agent2_nodes}
    )

    # Algorithms per cluster (you can vary this later)
    # LLM_API mode uses exhaustive search for better solution quality
    if method == "LLM_API":
        cluster_algorithms = {"Human": "greedy", "Agent1": "maxsum", "Agent2": "maxsum"}
    else:
        cluster_algorithms = {"Human": "greedy", "Agent1": agent_algorithm, "Agent2": agent_algorithm}

    # Message type per cluster. For RB mode, human also uses rule_based to enable structured UI.
    # For LLM modes, human uses free_text while agents use the specified message type.
    if method == "RB":
        cluster_message_types = {"Human": "rule_based", "Agent1": "rule_based", "Agent2": "rule_based"}
    elif method == "LLM_API":
        cluster_message_types = {"Human": "free_text", "Agent1": "constraints", "Agent2": "constraints"}
    elif method == "LLM_F":
        cluster_message_types = {"Human": "free_text", "Agent1": "free_text", "Agent2": "free_text"}
    elif method == "LLM_RB":
        cluster_message_types = {"Human": "llm_rb", "Agent1": "llm_rb", "Agent2": "llm_rb"}
    else:
        raise ValueError(f"Unknown METHOD: {method}")

    domain = ["red", "green", "blue"]

    run_clustered_simulation(
        node_names=node_names,
        clusters=clusters,
        adjacency=adjacency,
        owners=owners,
        cluster_algorithms=cluster_algorithms,
        cluster_message_types=cluster_message_types,
        domain=domain,
        max_iterations=max_iters,
        interactive=True,
        manual_mode=manual_mode,
        human_owners=["Human"],
        use_ui=use_ui,
        ui_title=f"{method} — Human Turn",
        output_dir=str(results_dir),
        convergence_k=int(convergence_k),
        stop_on_soft=bool(stop_on_soft),
        stop_on_hard=bool(stop_on_hard),
        counterfactual_utils=bool(counterfactual_utils),
        fixed_constraints=bool(fixed_constraints),
        num_fixed_nodes=int(num_fixed_nodes),
    )

    print(f"[run_experiment] Finished. Check outputs in: {results_dir}")


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Run the clustered graph-colouring study.")
    p.add_argument("--method", default=METHOD, choices=["RB", "LLM_API", "LLM_F", "LLM_RB"])
    ui = p.add_mutually_exclusive_group()
    ui.add_argument("--use-ui", dest="use_ui", action="store_true")
    ui.add_argument("--no-ui", dest="use_ui", action="store_false")
    p.set_defaults(use_ui=USE_UI)

    llm = p.add_mutually_exclusive_group()
    llm.add_argument("--manual", dest="manual_mode", action="store_true", help="No API calls")
    llm.add_argument("--api", dest="manual_mode", action="store_false", help="Use API if configured")
    p.set_defaults(manual_mode=MANUAL_MODE)

    p.add_argument("--max-iters", type=int, default=MAX_ITERS)
    p.add_argument("--agent-alg", default=AGENT_ALG, choices=["greedy", "maxsum"])
    p.add_argument("--k", type=int, default=CONVERGENCE_K, help="Soft convergence streak")
    p.add_argument("--stop-soft", action="store_true", default=STOP_ON_SOFT)
    p.add_argument("--stop-hard", action="store_true", default=STOP_ON_HARD)

    util = p.add_mutually_exclusive_group()
    util.add_argument("--counterfactual-utils", dest="counterfactual_utils", action="store_true", help="LLM-U/LLM-C: derive utilities/constraints via best-response counterfactuals")
    util.add_argument("--naive-utils", dest="counterfactual_utils", action="store_false", help="LLM-U/LLM-C: derive utilities/constraints from current assignment only")
    p.set_defaults(counterfactual_utils=COUNTERFACTUAL_UTILS)

    p.add_argument("--fixed-constraints", action="store_true", default=FIXED_CONSTRAINTS, help="Fix 1 internal node per cluster to force negotiation")
    p.add_argument("--num-fixed-nodes", type=int, default=1, choices=[0, 1, 2, 3], help="Number of fixed nodes per cluster (0-3)")

    args = p.parse_args()

    run_experiment(
        method=args.method,
        use_ui=bool(args.use_ui),
        manual_mode=bool(args.manual_mode),
        max_iters=int(args.max_iters),
        agent_algorithm=str(args.agent_alg),
        convergence_k=int(args.k),
        stop_on_soft=bool(args.stop_soft),
        stop_on_hard=bool(args.stop_hard),
        counterfactual_utils=bool(args.counterfactual_utils),
        fixed_constraints=bool(args.fixed_constraints),
        num_fixed_nodes=int(args.num_fixed_nodes),
    )


if __name__ == "__main__":
    main()
