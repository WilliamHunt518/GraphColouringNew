"""Test that agent sends offers when user clicks Pass button."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.rb_protocol import RBMove, Condition, Assignment, format_rb, parse_rb, pretty_rb

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

# Set neighbor colors that create conflicts
agent.neighbour_assignments = {'h1': 'red', 'h4': 'red', 'h5': 'green'}

class Msg:
    def __init__(self, sender, content):
        self.sender, self.content = sender, content

print("=" * 80)
print("TEST: Agent sends ConditionalOffer when user clicks Pass")
print("=" * 80)

# Step 1: Send __ANNOUNCE_CONFIG__
print("\n1. Human sends __ANNOUNCE_CONFIG__")
print("-" * 40)
agent.receive(Msg('Human', '__ANNOUNCE_CONFIG__'))

print(f"Agent phase: {agent.rb_phase}")
print(f"Agent penalty: {agent._compute_local_penalty():.3f}")
print(f"Agent assignments: {agent.assignments}")
print(f"Neighbor beliefs: {agent.neighbour_assignments}")

# Step 2: Agent step (should send config announcement)
print("\n2. Agent responds with config announcement")
print("-" * 40)
agent.sent_messages.clear()
agent.step()

if agent.sent_messages:
    config_msg = agent.sent_messages[-1]
    config_move = parse_rb(config_msg.content)
    print(f"Agent sent: {pretty_rb(config_move)}")
    print(f"Agent rb_proposed_nodes: {agent.rb_proposed_nodes}")

# Step 3: Human clicks PASS (agent should compute new assignments and send update)
print("\n3. Human clicks PASS button")
print("-" * 40)
print(f"Before step():")
print(f"  Assignments: {agent.assignments}")
print(f"  Penalty: {agent._compute_local_penalty():.3f}")
print(f"  rb_proposed_nodes: {agent.rb_proposed_nodes}")

agent.sent_messages.clear()
agent.step()

print(f"\nAfter step():")
print(f"  Assignments: {agent.assignments}")
print(f"  Penalty: {agent._compute_local_penalty():.3f}")
print(f"  Messages sent: {len(agent.sent_messages)}")

if agent.sent_messages:
    for msg in agent.sent_messages:
        move = parse_rb(msg.content)
        if move:
            print(f"\n  SUCCESS! Agent sent: {pretty_rb(move)}")
            if move.move == 'ConditionalOffer':
                assignments = move.assignments if hasattr(move, 'assignments') else []
                print(f"  Assignments: {[(a.node, a.colour) for a in assignments]}")
        else:
            print(f"  Agent sent (unparsed): {msg.content[:200]}")
else:
    print("\n  FAILED - Agent sent NO messages!")
    print("  This means Priority 0 did not trigger.")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
