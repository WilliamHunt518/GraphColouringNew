"""Debug test to understand why step() doesn't send messages."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_step_debug():
    """Debug why step() doesn't send messages."""
    print("\n" + "="*70)
    print("DEBUG: Step() Message Sending")
    print("="*70)

    # Simple problem
    nodes = ["a1", "h1"]
    edges = [("a1", "h1")]
    colors = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, colors)
    owners = {"a1": "Agent1", "h1": "Human"}

    try:
        agent = ToolCallingClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=SpeechLLMLayer(use_llm=True),
            local_nodes=["a1"],
            owners=owners
        )
        print("\n[OK] Agent created")
    except SystemExit:
        print("\n[SKIP] No API key")
        return

    # Set up conflict
    agent.assignments = {"a1": "red"}
    agent.neighbour_assignments = {"h1": "red"}

    # Move to bargain phase
    agent._config_announced = True
    agent._phase = "bargain"

    print(f"\n--- Initial State ---")
    print(f"Phase: {agent._phase}")
    print(f"Announced: {agent._config_announced}")
    print(f"_received_human_message_this_turn: {agent._received_human_message_this_turn}")
    print(f"received_messages count: {len(agent.received_messages)}")

    # Send message
    msg = Message(
        sender="Human",
        recipient="Agent1",
        content="I've set h1 to red"
    )

    print(f"\n--- Calling receive() ---")
    agent.receive(msg)

    print(f"After receive():")
    print(f"  _received_human_message_this_turn: {agent._received_human_message_this_turn}")
    print(f"  received_messages count: {len(agent.received_messages)}")
    print(f"  _last_human_text: '{agent._last_human_text}'")

    # Now call step()
    print(f"\n--- Calling step() ---")
    print(f"Backend LLM: {agent.backend_llm is not None}")

    before_count = len(agent.sent_messages)

    # Add detailed logging
    import logging
    logging.basicConfig(level=logging.DEBUG)

    agent.step()

    after_count = len(agent.sent_messages)

    print(f"\n--- After step() ---")
    print(f"Messages sent: {after_count - before_count}")
    print(f"Total sent messages: {after_count}")

    if after_count > before_count:
        last_msg = agent.sent_messages[-1]
        print(f"\n[OK] Message sent!")
        print(f"Content: {last_msg.content[:200]}...")
    else:
        print(f"\n[FAIL] No message sent")

        # Check flags again
        print(f"\nFinal state:")
        print(f"  _received_human_message_this_turn: {agent._received_human_message_this_turn}")
        print(f"  Backend LLM: {agent.backend_llm}")
        print(f"  Phase: {agent._phase}")


if __name__ == "__main__":
    test_step_debug()
