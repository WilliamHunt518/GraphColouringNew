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
from typing import Dict, List, Any, Optional, Callable

# Import modules using absolute package names.  When running this
# module directly or importing it after adding ``code`` to ``sys.path``
# the packages ``problems``, ``comm`` and ``agents`` resolve to the
# corresponding subpackages within the ``code`` directory.
from problems.graph_coloring import GraphColoring
from comm.communication_layer import LLMCommLayer, PassThroughCommLayer
from agents.cluster_agent import ClusterAgent
from agents.rule_based_cluster_agent import RuleBasedClusterAgent


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
    problem = GraphColoring(node_names, edges, domain)

    if human_owners is None:
        human_owners = ["Human"]
    # create cluster agents
    agents: List[ClusterAgent] = []
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
            comm_layer = PassThroughCommLayer()
            # import locally to avoid circular import at module top level
            from agents.multi_node_human_agent import MultiNodeHumanAgent
            ui = None
            if use_ui:
                from ui.human_turn_ui import HumanTurnUI
                ui = HumanTurnUI(title=ui_title)
            agent = MultiNodeHumanAgent(
                name=owner,
                problem=problem,
                comm_layer=comm_layer,
                local_nodes=list(local_nodes),
                owners=owners,
                initial_assignments=None,
                ui=ui,
            )
        else:
            # non‑interactive: decide between rule‑based baseline and LLM messages
            if message_type.lower() == "rule_based":
                # instantiate rule‑based baseline with pass‑through communication
                comm_layer = PassThroughCommLayer()
                agent = RuleBasedClusterAgent(
                    name=owner,
                    problem=problem,
                    comm_layer=comm_layer,
                    local_nodes=list(local_nodes),
                    owners=owners,
                    algorithm=algorithm,
                )
            else:
                # default LLM‑mediated cluster agent
                comm_layer = LLMCommLayer(manual=manual_mode, summariser=summariser)
                agent = ClusterAgent(
                    name=owner,
                    problem=problem,
                    comm_layer=comm_layer,
                    local_nodes=list(local_nodes),
                    owners=owners,
                    algorithm=algorithm,
                    message_type=message_type,
                )
        agents.append(agent)
    # containers for logs
    iteration_assignments: List[Dict[str, Any]] = []
    iteration_penalties: List[float] = []
    iteration_messages: List[List[tuple]] = []
    # synchronous iterations
    for step in range(1, max_iterations + 1):
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
        penalty = problem.evaluate_assignment(assignments)
        iteration_assignments.append(assignments.copy())
        iteration_penalties.append(penalty)
    # write logs and summary
    # per-cluster logs
    for agent in agents:
        log_path = os.path.join(output_dir, f"{agent.name}_log.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(agent.get_logs()))
    # communication log
    comm_path = os.path.join(output_dir, "communication_log.txt")
    with open(comm_path, "w", encoding="utf-8") as f:
        for i, msgs in enumerate(iteration_messages, start=1):
            for sender, recipient, content in msgs:
                f.write(f"Iteration {i}: {sender} -> {recipient}: {content}\n")
    # iteration summary
    summary_path = os.path.join(output_dir, "iteration_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        for i, (assign, pen) in enumerate(zip(iteration_assignments, iteration_penalties), start=1):
            f.write(f"Iteration {i}:\n")
            f.write(f"  Assignments: {assign}\n")
            f.write(f"  Global penalty: {pen}\n")
            if iteration_messages[i-1]:
                f.write("  Messages:\n")
                for sender, recipient, content in iteration_messages[i-1]:
                    f.write(f"    {sender} -> {recipient}: {content}\n")
            else:
                f.write("  Messages: None\n")
            f.write("\n")
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
    print(f"Clustered simulation outputs saved in {output_dir}")
