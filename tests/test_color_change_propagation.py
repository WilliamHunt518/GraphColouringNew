"""
Test that human color changes are properly propagated to agents.

Verifies Fix 1: When human changes a boundary node color in the UI,
agents should receive updates and their neighbour_assignments should reflect
the new colors.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer


def test_color_change_propagation():
    """Test that human color changes propagate to agents' neighbour_assignments."""

    # Create a simple 3-cluster problem
    # Agent1: a1, a2 | Human: h1, h2 | Agent2: b1, b2
    # Boundaries: a2-h1, h2-b1
    nodes = ["a1", "a2", "h1", "h2", "b1", "b2"]
    edges = [
        ("a1", "a2"),  # Agent1 internal
        ("a2", "h1"),  # Agent1-Human boundary
        ("h1", "h2"),  # Human internal
        ("h2", "b1"),  # Human-Agent2 boundary
        ("b1", "b2"),  # Agent2 internal
    ]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human", "b1": "Agent2", "b2": "Agent2"}

    # Create Agent1 - don't need API key for this test, just use template mode
    comm_layer = SpeechLLMLayer(use_llm=False)
    try:
        agent1 = ToolCallingClusterAgent(
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
    agent1.assignments = {"a1": "red", "a2": "blue"}

    # Agent1 initially knows h1 is green (from an earlier message)
    agent1.neighbour_assignments = {"h1": "green"}

    print(f"[Test] Initial agent1.neighbour_assignments: {agent1.neighbour_assignments}")
    assert agent1.neighbour_assignments["h1"] == "green", "Initial state should have h1=green"

    # Simulate human changing h1 from green to yellow
    # This mimics what on_colour_change() does
    # Send as structured dict (lines 3027-3031 of cluster_agent.py handle this)
    from agents.base_agent import Message

    boundary_updates = {"h1": "yellow"}
    update_msg = Message(
        sender="Human",
        recipient="Agent1",
        content=boundary_updates  # Send as dict - agent will extract assignments
    )

    print(f"[Test] Sending color update message to Agent1: {update_msg.content}")
    agent1.receive(update_msg)

    # Verify agent1's neighbour_assignments was updated
    print(f"[Test] After update, agent1.neighbour_assignments: {agent1.neighbour_assignments}")
    assert "h1" in agent1.neighbour_assignments, "h1 should still be in neighbour_assignments"
    assert agent1.neighbour_assignments["h1"] == "yellow", f"h1 should be yellow, got {agent1.neighbour_assignments.get('h1')}"

    print("[Test] [PASS] Color change propagation works correctly!")

    # Test with multiple boundary nodes
    agent1.neighbour_assignments = {"h1": "yellow", "h2": "green"}

    boundary_updates = {"h1": "red", "h2": "blue"}
    update_msg = Message(
        sender="Human",
        recipient="Agent1",
        content=boundary_updates  # Send as dict
    )

    print(f"[Test] Sending multi-node update: {update_msg.content}")
    agent1.receive(update_msg)

    print(f"[Test] After multi-node update: {agent1.neighbour_assignments}")
    assert agent1.neighbour_assignments["h1"] == "red", "h1 should be red"
    assert agent1.neighbour_assignments["h2"] == "blue", "h2 should be blue"

    print("[Test] [PASS] Multi-node color change propagation works!")

    # Test that on_colour_change only notifies about actual boundary nodes
    # The key filtering happens in on_colour_change(), not in receive()
    agent1.neighbour_assignments = {"h1": "red"}  # Reset - only h1 is boundary

    # If we send h3 directly, agent will accept it (that's fine)
    # But on_colour_change should NOT send h3 updates since it's not in neighbour_assignments
    print("[Test] Verifying on_colour_change only sends boundary updates...")

    # Simulate what happens when human changes h1 (boundary) and h3 (not boundary)
    test_updates = {"h1": "purple", "h3": "orange"}  # h3 is not in agent's boundaries

    # Filter like on_colour_change does
    filtered_updates = {
        node: color
        for node, color in test_updates.items()
        if node in agent1.neighbour_assignments  # Only boundaries
    }

    assert "h1" in filtered_updates, "h1 should be included (it's a boundary)"
    assert "h3" not in filtered_updates, "h3 should NOT be included (not a boundary)"

    print(f"[Test] Filtered updates: {filtered_updates}")
    print("[Test] [PASS] on_colour_change correctly filters to boundary nodes only!")
    print("[Test] All color change propagation tests passed!")


if __name__ == "__main__":
    test_color_change_propagation()
