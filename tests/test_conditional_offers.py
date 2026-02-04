"""Test that agents generate conditional offers when there are conflicts."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.rb_protocol import format_rb, parse_rb, pretty_rb

# Simulate the actual graph
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

# Set neighbor colors that create conflicts
agent.neighbour_assignments = {'h1': 'red', 'h4': 'red', 'h5': 'green'}

class Msg:
    def __init__(self, sender, content):
        self.sender, self.content = sender, content

print("=" * 80)
print("TEST: Agent generates conditional offers when conflicts exist")
print("=" * 80)

# Step 1: __ANNOUNCE_CONFIG__
print("\n1. Send __ANNOUNCE_CONFIG__")
agent.receive(Msg('Human', '__ANNOUNCE_CONFIG__'))
agent.step()
print(f"   Penalty: {agent._compute_local_penalty():.3f}")
print(f"   rb_proposed_nodes: {agent.rb_proposed_nodes}")

# Step 2: First Pass - should send boundary update
print("\n2. Pass #1 - Should send boundary update")
agent.sent_messages.clear()
agent.step()
msg1 = agent.sent_messages[0] if agent.sent_messages else None
if msg1:
    move1 = parse_rb(msg1.content)
    print(f"   Sent: {move1.move}")
    if hasattr(move1, 'reasons'):
        print(f"   Reasons: {move1.reasons}")
    if hasattr(move1, 'conditions'):
        print(f"   Conditions: {len(move1.conditions) if move1.conditions else 0}")
print(f"   Penalty: {agent._compute_local_penalty():.3f}")
print(f"   rb_proposed_nodes: {agent.rb_proposed_nodes}")

# Step 3: Second Pass - should try conditional offer (Priority 2 or 4)
print("\n3. Pass #2 - Should generate conditional offer if conflicts remain")
agent.sent_messages.clear()
agent.step()
msg2 = agent.sent_messages[0] if agent.sent_messages else None

if msg2:
    move2 = parse_rb(msg2.content)
    print(f"   Sent: {move2.move}")
    if hasattr(move2, 'reasons'):
        print(f"   Reasons: {move2.reasons}")
    if hasattr(move2, 'conditions') and move2.conditions:
        print(f"   Conditions ({len(move2.conditions)}):")
        for cond in move2.conditions:
            print(f"     IF {cond.node}={cond.colour}")
    else:
        print(f"   Conditions: 0")
    if hasattr(move2, 'assignments') and move2.assignments:
        print(f"   Assignments ({len(move2.assignments)}):")
        for assign in move2.assignments:
            print(f"     THEN {assign.node}={assign.colour}")

    if move2.conditions and len(move2.conditions) > 0:
        print("\n   ✓ SUCCESS - Agent generated conditional offer with IF conditions!")
    else:
        print("\n   ✗ FAILED - Agent sent another status update instead of conditional offer")
else:
    print("   ✗ FAILED - Agent sent nothing")

print(f"\n   Final penalty: {agent._compute_local_penalty():.3f}")
print(f"   rb_active_offers: {list(agent.rb_active_offers.keys())}")

print("\n" + "=" * 80)
