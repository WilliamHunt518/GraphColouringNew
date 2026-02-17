"""Test that Phase 3 template fallback uses simulation results to propose valid alternatives."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer


def test_phase3_template_fallback_with_simulations():
    """Test that Phase 3 template fallback extracts and uses simulation results."""
    print("\n" + "="*70)
    print("TEST: Phase 3 Template Fallback Uses Simulation Results")
    print("="*70)

    # Create simple problem with conflict
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

    print("\n--- Setup ---")
    print(f"Agent a1: {agent.assignments['a1']}")
    print(f"Human h4: {agent.neighbour_assignments['h4']}")
    print("Conflict: both red")

    # Manually construct api_results as if Phase 2 executed comprehensive simulation
    print("\n--- Simulating Phase 2 Results ---")
    api_results = {
        "current_penalty": 1.0,
        "current_conflicts": [("a1", "h4")],
        "best_response": {"a1": "blue", "penalty": 1.0},  # Best response still has penalty
        # Simulation results for h4=blue (works!)
        "simulation_h4_blue": {
            "penalty": 0.0,
            "conflicts": [],
            "my_best_response": {"a1": "green"}
        },
        # Simulation results for h4=green (also works!)
        "simulation_h4_green": {
            "penalty": 0.0,
            "conflicts": [],
            "my_best_response": {"a1": "blue"}
        },
        # h4=red doesn't work (same as current)
        "simulation_h4_red": {
            "penalty": 1.0,
            "conflicts": [("a1", "h4")]
        }
    }

    print("Simulations executed:")
    for key, value in api_results.items():
        if key.startswith("simulation_"):
            penalty = value.get("penalty", "N/A")
            print(f"  - {key}: penalty={penalty}")

    # Test Phase 3 with these results
    # Note: Phase 3 will try LLM first, then fall back to template
    print("\n--- Phase 3: Translate Outbound ---")

    # Directly call the template fallback logic by causing LLM to fail
    # We'll mock this by temporarily removing backend_llm
    original_llm = agent.backend_llm
    agent.backend_llm = None  # Force template fallback

    try:
        response = agent._translate_outbound(api_results, "What should we do?")

        print(f"\nResponse:")
        print(f"  Message type: {response.get('message_type')}")
        print(f"  Reason: {response.get('structured_content', {}).get('reason', 'N/A')}")
        print(f"  Requested changes: {response.get('structured_content', {}).get('requested_changes', {})}")
        print(f"  My assignments: {response.get('structured_content', {}).get('my_assignments', {})}")

        # Verify the template fallback found a working alternative
        requested_changes = response.get('structured_content', {}).get('requested_changes', {})

        if not requested_changes:
            print("\n[FAIL] No requested changes - template fallback didn't extract simulation results")
            return False

        # Check if the requested change matches a successful simulation
        for node, color in requested_changes.items():
            sim_key = f"simulation_{node}_{color}"
            if sim_key in api_results:
                sim_penalty = api_results[sim_key].get('penalty', float('inf'))
                if sim_penalty < 1e-6:
                    print(f"\n[OK] Template fallback proposed {node}={color} from simulation results (penalty=0)")
                    print(f"[OK] This is a TESTED, VALID alternative!")
                    return True
                else:
                    print(f"\n[FAIL] Template fallback proposed {node}={color} but simulation shows penalty={sim_penalty}")
                    return False
            else:
                print(f"\n[FAIL] Template fallback proposed {node}={color} but no simulation result found")
                print(f"Available simulations: {[k for k in api_results.keys() if k.startswith('simulation_')]}")
                return False

    finally:
        agent.backend_llm = original_llm  # Restore

    return False


def test_comprehensive_fallback_generates_simulations():
    """Test that Phase 1 enhanced fallback generates simulation calls."""
    print("\n" + "="*70)
    print("TEST: Phase 1 Enhanced Fallback Generates Simulations")
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

    agent.assignments = {"a1": "red"}
    agent.neighbour_assignments = {"h4": "red"}

    print("\n--- Testing Phase 1 Fallback ---")

    # Force Phase 1 to use fallback by removing backend_llm
    original_llm = agent.backend_llm
    agent.backend_llm = None

    try:
        # This should trigger the enhanced fallback (lines 330-352)
        api_calls = agent._translate_inbound("What should we do?")

        print(f"API calls generated: {len(api_calls)}")
        for i, call in enumerate(api_calls):
            print(f"  {i+1}. {call['method']}({call.get('params', {})})")

        # Check for simulation calls
        simulation_calls = [c for c in api_calls if c['method'] == 'simulate_neighbor_change']
        print(f"\nSimulation calls: {len(simulation_calls)}")

        if simulation_calls:
            print("[OK] Phase 1 fallback generated simulation calls!")

            # Verify it tests alternatives for visible neighbor h4
            h4_sims = [c for c in simulation_calls if 'h4' in str(c.get('params', {}))]
            print(f"Simulations for h4: {len(h4_sims)}")

            if h4_sims:
                print("[OK] Phase 1 fallback tests alternatives for visible neighbor h4")
                return True
            else:
                print("[FAIL] No simulations found for h4")
                return False
        else:
            print("[FAIL] Phase 1 fallback didn't generate simulation calls")
            return False

    finally:
        agent.backend_llm = original_llm


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TESTING: Phase 3 Uses Simulation Results")
    print("="*70)

    success1 = test_phase3_template_fallback_with_simulations()
    success2 = test_comprehensive_fallback_generates_simulations()

    print("\n" + "="*70)
    if success1 and success2:
        print("ALL TESTS PASSED!")
        print("- Phase 1 fallback generates comprehensive simulation calls")
        print("- Phase 3 fallback extracts and uses simulation results")
        print("- Agents propose only TESTED, VALID alternatives")
    else:
        print("SOME TESTS FAILED - Review output above")
    print("="*70)
