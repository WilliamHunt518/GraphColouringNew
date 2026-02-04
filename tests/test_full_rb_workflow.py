#!/usr/bin/env python3
"""Test complete RB workflow from start to convergence."""

import sys
import time
from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.communication_layer import PassThroughCommLayer
from agents.base_agent import Message

def main():
    print("=" * 80)
    print("COMPLETE RB WORKFLOW TEST")
    print("=" * 80)

    # Create problem with 3 clusters
    nodes = ['a1', 'a2', 'a3', 'a4', 'a5',  # Agent1
             'h1', 'h2', 'h3', 'h4', 'h5',  # Human
             'b1', 'b2', 'b3', 'b4', 'b5']  # Agent2

    edges = [
        # Agent1 internal
        ('a1', 'a2'), ('a2', 'a3'), ('a3', 'a4'), ('a4', 'a5'),
        # Agent1-Human boundary
        ('a2', 'h1'), ('a3', 'h2'), ('a4', 'h4'), ('a5', 'h5'),
        # Human internal
        ('h1', 'h2'), ('h2', 'h3'), ('h3', 'h4'), ('h4', 'h5'),
        # Human-Agent2 boundary
        ('h2', 'b2'), ('h5', 'b5'),
        # Agent2 internal
        ('b1', 'b2'), ('b2', 'b3'), ('b3', 'b4'), ('b4', 'b5'),
    ]

    domain = ['red', 'green', 'blue']
    owners = {
        'a1': 'Agent1', 'a2': 'Agent1', 'a3': 'Agent1', 'a4': 'Agent1', 'a5': 'Agent1',
        'h1': 'Human', 'h2': 'Human', 'h3': 'Human', 'h4': 'Human', 'h5': 'Human',
        'b1': 'Agent2', 'b2': 'Agent2', 'b3': 'Agent2', 'b4': 'Agent2', 'b5': 'Agent2',
    }

    fixed_nodes = {
        'a1': 'green',
        'h3': 'green',
        'b4': 'green',
    }

    problem = GraphColoring(nodes, edges, domain)
    comm_layer = PassThroughCommLayer()

    # Create agents
    agent1 = RuleBasedClusterAgent(
        name='Agent1',
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=['a1', 'a2', 'a3', 'a4', 'a5'],
        owners=owners,
        algorithm='greedy',
        fixed_local_nodes={'a1': 'green'},
    )

    agent2 = RuleBasedClusterAgent(
        name='Agent2',
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=['b1', 'b2', 'b3', 'b4', 'b5'],
        owners=owners,
        algorithm='greedy',
        fixed_local_nodes={'b4': 'green'},
    )

    print("\n[STEP 1] Created agents")
    print(f"  Agent1 nodes: {agent1.nodes}")
    print(f"  Agent2 nodes: {agent2.nodes}")
    print(f"  Agent1 phase: {agent1.rb_phase}")
    print(f"  Agent2 phase: {agent2.rb_phase}")

    # Human sets their colors (blind announcement)
    human_assignments = {
        'h1': 'red',
        'h2': 'blue',
        'h3': 'green',
        'h4': 'red',
        'h5': 'green',
    }

    print("\n[STEP 2] Human sets colors (blind):")
    for node, color in human_assignments.items():
        print(f"  {node}={color}")

    # Human announces configuration by sending __ANNOUNCE_CONFIG__
    print("\n[STEP 3] Human clicks 'Announce Configuration' button")
    print("  Sending __ANNOUNCE_CONFIG__ to Agent1...")
    msg1 = Message(sender='Human', recipient='Agent1', content='__ANNOUNCE_CONFIG__')
    agent1.receive(msg1)

    print("  Sending __ANNOUNCE_CONFIG__ to Agent2...")
    msg2 = Message(sender='Human', recipient='Agent2', content='__ANNOUNCE_CONFIG__')
    agent2.receive(msg2)

    print(f"\n[STEP 4] Check phase transitions")
    print(f"  Agent1 phase: {agent1.rb_phase} (should be 'bargain')")
    print(f"  Agent2 phase: {agent2.rb_phase} (should be 'bargain')")

    # Check if agents sent configuration announcements
    print(f"\n[STEP 5] Check configuration announcements")
    print(f"  Agent1 sent {len(agent1.sent_messages)} messages")
    print(f"  Agent2 sent {len(agent2.sent_messages)} messages")

    for i, msg in enumerate(agent1.sent_messages):
        print(f"    Agent1 msg {i+1}: {msg.content[:100]}...")

    for i, msg in enumerate(agent2.sent_messages):
        print(f"    Agent2 msg {i+1}: {msg.content[:100]}...")

    # Clear sent messages and simulate agent steps
    agent1.sent_messages = []
    agent2.sent_messages = []

    # Update agents with human's neighbor assignments
    print("\n[STEP 6] Agents observe human's announced colors")
    agent1.neighbour_assignments.update({k: v for k, v in human_assignments.items() if k in ['h1', 'h2', 'h4', 'h5']})
    agent2.neighbour_assignments.update({k: v for k, v in human_assignments.items() if k in ['h2', 'h5']})

    print(f"  Agent1 neighbor_assignments: {agent1.neighbour_assignments}")
    print(f"  Agent2 neighbor_assignments: {agent2.neighbour_assignments}")

    # Agents take next step to generate conditional offers
    print("\n[STEP 7] Agents step() to generate conditional offers")
    agent1.step()
    agent2.step()

    print(f"  Agent1 penalty: {agent1._compute_local_penalty():.3f}")
    print(f"  Agent2 penalty: {agent2._compute_local_penalty():.3f}")
    print(f"  Agent1 sent {len(agent1.sent_messages)} messages")
    print(f"  Agent2 sent {len(agent2.sent_messages)} messages")

    agent1_offers = []
    agent2_offers = []

    for msg in agent1.sent_messages:
        if "ConditionalOffer" in msg.content:
            agent1_offers.append(msg)
            print(f"    Agent1 offer: {msg.content[:150]}...")

    for msg in agent2.sent_messages:
        if "ConditionalOffer" in msg.content:
            agent2_offers.append(msg)
            print(f"    Agent2 offer: {msg.content[:150]}...")

    print(f"\n[STEP 8] Check if agents are satisfied")
    print(f"  Agent1 satisfied: {agent1.satisfied}")
    print(f"  Agent2 satisfied: {agent2.satisfied}")

    if not (agent1.satisfied and agent2.satisfied):
        print("\n[STEP 9] Agents not satisfied - need to accept offers")
        print("  In real workflow, human would:")
        print("    1. Review offers from agents")
        print("    2. Accept compatible offers")
        print("    3. Or reject with impossible conditions")
        print("    4. Or ask feasibility queries")
        print("    5. Continue until all parties satisfied")
    else:
        print("\n[STEP 9] SUCCESS! All agents satisfied")
        print("  Convergence achieved!")

    print("\n" + "=" * 80)
    print("WORKFLOW TEST COMPLETE")
    print("=" * 80)

    return agent1.satisfied and agent2.satisfied

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
