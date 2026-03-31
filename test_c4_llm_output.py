"""
test_c4_llm_output.py — Quick test to see what the C4 LLM prompts actually produce.

Sets up the "easy" preset graph, runs the constraint analyser with a few
representative human colour states, and calls the LLM layer to produce
node-overlay and panel-summary messages.  Output is printed to stdout so
you can judge whether the messages are expressive or templated.

Usage:
    python test_c4_llm_output.py
"""
from __future__ import annotations

import sys
import os

# Make sure we can import project modules
sys.path.insert(0, os.path.dirname(__file__))

from problems.graph_coloring import GraphColoring
from agents.constraint_analyser import ConstraintAnalyser
from comm.constraint_llm_layer import ConstraintLLMLayer

# ---------------------------------------------------------------------------
# Graph topology  (easy preset — same as cluster_simulation.py)
# ---------------------------------------------------------------------------
domain = ["red", "green", "blue"]

human_nodes   = ["h1", "h2", "h3", "h4", "h5"]
agent1_nodes  = ["a1", "a2", "a3", "a4", "a5"]
agent2_nodes  = ["b1", "b2", "b3", "b4", "b5"]

adjacency: dict = {
    "h1": ["h2", "h5"],
    "h2": ["h1", "h3", "h5"],
    "h3": ["h2", "h4"],
    "h4": ["h3", "h5"],
    "h5": ["h1", "h2", "h4"],
    "a1": ["a2", "a5"],
    "a2": ["a1", "a3", "a5"],
    "a3": ["a2", "a4"],
    "a4": ["a3", "a5"],
    "a5": ["a1", "a2", "a4"],
    "b1": ["b2", "b5"],
    "b2": ["b1", "b3", "b5"],
    "b3": ["b2", "b4"],
    "b4": ["b3", "b5"],
    "b5": ["b1", "b2", "b4"],
}
# Cross-cluster edges  (Human <-> Agent1)
adjacency["h1"].append("a2"); adjacency["a2"].append("h1")
adjacency["h4"].append("a4"); adjacency["a4"].append("h4")
adjacency["h4"].append("a5"); adjacency["a5"].append("h4")
# Cross-cluster edges  (Human <-> Agent2)
adjacency["h2"].append("b2"); adjacency["b2"].append("h2")
adjacency["h5"].append("b2"); adjacency["b2"].append("h5")

node_names = human_nodes + agent1_nodes + agent2_nodes
edges = []
seen: set = set()
for u, nbrs in adjacency.items():
    for v in nbrs:
        key = tuple(sorted([u, v]))
        if key not in seen:
            seen.add(key)
            edges.append((u, v))

problem = GraphColoring(node_names, edges, domain, conflict_penalty=10.0)

# Agent1 boundary: human nodes adjacent to Agent1
agent1_boundary = [h for h in human_nodes
                   if any(nb in agent1_nodes for nb in adjacency[h])]
# Agent2 boundary: human nodes adjacent to Agent2
agent2_boundary = [h for h in human_nodes
                   if any(nb in agent2_nodes for nb in adjacency[h])]

print("Agent1 boundary nodes:", agent1_boundary)
print("Agent2 boundary nodes:", agent2_boundary)
print()

analyser1 = ConstraintAnalyser(
    name="Agent1",
    problem=problem,
    agent_nodes=agent1_nodes,
    human_nodes=human_nodes,
    boundary_nodes=agent1_boundary,
    domain=domain,
)
analyser2 = ConstraintAnalyser(
    name="Agent2",
    problem=problem,
    agent_nodes=agent2_nodes,
    human_nodes=human_nodes,
    boundary_nodes=agent2_boundary,
    domain=domain,
)

llm = ConstraintLLMLayer(condition="C4")

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
SEP = "=" * 70

