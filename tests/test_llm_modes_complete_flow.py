"""Comprehensive integration test for LLM_TOOL and LLM_REACT modes.

Tests the complete announcement + first message flow:
1. Agent announces configuration with [report: ...] tag
2. Agent generates substantive first message analyzing conflicts
3. Messages are properly formatted and sent through comm layer
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.react_cluster_agent import ReActClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_agent(agent_class, agent_name_str):
    """Test a single agent type."""
    print(f"\n{'='*70}")
    print(f"TESTING {agent_name_str}")
    print(f"{'='*70}")

    # Setup graph with conflicts
    nodes = ["a1", "a2", "h1", "h2"]
    edges = [("a1", "h1"), ("a2", "h1"), ("a2", "h2")]
    domain = ["red", "blue", "green"]
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    comm_layer = SpeechLLMLayer(use_llm=False)

    print(f"\n[1] Creating agent...")
    try:
        agent = agent_class(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2"],
            owners=owners,
            backend_model="gpt-4-turbo",
            algorithm="greedy"
        )
        print(f"   [OK] Agent created successfully")
    except SystemExit as e:
        print(f"   [ERROR] FAILED: {e}")
        return False

    print(f"   Initial assignments: {agent.assignments}")
    print(f"   Phase: {agent._phase}")

    # Set human's boundary colors (to create conflicts)
    print(f"\n[2] Setting human's boundary colors...")
    agent.neighbour_assignments = {"h1": "red", "h2": "blue"}
    print(f"   Human boundaries: {agent.neighbour_assignments}")

    # Send __ANNOUNCE_CONFIG__ (bypassing comm layer like GUI does)
    print(f"\n[3] Sending __ANNOUNCE_CONFIG__...")
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.sent_messages = []  # Clear for testing
    agent.receive(msg)

    print(f"\n[4] Verifying announcement phase...")
    print(f"   Phase: {agent._phase}")
    print(f"   Config announced: {agent._config_announced}")
    print(f"   Messages sent: {len(agent.sent_messages)}")
    print(f"   Should generate first: {getattr(agent, '_should_generate_first_message', 'N/A')}")

    if len(agent.sent_messages) < 1:
        print(f"   [ERROR] FAILED: No announcement message sent")
        return False

    # Check announcement message
    announcement = agent.sent_messages[0]
    announcement_str = str(announcement.content)
    print(f"\n   [ANNOUNCEMENT MESSAGE]")
    print(f"   To: {announcement.recipient}")
    print(f"   Content preview: {announcement_str[:100]}...")

    if "[report:" not in announcement_str:
        print(f"   [ERROR] FAILED: Missing [report: ...] tag in announcement")
        return False
    print(f"   [OK] Contains [report: ...] tag")

    # Call step() to generate first substantive message
    print(f"\n[5] Calling step() to generate first substantive message...")
    print(f"   (This will take several seconds due to LLM calls)")
    agent.step()

    print(f"\n[6] Verifying first message generation...")
    print(f"   Total messages: {len(agent.sent_messages)}")
    print(f"   Should generate first: {getattr(agent, '_should_generate_first_message', 'N/A')}")

    if len(agent.sent_messages) < 2:
        print(f"   [ERROR] FAILED: No substantive message generated")
        return False

    # Check substantive messages
    print(f"\n   [SUBSTANTIVE MESSAGES]")
    for i in range(1, len(agent.sent_messages)):
        msg = agent.sent_messages[i]
        msg_str = str(msg.content)
        print(f"   Message {i}: to={msg.recipient}, preview={msg_str[:80]}...")

    print(f"\n   [OK] Generated {len(agent.sent_messages) - 1} substantive message(s)")

    # Verify message content is substantive (not just another announcement)
    first_substantive = str(agent.sent_messages[1].content)
    if "Here's my initial configuration" in first_substantive:
        print(f"   [WARNING] First message looks like duplicate announcement")
    elif any(keyword in first_substantive.lower() for keyword in ["propose", "suggest", "change", "conflict", "works for me"]):
        print(f"   [OK] First message is substantive (contains proposal/analysis)")
    else:
        print(f"   ? First message format unclear")

    print(f"\n{'='*70}")
    print(f"{agent_name_str}: PASSED [OK]")
    print(f"{'='*70}")
    return True


def main():
    """Run tests for both agent types."""
    print("\n" + "="*70)
    print("COMPREHENSIVE LLM MODES INTEGRATION TEST")
    print("="*70)

    results = {}

    # Test LLM_TOOL mode
    try:
        results['LLM_TOOL'] = test_agent(ToolCallingClusterAgent, "LLM_TOOL (Function Calling)")
    except Exception as e:
        print(f"\n[ERROR] LLM_TOOL test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results['LLM_TOOL'] = False

    # Test LLM_REACT mode
    try:
        results['LLM_REACT'] = test_agent(ReActClusterAgent, "LLM_REACT (ReAct Pattern)")
    except Exception as e:
        print(f"\n[ERROR] LLM_REACT test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results['LLM_REACT'] = False

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for mode, passed in results.items():
        status = "[OK] PASSED" if passed else "[ERROR] FAILED"
        print(f"  {mode}: {status}")

    all_passed = all(results.values())
    print("\n" + "="*70)
    if all_passed:
        print("ALL TESTS PASSED [OK]")
    else:
        print("SOME TESTS FAILED [ERROR]")
    print("="*70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
