"""
Full simulation test with scripted human inputs (headless/terminal only).

Tests the complete message flow from classification to response generation.
"""

import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.cluster_agent import ClusterAgent
from agents.multi_node_human_agent import MultiNodeHumanAgent
from problems.graph_coloring import GraphColoring
from agents.base_agent import Message


def create_test_problem():
    """Create a simple 3-cluster graph coloring problem"""
    # Nodes: Agent1 (a1, a2), Human (h1, h2), Agent2 (a3, a4)
    nodes = ["a1", "a2", "h1", "h2", "a3", "a4"]

    # Edges: connecting clusters
    edges = [
        ("a1", "h1"),  # Agent1 - Human boundary
        ("a2", "h2"),  # Agent1 - Human boundary
        ("h1", "a3"),  # Human - Agent2 boundary
        ("h2", "a4"),  # Human - Agent2 boundary
    ]

    domain = ["red", "green", "blue"]

    return GraphColoring(nodes, edges, domain)


def test_basic_simulation():
    """Test basic simulation with message exchange"""
    print("\n" + "="*60)
    print("Full Simulation Test: Basic Message Exchange")
    print("="*60 + "\n")

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"test_output/simulation_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    log_file = open(os.path.join(output_dir, "simulation_log.txt"), "w", encoding="utf-8")

    def log(message):
        print(message)
        log_file.write(message + "\n")
        log_file.flush()

    try:
        # Create problem
        problem = create_test_problem()
        log("Created graph coloring problem with 6 nodes and 4 edges")

        # Create mock comm layer
        class MockCommLayer:
            def format_content(self, sender, recipient, content):
                return str(content)

            def parse_content(self, sender, recipient, content):
                return content

        comm_layer = MockCommLayer()

        # Create owners mapping
        owners = {
            "a1": "Agent1",
            "a2": "Agent1",
            "h1": "Human",
            "h2": "Human",
            "a3": "Agent2",
            "a4": "Agent2"
        }

        # Create agents
        agent1 = ClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2"],
            owners=owners,
            algorithm="greedy",
            message_type="cost_list"
        )

        human = MultiNodeHumanAgent(
            name="Human",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["h1", "h2"],
            owners=owners
        )

        agent2 = ClusterAgent(
            name="Agent2",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a3", "a4"],
            owners=owners,
            algorithm="greedy",
            message_type="cost_list"
        )

        log("\nCreated 3 agents: Agent1, Human, Agent2")

        # Set initial assignments
        agent1.assignments = {"a1": "red", "a2": "green"}
        human.assignments = {"h1": "blue", "h2": "red"}
        agent2.assignments = {"a3": "green", "a4": "blue"}

        log("\nInitial assignments:")
        log(f"  Agent1: {agent1.assignments}")
        log(f"  Human: {human.assignments}")
        log(f"  Agent2: {agent2.assignments}")

        # Scenario 1: Human sends preference message to Agent1
        log("\n" + "-"*60)
        log("Scenario 1: Human sends preference to Agent1")
        log("-"*60)

        preference_message = "I'd like h1 to be red"
        log(f"\nHuman says: '{preference_message}'")

        # Simulate message sending
        msg = Message(sender="Human", recipient="Agent1", content=preference_message)
        agent1.receive(msg)

        log(f"\nAgent1 received message and classified it")
        if hasattr(agent1, "_last_message_classification") and agent1._last_message_classification:
            classification = agent1._last_message_classification
            log(f"  Classification: {classification.primary} (confidence: {classification.confidence:.2f})")
            log(f"  Extracted nodes: {classification.extracted_nodes}")
            log(f"  Extracted colors: {classification.extracted_colors}")

        # Agent1 processes and responds
        log("\nAgent1 processing...")
        agent1.step()

        # Check if cache was populated
        cached = agent1._get_cached_counterfactuals()
        if cached:
            log(f"  Counterfactuals cached: {len(cached.get('options', []))} options")
        else:
            log("  No counterfactuals cached")

        # Scenario 2: Human sends query to Agent1
        log("\n" + "-"*60)
        log("Scenario 2: Human sends query to Agent1")
        log("-"*60)

        query_message = "What are my options?"
        log(f"\nHuman says: '{query_message}'")

        msg = Message(sender="Human", recipient="Agent1", content=query_message)
        agent1.receive(msg)

        if hasattr(agent1, "_last_message_classification") and agent1._last_message_classification:
            classification = agent1._last_message_classification
            log(f"  Classification: {classification.primary}")

        # Scenario 3: Human sends information to Agent1
        log("\n" + "-"*60)
        log("Scenario 3: Human sends constraint information to Agent1")
        log("-"*60)

        info_message = "h1 can never be green"
        log(f"\nHuman says: '{info_message}'")

        msg = Message(sender="Human", recipient="Agent1", content=info_message)
        agent1.receive(msg)

        if hasattr(agent1, "_last_message_classification") and agent1._last_message_classification:
            classification = agent1._last_message_classification
            log(f"  Classification: {classification.primary}")

        # Check if constraint was stored
        if hasattr(agent1, "_human_stated_constraints"):
            log(f"  Stored constraints: {agent1._human_stated_constraints}")

        # Scenario 4: Human sends command to Agent1
        log("\n" + "-"*60)
        log("Scenario 4: Human sends command to Agent1")
        log("-"*60)

        command_message = "Change a1 to blue"
        log(f"\nHuman says: '{command_message}'")

        msg = Message(sender="Human", recipient="Agent1", content=command_message)
        agent1.receive(msg)

        if hasattr(agent1, "_last_message_classification") and agent1._last_message_classification:
            classification = agent1._last_message_classification
            log(f"  Classification: {classification.primary}")

        # Check if forced assignment was stored
        if hasattr(agent1, "forced_local_assignments"):
            log(f"  Forced assignments: {agent1.forced_local_assignments}")

        # Final summary
        log("\n" + "="*60)
        log("Simulation Complete")
        log("="*60)

        log("\nFinal state:")
        log(f"  Agent1 assignments: {agent1.assignments}")
        log(f"  Agent1 satisfied: {agent1.satisfied}")
        log(f"  Cache state: {'Populated' if agent1._get_cached_counterfactuals() else 'Empty'}")

        log(f"\nResults saved to: {output_dir}")

        log_file.close()

        print("\n[PASS] Simulation completed successfully")
        return 0

    except Exception as e:
        log(f"\n[FAIL] Simulation failed with exception: {e}")
        import traceback
        traceback.print_exc()
        log_file.write("\n" + traceback.format_exc())
        log_file.close()
        return 1


if __name__ == "__main__":
    exit_code = test_basic_simulation()
    sys.exit(exit_code)
