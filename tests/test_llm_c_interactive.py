"""
Interactive test for LLM_C mode with simulated human messages.
Tests the complete flow including classification, handlers, and conversational responses.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.cluster_agent import ClusterAgent
from agents.multi_node_human_agent import MultiNodeHumanAgent
from problems.graph_coloring import GraphColoring
from agents.base_agent import Message
from comm.communication_layer import LLMCommLayer


def create_test_setup():
    """Create a realistic 3-cluster graph problem"""
    # Nodes: Agent1 (a1-a5), Human (h1-h5), Agent2 (b1-b5)
    nodes = ["a1", "a2", "a3", "a4", "a5", "h1", "h2", "h3", "h4", "h5", "b1", "b2", "b3", "b4", "b5"]

    # Edges creating a challenging problem
    edges = [
        # Agent1 - Human boundary
        ("a2", "h1"), ("a4", "h4"), ("a5", "h4"),
        # Human - Agent2 boundary
        ("h2", "b2"), ("h5", "b2"), ("h5", "b5"),
        # Internal edges (within clusters)
        ("a1", "a2"), ("a3", "a4"),
        ("h1", "h2"), ("h3", "h4"), ("h4", "h5"),
        ("b1", "b2"), ("b3", "b4"),
    ]

    domain = ["red", "green", "blue"]

    return GraphColoring(nodes, edges, domain)


def test_interactive_llm_c():
    """Test LLM_C mode with interactive human messages"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"test_output/llm_c_interactive_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    conversation_file = open(os.path.join(output_dir, "conversation.txt"), "w", encoding="utf-8")
    debug_file = open(os.path.join(output_dir, "debug.txt"), "w", encoding="utf-8")

    def log_conversation(speaker, message):
        line = f"[{speaker}] {message}"
        # Handle Unicode encoding issues for console
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode('ascii', 'replace').decode('ascii'))
        conversation_file.write(line + "\n")
        conversation_file.flush()

    def log_debug(message):
        debug_file.write(message + "\n")
        debug_file.flush()

    try:
        # Create problem
        problem = create_test_setup()
        log_conversation("SYSTEM", f"Created problem with {len(problem.nodes)} nodes")

        # Check if API key exists
        api_key_file = "api_key.txt"
        if not os.path.exists(api_key_file):
            log_conversation("SYSTEM", "WARNING: No api_key.txt found - using mock comm layer")
            # Create mock comm layer
            class MockCommLayer:
                def format_content(self, sender, recipient, content):
                    if isinstance(content, dict):
                        data = content.get("data", {})
                        if content.get("type") == "constraints":
                            status = data.get("status")
                            if status == "SUCCESS":
                                return f"✓ Your boundary works! My coloring: {data.get('my_coloring')}"
                            else:
                                configs = data.get("valid_configs", [])
                                return f"✗ Current boundary doesn't work. {len(configs)} alternatives available"
                    return str(content)

                def parse_content(self, sender, recipient, content):
                    return content

            comm_layer = MockCommLayer()
        else:
            # Use real LLM comm layer (it reads api_key.txt automatically)
            llm_trace_file = os.path.join(output_dir, "llm_trace.jsonl")
            comm_layer = LLMCommLayer(use_history=True)
            # Set trace file if possible
            if hasattr(comm_layer, 'llm_trace_file'):
                comm_layer.llm_trace_file = llm_trace_file
            log_conversation("SYSTEM", "Using real LLM comm layer")

        # Create owners
        owners = {}
        for i in range(1, 6):
            owners[f"a{i}"] = "Agent1"
            owners[f"h{i}"] = "Human"
            owners[f"b{i}"] = "Agent2"

        # Create agents
        agent1 = ClusterAgent(
            name="Agent1",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["a1", "a2", "a3", "a4", "a5"],
            owners=owners,
            algorithm="greedy",
            message_type="constraints"  # LLM_C mode
        )

        agent2 = ClusterAgent(
            name="Agent2",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["b1", "b2", "b3", "b4", "b5"],
            owners=owners,
            algorithm="greedy",
            message_type="constraints"  # LLM_C mode
        )

        human = MultiNodeHumanAgent(
            name="Human",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["h1", "h2", "h3", "h4", "h5"],
            owners=owners
        )

        # Set initial assignments
        agent1.assignments = {"a1": "red", "a2": "green", "a3": "blue", "a4": "red", "a5": "green"}
        agent2.assignments = {"b1": "red", "b2": "green", "b3": "blue", "b4": "red", "b5": "green"}
        human.assignments = {"h1": "red", "h2": "green", "h3": "blue", "h4": "red", "h5": "green"}

        log_conversation("SYSTEM", "Initial assignments set")
        log_debug(f"Agent1: {agent1.assignments}")
        log_debug(f"Agent2: {agent2.assignments}")
        log_debug(f"Human: {human.assignments}")

        # Compute initial penalty
        all_assignments = {**agent1.assignments, **agent2.assignments, **human.assignments}
        initial_penalty = problem.evaluate_assignment(all_assignments)
        log_conversation("SYSTEM", f"Initial penalty: {initial_penalty:.2f}")

        # Scenario: Human interacts with Agent2
        log_conversation("SYSTEM", "\n=== Starting interaction with Agent2 ===\n")

        # Agent2 sends initial status
        agent2.neighbour_assignments = {k: v for k, v in human.assignments.items() if k in ["h2", "h5"]}
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))

        # Test 1: Human sends a query
        log_conversation("SYSTEM", "\n--- Test 1: Query ---")
        query = "What configurations can you work with?"
        log_conversation("Human", query)

        msg = Message(sender="Human", recipient="Agent2", content=query)
        agent2.receive(msg)

        # Check classification
        if hasattr(agent2, "_last_message_classification") and agent2._last_message_classification:
            classification = agent2._last_message_classification
            log_debug(f"Classification: {classification.primary} (confidence: {classification.confidence:.2f})")

        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # Test 2: Human states a constraint
        log_conversation("SYSTEM", "\n--- Test 2: Constraint ---")
        constraint = "h2 can never be blue"
        log_conversation("Human", constraint)

        msg = Message(sender="Human", recipient="Agent2", content=constraint)
        agent2.receive(msg)

        if hasattr(agent2, "_last_message_classification") and agent2._last_message_classification:
            classification = agent2._last_message_classification
            log_debug(f"Classification: {classification.primary}")

        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # Test 3: Human expresses a preference
        log_conversation("SYSTEM", "\n--- Test 3: Preference ---")
        preference = "I'd like h2 to be red"
        log_conversation("Human", preference)

        msg = Message(sender="Human", recipient="Agent2", content=preference)
        agent2.receive(msg)

        if hasattr(agent2, "_last_message_classification") and agent2._last_message_classification:
            classification = agent2._last_message_classification
            log_debug(f"Classification: {classification.primary}")

        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # Test 4: Check actual state
        log_conversation("SYSTEM", "\n--- Test 4: Query state ---")
        state_query = "Do you have a good coloring now?"
        log_conversation("Human", state_query)

        msg = Message(sender="Human", recipient="Agent2", content=state_query)
        agent2.receive(msg)

        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # Final state check
        log_conversation("SYSTEM", "\n=== Final State ===")
        final_penalty = problem.evaluate_assignment({**agent1.assignments, **agent2.assignments, **human.assignments})
        log_conversation("SYSTEM", f"Final penalty: {final_penalty:.2f}")
        log_conversation("SYSTEM", f"Agent2 assignments: {agent2.assignments}")
        log_conversation("SYSTEM", f"Agent2 satisfied: {agent2.satisfied}")

        # Check for conflicts
        conflicts = []
        for node in agent2.nodes:
            color = agent2.assignments.get(node)
            for nbr in problem.get_neighbors(node):
                if nbr not in agent2.nodes:
                    nbr_color = agent2.neighbour_assignments.get(nbr)
                    if nbr_color and color and str(nbr_color).lower() == str(color).lower():
                        conflicts.append((node, nbr, color))

        if conflicts:
            log_conversation("SYSTEM", f"CONFLICTS DETECTED: {conflicts}")
        else:
            log_conversation("SYSTEM", "No conflicts detected")

        log_conversation("SYSTEM", f"\nConversation saved to: {output_dir}")

        # Write agent logs to file
        agent1_log_file = os.path.join(output_dir, "agent1_log.txt")
        agent2_log_file = os.path.join(output_dir, "agent2_log.txt")

        with open(agent1_log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(agent1.logs))

        with open(agent2_log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(agent2.logs))

        conversation_file.close()
        debug_file.close()

        return output_dir

    except Exception as e:
        log_conversation("SYSTEM", f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        log_debug(traceback.format_exc())
        conversation_file.close()
        debug_file.close()
        return None


if __name__ == "__main__":
    print("\n" + "="*60)
    print("LLM_C Interactive Test")
    print("="*60 + "\n")

    output_dir = test_interactive_llm_c()

    if output_dir:
        print(f"\n{'='*60}")
        print(f"Test completed successfully!")
        print(f"Results saved to: {output_dir}")
        print(f"{'='*60}\n")
    else:
        print("\nTest failed")
        sys.exit(1)
