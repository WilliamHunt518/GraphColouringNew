"""Clustered DCOP simulation entry point.

This module provides a simulation driver for experiments on clustered
graph colouring as described in the revised graph colouring approach.
Instead of one agent per node, the graph is partitioned into clusters.
Each cluster agent controls all nodes within its cluster, runs a
specified local optimisation algorithm, and communicates with other
clusters using a configurable message format.  Communication between
clusters is mediated by a configurable communication layer (LLM or
pass-through) defined in ``comm.communication_layer``.

Example
-------
Define a simple clustered graph with two clusters and run for 5
iterations using different algorithms and message types::

    from code.cluster_simulation import run_clustered_simulation
    CONFIG = dict(
        node_names=["1","2","3","4","5","6"],
        clusters={"Alice": ["1","2","3"], "Bob": ["4","5","6"]},
        adjacency={
            "1": ["2","4"],
            "2": ["1","3"],
            "3": ["2","6"],
            "4": ["1","5"],
            "5": ["4","6"],
            "6": ["5","3"],
        },
        owners={"1":"Alice","2":"Alice","3":"Alice","4":"Bob","5":"Bob","6":"Bob"},
        cluster_algorithms={"Alice": "greedy", "Bob": "maxsum"},
        cluster_message_types={"Alice": "cost_list", "Bob": "free_text"},
        domain=["red","green","blue"],
        max_iterations=5,
        interactive=False,
        manual_mode=True,
        output_dir="./cluster_outputs",
    )
    run_clustered_simulation(**CONFIG)

This will create two cluster agents: Alice uses a greedy heuristic and
sends cost lists, while Bob uses an exhaustive search (Max–Sum) and
sends free‑form text descriptions of its assignments.  The function
generates per‑iteration logs, a global penalty summary and
visualisations in the specified output directory.
"""

from __future__ import annotations

import os
import datetime
import json
from typing import Dict, List, Any, Optional, Callable

# Import modules using absolute package names.  When running this
# module directly or importing it after adding ``code`` to ``sys.path``
# the packages ``problems``, ``comm`` and ``agents`` resolve to the
# corresponding subpackages within the ``code`` directory.
from problems.graph_coloring import GraphColoring
from comm.communication_layer import LLMCommLayer, PassThroughCommLayer
try:
    from comm.llm_rb_comm_layer import LLMRBCommLayer  # newer location
except Exception:
    try:
        from comm.communication_layer import LLMRBCommLayer  # fallback/legacy
    except Exception:
        LLMRBCommLayer = None

from agents.cluster_agent import ClusterAgent
from agents.rule_based_cluster_agent import RuleBasedClusterAgent


def _get_active_conditionals(agents: List[Any]) -> tuple:
    """Extract active conditional offers and configurations from all agents.

    Parameters
    ----------
    agents : list
        List of agent instances to extract conditionals from.

    Returns
    -------
    tuple
        (conditionals, configurations) - Two separate lists of offer dictionaries.
        Each has offer_id, sender, conditions, assignments, and status fields.
    """
    conditionals = []
    configurations = []
    for agent in agents:
        # Only extract from RuleBasedClusterAgent instances that have rb_active_offers
        if not hasattr(agent, 'rb_active_offers'):
            continue

        for offer_id, offer in agent.rb_active_offers.items():
            # Skip offers made BY the human TO this agent (don't show human's own offers back to them)
            # Offer IDs contain the sender name: "offer_<timestamp>_<sender>"
            if "_Human" in offer_id:
                continue

            # Determine status based on accepted offers
            accepted_offers = getattr(agent, 'rb_accepted_offers', set())
            status = "accepted" if offer_id in accepted_offers else "pending"

            # Extract conditions
            conditions_list = []
            if hasattr(offer, 'conditions') and offer.conditions:
                for cond in offer.conditions:
                    conditions_list.append({
                        "node": cond.node,
                        "colour": cond.colour,
                        "owner": cond.owner
                    })

            # Extract assignments
            assignments_list = []
            if hasattr(offer, 'assignments') and offer.assignments:
                for assign in offer.assignments:
                    assignments_list.append({
                        "node": assign.node,
                        "colour": assign.colour
                    })

            # Get reasons for categorization and UI display
            reasons = getattr(offer, 'reasons', [])

            offer_dict = {
                "offer_id": offer_id,
                "sender": agent.name,
                "conditions": conditions_list,
                "assignments": assignments_list,
                "status": status,
                "reasons": reasons  # Include reasons so UI can check for boundary_update
            }

            # Check if this is a configuration announcement
            if "initial_configuration" in reasons:
                configurations.append(offer_dict)
            else:
                conditionals.append(offer_dict)

    return conditionals, configurations


