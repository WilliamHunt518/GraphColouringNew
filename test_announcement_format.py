"""Test that announcement messages have correct [report: {...}] format."""

from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.communication_layer import PassThroughCommLayer


def test_announcement_message_format():
    """Test that announcement messages include [report: {...}] tag."""

    # Create simple graph: Agent owns a1, a2; Human owns h1
    # a1 and a2 are both boundary nodes (connected to h1)
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "h1"), ("a2", "h1")]  # Use edges, not adjacency dict
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)
    comm_layer = PassThroughCommLayer()

    # Create agent with pre-assigned colors
    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="greedy",
        message_type="constraints"
    )

    # Manually set assignments so we know what colors to expect
    agent.assignments = {"a1": "red", "a2": "blue"}
    print(f"Agent assignments: {agent.assignments}")

    # Check initial sent_messages
    print(f"Initial sent_messages: {len(agent.sent_messages)}")

    # Check phase before announcement
    print(f"Phase before: {getattr(agent, '_phase', 'not set')}")

    # Send __ANNOUNCE_CONFIG__
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    print(f"\nSending __ANNOUNCE_CONFIG__ to agent...")
    print(f"Message content type: {type(msg.content)}")
    print(f"Message content: {repr(msg.content)}")

    # Debug: Check what neighbors the agent sees
    print(f"\nAgent nodes: {agent.nodes}")
    print(f"Agent owners: {agent.owners}")
    recipients = set()
    for node in agent.nodes:
        neighbors = problem.get_neighbors(node)
        print(f"  Node {node} has neighbors: {neighbors}")
        for nbr in neighbors:
            if nbr not in agent.nodes:
                owner = agent.owners.get(nbr)
                print(f"    Neighbor {nbr} is owned by {owner}")
                if owner and owner != agent.name:
                    recipients.add(owner)
    print(f"  Recipients found: {recipients}")

    agent.receive(msg)

    print(f"\nAfter receive, sent_messages: {len(agent.sent_messages)}")
    print(f"Phase after: {getattr(agent, '_phase', 'not set')}")
    print(f"Config announced: {getattr(agent, '_config_announced', False)}")
    print(f"Config locked: {getattr(agent, '_config_locked', False)}")

    # Check that messages were sent
    sent_messages = agent.sent_messages
    print(f"\nSent {len(sent_messages)} messages:")

    for m in sent_messages:
        print(f"\nMessage to {m.recipient}:")
        print(f"Content: {m.content}")

        # Check format
        content_str = str(m.content)
        if "[report:" in content_str:
            print("[OK] Contains [report: tag")

            # Extract report
            import re
            report_match = re.search(r'\[report:\s*(\{.*?\})\s*\]', content_str)
            if report_match:
                report_str = report_match.group(1)
                print(f"[OK] Report extracted: {report_str}")

                # Check that it contains the boundary node colors
                if "'a1': 'red'" in report_str or '"a1": "red"' in report_str:
                    print("[OK] Contains a1=red")
                else:
                    print("[FAIL] Missing a1=red")

                if "'a2': 'blue'" in report_str or '"a2": "blue"' in report_str:
                    print("[OK] Contains a2=blue")
                else:
                    print("[FAIL] Missing a2=blue")
            else:
                print("[FAIL] Could not extract report with regex")
        else:
            print("[FAIL] Missing [report: tag")

    if len(sent_messages) == 0:
        print("[FAIL] No messages sent!")
        return False

    print("\n[PASS] Announcement message format is correct!")
    return True


if __name__ == "__main__":
    test_announcement_message_format()
