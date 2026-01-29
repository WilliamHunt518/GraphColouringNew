"""Test complete RB workflow: config announcement → offers → responses."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.rb_protocol import RBMove, Condition, Assignment, format_rb, parse_rb, pretty_rb
import time

# Simulate the actual graph from logs
nodes = ['h1', 'h2', 'h3', 'h4', 'h5', 'a1', 'a2', 'a3', 'a4', 'a5']
edges = [
    ('h1', 'h2'), ('h2', 'h3'), ('h3', 'h4'), ('h4', 'h5'), ('h5', 'h1'),
    ('a1', 'a2'), ('a2', 'a3'), ('a3', 'a4'), ('a4', 'a5'), ('a5', 'a1'),
    ('h1', 'a2'), ('h4', 'a4'), ('h5', 'a5'),  # Inter-cluster edges
]
domain = ['red', 'green', 'blue', 'yellow']
problem = GraphColoring(nodes=nodes, edges=edges, domain=domain)

owners = {
    'h1': 'Human', 'h2': 'Human', 'h3': 'Human', 'h4': 'Human', 'h5': 'Human',
    'a1': 'Agent1', 'a2': 'Agent1', 'a3': 'Agent1', 'a4': 'Agent1', 'a5': 'Agent1',
}

class DummyComm:
    def format_content(self, sender, recipient, content):
        return content
    def render_outbound(self, s, c, a=None):
        return c
    def parse_content(self, s, r, c):
        return {'raw': c}

comm = DummyComm()
agent = RuleBasedClusterAgent('Agent1', problem, comm, ['a1', 'a2', 'a3', 'a4', 'a5'], owners,
                              initial_assignments={'a1': 'green', 'a2': 'red', 'a3': 'green', 'a4': 'red', 'a5': 'green'})

class Msg:
    def __init__(self, sender, content):
        self.sender, self.content = sender, content

print("=" * 80)
print("WORKFLOW TEST: Config -> Offer -> Response")
print("=" * 80)

# Step 1: Send __ANNOUNCE_CONFIG__
print("\n1. Human sends __ANNOUNCE_CONFIG__")
print("-" * 40)
agent.receive(Msg('Human', '__ANNOUNCE_CONFIG__'))

print(f"Agent phase: {agent.rb_phase}")
print(f"Agent rb_active_offers: {list(agent.rb_active_offers.keys())}")
print(f"Agent rb_proposed_nodes: {agent.rb_proposed_nodes}")

# Step 2: Agent step (should send config announcement)
print("\n2. Agent responds to config announcement")
print("-" * 40)
agent.sent_messages.clear()
agent.step()

config_msg = None
if agent.sent_messages:
    config_msg = agent.sent_messages[-1]
    config_move = parse_rb(config_msg.content)
    print(f"Agent sent: {config_move.move if config_move else 'unknown'}")
    if config_move and config_move.move == "ConditionalOffer":
        print(f"  Assignments: {[(a.node, a.colour) for a in (config_move.assignments or [])]}")

print(f"Agent rb_proposed_nodes after step: {agent.rb_proposed_nodes}")

# Step 3: Human sends conditional offer
print("\n3. Human sends conditional offer")
print("-" * 40)
human_offer = RBMove(
    'ConditionalOffer',
    offer_id=f'offer_{int(time.time())}_Human',
    conditions=[
        Condition('a2', 'blue', 'Agent1'),
        Condition('a4', 'green', 'Agent1'),
    ],
    assignments=[
        Assignment('h1', 'green'),
        Assignment('h4', 'blue'),
    ],
    reasons=['human_proposal']
)

print(f"Human offers: If a2=blue AND a4=green, then h1=green AND h4=blue")
agent.receive(Msg('Human', format_rb(human_offer)))

print(f"Agent rb_active_offers: {list(agent.rb_active_offers.keys())}")
print(f"Agent rb_proposed_nodes: {agent.rb_proposed_nodes}")

# Step 4: Agent step (should evaluate and respond)
print("\n4. Agent evaluates offer and responds")
print("-" * 40)
agent.sent_messages.clear()

current_penalty = agent._compute_local_penalty()
print(f"Current penalty: {current_penalty:.3f}")

agent.step()

if agent.sent_messages:
    response = agent.sent_messages[-1]
    response_move = parse_rb(response.content)
    print(f"\nAgent response: {response_move.move if response_move else 'unknown'}")
    if response_move:
        print(f"Pretty: {pretty_rb(response_move)}")
        if hasattr(response_move, 'reasons'):
            print(f"Reasons: {response_move.reasons}")
else:
    print("❌ NO RESPONSE - Agent sent nothing!")

print(f"\nAgent rb_proposed_nodes after response: {agent.rb_proposed_nodes}")

# Step 5: Send another offer to test rejection
print("\n5. Human sends BAD offer (should be rejected)")
print("-" * 40)

# Check agent state after accepting
print(f"Agent state after accept:")
print(f"  Assignments: {agent.assignments}")
print(f"  Neighbor beliefs: {agent.neighbour_assignments}")
print(f"  Penalty: {agent._compute_local_penalty():.3f}")
print(f"  Satisfied: {agent.satisfied}")

bad_offer = RBMove(
    'ConditionalOffer',
    offer_id=f'offer_{int(time.time())}_Human',
    conditions=[
        Condition('a2', 'red', 'Agent1'),  # Would conflict with h1
    ],
    assignments=[
        Assignment('h1', 'red'),  # Creates conflict!
    ],
    reasons=['bad_proposal']
)

print(f"\nHuman offers: If a2=red, then h1=red (creates conflict!)")
agent.receive(Msg('Human', format_rb(bad_offer)))

agent.sent_messages.clear()
agent.step()

if agent.sent_messages:
    response = agent.sent_messages[-1]
    response_move = parse_rb(response.content)
    print(f"\nAgent response: {response_move.move if response_move else 'unknown'}")
    if response_move:
        print(f"Pretty: {pretty_rb(response_move)}")
        if hasattr(response_move, 'reasons'):
            print(f"Reasons: {response_move.reasons}")
else:
    print("\nNO RESPONSE - Agent sent nothing!")

print("\n" + "=" * 80)
print("WORKFLOW TEST COMPLETE")
print("=" * 80)
