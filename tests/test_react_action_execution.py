"""
Test ReAct agent action execution with actual API calls.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.react_cluster_agent import ReActClusterAgent
from problems.graph_coloring import GraphColoring
from comm.speech_llm_layer import SpeechLLMLayer

print("="*70)
print("TEST: ReAct Agent Action Execution")
print("="*70)

# Create simple problem
nodes = ["a1", "a2", "a3", "a4", "a5", "h1", "h2", "h3", "h4", "h5"]
edges = [
    ("a1", "a2"), ("a2", "a3"), ("a3", "a4"), ("a4", "a5"),
    ("a2", "h1"), ("a4", "h4"), ("a5", "h4")  # Boundary edges
]
domain = ["red", "blue", "green"]

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)
owners = {
    "a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "a4": "Agent1", "a5": "Agent1",
    "h1": "Human", "h2": "Human", "h3": "Human", "h4": "Human", "h5": "Human"
}

# Create agent
agent = ReActClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=SpeechLLMLayer(use_llm=False),
    local_nodes=["a1", "a2", "a3", "a4", "a5"],
    owners=owners
)

# Set neighbor assignments
agent.neighbour_assignments = {
    "h1": "red",
    "h2": "blue",
    "h3": "green",
    "h4": "red",
    "h5": "green"
}

print(f"\n[OK] Agent created")
print(f"  Neighbor assignments: {agent.neighbour_assignments}")

# Test cases for action execution
test_cases = [
    {
        "name": "get_current_penalty()",
        "text": "Action: get_current_penalty()",
        "expected_type": "dict",  # API returns dict, not tuple
        "expected_keys": ["penalty", "conflicts"],
    },
    {
        "name": "get_best_response_to() with 5 neighbors",
        "text": 'Action: get_best_response_to(neighbor_assignments={"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"})',
        "expected_type": "dict",
        "expected_keys": ["a1", "a2", "a3", "a4", "a5", "penalty"],
    },
    {
        "name": "simulate_neighbor_change() with 5 neighbors",
        "text": 'Action: simulate_neighbor_change(neighbor_nodes={"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"})',
        "expected_type": "dict",
        "expected_keys": ["new_penalty"],  # Only check for new_penalty
    },
]

print("\n" + "="*70)
print("Testing action execution...")
print("="*70)

all_passed = True

for i, test in enumerate(test_cases, 1):
    print(f"\n[Test {i}] {test['name']}")

    # Execute action using agent's method
    try:
        result = agent._execute_action_from_text(test['text'])

        # Check if error
        if isinstance(result, dict) and "error" in result:
            print(f"  [FAIL] Execution error: {result['error']}")
            all_passed = False
            continue

        # Check expected keys
        if not isinstance(result, dict):
            print(f"  [FAIL] Result is not a dict: {type(result)}")
            all_passed = False
            continue

        missing_keys = [k for k in test['expected_keys'] if k not in result]
        if missing_keys:
            print(f"  [FAIL] Missing expected keys: {missing_keys}")
            print(f"    Result keys: {list(result.keys())}")
            all_passed = False
            continue

        print(f"  [PASS] Execution successful")
        print(f"    Result keys: {list(result.keys())[:5]}...")
        if "penalty" in result:
            print(f"    Penalty: {result['penalty']}")

    except Exception as e:
        print(f"  [FAIL] Exception during execution: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

print("\n" + "="*70)
if all_passed:
    print("[PASS] ALL TESTS PASSED")
else:
    print("[FAIL] SOME TESTS FAILED")
print("="*70)
