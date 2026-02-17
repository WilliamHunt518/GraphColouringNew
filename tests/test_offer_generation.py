#!/usr/bin/env python3
"""Test that conditional offer generation now uses maxsum for ALL nodes."""

import sys
sys.path.insert(0, ".")

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.communication_layer import PassThroughCommLayer

# Create problem matching the user's scenario
nodes = ['a1', 'a2', 'a3', 'a4', 'a5', 'b1', 'b2', 'b3', 'b4', 'b5', 'h1', 'h2', 'h3', 'h4', 'h5']
edges = [
    # Agent1 internal
    ('a1', 'a2'), ('a1', 'a5'), ('a2', 'a3'), ('a2', 'a5'), ('a3', 'a4'), ('a4', 'a5'),
    # Agent2 internal
    ('b1', 'b2'), ('b1', 'b5'), ('b2', 'b3'), ('b2', 'b5'), ('b3', 'b4'), ('b4', 'b5'),
    # Human internal
    ('h1', 'h2'), ('h1', 'h5'), ('h2', 'h3'), ('h2', 'h5'), ('h3', 'h4'), ('h4', 'h5'),
    # Cross-cluster
    ('h1', 'a2'), ('h4', 'a4'), ('h4', 'a5'),
    ('h2', 'b2'), ('h5', 'b2'),
]
domain = ['red', 'green', 'blue']

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)

owners = {
    'a1': 'Agent1', 'a2': 'Agent1', 'a3': 'Agent1', 'a4': 'Agent1', 'a5': 'Agent1',
    'b1': 'Agent2', 'b2': 'Agent2', 'b3': 'Agent2', 'b4': 'Agent2', 'b5': 'Agent2',
    'h1': 'Human', 'h2': 'Human', 'h3': 'Human', 'h4': 'Human', 'h5': 'Human',
}

comm_layer = PassThroughCommLayer()

# Create Agent2 with the problematic initial state
agent = RuleBasedClusterAgent(
    name='Agent2',
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=['b1', 'b2', 'b3', 'b4', 'b5'],
    owners=owners,
    fixed_local_nodes={'b4': 'green'},
)

# Set initial neighbor assignments (Human's initial state)
agent.neighbour_assignments = {'h2': 'blue', 'h5': 'green'}

print("="*70)
print("Testing Conditional Offer Generation")
print("="*70)
print(f"Agent2 algorithm: {agent.algorithm}")
print(f"Fixed nodes: {agent.fixed_local_nodes}")
print(f"Initial neighbor assignments: {agent.neighbour_assignments}")
print()

# Generate a conditional offer
print("Generating conditional offer...")
print()

offer = agent._generate_conditional_offer('Human')

print()
print("="*70)
print("OFFER RESULT:")
print("="*70)

if offer is None:
    print("No offer generated")
    sys.exit(1)

print(f"Offer ID: {offer.offer_id}")
print(f"Conditions (what Human should do):")
for cond in offer.conditions:
    print(f"  - {cond.node} = {cond.colour}")

print(f"Assignments (what Agent2 will do):")
for assign in offer.assignments:
    print(f"  - {assign.node} = {assign.colour}")

print()

# Now simulate accepting the offer to verify it's conflict-free
print("Simulating offer acceptance...")

# Apply the conditions
test_neighbors = dict(agent.neighbour_assignments)
for cond in offer.conditions:
    test_neighbors[cond.node] = cond.colour

# Apply the assignments
test_agent_state = dict(agent.assignments)
for assign in offer.assignments:
    test_agent_state[assign.node] = assign.colour

# Set up agent state
agent.neighbour_assignments = test_neighbors

# Compute optimal assignment with maxsum
optimal_assignment = agent.compute_assignments()

# Check for conflicts
combined = {**test_neighbors, **optimal_assignment}
conflicts = []
for u, v in problem.edges:
    if u in combined and v in combined:
        if combined[u] == combined[v]:
            conflicts.append((u, v, combined[u]))

penalty = problem.evaluate_assignment(combined)

print()
print("="*70)
print("VERIFICATION:")
print("="*70)
print(f"Optimal assignment: {optimal_assignment}")
print(f"Combined state: {combined}")
print()

if conflicts:
    print("FAIL: OFFER CREATES CONFLICTS!")
    for u, v, color in conflicts:
        print(f"  - {u}={color} CLASHES with {v}={color}")
    print(f"Penalty: {penalty}")
    sys.exit(1)
else:
    print("SUCCESS: Offer is conflict-free!")
    print(f"Penalty: {penalty}")
    sys.exit(0)
