"""
Automated test suite for message handling and classification.

Tests the message classifier and handler methods without GUI.
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.message_classifier import MessageClassifier, ClassificationResult
from agents.cluster_agent import ClusterAgent
from problems.graph_coloring import GraphColoring


class MessageHandlingTest:
    """Test harness for message classification and handling"""

    def __init__(self, output_dir: str):
        """Initialize test harness with output directory"""
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # Create logs
        self.classification_log = open(os.path.join(output_dir, "classification_log.txt"), "w", encoding="utf-8")
        self.response_log = open(os.path.join(output_dir, "response_log.txt"), "w", encoding="utf-8")
        self.cache_trace = open(os.path.join(output_dir, "cache_trace.txt"), "w", encoding="utf-8")
        self.summary = open(os.path.join(output_dir, "test_summary.txt"), "w", encoding="utf-8")

        self.passed = 0
        self.failed = 0
        self.test_results = []

    def log_classification(self, test_name: str, message: str, result: ClassificationResult):
        """Log classification result"""
        self.classification_log.write(f"\n{'='*60}\n")
        self.classification_log.write(f"Test: {test_name}\n")
        self.classification_log.write(f"Message: {message}\n")
        self.classification_log.write(f"Classification:\n")
        self.classification_log.write(f"  Primary: {result.primary}\n")
        self.classification_log.write(f"  Secondary: {result.secondary}\n")
        self.classification_log.write(f"  Confidence: {result.confidence:.2f}\n")
        self.classification_log.write(f"  Extracted nodes: {result.extracted_nodes}\n")
        self.classification_log.write(f"  Extracted colors: {result.extracted_colors}\n")
        self.classification_log.flush()

    def log_response(self, test_name: str, message: str, handler: str, response: Dict[str, Any]):
        """Log handler response"""
        self.response_log.write(f"\n{'='*60}\n")
        self.response_log.write(f"Test: {test_name}\n")
        self.response_log.write(f"Message: {message}\n")
        self.response_log.write(f"Handler: {handler}\n")
        self.response_log.write(f"Response:\n")
        self.response_log.write(json.dumps(response, indent=2))
        self.response_log.write(f"\n")
        self.response_log.flush()

    def log_cache(self, test_name: str, cache_status: str, details: str):
        """Log cache behavior"""
        self.cache_trace.write(f"[{test_name}] {cache_status}: {details}\n")
        self.cache_trace.flush()

    def assert_equal(self, test_name: str, expected: Any, actual: Any, description: str):
        """Assert equality and log result"""
        if expected == actual:
            self.test_results.append((test_name, "PASS", description))
            self.passed += 1
            print(f"[PASS] {test_name}: {description}")
        else:
            self.test_results.append((test_name, "FAIL", f"{description} (expected={expected}, actual={actual})"))
            self.failed += 1
            print(f"[FAIL] {test_name}: {description} (expected={expected}, actual={actual})")

    def assert_in(self, test_name: str, item: Any, container: Any, description: str):
        """Assert item in container and log result"""
        if item in container:
            self.test_results.append((test_name, "PASS", description))
            self.passed += 1
            print(f"[PASS] {test_name}: {description}")
        else:
            self.test_results.append((test_name, "FAIL", f"{description} ({item} not in {container})"))
            self.failed += 1
            print(f"[FAIL] {test_name}: {description} ({item} not in {container})")

    def finalize(self):
        """Write summary and close logs"""
        self.summary.write(f"Test Summary\n")
        self.summary.write(f"{'='*60}\n")
        self.summary.write(f"Total tests: {self.passed + self.failed}\n")
        self.summary.write(f"Passed: {self.passed}\n")
        self.summary.write(f"Failed: {self.failed}\n")
        self.summary.write(f"\n")

        for test_name, status, description in self.test_results:
            self.summary.write(f"[{status}] {test_name}: {description}\n")

        self.classification_log.close()
        self.response_log.close()
        self.cache_trace.close()
        self.summary.close()

        print(f"\n{'='*60}")
        print(f"Test Summary: {self.passed} passed, {self.failed} failed")
        print(f"Results saved to: {self.output_dir}")


def test_message_classification():
    """Test message classification"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"test_output/message_handling_{timestamp}"
    test = MessageHandlingTest(output_dir)

    print("\n=== Testing Message Classification ===\n")

    # Create classifier (no LLM for testing, uses heuristic fallback)
    classifier = MessageClassifier(llm_call_function=None)

    # Test 1: Query classification
    message = "What color is b2?"
    result = classifier.classify_message(message)
    test.log_classification("test_query_1", message, result)
    test.assert_equal("test_query_1", "QUERY", result.primary, "Should classify as QUERY")
    test.assert_in("test_query_1", "b2", result.extracted_nodes, "Should extract node b2")

    # Test 2: Preference classification
    message = "I'd like h1 to be red"
    result = classifier.classify_message(message)
    test.log_classification("test_preference_1", message, result)
    test.assert_equal("test_preference_1", "PREFERENCE", result.primary, "Should classify as PREFERENCE")
    test.assert_in("test_preference_1", "h1", result.extracted_nodes, "Should extract node h1")
    test.assert_in("test_preference_1", "red", result.extracted_colors, "Should extract color red")

    # Test 3: Command classification
    message = "Change b2 to green"
    result = classifier.classify_message(message)
    test.log_classification("test_command_1", message, result)
    test.assert_equal("test_command_1", "COMMAND", result.primary, "Should classify as COMMAND")
    test.assert_in("test_command_1", "b2", result.extracted_nodes, "Should extract node b2")
    test.assert_in("test_command_1", "green", result.extracted_colors, "Should extract color green")

    # Test 4: Information classification
    message = "h1 can never be green"
    result = classifier.classify_message(message)
    test.log_classification("test_information_1", message, result)
    test.assert_equal("test_information_1", "INFORMATION", result.primary, "Should classify as INFORMATION")
    test.assert_in("test_information_1", "h1", result.extracted_nodes, "Should extract node h1")
    test.assert_in("test_information_1", "green", result.extracted_colors, "Should extract color green")

    # Test 5: Mixed classification
    message = "I'd like h1=red. Can you work with that?"
    result = classifier.classify_message(message)
    test.log_classification("test_mixed_1", message, result)
    # Heuristic classifier may classify as either PREFERENCE or QUERY (both valid)
    test.assert_in("test_mixed_1", result.primary, ["PREFERENCE", "QUERY"], "Should classify as PREFERENCE or QUERY")

    test.finalize()
    return test.passed, test.failed


