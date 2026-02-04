#!/usr/bin/env python3
"""Test that agents become satisfied after accepting offers."""

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.communication_layer import PassThroughCommLayer
from agents.base_agent import Message
from comm.rb_protocol import parse_rb

# Create simple problem
nodes = ['a1', 'a2', 'h1', 'h2']
edges = [('a1', 'a2'), ('a1', 'h1'), ('a2', 'h2')]
domain = ['red', 'green', 'blue']
owners = {'a1': 'Agent1', 'a2': 'Agent1', 'h1': 'Human', 'h2': 'Human'}

problem = GraphColoring(nodes, edges, domain)
comm_layer = PassThroughCommLayer()

agent = RuleBasedClusterAgent(
    name='Agent1',
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=['a1', 'a2'],
    owners=owners,
    algorithm='greedy',
)

print("=" * 80)
print("TEST: Agent Satisfaction After Accept")
print("=" * 80)

# Set up scenario where agent has conflict
agent.neighbour_assignments = {'h1': 'red', 'h2': 'blue'}
agent.assignments = {'a1': 'red', 'a2': 'blue'}  # a1=red conflicts with h1=red

print(f"\n[1] Initial state:")
print(f"  Agent assignments: {agent.assignments}")
print(f"  Agent penalty: {agent._compute_local_penalty():.3f}")
print(f"  Agent satisfied: {agent.satisfied}")

# Transition to bargain phase
msg = Message(sender='Human', recipient='Agent1', content='__ANNOUNCE_CONFIG__')
agent.receive(msg)
print(f"\n[2] After __ANNOUNCE_CONFIG__:")
print(f"  Agent phase: {agent.rb_phase}")

# Step to generate offer
agent.sent_messages = []
agent.step()

print(f"\n[3] After step():")
print(f"  Agent sent {len(agent.sent_messages)} messages")
print(f"  Agent penalty: {agent._compute_local_penalty():.3f}")
print(f"  Agent satisfied: {agent.satisfied}")

# Check for conditional offer
offer_id = None
for msg in agent.sent_messages:
    rb_move = parse_rb(msg.content)
    if rb_move and rb_move.move == "ConditionalOffer" and rb_move.offer_id:
        if rb_move.offer_id.startswith("offer_"):
            offer_id = rb_move.offer_id
            print(f"\n[4] Found conditional offer: {offer_id}")
            if rb_move.conditions:
                print(f"  Conditions: {[(c.node, c.colour) for c in rb_move.conditions]}")
            if rb_move.assignments:
                print(f"  Assignments: {[(a.node, a.colour) for a in rb_move.assignments]}")
            break

if not offer_id:
    print("\n[ERROR] Agent didn't send a conditional offer!")
    exit(1)

# Human accepts the offer
accept_msg_text = f'[rb:{{"move": "Accept", "refers_to": "{offer_id}"}}]'
accept_msg = Message(sender='Human', recipient='Agent1', content=accept_msg_text)

print(f"\n[5] Human accepts offer: {offer_id}")
agent.receive(accept_msg)

print(f"\n[6] After acceptance:")
print(f"  Agent assignments: {agent.assignments}")
print(f"  Agent penalty: {agent._compute_local_penalty():.3f}")
print(f"  Agent forced_local_assignments: {agent.forced_local_assignments}")
print(f"  Agent rb_proposed_nodes: {agent.rb_proposed_nodes}")
print(f"  Agent satisfied: {agent.satisfied}")

# Step again to check satisfaction
agent.step()

print(f"\n[7] After step():")
print(f"  Agent penalty: {agent._compute_local_penalty():.3f}")
print(f"  Agent satisfied: {agent.satisfied}")

if agent.satisfied:
    print("\n✓ SUCCESS: Agent became satisfied after accepting offer!")
    print("=" * 80)
    exit(0)
else:
    print("\n✗ FAILED: Agent not satisfied even though offer was accepted!")
    print("=" * 80)
    exit(1)
