"""Debug test for announcement flow."""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_announcement_flow():
    """Test complete announcement flow."""
    print("\n" + "="*70)
    print("DEBUG: Testing Announcement Flow")
    print("="*70)

    # Create graph
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "h1"), ("a2", "h1")]
    domain = ["red", "blue", "green"]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    comm_layer = SpeechLLMLayer(use_llm=False)

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2"],
        owners=owners,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    print(f"\n1. Initial state:")
    print(f"   - Phase: {agent._phase}")
    print(f"   - Config announced: {agent._config_announced}")
    print(f"   - Backend LLM: {'Present' if agent.backend_llm else 'None'}")
    print(f"   - Assignments: {agent.assignments}")

    # Set neighbor to create scenario
    agent.neighbour_assignments = {"h1": "red"}
    print(f"   - Neighbor assignments: {agent.neighbour_assignments}")

    # Clear sent messages
    agent.sent_messages = []

    print(f"\n2. Sending __ANNOUNCE_CONFIG__ message...")
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    print(f"   - Message content: '{msg.content}'")
    print(f"   - Message type: {type(msg.content)}")

    agent.receive(msg)

    print(f"\n3. After receive():")
    print(f"   - Phase: {agent._phase}")
    print(f"   - Config announced: {agent._config_announced}")
    print(f"   - Messages sent: {len(agent.sent_messages)}")

    if hasattr(agent, '_should_generate_first_message'):
        print(f"   - Should generate first message: {agent._should_generate_first_message}")

    if agent.sent_messages:
        print(f"\n4. Sent message details:")
        for i, msg in enumerate(agent.sent_messages):
            print(f"   Message {i+1}:")
            print(f"   - Recipient: {msg.recipient}")
            print(f"   - Content type: {type(msg.content)}")
            print(f"   - Content: {str(msg.content)[:200]}...")

            # Check for report tag
            content_str = str(msg.content)
            if "[report:" in content_str:
                print(f"   - ✓ Has report tag")
            else:
                print(f"   - ✗ Missing report tag")
    else:
        print(f"\n4. ✗ NO MESSAGES SENT - This is the problem!")

    print(f"\n5. Testing step() call...")
    agent.step()

    print(f"\n6. After step():")
    print(f"   - Messages sent: {len(agent.sent_messages)}")
    if hasattr(agent, '_should_generate_first_message'):
        print(f"   - Should generate first message: {agent._should_generate_first_message}")

    if len(agent.sent_messages) > 1:
        print(f"\n7. Second message details:")
        msg = agent.sent_messages[-1]
        print(f"   - Content: {str(msg.content)[:200]}...")

    print("\n" + "="*70)
    print("DEBUG COMPLETE")
    print("="*70)


if __name__ == "__main__":
    test_announcement_flow()
