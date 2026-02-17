"""
Direct test: Does the API actually consider neighbor constraints?

Test scenario:
- Agent controls: a1, a2
- Agent knows neighbor: h1
- Edge: (a2, h1)
- Set h1=red
- Ask agent for best response
- Agent should NOT return a2=red (would conflict with h1)
"""

from agents.cluster_agent import ClusterAgent
from agents.cluster_agent_api import ClusterAgentAPI
from problems.graph_coloring import GraphColoring

# Create problem
nodes = ["a1", "a2", "h1"]
edges = [("a1", "a2"), ("a2", "h1")]  # a2 connects to BOTH a1 AND h1
domain = ["red", "blue", "green"]

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)
owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}

class DummyComm:
    def format_content(self, sender, recipient, content):
        return str(content)

# Create agent
agent = ClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=DummyComm(),
    local_nodes=["a1", "a2"],
    owners=owners,
    algorithm="maxsum"
)

# Set neighbor assignment: h1=red
agent.neighbour_assignments = {"h1": "red"}

print("="*70)
print("TEST: Does API Consider Neighbor Constraints?")
print("="*70)
print("\nSetup:")
print(f"  Agent controls: a1, a2")
print(f"  Neighbor: h1=red")
print(f"  Edges: (a1, a2), (a2, h1)")
print(f"  CRITICAL: a2 connects to h1!")

# Create API
api = ClusterAgentAPI(agent)

# Test 1: Get best response with h1=red
print("\n--- Test 1: get_best_response_to(h1=red) ---")
result = api.get_best_response_to({"h1": "red"})
print(f"Result: {result}")
print(f"Penalty: {result.get('penalty')}")

# Check if agent proposed a2=red (BAD!)
if result.get("a2") == "red":
    print("\n[FAIL] Agent proposed a2=red when h1=red!")
    print("This creates a CONFLICT on edge (a2, h1)")
    print("\nAPI IS NOT CONSIDERING NEIGHBOR CONSTRAINTS!")
else:
    print(f"\n[OK] Agent proposed a2={result.get('a2')} (not red, good!)")

# Test 2: Manually verify penalty calculation
print("\n--- Test 2: Verify penalty calculation ---")
test_config = {"a1": "blue", "a2": "red", "h1": "red"}
penalty = problem.evaluate_assignment(test_config)
print(f"Manual test: a1=blue, a2=red, h1=red")
print(f"  Penalty: {penalty}")
print(f"  Expected: > 0 (conflict on a2-h1 edge)")

if penalty > 0:
    print("[OK] Penalty calculation correctly detects conflict")
else:
    print("[FAIL] Penalty calculation MISSING conflict!")

# Test 3: Check current penalty
print("\n--- Test 3: get_current_penalty() ---")
agent.assignments = {"a1": "blue", "a2": "red"}
penalty, conflicts = api.get_current_penalty()
print(f"Agent: a1=blue, a2=red")
print(f"Neighbor: h1=red")
print(f"Penalty: {penalty}")
print(f"Conflicts: {conflicts}")

if ("a2", "h1") in conflicts or ("h1", "a2") in conflicts:
    print("[OK] Conflict detected on (a2, h1) edge")
else:
    print("[FAIL] Conflict NOT detected!")
    print(f"  Edges in problem: {list(problem.edges)}")
    print(f"  Combined assignment: {dict(agent.neighbour_assignments) | agent.assignments}")

print("\n" + "="*70)
print("TEST COMPLETE")
print("="*70)
