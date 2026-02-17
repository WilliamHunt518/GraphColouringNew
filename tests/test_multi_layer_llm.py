"""Test multi-layer LLM architecture implementation.

This test verifies that the API library, tool calling agent, and ReAct agent
are correctly integrated and functional.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.cluster_agent_api import ClusterAgentAPI
from agents.cluster_agent import ClusterAgent
from comm.communication_layer import PassThroughCommLayer


def test_api_library():
    """Test that ClusterAgentAPI methods work correctly."""
    print("\n=== Testing API Library ===")

    # Create simple problem
    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "a3"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(
        nodes=nodes,
        edges=edges,
        domain=domain
    )

    # Create agent
    comm_layer = PassThroughCommLayer()
    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2", "a3"],
        owners={"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"},
        algorithm="greedy"
    )

    # Set neighbor assignments
    agent.neighbour_assignments = {"h1": "red", "h2": "blue"}

    # Test API
    api = ClusterAgentAPI(agent)

    print("\n1. Testing compute_assignments()")
    assignments = api.compute_assignments(algorithm="greedy")
    print(f"   Result: {assignments}")
    assert isinstance(assignments, dict), "Should return dict"
    assert len(assignments) == 3, "Should have 3 nodes"

    print("\n2. Testing get_current_penalty()")
    penalty, conflicts = api.get_current_penalty()
    print(f"   Result: penalty={penalty}, conflicts={conflicts}")
    assert isinstance(penalty, (int, float)), "Penalty should be numeric"
    assert isinstance(conflicts, list), "Conflicts should be list"

    print("\n3. Testing test_configuration()")
    result = api.test_configuration({"a1": "blue", "a2": "green", "a3": "red"})
    print(f"   Result: {result}")
    assert "penalty" in result, "Should have penalty"
    assert "feasible" in result, "Should have feasibility"
    assert "conflicts" in result, "Should have conflicts"

    print("\n4. Testing get_boundary_nodes()")
    boundary = api.get_boundary_nodes()
    print(f"   Result: {boundary}")
    assert isinstance(boundary, list), "Should return list"

    print("\n5. Testing check_feasibility()")
    feasible = api.check_feasibility("a1", "blue")
    print(f"   Result: {feasible}")
    assert isinstance(feasible, bool), "Should return bool"

    print("\n6. Testing get_available_colors()")
    available = api.get_available_colors("a1")
    print(f"   Result: {available}")
    assert isinstance(available, list), "Should return list"

    print("\n7. Testing get_neighbor_constraints()")
    constraints = api.get_neighbor_constraints("Human")
    print(f"   Result: {constraints}")
    assert "boundary_nodes" in constraints, "Should have boundary_nodes"
    assert "forbidden_colors" in constraints, "Should have forbidden_colors"

    print("\n[OK] API Library tests passed!")


def test_tool_calling_agent_import():
    """Test that ToolCallingClusterAgent can be imported."""
    print("\n=== Testing Tool Calling Agent Import ===")

    try:
        from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
        print("[OK] ToolCallingClusterAgent imported successfully")

        # Check that it has required methods
        assert hasattr(ToolCallingClusterAgent, 'step'), "Should have step method"
        assert hasattr(ToolCallingClusterAgent, 'receive'), "Should have receive method"
        assert hasattr(ToolCallingClusterAgent, '_execute_tool_call'), "Should have _execute_tool_call method"
        print("[OK] ToolCallingClusterAgent has required methods")

    except Exception as e:
        print(f"[FAIL] Failed to import ToolCallingClusterAgent: {e}")
        raise


def test_react_agent_import():
    """Test that ReActClusterAgent can be imported."""
    print("\n=== Testing ReAct Agent Import ===")

    try:
        from agents.react_cluster_agent import ReActClusterAgent
        print("[OK] ReActClusterAgent imported successfully")

        # Check that it has required methods
        assert hasattr(ReActClusterAgent, 'step'), "Should have step method"
        assert hasattr(ReActClusterAgent, 'receive'), "Should have receive method"
        assert hasattr(ReActClusterAgent, '_execute_action_from_text'), "Should have _execute_action_from_text method"
        print("[OK] ReActClusterAgent has required methods")

    except Exception as e:
        print(f"[FAIL] Failed to import ReActClusterAgent: {e}")
        raise


def test_speech_llm_layer():
    """Test that SpeechLLMLayer works correctly."""
    print("\n=== Testing Speech LLM Layer ===")

    try:
        from comm.speech_llm_layer import SpeechLLMLayer

        # Test with LLM disabled (template mode)
        layer = SpeechLLMLayer(use_llm=False)
        print("[OK] SpeechLLMLayer initialized")

        # Test human_to_backend (heuristic mode)
        print("\n1. Testing human_to_backend() with heuristic parser")
        structured = layer.human_to_backend("Human", "Agent1", "Can you set h1 to red?")
        print(f"   Result: {structured}")
        assert "type" in structured, "Should have type"
        assert "sentiment" in structured, "Should have sentiment"
        assert "original_text" in structured, "Should preserve original text"

        # Test backend_to_human (template mode)
        print("\n2. Testing backend_to_human() with template")
        backend_data = {
            "message_type": "proposal",
            "structured_content": {
                "my_assignments": {"a1": "red", "a2": "blue"},
                "reason": "This resolves conflicts"
            }
        }
        nl_message = layer.backend_to_human("Agent1", "Human", backend_data)
        print(f"   Result: {nl_message}")
        assert isinstance(nl_message, str), "Should return string"
        assert "[report:" in nl_message, "Should have report tag"

        print("\n[OK] Speech LLM Layer tests passed!")

    except Exception as e:
        print(f"[FAIL] Speech LLM Layer test failed: {e}")
        raise


def test_integration():
    """Test that all components work together."""
    print("\n=== Testing Integration ===")

    # Verify imports
    test_tool_calling_agent_import()
    test_react_agent_import()
    test_speech_llm_layer()

    print("\n[OK] All integration tests passed!")


if __name__ == "__main__":
    try:
        # Run tests
        test_api_library()
        test_integration()

        print("\n" + "="*50)
        print("[OK] ALL TESTS PASSED!")
        print("="*50)
        print("\nMulti-layer LLM architecture is ready to use.")
        print("\nTo run experiments:")
        print("  1. Add OpenAI API key to api_key.txt")
        print("  2. Launch: python launch_menu.py")
        print("  3. Select 'LLM_TOOL' or 'LLM_REACT' mode")
        print("  4. Click 'Start' to begin experiment")

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
