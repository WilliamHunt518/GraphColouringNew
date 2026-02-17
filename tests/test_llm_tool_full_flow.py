"""Full flow integration test for LLM_TOOL mode matching UI behavior."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.multi_node_human_agent import MultiNodeHumanAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message

def test_full_ui_flow():
    """Simulate exact flow that happens in the UI."""

    # Create problem with 3 clusters (like default experiment)
    nodes = ["a2", "a4", "a5", "h1", "h2", "h3", "h4", "h5", "b2"]
    edges = [
        ("a2", "a4"), ("a4", "a5"),  # Agent1 cluster
        ("h1", "h2"), ("h2", "h3"), ("h3", "h4"), ("h4", "h5"),  # Human cluster
        ("a2", "h1"), ("a4", "h4"), ("a5", "h5"),  # Agent1-Human edges
        ("h3", "b2")  # Human-Agent2 edge
    ]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)

    # Create agents
    owners = {
        "a2": "Agent1", "a4": "Agent1", "a5": "Agent1",
        "h1": "Human", "h2": "Human", "h3": "Human", "h4": "Human", "h5": "Human",
        "b2": "Agent2"
    }

    agent1_layer = SpeechLLMLayer()
    agent2_layer = SpeechLLMLayer()
    human_layer = SpeechLLMLayer()

    print("=== Creating agents ===")
    agent1 = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=agent1_layer,
        local_nodes=["a2", "a4", "a5"],
        owners=owners,
        backend_model="gpt-4-turbo"
    )

    agent2 = ToolCallingClusterAgent(
        name="Agent2",
        problem=problem,
        comm_layer=agent2_layer,
        local_nodes=["b2"],
        owners=owners,
        backend_model="gpt-4-turbo"
    )

    human = MultiNodeHumanAgent(
        name="Human",
        problem=problem,
        comm_layer=human_layer,
        local_nodes=["h1", "h2", "h3", "h4", "h5"],
        owners=owners
    )

    # Set neighbor assignments for agents
    agent1.neighbour_assignments = {"h1": "red", "h4": "red", "h5": "green"}
    agent2.neighbour_assignments = {"h3": "green"}

    print("=== Step 1: First step() calls - automatic announcements ===")
    print("Agent1 step()...")
    agent1.step()
    print(f"  Agent1 sent {len(agent1.sent_messages)} messages")
    if agent1.sent_messages:
        print(f"  Message recipients: {[m.recipient for m in agent1.sent_messages]}")
    agent1.sent_messages = []  # Clear like simulation does

    print("Agent2 step()...")
    agent2.step()
    print(f"  Agent2 sent {len(agent2.sent_messages)} messages")
    if agent2.sent_messages:
        print(f"  Message recipients: {[m.recipient for m in agent2.sent_messages]}")
    agent2.sent_messages = []

    print("\n=== Step 2: Human announces config ===")
    human.assignments = {
        "h1": "red", "h2": "blue", "h3": "green",
        "h4": "red", "h5": "green"
    }

    # Simulate UI sending __ANNOUNCE_CONFIG__
    msg_announce = Message(sender="Human", recipient="Agent2", content="__ANNOUNCE_CONFIG__")
    print(f"Sending: {msg_announce.sender} -> {msg_announce.recipient}: {msg_announce.content}")
    agent2.receive(msg_announce)

    print("\n=== Step 3: Human sends configuration to Agent1 ===")
    # Simulate what UI does: append [config: {...}]
    import json
    config_text = f"Here's my configuration: h1=red, h2=blue, h3=green, h4=red, h5=green [config: {json.dumps(human.assignments)}]"
    msg_config = Message(sender="Human", recipient="Agent1", content=config_text)
    print(f"Sending: {msg_config.sender} -> {msg_config.recipient}: {len(msg_config.content)} chars")
    agent1.receive(msg_config)

    print(f"\nAgent1 state after receive:")
    print(f"  received_messages: {len(agent1.received_messages)}")
    print(f"  _received_human_message_this_turn: {agent1._received_human_message_this_turn}")
    print(f"  _phase: {agent1._phase}")
    print(f"  _config_announced: {agent1._config_announced}")

    print("\n=== Step 4: Agent1 step() - should respond ===")
    print("Agent1 step()...")
    print(f"Agent1 conversation_history BEFORE: {len(agent1.conversation_history)} messages")
    agent1.step()
    print(f"Agent1 conversation_history AFTER: {len(agent1.conversation_history)} messages")

    print(f"\nAgent1 after step():")
    print(f"  sent_messages: {len(agent1.sent_messages)}")
    if agent1.sent_messages:
        for i, msg in enumerate(agent1.sent_messages):
            print(f"  Message {i+1}:")
            print(f"    To: {msg.recipient}")
            print(f"    Content (first 200 chars): {str(msg.content)[:200]}")
    else:
        print("  [NO MESSAGES SENT]")
        print(f"  conversation_history length: {len(agent1.conversation_history)}")
        if agent1.conversation_history:
            print("\n  Full conversation history:")
            for i, msg in enumerate(agent1.conversation_history):
                role = msg.get('role', 'unknown')
                print(f"  [{i}] Role: {role}")
                if role == "tool":
                    print(f"      Content: {msg.get('content', 'N/A')[:300]}")
                elif role == "assistant" and msg.get('tool_calls'):
                    print(f"      Tool calls: {len(msg.get('tool_calls', []))}")
                    for tc in msg.get('tool_calls', []):
                        print(f"        - {tc.get('function', {}).get('name')}: {tc.get('function', {}).get('arguments', '')[:100]}")
                elif role == "assistant":
                    print(f"      Content: {msg.get('content', 'N/A')[:300]}")

    print("\n=== Step 5: Human sends same config to Agent2 ===")
    msg_config2 = Message(sender="Human", recipient="Agent2", content=config_text)
    print(f"Sending: {msg_config2.sender} -> {msg_config2.recipient}: {len(msg_config2.content)} chars")
    agent2.receive(msg_config2)

    print("\n=== Step 6: Agent2 step() - should respond ===")
    print("Agent2 step()...")
    agent2.step()

    print(f"\nAgent2 after step():")
    print(f"  sent_messages: {len(agent2.sent_messages)}")
    if agent2.sent_messages:
        for i, msg in enumerate(agent2.sent_messages):
            print(f"  Message {i+1}:")
            print(f"    To: {msg.recipient}")
            print(f"    Content (first 200 chars): {str(msg.content)[:200]}")
    else:
        print("  [NO MESSAGES SENT]")

if __name__ == "__main__":
    test_full_ui_flow()
