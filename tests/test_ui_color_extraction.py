"""Test that UI can extract colors from announcement messages."""

import re
import ast
from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.communication_layer import LLMCommLayer


def extract_report_like_ui(text: str):
    """Extract report the same way the UI does."""
    report = {}
    try:
        m = re.search(r"\[report:\s*(\{.*?\})\s*\]", text)
        if m:
            rep = ast.literal_eval(m.group(1))
            if isinstance(rep, dict):
                report.update(rep)
    except Exception:
        report = {}
    return report


def test_ui_color_extraction():
    """Test that UI can extract agent colors from announcement."""

    # Create graph with Agent and Human
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "h1"), ("a2", "h1")]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)
    comm_layer = LLMCommLayer(manual=True)  # Manual mode to avoid LLM calls

    # Create agent
    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="greedy",
        message_type="constraints"
    )

    # Set agent's boundary colors
    agent.assignments = {"a1": "red", "a2": "blue"}

    print("=" * 70)
    print("TEST: UI Color Extraction from Announcement")
    print("=" * 70)
    print(f"\nAgent's boundary assignments: {agent.assignments}")

    # Trigger announcement
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    # Get announcement message (as UI would receive it)
    announcement = agent.sent_messages[0]
    message_text = str(announcement.content)

    print(f"\nMessage received by UI:")
    print(f"{message_text}\n")

    # Extract report (simulating UI's _extract_and_apply_reports)
    known_colors = extract_report_like_ui(message_text)

    print(f"Colors extracted by UI: {known_colors}")

    # Verify colors were extracted correctly
    if "a1" in known_colors and known_colors["a1"] == "red":
        print("[OK] a1=red extracted correctly")
    else:
        print(f"[FAIL] a1 not extracted correctly. Got: {known_colors.get('a1')}")
        return False

    if "a2" in known_colors and known_colors["a2"] == "blue":
        print("[OK] a2=blue extracted correctly")
    else:
        print(f"[FAIL] a2 not extracted correctly. Got: {known_colors.get('a2')}")
        return False

    print("\n" + "=" * 70)
    print("[PASS] UI successfully extracts agent colors from announcement!")
    print("       Agent nodes will now appear with correct colors in the graph.")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = test_ui_color_extraction()
    exit(0 if success else 1)
