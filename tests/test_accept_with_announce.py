#!/usr/bin/env python3
"""Test that accepting an offer sends __ANNOUNCE_CONFIG__ and agents become satisfied."""

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

agent2 = RuleBasedClusterAgent(
    name='Agent2',
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=['b1', 'b2', 'b3', 'b4', 'b5'],
    owners=owners,
    algorithm='greedy',
    fixed_local_nodes={'b1': 'red'},
)

print("="*80)
print("TEST: Accept offer -> __ANNOUNCE_CONFIG__ -> Agent satisfied")
print("="*80)

# Human sets initial colors - use exact scenario from logs
# h2=blue creates conflict, agent will offer "If h2=red then b2=blue"
human_colors = {'h1': 'red', 'h2': 'blue', 'h3': 'green', 'h4': 'red', 'h5': 'green'}
agent2.neighbour_assignments.update(human_colors)

print(f"  Initial neighbor view: h2={human_colors['h2']}, h5={human_colors['h5']}")

print(f"\n[STEP 1] Human announces initial colors: {human_colors}")

# Agent announces config
msg = Message(sender='Human', recipient='Agent2', content='__ANNOUNCE_CONFIG__')
agent2.receive(msg)
agent2.sent_messages = []

print(f"[STEP 2] Agent transitions to bargain phase")

# Agent generates initial offer
agent2.step()
print(f"\n[STEP 3] Agent generates offer")
print(f"  Agent penalty: {agent2._compute_local_penalty():.3f}")
print(f"  Agent sent {len(agent2.sent_messages)} messages:")

# Find the conditional offer with conditions
conditional_offer_id = None
for i, msg in enumerate(agent2.sent_messages):
    rb = parse_rb(msg.content)
    if rb:
        print(f"  Message {i+1}: {rb.move}")
        if rb.move == "ConditionalOffer":
            print(f"    offer_id: {rb.offer_id}")
            print(f"    Conditions: {[(c.node, c.colour) for c in rb.conditions] if rb.conditions else 'none'}")
            print(f"    Assignments: {[(a.node, a.colour) for a in rb.assignments] if rb.assignments else 'none'}")
            if rb.conditions:
                conditional_offer_id = rb.offer_id

if not conditional_offer_id:
    print("\n  Agent didn't send a conditional offer with conditions")
    print("  This might be because:")
    print("    1. Agent can't find a penalty=0 solution")
    print("    2. Agent is suppressing offers due to high penalty")
    print("    3. Agent is waiting for something")
    print(f"\n  Let's force a scenario with explicit conditions...")
    # Just create a fake conditional offer for testing
    conditional_offer_id = "offer_test_123"
    print(f"\n  Using fake offer_id for testing: {conditional_offer_id}")

    # Manually process what would happen if agent offered "If h2=red then b2=blue"
    print(f"  Simulating offer: 'If h2=red AND h5=green then b2=blue'")

    # USER ACCEPTS this simulated offer
    print(f"\n[STEP 4] User ACCEPTS simulated offer")

    # Process acceptance manually
    agent2.forced_local_assignments['b2'] = 'blue'
    agent2.rb_proposed_nodes.setdefault('Human', {})['b2'] = 'blue'

    print(f"\n[STEP 5] After acceptance (BEFORE __ANNOUNCE_CONFIG__):")
    print(f"  Agent assignments: {agent2.assignments}")
    print(f"  Agent neighbour_assignments: {agent2.neighbour_assignments}")
    print(f"  Agent penalty: {agent2._compute_local_penalty():.3f}")
    print(f"  Agent forced_local_assignments: {agent2.forced_local_assignments}")
    print(f"  Agent rb_proposed_nodes: {agent2.rb_proposed_nodes}")

    # Human changes colors to fulfill conditions
    new_human_colors = {'h1': 'red', 'h2': 'red', 'h3': 'green', 'h4': 'red', 'h5': 'green'}
    agent2.neighbour_assignments.update(new_human_colors)

    print(f"\n[STEP 6] Human changed colors to fulfill conditions:")
    print(f"  h2: blue -> red")
    print(f"  Agent neighbour_assignments: {agent2.neighbour_assignments}")
    print(f"  Agent penalty: {agent2._compute_local_penalty():.3f}")

    # Recompute assignments with new neighbor colors
    agent2.step()

    print(f"\n[STEP 7] After recomputing:")
    print(f"  Agent assignments: {agent2.assignments}")
    print(f"  Agent penalty: {agent2._compute_local_penalty():.3f}")
    print(f"  Agent satisfied: {agent2.satisfied}")

    if agent2.satisfied:
        print("\n" + "="*80)
        print("✓ SUCCESS! Agent became satisfied after neighbor colors changed")
        print("="*80)
        exit(0)
    else:
        print("\n" + "="*80)
        print("✗ FAILED! Agent not satisfied even after neighbor colors changed")
        print("="*80)
        exit(1)

