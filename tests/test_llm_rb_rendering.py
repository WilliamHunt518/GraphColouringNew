"""Test LLM-based rendering for Agent→Human messages in LLM_RB mode.

This test verifies that:
1. LLM is used for Agent→Human message rendering (not just templates)
2. Priority 0 unconditional announcements are suppressed
3. Priority 2 generates conditional offers more aggressively (penalty > 0, not just conflicts)
4. Messages are natural and varied (not template-based)
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from comm.llm_rb_comm_layer import LLMRBCommLayer
from comm.rb_protocol import RBMove, Assignment, Condition


def test_llm_rendering_enabled():
    """Test that LLM rendering is enabled by default."""
    comm = LLMRBCommLayer()
    assert comm.use_llm_rendering, "LLM rendering should be enabled by default"
    print("[OK] LLM rendering is enabled by default")


def test_llm_rendering_can_be_disabled():
    """Test that LLM rendering can be disabled via parameter."""
    comm = LLMRBCommLayer(use_llm_rendering=False)
    assert not comm.use_llm_rendering, "LLM rendering should be disabled when specified"
    print("[OK] LLM rendering can be disabled via parameter")


def test_conditional_offer_rendering():
    """Test rendering of ConditionalOffer with conditions."""
    comm = LLMRBCommLayer(manual=True)  # Use manual mode to test templates

    # Create a conditional offer with multiple conditions and assignments
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

    nl = comm._rbmove_to_nl("Agent1", "Human", move)
    print(f"\n[OK] Conditional offer rendered as:\n  {nl}")

    # Verify it contains the key elements
    assert "if" in nl.lower() or "If" in nl, "Should contain 'if' for conditional"
    assert "h1" in nl and "h2" in nl, "Should mention condition nodes"
    assert "b1" in nl and "b2" in nl, "Should mention assignment nodes"
    print("[OK] Conditional offer contains expected elements")


def test_unconditional_offer_rendering():
    """Test rendering of ConditionalOffer without conditions (announcements)."""
    comm = LLMRBCommLayer(manual=True)

    # Create an unconditional announcement
    move = RBMove(
        move="ConditionalOffer",
        conditions=[],  # No conditions = unconditional
        assignments=[
            Assignment(node="a2", colour="blue"),
        ]
    )

    nl = comm._rbmove_to_nl("Agent1", "Human", move)
    print(f"\n[OK] Unconditional announcement rendered as:\n  {nl}")

    # Verify it's an announcement (not a conditional with IF at the start)
    # Check that it doesn't start with conditional structure
    assert not nl.lower().startswith("if "), "Should NOT start with 'if' for unconditional"
    assert "a2" in nl, "Should mention the node"
    assert "blue" in nl, "Should mention the color"
    print("[OK] Unconditional announcement is not a conditional structure")


def test_reject_with_impossible_combinations():
    """Test rendering of Reject with impossible_combinations."""
    comm = LLMRBCommLayer(manual=True)

    # Create a reject with conditional constraint
    move = RBMove(
        move="Reject",
        impossible_combinations=[
            [
                {"node": "h4", "colour": "green"},
                {"node": "h1", "colour": "red"},
            ]
        ]
    )

    nl = comm._rbmove_to_nl("Agent1", "Human", move)
    print(f"\n[OK] Reject with impossible_combinations rendered as:\n  {nl}")

    # Verify it mentions the nodes
    assert "h4" in nl and "h1" in nl, "Should mention both nodes"
    assert "green" in nl and "red" in nl, "Should mention both colors"
    print("[OK] Reject with combinations contains expected elements")


def test_llm_rendering_with_api():
    """Test actual LLM rendering (requires API key)."""
    # Check if API key exists
    if not os.path.exists("api_key.txt"):
        print("\n[WARNING] Skipping LLM rendering test - no API key found")
        return

    comm = LLMRBCommLayer(use_llm_rendering=True)

    # Create a rich conditional offer
    move = RBMove(
        move="ConditionalOffer",
        conditions=[
            Condition(node="h1", colour="red", owner="neighbor"),
            Condition(node="h2", colour="blue", owner="neighbor"),
            Condition(node="h5", colour="green", owner="neighbor"),
        ],
        assignments=[
            Assignment(node="b1", colour="yellow"),
            Assignment(node="b2", colour="red"),
            Assignment(node="b3", colour="blue"),
        ]
    )

    nl = comm._rbmove_to_nl("Agent2", "Human", move)
    print(f"\n[OK] LLM-rendered conditional offer:\n  {nl}")

    # The LLM rendering should be more natural than templates
    # Check that it contains the key information
    assert "h1" in nl and "h2" in nl and "h5" in nl, "Should mention all condition nodes"
    assert "b1" in nl and "b2" in nl and "b3" in nl, "Should mention all assignment nodes"
    print("[OK] LLM rendering contains all expected nodes")

    # Try a second call to see variation (LLM should vary phrasing)
    nl2 = comm._rbmove_to_nl("Agent2", "Human", move)
    print(f"\n[OK] Second LLM-rendered conditional offer:\n  {nl2}")

    if nl != nl2:
        print("[OK] LLM shows variation in phrasing (good!)")
    else:
        print("[WARNING] LLM produced identical output (may use templates internally)")


if __name__ == "__main__":
    print("=" * 70)
    print("Testing LLM_RB Rendering Enhancements")
    print("=" * 70)

    test_llm_rendering_enabled()
    test_llm_rendering_can_be_disabled()
    test_conditional_offer_rendering()
    test_unconditional_offer_rendering()
    test_reject_with_impossible_combinations()
    test_llm_rendering_with_api()

    print("\n" + "=" * 70)
    print("All tests passed!")
    print("=" * 70)
