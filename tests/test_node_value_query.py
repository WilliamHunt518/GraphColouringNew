"""
Test to verify "what could I set X to?" queries work correctly.

This test verifies that when the human asks "what could I set node X to?",
the agent searches for valid values and responds appropriately.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.cluster_agent import ClusterAgent
from problems.graph_coloring import GraphColoring


def test_node_value_query():
    """Test that agent can answer 'what could I set X to?' queries"""

    # Create a constrained graph
    nodes = ["a1", "a2", "h1", "h4"]
    edges = [
        ("a1", "h1"),  # a1 must differ from h1
        ("a2", "h4"),  # a2 must differ from h4
    ]
    domain = ["red", "green", "blue"]
    problem = GraphColoring(nodes, edges, domain)

    # Agent owns a1, a2
    # Human owns h1, h4
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h4": "Human"}

    # Create agent
    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=None,
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="greedy",
        message_type="constraints",
        counterfactual_utils=True
    )

    print("=" * 60)
    print("Testing Node Value Query Handler")
    print("=" * 60)

    # Setup: h1=red, h4=red
    agent.neighbour_assignments = {"h1": "red", "h4": "red"}
    agent.compute_assignments()

    print(f"\nInitial state:")
    print(f"  Boundary: h1=red, h4=red")
    print(f"  Agent assignments: {agent.assignments}")

    # Calculate penalty
    full_assignment = {**agent.neighbour_assignments, **agent.assignments}
    penalty = problem.evaluate_assignment(full_assignment)
    print(f"  Penalty: {penalty:.2f}")

    # Simulate human asking: "What could I set h4 to?"
    print(f"\n---")
    print(f"Human asks: 'h1 must be red. What could I set h4 to that would work for you?'")
    print(f"---")

    # Create a mock classification result
    class MockClassification:
        def __init__(self):
            self.primary = "QUERY"
            self.confidence = 0.95
            self.raw_text = "h1 must be red. What could I set h4 to that would work for you?"
            self.extracted_nodes = ["h4"]
            self.extracted_colors = []

    classification = MockClassification()

    # Call the query handler
    result = agent._handle_query(classification)

    print(f"\nQuery handler result:")
    print(f"  Query type: {result.get('query_type')}")
    if result.get('query_type') == 'node_value_search':
        print(f"  Query node: {result.get('query_node')}")
        print(f"  Fixed boundary: {result.get('fixed_boundary')}")
        print(f"  Valid colors: {result.get('valid_colors')}")
        print(f"  Message: {result.get('message')}")

        valid_colors = result.get('valid_colors', [])
        if len(valid_colors) > 0:
            print(f"\n✓ SUCCESS: Found {len(valid_colors)} valid value(s) for h4: {valid_colors}")

            # Verify each suggested color actually works
            print(f"\nVerifying each suggestion:")
            for color in valid_colors:
                test_boundary = {"h1": "red", "h4": color}
                agent.neighbour_assignments = test_boundary
                agent.compute_assignments()
                test_assignment = {**agent.neighbour_assignments, **agent.assignments}
                test_penalty = problem.evaluate_assignment(test_assignment)
                status = "✓ WORKS" if test_penalty < 1e-6 else f"✗ FAILS (penalty={test_penalty:.2f})"
                print(f"  h4={color}: {status}")

            return True
        else:
            print(f"\n✗ FAILURE: No valid values found for h4")
            return False
    else:
        print(f"\n✗ FAILURE: Wrong query type: {result.get('query_type')}")
        return False


if __name__ == "__main__":
    success = test_node_value_query()
    sys.exit(0 if success else 1)
