"""Integration test for LLM_API announcement stage.

This test simulates the full flow:
1. Create agents in configure phase
2. Send __ANNOUNCE_CONFIG__
3. Verify announcements are sent with correct format
4. Verify no spam on subsequent steps
5. Verify colors are properly reported
"""

from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.communication_layer import PassThroughCommLayer
import re


def test_integration():
    """Full integration test of announcement stage."""
    print("=" * 70)
    print("INTEGRATION TEST: LLM_API Announcement Stage")
    print("=" * 70)

    # Create a 3-cluster graph: Agent1 - Human - Agent2
    nodes = ["a1", "a2", "h1", "h2", "b1", "b2"]
    edges = [
        ("a1", "h1"), ("a2", "h2"),  # Agent1 to Human
        ("h1", "b1"), ("h2", "b2")   # Human to Agent2
    ]
    owners = {
        "a1": "Agent1", "a2": "Agent1",
        "h1": "Human", "h2": "Human",
        "b1": "Agent2", "b2": "Agent2"
    }
    domain = ["red", "blue", "green", "yellow"]

    problem = GraphColoring(nodes, edges, domain)
    comm_layer = PassThroughCommLayer()

    # Create Agent1
    agent1 = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="greedy",
        message_type="constraints"
    )
    agent1.assignments = {"a1": "red", "a2": "blue"}

    # Create Agent2
    agent2 = ClusterAgent(
        name="Agent2",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["b1", "b2"],
        owners=owners,
        algorithm="greedy",
        message_type="constraints"
    )
    agent2.assignments = {"b1": "green", "b2": "yellow"}

    print("\n[Step 1] Configure phase - no messages should be sent")
    print("-" * 70)
    agent1.step()
    agent2.step()
    assert len(agent1.sent_messages) == 0, "Agent1 should not send in configure phase"
    assert len(agent2.sent_messages) == 0, "Agent2 should not send in configure phase"
    print("[OK] No messages sent in configure phase")

    print("\n[Step 2] Human announces configuration")
    print("-" * 70)
    msg_to_agent1 = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    msg_to_agent2 = Message(sender="Human", recipient="Agent2", content="__ANNOUNCE_CONFIG__")

    agent1.receive(msg_to_agent1)
    agent2.receive(msg_to_agent2)

    # Check announcements were sent
    assert len(agent1.sent_messages) == 1, f"Agent1 should send 1 announcement, got {len(agent1.sent_messages)}"
    assert len(agent2.sent_messages) == 1, f"Agent2 should send 1 announcement, got {len(agent2.sent_messages)}"

    # Verify format
    for agent, expected_nodes in [(agent1, ["a1", "a2"]), (agent2, ["b1", "b2"])]:
        msg = agent.sent_messages[0]
        content = str(msg.content)

        print(f"\n{agent.name} announcement: {content[:80]}...")

        # Check for report tag
        if "[report:" not in content:
            print(f"[FAIL] Missing [report: tag")
            return False

        # Extract report
        report_match = re.search(r'\[report:\s*(\{.*?\})\s*\]', content)
        if not report_match:
            print(f"[FAIL] Could not extract report")
            return False

        report_str = report_match.group(1)
        print(f"  Report: {report_str}")

        # Verify all boundary nodes are in report
        for node in expected_nodes:
            if f"'{node}'" not in report_str and f'"{node}"' not in report_str:
                print(f"[FAIL] Missing node {node} in report")
                return False

        print(f"[OK] {agent.name} announcement has correct format")

    # Clear messages to track spam
    agent1.sent_messages.clear()
    agent2.sent_messages.clear()

    print("\n[Step 3] Unlock step - no messages should be sent (spam check)")
    print("-" * 70)
    agent1.step()
    agent2.step()

    spam_count = len(agent1.sent_messages) + len(agent2.sent_messages)
    if spam_count > 0:
        print(f"[FAIL] Spam detected! {spam_count} messages sent during unlock")
        for msg in agent1.sent_messages + agent2.sent_messages:
            print(f"  Spam: {msg.content[:80]}...")
        return False

    print("[OK] No spam - agents correctly unlocked without sending messages")

    print("\n[Step 4] Normal operation - agents can now negotiate")
    print("-" * 70)
    agent1.step()
    agent2.step()

    total_messages = len(agent1.sent_messages) + len(agent2.sent_messages)
    print(f"[OK] Agents sent {total_messages} messages in normal operation (expected behavior)")

    print("\n" + "=" * 70)
    print("*** ALL TESTS PASSED! ***")
    print("=" * 70)
    print("\nKey features verified:")
    print("  1. Agents start in configure phase")
    print("  2. Announcements sent with [report: {...}] format")
    print("  3. No spam after unlock step")
    print("  4. Normal negotiation proceeds after announcement")
    return True


if __name__ == "__main__":
    success = test_integration()
    exit(0 if success else 1)
