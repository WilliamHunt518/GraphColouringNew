#!/usr/bin/env python3
"""Test script to verify all RB mode fixes are working."""

import sys
from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from agents.multi_node_human_agent import MultiNodeHumanAgent
from comm.communication_layer import PassThroughCommLayer
from comm.rb_protocol import RBMove

def test_rb_fixes():
    """Test RB mode agent interactions."""
    print("=" * 80)
    print("Testing RB Mode Fixes")
    print("=" * 80)

    # Create problem
    nodes = ['a1', 'a2', 'a3', 'h1', 'h2', 'h3', 'b1', 'b2']
    edges = [
        ('a1', 'a2'), ('a2', 'a3'),  # Agent1 internal
        ('a1', 'h1'), ('a2', 'h2'), ('a3', 'h3'),  # Agent1-Human boundary
        ('h1', 'h2'), ('h2', 'h3'),  # Human internal
        ('h1', 'b1'), ('h2', 'b2'),  # Human-Agent2 boundary
        ('b1', 'b2'),  # Agent2 internal
    ]
    domain = ['red', 'green', 'blue']
    owners = {
        'a1': 'Agent1', 'a2': 'Agent1', 'a3': 'Agent1',
        'h1': 'Human', 'h2': 'Human', 'h3': 'Human',
        'b1': 'Agent2', 'b2': 'Agent2',
    }

    problem = GraphColoring(nodes, edges, domain)
    comm_layer = PassThroughCommLayer()

    # Create agents
    agent1 = RuleBasedClusterAgent(
        name='Agent1',
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=['a1', 'a2', 'a3'],
        owners=owners,
        algorithm='greedy',
        fixed_local_nodes={'a1': 'green'},
    )

    agent2 = RuleBasedClusterAgent(
        name='Agent2',
        problem=problem,
        comm_layer=comm_layer,
        local_nodes=['b1', 'b2'],
        owners=owners,
        algorithm='greedy',
        fixed_local_nodes={'b2': 'green'},
    )

    print("\n[OK] Created agents")
    print(f"  Agent1 nodes: {agent1.nodes}")
    print(f"  Agent2 nodes: {agent2.nodes}")

    # Test Fix #7: Phase transition with __ANNOUNCE_CONFIG__
    print("\n" + "=" * 80)
    print("TEST 1: Phase Transition (__ANNOUNCE_CONFIG__)")
    print("=" * 80)

    from agents.base_agent import Message

    # Send __ANNOUNCE_CONFIG__ to trigger phase transition
    msg = Message(sender='Human', recipient='Agent1', content='__ANNOUNCE_CONFIG__')
    agent1.receive(msg)

    print(f"[OK] Agent1 rb_phase: {agent1.rb_phase}")
    assert agent1.rb_phase == "bargain", f"Agent1 should be in bargain phase, got {agent1.rb_phase}"
    print("[OK] Agent1 transitioned to bargain phase")

    # Check that Agent1 sent configuration announcement
    if agent1.sent_messages:
        config_msg = agent1.sent_messages[0]
        print(f"[OK] Agent1 sent configuration: {config_msg.content[:100]}...")
        assert "[rb:" in config_msg.content, "Should be RB protocol message"
        print("[OK] Configuration uses RB protocol format")

    # Test Fix #5: All conditional offers have penalty≈0
    print("\n" + "=" * 80)
    print("TEST 2: Conditional Offers Have Penalty≈0")
    print("=" * 80)

    # Set neighbor assignments
    agent1.neighbour_assignments = {'h1': 'red', 'h2': 'blue', 'h3': 'green'}

    # Generate conditional offer
    agent1.sent_messages = []
    agent1.step()

    if agent1.sent_messages:
        for msg in agent1.sent_messages:
            if "ConditionalOffer" in msg.content:
                print(f"[OK] Found conditional offer: {msg.content[:150]}...")
                # Check for penalty in reasons
                if "penalty=" in msg.content:
                    import re
                    match = re.search(r'penalty=([0-9.]+)', msg.content)
                    if match:
                        penalty = float(match.group(1))
                        print(f"[OK] Offer penalty: {penalty}")
                        assert penalty <= 0.1, f"Penalty should be ≈0, got {penalty}"
                        print("[OK] Penalty is ≈0 as required")
                break

    # Test Fix #4: Accepted assignments are locked
    print("\n" + "=" * 80)
    print("TEST 3: Accepted Assignments Are Locked")
    print("=" * 80)

    # Create an Accept message
    accept_msg = Message(
        sender='Human',
        recipient='Agent1',
        content='[rb:{"move": "Accept", "offer_id": "test_offer", "assignments": [{"node": "a2", "colour": "red"}]}]'
    )

    # Store offer in agent's tracking
    from comm.rb_protocol import RBMove, Assignment
    test_offer = RBMove(
        move="ConditionalOffer",
        conditions=[],
        assignments=[Assignment(node="a2", colour="red")],
        offer_id="test_offer"
    )
    agent1.rb_active_offers["test_offer"] = test_offer

    agent1.receive(accept_msg)

    # Check if assignment was locked
    if 'a2' in agent1.forced_local_assignments:
        print(f"[OK] Assignment a2={agent1.forced_local_assignments['a2']} is locked")
        assert agent1.forced_local_assignments['a2'] == 'red', "Should lock a2=red"
        print("[OK] Locked assignment matches accepted offer")
    else:
        print("[FAIL] Assignment was not locked!")
        return False

    # Test Fix #1: Satisfied agents don't spam
    print("\n" + "=" * 80)
    print("TEST 4: Satisfied Agents Don't Spam")
    print("=" * 80)

    agent1.satisfied = True
    agent1.sent_messages = []
    agent1.step()

    boundary_updates = [msg for msg in agent1.sent_messages if "boundary_update" in msg.content.lower()]
    print(f"[OK] Sent {len(boundary_updates)} boundary updates while satisfied")

    if len(boundary_updates) == 0:
        print("[OK] No spam - satisfied agent didn't send redundant updates")
    else:
        print("[FAIL] Satisfied agent still sending updates!")
        return False

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED [OK]")
    print("=" * 80)
    return True

if __name__ == "__main__":
    try:
        success = test_rb_fixes()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] TEST FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
