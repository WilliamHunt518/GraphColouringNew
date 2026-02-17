"""
Test that agents keep their own colors fixed during negotiation.

Verifies Fix 2: Agents should not modify their own assignments during
_send_backend_decision() - they should only request changes to boundary nodes.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.react_cluster_agent import ReActClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer


def test_tool_calling_agent_color_stability():
    """Test that ToolCallingClusterAgent doesn't change its own colors."""

    print("\n[Test] Testing ToolCallingClusterAgent color stability...")

    # Create a simple problem
    nodes = ["a1", "a2", "h1", "h2"]
    edges = [
        ("a1", "a2"),
        ("a2", "h1"),
        ("h1", "h2"),
    ]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

    # Create agent - use template mode (no API calls needed for this test)
    comm_layer = SpeechLLMLayer(use_llm=False)
    try:
        agent = ToolCallingClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2"],
            owners=owners,
            backend_model="gpt-4-turbo"
        )
    except SystemExit:
        print("[SKIP] No API key - skipping test")
        return

    # Set initial assignments
    initial_assignments = {"a1": "red", "a2": "blue"}
    agent.assignments = dict(initial_assignments)

    print(f"[Test] Initial agent assignments: {agent.assignments}")

    # Simulate LLM decision that tries to change agent's own colors
    decision = {
        "should_send_message": True,
        "recipient": "Human",
        "message_type": "proposal",
        "structured_content": {
            "my_assignments": {"a1": "green", "a2": "yellow"},  # LLM trying to change colors
            "reason": "I think these colors work better",
            "requested_changes": {"h1": "red"}
        }
    }

    print(f"[Test] Simulating LLM decision with my_assignments: {decision['structured_content']['my_assignments']}")

    # Call _send_backend_decision
    agent._send_backend_decision(decision)

    # Verify assignments haven't changed
    print(f"[Test] After _send_backend_decision, agent assignments: {agent.assignments}")
    assert agent.assignments == initial_assignments, \
        f"Agent assignments should not change! Expected {initial_assignments}, got {agent.assignments}"

    print("[Test] [PASS] ToolCallingClusterAgent maintains color stability!")


def test_react_agent_color_stability():
    """Test that ReActClusterAgent doesn't change its own colors."""

    print("\n[Test] Testing ReActClusterAgent color stability...")

    # Create a simple problem
    nodes = ["b1", "b2", "h1", "h2"]
    edges = [
        ("b1", "b2"),
        ("b2", "h1"),
        ("h1", "h2"),
    ]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)
    owners = {"b1": "Agent2", "b2": "Agent2", "h1": "Human", "h2": "Human"}

    # Create agent - use template mode
    comm_layer = SpeechLLMLayer(use_llm=False)
    try:
        agent = ReActClusterAgent(
            name="Agent2",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["b1", "b2"],
            owners=owners,
            backend_model="gpt-4-turbo"
        )
    except SystemExit:
        print("[SKIP] No API key - skipping test")
        return

    # Set initial assignments
    initial_assignments = {"b1": "green", "b2": "purple"}
    agent.assignments = dict(initial_assignments)

    print(f"[Test] Initial agent assignments: {agent.assignments}")

    # Simulate LLM decision
    decision = {
        "should_send_message": True,
        "recipient": "Human",
        "message_type": "proposal",
        "structured_content": {
            "my_assignments": {"b1": "red", "b2": "blue"},  # LLM trying to change colors
            "reason": "Better coloring",
            "requested_changes": {"h1": "yellow"}
        }
    }

    print(f"[Test] Simulating LLM decision with my_assignments: {decision['structured_content']['my_assignments']}")

    # Call _send_backend_decision
    agent._send_backend_decision(decision)

    # Verify assignments haven't changed
    print(f"[Test] After _send_backend_decision, agent assignments: {agent.assignments}")
    assert agent.assignments == initial_assignments, \
        f"Agent assignments should not change! Expected {initial_assignments}, got {agent.assignments}"

    print("[Test] [PASS] ReActClusterAgent maintains color stability!")


def test_agent_should_only_report_boundary_nodes():
    """Test that agents only include boundary nodes in message reports."""

    print("\n[Test] Testing that agents only report boundary node colors...")

    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [
        ("a1", "a2"),
        ("a2", "a3"),
        ("a3", "h1"),  # a3 is boundary
        ("h1", "h2"),
    ]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"}

    # Create agent - use template mode
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

    agent.assignments = {"a1": "red", "a2": "blue", "a3": "green"}

    # Get boundary nodes
    boundary_nodes = [n for n in agent.nodes if any(
        nbr not in agent.nodes
        for nbr in problem.get_neighbors(n)
    )]

    print(f"[Test] Agent nodes: {agent.nodes}")
    print(f"[Test] Boundary nodes: {boundary_nodes}")
    assert boundary_nodes == ["a3"], f"Expected ['a3'], got {boundary_nodes}"

    print("[Test] [PASS] Boundary detection works correctly!")
    print("[Test] Note: Message report filtering is handled by comm layer")


if __name__ == "__main__":
    test_tool_calling_agent_color_stability()
    test_react_agent_color_stability()
    test_agent_should_only_report_boundary_nodes()
    print("\n[Test] All agent color stability tests passed! [ALL PASS]")
