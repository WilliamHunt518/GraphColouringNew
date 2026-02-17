"""Test announcement with LLMCommLayer to verify report suffix is added."""

from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.communication_layer import LLMCommLayer
import re


def test_announcement_with_llm_layer():
    """Test that LLMCommLayer adds [report: {...}] suffix to announcements."""

    # Create simple graph
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "h1"), ("a2", "h1")]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)

    # Use LLMCommLayer in manual mode (no LLM calls)
    comm_layer = LLMCommLayer(manual=True)

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

    # Set assignments
    agent.assignments = {"a1": "red", "a2": "blue"}

    print("=" * 70)
    print("TEST: Announcement with LLMCommLayer")
    print("=" * 70)

    # Send __ANNOUNCE_CONFIG__
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    # Check announcement was sent
    assert len(agent.sent_messages) == 1, f"Expected 1 message, got {len(agent.sent_messages)}"
    announcement = agent.sent_messages[0]

    print(f"\nAnnouncement content type: {type(announcement.content)}")
    print(f"Announcement content:\n{announcement.content}\n")

    # With LLMCommLayer, content should be a STRING with [report: ...] suffix
    content_str = str(announcement.content)

    # Check for report tag
    if "[report:" not in content_str:
        print("[FAIL] Missing [report: tag in formatted message!")
        print(f"Content was: {content_str}")
        return False

    print("[OK] Contains [report: tag")

    # Extract report
    report_match = re.search(r'\[report:\s*(\{.*?\})\s*\]', content_str)
    if not report_match:
        print("[FAIL] Could not extract report with regex")
        return False

    report_str = report_match.group(1)
    print(f"[OK] Report extracted: {report_str}")

    # Verify nodes are in report
    if "'a1': 'red'" in report_str or '"a1": "red"' in report_str:
        print("[OK] Contains a1=red")
    else:
        print("[FAIL] Missing a1=red in report")
        return False

    if "'a2': 'blue'" in report_str or '"a2": "blue"' in report_str:
        print("[OK] Contains a2=blue")
    else:
        print("[FAIL] Missing a2=blue in report")
        return False

    print("\n" + "=" * 70)
    print("[PASS] LLMCommLayer correctly formats announcements with [report: ...] suffix!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = test_announcement_with_llm_layer()
    exit(0 if success else 1)
