#!/usr/bin/env python3
"""Test that agents now default to maxsum (exhaustive search)."""

import sys
sys.path.insert(0, ".")

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.communication_layer import PassThroughCommLayer

# Create problem with Agent2's nodes and edges (same as original bug)
nodes = ['b1', 'b2', 'b3', 'b4', 'b5', 'h2', 'h5']
edges = [
    ('b1', 'b2'),
    ('b1', 'b5'),
    ('b2', 'b3'),
    ('b2', 'b5'),
    ('b3', 'b4'),
    ('b4', 'b5'),
    ('h2', 'b2'),
    ('h5', 'b2'),
]
domain = ['red', 'green', 'blue']

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)

owners = {
    'b1': 'Agent2',
    'b2': 'Agent2',
    'b3': 'Agent2',
    'b4': 'Agent2',
    'b5': 'Agent2',
    'h2': 'Human',
    'h5': 'Human',
}

comm_layer = PassThroughCommLayer()

# Create agent WITHOUT specifying algorithm - should default to maxsum
agent = RuleBasedClusterAgent(
    name='Agent2',
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=['b1', 'b2', 'b3', 'b4', 'b5'],
    owners=owners,
    # algorithm parameter omitted - should default to maxsum now
    fixed_local_nodes={'b4': 'green'},
)

# Set external neighbor assignments (the problematic case)
agent.neighbour_assignments = {'h2': 'blue', 'h5': 'green'}

print("="*70)
print("Testing DEFAULT algorithm (should be maxsum)")
print("="*70)
print(f"Agent algorithm: {agent.algorithm}")
print(f"Fixed nodes: {agent.fixed_local_nodes}")
print(f"Neighbor assignments: {agent.neighbour_assignments}")
print()

# Run compute_assignments
assignment = agent.compute_assignments()

print("Assignment:", assignment)
print()

# Check for conflicts
conflicts = []
for u, v in problem.edges:
    if u in assignment and v in assignment:
        if assignment[u] == assignment[v]:
            conflicts.append((u, v, assignment[u]))

# Calculate penalty
penalty = problem.evaluate_assignment(assignment)

print("="*70)
print("RESULTS:")
print("="*70)
if conflicts:
    print("CONFLICTS FOUND:")
    for u, v, color in conflicts:
        print(f"  - {u}={color} CLASHES with {v}={color}")
    print()
    print(f"Total penalty: {penalty}")
    print()
    print("FAIL: Algorithm should find conflict-free solution!")
    sys.exit(1)
else:
    print("No conflicts found")
    print(f"Total penalty: {penalty}")
    print()
    if penalty == 0:
        print("SUCCESS: Default algorithm now uses exhaustive search!")
        sys.exit(0)
    else:
        print("WARNING: No conflicts but penalty > 0")
        sys.exit(1)
