"""Quick test of RB negotiation to see what's broken."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.rb_protocol import parse_rb, format_rb, pretty_rb, RBMove, Condition, Assignment
import time

# Create a simple test graph
# Human: h1-h2-h3
# Agent1: a1-a2
# Edges between: h1-a1, h3-a2

nodes = ["h1", "h2", "h3", "a1", "a2"]
edges = [
    ("h1", "h2"),
    ("h2", "h3"),
    ("h1", "a1"),
    ("h3", "a2"),
    ("a1", "a2"),
]
domain = ["red", "green", "blue"]
problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)

# Create owners
owners = {
    "h1": "Human", "h2": "Human", "h3": "Human",
    "a1": "Agent1", "a2": "Agent1",
}

# Create a dummy comm layer
class DummyCommLayer:
    def __init__(self):
        self.messages = []

    def send(self, sender, recipient, content):
        self.messages.append((sender, recipient, content))
        print(f"\n[SEND] {sender} -> {recipient}")
        print(f"  {content[:200]}")

    def render_outbound(self, sender, content, assignments=None):
        return content

    def parse_content(self, sender, recipient, content):
        """Parse incoming message content."""
        # For RB mode, just return the content as-is
        return {"raw": content}

comm_layer = DummyCommLayer()

# Create Agent1
agent1 = RuleBasedClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=["a1", "a2"],
    owners=owners,
    algorithm="greedy",
    initial_assignments={"a1": "red", "a2": "green"}
)

print("=" * 80)
print("INITIAL STATE")
print("=" * 80)
print(f"Agent1 assignments: {agent1.assignments}")
print(f"Agent1 neighbours: {agent1.neighbour_assignments}")
print(f"Agent1 boundary nodes: {agent1._get_boundary_nodes_for('Human')}")
print(f"Agent1 phase: {agent1.rb_phase}")

# Simulate phase transition to bargain
print("\n" + "=" * 80)
print("PHASE TRANSITION: configure -> bargain")
print("=" * 80)

class Message:
    def __init__(self, sender, content):
        self.sender = sender
        self.content = content

# Send __ANNOUNCE_CONFIG__ message
config_msg = Message("Human", "__ANNOUNCE_CONFIG__")
agent1.receive(config_msg)

print(f"Agent1 phase after transition: {agent1.rb_phase}")
print(f"Agent1 rb_active_offers: {len(agent1.rb_active_offers)} offers")

# Now agent1 should send configuration announcement in step()
print("\n" + "=" * 80)
print("AGENT1 STEP 1: Should send configuration announcement")
print("=" * 80)
agent1.step()

print(f"Messages sent: {len(comm_layer.messages)}")
if comm_layer.messages:
    print(f"Last message: {comm_layer.messages[-1]}")

# Simulate human sending an offer
print("\n" + "=" * 80)
print("HUMAN SENDS OFFER")
print("=" * 80)

# Human says: "If a1=blue AND a2=yellow, then h1=red AND h3=green"
human_offer = RBMove(
    move="ConditionalOffer",
    offer_id=f"offer_{int(time.time())}_Human",
    conditions=[
        Condition(node="a1", colour="blue", owner="Agent1"),
        Condition(node="a2", colour="yellow", owner="Agent1"),
    ],
    assignments=[
        Assignment(node="h1", colour="red"),
        Assignment(node="h3", colour="green"),
    ],
    reasons=["human_proposal"]
)

human_msg_text = format_rb(human_offer) + " " + pretty_rb(human_offer)
print(f"Human offer: {pretty_rb(human_offer)}")
print(f"Offer ID: {human_offer.offer_id}")

# Send to agent
human_msg = Message("Human", human_msg_text)
agent1.receive(human_msg)

print(f"\nAgent1 rb_active_offers after receiving human offer: {len(agent1.rb_active_offers)}")
for offer_id in agent1.rb_active_offers.keys():
    print(f"  - {offer_id}")

# Check if agent can find the offer
print(f"\nAgent1 rb_accepted_offers: {agent1.rb_accepted_offers}")
print(f"Agent1 rb_rejected_offers: {agent1.rb_rejected_offers}")

# Now agent should respond
print("\n" + "=" * 80)
print("AGENT1 STEP 2: Should evaluate and respond to human offer")
print("=" * 80)

# Clear messages
comm_layer.messages.clear()

agent1.step()

print(f"\nMessages sent: {len(comm_layer.messages)}")
if comm_layer.messages:
    for sender, recipient, content in comm_layer.messages:
        print(f"\n[Response] {sender} -> {recipient}")
        # Parse and pretty print
        rb_move = parse_rb(content)
        if rb_move:
            print(f"  Move: {rb_move.move}")
            print(f"  Pretty: {pretty_rb(rb_move)}")
        else:
            print(f"  Content: {content[:200]}")

print("\n" + "=" * 80)
print("CHECKING WHAT WENT WRONG")
print("=" * 80)

# Check if offer ID matching works
test_offer_id = f"offer_123_Human"
print(f"\nTest offer ID: {test_offer_id}")
print(f"Check 1 - old method: {test_offer_id.split('_')[-1]} == 'Human': {test_offer_id.split('_')[-1] == 'Human'}")
print(f"Check 2 - new method: '_Human' in '{test_offer_id}': {'_Human' in test_offer_id}")

# Check if our offer would be found
if agent1.rb_active_offers:
    offer_id = list(agent1.rb_active_offers.keys())[0]
    print(f"\nActual offer ID in rb_active_offers: {offer_id}")
    print(f"Would old method find it for recipient='Human'? {offer_id.split('_')[-1] if '_' in offer_id else None} == 'Human': {(offer_id.split('_')[-1] if '_' in offer_id else None) == 'Human'}")
    print(f"Would new method find it for recipient='Human'? '_Human' in '{offer_id}': {'_Human' in offer_id}")

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)
