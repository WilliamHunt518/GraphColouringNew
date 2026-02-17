"""Debug test for LLM_TOOL mode to identify why agents aren't responding."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer

def test_agent_step_basic():
    """Test that agent step() method is being called and can generate messages."""

    # Create simple 3-color problem with 2 clusters
    # Agent controls: a1, a2
    # Human controls: h1, h2
    # Boundary: a2 connects to h1

    nodes = ["a1", "a2", "h1", "h2"]
    edges = [
        ("a1", "a2"),
        ("a2", "h1"),
        ("h1", "h2")
    ]
    colors = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=colors)

    # Create agent
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}
    local_nodes = ["a1", "a2"]

    comm_layer = SpeechLLMLayer()

    print("\n=== Creating ToolCallingClusterAgent ===")
    try:
        agent = ToolCallingClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=local_nodes,
            owners=owners,
            backend_model="gpt-4-turbo"
        )
        print(f"[OK] Agent created successfully")
        print(f"  Backend LLM: {agent.backend_llm}")
        print(f"  Phase: {agent._phase}")
        print(f"  Config announced: {agent._config_announced}")
    except Exception as e:
        print(f"[FAIL] Failed to create agent: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test 1: First step() should send automatic announcement
    print("\n=== Test 1: First step() - Automatic Announcement ===")
    agent.step()
    print(f"  Phase after step: {agent._phase}")
    print(f"  Config announced: {agent._config_announced}")
    print(f"  Assignments: {agent.assignments}")

    # Test 2: Simulate receiving human message
    print("\n=== Test 2: Receiving human message ===")

    class MockMessage:
        def __init__(self, sender, recipient, content):
            self.sender = sender
            self.recipient = recipient
            self.content = content

    msg = MockMessage(sender="Human", recipient="Agent1", content="h1=red, h2=blue")

    print(f"  Sending message to agent: {msg.content}")
    agent.receive(msg)
    print(f"  Received messages count: {len(agent.received_messages)}")
    print(f"  _received_human_message_this_turn: {agent._received_human_message_this_turn}")

    # Test 3: step() should now process and respond
    print("\n=== Test 3: Second step() - Should generate response ===")
    print("  Calling step()...")

    try:
        agent.step()
        print(f"[OK] step() completed")
        print(f"  Conversation history length: {len(agent.conversation_history)}")
        if agent.conversation_history:
            print(f"  Last message role: {agent.conversation_history[-1].get('role')}")
    except Exception as e:
        print(f"[FAIL] step() failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Debug Summary ===")
    print(f"Phase: {agent._phase}")
    print(f"Config announced: {agent._config_announced}")
    print(f"Received messages: {len(agent.received_messages)}")
    print(f"Conversation history: {len(agent.conversation_history)}")
    print(f"Backend LLM available: {agent.backend_llm is not None}")

if __name__ == "__main__":
    test_agent_step_basic()
