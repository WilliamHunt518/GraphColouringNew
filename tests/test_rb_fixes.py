#!/usr/bin/env python3
"""Test script to verify RB fixes are working."""

import sys
from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.passthrough_comm_layer import PassThroughCommLayer

# Create a simple test graph
nodes = ['a1', 'a2', 'h1', 'h2']
edges = [('a1', 'a2'), ('a1', 'h1'), ('a2', 'h2')]
domain = ['red', 'green', 'blue']
owners = {'a1': 'Agent1', 'a2': 'Agent1', 'h1': 'Human', 'h2': 'Human'}

problem = GraphColoring(nodes, edges, domain)
comm_layer = PassThroughCommLayer()

# Create agent
agent = RuleBasedClusterAgent(
    name='Agent1',
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=['a1', 'a2'],
    owners=owners,
    algorithm='maxsum',
    initial_assignments={'a1': 'red', 'a2': 'green'},
)

print("Testing conditional offer generation...")
print(f"Agent boundary nodes: {[n for n in agent.nodes if any(problem.get_neighbors(n, node) for node in problem.get_nodes() if owners.get(node) != 'Agent1')]}")

# Set initial neighbor state
agent.neighbour_assignments = {'h1': 'red', 'h2': 'green'}

# Try to generate a conditional offer
print("\nGenerating conditional offer...")
try:
    offer = agent._generate_conditional_offer('Human')
    if offer:
        print(f"✓ Generated offer successfully")
        print(f"  Conditions: {offer.conditions if hasattr(offer, 'conditions') else 'None'}")
        print(f"  Assignments: {offer.assignments if hasattr(offer, 'assignments') else 'None'}")
        print(f"  Reasons: {offer.reasons if hasattr(offer, 'reasons') else 'None'}")
    else:
        print(f"✗ No offer generated (returned None)")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\nTest complete!")