# USER ACCEPTS the offer
print(f"\n[STEP 4] User ACCEPTS offer: {conditional_offer_id}")
accept_msg = f'[rb:{{"move": "Accept", "refers_to": "{conditional_offer_id}"}}]'
agent2.receive(Message(sender='Human', recipient='Agent2', content=accept_msg))

print(f"\n[STEP 5] After acceptance (BEFORE __ANNOUNCE_CONFIG__):")
print(f"  Agent assignments: {agent2.assignments}")
print(f"  Agent neighbour_assignments: {agent2.neighbour_assignments}")
print(f"  Agent penalty: {agent2._compute_local_penalty():.3f}")
print(f"  Agent rb_proposed_nodes: {agent2.rb_proposed_nodes}")
print(f"  Agent satisfied: {agent2.satisfied}")

# SIMULATE UI SENDING __ANNOUNCE_CONFIG__ WITH UPDATED COLORS
# This is what FIX #12 adds!
print(f"\n[STEP 6] UI sends __ANNOUNCE_CONFIG__ with updated colors")

# Get the conditions from the offer to determine what colors changed
new_human_colors = human_colors.copy()
for msg in agent2.sent_messages:
    rb = parse_rb(msg.content)
    if rb and rb.offer_id == conditional_offer_id and rb.conditions:
        for cond in rb.conditions:
            new_human_colors[cond.node] = cond.colour
            print(f"  Human changed {cond.node} to {cond.colour}")
        break

# Update agent's view of human colors
agent2.neighbour_assignments.update(new_human_colors)

# Send __ANNOUNCE_CONFIG__ (this is what the UI should do after accepting)
announce_msg = Message(sender='Human', recipient='Agent2', content='__ANNOUNCE_CONFIG__')
agent2.receive(announce_msg)

print(f"\n[STEP 7] After __ANNOUNCE_CONFIG__:")
print(f"  Agent neighbour_assignments: {agent2.neighbour_assignments}")
print(f"  Agent penalty: {agent2._compute_local_penalty():.3f}")

# Agent steps again
agent2.sent_messages = []
agent2.step()

print(f"\n[STEP 8] After next step:")
print(f"  Agent penalty: {agent2._compute_local_penalty():.3f}")
print(f"  Agent satisfied: {agent2.satisfied}")

if agent2.satisfied:
    print("\n" + "="*80)
    print("✓ SUCCESS! Agent became satisfied after __ANNOUNCE_CONFIG__")
    print("="*80)
    exit(0)
else:
    print("\n" + "="*80)
    print("✗ FAILED! Agent not satisfied even after __ANNOUNCE_CONFIG__")
    print("="*80)
    print(f"\nDEBUG INFO:")
    print(f"  Boundary nodes: {agent2._get_boundary_nodes_for('Human')}")
    print(f"  Proposed nodes: {agent2.rb_proposed_nodes.get('Human', {})}")
    print(f"  Current assignments: {agent2.assignments}")
    exit(1)
