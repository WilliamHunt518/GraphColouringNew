#!/usr/bin/env python3
"""Test the exact user workflow: reject -> feasibility -> accept -> satisfaction."""

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.communication_layer import PassThroughCommLayer
from agents.base_agent import Message
from comm.rb_protocol import parse_rb
import time

# Create problem matching the actual setup
nodes = ['a1', 'a2', 'a3', 'a4', 'a5', 'h1', 'h2', 'h3', 'h4', 'h5', 'b1', 'b2', 'b3', 'b4', 'b5']
edges = [
    ('a1', 'a2'), ('a2', 'a3'), ('a3', 'a4'), ('a4', 'a5'),
    ('a2', 'h1'), ('a3', 'h2'), ('a4', 'h4'), ('a5', 'h5'),
    ('h1', 'h2'), ('h2', 'h3'), ('h3', 'h4'), ('h4', 'h5'),
    ('h2', 'b2'), ('h5', 'b5'),
    ('b1', 'b2'), ('b2', 'b3'), ('b3', 'b4'), ('b4', 'b5'),
]
domain = ['red', 'green', 'blue']
owners = {
    'a1': 'Agent1', 'a2': 'Agent1', 'a3': 'Agent1', 'a4': 'Agent1', 'a5': 'Agent1',
    'h1': 'Human', 'h2': 'Human', 'h3': 'Human', 'h4': 'Human', 'h5': 'Human',
    'b1': 'Agent2', 'b2': 'Agent2', 'b3': 'Agent2', 'b4': 'Agent2', 'b5': 'Agent2',
}

problem = GraphColoring(nodes, edges, domain)
comm_layer = PassThroughCommLayer()

agent = RuleBasedClusterAgent(
    name='Agent1',
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=['a1', 'a2', 'a3', 'a4', 'a5'],
    owners=owners,
    algorithm='greedy',
    fixed_local_nodes={'a1': 'green'},
)

print("="*80)
print("USER WORKFLOW TEST: reject -> feasibility -> accept -> satisfaction")
print("="*80)

# Human sets colors
human_colors = {'h1': 'red', 'h2': 'blue', 'h3': 'green', 'h4': 'red', 'h5': 'green'}
agent.neighbour_assignments.update(human_colors)

print(f"\n[STEP 1] Human announces colors: {human_colors}")

# Agent announces config
msg = Message(sender='Human', recipient='Agent1', content='__ANNOUNCE_CONFIG__')
agent.receive(msg)
agent.sent_messages = []

print(f"[STEP 2] Agent transitions to bargain phase")
print(f"  Agent phase: {agent.rb_phase}")

# Agent generates initial offer
agent.step()
print(f"\n[STEP 3] Agent generates offer")
print(f"  Agent penalty: {agent._compute_local_penalty():.3f}")
print(f"  Agent sent {len(agent.sent_messages)} messages")

# Find the first conditional offer
first_offer_id = None
for msg in agent.sent_messages:
    rb = parse_rb(msg.content)
    if rb and rb.move == "ConditionalOffer" and rb.offer_id and "offer_" in rb.offer_id:
        first_offer_id = rb.offer_id
        print(f"  Found offer: {first_offer_id}")
        if rb.conditions:
            print(f"    Conditions: {[(c.node, c.colour) for c in rb.conditions]}")
        break

if not first_offer_id:
    print("  No conditional offer sent - agent may already be satisfied or can't find solution")
    print(f"  Agent satisfied: {agent.satisfied}")
    if agent.satisfied:
        print("\nAgent is already satisfied - test complete!")
        exit(0)
    else:
        print("\nAgent can't find penalty=0 solution with these colors")
        exit(1)

# USER REJECTS with impossible condition
print(f"\n[STEP 4] User REJECTS offer marking h4=red as impossible")
reject_msg = f'[rb:{{"move": "Reject", "refers_to": "{first_offer_id}", "impossible_conditions": [{{"node": "h4", "colour": "red"}}]}}]'
agent.receive(Message(sender='Human', recipient='Agent1', content=reject_msg))
agent.sent_messages = []

