"""Test that agents don't send contradictory messages."""

from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent
from comm.llm_rb_comm_layer import LLMRBCommLayer
from comm.rb_protocol import parse_rb

# Simple 3-cluster graph similar to the actual setup
local_nodes = ['h1', 'h2', 'h3', 'h4', 'h5', 'a1', 'a2', 'a3', 'a4', 'a5', 'b1', 'b2']
edges = [
    # Human cluster
    ('h1', 'h2'), ('h2', 'h3'), ('h3', 'h4'), ('h4', 'h5'),
    # Agent1 cluster
    ('a1', 'a2'), ('a2', 'a3'), ('a3', 'a4'), ('a4', 'a5'),
    # Agent2 cluster
    ('b1', 'b2'),
    # Boundary edges
    ('h1', 'a1'), ('h4', 'a4'),
    ('h2', 'b2'), ('h5', 'b1')
]
domain = ['red', 'green', 'blue']

problem = GraphColoring(local_nodes, edges, domain)

owners = {
    'h1': 'Human', 'h2': 'Human', 'h3': 'Human', 'h4': 'Human', 'h5': 'Human',
    'a1': 'Agent1', 'a2': 'Agent1', 'a3': 'Agent1', 'a4': 'Agent1', 'a5': 'Agent1',
    'b1': 'Agent2', 'b2': 'Agent2'
}

comm = LLMRBCommLayer(manual=True)

# Create Agent2
agent2 = RuleBasedClusterAgent(
    name='Agent2',
    local_nodes=['b1', 'b2'],
    owners=owners,
    problem=problem,
    comm_layer=comm,
    algorithm='greedy',
    initial_assignments={'b1': 'red', 'b2': 'red'}
)

# Set neighbor assignments (Human's local_nodes)
agent2.neighbour_assignments = {'h2': 'blue', 'h5': 'green'}

print("="*70)
print("TESTING CONTRADICTION PREVENTION")
print("="*70)

# Track messages sent
messages_sent = []

# Override send to capture messages
original_send = agent2.send
def capture_send(recipient, msg):
    messages_sent.append((recipient, msg))
    print(f"\n[{agent2.name} -> {recipient}]")
    # Parse and display
    rb_move = parse_rb(msg)
    if rb_move:
        from comm.rb_protocol import pretty_rb
        print(f"  {pretty_rb(rb_move)}")

        # Check for contradictions
        if rb_move.move == "ConditionalOffer" and hasattr(rb_move, 'assignments'):
            for assign in rb_move.assignments:
                if hasattr(assign, 'node') and hasattr(assign, 'colour'):
                    # Check if this contradicts previous messages
                    for prev_recip, prev_msg in messages_sent[:-1]:
                        if prev_recip == recipient:
                            prev_move = parse_rb(prev_msg)
                            if prev_move and hasattr(prev_move, 'assignments'):
                                for prev_assign in prev_move.assignments:
                                    if (hasattr(prev_assign, 'node') and
                                        prev_assign.node == assign.node and
                                        prev_assign.colour != assign.colour):
                                        print(f"\n  [WARNING]  CONTRADICTION DETECTED!")
                                        print(f"  Previously said: {prev_assign.node}={prev_assign.colour}")
                                        print(f"  Now saying: {assign.node}={assign.colour}")
                                        return
    original_send(recipient, msg)

agent2.send = capture_send

# Simulate announce config
print("\nPhase: CONFIGURE -> BARGAIN")
agent2.rb_phase = "bargain"

# Run multiple turns
print("\n" + "="*70)
for turn in range(5):
    print(f"\nTurn {turn + 1}:")
    print("-" * 70)

    # Show current state
    print(f"Current assignments: {agent2.assignments}")
    print(f"Proposed to Human: {agent2.rb_proposed_nodes.get('Human', {})}")

    agent2.step()

    if not messages_sent or len(messages_sent) == turn:
        print("  (no message sent this turn)")

# Check results
print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print(f"Total messages sent: {len(messages_sent)}")

# Check for contradictions
found_contradiction = False
for i, (recip1, msg1) in enumerate(messages_sent):
    move1 = parse_rb(msg1)
    if move1 and hasattr(move1, 'assignments'):
        for assign1 in move1.assignments:
            if hasattr(assign1, 'node') and hasattr(assign1, 'colour'):
                # Check against later messages to same recipient
                for recip2, msg2 in messages_sent[i+1:]:
                    if recip2 == recip1:
                        move2 = parse_rb(msg2)
                        if move2 and hasattr(move2, 'assignments'):
                            for assign2 in move2.assignments:
                                if (hasattr(assign2, 'node') and
                                    assign2.node == assign1.node and
                                    assign2.colour != assign1.colour):
                                    print(f"\n[FAIL] CONTRADICTION FOUND:")
                                    print(f"   Message {i+1}: {assign1.node}={assign1.colour}")
                                    print(f"   Later message: {assign2.node}={assign2.colour}")
                                    found_contradiction = True

if not found_contradiction:
    print("\n[OK] SUCCESS: No contradictions found!")
else:
    print("\n[FAIL] FAILED: Contradictions detected!")

print("\n" + "="*70)
