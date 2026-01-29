"""Debug test - trace through agent step() logic."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.rb_protocol import parse_rb, format_rb, pretty_rb, RBMove, Condition, Assignment
import time

# Monkey-patch the agent to add more logging
original_generate_rb_move = RuleBasedClusterAgent._generate_rb_move

def debug_generate_rb_move(self, recipient, changes):
    print(f"\n[DEBUG] _generate_rb_move called:")
    print(f"  recipient: {recipient}")
    print(f"  changes: {changes}")
    print(f"  rb_phase: {self.rb_phase}")
    print(f"  rb_active_offers: {list(self.rb_active_offers.keys())}")
    print(f"  rb_accepted_offers: {self.rb_accepted_offers}")
    print(f"  rb_rejected_offers: {self.rb_rejected_offers}")

    # Check for pending offers
    pending_offers_from_recipient = [
        (offer_id, offer) for offer_id, offer in self.rb_active_offers.items()
        if offer_id not in self.rb_accepted_offers
        and offer_id not in self.rb_rejected_offers
        and f"_{recipient}" in offer_id
    ]
    print(f"  pending_offers_from_recipient: {[oid for oid, _ in pending_offers_from_recipient]}")

    result = original_generate_rb_move(self, recipient, changes)

    print(f"  -> Returned move: {result.move if result else None}")
    if result:
        print(f"     Pretty: {pretty_rb(result)}")

    return result

RuleBasedClusterAgent._generate_rb_move = debug_generate_rb_move

# Now run the test
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

owners = {
    "h1": "Human", "h2": "Human", "h3": "Human",
    "a1": "Agent1", "a2": "Agent1",
}

class DummyCommLayer:
    def __init__(self):
        self.messages = []

    def send(self, sender, recipient, content):
        self.messages.append((sender, recipient, content))

    def render_outbound(self, sender, content, assignments=None):
        return content

    def parse_content(self, sender, recipient, content):
        return {"raw": content}

comm_layer = DummyCommLayer()

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
print("SETUP COMPLETE")
print("=" * 80)

# Phase transition
class Message:
    def __init__(self, sender, content):
        self.sender = sender
        self.content = content

config_msg = Message("Human", "__ANNOUNCE_CONFIG__")
agent1.receive(config_msg)

print(f"\nAfter __ANNOUNCE_CONFIG__:")
print(f"  rb_phase: {agent1.rb_phase}")
print(f"  rb_active_offers: {list(agent1.rb_active_offers.keys())}")

# Human sends offer
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
human_msg = Message("Human", human_msg_text)
agent1.receive(human_msg)

print(f"\nAfter receiving human offer:")
print(f"  rb_active_offers: {list(agent1.rb_active_offers.keys())}")
print(f"  rb_awaiting_response: {agent1.rb_awaiting_response}")

# Agent step
print("\n" + "=" * 80)
print("AGENT STEP")
print("=" * 80)

agent1.step()

print(f"\nAfter step():")
print(f"  Messages sent: {len(comm_layer.messages)}")
print(f"  rb_awaiting_response: {agent1.rb_awaiting_response}")