def run_scenario(label: str, human_partial: dict, node_domains: dict | None = None) -> None:
    """node_domains: optional {node: [allowed_colours]} for domain-restriction testing."""
    print(SEP)
    print(f"SCENARIO: {label}")
    assigned = {k: v for k, v in human_partial.items() if v is not None}
    print(f"  Human assignment: {assigned if assigned else '(nothing)'}")
    if node_domains:
        print(f"  Domain restrictions: {node_domains}")
    print()

    for analyser, agent_name, boundary in [
        (analyser1, "Agent1", agent1_boundary),
        (analyser2, "Agent2", agent2_boundary),
    ]:
        fset = analyser.compute_feasibility_set(human_partial)
        feasibility_count = len(fset)
        consequence_sets = analyser.compute_consequence_sets(human_partial)
        boundary_joint = analyser.compute_boundary_joint_feasibility(human_partial)

        boundary_set = set(boundary)
        all_boundary_assignments = {n: human_partial.get(n) for n in boundary}
        all_consequence_counts = {
            n: {col: len(cfgs) for col, cfgs in consequence_sets.get(n, {}).items()}
            for n in boundary
        }

        # ---- Panel summary ----
        llm_data = {
            "feasibility_count": feasibility_count,
            "consequence_sets": {
                n: {col: len(cfgs) for col, cfgs in colour_map.items()}
                for n, colour_map in consequence_sets.items()
            },
            "boundary_joint_feasibility": boundary_joint,
            "boundary_nodes": boundary,
            "human_boundary_partial": {k: v for k, v in human_partial.items() if k in boundary_set},
            "full_domain": domain,
        }
        panel_msg = llm.summarise(agent_name, llm_data)
        print(f"  [{agent_name}] Panel summary:")
        print(f"    {panel_msg}")
        print()

        # ---- Per-node overlays ----
        print(f"  [{agent_name}] Node overlays (boundary: {boundary}):")
        for bnode in boundary:
            cur_col = human_partial.get(bnode)
            colour_map = consequence_sets.get(bnode, {})
            key = str(cur_col).lower() if cur_col else ""
            configs = colour_map.get(key, [])
            bnode_domain = (node_domains or {}).get(bnode, domain)

            node_summary = llm.summarise_node(
                bnode,
                {
                    "current_colour": cur_col,
                    "configs": configs,
                    "all_colour_configs": colour_map,
                    "boundary_joint_feasibility": boundary_joint,
                    "boundary_nodes": boundary,
                    "all_boundary_assignments": all_boundary_assignments,
                    "all_consequence_counts": all_consequence_counts,
                    "node_allowed_domain": list(bnode_domain),
                },
            )
            col_display = f"={cur_col}" if cur_col else " (unassigned)"
            print(f"    {bnode}{col_display}:")
            for line in node_summary.split("\n"):
                print(f"      {line}")
        print()


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

# 1. Nothing assigned yet
run_scenario("Nothing assigned", {n: None for n in human_nodes})

# 2. One boundary node assigned — good colour
run_scenario("h1=red (Agent1 boundary)", {**{n: None for n in human_nodes}, "h1": "red"})

# 3. One boundary node assigned — bad colour (h4 connects to a4 and a5)
run_scenario("h4=red (Agent1 boundary, potentially blocking)", {**{n: None for n in human_nodes}, "h4": "red"})

# 4. Both Agent1 boundary nodes assigned — conflict scenario
run_scenario("h1=red, h4=red", {**{n: None for n in human_nodes}, "h1": "red", "h4": "red"})

# 5. Both Agent2 boundary nodes assigned — valid
run_scenario("h2=red, h5=green (Agent2 boundary)", {**{n: None for n in human_nodes}, "h2": "red", "h5": "green"})

# 6. Both Agent2 boundary nodes same colour  — likely conflict with b2
run_scenario("h2=blue, h5=blue (Agent2 both blue, b2 neighbours both)", {**{n: None for n in human_nodes}, "h2": "blue", "h5": "blue"})

# 7. Mixed partial — some good, one bad
run_scenario("h1=green, h4=green, h2=red, h5=blue",
             {**{n: None for n in human_nodes}, "h1": "green", "h4": "green", "h2": "red", "h5": "blue"})

# 8. Domain restriction: h4 only allows [blue, red] — green is domain-excluded (UI shows this).
#    Agent1 boundary includes h4. With h4=blue, check that the overlay does NOT say "green is blocked"
#    (already shown by the domain chip), but DOES note if any in-domain colour has zero agent configs.
run_scenario(
    "h4=blue, domain restricted [blue,red] on h4 — green should be silent",
    {**{n: None for n in human_nodes}, "h4": "blue"},
    node_domains={"h4": ["blue", "red"]},
)

# 9. Domain restriction + in-domain colour blocked by agent: h4 domain=[blue,red], but
#    suppose we simulate the analyser seeing green in consequence counts with 0 configs.
#    Actually just set h4=red with domain=[blue,red] and full assignment to see overlap handling.
run_scenario(
    "h4=red, domain=[blue,red]; h2=blue, h5=blue (Agent2 conflict)",
    {**{n: None for n in human_nodes}, "h4": "red", "h2": "blue", "h5": "blue"},
    node_domains={"h4": ["blue", "red"]},
)

print(SEP)
print("Done.")
