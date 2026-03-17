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


def _build_topology(graph_preset: str, num_fixed_nodes: int = 2) -> tuple:
    """Return (node_names, clusters, adjacency, owners, explicit_fixed, node_domains) for the given preset.

    Presets
    -------
    "easy"    – 5-node-per-cluster topology; seed-42 fixed-node selection.
    "medium"  – Same 5-node topology but with pre-designed explicit fixed
                nodes (h3=red, a3=green, b3=blue) that create interesting
                cross-cluster constraint tension.
    "hard"    – 6-node-per-cluster topology; 6-cycle + antipodal chord;
                seed-42 fixed-node selection.
    "expert"  – Same 6-node topology but with pre-designed explicit fixed
                nodes (h3=green, h6=red, a1=blue, a4=red, b2=green,
                b5=red) for tighter constraints.

    ``explicit_fixed`` is ``None`` for presets that use seed-42 selection
    (easy/hard) and a per-cluster dict ``{owner: {node: colour}}`` for
    presets with pre-designed constraints (medium/expert).
    """
    preset = graph_preset.lower()
    domain = ["red", "green", "blue"]
    explicit_fixed = None  # default: no pre-designed fixed constraints
    node_domains: dict | None = None  # default: no per-node domain restrictions

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

    elif preset in ("tight", "dense", "dense_tight"):
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
        else:  # dense_tight
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

    else:
        raise ValueError(
            f"Unknown graph_preset: {graph_preset!r}. "
            "Use 'easy', 'medium', 'tight', 'hard', 'expert', "
            "'dense', 'dense_tight', or 'super'."
        )

    node_names = human_nodes + agent1_nodes + agent2_nodes
    clusters = {"Human": human_nodes, "Agent1": agent1_nodes, "Agent2": agent2_nodes}
    owners = (
        {n: "Human" for n in human_nodes}
        | {n: "Agent1" for n in agent1_nodes}
        | {n: "Agent2" for n in agent2_nodes}
    )
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
                   choices=["easy", "tight", "hard",
                            "cx_easy", "cx_medium", "cx_hard",
                            "medium", "expert", "dense", "dense_tight", "super"],
                   help="Presets: easy/tight/hard (simple constraints), "
                        "cx_easy/cx_medium/cx_hard (complex per-node domain constraints)")
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