print(f"  Agent rb_impossible_conditions: {agent.rb_impossible_conditions}")

# USER ASKS FEASIBILITY
print(f"\n[STEP 5] User asks feasibility: 'Is h1=green feasible?'")
query_id = f"query_{int(time.time())}"
feasibility_msg = f'[rb:{{"move": "FeasibilityQuery", "query_id": "{query_id}", "conditions": [{{"node": "h1", "colour": "green", "owner": "Human"}}]}}]'
agent.receive(Message(sender='Human', recipient='Agent1', content=feasibility_msg))
agent.sent_messages = []

# Agent should respond with FeasibilityResponse AND auto-send conditional offer (fix #6)
agent.step()

print(f"\n[STEP 6] Agent responds to feasibility query")
print(f"  Agent sent {len(agent.sent_messages)} messages")

feasibility_response = None
auto_offer_id = None

for msg in agent.sent_messages:
    rb = parse_rb(msg.content)
    if rb:
        if rb.move == "FeasibilityResponse":
            feasibility_response = rb
            print(f"  FeasibilityResponse: is_feasible={rb.is_feasible}")
            if rb.is_feasible and rb.required_assignments:
                print(f"    Required: {[(a.node, a.colour) for a in rb.required_assignments]}")
        elif rb.move == "ConditionalOffer" and rb.offer_id and "offer_" in rb.offer_id:
            auto_offer_id = rb.offer_id
            print(f"  Auto-sent ConditionalOffer: {auto_offer_id}")
            if rb.conditions:
                print(f"    Conditions: {[(c.node, c.colour) for c in rb.conditions]}")
            if rb.assignments:
                print(f"    Assignments: {[(a.node, a.colour) for a in rb.assignments]}")

if not feasibility_response:
    print("  ERROR: No FeasibilityResponse!")
    exit(1)

if not auto_offer_id:
    print("  ERROR: No auto-sent conditional offer (fix #6 not working!)")
    exit(1)

# USER ACCEPTS the auto-sent offer
print(f"\n[STEP 7] User ACCEPTS the auto-sent offer: {auto_offer_id}")
accept_msg = f'[rb:{{"move": "Accept", "refers_to": "{auto_offer_id}"}}]'
agent.receive(Message(sender='Human', recipient='Agent1', content=accept_msg))

print(f"\n[STEP 8] After acceptance:")
print(f"  Agent assignments: {agent.assignments}")
print(f"  Agent penalty: {agent._compute_local_penalty():.3f}")
print(f"  Agent forced_local_assignments: {agent.forced_local_assignments}")
print(f"  Agent rb_proposed_nodes: {agent.rb_proposed_nodes}")
print(f"  Agent satisfied: {agent.satisfied}")

# Agent steps again
agent.sent_messages = []
agent.step()

print(f"\n[STEP 9] After next step:")
print(f"  Agent penalty: {agent._compute_local_penalty():.3f}")
print(f"  Agent satisfied: {agent.satisfied}")
print(f"  Agent sent {len(agent.sent_messages)} messages")

if agent.satisfied:
    print("\n" + "="*80)
    print("SUCCESS! Agent became satisfied after accepting offer!")
    print("="*80)
    exit(0)
else:
    print("\n" + "="*80)
    print("FAILED! Agent not satisfied even after accepting offer")
    print("="*80)
    print("\nDEBUG INFO:")
    print(f"  Boundary nodes: {agent._get_boundary_nodes_for('Human')}")
    print(f"  Proposed nodes: {agent.rb_proposed_nodes.get('Human', {})}")
    print(f"  Current assignments: {agent.assignments}")
    print(f"  Recipients: {agent._get_recipient_clusters()}")
    exit(1)
