#!/usr/bin/env python3
"""Test script to reproduce the b1/b2 clash bug in greedy solver."""

import sys
sys.path.insert(0, ".")

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.communication_layer import PassThroughCommLayer

# Create problem with Agent2's nodes and edges
nodes = ['b1', 'b2', 'b3', 'b4', 'b5', 'h2', 'h5']
edges = [
    ('b1', 'b2'),  # Internal edge
    ('b1', 'b5'),  # Internal edge
    ('b2', 'b3'),  # Internal edge
    ('b2', 'b5'),  # Internal edge
    ('b3', 'b4'),  # Internal edge
    ('b4', 'b5'),  # Internal edge
    ('h2', 'b2'),  # External edge
    ('h5', 'b2'),  # External edge
]
domain = ['red', 'green', 'blue']

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)

# Create Agent2
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
agent = RuleBasedClusterAgent(
    name='Agent2',
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=['b1', 'b2', 'b3', 'b4', 'b5'],
    owners=owners,
    algorithm='maxsum',  # Changed from 'greedy' to 'maxsum' for exhaustive search
    fixed_local_nodes={'b4': 'green'},
)

# Set external neighbor assignments
agent.neighbour_assignments = {'h2': 'blue', 'h5': 'green'}

print("="*70)
print("Testing greedy solver with Agent2's configuration")
print("="*70)
print(f"Fixed nodes: {agent.fixed_local_nodes}")
print(f"Neighbor assignments: {agent.neighbour_assignments}")
print(f"Node order: {agent.nodes}")
print()

# Run compute_assignments
print("Running compute_assignments()...")
print()
assignment = agent.compute_assignments()

print()
print("="*70)
print("RESULT:")
print("="*70)
print(f"Assignment: {assignment}")
print()

# Check for conflicts
conflicts = []
for u, v in problem.edges:
    if u in assignment and v in assignment:
        if assignment[u] == assignment[v]:
            conflicts.append((u, v, assignment[u]))

if conflicts:
    print("CONFLICTS FOUND:")
    for u, v, color in conflicts:
        print(f"  - {u}={color} CLASHES with {v}={color}")
else:
    print("No conflicts found")

# Calculate penalty
penalty = problem.evaluate_assignment(assignment)
print(f"\nTotal penalty: {penalty}")

# Print debug logs
print()
print("="*70)
print("GREEDY SOLVER DEBUG LOGS:")
print("="*70)
for log_line in agent.logs:
    if "GREEDY DEBUG" in log_line:
        print(log_line)
