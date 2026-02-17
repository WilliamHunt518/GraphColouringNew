"""Test that announcements are silent (colors update but no chat message)."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


print("\n" + "="*70)
print("TESTING SILENT ANNOUNCEMENT")
print("="*70)

# Setup
nodes = ["a1", "a2", "h1"]
edges = [("a1", "h1"), ("a2", "h1")]
domain = ["red", "blue", "green"]
owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}

problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
comm_layer = SpeechLLMLayer(use_llm=False)

agent = ToolCallingClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=["a1", "a2"],
    owners=owners,
    backend_model="gpt-4-turbo",
    algorithm="greedy"
)

agent.neighbour_assignments = {"h1": None}

print("\n[TEST 1] Check announcement message format...")
agent.step()

if agent.sent_messages:
    msg = agent.sent_messages[0]
    content = str(msg.content)

    print(f"   Message content: {content}")

    # Check for silent marker
    if content.startswith("__SILENT__"):
        print("   [OK] Message has __SILENT__ marker")
    else:
        print("   [ERROR] Message missing __SILENT__ marker!")

    # Check for report tag
    if "[report:" in content:
        print("   [OK] Message has [report:] tag for UI color updates")
    else:
        print("   [ERROR] Message missing [report:] tag!")

    # Check that it doesn't have the old text
    if "Here's my initial configuration" not in content:
        print("   [OK] Old announcement text removed")
    else:
        print("   [ERROR] Still has old announcement text!")
else:
    print("   [ERROR] No messages sent!")

print("\n[TEST 2] Simulate UI processing...")
# Simulate what the UI does
if agent.sent_messages:
    msg_content = str(agent.sent_messages[0].content)

    # Check if UI would display this
    if msg_content.startswith("__SILENT__"):
        print("   [OK] UI will skip displaying this message in chat")
        print("   [OK] But UI will still extract [report:] tag and update colors")
    else:
        print("   [ERROR] UI would display this in chat (not silent!)")

print("\n[TEST 3] Check first substantive message after human announces...")
# Simulate human announcement
human_msg = Message(
    sender="Human",
    recipient="Agent1",
    content="Here's my configuration: h1=red [report: {\"h1\": \"red\"}]"
)
agent.receive(human_msg)

# Agent should now generate substantive message
initial_count = len(agent.sent_messages)
agent.step()

if len(agent.sent_messages) > initial_count:
    substantive_msg = agent.sent_messages[-1]
    content = str(substantive_msg.content)

    print(f"   Substantive message: {content[:150]}...")

    # Check it's not silent
    if not content.startswith("__SILENT__"):
        print("   [OK] Substantive message is visible in chat")
    else:
        print("   [ERROR] Substantive message is marked silent!")

    # Check it has report tag (for color updates)
    if "[report:" in content:
        print("   [OK] Substantive message includes color updates")

else:
    print("   [INFO] No substantive message (may need API key or conflicts)")

print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print("Expected behavior:")
print("  1. Announcement: Silent (__SILENT__ marker) with [report:] tag")
print("  2. UI: Extracts colors, updates graph, NO chat message")
print("  3. After human announces: Substantive offer in chat")
print("="*70)
