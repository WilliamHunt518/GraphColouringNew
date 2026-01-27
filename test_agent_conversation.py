#!/usr/bin/env python3
"""
Manual test to verify agent behavior in LLM_API mode.
Simulates the exact conversation flow the user expects.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from comm.communication_layer import LLMCommLayer

def test_agent_conversation():
    """Test the agent conversation flow."""

    print("=" * 80)
    print("MANUAL AGENT CONVERSATION TEST")
    print("=" * 80)
    print()

    # Set up the graph topology (same as run_experiment.py)
    human_nodes = ["h1", "h2", "h3", "h4", "h5"]
    agent1_nodes = ["a1", "a2", "a3", "a4", "a5"]
    node_names = human_nodes + agent1_nodes

    adjacency = {
        # Human cluster
        "h1": ["h2", "h5"],
        "h2": ["h1", "h3", "h5"],
        "h3": ["h2", "h4"],
        "h4": ["h3", "h5"],
        "h5": ["h1", "h2", "h4"],
        # Agent1 cluster
        "a1": ["a2", "a5"],
        "a2": ["a1", "a3", "a5"],
        "a3": ["a2", "a4"],
        "a4": ["a3", "a5"],
        "a5": ["a1", "a2", "a4"],
    }

    # Cross-cluster edges
    adjacency["h1"].append("a2")
    adjacency["a2"].append("h1")
    adjacency["h4"].append("a4")
    adjacency["a4"].append("h4")
    adjacency["h4"].append("a5")
    adjacency["a5"].append("h4")

    owners = {}
    for node in human_nodes:
        owners[node] = "Human"
    for node in agent1_nodes:
        owners[node] = "Agent1"

    domain = ["red", "green", "blue"]

    # Convert adjacency dict to edge list
    edges = []
    seen = set()
    for node, neighbors in adjacency.items():
        for neighbor in neighbors:
            edge = tuple(sorted([node, neighbor]))
            if edge not in seen:
                edges.append(edge)
                seen.add(edge)

    # Create problem
    problem = GraphColoring(
        nodes=node_names,
        edges=edges,
        domain=domain,
        conflict_penalty=10.0,
        preferences={node: {color: 0.0 for color in domain} for node in node_names}
    )

    # Create Agent1 (LLM_API mode uses "api" message type)
    # CRITICAL: a2 is FIXED to red (matches actual experiment setup)
    # This creates unavoidable conflict when h1=red (since h1 connects to a2)
    comm_layer = LLMCommLayer(manual=False, summariser=None, use_history=True)

    # Capture sent messages
    sent_messages = []

    agent1 = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=agent1_nodes,
        owners=owners,
        algorithm="maxsum",  # Exhaustive search (for LLM_API mode)
        message_type="api",  # LLM_API mode uses "api" message type
        counterfactual_utils=True,
        fixed_local_nodes={"a2": "red"}  # a2 FIXED to red (from actual run)
    )

    # Override send method to capture messages
    original_send = agent1.send
    def capture_send(recipient, content):
        sent_messages.append({"recipient": recipient, "content": content})
        return original_send(recipient, content)
    agent1.send = capture_send

    # Initialize agent with default colors
    agent1.assignments = {node: "red" for node in agent1_nodes}
    agent1.neighbour_assignments = {}

    print(f"Agent1 initial assignments: {agent1.assignments}")
    print()

    # ========================================================================
    # TEST CONVERSATION
    # ========================================================================

    conversation_log = []

    # Turn 1: Human sends initial config
    print("=" * 80)
    print("TURN 1: Human sends initial boundary config")
    print("=" * 80)
    human_msg_1 = ""  # Empty config update
    human_boundary_1 = {"h1": "green", "h4": "red"}

    print(f"Human boundary: {human_boundary_1}")
    print(f"Human message: '{human_msg_1}'")
    print()

    # Update agent's neighbor knowledge
    agent1.neighbour_assignments = dict(human_boundary_1)

    # Agent processes this (send just the text string, not wrapped in dict)
    msg = Message(sender="Human", recipient="Agent1", content=human_msg_1)
    agent1.receive(msg)

    # Run agent's step to process and respond
    try:
        agent1.step()
    except Exception as e:
        print(f"ERROR during agent step: {e}")
        import traceback
        traceback.print_exc()

    # Check what agent sent (look at last message)
    print(f"Agent1 assignments after turn 1: {agent1.assignments}")
    print(f"Agent1 satisfied: {agent1.satisfied}")
    print()

    conversation_log.append({
        "turn": 1,
        "human_msg": human_msg_1,
        "human_boundary": human_boundary_1,
        "agent_assignments": dict(agent1.assignments),
        "agent_satisfied": agent1.satisfied
    })

    # Turn 2: Human asks hypothetical
    print("=" * 80)
    print("TURN 2: Human asks hypothetical about h1=red")
    print("=" * 80)
    human_msg_2 = "h1 may need to be red. Can you plan a colouring around this change or not?"
    human_boundary_2 = {"h1": "red", "h4": "red"}  # Hypothetical

    print(f"Human message: '{human_msg_2}'")
    print(f"Human boundary (hypothetical): {human_boundary_2}")
    print()

    # Update agent's neighbor knowledge
    agent1.neighbour_assignments = dict(human_boundary_2)
    print(f"DEBUG: Set neighbour_assignments to: {agent1.neighbour_assignments}")

    # Agent processes this (send just the text string, not wrapped in dict)
    msg = Message(sender="Human", recipient="Agent1", content=human_msg_2)
    agent1.receive(msg)
    print(f"DEBUG: After receive(), neighbour_assignments = {agent1.neighbour_assignments}")

    # Run agent's step to process and respond
    try:
        agent1.step()
    except Exception as e:
        print(f"ERROR during agent step: {e}")
        import traceback
        traceback.print_exc()

    print(f"DEBUG: After step(), neighbour_assignments = {agent1.neighbour_assignments}")
    print(f"Agent1 assignments after turn 2: {agent1.assignments}")
    print(f"Agent1 satisfied: {agent1.satisfied}")

    # Show formatted messages for both turns
    print(f"\nTotal messages sent: {len(sent_messages)}")

    # Format messages using comm layer
    comm_formatter = LLMCommLayer(manual=False, summariser=None, use_history=False)

    print(f"\n{'='*80}")
    print(f"FORMATTED AGENT MESSAGES:")
    print(f"{'='*80}")

    # Turn 1 messages (first 2)
    print(f"\n--- TURN 1 Messages ---")
    for i, msg in enumerate(sent_messages[:2], 1):
        formatted = comm_formatter.format_content("Agent1", msg["recipient"], msg["content"])
        clean = formatted.split("[mapping:")[0].split("[report:")[0].strip()
        print(f"{i}. {clean}")

    # Turn 2 messages (last 2)
    print(f"\n--- TURN 2 Messages ---")
    for i, msg in enumerate(sent_messages[2:], 1):
        formatted = comm_formatter.format_content("Agent1", msg["recipient"], msg["content"])
        clean = formatted.split("[mapping:")[0].split("[report:")[0].strip()
        print(f"{i}. {clean}")
    print()

    # Check what the agent computed
    tested_configs = getattr(agent1, "_last_tested_boundary_configs", [])
    print(f"Tested {len(tested_configs)} boundary configurations:")
    for i, test in enumerate(tested_configs[:5], 1):
        config = test["config"]
        penalty = test["penalty"]
        print(f"  {i}. {config}: penalty={penalty:.2f}")
    print()

    conversation_log.append({
        "turn": 2,
        "human_msg": human_msg_2,
        "human_boundary": human_boundary_2,
        "agent_assignments": dict(agent1.assignments),
        "agent_satisfied": agent1.satisfied,
        "tested_configs": [{"config": t["config"], "penalty": t["penalty"]} for t in tested_configs]
    })

    # Expected behavior check
    print("=" * 80)
    print("EXPECTED BEHAVIOR CHECK")
    print("=" * 80)
    print()

    # Check 1: Did agent test h1=red with all h4 values?
    h1_red_configs = [t for t in tested_configs if t["config"].get("h1") == "red"]
    print(f"[CHECK] Agent tested {len(h1_red_configs)} configs with h1=red")

    if h1_red_configs:
        for cfg in h1_red_configs:
            print(f"  - {cfg['config']}: penalty={cfg['penalty']:.2f}")

    # Check 2: Did agent find that h1=red doesn't work?
    all_h1_red_fail = all(t["penalty"] > 0 for t in h1_red_configs)
    if all_h1_red_fail:
        print(f"[CHECK] All h1=red configs failed (penalty > 0)")
    else:
        print(f"[ERROR] Some h1=red configs succeeded")

    # Check 3: Should agent have said "h1=red doesn't work"?
    print()
    print("Expected agent response:")
    print("  'With h1=red, I tested all h4 values (red, green, blue).")
    print("   All gave penalty > 0. For me to solve this, h1 would need")
    print("   to be green or blue instead of red.'")
    print()

    # Save conversation log
    log_path = project_root / "test_conversation_log.txt"
    with open(log_path, "w") as f:
        f.write("AGENT CONVERSATION TEST LOG\n")
        f.write("=" * 80 + "\n\n")

        for turn_data in conversation_log:
            f.write(f"TURN {turn_data['turn']}:\n")
            f.write(f"  Human message: {turn_data['human_msg']}\n")
            f.write(f"  Human boundary: {turn_data['human_boundary']}\n")
            f.write(f"  Agent assignments: {turn_data['agent_assignments']}\n")
            f.write(f"  Agent satisfied: {turn_data['agent_satisfied']}\n")

            if "tested_configs" in turn_data:
                f.write(f"  Tested configs:\n")
                for cfg in turn_data["tested_configs"]:
                    f.write(f"    - {cfg['config']}: penalty={cfg['penalty']:.2f}\n")

            f.write("\n")

    print(f"Conversation log saved to: {log_path}")
    print()

    return conversation_log

if __name__ == "__main__":
    try:
        test_agent_conversation()
    except Exception as e:
        print(f"TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
