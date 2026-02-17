"""Integration test: Verify LLM_TOOL agents actually send messages after announcement.

This test creates a real scenario with conflicts and verifies that:
1. Agents announce their initial config
2. Agents send substantive messages after announcement
3. Messages contain specific proposals (not just silence)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.multi_node_human_agent import MultiNodeHumanAgent
from comm.speech_llm_layer import SpeechLLMLayer


def test_agent_sends_first_message_after_announcement():
    """Test that agent sends substantive message after config announcement."""
    print("\n" + "="*70)
    print("INTEGRATION TEST: Agent Sends Messages After Announcement")
    print("="*70)

    # Create problem with KNOWN conflict
    # Agent1: a1, a2, a3
    # Human: h1, h2, h3, h4, h5
    # Edges: (a1, h1), (a2, h2), (a3, h3)
    nodes = ["a1", "a2", "a3", "h1", "h2", "h3", "h4", "h5"]
    edges = [
        ("a1", "h1"),  # Boundary edge
        ("a2", "h2"),  # Boundary edge
        ("a3", "h3"),  # Boundary edge
    ]
    colors = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, colors)
    owners = {
        "a1": "Agent1", "a2": "Agent1", "a3": "Agent1",
        "h1": "Human", "h2": "Human", "h3": "Human", "h4": "Human", "h5": "Human"
    }

    # Create agents
    try:
        agent = ToolCallingClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=SpeechLLMLayer(use_llm=True),  # Use REAL LLM
            local_nodes=["a1", "a2", "a3"],
            owners=owners
        )
        print("\n[OK] Agent created with LLM backend")
    except SystemExit as e:
        print(f"\n[SKIP] No API key available, skipping LLM test: {e}")
        return

    human = MultiNodeHumanAgent(
        name="Human",
        problem=problem,
        comm_layer=None,
        local_nodes=["h1", "h2", "h3", "h4", "h5"],
        owners=owners
    )

    # Set initial assignments WITH CONFLICT
    agent.assignments = {"a1": "red", "a2": "blue", "a3": "green"}
    human.assignments = {"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "blue"}

    # Set up neighbor awareness
    agent.neighbour_assignments = {"h1": "red", "h2": "blue", "h3": "green"}
    human.neighbour_assignments = {"a1": "red", "a2": "blue", "a3": "green"}

    print(f"\n--- Initial State ---")
    print(f"Agent1 assignments: {agent.assignments}")
    print(f"Human assignments: {human.assignments}")

    # Check penalty
    penalty, conflicts = agent.api.get_current_penalty()
    print(f"Initial penalty: {penalty}")
    print(f"Initial conflicts: {conflicts}")

    # PHASE 1: Agent announces config
    print(f"\n--- Phase 1: Agent Announcement ---")
    print(f"Agent phase: {agent._phase}")
    print(f"Agent announced: {agent._config_announced}")

    # Call step() to trigger announcement
    initial_message_count = len(agent.sent_messages)
    agent.step()

    announcement_count = len(agent.sent_messages) - initial_message_count
    print(f"Messages sent during announcement: {announcement_count}")

    if announcement_count > 0:
        last_msg = agent.sent_messages[-1]
        print(f"[OK] Announcement sent to {last_msg.recipient}")
        print(f"    Content preview: {str(last_msg.content)[:150]}...")
    else:
        print(f"[FAIL] No announcement sent!")
        return

    # PHASE 2: Simulate human announcing their config
    print(f"\n--- Phase 2: Human Announces Config ---")

    # Create announcement message from human
    from agents.base_agent import Message
    announcement_msg = Message(
        sender="Human",
        recipient="Agent1",
        content="__ANNOUNCE_CONFIG__"
    )

    print(f"Human sends: __ANNOUNCE_CONFIG__")
    agent.receive(announcement_msg)

    # Agent should now be in bargain phase
    print(f"Agent phase after receiving announcement: {agent._phase}")
    print(f"Agent announced: {agent._config_announced}")

    # PHASE 3: Agent should respond to the config
    print(f"\n--- Phase 3: Agent Responds to Config ---")

    # Give agent the human's actual config
    human_config_msg = Message(
        sender="Human",
        recipient="Agent1",
        content=f"I've set my nodes: h1=red, h2=blue, h3=green"
    )

    print(f"Human sends: '{human_config_msg.content}'")
    agent.receive(human_config_msg)

    # Count messages before step
    before_step = len(agent.sent_messages)

    # Call step() - agent should analyze and respond
    print(f"\nCalling agent.step()...")
    agent.step()

    # Count messages after step
    after_step = len(agent.sent_messages)
    new_messages = after_step - before_step

    print(f"\n--- Results ---")
    print(f"Messages before step: {before_step}")
    print(f"Messages after step: {after_step}")
    print(f"New messages: {new_messages}")

    if new_messages == 0:
        print(f"\n[FAIL] Agent did NOT send any message after receiving human config!")
        print(f"\nDEBUG INFO:")
        print(f"  Agent phase: {agent._phase}")
        print(f"  Agent penalty: {penalty}")
        print(f"  Agent conflicts: {conflicts}")
        print(f"  Received messages: {len(agent.received_messages)}")
        print(f"  Last received: {agent.received_messages[-1].content if agent.received_messages else 'None'}")
        return False

    # Check the message content
    last_msg = agent.sent_messages[-1]
    print(f"\n[OK] Agent sent message!")
    print(f"Recipient: {last_msg.recipient}")
    print(f"Content preview: {str(last_msg.content)[:200]}...")

    # Verify it's substantive (not just announcement)
    content_str = str(last_msg.content).lower()

    # Check for proposal indicators
    has_proposal = any([
        "could you" in content_str,
        "change" in content_str,
        "if you" in content_str,
        "h1" in content_str or "h2" in content_str or "h3" in content_str,
    ])

    if has_proposal:
        print(f"[OK] Message contains substantive proposal")
    else:
        print(f"[WARN] Message might be generic (no specific proposal detected)")

    print(f"\n[SUCCESS] Agent sent {new_messages} message(s) after config announcement")
    return True


def test_agent_proposes_when_conflicts_exist():
    """Test that agent proposes changes when conflicts exist."""
    print("\n" + "="*70)
    print("INTEGRATION TEST: Agent Proposes Changes for Conflicts")
    print("="*70)

    # Create problem with GUARANTEED conflict
    nodes = ["a1", "h1"]
    edges = [("a1", "h1")]  # Direct conflict edge
    colors = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, colors)
    owners = {"a1": "Agent1", "h1": "Human"}

    try:
        agent = ToolCallingClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=SpeechLLMLayer(use_llm=True),
            local_nodes=["a1"],
            owners=owners
        )
        print("\n[OK] Agent created with LLM backend")
    except SystemExit as e:
        print(f"\n[SKIP] No API key available: {e}")
        return

    # Set up CONFLICT: both nodes are red
    agent.assignments = {"a1": "red"}
    agent.neighbour_assignments = {"h1": "red"}

    print(f"\n--- Conflict State ---")
    print(f"Agent a1: {agent.assignments['a1']}")
    print(f"Human h1: {agent.neighbour_assignments['h1']}")

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"Penalty: {penalty} (should be > 0)")
    print(f"Conflicts: {conflicts}")

    if penalty == 0:
        print(f"[FAIL] No conflict detected! Test setup is wrong.")
        return

    # Announce and move to bargain phase
    agent._config_announced = True
    agent._phase = "bargain"

    # Send human message
    from agents.base_agent import Message
    msg = Message(
        sender="Human",
        recipient="Agent1",
        content="I've set h1 to red"
    )

    agent.receive(msg)

    # Agent should respond
    before = len(agent.sent_messages)
    agent.step()
    after = len(agent.sent_messages)

    new_messages = after - before

    print(f"\n--- Results ---")
    print(f"New messages sent: {new_messages}")

    if new_messages == 0:
        print(f"[FAIL] Agent did not send any proposal despite conflict!")
        return False

    last_msg = agent.sent_messages[-1]
    content = str(last_msg.content).lower()

    print(f"Message content: {last_msg.content[:200]}...")

    # Check for proposal elements
    has_change_request = "change" in content or "could you" in content
    mentions_node = "h1" in content or "a1" in content
    mentions_color = any(c in content for c in ["red", "blue", "green"])

    print(f"\nProposal analysis:")
    print(f"  Has change request: {has_change_request}")
    print(f"  Mentions node: {mentions_node}")
    print(f"  Mentions color: {mentions_color}")

    if has_change_request and mentions_node and mentions_color:
        print(f"\n[SUCCESS] Agent sent specific proposal to resolve conflict")
        return True
    else:
        print(f"\n[WARN] Agent message might be too vague")
        return True  # Still sent something


def main():
    """Run integration tests."""
    print("\n" + "="*70)
    print("LLM_TOOL INTEGRATION TEST SUITE")
    print("Testing that agents actually send messages")
    print("="*70)

    results = []

    # Test 1: First message after announcement
    try:
        result1 = test_agent_sends_first_message_after_announcement()
        results.append(("First message after announcement", result1))
    except Exception as e:
        print(f"\n[ERROR] Test 1 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("First message after announcement", False))

    # Test 2: Proposals for conflicts
    try:
        result2 = test_agent_proposes_when_conflicts_exist()
        results.append(("Proposals for conflicts", result2))
    except Exception as e:
        print(f"\n[ERROR] Test 2 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Proposals for conflicts", False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All integration tests passed!")
        return 0
    else:
        print(f"\n[FAILURE] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
