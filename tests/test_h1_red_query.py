"""
Test that agent correctly handles hypothetical query:
"I have to make h1 red. Is this something you'll be able to plan around?"

Expected behavior:
- Extract constraint: h1 must be red
- Enumerate alternatives respecting that constraint
- Return ONLY configs where h1=red (with different h4 values)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring


def create_problem():
    """Create the exact problem from the user's transcript"""
    nodes = ["a1", "a2", "a3", "a4", "a5", "h1", "h2", "h3", "h4", "h5", "b1", "b2", "b3", "b4", "b5"]

    edges = [
        # Agent1 - Human boundary
        ("a2", "h1"), ("a4", "h4"), ("a5", "h4"),
        # Human - Agent2 boundary
        ("h2", "b2"), ("h5", "b2"), ("h5", "b5"),
        # Internal edges
        ("a1", "a2"), ("a3", "a4"),
        ("h1", "h2"), ("h3", "h4"), ("h4", "h5"),
        ("b1", "b2"), ("b3", "b4"),
    ]

    domain = ["red", "green", "blue"]
    return GraphColoring(nodes, edges, domain)


def test_h1_red_query():
    """Test the hypothetical query handling"""
    print("="*70)
    print("TEST: Hypothetical query with constraint")
    print("Query: 'I have to make h1 red. Is this something you'll be able")
    print("       to plan around?'")
    print("="*70)

    problem = create_problem()

    # Create owners
    owners = {}
    for i in range(1, 6):
        owners[f"a{i}"] = "Agent1"
        owners[f"h{i}"] = "Human"
        owners[f"b{i}"] = "Agent2"

    # Dummy comm layer (we don't need LLM for this test)
    class DummyCommLayer:
        def parse_content(self, sender, recipient, content):
            return content

        def classify_message(self, sender, recipient, history, text):
            class Classification:
                def __init__(self):
                    self.primary = "QUERY"
                    self.extracted_nodes = []
                    self.extracted_colors = []
                    self.raw_text = text
            return Classification()

    # Create Agent1
    agent1 = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=DummyCommLayer(),
        local_nodes=["a1", "a2", "a3", "a4", "a5"],
        owners=owners,
        algorithm="maxsum",
        message_type="constraints"
    )

    # Set initial boundary (h1=red, h4=red - which doesn't work)
    agent1.neighbour_assignments = {
        "h1": "red",
        "h4": "red"
    }

    print(f"\nInitial boundary: {agent1.neighbour_assignments}")

    # Verify this config doesn't work
    pen, _ = agent1._best_local_assignment_for(agent1.neighbour_assignments)
    print(f"Penalty with h1=red, h4=red: {pen}")

    # Now send the hypothetical query
    print("\n" + "-"*70)
    print("STEP 1: Human asks hypothetical query")
    print("-"*70)

    query = "I have to make h1 red. Is this something you'll be able to plan around?"
    print(f"\nHuman: {query}")

    msg = Message(sender="Human", recipient="Agent1", content=query)
    agent1.receive(msg)

    # Check if constraint was extracted
    print(f"\nAgent's _human_stated_constraints: {agent1._human_stated_constraints}")

    if "h1" in agent1._human_stated_constraints:
        h1_constraint = agent1._human_stated_constraints["h1"]
        if h1_constraint.get("required") == "red":
            print("[OK] Constraint extracted: h1 must be red")
        else:
            print(f"[FAIL] Wrong constraint: {h1_constraint}")
    else:
        print("[FAIL] Constraint NOT extracted!")

    # Now check if enumeration respects the constraint
    print("\n" + "-"*70)
    print("STEP 2: Enumerate alternatives respecting constraint")
    print("-"*70)

    result = agent1._enumerate_boundary_options()
    options = result.get("options", [])

    print(f"\nTotal options found: {len(options)}")
    print(f"Feasible options: {result.get('feasible_count', 0)}")

    # Check if all options have h1=red
    h1_red_count = sum(1 for o in options if o["boundary_config"].get("h1") == "red")
    h1_other_count = len(options) - h1_red_count

    print(f"\nOptions with h1=red: {h1_red_count}")
    print(f"Options with h1!=red: {h1_other_count}")

    if h1_other_count > 0:
        print("\n[FAIL] Found options that violate constraint h1=red!")
        for o in options:
            if o["boundary_config"].get("h1") != "red":
                print(f"  {o['boundary_config']} - VIOLATES CONSTRAINT")
    else:
        print("\n[OK] All options respect h1=red constraint!")

    # Show the feasible options
    print("\nFeasible options with h1=red:")
    feasible = [o for o in options if o["feasible"]]
    if feasible:
        for i, o in enumerate(feasible, 1):
            config = o["boundary_config"]
            print(f"  {i}. h1={config['h1']}, h4={config['h4']} (penalty={o['penalty']:.2f})")
    else:
        print("  [FAIL] NO FEASIBLE OPTIONS FOUND!")

    # Final verdict
    print("\n" + "="*70)
    print("SUMMARY:")
    print("="*70)

    success = True

    if "h1" not in agent1._human_stated_constraints or \
       agent1._human_stated_constraints["h1"].get("required") != "red":
        print("[FAIL] Constraint 'h1 must be red' was NOT extracted")
        success = False
    else:
        print("[OK] Constraint 'h1 must be red' extracted correctly")

    if h1_other_count > 0:
        print(f"[FAIL] Enumeration returned {h1_other_count} options that violate h1=red")
        success = False
    else:
        print("[OK] All enumerated options respect h1=red constraint")

    if not feasible:
        print("[FAIL] No feasible options found (should have h1=red, h4=blue/green)")
        success = False
    else:
        print(f"[OK] Found {len(feasible)} feasible options where h1=red")

    if success:
        print("\n[SUCCESS] Agent correctly handles hypothetical query!")
        return 0
    else:
        print("\n[FAILURE] Agent still has bugs in handling hypothetical queries")
        return 1


if __name__ == "__main__":
    exit_code = test_h1_red_query()
    sys.exit(exit_code)
