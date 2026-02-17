"""Direct test of message formatting to verify the new format."""

import sys
sys.path.insert(0, r"E:\Files\PhD-Main\GC-New\GIT_LOCAL_ROOT\GraphColouringNew")

from comm.llm_rb_comm_layer import LLMRBCommLayer
from comm.rb_protocol import RBMove, Condition, Assignment

# Create comm layer
comm = LLMRBCommLayer(manual=True)  # Manual mode to avoid LLM calls

print("="*60)
print("Direct Format Test - New Message Format")
print("="*60)

# Test 1: Unconditional announcement (no conditions)
print("\n--- Test 1: Unconditional Announcement ---")
move1 = RBMove(
    move="ConditionalOffer",
    node=None,
    colour=None,
    reasons=["initial_configuration"],
    conditions=[],  # No conditions = unconditional
    assignments=[
        Assignment(node="a2", colour="blue"),
        Assignment(node="a4", colour="red"),
        Assignment(node="a5", colour="blue")
    ],
    offer_id="test1"
)
formatted1 = comm.format_content("Agent1", "Human", move1)
print(f"Message: {formatted1}")
print(f"Expected: I'll do a2=blue, a4=red, a5=blue")

# Test 2: Conditional offer (with conditions)
print("\n--- Test 2: Conditional Offer ---")
move2 = RBMove(
    move="ConditionalOffer",
    node=None,
    colour=None,
    reasons=["test"],
    conditions=[
        Condition(node="h1", colour="red", owner="Human"),
        Condition(node="h4", colour="green", owner="Human")
    ],
    assignments=[
        Assignment(node="a2", colour="blue"),
        Assignment(node="a4", colour="blue"),
        Assignment(node="a5", colour="red")
    ],
    offer_id="test2"
)
formatted2 = comm.format_content("Agent1", "Human", move2)
print(f"Message: {formatted2}")
print(f"Expected: Can you do h1=red, h4=green? I'll do a2=blue, a4=blue, a5=red")

# Test 3: Simple PROPOSE
print("\n--- Test 3: Simple PROPOSE ---")
move3 = RBMove(
    move="Propose",
    node="h1",
    colour="red",
    reasons=[]
)
formatted3 = comm.format_content("Agent1", "Human", move3)
print(f"Message: {formatted3}")
print(f"Expected: I can do h1=red")

print("\n" + "="*60)
if "Can you do" in formatted2 and "I'll do" in formatted2:
    print("✓ SUCCESS: New format is working!")
else:
    print("✗ FAIL: Still using old format")
print("="*60)
