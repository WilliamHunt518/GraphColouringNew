"""Test the correct flow: agent announces, waits for human, then responds."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


print("\n" + "="*70)
print("TESTING CORRECT ANNOUNCEMENT FLOW")
print("="*70)

# Setup
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
print(f"   Initial assignments (algorithmic): {agent.assignments}")
print(f"   Phase: {agent._phase}")
print(f"   Messages sent: {len(agent.sent_messages)}")

# Set neighbor assignments
agent.neighbour_assignments = {"h1": None, "h2": None}

print("\n[STEP 2] Agent announces config (should be fast, no LLM)...")
agent.step()

print(f"   Phase after step: {agent._phase}")
print(f"   Config announced: {agent._config_announced}")
print(f"   Messages sent: {len(agent.sent_messages)}")
if agent.sent_messages:
    msg = agent.sent_messages[0]
    print(f"   Message to: {msg.recipient}")
    print(f"   Message preview: {str(msg.content)[:100]}...")
    # Check it has report tag
    if "[report:" in str(msg.content):
        print("   [OK] Message has [report:] tag for UI")
    else:
        print("   [ERROR] Message missing [report:] tag!")

print("\n[STEP 3] Agent step() again (should NOT generate message - waiting for human)...")
initial_count = len(agent.sent_messages)
agent.step()

if len(agent.sent_messages) == initial_count:
    print("   [OK] No new messages sent - agent is waiting")
else:
    print(f"   [ERROR] Agent sent {len(agent.sent_messages) - initial_count} unexpected messages!")

print("\n[STEP 4] Human announces their config...")
human_msg = Message(
    sender="Human",
    recipient="Agent1",
    content="Here's my configuration: h1=red, h2=blue [report: {\"h1\": \"red\", \"h2\": \"blue\"}]"
)
agent.receive(human_msg)
print(f"   Agent received human announcement")
print(f"   _received_human_message_this_turn: {agent._received_human_message_this_turn}")

print("\n[STEP 5] Agent step() (should NOW generate substantive response with LLM)...")
print("   NOTE: This will only work if OpenAI API key is configured")
print("   Without API key, agent will fall back to algorithmic mode")

before_count = len(agent.sent_messages)
try:
    agent.step()
    after_count = len(agent.sent_messages)

    if after_count > before_count:
        print(f"   [OK] Agent sent {after_count - before_count} message(s) in response")
        for msg in agent.sent_messages[before_count:]:
            print(f"   Response to: {msg.recipient}")
            print(f"   Response preview: {str(msg.content)[:150]}...")
    else:
        print("   [INFO] No messages sent (might be due to no conflicts or no API key)")
except Exception as e:
    print(f"   [ERROR] Exception during step: {e}")

print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print(f"Expected flow:")
print(f"  1. Agent announces config immediately (fast, template-based)")
print(f"  2. Agent waits for human announcement")
print(f"  3. After human announces, agent generates substantive response (LLM)")
print(f"\nActual results:")
print(f"  - Announcement sent: {agent._config_announced}")
print(f"  - Total messages: {len(agent.sent_messages)}")
print(f"  - Phase: {agent._phase}")
print("="*70)
