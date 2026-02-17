"""Test that LLM rendering uses correct perspective (you vs I).

When Agent B sends a message to Human:
- Conditions (human's nodes like h1, h2) should use "you"
- Assignments (agent's nodes like b1, b2) should use "I"

CRITICAL: Agent should NEVER say "if you set b2..." (referring to its own nodes)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from comm.llm_rb_comm_layer import LLMRBCommLayer
from comm.rb_protocol import RBMove, Assignment, Condition


def test_perspective_agent_to_human():
    """Test that Agent->Human uses correct perspective."""
    # Check if API key exists
    if not os.path.exists("api_key.txt"):
        print("[WARNING] Skipping test - no API key found")
        return

    comm = LLMRBCommLayer(use_llm_rendering=True)

    # Agent2 sends to Human
    # Conditions: h1, h2 (Human's nodes) -> should say "you"
    # Assignments: b1, b2 (Agent2's nodes) -> should say "I"
    move = RBMove(
        move="ConditionalOffer",
        conditions=[
            Condition(node="h1", colour="red", owner="neighbor"),
            Condition(node="h2", colour="blue", owner="neighbor"),
        ],
        assignments=[
            Assignment(node="b1", colour="green"),
            Assignment(node="b2", colour="yellow"),
        ]
    )

    nl = comm._rbmove_to_nl("Agent2", "Human", move)
    print(f"\nAgent2 -> Human:")
    print(f"  {nl}")

    # Verify perspective
    errors = []

    # Check conditions (h nodes) - should be phrased as "you"
    if "h1" in nl or "h2" in nl:
        # Good - mentions the condition nodes
        # Now check that they're associated with "you" language
        # Look for patterns like "if you set h1" or "you could do h1"
        nl_lower = nl.lower()

        # Bad patterns: "I set h1", "I'll set h2", "my h1"
        bad_patterns = [
            ("i set h1", "Agent should not say 'I set h1' (h1 is human's node)"),
            ("i set h2", "Agent should not say 'I set h2' (h2 is human's node)"),
            ("i'll set h1", "Agent should not say 'I'll set h1' (h1 is human's node)"),
            ("i'll set h2", "Agent should not say 'I'll set h2' (h2 is human's node)"),
            ("my h1", "Agent should not say 'my h1' (h1 is human's node)"),
            ("my h2", "Agent should not say 'my h2' (h2 is human's node)"),
        ]

        for pattern, error_msg in bad_patterns:
            if pattern in nl_lower:
                errors.append(error_msg)
                print(f"  [ERROR] {error_msg}")

    # Check assignments (b nodes) - should be phrased as "I"
    if "b1" in nl or "b2" in nl:
        # Good - mentions the assignment nodes
        # Now check that they're associated with "I" language
        nl_lower = nl.lower()

        # Bad patterns: "you set b1", "your b2"
        bad_patterns = [
            ("you set b1", "Agent should not say 'you set b1' (b1 is agent's node)"),
            ("you set b2", "Agent should not say 'you set b2' (b2 is agent's node)"),
            ("you could set b1", "Agent should not say 'you could set b1' (b1 is agent's node)"),
            ("you could set b2", "Agent should not say 'you could set b2' (b2 is agent's node)"),
            ("your b1", "Agent should not say 'your b1' (b1 is agent's node)"),
            ("your b2", "Agent should not say 'your b2' (b2 is agent's node)"),
        ]

        for pattern, error_msg in bad_patterns:
            if pattern in nl_lower:
                errors.append(error_msg)
                print(f"  [ERROR] {error_msg}")

    if errors:
        print(f"\n[FAIL] Found {len(errors)} perspective error(s)")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print(f"  [OK] Perspective is correct")
        return True


def test_perspective_multiple_calls():
    """Test perspective across multiple LLM calls to check consistency."""
    if not os.path.exists("api_key.txt"):
        print("\n[WARNING] Skipping test - no API key found")
        return

    comm = LLMRBCommLayer(use_llm_rendering=True)

    move = RBMove(
        move="ConditionalOffer",
        conditions=[
            Condition(node="h3", colour="green", owner="neighbor"),
        ],
        assignments=[
            Assignment(node="a1", colour="red"),
            Assignment(node="a2", colour="blue"),
        ]
    )

    print("\nTesting perspective consistency across 3 calls:")
    all_correct = True

    for i in range(3):
        nl = comm._rbmove_to_nl("Agent1", "Human", move)
        print(f"\n  Call {i+1}: {nl}")

        nl_lower = nl.lower()

        # Check for bad patterns
        errors = []
        if "you set a1" in nl_lower or "you set a2" in nl_lower:
            errors.append("Agent1 said 'you set a1/a2' (should be 'I set' for agent's nodes)")
        if "i set h3" in nl_lower or "i'll set h3" in nl_lower:
            errors.append("Agent1 said 'I set h3' (should be 'you set' for human's nodes)")

        if errors:
            print(f"    [ERROR] Perspective issues:")
            for error in errors:
                print(f"      - {error}")
            all_correct = False
        else:
            print(f"    [OK] Perspective correct")

    return all_correct


if __name__ == "__main__":
    print("=" * 70)
    print("Testing LLM_RB Perspective Correctness")
    print("=" * 70)

    result1 = test_perspective_agent_to_human()
    result2 = test_perspective_multiple_calls()

    print("\n" + "=" * 70)
    if result1 and result2:
        print("All perspective tests passed!")
    else:
        print("SOME TESTS FAILED - perspective errors detected")
    print("=" * 70)
