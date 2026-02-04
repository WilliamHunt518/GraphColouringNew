"""
Manual validation to check if Agent1 can actually achieve penalty=0 with h1=red.

This tests the exact scenario from user's transcript where Agent1 claims
no solution exists with h1=red, but we suspect one does exist.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.cluster_agent import ClusterAgent
from problems.graph_coloring import GraphColoring
from comm.communication_layer import LLMCommLayer


def create_problem():
    """Create the exact problem from the test/transcript"""
    # 3 clusters: Agent1 (a1-a5), Human (h1-h5), Agent2 (b1-b5)
    nodes = ["a1", "a2", "a3", "a4", "a5", "h1", "h2", "h3", "h4", "h5", "b1", "b2", "b3", "b4", "b5"]

    # Edges
    edges = [
        # Agent1 - Human boundary
        ("a2", "h1"), ("a4", "h4"), ("a5", "h4"),
        # Human - Agent2 boundary
        ("h2", "b2"), ("h5", "b2"), ("h5", "b5"),
        # Internal edges (within clusters)
        ("a1", "a2"), ("a3", "a4"),
        ("h1", "h2"), ("h3", "h4"), ("h4", "h5"),
        ("b1", "b2"), ("b3", "b4"),
    ]

    domain = ["red", "green", "blue"]
    return GraphColoring(nodes, edges, domain)


def test_manual_solution():
    """Manually test if h1=red, h4=blue works for Agent1"""
    problem = create_problem()

    print("="*70)
    print("MANUAL VALIDATION: Does h1=red, h4=blue work for Agent1?")
    print("="*70)

    # Agent1's boundary beliefs
    boundary = {
        "h1": "red",
        "h4": "blue"
    }

    print(f"\nBoundary configuration: {boundary}")
    print("\nAgent1's nodes: a1, a2, a3, a4, a5")
    print("Agent1's edges (internal): (a1, a2), (a3, a4)")
    print("Agent1's edges (to boundary): (a2, h1), (a4, h4), (a5, h4)")

    # Manually compute a valid assignment
    print("\n" + "-"*70)
    print("MANUAL SOLUTION ATTEMPT:")
    print("-"*70)

    # Constraints:
    # - a2 ≠ h1 (red), so a2 must be green or blue
    # - a4 ≠ h4 (blue), so a4 must be red or green
    # - a5 ≠ h4 (blue), so a5 must be red or green
    # - a1 ≠ a2 (internal edge)
    # - a3 ≠ a4 (internal edge)

    print("\nConstraints:")
    print("  a2 != h1=red  ->  a2 in {green, blue}")
    print("  a4 != h4=blue  ->  a4 in {red, green}")
    print("  a5 != h4=blue  ->  a5 in {red, green}")
    print("  a1 != a2  (internal edge)")
    print("  a3 != a4  (internal edge)")

    print("\nTrying manual assignment:")
    manual_solution = {
        "h1": "red",
        "h4": "blue",
        "a1": "red",
        "a2": "green",   # a2 ≠ red (h1), a2 ≠ red (a1) [OK]
        "a3": "blue",
        "a4": "red",     # a4 ≠ blue (h4), a4 ≠ blue (a3) [OK]
        "a5": "green",   # a5 ≠ blue (h4) [OK]
    }

    for node in ["a1", "a2", "a3", "a4", "a5"]:
        print(f"  {node} = {manual_solution[node]}")

    # Evaluate this assignment
    penalty = problem.evaluate_assignment(manual_solution)
    print(f"\nPenalty for manual solution: {penalty}")

    if penalty == 0:
        print("[OK] MANUAL SOLUTION IS VALID!")
    else:
        print("[FAIL] Manual solution has conflicts")
        # Check which edges have conflicts
        print("\nChecking edges:")
        for u, v in problem.edges:
            if u in manual_solution and v in manual_solution:
                if manual_solution[u] == manual_solution[v]:
                    print(f"  CONFLICT: {u}={manual_solution[u]} -- {v}={manual_solution[v]}")
                else:
                    print(f"  OK: {u}={manual_solution[u]} -- {v}={manual_solution[v]}")

    # Now test if Agent1's _best_local_assignment_for() finds a valid solution
    print("\n" + "="*70)
    print("AGENT1's _best_local_assignment_for() TEST:")
    print("="*70)

    # Create Agent1
    owners = {}
    for i in range(1, 6):
        owners[f"a{i}"] = "Agent1"
        owners[f"h{i}"] = "Human"
        owners[f"b{i}"] = "Agent2"

    # Don't need real LLM for this test
    class DummyCommLayer:
        def __init__(self):
            pass

    agent1 = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=DummyCommLayer(),
        local_nodes=["a1", "a2", "a3", "a4", "a5"],
        owners=owners,
        algorithm="maxsum",  # Use exhaustive search to be sure
        message_type="constraints"
    )

    # Set boundary beliefs
    agent1.neighbour_assignments = {
        "h1": "red",
        "h4": "blue"
    }

    print(f"\nAgent1's boundary beliefs: {agent1.neighbour_assignments}")

    # Test _best_local_assignment_for()
    best_pen, best_assign = agent1._best_local_assignment_for(boundary)

    print(f"\nAgent's _best_local_assignment_for() result:")
    print(f"  Penalty: {best_pen}")
    print(f"  Assignment: {best_assign}")

    if best_pen < 1e-6:
        print("[OK] AGENT FOUND A VALID SOLUTION!")
    else:
        print("[FAIL] AGENT CLAIMS NO VALID SOLUTION EXISTS")
        print("\nThis is the BUG - manual solution works but agent can't find it!")

    # Test _compute_valid_boundary_configs_with_constraints()
    print("\n" + "="*70)
    print("AGENT1's _compute_valid_boundary_configs_with_constraints() TEST:")
    print("="*70)

    # First, set the constraint that h1=red is required
    agent1._human_stated_constraints = {
        "h1": {"required": "red", "forbidden": []}
    }

    print(f"\nAgent1's human constraints: {agent1._human_stated_constraints}")

    valid_configs = agent1._compute_valid_boundary_configs_with_constraints(max_configs=20)

    print(f"\nValid boundary configurations found: {len(valid_configs)}")
    for i, config in enumerate(valid_configs, 1):
        print(f"  {i}. {config}")

    if valid_configs:
        h1_red_configs = [c for c in valid_configs if c.get("h1") == "red"]
        print(f"\nConfigs with h1=red: {len(h1_red_configs)}")
        if h1_red_configs:
            print("[OK] AGENT FOUND h1=red CONFIGURATIONS!")
            for config in h1_red_configs:
                print(f"  {config}")
        else:
            print("[FAIL] BUG: No h1=red configs found even though manual solution exists!")
    else:
        print("[FAIL] BUG: Agent found ZERO valid configs even though manual solution exists!")

    # Final summary
    print("\n" + "="*70)
    print("SUMMARY:")
    print("="*70)
    print(f"Manual solution valid: {penalty == 0}")
    print(f"Agent's _best_local_assignment_for() finds solution: {best_pen < 1e-6}")
    print(f"Agent's _compute_valid_boundary_configs finds h1=red: {len([c for c in valid_configs if c.get('h1') == 'red']) > 0}")

    if penalty == 0 and best_pen >= 1e-6:
        print("\n[BUG] BUG CONFIRMED: Manual solution works but agent can't find it!")
        print("   Problem is in _best_local_assignment_for() implementation")
    elif penalty == 0 and best_pen < 1e-6 and not any(c.get('h1') == 'red' for c in valid_configs):
        print("\n[BUG] BUG CONFIRMED: Agent can find solution but enumeration misses it!")
        print("   Problem is in _compute_valid_boundary_configs_with_constraints()")
    else:
        print("\n[OK] Everything seems to work correctly")


if __name__ == "__main__":
    test_manual_solution()
