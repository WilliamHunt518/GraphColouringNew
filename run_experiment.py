"""Main entry point for the constraint visualisation study.

Run from the repository root with:

    python run_experiment.py --condition C1 --use-ui

Six conditions:
    C1  : User-Centric Formulaic — logical consequence expressions
    C2  : Agent-Centric Formulaic — feasible colour domain sets
    C3  : Human Domain Formulaic — valid colours for human's own nodes
    C4  : User-Centric Natural Language (LLM-summarised)
    C5  : Agent-Centric Natural Language (LLM-summarised)
    C6  : Human Domain Natural Language (LLM-summarised)

The human directly manipulates node colours by clicking; agents are passive
constraint analysers.  Chat panes are replaced with real-time constraint panels.
"""

from __future__ import annotations

import os
from pathlib import Path


# -----------------
# CONFIGURE HERE
# -----------------

CONDITION = "C1"   # one of: "C1", "C2", "C3", "C4", "C5", "C6"
USE_UI = True
USE_LLM = False    # True => call LLM for NL summaries in C4/C5/C6
FIXED_CONSTRAINTS = True
NUM_FIXED_NODES = 1


def _check_solvable_explicit(node_names, adjacency, explicit_fixed, domain):
    """Verify a valid 3-colouring exists with a given set of explicit fixed nodes.

    Uses backtracking (not brute-force product) so it scales to larger graphs.
    Raises ValueError if unsolvable.
    """
    adj_sets = {n: set(adjacency[n]) for n in node_names}
    free = [n for n in node_names if n not in explicit_fixed]
    assignment = dict(explicit_fixed)

    def backtrack(idx: int) -> bool:
        if idx == len(free):
            return True
        node = free[idx]
        for colour in domain:
            if all(assignment.get(nb) != colour for nb in adj_sets[node]):
                assignment[node] = colour
                if backtrack(idx + 1):
                    return True
                del assignment[node]
        return False

    if backtrack(0):
        return  # solvable – all good

    fixed_str = ", ".join(f"{n}={c}" for n, c in sorted(explicit_fixed.items()))
    raise ValueError(
        f"Graph preset is UNSOLVABLE with explicit fixed nodes: {fixed_str}"
    )


def _check_solvable_with_domains(node_names, adjacency, node_domains, domain):
    """Verify a valid colouring exists respecting per-node domain restrictions.

    Uses backtracking.  Raises ValueError if unsolvable.
    """
    adj_sets = {n: set(adjacency[n]) for n in node_names}
    assignment: dict = {}

    def _domain_for(node):
        return node_domains.get(node, domain)

    def backtrack(idx: int) -> bool:
        if idx == len(node_names):
            return True
        node = node_names[idx]
        for colour in _domain_for(node):
            if all(assignment.get(nb) != colour for nb in adj_sets[node]):
                assignment[node] = colour
                if backtrack(idx + 1):
                    return True
                del assignment[node]
        return False

    if backtrack(0):
        return
    raise ValueError(
        "Graph with complex constraints is UNSOLVABLE.  "
        "Check domain restrictions or graph topology."
    )


def _check_solvable(node_names, adjacency, clusters, domain, num_fixed_nodes):
    """Simulate the EXACT fixed-node selection (seed=42) used by cluster_simulation.py
    and verify a valid 3-colouring exists.  Raises ValueError with a diagnostic
    message if unsolvable so topology bugs are caught at import time.
    """
    import random, itertools

    random.seed(42)
    fixed: dict = {}
    for owner, nodes in clusters.items():
        internal = [n for n in nodes if all(nb in nodes for nb in adjacency[n])]
        num = min(num_fixed_nodes, len(internal)) if internal else 0
        if num == 0:
            continue
        chosen = random.sample(internal, num)
        for i, n in enumerate(chosen):
            fixed[n] = domain[(i + 1) % len(domain)]

    free = [n for n in node_names if n not in fixed]
    for combo in itertools.product(domain, repeat=len(free)):
        candidate = dict(fixed)
        for n, c in zip(free, combo):
            candidate[n] = c
        if all(candidate[u] != candidate[v]
               for u, nbrs in adjacency.items()
               for v in nbrs if u < v):
            return  # solvable – all good

    fixed_str = ", ".join(f"{n}={c}" for n, c in sorted(fixed.items()))
    raise ValueError(
        f"'hard' graph preset is UNSOLVABLE with seed-42 fixed nodes "
        f"({num_fixed_nodes} per cluster): {fixed_str}.  "
        f"Adjust the topology or chord structure."
    )


def _apply_isomorphic_shift(base_result: tuple, node_shift: int, colour_cycle: int) -> tuple:
    """Return an isomorphically equivalent variant of a _build_topology result.

    node_shift   – rotate each cluster's 1-based node labels by this offset
                   (e.g. shift=2 on 8 nodes: h1→h3, h7→h1, h8→h2)
    colour_cycle – steps to rotate the canonical colour order [blue, green, red]:
                     0 = identity
                     1 = blue→green, green→red, red→blue
                     2 = blue→red,   green→blue, red→green
    The graph structure is identical; only node labels and colour names change,
    so the problem is fully isomorphic to the original.
    """
    node_names, clusters, adjacency, owners, explicit_fixed, node_domains = base_result

    COLOURS = ["blue", "green", "red"]
    colour_map = {COLOURS[i]: COLOURS[(i + colour_cycle) % 3] for i in range(3)}

    rename: dict = {}
    for cname, nodes in clusters.items():
        if not nodes:
            continue
        prefix = nodes[0][0]  # "h", "a", "b", "c", …
        n = len(nodes)
        for i, node in enumerate(nodes):
            rename[node] = f"{prefix}{(i + node_shift) % n + 1}"

    def _r(nd: str) -> str:
        return rename.get(nd, nd)

    def _c(col: str) -> str:
        return colour_map.get(col.lower(), col)

    return (
        [_r(nd) for nd in node_names],
        {cname: [_r(nd) for nd in nodes] for cname, nodes in clusters.items()},
        {_r(u): [_r(v) for v in nbrs] for u, nbrs in adjacency.items()},
        {_r(nd): owner for nd, owner in owners.items()},
        {cname: {_r(nd): _c(col) for nd, col in fixed.items()}
         for cname, fixed in explicit_fixed.items()},
        {_r(nd): [_c(c) for c in dom] for nd, dom in node_domains.items()}
        if node_domains else None,
    )


