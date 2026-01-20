"""
Test to reproduce the REAL bug from docs/tmpChat.pdf:
- Agent2 starts with penalty=20.00 and only suggests 1 option: h2=green, h5=blue
- Human says "h2 cannot be green"
- Agent2 should suggest OTHER boundary options but doesn't
- Instead keeps trying to change its own nodes (which doesn't work)
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


def create_exact_problem_from_pdf():
    """Create the EXACT problem from the PDF with the same fixed constraints"""
    # From validation output in console:
    # Fixed: h3=green, a1=green, a3=blue, b3=green, b1=blue

    nodes = ["a1", "a2", "a3", "a4", "a5", "h1", "h2", "h3", "h4", "h5", "b1", "b2", "b3", "b4", "b5"]

    # Use same edge structure as the real problem
    edges = [
        # Agent1 - Human boundary
        ("a2", "h1"), ("a4", "h4"), ("a5", "h4"),
        # Human - Agent2 boundary
        ("h2", "b2"), ("h5", "b2"), ("h5", "b5"),
        # Internal edges
        ("a1", "a2"), ("a3", "a4"),
        ("h1", "h2"), ("h3", "h4"), ("h4", "h5"),
        ("b1", "b2"), ("b3", "b4"),
    ]

    domain = ["red", "green", "blue"]
    return GraphColoring(nodes, edges, domain)


def test_real_alternatives_bug():
    """Reproduce the EXACT bug from the PDF"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"test_output/real_bug_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    conversation_file = open(os.path.join(output_dir, "conversation.txt"), "w", encoding="utf-8")
    agent2_log_file = os.path.join(output_dir, "agent2_log.txt")

    def log_conversation(speaker, message):
        line = f"[{speaker}] {message}"
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode('ascii', 'replace').decode('ascii'))
        conversation_file.write(line + "\n")
        conversation_file.flush()

    try:
        problem = create_exact_problem_from_pdf()
        log_conversation("SYSTEM", f"Created problem with {len(problem.nodes)} nodes")

        # Check for API key
        api_key_file = "api_key.txt"
        if not os.path.exists(api_key_file):
            log_conversation("SYSTEM", "ERROR: No api_key.txt found")
            return None

        comm_layer = LLMCommLayer(use_history=True)
        log_conversation("SYSTEM", "Using real LLM comm layer")

        owners = {}
        for i in range(1, 6):
            owners[f"a{i}"] = "Agent1"
            owners[f"h{i}"] = "Human"
            owners[f"b{i}"] = "Agent2"

        # Fixed nodes from PDF/console
        fixed_agent2 = {"b1": "blue", "b3": "green"}

        agent2 = ClusterAgent(
            name="Agent2",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["b1", "b2", "b3", "b4", "b5"],
            owners=owners,
            algorithm="greedy",
            message_type="constraints",  # LLM_C mode
            fixed_local_nodes=fixed_agent2,
            counterfactual_utils=True  # Use best-response counterfactuals
        )

        human = MultiNodeHumanAgent(
            name="Human",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["h1", "h2", "h3", "h4", "h5"],
            owners=owners
        )

        # Set human's assignments from PDF: h1=green, h2=red, h3=green, h4=red, h5=blue
        human.assignments = {
            "h1": "green",  # I can see this in the PDF (left side)
            "h2": "red",    # Bottom node, circled red/brown
            "h3": "green",  # Fixed, green
            "h4": "red",    # Right side, red
            "h5": "blue"    # Top, blue
        }
        log_conversation("SYSTEM", f"Human assignments: {human.assignments}")

        # Agent2's boundary beliefs
        agent2.neighbour_assignments = {"h2": "red", "h5": "blue"}

        # STEP 1: Send status update - Agent2 should say it doesn't work
        log_conversation("SYSTEM", "\n=== STEP 1: Initial status update ===")
        log_conversation("You", "(status update)")

        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # Check penalty
        full_assignment = {**human.assignments, **agent2.assignments}
        initial_penalty = problem.evaluate_assignment(full_assignment)
        log_conversation("SYSTEM", f"Actual penalty: {initial_penalty:.2f}")

        # STEP 2: Human says h2 cannot be green
        log_conversation("SYSTEM", "\n=== STEP 2: Human states constraint ===")
        constraint = "H2 cannot ever be green. Any other options?"
        log_conversation("You", constraint)

        msg = Message(sender="Human", recipient="Agent2", content=constraint)
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # STEP 3: Agent says it can change b2 - human approves
        log_conversation("SYSTEM", "\n=== STEP 3: Human approves ===")
        log_conversation("You", "Ok go ahead")

        msg = Message(sender="Human", recipient="Agent2", content="Ok go ahead")
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # STEP 4: Human asks to suggest alternative configs
        log_conversation("SYSTEM", "\n=== STEP 4: Human asks for alternatives ===")
        request = "Suggest some alternative configs then"
        log_conversation("You", request)

        msg = Message(sender="Human", recipient="Agent2", content=request)
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # STEP 5: Human asks explicitly for boundary options
        log_conversation("SYSTEM", "\n=== STEP 5: Human asks explicitly ===")
        explicit = "So what I am asking is, if you cannot fix it on your end, i could change some of my colours, but I need to know how to do that. What options could I pick which you could plan around? Remember that h2 cannot be green"
        log_conversation("You", explicit)

        msg = Message(sender="Human", recipient="Agent2", content=explicit)
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # Final state
        log_conversation("SYSTEM", "\n=== Final State ===")
        final_penalty = problem.evaluate_assignment({**human.assignments, **agent2.assignments})
        log_conversation("SYSTEM", f"Final penalty: {final_penalty:.2f}")
        log_conversation("SYSTEM", f"Agent2 assignments: {agent2.assignments}")

        # Save agent logs
        with open(agent2_log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(agent2.logs))

        log_conversation("SYSTEM", f"\nResults saved to: {output_dir}")

        conversation_file.close()
        return output_dir

    except Exception as e:
        log_conversation("SYSTEM", f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        conversation_file.close()
        return None


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Reproducing REAL Bug from PDF")
    print("="*60 + "\n")

    output_dir = test_real_alternatives_bug()

    if output_dir:
        print(f"\n{'='*60}")
        print(f"Test completed!")
        print(f"Results saved to: {output_dir}")
        print(f"{'='*60}\n")
    else:
        print("\nTest failed")
        sys.exit(1)