def run_clustered_simulation(
    node_names: List[str],
    clusters: Dict[str, List[str]],
    adjacency: Dict[str, List[str]],
    owners: Dict[str, str],
    cluster_algorithms: Dict[str, str],
    cluster_message_types: Dict[str, str],
    domain: List[Any],
    max_iterations: int,
    interactive: bool,
    manual_mode: bool = False,
    human_owners: Optional[List[str]] = None,
    use_ui: bool = False,
    ui_title: str = "Human Turn",
    summariser: Optional[Callable] = None,
    output_dir: str = "./cluster_outputs",
    convergence_k: int = 2,
    stop_on_soft: bool = True,
    # Study default: never auto-end purely because the algorithm reached a
    # globally consistent colouring. Under partial observability, the
    # participant may not believe convergence. If you enable this flag, the run
    # will only terminate on hard convergence once the human has also indicated
    # satisfaction.
    stop_on_hard: bool = False,
    counterfactual_utils: bool = True,
    fixed_constraints: bool = True,
    num_fixed_nodes: int = 1,
) -> None:
    """Run a clustered DCOP simulation with the provided configuration.

    Parameters
    ----------
    node_names : list[str]
        Names of all nodes in the graph.
    clusters : dict[str, list[str]]
        Mapping from cluster (owner) names to the list of node names they
        control.
    adjacency : dict[str, list[str]]
        Adjacency map defining edges between nodes.  Each key is a
        node and its value is a list of neighbouring nodes.
    owners : dict[str, str]
        Mapping from node to the owner controlling it.  Should be
        consistent with ``clusters``.
    cluster_algorithms : dict[str, str]
        Mapping from cluster name to the algorithm used by that cluster
        (e.g., ``"greedy"``, ``"maxsum"``).
    cluster_message_types : dict[str, str]
        Mapping from cluster name to the message type used by that
        cluster (e.g., ``"cost_list"``, ``"constraints"``, ``"free_text"``).
    domain : list[Any]
        List of colours or values available to all nodes.
    max_iterations : int
        Maximum number of synchronous iterations to run.
    interactive : bool
        Whether to enable interactive prompts for human agents (not
        currently used in this clustered setup).
    manual_mode : bool, optional
        If True, the LLM communication layer will bypass API calls and
        instead use the provided summariser.
    summariser : callable, optional
        Function used in manual mode to summarise dictionary messages.
    output_dir : str, optional
        Directory in which to write logs and visualisations.
    """
    # ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    # convert adjacency dict to edge list (undirected) avoiding duplicates
    edges: List[tuple] = []
    for node, nbrs in adjacency.items():
        for nbr in nbrs:
            if (nbr, node) not in edges:
                edges.append((node, nbr))
    # instantiate global problem
    # CRITICAL: conflict_penalty must be >> max preference to ensure conflicts are always avoided
    # Preferences range from 1-3, so conflict_penalty=10.0 ensures conflicts dominate decision-making
    problem = GraphColoring(node_names, edges, domain, conflict_penalty=10.0)

    # ----------------------------
    # Fixed node constraints setup
    # ----------------------------
    # If fixed_constraints is enabled, select num_fixed_nodes internal nodes per cluster
    # and assign them fixed colors to force negotiation between clusters.
    cluster_fixed_nodes: Dict[str, Dict[str, Any]] = {}
    if fixed_constraints and num_fixed_nodes > 0 and domain:
        import random
        random.seed(42)  # Deterministic for reproducibility

        # For each cluster, find internal nodes and pick N to fix
        for owner, local_nodes in clusters.items():
            internal_nodes = [
                n for n in local_nodes
                if problem.is_internal_node(n, local_nodes)
            ]

            if internal_nodes:
                # Pick up to num_fixed_nodes random internal nodes
                num_to_fix = min(num_fixed_nodes, len(internal_nodes))
                fixed_nodes = random.sample(internal_nodes, num_to_fix)

                # Assign each fixed node a color (cycling through domain)
                fixed_dict = {}
                for i, fixed_node in enumerate(fixed_nodes):
                    # Cycle through domain colors (prefer non-first colors to create conflicts)
                    color_idx = (i + 1) % len(domain) if len(domain) > 1 else 0
                    fixed_color = domain[color_idx]
                    fixed_dict[fixed_node] = fixed_color
                    print(f"[Fixed Constraint] {owner}: node {fixed_node} fixed to {fixed_color}")

                cluster_fixed_nodes[owner] = fixed_dict
            else:
                # No fully internal nodes; use first N nodes as quasi-fixed
                if local_nodes:
                    num_to_fix = min(num_fixed_nodes, len(local_nodes))
                    fixed_nodes = local_nodes[:num_to_fix]

                    fixed_dict = {}
                    for i, fixed_node in enumerate(fixed_nodes):
                        color_idx = (i + 1) % len(domain) if len(domain) > 1 else 0
                        fixed_color = domain[color_idx]
                        fixed_dict[fixed_node] = fixed_color
                        print(f"[Fixed Constraint] {owner}: node {fixed_node} (boundary) fixed to {fixed_color}")

                    cluster_fixed_nodes[owner] = fixed_dict
                else:
                    cluster_fixed_nodes[owner] = {}

        # Validate that a solution exists with the fixed constraints
        # Use a simple greedy coloring to check feasibility
        print("[Validation] Checking if a solution exists with fixed constraints...")
        all_fixed_assignments = {}
        for owner_fixed in cluster_fixed_nodes.values():
            all_fixed_assignments.update(owner_fixed)

        # EXHAUSTIVE SEARCH to validate solvability
        # Greedy may fail even when solution exists, so we MUST use exhaustive search
        import itertools

        test_assignment = None
        free_nodes = [n for n in node_names if n not in all_fixed_assignments]

        print(f"[Validation] Searching {len(domain)**len(free_nodes)} possible colorings...")

        # Try all possible color combinations for free nodes
        found_valid_solution = False
        for combo in itertools.product(domain, repeat=len(free_nodes)):
            candidate = dict(all_fixed_assignments)
            for node, color in zip(free_nodes, combo):
                candidate[node] = color

            # Check if this is a valid coloring (no conflicts)
            penalty = problem.evaluate_assignment(candidate)
            if penalty == 0.0:
                test_assignment = candidate
                found_valid_solution = True
                print("[Validation] SUCCESS: Found a valid solution with penalty=0")
                break

        # CRITICAL CHECK: Halt if no valid solution exists
        if not found_valid_solution:
            print("\n" + "=" * 70)
            print("ERROR: PROBLEM IS UNSOLVABLE!")
            print("=" * 70)
            print("No valid graph coloring exists with the given constraints.")
            print(f"Fixed nodes: {all_fixed_assignments}")
            print(f"Domain: {domain}")
            print(f"Free nodes: {free_nodes}")
            print("\nThe problem setup is invalid. Cannot launch interface.")
            print("=" * 70)
            raise ValueError("Problem has no valid solution with penalty=0. Cannot proceed.")

        # Print the valid solution as a hint
        print("\n" + "=" * 70)
        print("HINT: Here is one valid coloring solution for this problem:")
        print("=" * 70)

        # Group by cluster for readability
        if clusters:
            for owner, local_nodes in sorted(clusters.items()):
                node_colors = {node: test_assignment[node] for node in sorted(local_nodes)}
                color_strs = [f"{node}={color}" for node, color in node_colors.items()]
                print(f"  {owner}: {', '.join(color_strs)}")
        else:
            # No clusters - just print all nodes
            for node, color in sorted(test_assignment.items()):
                print(f"  {node}={color}")

        print("=" * 70)
        print("(This is just one possible solution - there may be others!)")
        print(f"Solution penalty: {problem.evaluate_assignment(test_assignment)} (must be 0)")
        print("=" * 70 + "\n")

    if human_owners is None:
        human_owners = ["Human"]

    llm_rb_enabled = any(str(v) == 'llm_rb' for v in (cluster_message_types or {}).values())
    # create cluster agents
    agents: List[ClusterAgent] = []
    human_ui = None
    for owner, local_nodes in clusters.items():
        """Instantiate the appropriate agent for each cluster.

        If ``interactive`` is True and the owner name contains ``"Human"``,
        we instantiate a :class:`MultiNodeHumanAgent` to allow a human
        participant to control the cluster.  Otherwise we choose between
        the rule‑based baseline and the LLM‑mediated cluster agent based
        on the configured ``cluster_message_types``.
        """
        # determine the configured message type and algorithm for this cluster
        message_type = cluster_message_types.get(owner, "cost_list")
        algorithm = cluster_algorithms.get(owner, "greedy")
        # If interactive and this owner is labelled as human, use the interactive agent.
        if interactive and owner in human_owners:
            # use a pass‑through communication layer: no LLM summarisation
            comm_layer = (LLMRBCommLayer(manual=manual_mode, summariser=summariser, use_history=True) if "llm_rb" in [str(v).lower() for v in cluster_message_types.values()] else PassThroughCommLayer())
            # import locally to avoid circular import at module top level
            from agents.multi_node_human_agent import MultiNodeHumanAgent
            ui = None
            if use_ui:
                from ui.human_turn_ui import HumanTurnUI
                ui = HumanTurnUI(title=ui_title)
                human_ui = ui
            agent = MultiNodeHumanAgent(
                name=owner,
                problem=problem,
                comm_layer=comm_layer,
                local_nodes=list(local_nodes),
                owners=owners,
                initial_assignments=None,
                ui=ui,
                fixed_local_nodes=cluster_fixed_nodes.get(owner, {}),
            )
        else:
            # non‑interactive: decide between rule‑based baseline and LLM messages
            if message_type.lower() in ("rule_based","llm_rb"):
                # instantiate rule‑based baseline with pass‑through communication
                comm_layer = LLMRBCommLayer(manual=manual_mode, summariser=summariser, use_history=True) if message_type.lower()=="llm_rb" else PassThroughCommLayer()
                agent = RuleBasedClusterAgent(
                    name=owner,
                    problem=problem,
                    comm_layer=comm_layer,
                    local_nodes=list(local_nodes),
                    owners=owners,
                    algorithm=algorithm,
                    fixed_local_nodes=cluster_fixed_nodes.get(owner, {}),
                )
            else:
                # default LLM‑mediated cluster agent
                # Retain dialogue history so an LLM (when enabled) can condition on
                # prior turns. This is especially important for LLM-F, but is
                # also useful for the other LLM conditions.
                comm_layer = LLMCommLayer(manual=manual_mode, summariser=summariser, use_history=True)
                agent = ClusterAgent(
                    name=owner,
                    problem=problem,
                    comm_layer=comm_layer,
                    local_nodes=list(local_nodes),
                    owners=owners,
                    algorithm=algorithm,
                    message_type=message_type,
                    counterfactual_utils=bool(counterfactual_utils),
                    fixed_local_nodes=cluster_fixed_nodes.get(owner, {}),
                )
        agents.append(agent)

    # ----------------------------
    # Deterministic initialisation
    # ----------------------------
    # For the user study we want a known, shared starting point. Initialise
    # every node (human and agents) to the first colour in the domain.
    # This also makes early conflict states easy to interpret.
    if domain:
        default_colour = domain[0]
        for a in agents:
            if hasattr(a, "assignments"):
                try:
                    # type: ignore[attr-defined]
                    for n in getattr(a, "local_nodes", []):
                        a.assignments[n] = default_colour
                except Exception:
                    pass

        # Apply fixed node constraints after initial assignment
        if fixed_constraints:
            for a in agents:
                if hasattr(a, "assignments") and hasattr(a, "fixed_local_nodes"):
                    try:
                        for node, fixed_color in a.fixed_local_nodes.items():
                            a.assignments[node] = fixed_color
                    except Exception:
                        pass

    # Expose agents on the problem object for the experimenter debug UI.
    # This is intentionally not participant-facing.
    try:
        problem.debug_agents = agents  # type: ignore[attr-defined]
    except Exception:
        pass
    # containers for logs
    iteration_assignments: List[Dict[str, Any]] = []
    iteration_penalties: List[float] = []
    iteration_messages: List[List[tuple]] = []
    # synchronous iterations
    satisfied_streak = 0
    stop_reason: Optional[str] = None
    stop_iteration: Optional[int] = None

    # --------------------
    # Live logging setup
    # --------------------
    # Truncate existing logs at start, then append+flush each iteration. This
    # ensures partial runs still leave useful diagnostics.
    agent_log_paths = {a.name: os.path.join(output_dir, f"{a.name}_log.txt") for a in agents}
    for p in agent_log_paths.values():
        with open(p, "w", encoding="utf-8") as _f:
            _f.write("")
    comm_path = os.path.join(output_dir, "communication_log.txt")
    with open(comm_path, "w", encoding="utf-8") as _f:
        _f.write("")
    summary_path = os.path.join(output_dir, "iteration_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as _f:
        _f.write("")

    # Persist all LLM prompt/response traces (including manual/heuristic runs)
    # so non-convergence can be diagnosed post-hoc.
    llm_trace_path = os.path.join(output_dir, "llm_trace.jsonl")
    try:
        with open(llm_trace_path, "w", encoding="utf-8") as _f:
            _f.write("")
    except Exception:
        pass

    # --------------------
    # Ground Truth Analysis Log
    # --------------------
    # Generate comprehensive ground truth log showing:
    # 1. Full graph topology
    # 2. Fixed nodes for each agent
    # 3. Boundary nodes between agents
    # 4. ALL possible boundary configurations and whether agents can achieve penalty=0
    ground_truth_path = os.path.join(output_dir, "ground_truth_analysis.txt")
    try:
        with open(ground_truth_path, "w", encoding="utf-8") as gtf:
            gtf.write("=" * 80 + "\n")
            gtf.write("GROUND TRUTH ANALYSIS\n")
            gtf.write("=" * 80 + "\n\n")
            gtf.write("This file contains the ACTUAL graph structure and ALL valid solutions.\n")
            gtf.write("Compare this to agent logs to diagnose if agents are computing correctly.\n\n")

            # Section 1: Graph Structure
            gtf.write("=" * 80 + "\n")
            gtf.write("1. GRAPH STRUCTURE\n")
            gtf.write("=" * 80 + "\n\n")
            gtf.write(f"All Nodes: {sorted(node_names)}\n")
            gtf.write(f"Domain (colors): {domain}\n")
            gtf.write(f"Total Edges: {len(edges)}\n\n")

            gtf.write("Edges:\n")
            for u, v in sorted(edges):
                gtf.write(f"  {u} <-> {v}\n")
            gtf.write("\n")

            gtf.write("Node Ownership:\n")
            for node in sorted(node_names):
                owner = owners.get(node, "UNKNOWN")
                gtf.write(f"  {node}: {owner}\n")
            gtf.write("\n")

            # Section 2: Clusters and Fixed Nodes
            gtf.write("=" * 80 + "\n")
            gtf.write("2. CLUSTERS AND FIXED NODES\n")
            gtf.write("=" * 80 + "\n\n")

            for owner, local_nodes in sorted(clusters.items()):
                gtf.write(f"{owner}:\n")
                gtf.write(f"  Nodes: {sorted(local_nodes)}\n")

                fixed_dict = cluster_fixed_nodes.get(owner, {})
                if fixed_dict:
                    gtf.write(f"  Fixed Nodes: {dict(sorted(fixed_dict.items()))}\n")
                else:
                    gtf.write(f"  Fixed Nodes: None\n")
                gtf.write("\n")

            # Section 3: Boundary Analysis for each agent
            gtf.write("=" * 80 + "\n")
            gtf.write("3. BOUNDARY NODE ANALYSIS\n")
            gtf.write("=" * 80 + "\n\n")

            for agent in agents:
                if agent.name in (human_owners or []) or agent.name.lower() == "human":
                    continue  # Skip human for now

                gtf.write(f"Agent: {agent.name}\n")
                gtf.write(f"  Local Nodes: {sorted(agent.nodes)}\n")

                # Find boundary nodes (neighbors from other clusters)
                boundary_nodes = set()
                for my_node in agent.nodes:
                    for nbr in problem.get_neighbors(my_node):
                        if nbr not in agent.nodes:
                            boundary_nodes.add(nbr)

                gtf.write(f"  Boundary Nodes (neighbors from other clusters): {sorted(boundary_nodes)}\n")
                gtf.write(f"  Fixed Nodes: {dict(sorted(agent.fixed_local_nodes.items()))}\n")
                gtf.write("\n")

            # Section 4: Exhaustive Solution Analysis
            gtf.write("=" * 80 + "\n")
            gtf.write("4. EXHAUSTIVE SOLUTION ANALYSIS\n")
            gtf.write("=" * 80 + "\n\n")
            gtf.write("Testing ALL possible boundary configurations to find which ones allow penalty=0.\n\n")

            for agent in agents:
                if agent.name in (human_owners or []) or agent.name.lower() == "human":
                    continue  # Skip human

                gtf.write(f"\n{agent.name} - Exhaustive Boundary Analysis:\n")
                gtf.write("-" * 60 + "\n")

                # Find boundary nodes
                boundary_nodes = []
                for my_node in agent.nodes:
                    for nbr in problem.get_neighbors(my_node):
                        if nbr not in agent.nodes and nbr not in boundary_nodes:
                            boundary_nodes.append(nbr)
                boundary_nodes = sorted(boundary_nodes)

                if not boundary_nodes:
                    gtf.write("  No boundary nodes - agent is isolated.\n")
                    continue

                gtf.write(f"  Boundary Nodes: {boundary_nodes}\n")
                gtf.write(f"  Testing {len(domain) ** len(boundary_nodes)} combinations...\n\n")

                # Generate all combinations
                import itertools
                valid_configs = []
                invalid_configs = []

                for combo in itertools.product(domain, repeat=len(boundary_nodes)):
                    boundary_config = {boundary_nodes[i]: combo[i] for i in range(len(boundary_nodes))}

                    # Test if agent can achieve penalty=0 with this boundary
                    # Use agent's _best_local_assignment_for method
                    try:
                        best_pen, best_assign = agent._best_local_assignment_for(boundary_config)

                        if best_pen < 1e-6:
                            valid_configs.append((boundary_config, best_assign, best_pen))
                        else:
                            invalid_configs.append((boundary_config, best_assign, best_pen))
                    except Exception as e:
                        invalid_configs.append((boundary_config, {}, float('inf')))

                # Report results
                gtf.write(f"  Valid Configurations (penalty=0): {len(valid_configs)}\n")
                gtf.write(f"  Invalid Configurations (penalty>0): {len(invalid_configs)}\n\n")

                if valid_configs:
                    gtf.write("  VALID CONFIGURATIONS:\n")
                    for i, (config, assign, pen) in enumerate(valid_configs[:20], 1):  # Show first 20
                        config_str = ", ".join([f"{k}={v}" for k, v in sorted(config.items())])
                        assign_str = ", ".join([f"{k}={v}" for k, v in sorted(assign.items())])
                        gtf.write(f"    {i}. Boundary: {{{config_str}}} -> Agent assigns: {{{assign_str}}} (penalty={pen:.3f})\n")
                    if len(valid_configs) > 20:
                        gtf.write(f"    ... and {len(valid_configs) - 20} more valid configurations\n")
                    gtf.write("\n")

                if invalid_configs:
                    gtf.write("  INVALID CONFIGURATIONS (penalty > 0):\n")
                    for i, (config, assign, pen) in enumerate(invalid_configs[:10], 1):  # Show first 10
                        config_str = ", ".join([f"{k}={v}" for k, v in sorted(config.items())])
                        if assign:
                            assign_str = ", ".join([f"{k}={v}" for k, v in sorted(assign.items())])
                            gtf.write(f"    {i}. Boundary: {{{config_str}}} -> Best agent can do: {{{assign_str}}} (penalty={pen:.3f})\n")
                        else:
                            gtf.write(f"    {i}. Boundary: {{{config_str}}} -> ERROR computing assignment\n")
                    if len(invalid_configs) > 10:
                        gtf.write(f"    ... and {len(invalid_configs) - 10} more invalid configurations\n")
                    gtf.write("\n")

                # Summary of which boundary values work
                gtf.write("  BOUNDARY NODE VALUE ANALYSIS:\n")
                for bn in boundary_nodes:
                    valid_values = set()
                    for config, _, _ in valid_configs:
                        valid_values.add(config[bn])
                    if valid_values:
                        gtf.write(f"    {bn}: Can be {sorted(valid_values)} in valid configs\n")
                    else:
                        gtf.write(f"    {bn}: Never appears in valid configs (over-constrained?)\n")
                gtf.write("\n")

            gtf.write("=" * 80 + "\n")
            gtf.write("END OF GROUND TRUTH ANALYSIS\n")
            gtf.write("=" * 80 + "\n")

        print(f"[Ground Truth] Analysis saved to: {ground_truth_path}")
    except Exception as e:
        print(f"[Ground Truth] Failed to generate analysis: {e}")
        import traceback
        traceback.print_exc()

    log_cursors = {a.name: 0 for a in agents}

    def _flush_agent_logs() -> None:
        for a in agents:
            logs = a.get_logs()
            cur = log_cursors.get(a.name, 0)
            if cur < len(logs):
                with open(agent_log_paths[a.name], "a", encoding="utf-8") as f:
                    f.write("\n".join(logs[cur:]) + "\n")
                    f.flush()
                log_cursors[a.name] = len(logs)

    # --------------------
    # Async chat UI mode (participant UI)
    # --------------------
    if use_ui:
        # Run an asynchronous messaging session instead of synchronous rounds.
        # The session ends when the participant clicks "End experiment".
        try:
            from ui.human_turn_ui import HumanTurnUI
        except Exception:
            HumanTurnUI = None  # type: ignore

        human_agent = None
        for a in agents:
            if a.name in (human_owners or []) or a.name.lower() == "human":
                human_agent = a
                break
        if human_agent is not None and HumanTurnUI is not None:
            # Build visible subgraph for the human: own nodes + neighbour boundary nodes; edges only incident to human nodes.
            human_nodes = list(getattr(human_agent, "nodes", []))
            neigh_nodes = []
            for hn in human_nodes:
                for nb in problem.get_neighbors(hn):
                    if nb not in human_nodes:
                        neigh_nodes.append(nb)
            vis_nodes = sorted(set(human_nodes + neigh_nodes))
            vis_edges = []
            hset = set(human_nodes)
            for u in vis_nodes:
                for v in problem.get_neighbors(u):
                    if v in vis_nodes and ((u in hset) or (v in hset)):
                        if (v, u) not in vis_edges:
                            vis_edges.append((u, v))

            # Track separate iteration counters and wall-clock time
            start_ts = datetime.datetime.now()
            iter_counts = {a.name: 0 for a in agents}
            human_actions = 0

            # For pulling agent replies incrementally
            sent_cursor = {a.name: 0 for a in agents}

            def _now_iso():
                return datetime.datetime.now().isoformat(timespec="milliseconds")

            def _sync_neighbour_views():
                # Allow agents to see neighbour colours directly (only colours, not topology).
                global_assign = {}
                for ag in agents:
                    if hasattr(ag, "assignments") and isinstance(getattr(ag, "assignments"), dict):
                        global_assign.update(getattr(ag, "assignments"))
                # include human assignments from UI state if present
                if hasattr(ui, "_assignments"):
                    global_assign.update(getattr(ui, "_assignments"))
                for ag in agents:
                    if ag is human_agent:
                        continue
                    # boundary neighbours are any nodes adjacent to ag.nodes not owned by ag
                    beliefs = {}
                    for n in getattr(ag, "nodes", []):
                        for nb in problem.get_neighbors(n):
                            if nb not in getattr(ag, "nodes", []):
                                if nb in global_assign:
                                    beliefs[nb] = global_assign[nb]
                    setattr(ag, "neighbour_assignments", beliefs)

            name_to_agent = {getattr(a, 'name', str(idx)): a for idx, a in enumerate(agents)}

            def on_send(neigh: str, text: str) -> str:
                nonlocal human_actions, ui_iteration_counter
                # Special tokens used by the UI:
                # __INIT__: Let agent initiate dialogue (doesn't count as human action)
                # __PASS__: Human passes turn, let agent speak (doesn't count as human action)
                # __ANNOUNCE_CONFIG__: Phase transition from configure to bargain
                # __IMPOSSIBLE__: Human signals configuration is impossible
                is_special = (text in ["__INIT__", "__PASS__", "__ANNOUNCE_CONFIG__", "__IMPOSSIBLE__"])
                if not is_special:
                    human_actions += 1
                    iter_counts[str(getattr(human_agent, "name", "Human"))] += 1
                    ui_iteration_counter += 1
                # update human agent assignments from UI state
                try:
                    if hasattr(ui, "_assignments"):
                        human_agent.assignments = dict(getattr(ui, "_assignments"))
                except Exception:
                    pass

                # deliver to neighbour
                recipient = name_to_agent.get(neigh)
                if recipient is None:
                    return ""

                # refresh neighbour visibility (colours)
                _sync_neighbour_views()

                # Deliver message to agent (even for special tokens like __ANNOUNCE_CONFIG__)
                # Special tokens still need to be received by agents to trigger phase transitions
                if not is_special or text in ["__ANNOUNCE_CONFIG__", "__IMPOSSIBLE__"]:
                    msg = human_agent.send(neigh, text)
                    recipient.receive(msg)
                    with open(comm_path, "a", encoding="utf-8") as f:
                        f.write(f"{_now_iso()}\t{msg.sender}->{msg.recipient}\t{str(msg.content).replace(chr(9),' ')}\n")
                        f.flush()

                # step recipient once and capture its reply to human
                # Step recipient once and capture its reply to human.
                # For __INIT__ and __PASS__, we step without delivering a message.
                # For __ANNOUNCE_CONFIG__ and __IMPOSSIBLE__, message was delivered above and agent will respond.
                recipient.step()
                iter_counts[recipient.name] += 1
                # sync after step
                _sync_neighbour_views()

                # Extract and update conditionals and configurations in UI (for RB mode)
                if hasattr(ui, 'update_conditionals'):
                    try:
                        conditionals, configurations = _get_active_conditionals(agents)
                        ui.update_conditionals(conditionals)
                        # Also update configurations if method exists
                        if hasattr(ui, 'update_configurations'):
                            ui.update_configurations(configurations)
                    except Exception as e:
                        pass  # Silent failure - not critical

                reply_texts = []
                # pull any messages sent to human
                sent = getattr(recipient, "sent_messages", []) or []
                for m in sent:
                    if m.recipient == human_agent.name:
                        reply_texts.append(str(m.content))
                        with open(comm_path, "a", encoding="utf-8") as f:
                            f.write(f"{_now_iso()}\t{m.sender}->{m.recipient}\t{str(m.content).replace(chr(9),' ')}\n")
                            f.flush()
                # clear delivered
                recipient.sent_messages = [m for m in sent if m.recipient != human_agent.name]

                # update iteration summary with timestamp, penalty, score
                try:
                    # Build global assignment from all agents (human from UI + agents from their dicts)
                    all_assign = {}
                    for ag in agents:
                        if hasattr(ag, "assignments") and isinstance(getattr(ag, "assignments"), dict):
                            all_assign.update(getattr(ag, "assignments"))
                    if hasattr(ui, "_assignments"):
                        all_assign.update(getattr(ui, "_assignments"))
                    pen = problem.evaluate_assignment(all_assign)
                    score = problem.compute_score(all_assign) if hasattr(problem, "compute_score") else 0
                    elapsed = (datetime.datetime.now() - start_ts).total_seconds()
                    with open(summary_path, "a", encoding="utf-8") as f:
                        f.write(f"{_now_iso()}\telapsed={elapsed:.3f}\tpenalty={pen:.3f}\ttotal_score={score}\tcounts={json.dumps(iter_counts)}\n")
                        f.flush()

                    # --- Create checkpoint if valid coloring (penalty = 0) ---
                    if pen <= 1e-9:
                        checkpoint = create_checkpoint(ui_iteration_counter, all_assign, pen, score)
                        checkpoints.append(checkpoint)
                        print(f"[Checkpoint] Saved #{checkpoint['id']} at UI iteration {ui_iteration_counter} (penalty={pen:.6f})")
                        # Update problem.checkpoints reference so UI can detect it
                        setattr(problem, 'checkpoints', checkpoints)
                except Exception as e:
                    import traceback
                    print(f"[Checkpoint] Error in on_send: {e}")
                    traceback.print_exc()

                return "\n".join(reply_texts).strip()

            def on_colour_change(new_assignments: Dict[str, Any]) -> None:
                """Handle human color changes via canvas clicks - check for valid colorings."""
                nonlocal ui_iteration_counter
                # Update human agent assignments
                try:
                    human_agent.assignments = dict(new_assignments)
                except Exception:
                    pass

                # Check for valid coloring after color change
                try:
                    # Gather all assignments from all agents
                    all_assign = {}
                    for ag in agents:
                        if hasattr(ag, "assignments") and isinstance(getattr(ag, "assignments"), dict):
                            all_assign.update(getattr(ag, "assignments"))
                    # Override with current human assignments
                    all_assign.update(new_assignments)

                    # Evaluate penalty
                    pen = problem.evaluate_assignment(all_assign)
                    score = problem.compute_score(all_assign) if hasattr(problem, "compute_score") else 0

                    # Create checkpoint if valid coloring
                    if pen <= 1e-9:
                        ui_iteration_counter += 1
                        checkpoint = create_checkpoint(ui_iteration_counter, all_assign, pen, score)
                        checkpoints.append(checkpoint)
                        print(f"[Checkpoint] Saved #{checkpoint['id']} after color change (penalty={pen:.6f})")
                        setattr(problem, 'checkpoints', checkpoints)
                except Exception as e:
                    print(f"[Checkpoint] Error in on_colour_change: {e}")

            def on_end(final_assignments: dict) -> None:
                # persist final assignments from UI into human agent
                try:
                    human_agent.assignments = dict(final_assignments)
                except Exception:
                    pass

            ui = HumanTurnUI(title=ui_title)
            # mark rb mode flags if needed
            human_msg_type = cluster_message_types.get(human_agent.name, "").lower()
            ui._rb_mode = bool(human_msg_type in ("rule_based", "rb"))
            # Only structured dropdowns for pure RB mode, not LLM_RB
            structured_rb_ui = bool(human_msg_type in ("rule_based", "rb"))
            # LLM_RB gets live translation UI instead
            ui._llm_rb_mode = bool(human_msg_type == "llm_rb")
            # boundary nodes per neighbour (for RB dropdown)
            rb_boundary = {}
            for neigh in [a.name for a in agents if a is not human_agent]:
                bn=[]
                for hn in human_nodes:
                    for nb in problem.get_neighbors(hn):
                        if owners.get(nb)==neigh:
                            bn.append(hn)
                rb_boundary[neigh]=sorted(set(bn))
            ui._rb_boundary_nodes_by_neigh = rb_boundary

            # start async session (blocks)
            def _debug_text() -> str:
                try:
                    # Build a best-effort global assignment
                    all_assign = {}
                    for ag in agents:
                        if hasattr(ag, "assignments") and isinstance(getattr(ag, "assignments"), dict):
                            all_assign.update(getattr(ag, "assignments"))
                    if hasattr(ui, "_assignments"):
                        all_assign.update(getattr(ui, "_assignments"))

                    pen = problem.compute_penalty(all_assign) if hasattr(problem, "compute_penalty") else problem.evaluate_assignment(all_assign)
                    total_score = problem.compute_score(all_assign) if hasattr(problem, "compute_score") else 0

                    lines = []
                    lines.append(f"Penalty: {pen}")
                    lines.append(f"Total score: {total_score}")
                    lines.append("")
                    # Per-agent snapshots
                    pts = {"blue": 1, "green": 2, "red": 3}
                    for ag in agents:
                        nm = getattr(ag, "name", "?")
                        sat = getattr(ag, "satisfied", None)
                        asg = getattr(ag, "assignments", {})
                        local = 0
                        try:
                            nodes = getattr(ag, "nodes", [])
                            for n in nodes:
                                c = str(asg.get(n, "")).lower()
                                local += pts.get(c, 0)
                        except Exception:
                            pass
                        lines.append(f"[{nm}] satisfied={sat} local_score={local}")
                    lines.append("")
                    # Last few communication log lines (if present)
                    try:
                        with open(comm_path, "r", encoding="utf-8") as f:
                            tail = f.readlines()[-20:]
                        lines.append("--- communication_log tail ---")
                        lines.extend([ln.rstrip("\n") for ln in tail])
                    except Exception:
                        pass
                    return "\n".join(lines)
                except Exception as e:
                    return f"(debug error) {e}"

            def _get_debug_visible_graph(owner_name: str, adjacency: Dict[str, List[str]], owners: Dict[str, str]) -> Tuple[List[str], List[Tuple[str, str]]]:
                """Experimenter-visible subgraph for a given participant.

                Includes:
                - all nodes in the participant's cluster
                - all immediate neighbour nodes connected by inter-cluster edges
                - all edges internal to the cluster plus the inter-cluster edges
                """
                local = {n for n, o in owners.items() if o == owner_name}
                neigh = set()
                for u in list(local):
                    for v in adjacency.get(u, []):
                        if v not in local:
                            neigh.add(v)
                vis_nodes = sorted(local | neigh)
                vis_edges_set = set()
                for u in vis_nodes:
                    for v in adjacency.get(u, []):
                        if v in vis_nodes:
                            # keep only edges touching local nodes
                            if u in local or v in local:
                                a, b = (u, v) if str(u) <= str(v) else (v, u)
                                vis_edges_set.add((a, b))
                return vis_nodes, sorted(vis_edges_set)

            # ----------------------------
            # Initialize checkpoint system for UI mode
            # ----------------------------
            checkpoints: List[Dict[str, Any]] = []
            checkpoint_id_counter = 0
            ui_iteration_counter = 0

            def create_checkpoint(iteration: int, assignments: Dict[str, Any], penalty: float, score: float) -> Dict[str, Any]:
                """Create a checkpoint snapshot when a valid coloring is reached."""
                nonlocal checkpoint_id_counter
                checkpoint_id_counter += 1
                return {
                    "id": checkpoint_id_counter,
                    "iteration": iteration,
                    "assignments": dict(assignments),
                    "penalty": penalty,
                    "score": score,
                    "timestamp": datetime.datetime.now().isoformat(),
                }

            # Expose checkpoints to problem object so UI can access them
            setattr(problem, 'checkpoints', checkpoints)

            ui.run_async_chat(
                nodes=human_nodes,
                domain=domain,
                owners=owners,
                current_assignments=dict(human_agent.assignments),
                neighbour_owners=[a.name for a in agents if a is not human_agent],
                visible_graph=(vis_nodes, vis_edges),
                on_send=on_send,
                on_colour_change=on_colour_change,
                get_agent_satisfied_fn=lambda n: bool(getattr(name_to_agent.get(n), "satisfied", False)),
                debug_get_text_fn=_debug_text,
                debug_agents=agents,
                debug_get_visible_graph_fn=lambda owner_name: _get_debug_visible_graph(owner_name, adjacency, owners),
                fixed_nodes=getattr(human_agent, "fixed_local_nodes", {}),
                problem=problem,
                structured_rb_mode=structured_rb_ui,
                comm_layer=getattr(human_agent, "comm_layer", None),
            )
            # After UI exits, fall through to compute final output, skipping synchronous loop
            stop_reason = getattr(ui, "end_reason", "") or "human_end"
            stop_iteration = 0
            # refresh assignment dicts
            try:
                human_agent.assignments = dict(ui._assignments)
            except Exception:
                pass
            # jump to end-of-run section by setting max_iterations=0
            max_iterations = 0
        else:
            pass

    # ----------------------------
    # Checkpoint system for undo/restore
    # ----------------------------
    checkpoints: List[Dict[str, Any]] = []
    checkpoint_id_counter = 0

    def create_checkpoint(iteration: int, assignments: Dict[str, Any], penalty: float, score: float) -> Dict[str, Any]:
        """Create a checkpoint snapshot when a valid coloring is reached."""
        nonlocal checkpoint_id_counter
        checkpoint_id_counter += 1
        return {
            "id": checkpoint_id_counter,
            "iteration": iteration,
            "assignments": dict(assignments),
            "penalty": penalty,
            "score": score,
            "timestamp": datetime.datetime.now().isoformat(),
        }

    for step in range(1, max_iterations + 1):
        # Expose iteration counter to UI / human agents.
        # (GraphColoringProblem doesn't track this itself.)
        setattr(problem, "iteration", step)
        # perform step for each cluster
        for agent in agents:
            agent.step()
        # gather outgoing messages
        deliveries = []
        for agent in agents:
            deliveries += agent.sent_messages
            agent.sent_messages = []
        # record messages
        iter_msgs = []
        for msg in deliveries:
            iter_msgs.append((msg.sender, msg.recipient, msg.content))
            # deliver message to recipient
            for agent in agents:
                if agent.name == msg.recipient:
                    agent.receive(msg)
                    break
        iteration_messages.append(iter_msgs)
        # record assignments and compute global penalty
        assignments: Dict[str, Any] = {}
        for agent in agents:
            for node, val in agent.assignments.items():
                assignments[node] = val
        # Give *agents* direct access to true boundary neighbour colours (node colours only, no topology).
        try:
            human_set = set(human_owners or [])
            for _a in agents:
                if getattr(_a, 'name', None) in human_set:
                    continue
                if not hasattr(_a, 'neighbour_assignments') or getattr(_a, 'neighbour_assignments') is None:
                    _a.neighbour_assignments = {}
                for _local in getattr(_a, 'nodes', []):
                    for _nbr in adjacency.get(_local, []):
                        if owners.get(_nbr) != owners.get(_local):
                            if _nbr in assignments:
                                _a.neighbour_assignments[str(_nbr)] = assignments[_nbr]
        except Exception:
            pass

        penalty = problem.evaluate_assignment(assignments)
        iteration_assignments.append(assignments.copy())
        iteration_penalties.append(penalty)

        # Checkpoint capture: save valid colorings (penalty=0)
        if penalty <= 1e-9:  # Valid coloring (no conflicts)
            # Compute score from preferences (optional, for now use 0)
            score = 0.0  # Could compute from preferences if needed
            checkpoint = create_checkpoint(step, assignments, penalty, score)
            checkpoints.append(checkpoint)
            print(f"[Checkpoint] Saved #{checkpoint['id']} at iteration {step} (penalty={penalty:.6f})")

            # Expose checkpoints to UI via problem object
            setattr(problem, 'checkpoints', checkpoints)

        # Live log flush
        _flush_agent_logs()

        # Flush any comm-layer LLM traces incrementally (for *each* agent).
        try:
            for _a in agents:
                _cl = getattr(_a, 'comm_layer', None)
                if _cl is not None and hasattr(_cl, 'flush_debug_calls'):
                    _cl.flush_debug_calls(llm_trace_path)
        except Exception:
            pass
        # Communication log (append this iteration)
        with open(comm_path, "a", encoding="utf-8") as f:
            for sender, recipient, content in iter_msgs:
                f.write(f"Iteration {step}: {sender} -> {recipient}: {content}\n")
            f.flush()

        # Summary log (append each iteration) — includes satisfaction flags so
        # you can verify the human checkbox is being respected.
        human_ok_now = True
        agent_ok_now = True
        for a in agents:
            if human_owners is not None and getattr(a, "name", None) in human_owners:
                human_ok_now = human_ok_now and bool(getattr(a, "satisfied", False))
            else:
                agent_ok_now = agent_ok_now and bool(getattr(a, "satisfied", False))
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(
                f"Iteration {step}: penalty={penalty:.3f}; human_satisfied={human_ok_now}; agent_satisfied={agent_ok_now}; streak={satisfied_streak}/{max(1, int(convergence_k))}\n"
            )
            f.flush()

        # --------------------
        # Stopping criteria
        # --------------------
        # Hard convergence: the current global colouring has zero clashes.
        # IMPORTANT: we do not terminate solely on this signal by default.
        # If enabled, require the human to also confirm satisfaction.
        if stop_on_hard and penalty <= 1e-9 and human_ok_now:
            stop_reason = "hard_convergence_human_confirmed"
            stop_iteration = step
            break

        # Soft convergence: both human and agent(s) report "satisfied" for K
        # consecutive turns.
        if stop_on_soft:
            human_ok = True
            agent_ok = True
            for a in agents:
                if human_owners is not None and getattr(a, "name", None) in human_owners:
                    human_ok = human_ok and bool(getattr(a, "satisfied", False))
                else:
                    agent_ok = agent_ok and bool(getattr(a, "satisfied", False))

            if human_ok and agent_ok:
                satisfied_streak += 1
            else:
                satisfied_streak = 0

            if satisfied_streak >= max(1, int(convergence_k)):
                stop_reason = "soft_convergence"
                stop_iteration = step
                break

        
    # Final live-log flush and stop reason
    _flush_agent_logs()
    with open(summary_path, "a", encoding="utf-8") as f:
        if stop_reason is not None:
            f.write(f"\nStopped early at iteration {stop_iteration} due to {stop_reason}.\n")
        else:
            f.write(f"\nReached max_iterations={max_iterations}.\n")
        f.flush()
    # generate simple visualisation of the graph topology
    try:
        import matplotlib.pyplot as plt
        import math
        n = len(node_names)
        angle_step = 2 * math.pi / max(n, 1)
        positions = {name: (math.cos(i * angle_step), math.sin(i * angle_step)) for i, name in enumerate(node_names)}
        # initial topology
        plt.figure(figsize=(6, 6))
        for u, v in edges:
            x_vals = [positions[u][0], positions[v][0]]
            y_vals = [positions[u][1], positions[v][1]]
            plt.plot(x_vals, y_vals, color="black")
        for name in node_names:
            x, y = positions[name]
            plt.scatter(x, y)
            label = f"{name} ({owners.get(name, '?')})"
            plt.text(x, y + 0.05, label, ha="center")
        plt.axis('off')
        plt.title("Clustered Graph Topology")
        plt.savefig(os.path.join(output_dir, "topology.png"), bbox_inches='tight')
        plt.close()
    except Exception:
        pass
    # generate per-iteration visualisation
    try:
        import matplotlib.pyplot as plt
        colour_map = {"red": "red", "green": "green", "blue": "blue"}
        import math
        n = len(node_names)
        angle_step = 2 * math.pi / max(n, 1)
        positions = {name: (math.cos(i * angle_step), math.sin(i * angle_step)) for i, name in enumerate(node_names)}
        for idx, (assign, pen) in enumerate(zip(iteration_assignments, iteration_penalties), start=1):
            plt.figure(figsize=(6, 6))
            for u, v in edges:
                x_vals = [positions[u][0], positions[v][0]]
                y_vals = [positions[u][1], positions[v][1]]
                plt.plot(x_vals, y_vals, color="black")
            for name in node_names:
                x, y = positions[name]
                colour = colour_map.get(assign.get(name, ''), 'gray')
                plt.scatter(x, y, s=200, color=colour)
                owner_label = owners.get(name, '?')
                assign_val = assign.get(name, 'None')
                plt.text(x, y + 0.05, f"{name}\n({owner_label})\n{assign_val}", ha="center", fontsize=8)
            plt.axis('off')
            plt.title(f"Iteration {idx} (penalty {pen:.3f})")
            plt.savefig(os.path.join(output_dir, f"iteration_{idx}.png"), bbox_inches='tight')
            plt.close()
    except Exception:
        pass
    if stop_reason is not None:
        print(f"[cluster_simulation] Stopped early at iteration {stop_iteration} ({stop_reason}).")
    print(f"Clustered simulation outputs saved in {output_dir}")

    # -----------------------------
    # Participant-facing results UI
    # -----------------------------
    # If we ran with the Tkinter participant UI, show a final window with the
    # full graph and a short summary so the participant can verify the outcome.
    try:
        if use_ui and human_ui is not None and getattr(human_ui, "_root", None) is not None:
            from ui.results_window import ResultsWindow, RunSummary

            final_assign = iteration_assignments[-1] if iteration_assignments else {}
            summary = RunSummary(
                stop_reason=str(stop_reason or f"max_iterations_{max_iterations}"),
                iterations=len(iteration_penalties),
                penalties=list(iteration_penalties),
                total_messages=sum(len(m) for m in iteration_messages),
            )
            win = ResultsWindow(
                getattr(human_ui, "_root"),
                title="Results",
                nodes=list(node_names),
                edges=list(edges),
                owners=dict(owners),
                final_assignments=dict(final_assign),
                summary=summary,
                domain=list(domain),
            )
            # Block until the results window is closed, then close the main UI.
            getattr(human_ui, "_root").wait_window(win._top)  # type: ignore[attr-defined]
            try:
                getattr(human_ui, "_root").destroy()
            except Exception:
                pass
    except Exception:
        pass

    
