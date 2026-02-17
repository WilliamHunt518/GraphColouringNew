"""Test that agents handle questions and constraints properly."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_question_answering():
    """Test that agent answers questions instead of ignoring them."""
    print("\n" + "="*70)
    print("TEST: Question Answering")
    print("="*70)

    # Simple problem
    nodes = ["a1", "h1", "h4"]
    edges = [("a1", "h1"), ("a1", "h4")]
    colors = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, colors)
    owners = {"a1": "Agent1", "h1": "Human", "h4": "Human"}

    # Create agent WITHOUT LLM (will use fallbacks)
    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=SpeechLLMLayer(use_llm=False),
        local_nodes=["a1"],
        owners=owners
    )

    # Set up state
    agent.assignments = {"a1": "red"}
    agent.neighbour_assignments = {"h1": "green", "h4": "blue"}
    agent._config_announced = True
    agent._phase = "bargain"

    print(f"\n--- Setup ---")
    print(f"Agent a1: {agent.assignments['a1']}")
    print(f"Human h1: {agent.neighbour_assignments['h1']}")
    print(f"Human h4: {agent.neighbour_assignments['h4']}")

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"Current penalty: {penalty}")

    # Test 1: Question about scenario
    print(f"\n--- Test 1: Question 'Can that work?' ---")
    msg1 = Message(
        sender="Human",
        recipient="Agent1",
        content="I can make h4 blue if h1 is green. Can that work?"
    )

    agent.receive(msg1)
    before1 = len(agent.sent_messages)
    agent.step()
    after1 = len(agent.sent_messages)

    if after1 > before1:
        reply1 = agent.sent_messages[-1].content
        print(f"Agent reply: {reply1}")

        # Check if it's answering the question
        reply_lower = str(reply1).lower()
        if "yes" in reply_lower or "that works" in reply_lower or "no" in reply_lower:
            print(f"[OK] Agent ANSWERED the question")
        else:
            print(f"[WARN] Agent didn't clearly answer yes/no")
    else:
        print(f"[FAIL] No reply")

    # Test 2: Constraint declaration
    print(f"\n--- Test 2: Constraint 'h4 can't be green' ---")
    agent.sent_messages.clear()  # Reset

    msg2 = Message(
        sender="Human",
        recipient="Agent1",
        content="h4 can't ever be green"
    )

    agent.receive(msg2)
    before2 = len(agent.sent_messages)
    agent.step()
    after2 = len(agent.sent_messages)

    if after2 > before2:
        reply2 = agent.sent_messages[-1].content
        print(f"Agent reply: {reply2}")

        # Check if it acknowledges the constraint
        reply_lower = str(reply2).lower()
        if "understood" in reply_lower or "okay" in reply_lower or "got it" in reply_lower:
            print(f"[OK] Agent ACKNOWLEDGED the constraint")
        else:
            print(f"[INFO] Agent response: {reply2[:100]}...")
    else:
        print(f"[FAIL] No reply")

    print(f"\n[COMPLETE] Question handling test done")


if __name__ == "__main__":
    test_question_answering()
