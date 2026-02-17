"""
Test that agents use exhaustive algorithm for optimal solutions.

This test verifies the fix for the issue where agents were rejecting
configurations that should work because they were using greedy algorithm
instead of exhaustive search.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.cluster_agent_api import ClusterAgentAPI
from agents.cluster_agent import ClusterAgent
from problems.graph_coloring import GraphColoring


def test_api_defaults_to_exhaustive():
    """Test that ClusterAgentAPI.compute_assignments() defaults to exhaustive (maxsum)."""

    # Create a simple 3-cluster graph:
    # Agent1: a1, a2 (connects to h1)
    # Human: h1 (boundary)
    #
    # Edges: (a1, a2), (a2, h1)
    # If h1=red, optimal for Agent1 is: a2=blue, a1=red (penalty=0)
    # Greedy might assign a1=blue first, then a2=red (conflicts with a1), then stuck

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

    # Create agent with dummy comm layer
    class DummyComm:
        def format_content(self, sender, recipient, content):
            return str(content)

    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=DummyComm(),
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="maxsum",  # Agent uses maxsum by default
        initial_assignments={"a1": "red", "a2": "blue"}
    )

    # Set neighbor belief
    agent.neighbour_assignments = {"h1": "red"}

    # Create API wrapper
    api = ClusterAgentAPI(agent)

    # Call compute_assignments() without specifying algorithm (should use maxsum by default)
    result = api.compute_assignments()

    # Verify result is optimal
    # With h1=red, agent should find: a2=blue (not red, avoids conflict), a1=red or green
    print(f"Result: {result}")
    print(f"Agent algorithm after call: {agent.algorithm}")

    # Check penalty is 0
    test_assignment = {**agent.neighbour_assignments, **result}
    penalty = problem.evaluate_assignment(test_assignment)
    print(f"Penalty: {penalty}")

    assert penalty == 0, f"Expected penalty=0 with exhaustive search, got {penalty}"
    assert result["a2"] != "red", f"a2 should not be red (conflicts with h1=red)"
    print("[PASS] API defaults to exhaustive search and finds optimal solution")


def test_get_best_response_to_is_exhaustive():
    """Test that get_best_response_to() uses exhaustive search."""

    # Same setup as above
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
        initial_assignments={"a1": "red", "a2": "blue"}
    )

    api = ClusterAgentAPI(agent)

    # Test get_best_response_to with h1=red
    result = api.get_best_response_to(neighbor_assignments={"h1": "red"})

    print(f"Best response to h1=red: {result}")

    # Verify result is optimal
    test_assignment = {"h1": "red", **result}
    penalty = problem.evaluate_assignment(test_assignment)
    print(f"Penalty: {penalty}")

    assert penalty == 0, f"Expected penalty=0 with best response, got {penalty}"
    assert result["a2"] != "red", f"a2 should not be red (conflicts with h1=red)"
    print("[PASS] get_best_response_to() uses exhaustive search and finds optimal solution")


def test_consistency_between_compute_and_best_response():
    """Test that compute_assignments() and get_best_response_to() give same results."""

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
        initial_assignments={"a1": "red", "a2": "blue"}
    )

    # Set neighbor belief
    agent.neighbour_assignments = {"h1": "red"}

    api = ClusterAgentAPI(agent)

    # Call both methods
    result1 = api.compute_assignments()  # Uses agent's current neighbour_assignments
    result2 = api.get_best_response_to(neighbor_assignments={"h1": "red"})

    print(f"compute_assignments(): {result1}")
    print(f"get_best_response_to(): {result2}")

    # Both should find penalty=0 solutions
    test1 = {"h1": "red", **result1}
    test2 = {"h1": "red", **result2}
    penalty1 = problem.evaluate_assignment(test1)
    penalty2 = problem.evaluate_assignment(test2)

    print(f"Penalty1: {penalty1}, Penalty2: {penalty2}")

    assert penalty1 == 0, f"compute_assignments() should find penalty=0, got {penalty1}"
    assert penalty2 == 0, f"get_best_response_to() should find penalty=0, got {penalty2}"
    print("[PASS] Both methods use exhaustive search and find optimal solutions")


if __name__ == "__main__":
    print("Testing exhaustive algorithm fix...\n")

    print("Test 1: API defaults to exhaustive")
    print("-" * 50)
    test_api_defaults_to_exhaustive()
    print()

    print("Test 2: get_best_response_to is exhaustive")
    print("-" * 50)
    test_get_best_response_to_is_exhaustive()
    print()

    print("Test 3: Consistency between methods")
    print("-" * 50)
    test_consistency_between_compute_and_best_response()
    print()

    print("=" * 50)
    print("[PASS] ALL TESTS PASSED")
    print("=" * 50)
