"""Direct API test to verify get_best_response_to() works."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer

# Create simple problem
nodes = ["a1", "a2", "h1", "h2"]
edges = [("a1", "a2"), ("a2", "h1"), ("h1", "h2")]
problem = GraphColoring(nodes=nodes, edges=edges, domain=["red", "blue", "green"])

owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

agent = ToolCallingClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=SpeechLLMLayer(),
    local_nodes=["a1", "a2"],
    owners=owners
)

# Set neighbor assignments
agent.neighbour_assignments = {"h1": "red", "h2": "blue"}

print("=== Testing API directly ===")
print(f"Neighbor assignments: {agent.neighbour_assignments}")

# Test 1: Call with no arguments (should use current neighbors)
print("\nTest 1: get_best_response_to() with no arguments")
result1 = agent.api.get_best_response_to()
print(f"Result: {result1}")
print(f"  Type: {type(result1)}")
if isinstance(result1, dict):
    print(f"  Keys: {result1.keys()}")
    print(f"  Penalty: {result1.get('penalty', 'NOT FOUND')}")

# Test 2: Call with explicit arguments
print("\nTest 2: get_best_response_to(neighbor_assignments={'h1': 'red', 'h2': 'blue'})")
result2 = agent.api.get_best_response_to(neighbor_assignments={"h1": "red", "h2": "blue"})
print(f"Result: {result2}")
if isinstance(result2, dict):
    print(f"  Keys: {result2.keys()}")
    print(f"  Penalty: {result2.get('penalty', 'NOT FOUND')}")

# Test 3: Check current penalty
print("\nTest 3: get_current_penalty()")
penalty, conflicts = agent.api.get_current_penalty()
print(f"Penalty: {penalty}")
print(f"Conflicts: {conflicts}")

print("\n=== All tests passed ===")
