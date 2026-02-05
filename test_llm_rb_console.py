"""Console test for LLM_RB communication layer.

Tests the parse/format flow without UI.
"""

import sys
from comm.llm_rb_comm_layer import LLMRBCommLayer
from comm.rb_protocol import RBMove, Condition, Assignment, format_rb

def test_parse_and_format():
    """Test parsing and formatting of RBMove messages."""

    # Create comm layer (manual=True to avoid LLM calls for deterministic testing)
    comm = LLMRBCommLayer(manual=False)  # Set to False to use actual LLM

    print("="*60)
    print("LLM_RB Console Test")
    print("="*60)

    # Test 1: Simple PROPOSE
    print("\n--- Test 1: Simple PROPOSE ---")
    move1 = RBMove(move="Propose", node="h1", colour="red", reasons=[])
    formatted1 = format_rb(move1)
    print(f"Agent sends: {formatted1}")

    parsed1 = comm.parse_content("Agent1", "Human", formatted1)
    print(f"Parsed type: {type(parsed1).__name__}")
    print(f"Parsed move: {parsed1.move if hasattr(parsed1, 'move') else 'N/A'}")

    display1 = comm.format_content("Agent1", "Human", parsed1)
    print(f"Human sees: {display1[:100]}...")

    # Test 2: ConditionalOffer
    print("\n--- Test 2: ConditionalOffer ---")
    move2 = RBMove(
        move="ConditionalOffer",
        node=None,
        colour=None,
        reasons=["test"],
        conditions=[
            Condition(node="h2", colour="red", owner="Human"),
            Condition(node="h5", colour="green", owner="Human")
        ],
        assignments=[
            Assignment(node="b2", colour="blue")
        ],
        offer_id="test_offer_123"
    )
    formatted2 = format_rb(move2)
    print(f"Agent sends: {formatted2[:80]}...")

    parsed2 = comm.parse_content("Agent2", "Human", formatted2)
    print(f"Parsed type: {type(parsed2).__name__}")
    if hasattr(parsed2, 'conditions'):
        print(f"  Conditions: {len(parsed2.conditions or [])} items")
        if parsed2.conditions:
            print(f"    - {parsed2.conditions[0].node}={parsed2.conditions[0].colour}")
    if hasattr(parsed2, 'assignments'):
        print(f"  Assignments: {len(parsed2.assignments or [])} items")
        if parsed2.assignments:
            print(f"    - {parsed2.assignments[0].node}={parsed2.assignments[0].colour}")

    display2 = comm.format_content("Agent2", "Human", parsed2)
    print(f"Human sees: {display2[:120]}...")

    # Test 3: Human natural language input
    print("\n--- Test 3: Human Natural Language ---")
    human_text = "I can do h1=red if you do h2=blue"
    print(f"Human types: {human_text}")

    parsed_human = comm.parse_content("Human", "Agent1", human_text)
    print(f"Parsed type: {type(parsed_human).__name__}")
    if hasattr(parsed_human, 'move'):
        print(f"Parsed as: {parsed_human.move}")
        print(f"  Node: {parsed_human.node}")
        print(f"  Colour: {parsed_human.colour}")

    formatted_human = comm.format_content("Human", "Agent1", parsed_human)
    print(f"Agent receives: {formatted_human[:100]}...")

    print("\n" + "="*60)
    print("Test Complete")
    print("="*60)

    return True

if __name__ == "__main__":
    try:
        success = test_parse_and_format()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
