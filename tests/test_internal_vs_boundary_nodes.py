"""
Test that agents can modify internal nodes but not boundary nodes.

Verifies the corrected Fix 2: Agents should:
- Freely modify internal nodes (non-boundary)
- NOT modify boundary nodes (require coordination)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer


def test_internal_node_modification_allowed():
    """Test that agents can modify their internal nodes."""

    print("\n[Test] Testing internal node modification...")

    # Create a graph where agent has internal + boundary nodes
    # a1 - a2 - a3 - h1
    # a1, a2 are internal (no external edges from a1, and a2 only connects internally)
    # a3 is boundary (connects to h1)
    nodes = ["a1", "a2", "a3", "h1"]
    edges = [
        ("a1", "a2"),  # Internal edge
        ("a2", "a3"),  # Internal edge
        ("a3", "h1"),  # Boundary edge
    ]
    domain = ["red", "blue", "green"]
    problem = GraphColoring(nodes, edges, domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human"}

    # Create agent
    comm_layer = SpeechLLMLayer(use_llm=False)
    try:
        agent = ToolCallingClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2", "a3"],
            owners=owners,
            backend_model="gpt-4-turbo"
        )
    except SystemExit:
        print("[SKIP] No API key - skipping test")
        return

    # Set initial assignments
    agent.assignments = {"a1": "red", "a2": "red", "a3": "blue"}

    print(f"[Test] Initial assignments: {agent.assignments}")
    print(f"[Test] Agent nodes: {agent.nodes}")

    # Identify boundary nodes
    boundary = []
    for node in agent.nodes:
        for neighbor in problem.get_neighbors(node):
            if neighbor not in agent.nodes:
                boundary.append(node)
                break

    print(f"[Test] Boundary nodes: {boundary}")
    internal = [n for n in agent.nodes if n not in boundary]
    print(f"[Test] Internal nodes: {internal}")

    # Simulate LLM decision that modifies internal nodes (a1, a2) and tries to modify boundary (a3)
    decision = {
        "should_send_message": True,
        "recipient": "Human",
        "message_type": "proposal",
        "structured_content": {
            "my_assignments": {
                "a1": "blue",   # Internal - should be applied
                "a2": "green",  # Internal - should be applied
                "a3": "red"     # Boundary - should NOT be applied
            },
            "reason": "Testing internal vs boundary",
        }
    }

    print(f"\n[Test] Simulating LLM decision with my_assignments: {decision['structured_content']['my_assignments']}")

    # Call _send_backend_decision
    agent._send_backend_decision(decision)

    # Verify results
    print(f"\n[Test] After _send_backend_decision, agent assignments: {agent.assignments}")

    # Internal nodes should be updated
    assert agent.assignments["a1"] == "blue", f"a1 should be blue (internal node), got {agent.assignments['a1']}"
    assert agent.assignments["a2"] == "green", f"a2 should be green (internal node), got {agent.assignments['a2']}"

    # Boundary node should NOT be updated
    assert agent.assignments["a3"] == "blue", f"a3 should still be blue (boundary node), got {agent.assignments['a3']}"

    print("[Test] [PASS] Internal nodes modified, boundary nodes protected!")


def test_boundary_node_identification():
    """Test that boundary nodes are correctly identified."""

    print("\n[Test] Testing boundary node identification...")

    # Agent1: a1, a2, a3, a4
    # Graph: a1-a2-a3-h1, a4-h2
    # Boundaries: a3 (connects to h1), a4 (connects to h2)
    # Internal: a1, a2
    nodes = ["a1", "a2", "a3", "a4", "h1", "h2"]
    edges = [
        ("a1", "a2"),
        ("a2", "a3"),
        ("a3", "h1"),
        ("a4", "h2"),
    ]
    domain = ["red", "blue", "green"]
    problem = GraphColoring(nodes, edges, domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "a4": "Agent1", "h1": "Human", "h2": "Human"}

    comm_layer = SpeechLLMLayer(use_llm=False)
    try:
        agent = ToolCallingClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2", "a3", "a4"],
            owners=owners,
            backend_model="gpt-4-turbo"
        )
    except SystemExit:
        print("[SKIP] No API key - skipping test")
        return

    agent.assignments = {"a1": "red", "a2": "blue", "a3": "green", "a4": "red"}

    # Identify boundary nodes
    boundary = []
    for node in agent.nodes:
        for neighbor in problem.get_neighbors(node):
            if neighbor not in agent.nodes:
                boundary.append(node)
                break

    print(f"[Test] Agent nodes: {agent.nodes}")
    print(f"[Test] Boundary nodes: {boundary}")

    assert set(boundary) == {"a3", "a4"}, f"Expected boundaries: a3, a4; got: {boundary}"

    internal = [n for n in agent.nodes if n not in boundary]
    print(f"[Test] Internal nodes: {internal}")

    assert set(internal) == {"a1", "a2"}, f"Expected internal: a1, a2; got: {internal}"

    print("[Test] [PASS] Boundary identification works correctly!")


if __name__ == "__main__":
    test_boundary_node_identification()
    test_internal_node_modification_allowed()
    print("\n[Test] All internal vs boundary tests passed! [ALL PASS]")
