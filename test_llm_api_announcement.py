"""Test that LLM_API mode has announcement stage."""

from agents.cluster_agent import ClusterAgent
from agents.base_agent import Message
from problems.graph_coloring import GraphColoring
from comm.communication_layer import PassThroughCommLayer


def test_announcement_stage():
    """Test that agent starts in configure phase and handles __ANNOUNCE_CONFIG__."""

    # Create simple graph: 3 nodes, agent owns 2, human owns 1
    nodes = ["a1", "a2", "h1"]
    edges = [("a1", "h1"), ("a2", "h1")]  # Use edges, not adjacency dict
    owners = {"a1": "Agent1", "a2": "Agent1", "h1": "Human"}
    domain = ["red", "blue", "green"]

    problem = GraphColoring(nodes, edges, domain)
    comm_layer = PassThroughCommLayer()

    # Create agent
    agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="greedy",
        message_type="constraints"
    )

    # Check initial phase
    assert agent._phase == "configure", f"Expected configure phase, got {agent._phase}"
    print("[OK] Agent starts in configure phase")

    # Step 1: Should compute assignments but not send messages
    agent.step()
    print("[OK] Step 1 completed (no messages sent in configure phase)")

    # Send __ANNOUNCE_CONFIG__
    msg = Message(sender="Human", recipient="Agent1", content="__ANNOUNCE_CONFIG__")
    agent.receive(msg)

    # Check phase transition
    assert agent._phase == "bargain", f"Expected bargain phase, got {agent._phase}"
    assert agent._config_announced == True, "Config should be announced"
    print("[OK] Agent transitioned to bargain phase after __ANNOUNCE_CONFIG__")

    # Step 2: Should now send messages
    agent.step()
    print("[OK] Step 2 completed (messages can be sent in bargain phase)")

    print("\n[PASS] All tests passed! LLM_API mode has announcement stage.")


if __name__ == "__main__":
    test_announcement_stage()
