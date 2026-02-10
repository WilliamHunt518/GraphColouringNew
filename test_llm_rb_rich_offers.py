"""Test LLM_RB parsing of rich multi-node conditional offers.

This test verifies that LLM_RB mode can parse rich conditional offers
with multiple nodes in both the condition and assignment parts.
"""

import sys
import io
from comm.llm_rb_comm_layer import LLMRBCommLayer

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def test_rich_conditional_offers():
    """Test parsing of rich multi-node conditional offers."""

    # Create LLMRBCommLayer in manual mode (no API calls)
    comm = LLMRBCommLayer(manual=True)

    test_cases = [
        # Single-node conditional (baseline)
        {
            "input": "If you could set h1 to red, then I could set b1 to green",
            "expected_conditions": 1,
            "expected_assignments": 1,
        },
        # Multi-node conditional (rich offer)
        {
            "input": "If you do h1=red AND h2=blue, then I can do b1=green AND b2=yellow",
            "expected_conditions": 2,
            "expected_assignments": 2,
        },
        # Very rich conditional (3+ nodes)
        {
            "input": "If you could set h1 to red, h2 to blue, and h5 to green, then I could handle b1=yellow, b2=red, and b3=blue",
            "expected_conditions": 3,
            "expected_assignments": 3,
        },
        # Natural language variant
        {
            "input": "If you could do h1 red and h2 blue, then I'll set b1 green and b2 yellow",
            "expected_conditions": 2,
            "expected_assignments": 2,
        },
    ]

    print("=" * 80)
    print("Testing LLM_RB Rich Conditional Offer Parsing")
    print("=" * 80)

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['input']}")
        print("-" * 80)

        # Parse the message
        result = comm.parse_content("Human", "Agent1", test["input"])

        if result is None:
            print(f"[FAILED] Returned None (no parse)")
            failed += 1
            continue

        # Check if it's a ConditionalOffer
        if not hasattr(result, 'move') or result.move != "ConditionalOffer":
            print(f"[FAILED] Not a ConditionalOffer (got {result.move if hasattr(result, 'move') else 'unknown'})")
            failed += 1
            continue

        # Count conditions and assignments
        conditions = getattr(result, 'conditions', None) or []
        assignments = getattr(result, 'assignments', None) or []

        num_conditions = len(conditions)
        num_assignments = len(assignments)

        print(f"Parsed: {num_conditions} conditions, {num_assignments} assignments")

        if conditions:
            print(f"  Conditions: {[(c.node, c.colour) for c in conditions]}")
        if assignments:
            print(f"  Assignments: {[(a.node, a.colour) for a in assignments]}")

        # Check expectations
        expected_cond = test['expected_conditions']
        expected_assign = test['expected_assignments']

        if num_conditions == expected_cond and num_assignments == expected_assign:
            print(f"[PASSED] Got expected {expected_cond} conditions and {expected_assign} assignments")
            passed += 1
        else:
            print(f"[FAILED] Expected {expected_cond} conditions and {expected_assign} assignments, got {num_conditions} and {num_assignments}")
            failed += 1

    print("\n" + "=" * 80)
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)

    if failed > 0:
        print("\n[WARNING] Some tests failed. The heuristic parser may need further tuning.")
        print("Note: These tests use the heuristic parser (manual=True).")
        print("The LLM-based parser (manual=False) may perform better on complex cases.")
    else:
        print("\n[SUCCESS] All tests passed! Rich conditional offers are being parsed correctly.")

    return passed, failed

def test_agent_to_human_rendering():
    """Test rendering of rich conditional offers from agents to humans."""
    from comm.rb_protocol import RBMove, Condition, Assignment

    comm = LLMRBCommLayer(manual=True)

    print("\n" + "=" * 80)
    print("Testing Agent->Human Rendering of Rich Conditional Offers")
    print("=" * 80)

    # Create a rich conditional offer
    conditions = [
        Condition(node="h1", colour="red", owner="Human"),
        Condition(node="h2", colour="blue", owner="Human"),
        Condition(node="h5", colour="green", owner="Human"),
    ]

    assignments = [
        Assignment(node="b1", colour="yellow"),
        Assignment(node="b2", colour="red"),
        Assignment(node="b3", colour="blue"),
    ]

    rb_move = RBMove(
        move="ConditionalOffer",
        conditions=conditions,
        assignments=assignments,
        offer_id="test_offer_123"
    )

    # Render to natural language
    nl_text = comm._rbmove_to_nl("Agent1", "Human", rb_move)

    print(f"\nRBMove:")
    print(f"  Conditions: {[(c.node, c.colour) for c in conditions]}")
    print(f"  Assignments: {[(a.node, a.colour) for a in assignments]}")
    print(f"\nRendered Natural Language:")
    print(f"  {nl_text}")

    # Check that it mentions multiple nodes
    has_multiple_conditions = all(c.node in nl_text for c in conditions)
    has_multiple_assignments = all(a.node in nl_text for a in assignments)

    if has_multiple_conditions and has_multiple_assignments:
        print(f"\n[PASSED] Rendering includes all nodes from both conditions and assignments")
        return True
    else:
        print(f"\n[FAILED] Rendering is missing some nodes")
        print(f"   All conditions present: {has_multiple_conditions}")
        print(f"   All assignments present: {has_multiple_assignments}")
        return False

if __name__ == "__main__":
    print("\nLLM_RB Rich Conditional Offer Test Suite\n")

    # Test parsing (human -> agent)
    parse_passed, parse_failed = test_rich_conditional_offers()

    # Test rendering (agent -> human)
    render_ok = test_agent_to_human_rendering()

    print("\n" + "=" * 80)
    print("OVERALL RESULTS")
    print("=" * 80)
    print(f"Parsing: {parse_passed} passed, {parse_failed} failed")
    print(f"Rendering: [PASSED]" if render_ok else "Rendering: [FAILED]")

    if parse_failed == 0 and render_ok:
        print("\n[SUCCESS] All tests passed! LLM_RB mode supports rich multi-node conditional offers.")
        sys.exit(0)
    else:
        print("\n[WARNING] Some tests failed. See details above.")
        sys.exit(1)
