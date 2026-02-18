"""
Quick test for ReAct agent announcement response.
"""

from agents.react_cluster_agent import ReActClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.speech_llm_layer import SpeechLLMLayer

print("="*70)
print("TEST: ReAct Agent Announcement Response")
print("="*70)

# Create simple problem
nodes = ["a1", "a2", "h1", "h2"]
edges = [("a1", "a2"), ("a2", "h2")]
domain = ["red", "blue", "green"]

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)
owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

# Create agent
try:
    agent = ReActClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=SpeechLLMLayer(use_llm=False),
        local_nodes=["a1", "a2"],
        owners=owners
    )
    print(f"\n[OK] Agent created")
    print(f"  backend_llm: {agent.backend_llm is not None}")
    print(f"  Initial assignments: {agent.assignments}")
except Exception as e:
    print(f"\n[FAIL] Error creating agent: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Simulate announcement flow
print("\n--- Step 1: Simulate _sync_neighbour_views ---")
agent.neighbour_assignments = {"h2": "red"}
print(f"  neighbour_assignments: {agent.neighbour_assignments}")

# Simulate receiving __ANNOUNCE_CONFIG__
print("\n--- Step 2: Agent receives __ANNOUNCE_CONFIG__ ---")
msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
agent.receive(msg)
print(f"  Message received")
print(f"  _received_human_message_this_turn: {agent._received_human_message_this_turn}")

# Call step (this should generate announcement response)
print("\n--- Step 3: Agent.step() ---")
try:
    agent.step()
    print(f"  step() completed")
except Exception as e:
    print(f"\n[FAIL] Error in step(): {e}")
    import traceback
    traceback.print_exc()

# Check if message was sent
print("\n--- Step 4: Check Results ---")
print(f"Agent's final assignments: {agent.assignments}")
print(f"Config announced: {agent._config_announced}")
print(f"Phase: {agent._phase}")

# Check logs
print("\n--- Agent Logs (last 10) ---")
for log in agent.logs[-10:]:
    print(f"  {log}")

print("\n" + "="*70)
print("Test complete - check logs above for errors")
print("="*70)
