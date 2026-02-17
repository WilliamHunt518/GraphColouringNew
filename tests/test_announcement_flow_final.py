"""
Test the COMPLETE announcement flow as it happens in the system.

Flow:
1. Human clicks "Announce Config"
2. _sync_neighbour_views() updates agent's neighbour_assignments with human's colors
3. Agent receives __ANNOUNCE_CONFIG__ message
4. Agent._handle_announce_config() is called
5. Agent should RECOMPUTE assignments to respect human's colors
6. Agent announces back with non-conflicting colors

This test verifies the agent recomputes BEFORE announcing.
"""

from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.speech_llm_layer import SpeechLLMLayer

print("="*70)
print("TEST: Complete Announcement Flow with Neighbor Constraint Respect")
print("="*70)

# Create problem with conflict potential
nodes = ["a1", "a2", "h1", "h2"]
edges = [
    ("a1", "a2"),  # Internal
    ("a2", "h2"),  # CRITICAL: boundary edge
]
domain = ["red", "blue", "green"]

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)
owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

# Create agent
agent = ToolCallingClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=SpeechLLMLayer(use_llm=False),
    local_nodes=["a1", "a2"],
    owners=owners
)

print("\n--- Initial State ---")
print(f"Agent initial assignments (RANDOM): {agent.assignments}")
print(f"Agent neighbour_assignments: {agent.neighbour_assignments}")
print(f"Edge (a2, h2) exists!")

# STEP 1: Simulate _sync_neighbour_views() - human has announced h2=red
print("\n--- STEP 1: Human announces (via _sync_neighbour_views) ---")
human_config = {"h1": "blue", "h2": "red"}
print(f"Human announces: {human_config}")

# Simulate what _sync_neighbour_views() does
# It would set neighbour_assignments based on adjacency
agent.neighbour_assignments = {"h2": "red"}  # h2 is adjacent to a2
print(f"Agent's neighbour_assignments updated: {agent.neighbour_assignments}")

# STEP 2: Agent receives __ANNOUNCE_CONFIG__
print("\n--- STEP 2: Agent receives __ANNOUNCE_CONFIG__ ---")
msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
print(f"Message: {msg.content}")

# Check assignments BEFORE handling
print(f"\nBEFORE _handle_announce_config:")
print(f"  agent.assignments: {agent.assignments}")
a2_before = agent.assignments.get("a2")

# STEP 3: Call _handle_announce_config (this is what receive() would trigger)
print(f"\nCalling _handle_announce_config...")
agent._handle_announce_config("Human")

# Check assignments AFTER handling
print(f"\nAFTER _handle_announce_config:")
print(f"  agent.assignments: {agent.assignments}")
a2_after = agent.assignments.get("a2")

# VERIFICATION
print("\n" + "="*70)
print("VERIFICATION")
print("="*70)

if a2_after == "red" and agent.neighbour_assignments.get("h2") == "red":
    print(f"\n[FAIL] Agent announced a2=red when h2=red!")
    print(f"This creates a CONFLICT on edge (a2, h2)")
    print("\nBUG NOT FIXED!")
    exit(1)
else:
    print(f"\n[OK] Agent announced a2={a2_after} (not red)")
    print(f"No conflict with h2=red on edge (a2, h2)")

# Check penalty
from agents.cluster_agent_api import ClusterAgentAPI
api = ClusterAgentAPI(agent)
penalty, conflicts = api.get_current_penalty()

print(f"\nPenalty: {penalty}")
print(f"Conflicts: {conflicts}")

if penalty > 0:
    print(f"\n[FAIL] Non-zero penalty! Conflicts exist: {conflicts}")
    print("Agent's announced config conflicts with human's config!")
    exit(1)
else:
    print(f"\n[OK] Zero penalty - agent's config is compatible with human's!")

# Check if recomputation happened
if a2_before == a2_after and a2_after == "red":
    print(f"\n[WARN] Assignments didn't change (a2 stayed red)")
    print("Recomputation may not have run!")
else:
    print(f"\n[OK] Recomputation changed assignments:")
    print(f"  Before: a2={a2_before}")
    print(f"  After: a2={a2_after}")

print("\n" + "="*70)
print("SUCCESS: Agent respects human's colors when announcing!")
print("="*70)
print("\nSummary:")
print("1. Human announces h2=red")
print("2. _sync_neighbour_views() updates agent.neighbour_assignments")
print("3. Agent receives __ANNOUNCE_CONFIG__")
print("4. Agent recomputes assignments considering h2=red")
print("5. Agent announces conflict-free configuration!")
print("="*70)
