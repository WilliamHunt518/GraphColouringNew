"""Test the new conditional proposal protocol."""

from comm.rb_protocol import RBMove, Condition, Assignment, format_rb, parse_rb, pretty_rb
import time

def test_conditional_offer():
    """Test creating and parsing a conditional offer."""
    print("=== Test 1: Conditional Offer ===")

    # Create a conditional offer
    offer = RBMove(
        move="ConditionalOffer",
        offer_id=f"offer_{int(time.time())}_Agent1",
        conditions=[
            Condition(node="h1", colour="red", owner="Human"),
            Condition(node="h4", colour="green", owner="Human"),
        ],
        assignments=[
            Assignment(node="a2", colour="blue"),
            Assignment(node="a3", colour="yellow"),
        ],
        reasons=["penalty=0.000", "mutual_benefit"]
    )

    # Format to wire format
    wire_format = format_rb(offer)
    print(f"Wire format: {wire_format}")

    # Pretty print
    pretty = pretty_rb(offer)
    print(f"Pretty format: {pretty}")

    # Parse back
    parsed = parse_rb(wire_format)
    print(f"Parsed: {parsed}")
    print(f"Parsed conditions: {parsed.conditions if parsed else None}")
    print(f"Parsed assignments: {parsed.assignments if parsed else None}")
    print()

def test_counter_proposal():
    """Test creating and parsing a counter proposal."""
    print("=== Test 2: Counter Proposal ===")

    counter = RBMove(
        move="CounterProposal",
        node="h1",
        colour="blue",
        refers_to="proposal_h1_red",
        reasons=["conflicts_with_fixed_a5"]
    )

    wire_format = format_rb(counter)
    print(f"Wire format: {wire_format}")

    pretty = pretty_rb(counter)
    print(f"Pretty format: {pretty}")

    parsed = parse_rb(wire_format)
    print(f"Parsed: {parsed}")
    print()

def test_accept():
    """Test creating and parsing an accept move."""
    print("=== Test 3: Accept ===")

    accept = RBMove(
        move="Accept",
        refers_to="offer_1643234567",
        reasons=["accepted_conditional_offer"]
    )

    wire_format = format_rb(accept)
    print(f"Wire format: {wire_format}")

    pretty = pretty_rb(accept)
    print(f"Pretty format: {pretty}")

    parsed = parse_rb(wire_format)
    print(f"Parsed: {parsed}")
    print()

def test_legacy_compatibility():
    """Test backward compatibility with old move types."""
    print("=== Test 4: Legacy Compatibility ===")

    # Old Challenge move should map to CounterProposal
    old_challenge = '[rb:{"move": "Challenge", "node": "h1", "colour": "red"}]'
    parsed = parse_rb(old_challenge)
    print(f"Old Challenge '[rb:{{\"move\": \"Challenge\", ...}}]' parsed as: {parsed.move if parsed else None}")

    # Old Justify move should map to Propose
    old_justify = '[rb:{"move": "Justify", "node": "a2", "colour": "blue"}]'
    parsed = parse_rb(old_justify)
    print(f"Old Justify '[rb:{{\"move\": \"Justify\", ...}}]' parsed as: {parsed.move if parsed else None}")
    print()

def test_simple_moves():
    """Test simple Propose and Commit moves still work."""
    print("=== Test 5: Simple Moves ===")

    propose = RBMove(
        move="Propose",
        node="h1",
        colour="red",
        reasons=["initial_proposal"]
    )

    wire = format_rb(propose)
    print(f"Propose wire: {wire}")
    print(f"Propose pretty: {pretty_rb(propose)}")

    commit = RBMove(
        move="Commit",
        node="a2",
        colour="blue",
        reasons=["satisfied_with_proposal"]
    )

    wire = format_rb(commit)
    print(f"Commit wire: {wire}")
    print(f"Commit pretty: {pretty_rb(commit)}")
    print()

if __name__ == "__main__":
    test_conditional_offer()
    test_counter_proposal()
    test_accept()
    test_legacy_compatibility()
    test_simple_moves()
    print("All tests completed!")
