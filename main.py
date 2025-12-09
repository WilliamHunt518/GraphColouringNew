"""
Simple PyCharm-friendly entry point for running DCOP agent simulations.

You can tweak the CONFIG dict below instead of passing terminal args.

This calls the same runner functionality that run_simulation.py uses,
but everything is configured in one place.
"""

from typing import Dict, List, Optional, Any

from run_simulation import run_simulation, build_agent


def run_custom_simulation(
    node_names: List[str],
    agent_modes: List[str],
    adjacency: Dict[str, List[str]],
    owners: Dict[str, str],
    max_iterations: int,
    interactive: bool,
    manual_mode: bool = False,
    summariser: Optional[callable] = None,
    output_dir: str = "./outputs",
    random_pref_range: Optional[tuple] = None,
    detect_convergence: bool = False,
    multi_node_mode: bool = False,
) -> None:
    """Run a custom DCOP simulation with user-defined adjacency and owners.

    This helper constructs a ``GraphColoring`` problem from the given
    adjacency map, instantiates agents using :func:`build_agent`,
    executes the algorithm for ``max_iterations`` steps, and writes
    detailed logs and visualisations to ``output_dir``.

    By default, each node is treated as an individual agent.  If
    ``multi_node_mode`` is set to True, nodes belonging to the same
    owner (as specified in the ``owners`` mapping) are grouped
    together and controlled by a single ``MultiNodeAgent``.  In
    multi‑node mode, the ``owners`` mapping determines both the
    grouping of nodes into agents and the labelling in outputs.  When
    ``multi_node_mode`` is False (default), the mapping is purely
    cosmetic and does not influence the algorithm.
    """
    import os
    from problems.graph_coloring import GraphColoring
    import matplotlib.pyplot as plt

    # ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # convert adjacency dict to a list of undirected edges, avoiding duplicates
    edges: List[tuple] = []
    for node, nbrs in adjacency.items():
        for nbr in nbrs:
            if (nbr, node) not in edges:
                edges.append((node, nbr))

    # define a fixed colour domain
    domain = ["red", "green", "blue"]
    problem = GraphColoring(node_names, edges, domain)
    # optionally assign random personal preferences to break ties.  If
    # random_pref_range is provided as a tuple (low, high), each
    # agent's preferences for each colour are drawn uniformly from
    # [low, high], as suggested in the literature【94679395507773†L2148-L2153】.  This
    # helps break symmetries in standard Max–Sum which otherwise
    # normalises all utilities to zero when preferences are identical.
    if random_pref_range is not None:
        import random
        low, high = random_pref_range
        for node in problem.nodes:
            for val in problem.domain:
                # assign random preference weight for each colour
                problem.preferences[node][val] = random.uniform(low, high)
    agents: List[Any] = []
    if not multi_node_mode:
        # single-node agents: one agent per node
        agents = [
            build_agent(
                mode,
                name,
                problem,
                interactive,
                manual=manual_mode,
                summariser=summariser,
            )
            for name, mode in zip(node_names, agent_modes)
        ]
    else:
        # multi-node agents: one agent per owner.  Each owner has an associated
        # agent mode taken from agent_modes (length must equal number of owners).
        from agents.multi_node_agent import MultiNodeAgent
        from comm.communication_layer import LLMCommLayer, PassThroughCommLayer
        # group nodes by owner
        owners_to_nodes: Dict[str, List[str]] = {}
        for node in node_names:
            owner = owners.get(node)
            owners_to_nodes.setdefault(owner, []).append(node)
        # map provided modes to owners.  Expect len(agent_modes) == number of owners
        unique_owners = list(owners_to_nodes.keys())
        if len(agent_modes) != len(unique_owners):
            raise ValueError(
                "In multi_node_mode, the number of agent_modes must equal the number of owners"
            )
        for owner, mode in zip(unique_owners, agent_modes):
            # choose communication layer based on mode
            mode = mode.upper()
            if mode == "1Z":
                comm_layer = PassThroughCommLayer()
            else:
                # default to LLM layer for algorithmic and human modes
                comm_layer = LLMCommLayer(manual=manual_mode, summariser=summariser)
            agent = MultiNodeAgent(
                name=owner,
                problem=problem,
                comm_layer=comm_layer,
                local_nodes=owners_to_nodes[owner],
                owners=owners,
            )
            agents.append(agent)
    # containers for logs and messages
    iteration_assignments: List[Dict[str, str]] = []
    iteration_penalties: List[float] = []
    iteration_messages: List[List[tuple]] = []

    # run synchronous iterations with optional convergence detection
    # maintain last message mapping to detect convergence
    last_messages_map: Dict[tuple, Any] = {}
    stable_count = 0
    for step in range(1, max_iterations + 1):
        # each agent performs a step
        for agent in agents:
            agent.step()
        # collect and deliver messages
        deliveries: List['Message'] = []
        for agent in agents:
            deliveries += agent.sent_messages
            agent.sent_messages = []
        # record messages for this iteration
        iter_msgs: List[tuple] = []
        current_messages_map: Dict[tuple, Any] = {}
        for msg in deliveries:
            iter_msgs.append((msg.sender, msg.recipient, msg.content))
            # deliver to recipient
            for agent in agents:
                if agent.name == msg.recipient:
                    agent.receive(msg)
                    break
            # record for convergence detection: mapping by (sender, recipient)
            current_messages_map[(msg.sender, msg.recipient)] = msg.content
        iteration_messages.append(iter_msgs)
        # record assignments and penalty
        # build assignment dictionary mapping each node to its assigned colour
        assignments: Dict[str, str] = {}
        for agent in agents:
            # if the agent controls multiple nodes, update from its assignments dict
            if hasattr(agent, "nodes"):
                # MultiNodeAgent: assignments property is dict
                for node, val in getattr(agent, "assignments", {}).items():
                    assignments[node] = val
            else:
                assignments[agent.name] = agent.assignment
        penalty = problem.evaluate_assignment(assignments)
        iteration_assignments.append(assignments.copy())
        iteration_penalties.append(penalty)
        # check for convergence if enabled
        if detect_convergence:
            if current_messages_map == last_messages_map and current_messages_map:
                # messages unchanged from last iteration
                stable_count += 1
            else:
                stable_count = 0
            last_messages_map = current_messages_map
            # if messages stable for at least one consecutive iteration, stop
            if stable_count >= 1:
                # update max_iterations to break outer loop early
                # note: break out of for loop
                break

    # save visualisation of the graph topology
    # generate simple coordinates along a circle for visualization
    import math
    n = len(node_names)
    angle_step = 2 * math.pi / max(n, 1)
    positions = {name: (math.cos(i * angle_step), math.sin(i * angle_step)) for i, name in enumerate(node_names)}
    plt.figure(figsize=(6, 6))
    # draw edges
    for u, v in edges:
        x_vals = [positions[u][0], positions[v][0]]
        y_vals = [positions[u][1], positions[v][1]]
        plt.plot(x_vals, y_vals)
    # draw nodes and labels
    for name in node_names:
        x, y = positions[name]
        plt.scatter(x, y)
        label = f"{name} ({owners.get(name, '?')})"
        plt.text(x, y + 0.05, label, ha="center")
    plt.axis('off')
    plt.title("Graph Topology")
    topo_path = os.path.join(output_dir, "topology.png")
    # attempt to save the topology figure; catching errors from large image sizes
    try:
        plt.savefig(topo_path, bbox_inches='tight')
    except Exception:
        # silently ignore failures to save the topology
        pass
    plt.close()

    # write per-agent logs
    for agent in agents:
        log_path = os.path.join(output_dir, f"{agent.name}_log.txt")
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(agent.get_logs()))
    # write communication log
    comm_path = os.path.join(output_dir, "communication_log.txt")
    with open(comm_path, 'w', encoding='utf-8') as f:
        for i, msgs in enumerate(iteration_messages, start=1):
            for sender, recipient, content in msgs:
                f.write(f"Iteration {i}: {sender} -> {recipient}: {content}\n")
    # write iteration summary
    summary_path = os.path.join(output_dir, "iteration_summary.txt")
    with open(summary_path, 'w', encoding='utf-8') as f:
        actual_iters = len(iteration_assignments)
        # note if convergence was detected
        if detect_convergence and actual_iters < max_iterations:
            f.write(f"Converged after {actual_iters} iterations.\n\n")
        for i in range(actual_iters):
            f.write(f"Iteration {i+1}:\n")
            f.write(f"  Assignments: {iteration_assignments[i]}\n")
            f.write(f"  Global penalty: {iteration_penalties[i]}\n")
            if iteration_messages[i]:
                f.write("  Messages:\n")
                for sender, recipient, content in iteration_messages[i]:
                    f.write(f"    {sender} -> {recipient}: {content}\n")
            else:
                f.write("  Messages: None\n")
            f.write("\n")

    # generate a sequence of images showing the assignments over iterations
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        # mapping of domain values to actual colours for plotting
        colour_map: Dict[str, str] = {
            'red': 'red',
            'green': 'green',
            'blue': 'blue',
        }
        for idx, (assign, penalty_val) in enumerate(zip(iteration_assignments, iteration_penalties), start=1):
            plt.figure(figsize=(6, 6))
            # draw edges
            for u, v in edges:
                x_vals = [positions[u][0], positions[v][0]]
                y_vals = [positions[u][1], positions[v][1]]
                plt.plot(x_vals, y_vals, color="black")
            # draw nodes with assigned colours
            for name in node_names:
                x, y = positions[name]
                colour = colour_map.get(assign.get(name, ''), 'gray')
                plt.scatter(x, y, s=200, color=colour)
                # label includes node name, owner and assignment
                owner_label = owners.get(name, '?')
                assign_val = assign.get(name, 'None')
                plt.text(x, y + 0.05, f"{name}\n({owner_label})\n{assign_val}", ha="center", fontsize=8)
            plt.axis('off')
            plt.title(f"Iteration {idx} (penalty {penalty_val:.3f})")
            img_path = os.path.join(output_dir, f"iteration_{idx}.png")
            plt.savefig(img_path, bbox_inches='tight')
            plt.close()
    except Exception as e:
        # fail silently if plotting fails (e.g. no display)
        pass

    print(f"Outputs saved in {output_dir}")


