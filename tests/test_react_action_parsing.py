"""
Test ReAct agent action parsing with dictionary arguments.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.react_cluster_agent import ReActClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.speech_llm_layer import SpeechLLMLayer
import re

print("="*70)
print("TEST: ReAct Action Parsing with Dictionary Arguments")
print("="*70)

# Create simple problem
nodes = ["a1", "a2", "h1", "h2"]
edges = [("a1", "a2"), ("a2", "h2")]
domain = ["red", "blue", "green"]

problem = GraphColoring(nodes, edges, domain, conflict_penalty=10.0)
owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

# Create agent (without OpenAI key - we're just testing parsing)
try:
    agent = ReActClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=SpeechLLMLayer(use_llm=False),
        local_nodes=["a1", "a2"],
        owners=owners
    )
    print(f"\n[OK] Agent created")
except Exception as e:
    print(f"\n[FAIL] Error creating agent: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test cases for action parsing
test_cases = [
    {
        "name": "Simple dict argument",
        "text": 'Action: get_best_response_to(neighbor_assignments={"h1": "red"})',
        "expected_func": "get_best_response_to",
        "expected_args": '{"h1": "red"}',
    },
    {
        "name": "Multiple dict entries",
        "text": 'Action: get_best_response_to(neighbor_assignments={"h1": "red", "h2": "blue"})',
        "expected_func": "get_best_response_to",
        "expected_args": '{"h1": "red", "h2": "blue"}',
    },
    {
        "name": "Dict with 5 entries (typical case)",
        "text": 'Action: get_best_response_to(neighbor_assignments={"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"})',
        "expected_func": "get_best_response_to",
        "expected_args": '{"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"}',
    },
    {
        "name": "simulate_neighbor_change with dict",
        "text": 'Action: simulate_neighbor_change(neighbor_nodes={"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"})',
        "expected_func": "simulate_neighbor_change",
        "expected_args": '{"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"}',
    },
    {
        "name": "No arguments",
        "text": 'Action: get_current_penalty()',
        "expected_func": "get_current_penalty",
        "expected_args": '',
    },
]

print("\n" + "="*70)
print("Testing action parsing...")
print("="*70)

all_passed = True

for i, test in enumerate(test_cases, 1):
    print(f"\n[Test {i}] {test['name']}")
    print(f"  Input: {test['text'][:80]}...")

    # Parse action (replicate the logic from _execute_action_from_text)
    action_start = re.search(r"Action:\s*(\w+)\(", test['text'], re.IGNORECASE)

    if not action_start:
        print(f"  [FAIL] Could not parse action")
        all_passed = False
        continue

    action_name = action_start.group(1)

    # Find matching closing parenthesis by counting
    start_pos = action_start.end()  # Position after opening (
    paren_count = 1
    i = start_pos

    while i < len(test['text']) and paren_count > 0:
        if test['text'][i] == '(':
            paren_count += 1
        elif test['text'][i] == ')':
            paren_count -= 1
        i += 1

    if paren_count != 0:
        print(f"  [FAIL] Unmatched parentheses")
        all_passed = False
        continue

    # Extract args between opening ( and matching closing )
    action_args_str = test['text'][start_pos:i-1]

    # Validate
    if action_name != test['expected_func']:
        print(f"  [FAIL] Function name mismatch")
        print(f"    Expected: {test['expected_func']}")
        print(f"    Got: {action_name}")
        all_passed = False
        continue

    # For dict args, extract just the dict part for comparison
    if '=' in action_args_str:
        # Extract value after =
        key, val = action_args_str.split('=', 1)
        actual_dict_str = val.strip()
    else:
        actual_dict_str = action_args_str.strip()

    expected_dict_str = test['expected_args'].strip()

    # Remove spaces for comparison (JSON formatting may vary)
    actual_normalized = actual_dict_str.replace(' ', '')
    expected_normalized = expected_dict_str.replace(' ', '')

    if actual_normalized != expected_normalized:
        print(f"  [FAIL] Arguments mismatch")
        print(f"    Expected: {test['expected_args']}")
        print(f"    Got: {action_args_str}")
        all_passed = False
        continue

    print(f"  [PASS] Correctly parsed: {action_name}({action_args_str[:50]}...)")

print("\n" + "="*70)
if all_passed:
    print("[PASS] ALL TESTS PASSED")
else:
    print("[FAIL] SOME TESTS FAILED")
print("="*70)
