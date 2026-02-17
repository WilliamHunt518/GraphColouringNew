"""Integration test for LLM_TOOL and LLM_REACT modes.

Tests that the new modes can be instantiated and execute basic operations.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from problems.graph_coloring import GraphColoring
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from agents.react_cluster_agent import ReActClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer


def test_agent_instantiation():
    """Test that both agent types can be instantiated."""
    print("\n=== Testing Agent Instantiation ===")

    # Create simple problem
    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "a3"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"}

    # Test ToolCallingClusterAgent
    print("\n1. Testing ToolCallingClusterAgent instantiation...")
    comm_layer = SpeechLLMLayer(use_llm=False)  # Use template mode (no API calls)

    try:
        tool_agent = ToolCallingClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2", "a3"],
            owners=owners,
            backend_model="gpt-4-turbo",
            algorithm="greedy"
        )
        print("   [OK] ToolCallingClusterAgent created successfully")
        print(f"   - API library: {tool_agent.api}")
        print(f"   - Tool definitions: {len(tool_agent.tool_definitions)} functions")
        assert len(tool_agent.tool_definitions) == 11, "Should have 11 tool definitions"
    except Exception as e:
        print(f"   [FAIL] Failed to create ToolCallingClusterAgent: {e}")
        raise

    # Test ReActClusterAgent
    print("\n2. Testing ReActClusterAgent instantiation...")
    comm_layer = SpeechLLMLayer(use_llm=False)  # Use template mode (no API calls)

    try:
        react_agent = ReActClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2", "a3"],
            owners=owners,
            backend_model="gpt-4-turbo",
            max_react_iterations=5,
            algorithm="greedy"
        )
        print("   [OK] ReActClusterAgent created successfully")
        print(f"   - API library: {react_agent.api}")
        print(f"   - Max iterations: {react_agent.max_react_iterations}")
        print(f"   - ReAct prompt length: {len(react_agent.react_prompt)} chars")
        assert react_agent.max_react_iterations == 5, "Should have max 5 iterations"
    except Exception as e:
        print(f"   [FAIL] Failed to create ReActClusterAgent: {e}")
        raise

    print("\n[OK] All agent instantiation tests passed!")


def test_agent_basic_operations():
    """Test that agents can execute basic operations."""
    print("\n=== Testing Agent Basic Operations ===")

    # Create simple problem
    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "a3"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"}

    # Test with ToolCallingClusterAgent
    print("\n1. Testing ToolCallingClusterAgent operations...")
    comm_layer = SpeechLLMLayer(use_llm=False)

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2", "a3"],
        owners=owners,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Set neighbor assignments
    agent.neighbour_assignments = {"h1": "red", "h2": "blue"}

    # Test API operations
    print("   - Testing compute_assignments()...")
    assignments = agent.api.compute_assignments(algorithm="greedy")
    print(f"     Result: {assignments}")
    assert len(assignments) == 3, "Should have 3 node assignments"

    print("   - Testing get_current_penalty()...")
    penalty, conflicts = agent.api.get_current_penalty()
    print(f"     Result: penalty={penalty}, conflicts={len(conflicts)}")
    assert isinstance(penalty, (int, float)), "Penalty should be numeric"

    print("   - Testing get_boundary_nodes()...")
    boundary = agent.api.get_boundary_nodes()
    print(f"     Result: {boundary}")
    assert len(boundary) == 2, "Should have 2 boundary nodes"

    print("\n[OK] All basic operation tests passed!")


def test_announcement_phase():
    """Test that announcement phase works for new modes."""
    print("\n=== Testing Announcement Phase ===")

    # Create simple problem
    nodes = ["a1", "a2", "a3", "h1", "h2"]
    edges = [("a1", "a2"), ("a2", "a3"), ("a2", "h1"), ("a3", "h2")]
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)
    owners = {"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "h1": "Human", "h2": "Human"}

    comm_layer = SpeechLLMLayer(use_llm=False)

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2", "a3"],
        owners=owners,
        backend_model="gpt-4-turbo",
        algorithm="greedy"
    )

    # Check initial phase
    print(f"1. Initial phase: {agent._phase}")
    assert agent._phase == "configure", "Should start in configure phase"
    assert not agent._config_announced, "Config should not be announced yet"

    print("2. Triggering announcement via __ANNOUNCE_CONFIG__...")
    from agents.base_agent import Message
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    print(f"3. After announcement - phase: {agent._phase}, announced: {agent._config_announced}")
    assert agent._phase == "bargain", "Should transition to bargain phase"
    assert agent._config_announced, "Config should be announced"

    print("\n[OK] Announcement phase tests passed!")


if __name__ == "__main__":
    try:
        # Run tests
        test_agent_instantiation()
        test_agent_basic_operations()
        test_announcement_phase()

        print("\n" + "="*70)
        print("[OK] ALL INTEGRATION TESTS PASSED!")
        print("="*70)
        print("\nThe new LLM_TOOL and LLM_REACT modes are working correctly.")
        print("\nTo test with OpenAI API:")
        print("  1. Add valid API key to api_key.txt")
        print("  2. Run: python launch_menu.py")
        print("  3. Select 'LLM_TOOL' or 'LLM_REACT'")
        print("  4. Click 'Start'")

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
