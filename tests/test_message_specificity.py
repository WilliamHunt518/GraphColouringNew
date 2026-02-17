"""Test message specificity after Iteration 1 prompt improvements.

Checks that agents produce specific, actionable messages instead of vague ones.
"""

import sys
import json
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.react_cluster_agent import ReActClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


# Vague phrases that should NOT appear in messages
VAGUE_PHRASES = [
    "make a change",
    "adjust colors",
    "modify",
    "reconsider",
    "let's",
    "we should",
    "might need",
    "consider changing",
    "a neighboring node",
    "some boundary nodes",
    "certain colors",
    "review this setup",
    "further reduce",
]


def extract_structured_content(message_content):
    """Extract structured content from message string (may have [report: ...] suffix)."""
    # Try to find JSON in message
    content_str = str(message_content)

    # Look for patterns like: {"requested_changes": {...}, "reason": "..."}
    # This might be embedded in natural language from speech layer

    # For direct testing, return the content as-is if it's already structured
    if isinstance(message_content, dict):
        return message_content

    # Try to parse JSON from string
    try:
        # Remove [report: ...] suffix if present
        if "[report:" in content_str:
            content_str = content_str.split("[report:")[0].strip()
        return json.loads(content_str)
    except:
        # If not JSON, try to extract from natural language
        # Check for node=color patterns
        requested = {}
        for match in re.finditer(r'\b([a-z]\d+)\s*=\s*(\w+)', content_str):
            node, color = match.groups()
            requested[node] = color

        return {
            "reason": content_str,
            "requested_changes": requested
        }


def check_message_specificity(agent_name, agent_class):
    """Test message specificity for an agent class."""
    print(f"\n{'='*70}")
    print(f"TESTING MESSAGE SPECIFICITY: {agent_name}")
    print(f"{'='*70}")

    # Setup graph with conflicts
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
    comm_layer = SpeechLLMLayer(use_llm=False)  # Disable LLM for faster testing

    print(f"\n[1] Creating agent...")
    try:
        agent = agent_class(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2", "a4"],
            owners=owners,
            backend_model="gpt-4-turbo",
            algorithm="greedy"
        )
        print(f"   [OK] Agent created")
    except SystemExit as e:
        print(f"   [ERROR] Failed to create agent: {e}")
        return False

    print(f"   Agent nodes: {agent.nodes}")
    print(f"   Agent assignments: {agent.assignments}")

    # Set conflicting neighbor colors
    print(f"\n[2] Setting up conflicts...")
    agent.assignments = {"a1": "green", "a2": "red", "a4": "red"}
    agent.neighbour_assignments = {"h1": "red", "h4": "red"}  # Conflicts with a2 and a4
    print(f"   Agent: {agent.assignments}")
    print(f"   Human: {agent.neighbour_assignments}")

    # Get penalty to verify conflicts exist
    penalty, conflicts = agent.api.get_current_penalty()
    print(f"   Penalty: {penalty}, Conflicts: {conflicts}")

    if penalty == 0:
        print(f"   [WARNING] No conflicts detected - test may not be meaningful")

    # Send announcement trigger
    print(f"\n[3] Triggering announcement...")
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.sent_messages = []
    agent.receive(msg)

    print(f"   Messages after announcement: {len(agent.sent_messages)}")

    # Send a human message to trigger agent response (agents wait for human messages)
    print(f"\n[4] Sending human message to trigger agent response...")
    human_msg = Message(
        sender="Human",
        recipient="Agent1",
        content="I've announced my configuration. What changes would you like me to make?"
    )
    agent.receive(human_msg)

    # Generate response
    print(f"\n[5] Agent generating response (this will take time with LLM calls)...")
    agent.step()

    print(f"   Total messages: {len(agent.sent_messages)}")

    # Analyze messages for specificity
    print(f"\n[6] ANALYZING MESSAGE SPECIFICITY")
    print(f"   {'='*60}")

    issues_found = []
    specific_count = 0
    vague_count = 0

    for i, sent_msg in enumerate(agent.sent_messages[1:], 1):  # Skip announcement
        print(f"\n   [Message {i}]")
        print(f"   To: {sent_msg.recipient}")

        content_str = str(sent_msg.content)
        print(f"   Content: {content_str[:200]}...")

        # Extract structured content
        structured = extract_structured_content(sent_msg.content)
        reason = structured.get("reason", "")
        requested = structured.get("requested_changes", {})

        print(f"   Requested changes: {requested}")

        # Check 1: Vague phrases
        vague_found = []
        reason_lower = reason.lower()
        for phrase in VAGUE_PHRASES:
            if phrase.lower() in reason_lower:
                vague_found.append(phrase)

        if vague_found:
            vague_count += 1
            issue = f"Message {i} contains vague phrases: {vague_found}"
            issues_found.append(issue)
            print(f"   [X] VAGUE: {vague_found}")
        else:
            print(f"   [OK] No vague phrases detected")

        # Check 2: requested_changes populated (if conflicts exist)
        if penalty > 0:
            if not requested or len(requested) == 0:
                issue = f"Message {i} has empty requested_changes despite penalty={penalty}"
                issues_found.append(issue)
                print(f"   [X] EMPTY requested_changes (penalty={penalty})")
            else:
                # Check if contains actual node names (not placeholders)
                has_valid_nodes = any(
                    isinstance(node, str) and len(node) >= 2
                    for node in requested.keys()
                )
                if has_valid_nodes:
                    specific_count += 1
                    print(f"   [OK] SPECIFIC: Contains node-color pairs")
                else:
                    issue = f"Message {i} has invalid node names in requested_changes: {requested}"
                    issues_found.append(issue)
                    print(f"   [X] INVALID node names: {requested}")

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Messages analyzed: {len(agent.sent_messages) - 1}")
    print(f"Specific messages: {specific_count}")
    print(f"Vague messages: {vague_count}")
    print(f"Issues found: {len(issues_found)}")

    if issues_found:
        print(f"\n[X] ISSUES DETECTED:")
        for issue in issues_found:
            print(f"   - {issue}")
        return False
    else:
        print(f"\n[OK] ALL MESSAGES ARE SPECIFIC!")
        return True


def main():
    """Run tests for both agent types."""
    print("="*70)
    print("MESSAGE SPECIFICITY TEST (After Iteration 1)")
    print("="*70)

    results = {}

    # Test LLM_TOOL
    try:
        results['LLM_TOOL'] = check_message_specificity("LLM_TOOL", ToolCallingClusterAgent)
    except Exception as e:
        print(f"\n[X] LLM_TOOL test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results['LLM_TOOL'] = False

    # Test LLM_REACT
    try:
        results['LLM_REACT'] = check_message_specificity("LLM_REACT", ReActClusterAgent)
    except Exception as e:
        print(f"\n[X] LLM_REACT test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results['LLM_REACT'] = False

    # Final summary
    print(f"\n{'='*70}")
    print(f"FINAL RESULTS")
    print(f"{'='*70}")
    for mode, passed in results.items():
        status = "[OK] PASSED" if passed else "[X] FAILED"
        print(f"{mode}: {status}")

    all_passed = all(results.values())
    if all_passed:
        print(f"\n[SUCCESS] ALL TESTS PASSED! Messages are specific.")
    else:
        print(f"\n[WARNING] SOME TESTS FAILED. Review issues above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
