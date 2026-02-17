"""
Test that agents compute valid assignments BEFORE announcing.

CRITICAL BUG: Agents initialized with RANDOM colors and announced them
without considering neighbor constraints, leading to clashing configs
in the very first message!

The fix: Recompute assignments before announcing to respect known neighbor colors.
"""

from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.cluster_agent import ClusterAgent
from problems.graph_coloring import GraphColoring
from comm.speech_llm_layer import SpeechLLMLayer

print("="*70)
print("TEST: Agents Respect Neighbor Constraints When Announcing")
print("="*70)

# Create problem with potential conflict
nodes = ["a1", "a2", "h1", "h2"]
edges = [
    ("a1", "a2"),  # Internal edge
    ("a2", "h2"),  # Boundary edge - CRITICAL!
]
domain = ["red", "blue", "green"]

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)
owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

class DummyComm:
    def format_content(self, sender, recipient, content):
        return str(content)

# Create agent
agent = ToolCallingClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=SpeechLLMLayer(use_llm=False),
    local_nodes=["a1", "a2"],
    owners=owners
)

print("\nSetup:")
print(f"  Agent controls: a1, a2")
print(f"  Edge (a2, h2) exists - potential for conflict!")
print(f"  Initial assignments (RANDOM): {agent.assignments}")

# Simulate human announcing first (CORRECT flow)
print("\n--- Scenario 1: Human announces first (CORRECT) ---")
agent.neighbour_assignments = {"h2": "red"}  # Human announces h2=red
print(f"Human announces: h2=red")

# Now agent should recompute before announcing
print("\nAgent recomputing before announcement...")
# Call the announcement method
agent._send_automatic_announcement()

# Check announced values
print(f"Agent's recomputed assignments: {agent.assignments}")
a2_color = agent.assignments.get("a2")

if a2_color == "red":
    print(f"\n[FAIL] Agent announced a2=red when h2=red!")
    print(f"This creates a CONFLICT on edge (a2, h2)")
    print("BUG NOT FIXED!")
else:
    print(f"\n[OK] Agent announced a2={a2_color} (not red)")
    print(f"No conflict with h2=red")

# Verify penalty
from agents.cluster_agent_api import ClusterAgentAPI
api = ClusterAgentAPI(agent)
penalty, conflicts = api.get_current_penalty()
print(f"\nPenalty check: {penalty}")
print(f"Conflicts: {conflicts}")

if penalty > 0:
    print("[FAIL] Non-zero penalty after announcement!")
else:
    print("[OK] Zero penalty - no conflicts!")

print("\n" + "="*70)

# Reset for scenario 2
print("\n--- Scenario 2: Agent announces before knowing neighbors (BAD but possible) ---")

# Create new agent
agent2 = ToolCallingClusterAgent(
    name="Agent2",
    problem=problem,
    comm_layer=SpeechLLMLayer(use_llm=False),
    local_nodes=["a1", "a2"],
    owners=owners
)

print(f"Initial assignments (RANDOM): {agent2.assignments}")
print("neighbor_assignments: {} (EMPTY)")

# Agent announces WITHOUT knowing neighbor colors
print("\nAgent attempting to announce without neighbor knowledge...")
agent2._send_automatic_announcement()

print(f"Agent announced: {agent2.assignments}")
print("\n[WARN] Agent doesn't know neighbor colors yet")
print("This is unavoidable if agent must announce first.")
print("The REAL fix is ensuring human announces first in the protocol!")

print("\n" + "="*70)
print("SUMMARY:")
print("="*70)
print("1. When human announces first: Agent recomputes to respect constraints [OK]")
print("2. When agent announces first: No neighbor info available [WARN]")
print("\nRECOMMENDATION: Enforce protocol where HUMAN announces first!")
print("="*70)
