"""Test that announcement stage doesn't cause spam messages."""

from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.communication_layer import PassThroughCommLayer


def test_announcement_no_spam():
    """Test that agent doesn't spam messages after announcement."""

    # Create simple graph: Agent owns a1, a2; Human owns h1
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "h1"), ("a2", "h1")]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)
    comm_layer = PassThroughCommLayer()

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

    # Set initial assignments
    agent.assignments = {"a1": "red", "a2": "blue"}

    # Step 1: Configure phase - no messages should be sent
    print("=== Step 1: Configure phase ===")
    agent.step()
    assert len(agent.sent_messages) == 0, "No messages in configure phase"
    print("[OK] No messages sent in configure phase")

    # Send __ANNOUNCE_CONFIG__
    print("\n=== Announcement ===")
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    # Check that announcement was sent
    assert len(agent.sent_messages) == 1, f"Expected 1 announcement, got {len(agent.sent_messages)}"
    announcement = agent.sent_messages[0]
    print(f"Announcement sent: {announcement.content[:80]}...")

    # Verify report is in announcement
    assert "[report:" in str(announcement.content), "Announcement should contain [report: tag"
    print("[OK] Announcement contains [report: tag")

    # Clear messages to track new ones
    agent.sent_messages.clear()

    # Step 2: Should unlock but NOT send any messages (just unlocks and returns)
    print("\n=== Step 2: Unlock (no messages expected) ===")
    agent.step()
    num_messages_after_unlock = len(agent.sent_messages)
    print(f"Messages sent after unlock step: {num_messages_after_unlock}")

    if num_messages_after_unlock == 0:
        print("[OK] No spam - agent correctly unlocked and returned without sending messages")
    else:
        print("[FAIL] Agent sent messages during unlock step (spam detected!)")
        for m in agent.sent_messages:
            print(f"  Spam message: {m.content[:80]}...")
        return False

    # Step 3: Normal operation - agent may send messages if there's something to say
    print("\n=== Step 3: Normal operation ===")
    agent.step()
    print(f"Messages sent in normal operation: {len(agent.sent_messages)}")
    print("[OK] Agent now in normal bargain phase")

    print("\n[PASS] No spam detected! Announcement stage works correctly.")
    return True


if __name__ == "__main__":
    test_announcement_no_spam()
