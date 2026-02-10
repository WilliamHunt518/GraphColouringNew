"""Test script for LLM_RB translation improvements.

This script tests the enhanced natural language → RB grammar translation
to ensure all RB UI functionality is accessible via natural language.
"""

from comm.llm_rb_comm_layer import LLMRBCommLayer
from comm.rb_protocol import RBMove, parse_rb, pretty_rb
import json


def test_translation(text: str, expected_move_type: str, description: str):
    """Test a single translation case."""
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"{'='*70}")
    print(f"Input: \"{text}\"")

    # Create a comm layer in manual mode (no LLM, use heuristics only)
    comm = LLMRBCommLayer(manual=True)

    # Parse the text
    result = comm.parse_content(sender="Human", recipient="Agent1", message=text)

    print(f"\nParsed move type: {result.move if result else 'None'}")
    print(f"Expected move type: {expected_move_type}")

    if result:
        print(f"\nFull parsed structure:")
        print(f"  {pretty_rb(result)}")
        print(f"\nJSON representation:")
        print(f"  {json.dumps(result.to_dict(), indent=2)}")

        # Verify move type
        if result.move == expected_move_type:
            print(f"\nPASS PASS: Move type matches")
            return True
        else:
            print(f"\nFAIL FAIL: Move type mismatch")
            return False
    else:
        print(f"\nFAIL FAIL: Parsing returned None")
        return False


def main():
    """Run all test cases."""
    print("="*70)
    print("LLM_RB TRANSLATION TESTS")
    print("="*70)
    print("\nTesting heuristic parser (manual mode, no LLM)")

    tests = [
        # Simple rejections
        ("h4 cannot be green", "Reject", "Simple rejection (impossible condition)"),
        ("I can't do h5=red", "Reject", "Simple rejection with assignment syntax"),

        # Conditional rejections (impossible combinations)
        ("h4 can't be green when h1 is red", "Reject", "Conditional rejection (when)"),
        ("I can't use h2=blue and h3=red together", "Reject", "Conditional rejection (together)"),

        # Feasibility queries
        ("Would h2=blue work for you?", "FeasibilityQuery", "Single condition feasibility query"),
        ("Would h2=blue and h3=red work?", "FeasibilityQuery", "Multi-condition feasibility query"),

        # Conditional offers
        ("If you do h1=red, I can do a3=green", "ConditionalOffer", "Simple conditional offer"),

        # Proposals
        ("What if I set h4 to red?", "Propose", "Simple proposal"),

        # Accepts
        ("That works for me", "Accept", "Accept proposal"),

        # Counter-proposals
        ("Could you try h1=green instead?", "CounterProposal", "Counter-proposal"),
    ]

    results = []
    for text, expected_type, description in tests:
        passed = test_translation(text, expected_type, description)
        results.append((description, passed))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    total = len(results)
    passed = sum(1 for _, p in results if p)

    for desc, p in results:
        status = "PASS PASS" if p else "FAIL FAIL"
        print(f"{status}: {desc}")

    print(f"\nTotal: {passed}/{total} tests passed ({100*passed//total}%)")

    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed")
        return 1


def test_specific_case():
    """Test a specific case with detailed output for debugging."""
    print("\nDETAILED TEST: Conditional rejection")
    print("="*70)

    text = "h4 can't be green when h1 is red"

    comm = LLMRBCommLayer(manual=True)
    result = comm._heuristic_nl_to_rbmove(text)

    print(f"Input: \"{text}\"")
    print(f"\nParsed result: {result}")

    if result:
        print(f"\nMove type: {result.move}")
        print(f"Impossible conditions: {getattr(result, 'impossible_conditions', None)}")
        print(f"Impossible combinations: {getattr(result, 'impossible_combinations', None)}")

        # Check if it has the right structure
        if hasattr(result, 'impossible_combinations') and result.impossible_combinations:
            print(f"\nPASS Has impossible_combinations field")
            combo = result.impossible_combinations[0]
            print(f"  Combination: {combo}")

            # Verify it contains both h4=green and h1=red
            nodes_colors = [(item['node'], item['colour']) for item in combo]
            print(f"  Node-color pairs: {nodes_colors}")

            if ('h4', 'green') in nodes_colors and ('h1', 'red') in nodes_colors:
                print(f"\nPASS Contains both h4=green and h1=red")
            else:
                print(f"\nFAIL Missing expected node-color pairs")
        else:
            print(f"\nFAIL Missing impossible_combinations field")
    else:
        print(f"\nFAIL Parsing failed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        test_specific_case()
    else:
        exit_code = main()
        sys.exit(exit_code)
