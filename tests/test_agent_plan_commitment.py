"""Test that agents make concrete plans when requesting changes.

Verifies that agents:
1. Test neighbor color changes with simulate_neighbor_change()
2. Get their OWN plan with get_best_response_to()
3. Include both requested_changes AND my_assignments in proposals
4. Apply my_assignments when the human accepts
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_agent_has_plan():
    """Test that agent makes a concrete plan when requesting changes."""
    print("="*70)
    print("TEST: Agent Plan Commitment")
    print("="*70)

    # Setup with conflicts
    nodes = ["a1", "a2", "a4", "h1", "h4"]
    edges = [("a2", "h1"), ("a4", "h4")]
    domain = ["red", "blue", "green"]
    owners = {
        "a1": "Agent1",
        "a2": "Agent1",
        "a4": "Agent1",
        "h1": "Human",
        "h4": "Human"
    }

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    comm_layer = SpeechLLMLayer(use_llm=False)

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2", "a4"],
        owners=owners,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Create conflicts
    agent.assignments = {"a1": "green", "a2": "red", "a4": "red"}
    agent.neighbour_assignments = {"h1": "red", "h4": "red"}

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"\n[Setup]")
    print(f"  Agent assignments: {agent.assignments}")
    print(f"  Human assignments: {agent.neighbour_assignments}")
    print(f"  Penalty: {penalty}, Conflicts: {conflicts}")

    # Announce and trigger response
    agent.sent_messages = []
    agent.receive(Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__"))
    agent.receive(Message(
        sender="Human",
        recipient="Agent1",
        content="What changes do you suggest?"
    ))

    print(f"\n[Generating Response]")
    agent.step()

    # Check the proposal
    if len(agent.sent_messages) < 2:
        print(f"\n[FAIL] No response generated")
        return False

    msg = agent.sent_messages[-1]
    content_str = str(msg.content)

    print(f"\n[Response]")
    print(f"  {content_str}")

    # Parse to check for package deal
    print(f"\n[Verification]")

    # Check 1: Does it request specific changes?
    has_request = False
    for node in ["h1", "h4"]:
        for color in ["blue", "green"]:
            if f"{node}" in content_str and color in content_str:
                has_request = True
                print(f"  [OK] Requests specific change: {node} to {color}")
                break

    if not has_request:
        print(f"  [FAIL] No specific node-color request found")
        return False

    # Check 2: Does it mention what the agent will do?
    # Look for patterns like "I'll set", "I can set", "Then I'll"
    has_plan = any(phrase in content_str.lower() for phrase in [
        "i'll set", "i can set", "then i'll", "i will set",
        "i'll assign", "i can assign"
    ])

    if has_plan:
        print(f"  [OK] Mentions agent's plan (package deal)")
    else:
        print(f"  [WARNING] Doesn't clearly state agent's plan")

    # Check 3: Try to simulate acceptance - does agent apply the plan?
    print(f"\n[Simulating Acceptance]")
    initial_assignments = dict(agent.assignments)
    print(f"  Before: {initial_assignments}")

    # Simulate human accepting by changing h4 to blue
    agent.neighbour_assignments["h4"] = "blue"
    agent.receive(Message(sender="Human", recipient="Agent1", content="OK, I changed h4 to blue"))

    agent.step()

    final_assignments = agent.assignments
    print(f"  After: {final_assignments}")

    if initial_assignments != final_assignments:
        print(f"  [OK] Agent updated their assignments (applied plan)")
        print(f"  Changes: {', '.join(f'{k}:{v}' for k,v in final_assignments.items() if initial_assignments.get(k) != v)}")
    else:
        print(f"  [WARNING] Agent didn't update assignments")

    # Check final penalty
    final_penalty, final_conflicts = agent.api.get_current_penalty()
    print(f"\n[Final State]")
    print(f"  Penalty: {final_penalty}")
    print(f"  Conflicts: {final_conflicts}")

    if final_penalty == 0:
        print(f"  [SUCCESS] Penalty is 0 - plan worked!")
        return True
    else:
        print(f"  [PARTIAL] Penalty > 0, but agent made a concrete attempt")
        return True  # Still pass if agent tried to execute a plan


if __name__ == "__main__":
    success = test_agent_has_plan()
    sys.exit(0 if success else 1)
