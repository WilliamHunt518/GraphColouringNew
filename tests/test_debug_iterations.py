"""Debug test to see what the backend LLM is producing."""

import sys
import json
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_with_logging():
    """Test and capture all logging."""
    print("Testing LLM_TOOL with debug logging")
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

    # Enable more detailed logging
    agent.log_file = "test_debug.log"

    # Set up conflicts
    agent.assignments = {"a1": "green", "a2": "red", "a4": "red"}
    agent.neighbour_assignments = {"h1": "red", "h4": "red"}

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"\nInitial state:")
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
    print(f"\nGenerating response...")
    agent.step()

    # Check what was sent
    if len(agent.sent_messages) > 1:
        last_msg = agent.sent_messages[-1]
        print(f"\n{'='*70}")
        print(f"MESSAGE ANALYSIS")
        print(f"{'='*70}")
        print(f"To: {last_msg.recipient}")
        print(f"Content: {last_msg.content}")

        # Try to extract structured content
        if hasattr(last_msg, 'structured_content'):
            print(f"\nStructured content:")
            print(json.dumps(last_msg.structured_content, indent=2))

    # Check log file
    print(f"\n{'='*70}")
    print(f"RECENT LOG ENTRIES (last 50 lines)")
    print(f"{'='*70}")
    try:
        with open("test_debug.log", "r") as f:
            lines = f.readlines()
            for line in lines[-50:]:
                print(line.rstrip())
    except:
        print("Could not read log file")


if __name__ == "__main__":
    test_with_logging()
