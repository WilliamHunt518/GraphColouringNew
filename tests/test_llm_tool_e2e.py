"""End-to-end test for LLM_TOOL mode - full dialogue to consensus."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.multi_node_human_agent import MultiNodeHumanAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message
import json

def print_status(agent, label):
    """Print agent status for debugging."""
    penalty, conflicts = agent.api.get_current_penalty()
    print(f"\n{label}:")
    print(f"  Assignments: {agent.assignments}")
    print(f"  Penalty: {penalty}")
    print(f"  Conflicts: {conflicts}")

def simulate_dialogue():
    """Simulate complete dialogue from announcement to consensus."""

    # Create problem matching default experiment
    nodes = ["a1", "a2", "a3", "a4", "a5", "h1", "h2", "h3", "h4", "h5", "b1", "b2", "b3", "b4", "b5"]
    edges = [
        # Agent1 cluster
        ("a1", "a2"), ("a2", "a3"), ("a3", "a4"), ("a4", "a5"),
        # Human cluster
        ("h1", "h2"), ("h2", "h3"), ("h3", "h4"), ("h4", "h5"),
        # Agent2 cluster
        ("b1", "b2"), ("b2", "b3"), ("b3", "b4"), ("b4", "b5"),
        # Inter-cluster edges
        ("a2", "h1"), ("a4", "h4"), ("a5", "h5"),  # Agent1-Human
        ("h2", "b1"), ("h5", "b5")  # Human-Agent2
    ]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)

    owners = {
        "a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "a4": "Agent1", "a5": "Agent1",
        "h1": "Human", "h2": "Human", "h3": "Human", "h4": "Human", "h5": "Human",
        "b1": "Agent2", "b2": "Agent2", "b3": "Agent2", "b4": "Agent2", "b5": "Agent2"
    }

    print("=== Creating agents ===")
    agent1 = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=SpeechLLMLayer(),
        local_nodes=["a1", "a2", "a3", "a4", "a5"],
        owners=owners
    )

    agent2 = ToolCallingClusterAgent(
        name="Agent2",
        problem=problem,
        comm_layer=SpeechLLMLayer(),
        local_nodes=["b1", "b2", "b3", "b4", "b5"],
        owners=owners
    )

    human = MultiNodeHumanAgent(
        name="Human",
        problem=problem,
        comm_layer=SpeechLLMLayer(),
        local_nodes=["h1", "h2", "h3", "h4", "h5"],
        owners=owners
    )

    # Initialize neighbor assignments
    agent1.neighbour_assignments = {"h1": "red", "h4": "red", "h5": "green"}
    agent2.neighbour_assignments = {"h2": "blue", "h5": "green"}
    human.assignments = {"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"}

    print("\n=== ROUND 1: Automatic announcements ===")
    agent1.step()
    agent2.step()

    print(f"Agent1 sent {len(agent1.sent_messages)} messages")
    print(f"Agent2 sent {len(agent2.sent_messages)} messages")
    agent1.sent_messages = []
    agent2.sent_messages = []

    print("\n=== ROUND 2: Human announces config ===")
    print(f"Human config: {human.assignments}")

    # Send to Agent1
    msg1 = Message(
        sender="Human",
        recipient="Agent1",
        content=f"Here's my configuration: h1=red, h2=blue, h3=green, h4=red, h5=green [config: {json.dumps(human.assignments)}]"
    )
    agent1.receive(msg1)
    agent1.step()

    print_status(agent1, "Agent1 after receiving human config")

    if agent1.sent_messages:
        msg_to_human = agent1.sent_messages[0]
        print(f"\nAgent1 -> Human: {msg_to_human.content[:200]}")
        agent1_response = msg_to_human.content
    else:
        print("\n[ERROR] Agent1 sent NO messages!")
        return False

    agent1.sent_messages = []

    # Send to Agent2
    msg2 = Message(
        sender="Human",
        recipient="Agent2",
        content=f"Here's my configuration: h1=red, h2=blue, h3=green, h4=red, h5=green [config: {json.dumps(human.assignments)}]"
    )
    agent2.receive(msg2)
    agent2.step()

    print_status(agent2, "Agent2 after receiving human config")

    if agent2.sent_messages:
        msg_to_human = agent2.sent_messages[0]
        print(f"\nAgent2 -> Human: {msg_to_human.content[:200]}")
        agent2_response = msg_to_human.content
    else:
        print("\n[ERROR] Agent2 sent NO messages!")
        return False

    agent2.sent_messages = []

    # Check if agents accepted (penalty=0) or proposed changes
    penalty1, _ = agent1.api.get_current_penalty()
    penalty2, _ = agent2.api.get_current_penalty()

    if penalty1 == 0 and penalty2 == 0:
        print("\n=== SUCCESS: Both agents accepted! ===")
        return True

    print(f"\n=== ROUND 3: Human responds to proposals ===")
    print(f"Agent1 penalty: {penalty1}, Agent2 penalty: {penalty2}")

    # If Agent1 needs changes, try to accommodate
    if penalty1 > 0:
        # Agent1 likely asked to change h4
        # Try h4=blue (common request)
        human.assignments["h4"] = "blue"
        agent1.neighbour_assignments["h4"] = "blue"

        msg3 = Message(
            sender="Human",
            recipient="Agent1",
            content=f"I changed h4 to blue [config: {json.dumps(human.assignments)}]"
        )
        agent1.receive(msg3)
        agent1.step()

        print_status(agent1, "Agent1 after human accommodated")

        if agent1.sent_messages:
            print(f"\nAgent1 -> Human: {agent1.sent_messages[0].content[:200]}")
        else:
            print("\n[ERROR] Agent1 sent NO response to accommodation!")
            return False

        agent1.sent_messages = []

    # Check final status
    penalty1, _ = agent1.api.get_current_penalty()
    penalty2, _ = agent2.api.get_current_penalty()

    print(f"\n=== FINAL STATUS ===")
    print(f"Agent1 penalty: {penalty1}")
    print(f"Agent2 penalty: {penalty2}")
    print(f"Human: {human.assignments}")
    print(f"Agent1: {agent1.assignments}")
    print(f"Agent2: {agent2.assignments}")

    if penalty1 == 0 and penalty2 == 0:
        print("\n=== SUCCESS: Consensus reached! ===")
        return True
    else:
        print("\n=== INCOMPLETE: Did not reach penalty=0 ===")
        return False

if __name__ == "__main__":
    try:
        success = simulate_dialogue()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n=== FATAL ERROR ===")
        print(f"{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
