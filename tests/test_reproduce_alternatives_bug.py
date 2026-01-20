"""
Test to reproduce the bug where agent fails to suggest alternatives when told
"h2 cannot be green" after initially suggesting h2=green as the only option.

This simulates the exact scenario from the user's transcript:
1. Set h1=green, h2=red, h3=green(fixed), h4=red, h5=blue
2. Agent2 says it can't work and suggests h2=green
3. Human says "h2 cannot be green"
4. Agent should suggest OTHER alternatives, but instead either:
   - Keeps suggesting h2=green
   - Claims to change internal nodes without helping
   - Doesn't provide actionable alternatives
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


def create_test_problem():
    """Create the exact problem setup from the user's transcript"""
    # 3 clusters: Agent1 (a1-a5), Human (h1-h5), Agent2 (b1-b5)
    nodes = ["a1", "a2", "a3", "a4", "a5", "h1", "h2", "h3", "h4", "h5", "b1", "b2", "b3", "b4", "b5"]

    # Edges - using default problem structure
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


def test_alternatives_bug():
    """Reproduce the exact bug from user's transcript"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"test_output/alternatives_bug_{timestamp}"
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
        # Create problem
        problem = create_test_problem()
        log_conversation("SYSTEM", f"Created problem with {len(problem.nodes)} nodes")

        # Check for API key
        api_key_file = "api_key.txt"
        if not os.path.exists(api_key_file):
            log_conversation("SYSTEM", "ERROR: No api_key.txt found - cannot run test with real LLM")
            return None

        # Use real LLM comm layer
        comm_layer = LLMCommLayer(use_history=True)
        log_conversation("SYSTEM", "Using real LLM comm layer")

        # Create owners
        owners = {}
        for i in range(1, 6):
            owners[f"a{i}"] = "Agent1"
            owners[f"h{i}"] = "Human"
            owners[f"b{i}"] = "Agent2"

        # Fixed nodes (from user's transcript setup)
        fixed_constraints = {
            "h3": "green",  # h3 is fixed
            "a1": "green",  # from validation output
            "a3": "blue",   # from validation output
            "b3": "green",  # from validation output
            "b1": "blue",   # from validation output
        }

        # Create Agent2 (the problematic one)
        agent2 = ClusterAgent(
            name="Agent2",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["b1", "b2", "b3", "b4", "b5"],
            owners=owners,
            algorithm="greedy",
            message_type="constraints",  # LLM_C mode
            fixed_local_nodes={k: v for k, v in fixed_constraints.items() if k in ["b1", "b3"]}
        )

        # Create human
        human = MultiNodeHumanAgent(
            name="Human",
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=["h1", "h2", "h3", "h4", "h5"],
            owners=owners
        )

        # STEP 1: Set human's initial assignments as per user's scenario
        # h1=green, h2=red, h3=green(fixed), h4=red, h5=blue
        human.assignments = {
            "h1": "green",
            "h2": "red",
            "h3": "green",  # fixed
            "h4": "red",
            "h5": "blue"
        }
        log_conversation("SYSTEM", f"Human assignments: {human.assignments}")

        # Set Agent2's boundary beliefs
        agent2.neighbour_assignments = {
            "h2": "red",
            "h5": "blue"
        }

        # STEP 2: Agent2 runs step() to generate initial response
        log_conversation("SYSTEM", "\n=== STEP 2: Agent2 initial response ===")
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # STEP 3: Human says "h2 cannot be green"
        log_conversation("SYSTEM", "\n=== STEP 3: Human states constraint ===")
        constraint_msg = "h2 cannot be green. Are there any other configurations I could assume which would work?"
        log_conversation("Human", constraint_msg)

        msg = Message(sender="Human", recipient="Agent2", content=constraint_msg)
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # STEP 4: Human asks again for clarity
        log_conversation("SYSTEM", "\n=== STEP 4: Human asks for specific options ===")
        query_msg = "What settings could I choose that would work?"
        log_conversation("Human", query_msg)

        msg = Message(sender="Human", recipient="Agent2", content=query_msg)
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # STEP 5: Human points out the issue
        log_conversation("SYSTEM", "\n=== STEP 5: Human frustrated ===")
        frustrated_msg = "So are you saying that my current choices are ones which you can plan a good colouring around? I.e I do not have to change h2 and h5?"
        log_conversation("Human", frustrated_msg)

        msg = Message(sender="Human", recipient="Agent2", content=frustrated_msg)
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # STEP 6: Human offers alternative
        log_conversation("SYSTEM", "\n=== STEP 6: Human offers h2=blue ===")
        offer_msg = "But as I said I cannot make h2 green. I could make it blue?"
        log_conversation("Human", offer_msg)

        msg = Message(sender="Human", recipient="Agent2", content=offer_msg)
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # STEP 7: Human asks directly for alternatives
        log_conversation("SYSTEM", "\n=== STEP 7: Human asks for alternatives AGAIN ===")
        direct_msg = "You haven't proposed any alternatives other than h2=green, which incurs a penalty for me. What OTHER options are there?"
        log_conversation("Human", direct_msg)

        msg = Message(sender="Human", recipient="Agent2", content=direct_msg)
        agent2.receive(msg)
        agent2.step()

        if agent2.sent_messages:
            for msg in agent2.sent_messages:
                if msg.recipient == "Human":
                    log_conversation("Agent2", str(msg.content))
            agent2.sent_messages = []

        # Write agent logs
        with open(agent2_log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(agent2.logs))

        log_conversation("SYSTEM", f"\n=== Test complete ===")
        log_conversation("SYSTEM", f"Conversation saved to: {output_dir}")
        log_conversation("SYSTEM", f"Agent2 logs saved to: {agent2_log_file}")

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
    print("Reproducing Alternatives Bug")
    print("="*60 + "\n")

    output_dir = test_alternatives_bug()

    if output_dir:
        print(f"\n{'='*60}")
        print(f"Test completed!")
        print(f"Results saved to: {output_dir}")
        print(f"{'='*60}\n")
    else:
        print("\nTest failed")
        sys.exit(1)
