"""Test that announcements are formatted as natural language."""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.react_cluster_agent import ReActClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_tool_calling_announcement():
    """Test ToolCallingClusterAgent announcement format."""
    print("\n=== Testing ToolCallingClusterAgent Announcement ===")

    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "a3"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"}

    comm_layer = SpeechLLMLayer(use_llm=False)
    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2", "a3"],
        owners=owners,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Set neighbor assignments
    agent.neighbour_assignments = {"h1": "red", "h2": "blue"}

    # Compute assignments
    agent.assignments = agent.api.compute_assignments(algorithm="greedy")
    print(f"Agent assignments: {agent.assignments}")

    # Trigger announcement
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    # Check that message was sent and formatted through comm layer
    assert len(agent.sent_messages) > 0, "Should have sent announcement"
    sent_msg = agent.sent_messages[-1]

    # The message content should be formatted by comm_layer.format_content()
    formatted_content = sent_msg.content
    print(f"\nFormatted announcement: {formatted_content}")

    # Verify it's a string, not a dict
    assert isinstance(formatted_content, str), "Formatted announcement should be a string"

    # Verify it contains expected elements
    assert "Here's my initial configuration:" in formatted_content or "initial configuration" in formatted_content.lower(), \
        "Should mention initial configuration"
    assert "[report:" in formatted_content, "Should have report tag"

    print("[OK] ToolCallingClusterAgent announcement is formatted as natural language")


def test_react_announcement():
    """Test ReActClusterAgent announcement format."""
    print("\n=== Testing ReActClusterAgent Announcement ===")

    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "a3"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"}

    comm_layer = SpeechLLMLayer(use_llm=False)
    agent = ReActClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2", "a3"],
        owners=owners,
        backend_model="gpt-4-turbo",
        max_react_iterations=5,
        algorithm="greedy"
    )

    # Set neighbor assignments
    agent.neighbour_assignments = {"h1": "red", "h2": "blue"}

    # Compute assignments
    agent.assignments = agent.api.compute_assignments(algorithm="greedy")
    print(f"Agent assignments: {agent.assignments}")

    # Trigger announcement
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    # Check that message was sent and formatted through comm layer
    assert len(agent.sent_messages) > 0, "Should have sent announcement"
    sent_msg = agent.sent_messages[-1]

    # The message content should be formatted by comm_layer.format_content()
    formatted_content = sent_msg.content
    print(f"\nFormatted announcement: {formatted_content}")

    # Verify it's a string, not a dict
    assert isinstance(formatted_content, str), "Formatted announcement should be a string"

    # Verify it contains expected elements
    assert "Here's my initial configuration:" in formatted_content or "initial configuration" in formatted_content.lower(), \
        "Should mention initial configuration"
    assert "[report:" in formatted_content, "Should have report tag"

    print("[OK] ReActClusterAgent announcement is formatted as natural language")


if __name__ == "__main__":
    try:
        test_tool_calling_announcement()
        test_react_announcement()

        print("\n" + "="*70)
        print("[OK] ALL ANNOUNCEMENT FORMAT TESTS PASSED!")
        print("="*70)
        print("\nAnnouncements are now formatted as natural language.")
        print("Example: 'Here's my initial configuration: a2=blue, a4=red [report: {...}]'")

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
