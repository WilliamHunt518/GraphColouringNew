"""Test script for impossible conditions feature.

This script verifies that:
1. RBMove can store and serialize impossible_conditions
2. parse_rb correctly parses impossible_conditions
3. pretty_rb displays impossible conditions in Reject messages
"""

from comm.rb_protocol import RBMove, Condition, Assignment, format_rb, parse_rb, pretty_rb


def test_impossible_conditions():
    """Test the impossible conditions feature."""
    print("=" * 60)
    print("Testing Impossible Conditions Feature")
    print("=" * 60)

    # Test 1: Create a Reject move with impossible conditions
    print("\n1. Creating Reject move with impossible conditions...")
    reject_move = RBMove(
        move="Reject",
        refers_to="offer_123_Agent1",
        reasons=["human_rejected", "unacceptable_terms"],
        impossible_conditions=[
            {"node": "h4", "colour": "green"},
            {"node": "h5", "colour": "red"}
        ]
    )
    print(f"   Created: {reject_move}")

    # Test 2: Serialize to dict
    print("\n2. Serializing to dict...")
    move_dict = reject_move.to_dict()
    print(f"   Dict: {move_dict}")
    assert "impossible_conditions" in move_dict
    assert len(move_dict["impossible_conditions"]) == 2
    print("   [PASS] Serialization successful")

    # Test 3: Format as wire message
    print("\n3. Formatting as wire message...")
    wire_msg = format_rb(reject_move)
    print(f"   Wire format: {wire_msg}")
    assert "[rb:" in wire_msg
    assert "impossible_conditions" in wire_msg
    print("   [PASS] Wire format successful")

    # Test 4: Parse from wire message
    print("\n4. Parsing from wire message...")
    parsed = parse_rb(wire_msg)
    print(f"   Parsed: {parsed}")
    assert parsed is not None
    assert parsed.move == "Reject"
    assert parsed.impossible_conditions is not None
    assert len(parsed.impossible_conditions) == 2
    assert parsed.impossible_conditions[0]["node"] == "h4"
    assert parsed.impossible_conditions[0]["colour"] == "green"
    print("   [PASS] Parsing successful")

    # Test 5: Pretty print
    print("\n5. Pretty printing...")
    pretty_msg = pretty_rb(reject_move)
    print(f"   Pretty: {pretty_msg}")
    assert "marking as impossible" in pretty_msg
    assert "h4=green" in pretty_msg
    assert "h5=red" in pretty_msg
    print("   [PASS] Pretty print successful")

    # Test 6: Reject without impossible conditions (backward compatibility)
    print("\n6. Testing backward compatibility (no impossible conditions)...")
    simple_reject = RBMove(
        move="Reject",
        refers_to="offer_456_Agent2",
        reasons=["human_rejected"]
    )
    wire_msg2 = format_rb(simple_reject)
    parsed2 = parse_rb(wire_msg2)
    pretty_msg2 = pretty_rb(simple_reject)
    print(f"   Wire: {wire_msg2}")
    print(f"   Parsed: {parsed2}")
    print(f"   Pretty: {pretty_msg2}")
    assert parsed2 is not None
    assert parsed2.impossible_conditions is None
    assert "marking as impossible" not in pretty_msg2
    print("   [PASS] Backward compatibility maintained")

    # Test 7: Accept move (should not have impossible_conditions)
    print("\n7. Testing other move types...")
    accept_move = RBMove(
        move="Accept",
        refers_to="offer_789_Agent1"
    )
    accept_dict = accept_move.to_dict()
    print(f"   Accept dict: {accept_dict}")
    assert "impossible_conditions" not in accept_dict or accept_dict.get("impossible_conditions") is None
    print("   [PASS] Other moves unaffected")

    # Test 8: ConditionalOffer (should work normally)
    print("\n8. Testing ConditionalOffer...")
    offer = RBMove(
        move="ConditionalOffer",
        offer_id="offer_test_123",
        conditions=[
            Condition(node="h1", colour="red", owner="Human")
        ],
        assignments=[
            Assignment(node="a2", colour="blue")
        ]
    )
    offer_msg = format_rb(offer)
    parsed_offer = parse_rb(offer_msg)
    pretty_offer = pretty_rb(offer)
    print(f"   Wire: {offer_msg[:100]}...")
    print(f"   Pretty: {pretty_offer}")
    assert parsed_offer is not None
    assert parsed_offer.move == "ConditionalOffer"
    print("   [PASS] ConditionalOffer works normally")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    test_impossible_conditions()
