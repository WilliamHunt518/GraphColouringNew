"""Test the full UI flow to see where announcement is failing."""

from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.communication_layer import LLMCommLayer
import re


def simulate_on_send_flow():
    """Simulate the exact flow that happens in cluster_simulation.py"""

    print("=" * 70)
    print("SIMULATING FULL UI FLOW")
    print("=" * 70)

    # Create graph
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "h1"), ("a2", "h1")]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)

    # Create agent with LLMCommLayer (like real UI)
    agent_comm = LLMCommLayer(manual=True)
    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=agent_comm,
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="greedy",
        message_type="constraints"  # LLM_API mode
    )
    agent.assignments = {"a1": "red", "a2": "blue"}

    # Create human agent
    human_comm = LLMCommLayer(manual=True)
    human_agent = ClusterAgent(
        name="Human",
        problem=problem,
        comm_layer=human_comm,
        local_nodes=["h1"],
        owners=owners,
        algorithm="greedy",
        message_type="constraints"
    )
    human_agent.assignments = {"h1": "green"}

    print(f"\n[STEP 1] Human triggers announcement")
    print(f"Agent phase: {getattr(agent, '_phase', 'not set')}")
    print(f"Agent assignments: {agent.assignments}")

    # Simulate on_send callback (from cluster_simulation.py line 754-759)
    # For special tokens, bypass comm layer to preserve exact string
    print(f"\n[STEP 2] Send __ANNOUNCE_CONFIG__ to agent")
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    print(f"Message sent: {msg}")
    print(f"Message content type: {type(msg.content)}")
    print(f"Message content: {msg.content}")

    # Agent receives message
    print(f"\n[STEP 3] Agent receives message")
    agent.receive(msg)
    print(f"Agent phase after receive: {getattr(agent, '_phase', 'not set')}")
    print(f"Agent sent_messages count: {len(agent.sent_messages)}")

    # Step agent
    print(f"\n[STEP 4] Step agent")
    agent.step()
    print(f"Agent sent_messages count after step: {len(agent.sent_messages)}")

    # Extract replies (from cluster_simulation.py lines 781-810)
    print(f"\n[STEP 5] Extract agent's replies")
    reply_texts = []
    sent = getattr(agent, "sent_messages", []) or []
    print(f"Agent has {len(sent)} sent messages")

    for m in sent:
        print(f"\n  Processing message to {m.recipient}:")
        print(f"    Content type: {type(m.content)}")
        print(f"    Content: {str(m.content)[:150]}...")

        if m.recipient == "Human":
            # Extract report (like cluster_simulation.py lines 788-798)
            content_str = str(m.content)
            report_match = re.search(r'\[report:\s*(\{.*?\})\s*\]', content_str)
            report_suffix = ""
            if report_match:
                print(f"    [OK] Found report: {report_match.group(1)}")
                report_suffix = f" [report: {report_match.group(1)}]"
                # Remove report from content before parsing
                content_str = content_str[:report_match.start()] + content_str[report_match.end():]
                content_str = content_str.strip()
            else:
                print(f"    [WARNING] No report found in message!")

            # Parse and format (lines 800-803)
            parsed = human_comm.parse_content(m.sender, m.recipient, content_str)
            formatted = human_comm.format_content(m.sender, m.recipient, parsed)

            # Re-append report
            final_message = formatted + report_suffix
            reply_texts.append(final_message)

            print(f"    Final message: {final_message[:150]}...")

            # Check if report is still present
            if "[report:" in final_message:
                print(f"    [OK] Report preserved in final message")
            else:
                print(f"    [ERROR] Report lost in final message!")

    # Return reply (line 842)
    reply = "\n".join(reply_texts).strip()

    print(f"\n[STEP 6] Return reply to UI")
    print(f"Reply length: {len(reply)}")
    print(f"Reply: {reply}")

    if not reply:
        print("\n[ERROR] No reply! Agent didn't send any messages!")
        return False

    if "[report:" not in reply:
        print("\n[ERROR] Reply doesn't contain [report: tag]!")
        return False

    print("\n" + "=" * 70)
    print("[SUCCESS] Full UI flow works correctly!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = simulate_on_send_flow()
    exit(0 if success else 1)