def test_handler_integration():
    """Test handler methods (basic integration without full simulation)"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"test_output/handler_integration_{timestamp}"
    test = MessageHandlingTest(output_dir)

    print("\n=== Testing Handler Integration ===\n")

    # Create a minimal problem and agent
    try:
        # Create simple 3-coloring problem
        from problems.graph_coloring import GraphColoring

        nodes = ["a1", "a2", "h1", "h2"]
        edges = [("a1", "h1"), ("a2", "h2"), ("h1", "h2")]
        domain = ["red", "green", "blue"]

        problem = GraphColoring(nodes, edges, domain)

        # Create minimal comm layer (no LLM)
        class MockCommLayer:
            def format_content(self, sender, recipient, content):
                return str(content)

            def parse_content(self, sender, recipient, content):
                return content

        comm_layer = MockCommLayer()

        # Create agent with local nodes a1, a2
        local_nodes = ["a1", "a2"]
        owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human", "h2": "Human"}

        agent = ClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=local_nodes,
            owners=owners,
            algorithm="greedy",
            message_type="cost_list"
        )

        # Set initial assignments
        agent.assignments = {"a1": "red", "a2": "green"}
        agent.neighbour_assignments = {"h1": "red", "h2": "blue"}

        # Test query handler
        print("Testing query handler...")
        classifier = MessageClassifier(llm_call_function=None)
        message = "Can you work with h1=red?"
        classification = classifier.classify_message(message)
        test.log_classification("handler_query", message, classification)

        try:
            response = agent._handle_query(classification)
            test.log_response("handler_query", message, "query_handler", response)
            test.assert_in("handler_query", "query_type", response, "Response should have query_type")
            print(f"Query handler response: {response}")
        except Exception as e:
            test.test_results.append(("handler_query", "FAIL", f"Exception: {e}"))
            test.failed += 1
            print(f"✗ Query handler failed: {e}")

        # Test preference handler
        print("Testing preference handler...")
        message = "I'd like h1 to be green"
        classification = classifier.classify_message(message)
        test.log_classification("handler_preference", message, classification)

        try:
            response = agent._handle_preference(classification)
            test.log_response("handler_preference", message, "preference_handler", response)
            test.assert_in("handler_preference", "preference_type", response, "Response should have preference_type")
            print(f"Preference handler response: {response}")
        except Exception as e:
            test.test_results.append(("handler_preference", "FAIL", f"Exception: {e}"))
            test.failed += 1
            print(f"✗ Preference handler failed: {e}")

        # Test information handler
        print("Testing information handler...")
        message = "h1 can never be green"
        classification = classifier.classify_message(message)
        test.log_classification("handler_information", message, classification)

        try:
            response = agent._handle_information(classification)
            test.log_response("handler_information", message, "information_handler", response)
            test.assert_in("handler_information", "info_type", response, "Response should have info_type")
            print(f"Information handler response: {response}")
        except Exception as e:
            test.test_results.append(("handler_information", "FAIL", f"Exception: {e}"))
            test.failed += 1
            print(f"✗ Information handler failed: {e}")

        # Test command handler
        print("Testing command handler...")
        message = "Change a1 to blue"
        classification = classifier.classify_message(message)
        test.log_classification("handler_command", message, classification)

        try:
            response = agent._handle_command(classification)
            test.log_response("handler_command", message, "command_handler", response)
            test.assert_in("handler_command", "command_type", response, "Response should have command_type")
            print(f"Command handler response: {response}")
        except Exception as e:
            test.test_results.append(("handler_command", "FAIL", f"Exception: {e}"))
            test.failed += 1
            print(f"✗ Command handler failed: {e}")

        # Test cache behavior
        print("Testing cache behavior...")
        test.log_cache("cache_test", "INIT", "Testing counterfactual caching")

        # Cache some data
        cache_data = {
            "options": [
                {"boundary_config": {"h1": "red", "h2": "blue"}, "penalty": 0.0, "agent_score": 5},
                {"boundary_config": {"h1": "green", "h2": "blue"}, "penalty": 0.0, "agent_score": 4},
            ]
        }
        agent._cache_counterfactuals(cache_data)
        test.log_cache("cache_test", "CACHED", f"Stored {len(cache_data['options'])} options")

        # Retrieve cached data
        cached = agent._get_cached_counterfactuals()
        if cached and "options" in cached:
            test.assert_equal("cache_retrieve", len(cache_data["options"]), len(cached["options"]), "Cache should return same number of options")
            test.log_cache("cache_test", "RETRIEVED", f"Got {len(cached['options'])} options from cache")
        else:
            test.test_results.append(("cache_retrieve", "FAIL", "Failed to retrieve cached data"))
            test.failed += 1
            test.log_cache("cache_test", "FAILED", "Could not retrieve cached data")

        # Test cache invalidation
        agent.neighbour_assignments["h1"] = "blue"  # Change boundary state
        cached_after_change = agent._get_cached_counterfactuals()
        if cached_after_change is None:
            test.assert_equal("cache_invalidate", None, cached_after_change, "Cache should be invalidated after boundary change")
            test.log_cache("cache_test", "INVALIDATED", "Cache cleared after boundary change")
        else:
            test.test_results.append(("cache_invalidate", "FAIL", "Cache not invalidated after boundary change"))
            test.failed += 1
            test.log_cache("cache_test", "FAILED", "Cache should have been invalidated")

    except Exception as e:
        print(f"Failed to set up handler test: {e}")
        import traceback
        traceback.print_exc()
        test.test_results.append(("handler_setup", "FAIL", f"Setup exception: {e}"))
        test.failed += 1

    test.finalize()
    return test.passed, test.failed


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Message Handling Test Suite")
    print("="*60)

    total_passed = 0
    total_failed = 0

    # Run classification tests
    passed, failed = test_message_classification()
    total_passed += passed
    total_failed += failed

    # Run handler integration tests
    passed, failed = test_handler_integration()
    total_passed += passed
    total_failed += failed

    # Final summary
    print("\n" + "="*60)
    print(f"Overall Results: {total_passed} passed, {total_failed} failed")
    print("="*60)

    sys.exit(0 if total_failed == 0 else 1)
