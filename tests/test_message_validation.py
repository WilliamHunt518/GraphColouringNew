"""
Test message validation: partial observability and specificity.

This test verifies that agents correctly validate messages to:
1. Block mentions of invisible neighbor nodes (partial observability)
2. Block vague messages without specific requests
3. Block requests to change agent's own nodes
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.cluster_agent_api import ClusterAgentAPI
from problems.graph_coloring import GraphColoring


def test_partial_observability_validation():
    """Test that validation blocks messages mentioning invisible nodes."""

    # Create graph with 3 clusters:
    # Agent2: b1, b2
    # Human: h1, h2, h3
    # Edges: (b1, h1), (b2, h3)
    # Agent2 can see: h1, h3 (has edges)
    # Agent2 CANNOT see: h2 (no edge to Agent2's cluster)

    nodes = ["b1", "b2", "h1", "h2", "h3"]
    edges = [("b1", "h1"), ("b2", "h3"), ("h1", "h2"), ("h2", "h3")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(
        nodes=nodes,
        edges=edges,
        domain=domain,
        conflict_penalty=10.0
    )

    owners = {
        "b1": "Agent2",
        "b2": "Agent2",
        "h1": "Human",
        "h2": "Human",
        "h3": "Human"
    }

    class DummyComm:
        def format_content(self, sender, recipient, content):
            return str(content)

    agent = ToolCallingClusterAgent(
        name="Agent2",
        problem=problem,
        comm_layer=DummyComm(),
        local_nodes=["b1", "b2"],
        owners=owners,
        algorithm="maxsum"
    )

    agent.neighbour_assignments = {"h1": "red", "h2": "blue", "h3": "red"}

    # Test Case 1: Valid message (mentions only visible nodes)
    print("\n" + "="*50)
    print("Test 1: Valid message (only visible nodes)")
    print("="*50)

    valid_content = {
        "message_type": "proposal",
        "reason": "Could you change h1 from red to blue and h3 from red to green?",
        "requested_changes": {"h1": "blue", "h3": "green"}
    }

    is_valid, error = agent._validate_message_specificity(valid_content)
    print(f"Content: {valid_content}")
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Error: {error}")

    assert is_valid, f"Valid message was rejected: {error}"
    print("[PASS] Valid message accepted")

    # Test Case 2: Invalid message (mentions invisible node h2)
    print("\n" + "="*50)
    print("Test 2: Invalid message (mentions invisible h2)")
    print("="*50)

    invalid_content = {
        "message_type": "proposal",
        "reason": "Could you change h1 to blue and h2 to green?",  # h2 is invisible!
        "requested_changes": {"h1": "blue", "h2": "green"}
    }

    is_valid, error = agent._validate_message_specificity(invalid_content)
    print(f"Content: {invalid_content}")
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Error: {error}")

    assert not is_valid, "Invalid message (invisible node) was accepted!"
    assert "PARTIAL OBSERVABILITY VIOLATION" in error, f"Wrong error message: {error}"
    assert "h2" in error, f"Error should mention h2: {error}"
    print("[PASS] Invalid message blocked (mentions invisible h2)")


def test_vague_message_validation():
    """Test that validation blocks vague messages."""

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

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=DummyComm(),
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="maxsum"
    )

    agent.neighbour_assignments = {"h1": "red"}

    # Test Case 1: Specific message
    print("\n" + "="*50)
    print("Test 3: Specific message (good)")
    print("="*50)

    specific_content = {
        "message_type": "proposal",
        "reason": "Could you change h1 from red to blue?",
        "requested_changes": {"h1": "blue"}
    }

    is_valid, error = agent._validate_message_specificity(specific_content)
    print(f"Content: {specific_content}")
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Error: {error}")

    assert is_valid, f"Specific message was rejected: {error}"
    print("[PASS] Specific message accepted")

    # Test Case 2: Vague message
    print("\n" + "="*50)
    print("Test 4: Vague message (bad)")
    print("="*50)

    vague_content = {
        "message_type": "proposal",
        "reason": "Could you make a change to reduce conflicts?",  # Vague!
        "requested_changes": {}
    }

    is_valid, error = agent._validate_message_specificity(vague_content)
    print(f"Content: {vague_content}")
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Error: {error}")

    assert not is_valid, "Vague message was accepted!"
    assert "VAGUE MESSAGE" in error or "make a change" in error, f"Wrong error message: {error}"
    print("[PASS] Vague message blocked")


def test_ownership_validation():
    """Test that validation blocks requests to change agent's own nodes."""

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

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=DummyComm(),
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="maxsum"
    )

    agent.neighbour_assignments = {"h1": "red"}

    # Test Case: Request to change own node
    print("\n" + "="*50)
    print("Test 5: Request to change own node (bad)")
    print("="*50)

    ownership_violation = {
        "message_type": "proposal",
        "reason": "Could you change a1 from red to blue?",  # a1 is agent's own node!
        "requested_changes": {"a1": "blue"}
    }

    is_valid, error = agent._validate_message_specificity(ownership_violation)
    print(f"Content: {ownership_violation}")
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Error: {error}")

    assert not is_valid, "Ownership violation was accepted!"
    assert "OWNERSHIP VIOLATION" in error, f"Wrong error message: {error}"
    assert "a1" in error, f"Error should mention a1: {error}"
    print("[PASS] Ownership violation blocked")


if __name__ == "__main__":
    print("Testing message validation (partial observability & specificity)...\n")

    test_partial_observability_validation()
    test_vague_message_validation()
    test_ownership_validation()

    print("\n" + "="*50)
    print("[PASS] ALL VALIDATION TESTS PASSED")
    print("="*50)
    print("\nValidation now blocks:")
    print("1. Messages mentioning invisible neighbor nodes (partial observability)")
    print("2. Vague messages without specific requests")
    print("3. Requests to change agent's own nodes (ownership violations)")
