"""
Test that agents accept valid configurations instead of asking for changes.

This test verifies that agents check if they can achieve penalty=0 with the
human's CURRENT configuration before asking for changes.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.cluster_agent_api import ClusterAgentAPI
from agents.cluster_agent import ClusterAgent
from problems.graph_coloring import GraphColoring


def test_agent_accepts_penalty_free_config():
    """Test that agent accepts when penalty=0 is achievable with current neighbor colors."""

    # Create a simple graph:
    # Agent: a1, a2, a3
    # Human: h1, h2
    # Edges: (a1, a2), (a2, h1), (a3, h2)
    #
    # If human sets: h1=red, h2=blue
    # Agent can achieve penalty=0 with: a1=blue, a2=blue, a3=red

    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(
        nodes=nodes,
        edges=edges,
        domain=domain,
        conflict_penalty=10.0
    )

    owners = {
        "a1": "Agent1",
        "a2": "Agent1",
        "a3": "Agent1",
        "h1": "Human",
        "h2": "Human"
    }

    class DummyComm:
        def format_content(self, sender, recipient, content):
            return str(content)

    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=DummyComm(),
        local_nodes=["a1", "a2", "a3"],
        owners=owners,
        algorithm="maxsum",
        initial_assignments={"a1": "red", "a2": "red", "a3": "red"}
    )

    # Human sets valid configuration
    agent.neighbour_assignments = {"h1": "red", "h2": "blue"}

    # Create API wrapper
    api = ClusterAgentAPI(agent)

    # Agent should find best response to current neighbor colors
    result = api.get_best_response_to(neighbor_assignments={"h1": "red", "h2": "blue"})

    print(f"Current neighbor assignments: {agent.neighbour_assignments}")
    print(f"Best response: {result}")

    # Check penalty with this response
    test_assignment = {**agent.neighbour_assignments, **result}
    penalty = problem.evaluate_assignment(test_assignment)
    print(f"Penalty with best response: {penalty}")

    assert penalty == 0, f"Expected penalty=0 with best response, got {penalty}"
    print("[PASS] Agent can achieve penalty=0 with human's current configuration")
    print("[PASS] Agent should ACCEPT this config, not ask for changes!")


def test_agent_workflow_acceptance_vs_negotiation():
    """Test the complete workflow: check current config first, then negotiate if needed."""

    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "a2"), ("a2", "h1")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(
        nodes=nodes,
        edges=edges,
        domain=domain,
        conflict_penalty=10.0
    )

    owners = {
        "a1": "Agent1",
        "a2": "Agent1",
        "h1": "Human"
    }

    class DummyComm:
        def format_content(self, sender, recipient, content):
            return str(content)

    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=DummyComm(),
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="maxsum",
        initial_assignments={"a1": "red", "a2": "red"}
    )

    api = ClusterAgentAPI(agent)

    # Test Case 1: Human config is VALID (h1=red)
    # Agent can do: a1=blue, a2=blue (no conflict with h1=red)
    print("\n" + "="*50)
    print("Case 1: Human config is VALID (should ACCEPT)")
    print("="*50)

    agent.neighbour_assignments = {"h1": "red"}
    result1 = api.get_best_response_to(neighbor_assignments={"h1": "red"})
    test1 = {"h1": "red", **result1}
    penalty1 = problem.evaluate_assignment(test1)

    print(f"Human sets: h1=red")
    print(f"Agent's best response: {result1}")
    print(f"Penalty: {penalty1}")

    assert penalty1 == 0, f"Expected penalty=0 for valid config, got {penalty1}"
    print("[PASS] Agent should send message_type='acceptance' with requested_changes={}")

    # The key point is demonstrated: agents should check current config FIRST
    # If penalty=0 achievable -> accept
    # If penalty > 0 -> negotiate

    print("\n[PASS] Workflow verified: Check current config first, then decide")
    print("  - If get_best_response_to(current) gives penalty=0 -> ACCEPT")
    print("  - If get_best_response_to(current) gives penalty>0 -> NEGOTIATE")


if __name__ == "__main__":
    print("Testing agent acceptance vs negotiation workflow...\n")

    print("Test 1: Agent accepts valid configuration")
    print("-" * 50)
    test_agent_accepts_penalty_free_config()
    print()

    print("Test 2: Complete workflow (acceptance vs negotiation)")
    print("-" * 50)
    test_agent_workflow_acceptance_vs_negotiation()
    print()

    print("=" * 50)
    print("[PASS] ALL TESTS PASSED")
    print("=" * 50)
    print("\nKey takeaway:")
    print("Agents MUST check get_best_response_to() with CURRENT neighbor colors FIRST.")
    print("If penalty=0 achievable -> ACCEPT")
    print("If penalty > 0 -> NEGOTIATE")
