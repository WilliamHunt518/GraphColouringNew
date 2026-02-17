"""Test boundary node detection in conditional offer generation."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from problems.graph_coloring import GraphColoring
from comm.communication_layer import PassThroughCommLayer

# Create simple 3-cluster problem
nodes = ['a1', 'a2', 'h1', 'h2', 'b1', 'b2']
edges = [
    ('a1', 'a2'),  # Internal to Agent1
    ('a2', 'h1'),  # Agent1-Human boundary
    ('h1', 'h2'),  # Internal to Human
    ('h2', 'b1'),  # Human-Agent2 boundary
    ('b1', 'b2'),  # Internal to Agent2
]
domain = ['red', 'green', 'blue']
owners = {
    'a1': 'Agent1',
    'a2': 'Agent1',
    'h1': 'Human',
    'h2': 'Human',
    'b1': 'Agent2',
    'b2': 'Agent2',
}

problem = GraphColoring(nodes, edges, domain)
comm = PassThroughCommLayer()

# Create Agent1
agent1 = RuleBasedClusterAgent(
    name='Agent1',
    problem=problem,
    comm_layer=comm,
    local_nodes=['a1', 'a2'],
    owners=owners,
    algorithm='greedy'
)

# Set initial assignments
agent1.assignments = {'a1': 'red', 'a2': 'blue'}
agent1.neighbour_assignments = {'h1': 'blue'}  # Conflict!

print("=" * 70)
print("Test: Boundary Detection in Conditional Offer Generation")
print("=" * 70)
print(f"Agent1 controls: {agent1.nodes}")
print(f"Owners: {agent1.owners}")
print(f"Neighbor assignments: {agent1.neighbour_assignments}")
print(f"Agent1's assignments: {agent1.assignments}")
print()

# Try to generate conditional offer to Human
print("Generating conditional offer from Agent1 to Human...")
print()

offer = agent1._generate_conditional_offer('Human')

if offer:
    print(f"Generated offer: {offer}")
    print(f"Conditions: {offer.conditions}")
    print(f"Assignments: {offer.assignments}")
    print()

    # Check for bugs
    errors = []
    for cond in offer.conditions:
        if cond.node.startswith('a'):
            errors.append(f"ERROR: Condition contains Agent1's node: {cond.node}")
    for assign in offer.assignments:
        if assign.node.startswith('h'):
            errors.append(f"ERROR: Assignment contains Human's node: {assign.node}")

    if errors:
        print("BUGS DETECTED:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("SUCCESS: Offer has correct node ownership")
else:
    print("No offer generated")

print("=" * 70)
