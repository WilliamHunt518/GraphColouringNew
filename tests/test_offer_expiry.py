"""Test offer expiry mechanism to prevent agent deadlock.

This test verifies that Agent2 doesn't get stuck when the human doesn't
respond to its offers. After 5 iterations, the offer should expire and
the agent should be able to generate new offers.
"""

import sys
import time
from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from agents.base_agent import Message
from comm.communication_layer import PassThroughCommLayer


def test_offer_expiry():
    """Test that unanswered offers expire and don't block new offers."""

    print("=" * 70)
    print("Testing Offer Expiry Mechanism")
    print("=" * 70)

    # Create a simple 3-cluster graph with conflicts
    edges = [
        ("h1", "h2"), ("h2", "h3"), ("h3", "h4"), ("h4", "h5"),  # Human cluster internal
        ("a1", "a2"), ("a2", "a3"),  # Agent1 cluster internal
        ("b1", "b2"), ("b2", "b3"),  # Agent2 cluster internal
        ("h1", "a2"), ("h4", "a4"),  # Human-Agent1 boundary
        ("h2", "b2"), ("h5", "b5"),  # Human-Agent2 boundary
        ("b2", "b3"), ("b3", "b4"), ("b4", "b5"),  # More internal edges to create conflicts
    ]

    # Set initial conflicting colors for human nodes
    initial_human_colors = {"h2": "red", "h5": "red"}

    nodes = ["h1", "h2", "h3", "h4", "h5", "a1", "a2", "a3", "a4", "a5", "b1", "b2", "b3", "b4", "b5"]
    colors = ["red", "green", "blue"]

    problem = GraphColoring(nodes=nodes, edges=edges, domain=colors)

    owners = {
        "h1": "Human", "h2": "Human", "h3": "Human", "h4": "Human", "h5": "Human",
        "a1": "Agent1", "a2": "Agent1", "a3": "Agent1", "a4": "Agent1", "a5": "Agent1",
        "b1": "Agent2", "b2": "Agent2", "b3": "Agent2", "b4": "Agent2", "b5": "Agent2",
    }

    # Create Agent2 with RB protocol
    comm_layer = PassThroughCommLayer()
    agent2 = RuleBasedClusterAgent(
        name="Agent2",
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=["b1", "b2", "b3", "b4", "b5"],
        owners=owners,
        algorithm="greedy"
    )

    # Set neighbour assignments to create conflicts
    agent2.neighbour_assignments = initial_human_colors

    print(f"\nAgent2 initial state:")
    print(f"  Nodes: {agent2.nodes}")
    print(f"  Initial assignments: {agent2.assignments}")
    print(f"  Known neighbour colors: {agent2.neighbour_assignments}")
    print(f"  Initial penalty: {agent2._compute_local_penalty():.3f}")
    print(f"  Phase: {agent2.rb_phase}")

    # Transition to bargain phase
    print("\n" + "-" * 70)
    print("Step 1: Transition to BARGAIN phase")
    print("-" * 70)

    # Simulate receiving __ANNOUNCE_CONFIG__ from human
    config_msg = Message(sender="Human", recipient="Agent2", content="__ANNOUNCE_CONFIG__")
    agent2.receive(config_msg)

    print(f"  Phase after transition: {agent2.rb_phase}")
    print(f"  Iteration counter: {agent2.rb_iteration_counter}")

    # Run a few steps to generate offers
    print("\n" + "-" * 70)
    print("Steps 2-7: Agent generates offers (human doesn't respond)")
    print("-" * 70)

    for i in range(1, 7):
        print(f"\n--- Iteration {i} ---")
        agent2.step()

        # Check active offers
        active_offers = [oid for oid in agent2.rb_active_offers.keys()
                        if oid not in agent2.rb_accepted_offers
                        and oid not in agent2.rb_rejected_offers
                        and "Agent2" in oid
                        and not oid.startswith("update_")
                        and not oid.startswith("config_")]

        print(f"  Iteration counter: {agent2.rb_iteration_counter}")
        print(f"  Active offers from Agent2: {len(active_offers)}")
        if active_offers:
            for oid in active_offers:
                offer_iter = agent2.rb_offer_iteration.get(oid, 0)
                age = agent2.rb_iteration_counter - offer_iter
                print(f"    • {oid} (age: {age} iterations)")

        print(f"  Penalty: {agent2._compute_local_penalty():.3f}")
        print(f"  Satisfied: {agent2.satisfied}")

        # Simulate human making some changes (but not responding to offers)
        if i == 3:
            print("  [Human changes h2 to blue, h5 to red]")
            agent2.neighbour_assignments["h2"] = "blue"
            agent2.neighbour_assignments["h5"] = "red"

    # Check final state
    print("\n" + "=" * 70)
    print("Final Check")
    print("=" * 70)

    active_offers = [oid for oid in agent2.rb_active_offers.keys()
                    if oid not in agent2.rb_accepted_offers
                    and oid not in agent2.rb_rejected_offers
                    and "Agent2" in oid
                    and not oid.startswith("update_")
                    and not oid.startswith("config_")]

    print(f"\nActive offers from Agent2: {len(active_offers)}")
    if active_offers:
        print("  [FAIL] Offers should have expired!")
        for oid in active_offers:
            offer_iter = agent2.rb_offer_iteration.get(oid, 0)
            age = agent2.rb_iteration_counter - offer_iter
            print(f"    - {oid} (age: {age} iterations)")
        return False
    else:
        print("  [PASS] Old offers have been expired successfully!")
        print("  Agent2 can now generate new offers without being blocked.")

    print(f"\nExpired/Rejected offers: {len(agent2.rb_rejected_offers)}")
    print(f"Iteration counter: {agent2.rb_iteration_counter}")

    return True


if __name__ == "__main__":
    success = test_offer_expiry()
    sys.exit(0 if success else 1)