def main() -> None:
    """Entry point for running customised DCOP simulations.

    Adjust the CONFIG dictionary below to specify nodes, modes, adjacency
    (edge structure) and an owner mapping.  Then run this script to
    execute the simulation and generate outputs in the specified
    directory.  For the original single-node-per-agent setup, leave
    ``adjacency`` empty and use ``node_names`` with ``agent_modes``.
    """
    # ------------------------------------------------------------------
    # CONFIGURATION
    # Define the nodes and modes.  Each node is an individual agent.
    # CONFIG = dict(
    #     node_names=["a", "b"],
    #     agent_modes=["1A", "1A"],
    #     owners={"a": "Alice", "b": "Bob"},
    #     adjacency={
    #         "a": ["b"],
    #         "b": ["a"],
    #     },
    #     max_iterations=5,
    #     interactive=False,
    #     output_dir="./outputs",
    #     manual_mode=False,
    #     multi_node_mode=False,
    # )

    # Define a more complex graph with 6 nodes and 2 owners,
    CONFIG = dict(node_names=["1", "2", "3", "4", "5", "6"], agent_modes=["1C", "1A"],
                  owners={"1": "Alice", "2": "Alice", "3": "Alice", "4": "Bob", "5": "Bob", "6": "Bob", },
                  adjacency={"1": ["2", "4"], "2": ["1", "3"], "3": ["2", "6"], "4": ["5", "1"], "5": ["4", "6"],
                             "6": ["5", "3"], }, max_iterations=10, interactive=False, output_dir="./outputs",
                  manual_mode=False, multi_node_mode=True, )

    # ensure lengths match: in multi-node mode, agent_modes refers to owners
    if not CONFIG.get("multi_node_mode", False):
        if len(CONFIG["node_names"]) != len(CONFIG["agent_modes"]):
            raise ValueError("node_names and agent_modes must have the same length in per-node mode")
    else:
        # multi-node mode: number of agent_modes must equal number of unique owners
        unique_owners = set(CONFIG["owners"].values())
        if len(CONFIG["agent_modes"]) != len(unique_owners):
            raise ValueError(
                "In multi_node_mode, agent_modes must specify one mode per owner"
            )
    # run the custom simulation
    # define a basic summariser function for manual mode.  This function
    # is called whenever an agent needs to summarise a mapping in
    # manual_mode.  It returns a simple descriptive string.  Users can
    # modify this function to provide custom summaries or prompt the
    # operator for input.
    def summariser(sender: str, recipient: str, mapping: dict[str, float]) -> str:
        # choose the best option based on highest score
        if not mapping:
            return "No mapping provided."
        best = max(mapping, key=mapping.get)
        # build descriptive summary
        parts = [f"{k}:{v:.3f}" for k, v in mapping.items()]
        return f"{sender} suggests {best} is best for {recipient}. Scores: " + ", ".join(parts)

    run_custom_simulation(
        node_names=CONFIG["node_names"],
        agent_modes=CONFIG["agent_modes"],
        adjacency=CONFIG["adjacency"],
        owners=CONFIG["owners"],
        max_iterations=CONFIG["max_iterations"],
        interactive=CONFIG["interactive"],
        output_dir=CONFIG["output_dir"],
        random_pref_range=(-0.1, 0.1),
        manual_mode=CONFIG.get("manual_mode", False),
        summariser=summariser,
        detect_convergence=True,
        multi_node_mode=CONFIG.get("multi_node_mode", False),
    )


if __name__ == "__main__":
    main()