def _build_topology(graph_preset: str, num_fixed_nodes: int = 2) -> tuple:
    """Return (node_names, clusters, adjacency, owners, explicit_fixed, node_domains) for the given preset.

    Presets
    -------
    "easy"         – 5-node-per-cluster topology; seed-42 fixed-node selection.
    "medium"       – Same 5-node topology but with pre-designed explicit fixed
                     nodes (h3=red, a3=green, b3=blue) that create interesting
                     cross-cluster constraint tension.
    "hard"         – 6-node-per-cluster topology; 6-cycle + antipodal chord;
                     seed-42 fixed-node selection.
    "expert"       – Same 6-node topology but with pre-designed explicit fixed
                     nodes (h3=green, h6=red, a1=blue, a4=red, b2=green,
                     b5=red) for tighter constraints.
    "tight2"       – 5-node topology (same as easy) with agent-focused fixed
                     nodes h3=red, a1=green, a3=red, b1=blue, b3=green.
                     Forces most of each agent cluster; 4 valid solutions.
    "tight3"       – 5-node topology with two human fixed nodes (h2=red,
                     h3=green) plus agent internals a1=blue, a3=green,
                     b1=green, b3=red.  Cascades force h1, h5 uniquely; 4
                     valid solutions.
    "tight4"       – 5-node topology; h4=red (human boundary) plus agent
                     internals a1=red, a3=blue, b3=blue, b5=green.  Most
                     agent nodes forced; only 2 valid solutions.
    "cx_easy_plus" – 5-node complex-constraint topology with h3 connected to
                     BOTH agents (h3--a1 and h3--b3) as extra cross-cluster
                     edges.  No single-colour fixed nodes; all domains 2-colour.
                     Harder than cx_easy due to h3 being a cross-cluster hub.
    "cx_hard_free" – 6-node complex-constraint topology (same as cx_hard) but
                     with NO single-colour fixed nodes.  The four cx_hard fixed
                     nodes (h3, h6, a4, b2) are each relaxed to a 2-colour
                     domain, removing the immediate narrowing they provided.

    ``explicit_fixed`` is ``None`` for presets that use seed-42 selection
    (easy/hard) and a per-cluster dict ``{owner: {node: colour}}`` for
    presets with pre-designed constraints (medium/expert).
    """
    preset = graph_preset.lower()
    domain = ["red", "green", "blue"]
    explicit_fixed = None  # default: no pre-designed fixed constraints
    node_domains: dict | None = None  # default: no per-node domain restrictions
    agent3_nodes: list = []  # populated only by 4-cluster (trio) presets

    if preset in ("easy", "medium"):
        human_nodes = ["h1", "h2", "h3", "h4", "h5"]
        agent1_nodes = ["a1", "a2", "a3", "a4", "a5"]
        agent2_nodes = ["b1", "b2", "b3", "b4", "b5"]

        adjacency = {
            # Human cluster (5-cycle + chord h2-h5)
            "h1": ["h2", "h5"],
            "h2": ["h1", "h3", "h5"],
            "h3": ["h2", "h4"],
            "h4": ["h3", "h5"],
            "h5": ["h1", "h2", "h4"],
            # Agent1 cluster (5-cycle + chord a2-a5)
            "a1": ["a2", "a5"],
            "a2": ["a1", "a3", "a5"],
            "a3": ["a2", "a4"],
            "a4": ["a3", "a5"],
            "a5": ["a1", "a2", "a4"],
            # Agent2 cluster (5-cycle + chord b2-b5)
            "b1": ["b2", "b5"],
            "b2": ["b1", "b3", "b5"],
            "b3": ["b2", "b4"],
            "b4": ["b3", "b5"],
            "b5": ["b1", "b2", "b4"],
        }

        # Cross-cluster edges
        # Human <-> Agent1: h1--a2, h4--a4, h4--a5  (one-to-many from h4)
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h4"].append("a4"); adjacency["a4"].append("h4")
        adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
        # Human <-> Agent2: h2--b2, h5--b2  (many-to-one into b2)
        adjacency["h2"].append("b2"); adjacency["b2"].append("h2")
        adjacency["h5"].append("b2"); adjacency["b2"].append("h5")

        if preset == "medium":
            # Pre-designed fixed constraints creating interesting cross-cluster tension.
            # h3=red makes h2 and h4 non-red; a3=green constrains a2/a4; b3=blue
            # constrains b2 which is also constrained by h2 and h5 choices.
            # Verified solution: h1=green,h2=blue,h3=red,h4=green,h5=red;
            #   a1=green,a2=red,a3=green,a4=red,a5=blue;
            #   b1=red,b2=green,b3=blue,b4=red,b5=blue
            explicit_fixed = {
                "Human": {"h3": "red"},
                "Agent1": {"a3": "green"},
                "Agent2": {"b3": "blue"},
            }
            node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
            all_fixed_tmp: dict = {}
            for d in explicit_fixed.values():
                all_fixed_tmp.update(d)
            _check_solvable_explicit(node_names_tmp, adjacency, all_fixed_tmp, domain)

    elif preset in ("tight", "dense", "dense_tight", "tight2", "tight3", "tight4"):
        # 5 nodes per cluster — same base topology as easy/medium (5-cycle + chord h2-h5),
        # but with pre-designed explicit fixed constraints that create tighter problems.
        # "dense" and "dense_tight" add two extra cross-cluster edges (h3–a1, h1–b5).
        human_nodes = ["h1", "h2", "h3", "h4", "h5"]
        agent1_nodes = ["a1", "a2", "a3", "a4", "a5"]
        agent2_nodes = ["b1", "b2", "b3", "b4", "b5"]

        adjacency = {
            # Human cluster (5-cycle + chord h2-h5)
            "h1": ["h2", "h5"],
            "h2": ["h1", "h3", "h5"],
            "h3": ["h2", "h4"],
            "h4": ["h3", "h5"],
            "h5": ["h1", "h2", "h4"],
            # Agent1 cluster (5-cycle + chord a2-a5)
            "a1": ["a2", "a5"],
            "a2": ["a1", "a3", "a5"],
            "a3": ["a2", "a4"],
            "a4": ["a3", "a5"],
            "a5": ["a1", "a2", "a4"],
            # Agent2 cluster (5-cycle + chord b2-b5)
            "b1": ["b2", "b5"],
            "b2": ["b1", "b3", "b5"],
            "b3": ["b2", "b4"],
            "b4": ["b3", "b5"],
            "b5": ["b1", "b2", "b4"],
        }

        # Standard cross-cluster edges (same as easy/medium)
        # Human <-> Agent1: h1--a2, h4--a4, h4--a5
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h4"].append("a4"); adjacency["a4"].append("h4")
        adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
        # Human <-> Agent2: h2--b2, h5--b2
        adjacency["h2"].append("b2"); adjacency["b2"].append("h2")
        adjacency["h5"].append("b2"); adjacency["b2"].append("h5")

        if preset in ("dense", "dense_tight"):
            # Extra cross-cluster edges: h3–a1 (Agent1 tighter), h1–b5 (Agent2 tighter)
            adjacency["h3"].append("a1"); adjacency["a1"].append("h3")
            adjacency["h1"].append("b5"); adjacency["b5"].append("h1")

        if preset == "tight":
            # 2 fixed per agent cluster (up from 1).
            # a3=blue + a1=red: forces a2=green, a5=blue uniquely; a4 depends on h4.
            # b3=red + b5=green: forces b2=blue, b4=blue, b1=red uniquely.
            # Human has exactly 2 valid colorings (h4=red or h4=green).
            # Verified solutions (2 total):
            #   h1=blue,h2=red,h3=blue,h4=red,h5=green  → a4=green
            #   h1=blue,h2=green,h3=blue,h4=green,h5=red → a4=red
            explicit_fixed = {
                "Human":  {"h3": "blue"},
                "Agent1": {"a3": "blue", "a1": "red"},
                "Agent2": {"b3": "red", "b5": "green"},
            }
        elif preset == "dense":
            # 2 fixed per agent cluster. Extra edges h3–a1 and h1–b5 add cross tension.
            # a3=blue + a1=red: h3–a1 cross-edge satisfied (a1=red ≠ h3=green).
            # b3=red + b5=green: h1–b5 cross-edge satisfied (b5=green ≠ h1=blue).
            # Verified solution: h1=blue,h2=red,h3=green,h4=red,h5=green;
            #   a1=red,a2=green,a3=blue,a4=green,a5=blue;
            #   b1=red,b2=blue,b3=red,b4=blue,b5=green
            explicit_fixed = {
                "Human":  {"h3": "green"},
                "Agent1": {"a3": "blue", "a1": "red"},
                "Agent2": {"b3": "red", "b5": "green"},
            }
        elif preset == "dense_tight":
            # Dense topology + 2 fixed per agent cluster.
            # Combines extra cross-edges with tight agent constraints.
            # b5=green forces h1 ≠ green; h2/h5–b2 cross-edges force b2=blue uniquely.
            # Verified solution:
            #   h1=blue,h2=red,h3=green,h4=red,h5=green
            #   a1=red,a2=green,a3=blue,a4=green,a5=blue
            #   b1=red,b2=blue,b3=red,b4=blue,b5=green
            explicit_fixed = {
                "Human":  {"h3": "green"},
                "Agent1": {"a3": "blue", "a1": "red"},
                "Agent2": {"b3": "red", "b5": "green"},
            }
        elif preset == "tight2":
            # Standard easy topology.  Different colour assignment from "tight":
            # a1=green + a3=red forces a2=blue and a5=red uniquely in Agent1.
            # b1=blue + b3=green forces b2=red and b5=green uniquely in Agent2.
            # Human has h3=red; only a4 (Agent1) and b4 (Agent2) remain free,
            # each determined by the adjacent human node.  4 valid solutions.
            # Verified solution (h2=green, h5=blue, b4=red):
            #   h1=red, h2=green, h3=red, h4=green, h5=blue
            #   a1=green, a2=blue, a3=red, a4=blue, a5=red
            #   b1=blue, b2=red, b3=green, b4=red, b5=green
            explicit_fixed = {
                "Human":  {"h3": "red"},
                "Agent1": {"a1": "green", "a3": "red"},
                "Agent2": {"b1": "blue", "b3": "green"},
            }
        elif preset == "tight3":
            # Standard easy topology.  Human has two fixed nodes (h2=red, h3=green).
            # Agent1: a1=blue + a3=green forces a2=red and a5=green uniquely.
            # Agent2: b1=green + b3=red forces b2=blue and b5=red uniquely.
            # Cross-edges cascade to force h1=blue and h5=green in all solutions.
            # Only h4 (Agent1 a4) and b4 remain free.  4 valid solutions.
            # Verified solution (h4=red, b4=green):
            #   h1=blue, h2=red, h3=green, h4=red, h5=green
            #   a1=blue, a2=red, a3=green, a4=blue, a5=green
            #   b1=green, b2=blue, b3=red, b4=green, b5=red
            explicit_fixed = {
                "Human":  {"h2": "red", "h3": "green"},
                "Agent1": {"a1": "blue", "a3": "green"},
                "Agent2": {"b1": "green", "b3": "red"},
            }
        else:  # tight4
            # Standard easy topology.  h4=red fixes the human boundary node that
            # connects to both a4 and a5.  Agent1: a1=red + a3=blue forces a2=green,
            # a5=blue, and a4=green (via h4) uniquely — entire Agent1 determined.
            # Agent2: b3=blue + b5=green forces b4=red, b2=red, b1=blue uniquely.
            # Only the two unconstrained human nodes h2/h5 vary (2 valid solutions).
            # Verified solution (h2=green, h5=blue):
            #   h1=red, h2=green, h3=blue, h4=red, h5=blue
            #   a1=red, a2=green, a3=blue, a4=green, a5=blue
            #   b1=blue, b2=red, b3=blue, b4=red, b5=green
            explicit_fixed = {
                "Human":  {"h4": "red"},
                "Agent1": {"a1": "red", "a3": "blue"},
                "Agent2": {"b3": "blue", "b5": "green"},
            }

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        all_fixed_tmp: dict = {}
        for d in explicit_fixed.values():
            all_fixed_tmp.update(d)
        _check_solvable_explicit(node_names_tmp, adjacency, all_fixed_tmp, domain)

    elif preset in ("hard", "expert"):
        # 6 nodes per cluster, 2 cross-edges per agent pair.
        human_nodes = ["h1", "h2", "h3", "h4", "h5", "h6"]
        agent1_nodes = ["a1", "a2", "a3", "a4", "a5", "a6"]
        agent2_nodes = ["b1", "b2", "b3", "b4", "b5", "b6"]

        adjacency = {
            # Human cluster: 6-cycle + antipodal chord h3-h6
            "h1": ["h2", "h6"],
            "h2": ["h1", "h3"],
            "h3": ["h2", "h4", "h6"],
            "h4": ["h3", "h5"],
            "h5": ["h4", "h6"],
            "h6": ["h5", "h1", "h3"],
            # Agent1 cluster: 6-cycle + antipodal chord a3-a6
            "a1": ["a2", "a6"],
            "a2": ["a1", "a3"],
            "a3": ["a2", "a4", "a6"],
            "a4": ["a3", "a5"],
            "a5": ["a4", "a6"],
            "a6": ["a5", "a1", "a3"],
            # Agent2 cluster: 6-cycle + antipodal chord b3-b6
            "b1": ["b2", "b6"],
            "b2": ["b1", "b3"],
            "b3": ["b2", "b4", "b6"],
            "b4": ["b3", "b5"],
            "b5": ["b4", "b6"],
            "b6": ["b5", "b1", "b3"],
        }

        # Cross-cluster edges (2 per agent pair — symmetric one-to-one)
        # Human <-> Agent1: h1--a2, h4--a5
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
        # Human <-> Agent2: h2--b3, h5--b6
        adjacency["h2"].append("b3"); adjacency["b3"].append("h2")
        adjacency["h5"].append("b6"); adjacency["b6"].append("h5")

        if preset == "hard":
            # Verify solvability with the actual fixed-node selection used at runtime
            node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
            clusters_tmp = {"Human": human_nodes, "Agent1": agent1_nodes, "Agent2": agent2_nodes}
            _check_solvable(node_names_tmp, adjacency, clusters_tmp, domain, num_fixed_nodes)
        else:  # expert
            # Pre-designed fixed constraints for a tighter problem.
            # Human: h3=green + h6=red (chord pair — both fixed, different colours).
            # Agent1: a1=blue (low-degree), a4=red (internal).
            # Agent2: b2=green, b5=red (both internal; b2 adj to b3/b6 in-cluster).
            # Verified solution:
            #   h1=blue,h2=red,h3=green,h4=red,h5=blue,h6=red;
            #   a1=blue,a2=red,a3=green,a4=red,a5=green,a6=red;
            #   b1=red,b2=green,b3=blue,b4=green,b5=red,b6=green
            explicit_fixed = {
                "Human": {"h3": "green", "h6": "red"},
                "Agent1": {"a1": "blue", "a4": "red"},
                "Agent2": {"b2": "green", "b5": "red"},
            }
            node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
            all_fixed_tmp = {}
            for d in explicit_fixed.values():
                all_fixed_tmp.update(d)
            _check_solvable_explicit(node_names_tmp, adjacency, all_fixed_tmp, domain)

    elif preset == "super":
        # 8 nodes per cluster — hardest preset.
        # Topology: 8-cycle + 1 antipodal chord (x1–x5) per cluster.
        # Cross-edges: h1–a2, h5–a5 (Human↔Agent1), h3–b3, h7–b7 (Human↔Agent2).
        # Fixed: 2 per human cluster + 2 per agent cluster (6 total).
        # Verified solution:
        #   Human:  h1=blue, h2=green, h3=red,  h4=blue, h5=green, h6=red, h7=blue, h8=red
        #   Agent1: a1=blue, a2=red,   a3=blue, a4=green, a5=red, a6=blue, a7=green, a8=red
        #   Agent2: b1=red,  b2=green, b3=blue, b4=red,   b5=green, b6=blue, b7=red, b8=green
        human_nodes  = [f"h{i}" for i in range(1, 9)]
        agent1_nodes = [f"a{i}" for i in range(1, 9)]
        agent2_nodes = [f"b{i}" for i in range(1, 9)]

        def _eight_cycle_with_chord(prefix: str) -> dict:
            ns = [f"{prefix}{i}" for i in range(1, 9)]
            adj: dict = {n: [] for n in ns}
            for i in range(8):
                a, b = ns[i], ns[(i + 1) % 8]
                adj[a].append(b)
                adj[b].append(a)
            # Antipodal chord: node 1 – node 5  (indices 0 and 4)
            adj[ns[0]].append(ns[4])
            adj[ns[4]].append(ns[0])
            return adj

        adjacency = {}
        for prefix in ("h", "a", "b"):
            adjacency.update(_eight_cycle_with_chord(prefix))

        # Cross-cluster edges
        # Human ↔ Agent1: h1–a2, h5–a5
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h5"].append("a5"); adjacency["a5"].append("h5")
        # Human ↔ Agent2: h3–b3, h7–b7
        adjacency["h3"].append("b3"); adjacency["b3"].append("h3")
        adjacency["h7"].append("b7"); adjacency["b7"].append("h7")

        explicit_fixed = {
            "Human":  {"h3": "red",   "h7": "blue"},
            "Agent1": {"a4": "green", "a8": "red"},
            "Agent2": {"b2": "green", "b6": "blue"},
        }

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        all_fixed_tmp: dict = {}
        for d in explicit_fixed.values():
            all_fixed_tmp.update(d)
        _check_solvable_explicit(node_names_tmp, adjacency, all_fixed_tmp, domain)

    elif preset in ("cx_easy", "cx_medium", "cx_hard"):
        # Complex-constraint presets: per-node colour domain restrictions.
        # Every node is restricted to 1–3 colours; 1-colour nodes are "fixed".
        # Topology is the same 5-node base (cx_easy/cx_medium) or 6-node (cx_hard).

        if preset == "cx_hard":
            # --- 6-node per cluster (mirrors "hard" topology) ---
            human_nodes  = ["h1","h2","h3","h4","h5","h6"]
            agent1_nodes = ["a1","a2","a3","a4","a5","a6"]
            agent2_nodes = ["b1","b2","b3","b4","b5","b6"]

            adjacency = {
                "h1":["h2","h6"], "h2":["h1","h3"], "h3":["h2","h4","h6"],
                "h4":["h3","h5"], "h5":["h4","h6"], "h6":["h5","h1","h3"],
                "a1":["a2","a6"], "a2":["a1","a3"], "a3":["a2","a4","a6"],
                "a4":["a3","a5"], "a5":["a4","a6"], "a6":["a5","a1","a3"],
                "b1":["b2","b6"], "b2":["b1","b3"], "b3":["b2","b4","b6"],
                "b4":["b3","b5"], "b5":["b4","b6"], "b6":["b5","b1","b3"],
            }
            adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
            adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
            adjacency["h2"].append("b3"); adjacency["b3"].append("h2")
            adjacency["h5"].append("b6"); adjacency["b6"].append("h5")

            # Per-node domain restrictions (verified solution:
            #   h1=blue,h2=red,h3=green,h4=red,h5=blue,h6=red;
            #   a1=blue,a2=red,a3=green,a4=red,a5=green,a6=red;
            #   b1=red,b2=green,b3=blue,b4=green,b5=red,b6=green)
            node_domains = {
                "h1":["blue","red"],   "h2":["red","green"],
                "h3":["green"],        "h4":["red","blue"],
                "h5":["blue","green"], "h6":["red"],
                "a1":["blue","green"], "a2":["red","blue"],
                "a3":["green","red"],  "a4":["red"],
                "a5":["green","blue"], "a6":["red","blue"],
                "b1":["red","blue"],   "b2":["green"],
                "b3":["blue","red"],   "b4":["green","blue"],
                "b5":["red","green"],  "b6":["green","red"],
            }
            explicit_fixed = {
                "Human":  {"h3":"green","h6":"red"},
                "Agent1": {"a4":"red"},
                "Agent2": {"b2":"green"},
            }

        else:
            # --- 5-node per cluster (mirrors "easy" topology) ---
            human_nodes  = ["h1","h2","h3","h4","h5"]
            agent1_nodes = ["a1","a2","a3","a4","a5"]
            agent2_nodes = ["b1","b2","b3","b4","b5"]

            adjacency = {
                "h1":["h2","h5"], "h2":["h1","h3","h5"],
                "h3":["h2","h4"], "h4":["h3","h5"], "h5":["h1","h2","h4"],
                "a1":["a2","a5"], "a2":["a1","a3","a5"],
                "a3":["a2","a4"], "a4":["a3","a5"], "a5":["a1","a2","a4"],
                "b1":["b2","b5"], "b2":["b1","b3","b5"],
                "b3":["b2","b4"], "b4":["b3","b5"], "b5":["b1","b2","b4"],
            }
            adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
            adjacency["h4"].append("a4"); adjacency["a4"].append("h4")
            adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
            adjacency["h2"].append("b2"); adjacency["b2"].append("h2")
            adjacency["h5"].append("b2"); adjacency["b2"].append("h5")

            if preset == "cx_easy":
                # Moderate restrictions — several solutions remain.
                # Verified solution:
                #   h1=red,h2=blue,h3=red,h4=blue,h5=green;
                #   a1=blue,a2=green,a3=blue,a4=green,a5=red;
                #   b1=green,b2=red,b3=blue,b4=red,b5=blue
                node_domains = {
                    "h1":["red","green"],  "h2":["blue","red"],
                    "h4":["blue","green"], "h5":["red","green"],
                    "a1":["blue","red"],   "a2":["green","blue"],
                    "a4":["green","red"],  "a5":["red","green"],
                    "b2":["red","blue"],
                    "b4":["red","blue"],   "b5":["blue","green"],
                }
                explicit_fixed = {"Human":{},"Agent1":{},"Agent2":{}}

            else:  # cx_medium
                # Tighter restrictions with three fixed nodes.
                # Verified solution:
                #   h1=red,h2=blue,h3=red,h4=blue,h5=green;
                #   a1=blue,a2=green,a3=blue,a4=green,a5=red;
                #   b1=green,b2=red,b3=blue,b4=red,b5=blue
                node_domains = {
                    "h1":["red","green"],  "h2":["blue","red"],
                    "h3":["red"],          "h4":["blue","green"],
                    "h5":["red","green"],
                    "a1":["blue","green"], "a2":["green","blue"],
                    "a3":["blue"],         "a4":["green","red"],
                    "a5":["red","green"],
                    "b1":["green","blue"], "b2":["red"],
                    "b3":["blue","red"],   "b4":["red","blue"],
                    "b5":["blue","green"],
                }
                explicit_fixed = {
                    "Human":  {"h3":"red"},
                    "Agent1": {"a3":"blue"},
                    "Agent2": {"b2":"red"},
                }

        # Verify solvability
        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_easy_plus":
        # 5-node topology (identical to cx_easy/cx_medium base) but with two extra
        # cross-cluster edges from h3 — the node that had NO cross-cluster connections
        # in the standard easy layout.  h3 now connects to BOTH agents (h3--a1, h3--b3),
        # making it a genuine coordination bottleneck on the human side.
        #
        # All nodes have exactly 2-colour domains; no node is fixed to 1 colour.
        # This makes the problem harder than cx_easy (more cross-cluster coupling) while
        # still having no single forced choices to lean on.
        #
        # Verified solution:
        #   h1=red,  h2=blue, h3=red,  h4=blue, h5=green
        #   a1=blue, a2=green,a3=blue, a4=green,a5=red
        #   b1=green,b2=red,  b3=blue, b4=red,  b5=blue
        human_nodes  = ["h1","h2","h3","h4","h5"]
        agent1_nodes = ["a1","a2","a3","a4","a5"]
        agent2_nodes = ["b1","b2","b3","b4","b5"]

        adjacency = {
            "h1":["h2","h5"], "h2":["h1","h3","h5"],
            "h3":["h2","h4"], "h4":["h3","h5"], "h5":["h1","h2","h4"],
            "a1":["a2","a5"], "a2":["a1","a3","a5"],
            "a3":["a2","a4"], "a4":["a3","a5"], "a5":["a1","a2","a4"],
            "b1":["b2","b5"], "b2":["b1","b3","b5"],
            "b3":["b2","b4"], "b4":["b3","b5"], "b5":["b1","b2","b4"],
        }
        # Standard cross-cluster edges (same as easy)
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h4"].append("a4"); adjacency["a4"].append("h4")
        adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
        adjacency["h2"].append("b2"); adjacency["b2"].append("h2")
        adjacency["h5"].append("b2"); adjacency["b2"].append("h5")
        # NEW: h3 connected to both agents (was previously isolated cross-cluster)
        adjacency["h3"].append("a1"); adjacency["a1"].append("h3")
        adjacency["h3"].append("b3"); adjacency["b3"].append("h3")

        node_domains = {
            "h1":["red","green"],  "h2":["blue","red"],
            "h3":["red","green"],  "h4":["blue","green"],  "h5":["red","green"],
            "a1":["blue","red"],   "a2":["green","blue"],
            "a3":["blue","red"],   "a4":["green","red"],   "a5":["red","green"],
            "b1":["green","red"],  "b2":["red","blue"],
            "b3":["blue","green"], "b4":["red","blue"],    "b5":["blue","green"],
        }
        explicit_fixed = {"Human":{},"Agent1":{},"Agent2":{}}

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_hard_free":
        # 6-node topology identical to cx_hard, but with NO single-colour fixed nodes.
        # The four nodes that cx_hard fixes to 1 colour (h3, h6, a4, b2) are each given
        # a 2-colour domain instead.  Every other node keeps its cx_hard 2-colour domain.
        #
        # This is harder than cx_easy/cx_medium (larger graph, more internal structure)
        # and harder than cx_easy_plus (6 nodes per cluster instead of 5), but without
        # the immediate narrowing that single-colour fixed nodes provide.
        #
        # Verified solution (same as cx_hard):
        #   h1=blue,h2=red, h3=green,h4=red, h5=blue,h6=red
        #   a1=blue,a2=red, a3=green,a4=red, a5=green,a6=red
        #   b1=red, b2=green,b3=blue,b4=green,b5=red, b6=green
        human_nodes  = ["h1","h2","h3","h4","h5","h6"]
        agent1_nodes = ["a1","a2","a3","a4","a5","a6"]
        agent2_nodes = ["b1","b2","b3","b4","b5","b6"]

        adjacency = {
            "h1":["h2","h6"], "h2":["h1","h3"], "h3":["h2","h4","h6"],
            "h4":["h3","h5"], "h5":["h4","h6"], "h6":["h5","h1","h3"],
            "a1":["a2","a6"], "a2":["a1","a3"], "a3":["a2","a4","a6"],
            "a4":["a3","a5"], "a5":["a4","a6"], "a6":["a5","a1","a3"],
            "b1":["b2","b6"], "b2":["b1","b3"], "b3":["b2","b4","b6"],
            "b4":["b3","b5"], "b5":["b4","b6"], "b6":["b5","b1","b3"],
        }
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
        adjacency["h2"].append("b3"); adjacency["b3"].append("h2")
        adjacency["h5"].append("b6"); adjacency["b6"].append("h5")

        # Same as cx_hard but h3/h6/a4/b2 expanded from 1 colour to 2.
        node_domains = {
            "h1":["blue","red"],   "h2":["red","green"],
            "h3":["green","blue"], "h4":["red","blue"],
            "h5":["blue","green"], "h6":["red","green"],
            "a1":["blue","green"], "a2":["red","blue"],
            "a3":["green","red"],  "a4":["red","green"],
            "a5":["green","blue"], "a6":["red","blue"],
            "b1":["red","blue"],   "b2":["green","red"],
            "b3":["blue","red"],   "b4":["green","blue"],
            "b5":["red","green"],  "b6":["green","red"],
        }
        explicit_fixed = {"Human":{},"Agent1":{},"Agent2":{}}

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_expert":
        # 6-node per cluster — same internal topology as cx_hard (6-cycle + chord x3–x6),
        # but with 6 cross-cluster edges instead of 4.  EVERY human node is directly
        # constrained by at least one agent (vs 2 unconstrained nodes in cx_hard/cx_hard_free).
        #
        # Cross-edges:  h1–a2, h4–a5, h3–a1 (new)  for Human↔Agent1
        #               h2–b3, h5–b6, h6–b1 (new)  for Human↔Agent2
        #
        # Design intent: the user has no "safe" node to start with — every move
        # requires reasoning about what the agents must do.  Tight 2-colour domains
        # create long forced cascades once any single node is resolved:
        #   h1=blue → h2=red(forced) → h3=green(forced) → h4=red(forced) → h5=blue(forced)
        #             h6=red(forced) → and all of Agent1+Agent2 cascade from cross-edges.
        #
        # Verified solution:
        #   h1=blue, h2=red, h3=green, h4=red, h5=blue, h6=red
        #   a1=blue, a2=red, a3=green, a4=red, a5=blue, a6=red
        #   b1=blue, b2=red, b3=green, b4=red, b5=blue, b6=red
        human_nodes  = ["h1","h2","h3","h4","h5","h6"]
        agent1_nodes = ["a1","a2","a3","a4","a5","a6"]
        agent2_nodes = ["b1","b2","b3","b4","b5","b6"]

        adjacency = {
            "h1":["h2","h6"], "h2":["h1","h3"], "h3":["h2","h4","h6"],
            "h4":["h3","h5"], "h5":["h4","h6"], "h6":["h5","h1","h3"],
            "a1":["a2","a6"], "a2":["a1","a3"], "a3":["a2","a4","a6"],
            "a4":["a3","a5"], "a5":["a4","a6"], "a6":["a5","a1","a3"],
            "b1":["b2","b6"], "b2":["b1","b3"], "b3":["b2","b4","b6"],
            "b4":["b3","b5"], "b5":["b4","b6"], "b6":["b5","b1","b3"],
        }
        # Standard edges
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
        adjacency["h2"].append("b3"); adjacency["b3"].append("h2")
        adjacency["h5"].append("b6"); adjacency["b6"].append("h5")
        # New edges — cover h3 and h6 so all human nodes are cross-constrained
        adjacency["h3"].append("a1"); adjacency["a1"].append("h3")
        adjacency["h6"].append("b1"); adjacency["b1"].append("h6")

        node_domains = {
            # h1=blue: wrong=green; h2 domain traps blue (h1–h2 direct conflict)
            "h1":["blue","green"],  "h2":["red","blue"],
            # h3: trapped by h2+h6 both red (chord); wrong=red creates double conflict
            "h3":["green","red"],   "h4":["red","green"],
            # h5: both neighbours (h4,h6) are red; wrong=red = immediate double conflict
            "h5":["blue","red"],    "h6":["red","blue"],
            # Agent1: a1 trapped by h3 cross-edge; a5 trapped by h4 cross-edge
            "a1":["blue","green"],  "a2":["red","blue"],
            "a3":["green","red"],   "a4":["red","green"],
            "a5":["blue","red"],    "a6":["red","blue"],
            # Agent2: b1 trapped by h6 cross-edge; b6 trapped by h5 cross-edge
            "b1":["blue","red"],    "b2":["red","blue"],
            "b3":["green","blue"],  "b4":["red","green"],
            "b5":["blue","red"],    "b6":["red","blue"],
        }
        explicit_fixed = {"Human":{},"Agent1":{},"Agent2":{}}

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_gauntlet":
        # 6-node per cluster — 6 cross-cluster edges where h2 and h5 are each constrained
        # by BOTH agents simultaneously.  h3 and h6 have no direct cross-edges but are
        # tightly coupled to h2/h5 internally.
        #
        # Cross-edges:  h1–a2, h2–a3 (new), h4–a5, h5–a6 (new)  for Human↔Agent1
        #               h2–b3, h5–b6                              for Human↔Agent2
        #
        # Design intent:
        #   h2 is constrained by Agent1 (a3) AND Agent2 (b3) simultaneously.
        #   h5 is constrained by Agent1 (a6) AND Agent2 (b6) simultaneously.
        #   The user cannot safely assign h2 or h5 until they know what BOTH agents
        #   intend to do — forcing genuine bilateral coordination before any move.
        #
        # Ultra-tight domain design: a3 and b3 both green in the target solution,
        # so h2 ≠ green from both sides → h2 = red (doubly forced).
        # Similarly a6 and b6 both red → h5 ≠ red from both sides → h5 = blue.
        #
        # Verified solution (one of 60):
        #   h1=blue, h2=red, h3=green, h4=red, h5=blue, h6=red
        #   a1=blue, a2=red, a3=green, a4=red, a5=blue, a6=red
        #   b1=green,b2=blue,b3=green, b4=red, b5=blue, b6=red
        human_nodes  = ["h1","h2","h3","h4","h5","h6"]
        agent1_nodes = ["a1","a2","a3","a4","a5","a6"]
        agent2_nodes = ["b1","b2","b3","b4","b5","b6"]

        adjacency = {
            "h1":["h2","h6"], "h2":["h1","h3"], "h3":["h2","h4","h6"],
            "h4":["h3","h5"], "h5":["h4","h6"], "h6":["h5","h1","h3"],
            "a1":["a2","a6"], "a2":["a1","a3"], "a3":["a2","a4","a6"],
            "a4":["a3","a5"], "a5":["a4","a6"], "a6":["a5","a1","a3"],
            "b1":["b2","b6"], "b2":["b1","b3"], "b3":["b2","b4","b6"],
            "b4":["b3","b5"], "b5":["b4","b6"], "b6":["b5","b1","b3"],
        }
        # Human↔Agent1: h1–a2, h2–a3 (h2 gets its first agent constraint here), h4–a5, h5–a6
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h2"].append("a3"); adjacency["a3"].append("h2")
        adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
        adjacency["h5"].append("a6"); adjacency["a6"].append("h5")
        # Human↔Agent2: h2–b3 (h2 now doubly constrained), h5–b6 (h5 now doubly constrained)
        adjacency["h2"].append("b3"); adjacency["b3"].append("h2")
        adjacency["h5"].append("b6"); adjacency["b6"].append("h5")

        # h2 domain [red,green]: a3=green → h2≠green → h2=red (forced by Agent1)
        #                        b3=green → h2≠green → h2=red (forced by Agent2)
        #                        Both agents independently force h2=red.
        # h5 domain [blue,red]:  a6=red  → h5≠red  → h5=blue (forced by Agent1)
        #                        b6=red  → h5≠red  → h5=blue (forced by Agent2)
        node_domains = {
            "h1":["blue","green"],  "h2":["red","green"],
            "h3":["green","red"],   "h4":["red","green"],
            "h5":["blue","red"],    "h6":["red","blue"],
            # Agent1: a3=green forces h2; a6=red forces h5
            "a1":["blue","red"],    "a2":["red","blue"],
            "a3":["green","blue"],  "a4":["red","green"],
            "a5":["blue","green"],  "a6":["red","blue"],
            # Agent2: b3=green forces h2; b6=red forces h5
            "b1":["red","green"],   "b2":["blue","red"],
            "b3":["green","red"],   "b4":["red","blue"],
            "b5":["blue","green"],  "b6":["red","green"],
        }
        explicit_fixed = {"Human":{},"Agent1":{},"Agent2":{}}

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_super":
        # 8-node per cluster — combines the size of the "super" topology with
        # per-node domain restrictions.  This is the largest and most structurally
        # complex preset.
        #
        # Topology per cluster: 8-cycle + antipodal chord (x1–x5).
        # Cross-edges: h1–a2, h5–a5  (Human↔Agent1)
        #              h3–b3, h7–b7  (Human↔Agent2)
        #
        # Design intent: the 8-node cycle creates longer deduction chains than
        # the 6-node version.  Every domain is 2-colour and aligned so that
        # knowing any one cross-boundary value cascades through 5–6 nodes before
        # reaching a free choice.  Unlike cx_expert/gauntlet, the human cluster
        # has no doubly-constrained nodes — but the sheer chain length (8 nodes
        # per cluster) means mistakes propagate further before they manifest.
        #
        # Verified solution:
        #   h: blue, red, green, blue, red, green, blue, red
        #   a: red,  green, blue, red,  green, blue, red,  green
        #   b: green, blue, red,  green, blue, red,  green, blue
        human_nodes  = [f"h{i}" for i in range(1, 9)]
        agent1_nodes = [f"a{i}" for i in range(1, 9)]
        agent2_nodes = [f"b{i}" for i in range(1, 9)]

        def _eight_cycle_chord(prefix: str) -> dict:
            ns = [f"{prefix}{i}" for i in range(1, 9)]
            adj: dict = {n: [] for n in ns}
            for i in range(8):
                a_n, b_n = ns[i], ns[(i + 1) % 8]
                adj[a_n].append(b_n)
                adj[b_n].append(a_n)
            # Antipodal chord: node 1 – node 5 (indices 0 and 4)
            adj[ns[0]].append(ns[4])
            adj[ns[4]].append(ns[0])
            return adj

        adjacency = {}
        for pfx in ("h", "a", "b"):
            adjacency.update(_eight_cycle_chord(pfx))

        # Cross-cluster edges (same as "super" simple-constraint preset)
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h5"].append("a5"); adjacency["a5"].append("h5")
        adjacency["h3"].append("b3"); adjacency["b3"].append("h3")
        adjacency["h7"].append("b7"); adjacency["b7"].append("h7")

        # Tight 2-colour domains.  Rotating pattern per cluster:
        #   h: B R G B R G B R  (blue=1,4,7; red=2,5,8; green=3,6)
        #   a: R G B R G B R G  (shifted +1)
        #   b: G B R G B R G B  (shifted +2)
        # Wrong option for each node is the "next colour in the wheel" — locally
        # plausible but creates a conflict 2–3 hops away via adjacency chains.
        node_domains = {
            "h1":["blue","red"],    "h2":["red","green"],
            "h3":["green","blue"],  "h4":["blue","green"],
            "h5":["red","blue"],    "h6":["green","red"],
            "h7":["blue","green"],  "h8":["red","blue"],
            "a1":["red","blue"],    "a2":["green","red"],
            "a3":["blue","green"],  "a4":["red","blue"],
            "a5":["green","blue"],  "a6":["blue","red"],
            "a7":["red","green"],   "a8":["green","blue"],
            "b1":["green","red"],   "b2":["blue","green"],
            "b3":["red","blue"],    "b4":["green","red"],
            "b5":["blue","red"],    "b6":["red","green"],
            "b7":["green","blue"],  "b8":["blue","green"],
        }
        explicit_fixed = {"Human":{},"Agent1":{},"Agent2":{}}

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset in ("trio", "trio_tight"):
        # 4-cluster topology: Human + Agent1 + Agent2 + Agent3 (5 nodes each).
        # All clusters use the same 5-cycle + chord (x2–x5) internal structure as
        # the easy/tight presets.
        #
        # Cross-cluster edges  (deliberately few; total 6 cross edges):
        #   Human ↔ Agent1:  h1–a2, h4–a4
        #   Human ↔ Agent2:  h2–b2, h5–b2
        #   Human ↔ Agent3:  h4–c1, h3–c3
        #
        # h4 is the only human node connected to TWO agent clusters (Agent1 via
        # a4 and Agent3 via c1), making it the key coordination bottleneck.
        #
        # Fixed agent nodes – heavy (2 per agent cluster) vs 0–1 human fixed.
        # Agent fixing forces most agent nodes, leaving a4 and c4 dependent on
        # human choices only late in the solve, creating backtracking pressure.
        #
        # Fixed: a1=red, a3=blue  → forces a2=green, a5=blue; a4 depends on h4
        #        b3=green, b5=red → forces b4=blue, b2=blue, b1=green
        #        c1=blue, c3=red  → forces c2=green, c5=red; c4 free
        #        Human: none (trio) or h5=green (trio_tight)
        #
        # "trio" cross-edge effects on human:
        #   h1≠green (a2=green), h2≠blue (b2=blue), h5≠blue (b2=blue),
        #   h4≠blue (c1=blue), h3≠red (c3=red)
        # This forces {h2,h5}={red,green}; h4∈{red,green}; h1∈{red,blue}.
        # h1 is FORCED to blue by internal adjacency (any other choice creates
        # an impossible assignment for the chord-connected h2+h5 pair), but
        # this is not immediately obvious — the human must try h1=red or
        # h1=green first and trace the contradiction.  6 valid solutions.
        #
        # "trio_tight" adds h5=green which cascades:
        #   h2=red (forced by chord+b2), h4=red (forced by h5+c1), h1=blue (forced).
        # Only h3 (2 options) and c4 (2 options) remain free.  4 valid solutions.
        #
        # Verified solution for both ("trio" h2=red,h5=green branch; "trio_tight"):
        #   h1=blue, h2=red, h3=green, h4=red, h5=green
        #   a1=red,  a2=green, a3=blue, a4=green, a5=blue
        #   b1=green, b2=blue, b3=green, b4=blue, b5=red
        #   c1=blue, c2=green, c3=red,  c4=green, c5=red

        human_nodes  = ["h1", "h2", "h3", "h4", "h5"]
        agent1_nodes = ["a1", "a2", "a3", "a4", "a5"]
        agent2_nodes = ["b1", "b2", "b3", "b4", "b5"]
        agent3_nodes = ["c1", "c2", "c3", "c4", "c5"]

        def _five_cycle_chord(prefix: str) -> dict:
            ns = [f"{prefix}{i}" for i in range(1, 6)]
            adj: dict = {n: [] for n in ns}
            for i in range(5):
                a_n, b_n = ns[i], ns[(i + 1) % 5]
                adj[a_n].append(b_n)
                adj[b_n].append(a_n)
            # Chord: node 2 – node 5 (indices 1 and 4)
            adj[ns[1]].append(ns[4])
            adj[ns[4]].append(ns[1])
            return adj

        adjacency = {}
        for pfx in ("h", "a", "b", "c"):
            adjacency.update(_five_cycle_chord(pfx))

        # Human ↔ Agent1
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h4"].append("a4"); adjacency["a4"].append("h4")
        # Human ↔ Agent2
        adjacency["h2"].append("b2"); adjacency["b2"].append("h2")
        adjacency["h5"].append("b2"); adjacency["b2"].append("h5")
        # Human ↔ Agent3  (h4 is now cross-linked to BOTH Agent1 and Agent3)
        adjacency["h4"].append("c1"); adjacency["c1"].append("h4")
        adjacency["h3"].append("c3"); adjacency["c3"].append("h3")

        human_fixed: dict = {}
        if preset == "trio_tight":
            # Fix h5=green: cascades h2=red (chord+b2), h4=red (h5+c1), h1=blue.
            # Only h3 and c4 remain free → 4 valid solutions.
            human_fixed = {"h5": "green"}

        explicit_fixed = {
            "Human":  human_fixed,
            "Agent1": {"a1": "red", "a3": "blue"},
            "Agent2": {"b3": "green", "b5": "red"},
            "Agent3": {"c1": "blue", "c3": "red"},
        }

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes + agent3_nodes
        all_fixed_tmp: dict = {}
        for d in explicit_fixed.values():
            all_fixed_tmp.update(d)
        _check_solvable_explicit(node_names_tmp, adjacency, all_fixed_tmp, domain)

    elif preset in ("trio_cx", "trio_tight_cx"):
        # 4-cluster topology identical to trio/trio_tight, but using per-node
        # colour-domain restrictions (cx style) instead of all-or-nothing fixed nodes.
        #
        # The key design difference from trio:
        #   - Agent2's b3/b5 are relaxed from fixed (1 colour) to 2-colour domains.
        #   - Agent3's c3 is relaxed from fixed to 2-colour.
        #   - Several "naturally constrained" nodes get explicit 2-colour domains
        #     (they were already limited by adjacency, but making it visible helps).
        #   - Two human nodes (h1, h4) get 2-colour domains reflecting their
        #     cross-cluster constraints — early choices look free, but the
        #     combination bites late.
        #
        # trio_tight_cx additionally fixes h5=green (same trigger as trio_tight).
        #
        # Same cross-cluster edges as trio:
        #   h1–a2, h4–a4  (Human ↔ Agent1)
        #   h2–b2, h5–b2  (Human ↔ Agent2)
        #   h4–c1, h3–c3  (Human ↔ Agent3; h4 doubly constrained)
        #
        # Verified solution (same as trio):
        #   h1=blue, h2=red, h3=green, h4=red, h5=green
        #   a1=red,  a2=green, a3=blue, a4=green, a5=blue
        #   b1=green, b2=blue, b3=green, b4=blue, b5=red
        #   c1=blue, c2=green, c3=red,  c4=green, c5=red

        human_nodes  = ["h1", "h2", "h3", "h4", "h5"]
        agent1_nodes = ["a1", "a2", "a3", "a4", "a5"]
        agent2_nodes = ["b1", "b2", "b3", "b4", "b5"]
        agent3_nodes = ["c1", "c2", "c3", "c4", "c5"]

        def _five_cycle_chord_cx(prefix: str) -> dict:
            ns = [f"{prefix}{i}" for i in range(1, 6)]
            adj: dict = {n: [] for n in ns}
            for i in range(5):
                a_n, b_n = ns[i], ns[(i + 1) % 5]
                adj[a_n].append(b_n)
                adj[b_n].append(a_n)
            adj[ns[1]].append(ns[4])
            adj[ns[4]].append(ns[1])
            return adj

        adjacency = {}
        for pfx in ("h", "a", "b", "c"):
            adjacency.update(_five_cycle_chord_cx(pfx))

        # Human ↔ Agent1
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h4"].append("a4"); adjacency["a4"].append("h4")
        # Human ↔ Agent2
        adjacency["h2"].append("b2"); adjacency["b2"].append("h2")
        adjacency["h5"].append("b2"); adjacency["b2"].append("h5")
        # Human ↔ Agent3
        adjacency["h4"].append("c1"); adjacency["c1"].append("h4")
        adjacency["h3"].append("c3"); adjacency["c3"].append("h3")

        # Per-node domain restrictions.
        # Nodes absent from this dict keep the full 3-colour domain.
        # Human: 2-colour hints that reflect cross-edge realities without fixing.
        #   h1 can't be green (adj a2=green), so offer [blue,red] — the human
        #   will find that red also fails, making blue the late discovery.
        #   h4 can't be blue (adj c1=blue), so [red,green].
        # Agent1: a1 fixed red; a3,a5 restricted (adjacency already excludes 1 colour).
        # Agent2: b3,b5 each get 2 options (relaxed from trio's fixed — Agent2 is no
        #   longer immediately fully determined, so early choices feel freer).
        # Agent3: c1 fixed blue; c3 relaxed to [red,green] so h3 isn't trivially forced.
        node_domains = {
            # Human (lightly restricted)
            "h1": ["blue", "red"],    # green excluded (adj a2 which must be green)
            "h4": ["red", "green"],   # blue excluded (adj c1=blue)
            # Agent1
            "a1": ["red"],            # fixed
            "a2": ["green", "blue"],  # adj a1=red → can't be red
            "a3": ["blue", "green"],  # adj a2 → 2 options
            "a4": ["red", "green"],   # adj a3 (blue/green) → blue excluded
            "a5": ["blue", "green"],  # adj a1=red → can't be red
            # Agent2 (relaxed — 2-colour domains instead of fixed)
            "b2": ["blue", "red"],    # adj h2,h5 (must avoid their colours)
            "b3": ["green", "red"],   # was fixed green in trio; now 2-colour
            "b4": ["blue", "red"],    # adj b3,b5
            "b5": ["red", "blue"],    # was fixed red in trio; now 2-colour
            # Agent3
            "c1": ["blue"],           # fixed
            "c2": ["green", "red"],   # adj c1=blue → can't be blue
            "c3": ["red", "green"],   # was fixed red in trio; now 2-colour
            "c4": ["green", "blue"],  # adj c3,c5 → red excluded
            "c5": ["red", "blue"],    # adj c1=blue,c2 → green excluded
        }

        if preset == "trio_tight_cx":
            # Fix h5=green (same trigger as trio_tight): cascade forces h2,h4,h1.
            node_domains["h5"] = ["green"]
            node_domains["h2"] = ["red", "green"]  # blue excluded by b2
            node_domains["h3"] = ["green", "blue"]  # red excluded by c3 cross-edge
            human_fixed = {"h5": "green"}
        else:
            node_domains["h2"] = ["red", "green"]   # blue excluded by b2
            node_domains["h3"] = ["green", "blue"]  # red excluded by c3 cross-edge
            node_domains["h5"] = ["red", "green"]   # blue excluded by b2
            human_fixed = {}

        explicit_fixed = {
            "Human":  human_fixed,
            "Agent1": {"a1": "red"},
            "Agent2": {},
            "Agent3": {"c1": "blue"},
        }

        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes + agent3_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_easy_8":
        # ── Easy 8-node testing preset: 2 agents, lighter cx constraints ──
        # Topology: agent clusters use 8-cycle + 4 antipodal chords {x1–x5, x2–x6, x3–x7, x4–x8}.
        # Human cluster uses 8-cycle + modified chords {h1–h5, h2–h6, h3–h7, h4–h1}:
        #   h4–h1 replaces the antipodal h4–h8, making h1 a hub (degree 6) and h8 low-degree (2).
        #
        # Cross-edges (7 total):
        #   h1–a2, h5–a5, h6–a2  (Human↔Agent1; a2 shared between h1 and h6)
        #   h1–b1, h3–b3, h5–b5, h7–b7  (Human↔Agent2)
        # h1/h5 face both agents; h6→a2 is the only shared agent boundary node.
        #
        # Constraints (~50% of nodes — 12/24 — have 2-colour domains; no fixed nodes):
        #   Human (4/8): h1=[blue,red]  h2=[red,green]  h4=[red,green]  h5=[green,red]
        #   Agent1 (4/8): a1=[blue,red]  a2=[green,red]  a5=[red,blue]  a6=[blue,red]
        #   Agent2 (4/8): b1=[green,red]  b3=[red,blue]  b5=[red,blue]  b7=[blue,green]
        #
        # Verified solution:
        #   h: blue, red,   green, red,   green, blue, red,   green
        #   a: blue, green, blue,  green, red,   blue, green, red
        #   b: green,blue,  red,   green, blue,  red,  blue,  red
        human_nodes  = [f"h{i}" for i in range(1, 9)]
        agent1_nodes = [f"a{i}" for i in range(1, 9)]
        agent2_nodes = [f"b{i}" for i in range(1, 9)]

        def _mk_8cyc_antipodal(prefix: str) -> dict:
            ns = [f"{prefix}{i}" for i in range(1, 9)]
            adj: dict = {n: [] for n in ns}
            for i in range(8):
                a_n, b_n = ns[i], ns[(i + 1) % 8]
                adj[a_n].append(b_n); adj[b_n].append(a_n)
            for i in range(4):
                adj[ns[i]].append(ns[i + 4]); adj[ns[i + 4]].append(ns[i])
            return adj

        adjacency = {}
        for pfx in ("a", "b"):
            adjacency.update(_mk_8cyc_antipodal(pfx))

        h_ns = [f"h{i}" for i in range(1, 9)]
        adjacency.update({n: [] for n in h_ns})
        for i in range(8):
            u, v = h_ns[i], h_ns[(i + 1) % 8]
            adjacency[u].append(v); adjacency[v].append(u)
        for chord in [("h1", "h5"), ("h2", "h6"), ("h3", "h7"), ("h4", "h1")]:
            adjacency[chord[0]].append(chord[1]); adjacency[chord[1]].append(chord[0])

        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h5"].append("a5"); adjacency["a5"].append("h5")
        adjacency["h6"].append("a2"); adjacency["a2"].append("h6")
        adjacency["h1"].append("b1"); adjacency["b1"].append("h1")
        adjacency["h3"].append("b3"); adjacency["b3"].append("h3")
        adjacency["h5"].append("b5"); adjacency["b5"].append("h5")
        adjacency["h7"].append("b7"); adjacency["b7"].append("h7")

        node_domains = {
            "h1": ["blue", "red"],    # adj a2=green, b1=green cross-edges → h1≠green
            "h2": ["red", "green"],   # adj h1=[blue,red] (cycle)          → h2≠blue
            "h4": ["red", "green"],   # adj h1=[blue,red] (chord h4–h1)    → h4≠blue
            "h5": ["green", "red"],   # adj h4=[red,green] + h1 (chord)    → h5≠blue
            "a1": ["blue", "red"],    # adj a2=[green,red] (cycle)         → a1≠green
            "a2": ["green", "red"],   # adj h1=blue, h6=blue cross-edges   → a2≠blue
            "a5": ["red", "blue"],    # adj h5=green cross-edge            → a5≠green
            "a6": ["blue", "red"],    # adj a2=[green,red] (chord a2–a6)   → a6≠green
            "b1": ["green", "red"],   # adj h1=blue cross-edge             → b1≠blue
            "b3": ["red", "blue"],    # adj h3=green cross-edge            → b3≠green
            "b5": ["red", "blue"],    # adj h5=green cross-edge            → b5≠green
            "b7": ["blue", "green"],  # adj h7=red   cross-edge            → b7≠red
        }
        explicit_fixed = {"Human": {}, "Agent1": {}, "Agent2": {}}
        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_hard_8":
        # ── Hard 8-node testing preset: 2 agents, denser cross-edges, tighter agent constraints ──
        # Same internal topology as cx_easy_8 (h4–h1 chord for human, antipodal for agents).
        #
        # Cross-edges (10 total — ~43% more than easy_8):
        #   h1–a2, h5–a5, h6–a2, h3–a6, h1–a8  (Human↔Agent1)
        #   h1–b1, h3–b3, h5–b5, h4–b5, h7–b7  (Human↔Agent2)
        # Two shared agent boundary nodes:
        #   a2: receives h1 and h6 (both blue → domain unchanged [green,red])
        #   b5: receives h5=green and h4=red → b5≠green,≠red → b5=[blue] FIXED
        # h1 connects to 4 cross-cluster neighbours (a2, a8, b1); h3 spans both agents (a6, b3).
        #
        # Constraints (~67% of nodes — 16/24 — have restricted domains; b5 is fixed):
        #   Human (4/8):  h1=[blue,red]  h2=[red,green]  h4=[red,green]  h5=[green,red]
        #   Agent1 (6/8): a1=[blue,red]  a2=[green,red]  a5=[red,blue]   a6=[blue,red]
        #                 a7=[green,red]  a8=[red,green]
        #   Agent2 (6/8): b1=[green,red]  b2=[blue,red]  b3=[red,blue]   b4=[green,blue]
        #                 b5=[blue] (fixed)  b7=[blue,green]
        #
        # Verified solution:
        #   h: blue, red,   green, red,   green, blue, red,   green
        #   a: blue, green, blue,  green, red,   blue, green, red
        #   b: green,blue,  red,   green, blue,  red,  blue,  red
        human_nodes  = [f"h{i}" for i in range(1, 9)]
        agent1_nodes = [f"a{i}" for i in range(1, 9)]
        agent2_nodes = [f"b{i}" for i in range(1, 9)]

        def _mk_8cyc_antipodal_h8(prefix: str) -> dict:
            ns = [f"{prefix}{i}" for i in range(1, 9)]
            adj: dict = {n: [] for n in ns}
            for i in range(8):
                a_n, b_n = ns[i], ns[(i + 1) % 8]
                adj[a_n].append(b_n); adj[b_n].append(a_n)
            for i in range(4):
                adj[ns[i]].append(ns[i + 4]); adj[ns[i + 4]].append(ns[i])
            return adj

        adjacency = {}
        for pfx in ("a", "b"):
            adjacency.update(_mk_8cyc_antipodal_h8(pfx))

        h_ns = [f"h{i}" for i in range(1, 9)]
        adjacency.update({n: [] for n in h_ns})
        for i in range(8):
            u, v = h_ns[i], h_ns[(i + 1) % 8]
            adjacency[u].append(v); adjacency[v].append(u)
        for chord in [("h1", "h5"), ("h2", "h6"), ("h3", "h7"), ("h4", "h1")]:
            adjacency[chord[0]].append(chord[1]); adjacency[chord[1]].append(chord[0])

        # Human↔Agent1 (h6 shares a2 with h1; h3 reaches a6; h1 also reaches a8)
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h5"].append("a5"); adjacency["a5"].append("h5")
        adjacency["h6"].append("a2"); adjacency["a2"].append("h6")
        adjacency["h3"].append("a6"); adjacency["a6"].append("h3")
        adjacency["h1"].append("a8"); adjacency["a8"].append("h1")
        # Human↔Agent2 (h4 shares b5 with h5 → b5 fixed; h3 spans both agents)
        adjacency["h1"].append("b1"); adjacency["b1"].append("h1")
        adjacency["h3"].append("b3"); adjacency["b3"].append("h3")
        adjacency["h5"].append("b5"); adjacency["b5"].append("h5")
        adjacency["h4"].append("b5"); adjacency["b5"].append("h4")
        adjacency["h7"].append("b7"); adjacency["b7"].append("h7")

        node_domains = {
            # Human (4/8) — same as easy_8
            "h1": ["blue", "red"],    # cross-edges to a2, a8, b1          → h1≠green
            "h2": ["red", "green"],   # adj h1=[blue,red] (cycle)          → h2≠blue
            "h4": ["red", "green"],   # adj h1=[blue,red] (chord h4–h1)    → h4≠blue
            "h5": ["green", "red"],   # adj h4=[red,green] + h1 (chord)    → h5≠blue
            # Agent1 (6/8)
            "a1": ["blue", "red"],    # adj a2=[green,red] (cycle)         → a1≠green
            "a2": ["green", "red"],   # adj h1=blue, h6=blue cross-edges   → a2≠blue
            "a5": ["red", "blue"],    # adj h5=green cross-edge            → a5≠green
            "a6": ["blue", "red"],    # adj h3=green cross-edge + chord    → a6≠green
            "a7": ["green", "red"],   # adj a6=[blue,red] (cycle)          → a7≠blue
            "a8": ["red", "green"],   # adj h1=blue cross-edge             → a8≠blue
            # Agent2 (6/8)
            "b1": ["green", "red"],   # adj h1=blue cross-edge             → b1≠blue
            "b2": ["blue", "red"],    # adj b1=[green,red] (cycle)         → b2≠green
            "b3": ["red", "blue"],    # adj h3=green cross-edge            → b3≠green
            "b4": ["green", "blue"],  # adj b3=[red,blue] (cycle)          → b4≠red
            "b5": ["blue"],           # adj h5=green + h4=red → ≠green,≠red → fixed blue
            "b7": ["blue", "green"],  # adj h7=red   cross-edge            → b7≠red
        }
        explicit_fixed = {"Human": {}, "Agent1": {}, "Agent2": {}}
        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_test_10":
        # ── Testing preset: 10 nodes per cluster, 2 agents, moderate cx constraints ──
        # Topology: 10-cycle + 5 chords {x1–x5, x2–x6, x3–x7, x4–x8, x5–x9} per cluster.
        # Nodes x1–x4 and x6–x10 have degree 3 (2 cycle + 1 chord); x5 has degree 4
        # (2 cycle + chords to x1 and x9) — ~36% more internal edges than 10-cycle+1.
        #
        # Cross-edges (6 total, 50% more than original 4):
        #   h1–a2, h5–a5, h6–a6  (Human↔Agent1)
        #   h3–b3, h8–b8, h6–b6  (Human↔Agent2)
        # h6 connects to BOTH agents (a6 and b6), making it the bilateral hub.
        # h6's neighbours a6=blue and b6=red force h6=green uniquely.
        #
        # Constraints (~50% of nodes have 2-colour domain, 50% fully free):
        #   h1: adj a2=green               → h1≠green  → [blue, red]
        #   h6: adj a6=blue, b6=red        → h6≠blue,≠red → [green, red]  (forced green)
        #   a1: adj a2=green, a10=green, a5=green (chord) → a1≠green → [red, blue]
        #   a2: adj h1=blue cross-edge     → a2≠blue   → [green, red]
        #   a5: adj h5=red  cross-edge     → a5≠red    → [green, blue]
        #   a6: adj h6=green cross-edge    → a6≠green  → [blue, red]
        #   b3: adj h3=green cross-edge    → b3≠green  → [red, blue]
        #   b6: adj h6=green cross-edge    → b6≠green  → [red, blue]
        #   b8: adj h8=red   cross-edge    → b8≠red    → [blue, green]
        # No fixed (1-colour) nodes.
        #
        # Verified solution:
        #   h:  blue, red,  green, blue, red,  green, blue, red,  green, red
        #   a:  red,  green,blue,  red,  green,blue,  red,  green,blue,  green
        #   b:  green,blue, red,   green,blue, red,   green,blue, red,   blue
        human_nodes  = [f"h{i}" for i in range(1, 11)]
        agent1_nodes = [f"a{i}" for i in range(1, 11)]
        agent2_nodes = [f"b{i}" for i in range(1, 11)]

        def _mk_10cyc(prefix: str) -> dict:
            ns = [f"{prefix}{i}" for i in range(1, 11)]
            adj: dict = {n: [] for n in ns}
            for i in range(10):
                a_n, b_n = ns[i], ns[(i + 1) % 10]
                adj[a_n].append(b_n); adj[b_n].append(a_n)
            # 4 chords x1–x5, x2–x6, x3–x7, x4–x8 (antipodal pairs in first half)
            for i in range(4):
                adj[ns[i]].append(ns[i + 4]); adj[ns[i + 4]].append(ns[i])
            # Extra chord x5–x9 (ns[4] to ns[8])
            adj[ns[4]].append(ns[8]); adj[ns[8]].append(ns[4])
            return adj

        adjacency = {}
        for pfx in ("h", "a", "b"):
            adjacency.update(_mk_10cyc(pfx))

        # Human↔Agent1
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h5"].append("a5"); adjacency["a5"].append("h5")
        adjacency["h6"].append("a6"); adjacency["a6"].append("h6")
        # Human↔Agent2
        adjacency["h3"].append("b3"); adjacency["b3"].append("h3")
        adjacency["h8"].append("b8"); adjacency["b8"].append("h8")
        adjacency["h6"].append("b6"); adjacency["b6"].append("h6")  # h6 faces both agents

        # ~50% of nodes (15/30) have 2-colour domains; no fixed nodes.
        node_domains = {
            "h1": ["blue", "red"],    # adj a2=green cross-edge          → h1≠green
            "h2": ["red", "green"],   # adj h1=[blue,red] (cycle) + chord h6=[green,red] → h2≠blue
            "h5": ["red", "green"],   # adj h1(chord) + h6=[green,red](chord) → h5≠blue
            "h6": ["green", "red"],   # adj a6=blue, b6=red cross-edges  → h6≠blue,≠red
            "a1": ["red", "blue"],    # internal adj a2=G, a10=G, a5=G   → a1≠green
            "a2": ["green", "red"],   # adj h1=blue  cross-edge          → a2≠blue
            "a3": ["blue", "red"],    # adj a2=[green,red] (cycle) → a3≠green
            "a5": ["green", "blue"],  # adj h5=red   cross-edge          → a5≠red
            "a6": ["blue", "red"],    # adj h6=green cross-edge          → a6≠green
            "a7": ["red", "green"],   # adj a6=[blue,red] (cycle) → a7≠blue
            "b2": ["blue", "green"],  # adj b6=[red,blue] (chord x2–x6) → b2≠red
            "b3": ["red", "blue"],    # adj h3=green cross-edge          → b3≠green
            "b5": ["blue", "green"],  # adj b6=[red,blue] (cycle) → b5≠red
            "b6": ["red", "blue"],    # adj h6=green cross-edge          → b6≠green
            "b8": ["blue", "green"],  # adj h8=red   cross-edge          → b8≠red
        }
        explicit_fixed = {"Human": {}, "Agent1": {}, "Agent2": {}}
        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset == "cx_test_trio_8":
        # ── Testing preset: 8 nodes per cluster, 3 agents, moderate cx constraints ──
        # 4 clusters: Human + Agent1 (a) + Agent2 (b) + Agent3 (c), 8 nodes each.
        # Topology: 8-cycle + 4 antipodal chords {x1–x5, x2–x6, x3–x7, x4–x8} per cluster.
        #
        # Cross-edges (9 total, 50% more than original 6):
        #   h1–a2, h5–a5, h2–a3  (Human↔Agent1)
        #   h3–b3, h7–b7, h5–b5  (Human↔Agent2)
        #   h2–c4, h6–c6, h8–c8  (Human↔Agent3)
        # h5 connects to Agent1 (a5) and Agent2 (b5) — dual-agent hub.
        # h2 connects to Agent1 (a3) and Agent3 (c4) — dual-agent hub.
        # Only h4 has no cross-cluster edge — the single freely safe start node.
        #
        # Constraints (~31% of nodes have 2-colour domain, 69% fully free):
        #   h5: adj a5=green, b5=blue → h5≠green,≠blue → [red, green]  (forced red)
        #   a2: adj h1=blue  → a2≠blue  → [green, red]
        #   a3: adj h2=red   → a3≠red   → [blue, green]
        #   a5: adj h5=red   → a5≠red   → [green, blue]
        #   b3: adj h3=green → b3≠green → [red, blue]
        #   b5: adj h5=red   → b5≠red   → [blue, green]
        #   b7: adj h7=blue  → b7≠blue  → [green, red]
        #   c4: adj h2=red   → c4≠red   → [blue, green]
        #   c6: adj h6=green → c6≠green → [red, blue]
        #   c8: adj h8=red   → c8≠red   → [green, blue]
        # No fixed (1-colour) nodes.
        #
        # Verified solution:
        #   h: blue, red,   green, blue, red,   green, blue, red
        #   a: red,  green, blue,  red,  green, blue,  red,  green
        #   b: green,blue,  red,   green,blue,  red,   green,blue
        #   c: blue, green, red,   blue, green, red,   blue, green
        human_nodes  = [f"h{i}" for i in range(1, 9)]
        agent1_nodes = [f"a{i}" for i in range(1, 9)]
        agent2_nodes = [f"b{i}" for i in range(1, 9)]
        agent3_nodes = [f"c{i}" for i in range(1, 9)]

        def _mk_8cyc_trio(prefix: str) -> dict:
            ns = [f"{prefix}{i}" for i in range(1, 9)]
            adj: dict = {n: [] for n in ns}
            for i in range(8):
                a_n, b_n = ns[i], ns[(i + 1) % 8]
                adj[a_n].append(b_n); adj[b_n].append(a_n)
            # 4 antipodal chords: x1–x5, x2–x6, x3–x7, x4–x8
            for i in range(4):
                adj[ns[i]].append(ns[i + 4]); adj[ns[i + 4]].append(ns[i])
            return adj

        adjacency = {}
        for pfx in ("h", "a", "b", "c"):
            adjacency.update(_mk_8cyc_trio(pfx))

        # Human↔Agent1 (h1, h5, h2)
        adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
        adjacency["h5"].append("a5"); adjacency["a5"].append("h5")
        adjacency["h2"].append("a3"); adjacency["a3"].append("h2")
        # Human↔Agent2 (h3, h7, h5 — h5 faces both Agent1 and Agent2)
        adjacency["h3"].append("b3"); adjacency["b3"].append("h3")
        adjacency["h7"].append("b7"); adjacency["b7"].append("h7")
        adjacency["h5"].append("b5"); adjacency["b5"].append("h5")
        # Human↔Agent3 (h2, h6, h8 — h2 faces both Agent1 and Agent3)
        adjacency["h2"].append("c4"); adjacency["c4"].append("h2")
        adjacency["h6"].append("c6"); adjacency["c6"].append("h6")
        adjacency["h8"].append("c8"); adjacency["c8"].append("h8")

        # ~50% of nodes (16/32) have 2-colour domains; no fixed nodes.
        node_domains = {
            "h1": ["blue", "red"],    # adj a2=[green,red] cross-edge → h1≠green
            "h3": ["green", "blue"],  # adj b3=[red,blue]  cross-edge → h3≠red
            "h5": ["red", "green"],   # adj a5=green, b5=blue cross-edges → h5≠green,≠blue
            "a1": ["red", "blue"],    # adj a2=[green,red] (cycle) → a1≠green
            "a2": ["green", "red"],   # adj h1=blue  cross-edge → a2≠blue
            "a3": ["blue", "green"],  # adj h2=red   cross-edge → a3≠red
            "a5": ["green", "blue"],  # adj h5=red   cross-edge → a5≠red
            "a6": ["blue", "red"],    # adj a2=[green,red] (chord a2–a6) → a6≠green
            "b3": ["red", "blue"],    # adj h3=green cross-edge → b3≠green
            "b4": ["green", "blue"],  # adj b3=[red,blue] (cycle) → b4≠red
            "b5": ["blue", "green"],  # adj h5=red   cross-edge → b5≠red
            "b7": ["green", "red"],   # adj h7=blue  cross-edge → b7≠blue
            "c2": ["green", "red"],   # adj c6=[red,blue] (chord c2–c6) → c2≠blue
            "c4": ["blue", "green"],  # adj h2=red   cross-edge → c4≠red
            "c6": ["red", "blue"],    # adj h6=green cross-edge → c6≠green
            "c8": ["green", "blue"],  # adj h8=red   cross-edge → c8≠red
        }
        explicit_fixed = {"Human": {}, "Agent1": {}, "Agent2": {}, "Agent3": {}}
        node_names_tmp = human_nodes + agent1_nodes + agent2_nodes + agent3_nodes
        _check_solvable_with_domains(node_names_tmp, adjacency, node_domains, domain)

    elif preset in ("cx_easy_8_b", "cx_easy_8_c", "cx_hard_8_b", "cx_hard_8_c"):
        # Isomorphic variants — same structure as the base preset, shifted so
        # participants see different node labels and colour assignments.
        _base, _shift, _cycle = {
            "cx_easy_8_b": ("cx_easy_8", 2, 1),  # hub moves to h3; blue→green
            "cx_easy_8_c": ("cx_easy_8", 4, 2),  # hub moves to h5; blue→red
            "cx_hard_8_b": ("cx_hard_8", 2, 1),
            "cx_hard_8_c": ("cx_hard_8", 4, 2),
        }[preset]
        return _apply_isomorphic_shift(_build_topology(_base, num_fixed_nodes), _shift, _cycle)

    else:
        raise ValueError(
            f"Unknown graph_preset: {graph_preset!r}. "
            "Use 'easy', 'medium', 'tight', 'tight2', 'tight3', 'tight4', 'hard', 'expert', "
            "'dense', 'dense_tight', 'super', 'cx_easy', 'cx_medium', 'cx_hard', "
            "'cx_easy_plus', 'cx_hard_free', 'cx_expert', 'cx_gauntlet', 'cx_super', "
            "'trio', 'trio_tight', 'trio_cx', 'trio_tight_cx', "
            "'cx_easy_8', 'cx_easy_8_b', 'cx_easy_8_c', "
            "'cx_hard_8', 'cx_hard_8_b', 'cx_hard_8_c', "
            "'cx_test_10', or 'cx_test_trio_8'."
        )

    node_names = human_nodes + agent1_nodes + agent2_nodes + agent3_nodes
    clusters: dict = {
        "Human":  human_nodes,
        "Agent1": agent1_nodes,
        "Agent2": agent2_nodes,
    }
    if agent3_nodes:
        clusters["Agent3"] = agent3_nodes
    owners: dict = {}
    for owner, nodes in clusters.items():
        for n in nodes:
            owners[n] = owner
    return node_names, clusters, adjacency, owners, explicit_fixed, node_domains


