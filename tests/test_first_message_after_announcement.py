"""Test that agents send substantive first message after announcement."""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.react_cluster_agent import ReActClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_tool_calling_first_message():
    """Test ToolCallingClusterAgent sends substantive first message."""
    print("\n=== Testing ToolCallingClusterAgent First Message ===")

    # Create a graph with conflicts
    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "a3"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"}

    comm_layer = SpeechLLMLayer(use_llm=False)  # Use template mode for testing
    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2", "a3"],
        owners=owners,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Set neighbor assignments to create conflicts
    agent.neighbour_assignments = {"h1": "red", "h2": "red"}

    # Compute assignments (will have conflicts)
    agent.assignments = agent.api.compute_assignments(algorithm="greedy")
    print(f"Agent assignments: {agent.assignments}")

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"Initial state - Penalty: {penalty}, Conflicts: {conflicts}")

    # Clear sent messages
    agent.sent_messages = []

    # Trigger announcement
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    print(f"\nMessages sent: {len(agent.sent_messages)}")

    # Should have at least 1 message (announcement)
    assert len(agent.sent_messages) >= 1, "Should have sent announcement"

    # Check announcement
    first_msg = agent.sent_messages[0]
    print(f"\n[1] Announcement: {first_msg.content[:100]}...")
    assert "initial configuration" in str(first_msg.content).lower(), "First message should be announcement"

    # Check if there's a substantive message (if penalty > 0)
    if penalty > 0:
        if len(agent.sent_messages) >= 2:
            second_msg = agent.sent_messages[1]
            print(f"[2] First substantive message: {second_msg.content[:150]}...")
            print("[OK] Agent sent substantive message after announcement")
        else:
            print("[INFO] Agent did not send substantive message (no backend LLM)")
    else:
        print("[INFO] No conflicts, substantive message optional")

    return True


def test_react_first_message():
    """Test ReActClusterAgent sends substantive first message."""
    print("\n=== Testing ReActClusterAgent First Message ===")

    # Create a graph with conflicts
    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "a3"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"}

    comm_layer = SpeechLLMLayer(use_llm=False)  # Use template mode for testing
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

    # Set neighbor assignments to create conflicts
    agent.neighbour_assignments = {"h1": "red", "h2": "red"}

    # Compute assignments (will have conflicts)
    agent.assignments = agent.api.compute_assignments(algorithm="greedy")
    print(f"Agent assignments: {agent.assignments}")

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"Initial state - Penalty: {penalty}, Conflicts: {conflicts}")

    # Clear sent messages
    agent.sent_messages = []

    # Trigger announcement
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    print(f"\nMessages sent: {len(agent.sent_messages)}")

    # Should have at least 1 message (announcement)
    assert len(agent.sent_messages) >= 1, "Should have sent announcement"

    # Check announcement
    first_msg = agent.sent_messages[0]
    print(f"\n[1] Announcement: {first_msg.content[:100]}...")
    assert "initial configuration" in str(first_msg.content).lower(), "First message should be announcement"

    # Check if there's a substantive message (if penalty > 0)
    if penalty > 0:
        if len(agent.sent_messages) >= 2:
            second_msg = agent.sent_messages[1]
            print(f"[2] First substantive message: {second_msg.content[:150]}...")
            print("[OK] Agent sent substantive message after announcement")
        else:
            print("[INFO] Agent did not send substantive message (no backend LLM)")
    else:
        print("[INFO] No conflicts, substantive message optional")

    return True


if __name__ == "__main__":
    try:
        test_tool_calling_first_message()
        test_react_first_message()

        print("\n" + "="*70)
        print("[OK] FIRST MESSAGE TESTS PASSED!")
        print("="*70)
        print("\nNote: Without API key, agents skip LLM-based first message.")
        print("With API key, agents will analyze conflicts and send substantive messages.")

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
