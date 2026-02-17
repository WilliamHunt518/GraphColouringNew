"""Final check: Verify messages have requested_changes populated."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def main():
    print("="*70)
    print("FINAL CHECK: Verify Iteration 1-4 Improvements")
    print("="*70)

    # Setup with conflicts
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

    # Create conflicts
    agent.assignments = {"a1": "green", "a2": "red", "a4": "red"}
    agent.neighbour_assignments = {"h1": "red", "h4": "red"}

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"\n[Setup]")
    print(f"  Agent assignments: {agent.assignments}")
    print(f"  Human assignments: {agent.neighbour_assignments}")
    print(f"  Penalty: {penalty}")
    print(f"  Conflicts: {conflicts}")

    # Announce
    agent.sent_messages = []
    agent.receive(Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__"))

    # Trigger response
    agent.receive(Message(
        sender="Human",
        recipient="Agent1",
        content="What changes do you need?"
    ))

    print(f"\n[Generating Response]")
    print(f"  (This will take 10-30 seconds with LLM calls...)")

    agent.step()

    # Analyze result
    print(f"\n{'='*70}")
    print(f"[Result Analysis]")
    print(f"{'='*70}")

    if len(agent.sent_messages) < 2:
        print(f"  [ERROR] No response generated")
        return False

    msg = agent.sent_messages[-1]
    content_str = str(msg.content)

    print(f"\n  To: {msg.recipient}")
    print(f"\n  Full message:")
    print(f"  " + "-"*66)
    for line in content_str.split('\n'):
        print(f"  {line}")
    print(f"  " + "-"*66)

    # Check for specificity markers
    print(f"\n[Specificity Checks]")

    vague_phrases = ["make a change", "adjust colors", "let's review",
                     "we should", "might need", "consider changing",
                     "a neighboring node", "some boundary nodes"]

    vague_found = []
    for phrase in vague_phrases:
        if phrase.lower() in content_str.lower():
            vague_found.append(phrase)

    if vague_found:
        print(f"  [X] VAGUE PHRASES FOUND: {vague_found}")
        return False
    else:
        print(f"  [OK] No vague phrases detected")

    # Check for specific node-color mentions
    has_specific = False
    for node in ["h1", "h4"]:
        for color in ["red", "blue", "green"]:
            if node in content_str.lower() and color in content_str.lower():
                has_specific = True
                print(f"  [OK] Mentions specific node '{node}' with color '{color}'")
                break

    if not has_specific:
        print(f"  [X] No specific node-color pairs found")
        return False

    print(f"\n[SUCCESS] Message is specific and actionable!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
