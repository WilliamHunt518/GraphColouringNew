"""Test that template fallback works when LLM fails."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_template_fallback():
    """Test that agents send messages even when LLM translation fails."""
    print("\n" + "="*70)
    print("TEST: Template Fallback (No LLM Required)")
    print("="*70)

    # Simple problem
    nodes = ["a1", "h1"]
    edges = [("a1", "h1")]
    colors = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, colors)
    owners = {"a1": "Agent1", "h1": "Human"}

    # Create agent WITHOUT LLM (will use fallbacks)
    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=SpeechLLMLayer(use_llm=False),  # No LLM
        local_nodes=["a1"],
        owners=owners
    )

    # Set up conflict
    agent.assignments = {"a1": "red"}
    agent.neighbour_assignments = {"h1": "red"}

    # Move to bargain phase
    agent._config_announced = True
    agent._phase = "bargain"

    print(f"\n--- Setup ---")
    print(f"Agent a1: {agent.assignments['a1']}")
    print(f"Human h1: {agent.neighbour_assignments['h1']}")

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"Penalty: {penalty}")
    print(f"Conflicts: {conflicts}")

    # Send message
    msg = Message(
        sender="Human",
        recipient="Agent1",
        content="I've set h1 to red"
    )

    agent.receive(msg)

    # Step - should use fallback and generate message
    print(f"\n--- Calling step() with template fallback ---")
    before_count = len(agent.sent_messages)

    agent.step()

    after_count = len(agent.sent_messages)
    new_messages = after_count - before_count

    print(f"\n--- Results ---")
    print(f"Messages sent: {new_messages}")

    if new_messages > 0:
        last_msg = agent.sent_messages[-1]
        print(f"[SUCCESS] Agent sent message using template fallback")
        print(f"Recipient: {last_msg.recipient}")
        print(f"Content: {last_msg.content}")
        return True
    else:
        print(f"[FAIL] No message sent")
        return False


if __name__ == "__main__":
    success = test_template_fallback()
    exit(0 if success else 1)
