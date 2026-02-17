"""Detailed test to see full message content after Iteration 1."""

import sys
import json
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_full_message():
    """Test and display full message content."""
    print("Testing LLM_TOOL mode with Iteration 1 improvements")
    print("="*70)

    # Setup
    nodes = ["a1", "a2", "a4", "h1", "h4"]
    edges = [("a2", "h1"), ("a4", "h4")]
    domain = ["red", "blue", "green"]
    owners = {
        "a1": "Agent1",
        "a2": "Agent1",
        "a4": "Agent1",
        "h1": "Human",
        "h4": "Human"
    }

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    comm_layer = SpeechLLMLayer(use_llm=False)

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2", "a4"],
        owners=owners,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Set up conflicts
    agent.assignments = {"a1": "green", "a2": "red", "a4": "red"}
    agent.neighbour_assignments = {"h1": "red", "h4": "red"}

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"\nInitial state:")
    print(f"  Agent: {agent.assignments}")
    print(f"  Human: {agent.neighbour_assignments}")
    print(f"  Penalty: {penalty}, Conflicts: {conflicts}")

    # Trigger announcement
    agent.sent_messages = []
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    # Send human message
    human_msg = Message(
        sender="Human",
        recipient="Agent1",
        content="I've announced my configuration. What changes would you like me to make?"
    )
    agent.receive(human_msg)

    # Generate response
    print(f"\nGenerating agent response (this will take time)...")
    agent.step()

    # Display full message
    print(f"\n{'='*70}")
    print(f"FULL MESSAGE CONTENT")
    print(f"{'='*70}")

    for i, sent_msg in enumerate(agent.sent_messages[1:], 1):
        print(f"\nMessage {i}:")
        print(f"To: {sent_msg.recipient}")
        print(f"Full content:")
        print("-" * 70)
        print(sent_msg.content)
        print("-" * 70)


if __name__ == "__main__":
    test_full_message()
