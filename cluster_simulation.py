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
                nonlocal human_actions
                # Special token used by the UI to let an agent initiate the dialogue.
                # This should not count as a human action.
                is_init = (text == "__INIT__")
                if not is_init:
                    human_actions += 1
                    iter_counts[str(getattr(human_agent, "name", "Human"))] += 1
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

                if not is_init:
                    msg = human_agent.send(neigh, text)
                    recipient.receive(msg)
                    with open(comm_path, "a", encoding="utf-8") as f:
                        f.write(f"{_now_iso()}\t{msg.sender}->{msg.recipient}\t{str(msg.content).replace(chr(9),' ')}\n")
                        f.flush()

                # step recipient once and capture its reply to human
                # Step recipient once and capture its reply to human.
                # For init, we step without delivering a human message.
                recipient.step()
                iter_counts[recipient.name] += 1
                # sync after step
                _sync_neighbour_views()

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
                    pen = problem.compute_penalty(all_assign)
                    score = problem.compute_score(all_assign) if hasattr(problem, "compute_score") else 0
                    elapsed = (datetime.datetime.now() - start_ts).total_seconds()
                    with open(iter_summary_path, "a", encoding="utf-8") as f:
                        f.write(f"{_now_iso()}\telapsed={elapsed:.3f}\tpenalty={pen:.3f}\ttotal_score={score}\tcounts={json.dumps(iter_counts)}\n")
                        f.flush()
                except Exception:
                    pass

                return "\n".join(reply_texts).strip()

            def on_end(final_assignments: dict) -> None:
                # persist final assignments from UI into human agent
                try:
                    human_agent.assignments = dict(final_assignments)
                except Exception:
                    pass

            ui = HumanTurnUI(title=ui_title)
            # mark rb mode flags if needed
            ui._rb_mode = bool(cluster_message_types.get(human_agent.name, "").lower() == "rule_based" or cluster_message_types.get(human_agent.name, "").lower() == "rb")
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

            ui.run_async_chat(
                nodes=human_nodes,
                domain=domain,
                owners=owners,
                current_assignments=dict(human_agent.assignments),
                neighbour_owners=[a.name for a in agents if a is not human_agent],
                visible_graph=(vis_nodes, vis_edges),
                on_send=on_send,
                get_agent_satisfied_fn=lambda n: bool(getattr(name_to_agent.get(n), "satisfied", False)),
                debug_get_text_fn=_debug_text,
                debug_agents=agents,
                debug_get_visible_graph_fn=lambda owner_name: _get_debug_visible_graph(owner_name, adjacency, owners),
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

    
