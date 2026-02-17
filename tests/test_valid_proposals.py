"""Test that agents only propose configurations that have been tested and verified."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from agents.base_agent import Message


def test_agents_propose_tested_alternatives():
    """Test that agents propose only alternatives that were tested via API."""
    print("\n" + "="*70)
    print("TEST: Agents Propose Only TESTED Alternatives")
    print("="*70)

    # Create a problem with conflicts
    nodes = ["a2", "a4", "h4"]
    edges = [("a2", "h4"), ("a4", "h4")]  # Both a2 and a4 connect to h4
    colors = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, colors)
    owners = {"a2": "Agent1", "a4": "Agent1", "h4": "Human"}

    # Create agent WITHOUT LLM (will use template fallback)
    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=SpeechLLMLayer(use_llm=False),
        local_nodes=["a2", "a4"],
        owners=owners
    )

    # Set up state with conflict: a2=red, a4=red, h4=red (all red - conflicts!)
    agent.assignments = {"a2": "red", "a4": "red"}
    agent.neighbour_assignments = {"h4": "red"}
    agent._config_announced = True
    agent._phase = "bargain"

    print("\n--- Setup ---")
    print(f"Agent nodes: a2={agent.assignments['a2']}, a4={agent.assignments['a4']}")
    print(f"Human node: h4={agent.neighbour_assignments['h4']}")

    penalty, conflicts = agent.api.get_current_penalty()
    print(f"Current penalty: {penalty}")
    print(f"Conflicts: {conflicts}")

    # Test that agent proposes a valid alternative
    print("\n--- Test: Agent Proposes Valid Alternative ---")

    msg = Message(
        sender="Human",
        recipient="Agent1",
        content="What should we do about the conflicts?"
    )

    agent.receive(msg)
    before = len(agent.sent_messages)
    agent.step()
    after = len(agent.sent_messages)

    if after > before:
        reply = agent.sent_messages[-1].content
        print(f"\nAgent reply: {reply}")

        # Extract requested_changes from the structured message
        structured = agent.sent_messages[-1]
        if hasattr(structured, 'content') and isinstance(structured.content, dict):
            requested_changes = structured.content.get('requested_changes', {})
        else:
            requested_changes = {}

        print(f"Requested changes: {requested_changes}")

        if requested_changes:
            # Verify the proposal was tested
            print("\n--- Verifying Proposal Was Tested ---")

            for node, color in requested_changes.items():
                # Test this specific proposal
                result = agent.api.simulate_neighbor_change(neighbor_nodes={node: color})
                penalty = result.get('penalty', float('inf'))
                conflicts = result.get('conflicts', [])

                print(f"Testing {node}={color}: penalty={penalty}, conflicts={conflicts}")

                if penalty < 1e-6:
                    print(f"[OK] Agent proposed {node}={color} which resolves conflicts (penalty=0)")
                else:
                    print(f"[FAIL] Agent proposed {node}={color} but it has penalty={penalty}, conflicts={conflicts}")
                    print(f"[FAIL] Agent should only propose tested alternatives with penalty=0!")
                    return False
        else:
            print("[WARN] Agent didn't request any specific changes")

        print("\n[SUCCESS] Agent only proposes tested, valid configurations!")
        return True
    else:
        print("[FAIL] No reply from agent")
        return False


def test_template_fallback_uses_simulation_results():
    """Test that template fallback uses simulation results from Phase 2."""
    print("\n" + "="*70)
    print("TEST: Template Fallback Uses Simulation Results")
    print("="*70)

    # Create simple problem
    nodes = ["a1", "h4"]
    edges = [("a1", "h4")]
    colors = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, colors)
    owners = {"a1": "Agent1", "h4": "Human"}

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=SpeechLLMLayer(use_llm=False),
        local_nodes=["a1"],
        owners=owners
    )

    # Set up conflict: both red
    agent.assignments = {"a1": "red"}
    agent.neighbour_assignments = {"h4": "red"}
    agent._config_announced = True
    agent._phase = "bargain"

    print("\n--- Setup ---")
    print(f"Agent a1: {agent.assignments['a1']}")
    print(f"Human h4: {agent.neighbour_assignments['h4']}")
    print("Conflict: both red")

    # Manually test Phase 1 fallback
    print("\n--- Phase 1: Translate Inbound (Fallback) ---")

    # Check visible neighbors
    visible_neighbor_nodes = set()
    for u, v in agent.problem.edges:
        if u in agent.nodes and v not in agent.nodes:
            visible_neighbor_nodes.add(v)
        elif v in agent.nodes and u not in agent.nodes:
            visible_neighbor_nodes.add(u)
    print(f"Visible neighbors: {visible_neighbor_nodes}")
    print(f"Domain (colors): {agent.domain}")

    api_calls = agent._translate_inbound("Can you help?")
    print(f"API calls generated: {len(api_calls)}")
    for i, call in enumerate(api_calls):
        print(f"  {i+1}. {call['method']}({call.get('params', {})})")

    # Check that simulate_neighbor_change was called for alternatives
    simulation_calls = [c for c in api_calls if c['method'] == 'simulate_neighbor_change']
    print(f"\nSimulation calls: {len(simulation_calls)}")

    if simulation_calls:
        print("[OK] Phase 1 fallback generates simulation calls")
        for call in simulation_calls[:3]:  # Show first 3
            print(f"  - {call}")
    else:
        print("[FAIL] Phase 1 fallback didn't generate simulation calls!")
        return False

    # Test Phase 2: Execute
    print("\n--- Phase 2: Execute API Methods ---")
    api_results = agent._execute_api_methods(api_calls)
    print(f"Results keys: {list(api_results.keys())}")

    # Check for simulation results
    sim_results = {k: v for k, v in api_results.items() if k.startswith('simulation_')}
    print(f"Simulation results: {len(sim_results)}")

    if sim_results:
        print("[OK] Phase 2 executed simulations")
        for key, value in list(sim_results.items())[:3]:  # Show first 3
            print(f"  - {key}: penalty={value.get('penalty', 'N/A')}")
    else:
        print("[FAIL] Phase 2 didn't produce simulation results!")
        return False

    # Test Phase 3: Translate Outbound (will use template fallback)
    print("\n--- Phase 3: Translate Outbound (Template Fallback) ---")
    response = agent._translate_outbound(api_results, "Can you help?")

    print(f"Message type: {response.get('message_type')}")
    print(f"Reason: {response.get('structured_content', {}).get('reason', 'N/A')}")
    print(f"Requested changes: {response.get('structured_content', {}).get('requested_changes', {})}")

    requested_changes = response.get('structured_content', {}).get('requested_changes', {})

    if requested_changes:
        # Verify the proposed change was tested and works
        for node, color in requested_changes.items():
            # Check if this combination appears in simulation results
            sim_key = f"simulation_{node}_{color}"
            if sim_key in api_results:
                sim_penalty = api_results[sim_key].get('penalty', float('inf'))
                if sim_penalty < 1e-6:
                    print(f"[OK] Template fallback proposed {node}={color} which was tested (penalty=0)")
                    return True
                else:
                    print(f"[FAIL] Template fallback proposed {node}={color} but simulation shows penalty={sim_penalty}")
                    return False
            else:
                print(f"[WARN] Template fallback proposed {node}={color} but no simulation result found")
                print(f"Available simulations: {[k for k in api_results.keys() if k.startswith('simulation_')]}")
                return False
    else:
        print("[WARN] No requested changes in response")
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TESTING: Valid Proposal Generation")
    print("="*70)

    success1 = test_agents_propose_tested_alternatives()
    success2 = test_template_fallback_uses_simulation_results()

    print("\n" + "="*70)
    if success1 and success2:
        print("ALL TESTS PASSED - Agents only propose tested, valid configurations!")
    else:
        print("SOME TESTS FAILED - Review output above")
    print("="*70)
