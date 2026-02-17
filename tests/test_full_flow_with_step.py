"""Test full flow: announcement + step() like the GUI does."""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


print("\n" + "="*70)
print("SIMULATING EXACT GUI FLOW")
print("="*70)

# Setup like GUI does
nodes = ["a1", "a2", "h1", "h2"]
edges = [("a1", "h1"), ("a2", "h1"), ("a2", "h2")]
domain = ["red", "blue", "green"]
owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
comm_layer = SpeechLLMLayer(use_llm=False)

print("\n[STEP 1] Creating agent...")
agent = ToolCallingClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=["a1", "a2"],
    owners=owners,
    backend_model="gpt-4-turbo",
    algorithm="greedy"
)

print(f"   Agent created: {agent.name}")
print(f"   Assignments: {agent.assignments}")
print(f"   Phase: {agent._phase}")

# Simulate human having colors (GUI would set these)
print("\n[STEP 2] Setting human's boundary colors...")
agent.neighbour_assignments = {"h1": "red", "h2": "blue"}
print(f"   Human boundaries: {agent.neighbour_assignments}")

# GUI sends __ANNOUNCE_CONFIG__ (bypassing comm layer)
print("\n[STEP 3] Sending __ANNOUNCE_CONFIG__ (like GUI does)...")
msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
print(f"   Message: {msg.content}")

agent.sent_messages = []  # Clear for testing
agent.receive(msg)

print(f"\n[STEP 4] After receive():")
print(f"   Phase: {agent._phase}")
print(f"   Config announced: {agent._config_announced}")
print(f"   Messages sent: {len(agent.sent_messages)}")
print(f"   Should generate first: {getattr(agent, '_should_generate_first_message', 'N/A')}")

if agent.sent_messages:
    print(f"\n   [ANNOUNCEMENT MESSAGE]")
    msg = agent.sent_messages[0]
    print(f"   To: {msg.recipient}")
    content_str = str(msg.content)
    print(f"   Content: {content_str[:150]}...")

    # Check for report tag (needed for UI color updates)
    if "[report:" in content_str:
        print(f"   [OK] Contains [report: ...] tag (UI will extract colors)")
        import re
        match = re.search(r'\[report:\s*({.*?})\]', content_str)
        if match:
            print(f"   Report data: {match.group(1)}")
    else:
        print(f"   [ERROR] Missing [report: ...] tag!")

# GUI calls step() after announcement (line 801 in cluster_simulation.py)
print(f"\n[STEP 5] Calling step() (like GUI does)...")
agent.step()

print(f"\n[STEP 6] After step():")
print(f"   Total messages sent: {len(agent.sent_messages)}")
print(f"   Should generate first: {getattr(agent, '_should_generate_first_message', 'N/A')}")

if len(agent.sent_messages) > 1:
    print(f"\n   [FIRST SUBSTANTIVE MESSAGE]")
    msg = agent.sent_messages[1]
    print(f"   To: {msg.recipient}")
    content_str = str(msg.content)
    print(f"   Content: {content_str[:200]}...")
else:
    print(f"\n   [ERROR] NO SECOND MESSAGE GENERATED")
    if agent.backend_llm is None:
        print(f"      Reason: No backend LLM (no api_key.txt)")
    else:
        print(f"      Reason: Unknown - check logs above")

print("\n" + "="*70)
print("FLOW COMPLETE")
print("="*70)

# Summary
print("\nSUMMARY:")
print(f"  - Announcement sent: {len(agent.sent_messages) >= 1}")
print(f"  - First message sent: {len(agent.sent_messages) >= 2}")
print(f"  - Backend LLM: {'Available' if agent.backend_llm else 'Missing'}")

if len(agent.sent_messages) >= 1:
    print(f"\n  Expected UI behavior:")
    print(f"    1. Graph colors update (from report tag in announcement)")
    print(f"    2. Chat shows {len(agent.sent_messages)} message(s)")
else:
    print(f"\n  [ERROR] PROBLEM: No messages sent at all!")
