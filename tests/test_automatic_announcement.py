"""Test that LLM_TOOL and LLM_REACT agents automatically announce on first step."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.react_cluster_agent import ReActClusterAgent
from problems.graph_coloring import GraphColoring


def test_tool_calling_automatic_announcement():
    """Test ToolCallingClusterAgent automatically announces on first step."""
    # Create simple problem
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "a2"), ("a2", "h1")]
    colors = ["red", "blue", "green"]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}
    problem = GraphColoring(nodes=nodes, edges=edges, domain=colors)

    # Create agent with no backend LLM (will fallback to algorithmic mode)
    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        local_nodes=["a1", "a2"],
        owners=owners,
        comm_layer=None,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Set neighbor assignments manually (since we're not using full simulation)
    agent.neighbour_assignments = {"h1": None}

    # Verify initial state
    assert agent._phase == "configure"
    assert not agent._config_announced
    assert len(agent.sent_messages) == 0

    # Call step() - should automatically announce
    agent.step()

    # Verify announcement sent
    assert agent._phase == "bargain", "Should transition to bargain phase"
    assert agent._config_announced, "Should mark config as announced"
    assert len(agent.sent_messages) == 1, f"Should send 1 announcement, got {len(agent.sent_messages)}"

    # Verify message content
    msg = agent.sent_messages[0]
    assert msg.recipient == "h1"
    assert isinstance(msg.content, dict)
    assert msg.content["type"] == "announcement"
    assert "report" in msg.content

    print("[OK] ToolCallingClusterAgent automatically announces on first step")


def test_react_automatic_announcement():
    """Test ReActClusterAgent automatically announces on first step."""
    # Create simple problem
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "a2"), ("a2", "h1")]
    colors = ["red", "blue", "green"]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}
    problem = GraphColoring(nodes=nodes, edges=edges, domain=colors)

    # Create agent with no backend LLM (will fallback to algorithmic mode)
    agent = ReActClusterAgent(
        name="Agent1",
        problem=problem,
        local_nodes=["a1", "a2"],
        owners=owners,
        comm_layer=None,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Set neighbor assignments manually (since we're not using full simulation)
    agent.neighbour_assignments = {"h1": None}

    # Verify initial state
    assert agent._phase == "configure"
    assert not agent._config_announced
    assert len(agent.sent_messages) == 0

    # Call step() - should automatically announce
    agent.step()

    # Verify announcement sent
    assert agent._phase == "bargain", "Should transition to bargain phase"
    assert agent._config_announced, "Should mark config as announced"
    assert len(agent.sent_messages) == 1, f"Should send 1 announcement, got {len(agent.sent_messages)}"

    # Verify message content
    msg = agent.sent_messages[0]
    assert msg.recipient == "h1"
    assert isinstance(msg.content, dict)
    assert msg.content["type"] == "announcement"
    assert "report" in msg.content

    print("[OK] ReActClusterAgent automatically announces on first step")


def test_multiple_neighbors():
    """Test automatic announcement to multiple neighbors."""
    # Create problem with 2 neighbors
    nodes = ["a1", "a2", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "h1"), ("a1", "h2")]
    colors = ["red", "blue", "green"]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}
    problem = GraphColoring(nodes=nodes, edges=edges, domain=colors)

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        local_nodes=["a1", "a2"],
        owners=owners,
        comm_layer=None,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Set neighbor assignments manually (since we're not using full simulation)
    agent.neighbour_assignments = {"h1": None, "h2": None}

    # Call step() - should announce to both neighbors
    agent.step()

    # Verify 2 announcements sent
    assert len(agent.sent_messages) == 2, f"Should send 2 announcements, got {len(agent.sent_messages)}"

    recipients = {msg.recipient for msg in agent.sent_messages}
    assert recipients == {"h1", "h2"}, f"Should send to h1 and h2, got {recipients}"

    print("[OK] Automatic announcement sent to multiple neighbors")


if __name__ == "__main__":
    test_tool_calling_automatic_announcement()
    test_react_automatic_announcement()
    test_multiple_neighbors()
    print("\n[PASS] All automatic announcement tests passed!")