def _assign_participant_id(
    results_root: Path,
    participant_name: str,
    condition: str,
    graph_preset: str,
    date_str: str,
) -> str:
    """Return a new anonymous participant ID (e.g. P001) and record it in the mapping file."""
    import csv

    mapping_file = results_root / "participant_mapping.csv"
    existing_ids: list[int] = []

    if mapping_file.exists():
        with open(mapping_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get("ID", "")
                if pid.startswith("P") and pid[1:].isdigit():
                    existing_ids.append(int(pid[1:]))

    next_num = max(existing_ids, default=0) + 1
    participant_id = f"P{next_num:03d}"

    write_header = not mapping_file.exists()
    with open(mapping_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["ID", "Name", "Date", "Condition", "GraphPreset"])
        writer.writerow([participant_id, participant_name, date_str, condition, graph_preset])

    return participant_id


def run_experiment(
    *,
    condition: str,
    use_ui: bool,
    use_llm: bool = False,
    fixed_constraints: bool = True,
    num_fixed_nodes: int = 1,
    graph_preset: str = "easy",
    output_dir: str | None = None,
    participant_name: str = "",
    test_run: bool = False,
) -> None:
    cwd = Path.cwd()
    if (cwd / "code").exists() or (cwd / "run_experiment.py").exists():
        project_root = cwd
    else:
        project_root = Path(__file__).resolve().parent

    import datetime
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    if output_dir is not None:
        results_dir = Path(output_dir)
    elif test_run:
        results_dir = project_root / "results" / "tempTest"
        # Wipe previous test run so it doesn't accumulate
        import shutil
        if results_dir.exists():
            shutil.rmtree(results_dir)
    else:
        results_root = project_root / "results"
        results_root.mkdir(parents=True, exist_ok=True)
        participant_id = _assign_participant_id(
            results_root,
            participant_name or "unknown",
            condition,
            graph_preset,
            date_str,
        )
        results_dir = results_root / date_str / participant_id
    results_dir.mkdir(parents=True, exist_ok=True)

    # Write run-level metadata so each output directory is self-contained.
    import json as _json
    _run_config = {
        "condition": condition,
        "graph_preset": graph_preset,
        "participant_name": participant_name,
        "timestamp_start": now.isoformat(),
        "use_llm": use_llm,
        "fixed_constraints": fixed_constraints,
        "num_fixed_nodes": num_fixed_nodes,
        "test_run": test_run,
        "output_dir": str(results_dir),
    }
    try:
        (results_dir / "run_config.json").write_text(
            _json.dumps(_run_config, indent=2), encoding="utf-8"
        )
    except Exception as _e:
        print(f"[run_experiment] Warning: could not write run_config.json: {_e}")

    print(f"[run_experiment] Condition: {condition}")
    if test_run:
        print(f"[run_experiment] TEST RUN — Writing results to: {results_dir}")
    else:
        print(f"[run_experiment] Writing results to: {results_dir}")

    node_names, clusters, adjacency, owners, explicit_fixed, node_domains = _build_topology(
        graph_preset, num_fixed_nodes=num_fixed_nodes if fixed_constraints else 0
    )
    print(f"[run_experiment] Graph preset: {graph_preset!r} ({len(list(clusters.values())[0])} nodes/cluster)")

    domain = ["red", "green", "blue"]

    # Presets with pre-designed fixed nodes (medium/expert) override seed-42 selection.
    preset_fixed_nodes = explicit_fixed  # None for easy/hard

    if use_ui:
        from cluster_simulation import run_constraint_viz_simulation
        run_constraint_viz_simulation(
            node_names=node_names,
            clusters=clusters,
            adjacency=adjacency,
            owners=owners,
            domain=domain,
            condition=condition,
            fixed_constraints=fixed_constraints,
            num_fixed_nodes=num_fixed_nodes,
            use_llm=use_llm,
            output_dir=str(results_dir),
            ui_title=f"Constraint Visualisation — {condition} ({graph_preset.capitalize()})",
            preset_fixed_nodes=preset_fixed_nodes,
            graph_preset=graph_preset,
            node_domains=node_domains,
        )
    else:
        from cluster_simulation import run_headless_constraint_viz
        colour_steps = [{}]  # default: one step with nothing assigned
        run_headless_constraint_viz(
            node_names=node_names,
            clusters=clusters,
            adjacency=adjacency,
            owners=owners,
            domain=domain,
            condition=condition,
            colour_steps=colour_steps,
            use_llm=use_llm,
            preset_fixed_nodes=preset_fixed_nodes,
            graph_preset=graph_preset,
            fixed_constraints=fixed_constraints,
            num_fixed_nodes=num_fixed_nodes,
        )

    print(f"[run_experiment] Finished. Check outputs in: {results_dir}")


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Run the constraint visualisation study.")
    p.add_argument("--condition", default=CONDITION, choices=["C1", "C2", "C3", "C4", "C5", "C6"])
    ui = p.add_mutually_exclusive_group()
    ui.add_argument("--use-ui", dest="use_ui", action="store_true")
    ui.add_argument("--no-ui", dest="use_ui", action="store_false")
    p.set_defaults(use_ui=USE_UI)

    p.add_argument("--use-llm", dest="use_llm", action="store_true", default=USE_LLM,
                   help="Call LLM for NL summaries (C4/C5/C6 only)")
    p.add_argument("--fixed-constraints", action="store_true", default=FIXED_CONSTRAINTS,
                   help="Fix internal nodes per cluster to force constraint structure")
    p.add_argument("--num-fixed-nodes", type=int, default=NUM_FIXED_NODES,
                   choices=[0, 1, 2, 3], help="Number of fixed nodes per cluster")
    p.add_argument("--graph-preset", default="easy",
                   choices=["easy", "tight", "tight2", "tight3", "tight4", "hard",
                            "cx_easy", "cx_medium", "cx_hard",
                            "cx_easy_plus", "cx_hard_free",
                            "cx_expert", "cx_gauntlet", "cx_super",
                            "trio", "trio_tight", "trio_cx", "trio_tight_cx",
                            "medium", "expert", "dense", "dense_tight", "super",
                            "cx_easy_8", "cx_easy_8_b", "cx_easy_8_c",
                            "cx_hard_8", "cx_hard_8_b", "cx_hard_8_c",
                            "cx_test_10", "cx_test_trio_8"],
                   help="Presets: easy/tight/hard (simple constraints), "
                        "cx_easy/cx_medium/cx_hard (complex per-node domain constraints), "
                        "cx_easy_plus/cx_hard_free/cx_expert/cx_gauntlet/cx_super (harder)")
    p.add_argument("--output-dir", default=None,
                   help="Override output directory (default: results/YYYY-MM-DD/<participant-id>)")
    p.add_argument("--participant-name", default="",
                   help="Participant's real name (mapped to an anonymous ID in the results directory)")
    p.add_argument("--test-run", action="store_true", default=False,
                   help="Save to results/tempTest (overwritten each run); no mapping entry created")

    args = p.parse_args()

    run_experiment(
        condition=args.condition,
        use_ui=bool(args.use_ui),
        use_llm=bool(args.use_llm),
        fixed_constraints=bool(args.fixed_constraints),
        num_fixed_nodes=int(args.num_fixed_nodes),
        graph_preset=str(args.graph_preset),
        output_dir=args.output_dir,
        participant_name=str(args.participant_name),
        test_run=bool(args.test_run),
    )


if __name__ == "__main__":
    main()
