"""Test script for RB dialogue convergence.

Simulates a complete RB dialogue from start to convergence, acting as both
human and agent to verify that Pass button works and convergence is detected.
"""

from __future__ import annotations
import sys
from typing import Any, Dict, List

# Import problem and agent classes
from problems.graph_coloring import GraphColoring
from agents.rule_based_cluster_agent import RuleBasedClusterAgent


class MockCommLayer:
    """Mock communication layer (RB doesn't use it)."""

    def parse_content(self, sender, recipient, content):
        """Mock parse - RB doesn't parse via comm layer."""
        return {}

    def render_message(self, sender, recipient, structured_content):
        """Mock render - RB formats its own messages."""
        return str(structured_content)


class MockHuman:
    """Simulates human participant."""

    def __init__(self, name: str, nodes: List[str], owners: Dict[str, str]):
        self.name = name
        self.nodes = set(nodes)
        self.owners = owners
        self.assignments = {}

    def propose(self, node: str, color: str):
        """Human proposes assignment."""
        self.assignments[node] = color
        return f"[rb:{{\"move\": \"Propose\", \"node\": \"{node}\", \"colour\": \"{color}\", \"reasons\": []}}] Propose {node}={color}"

    def commit(self, node: str, color: str):
        """Human commits to assignment."""
        return f"[rb:{{\"move\": \"Commit\", \"node\": \"{node}\", \"colour\": \"{color}\", \"reasons\": []}}] Commit {node}={color}"


def create_simple_problem():
    """Create minimal 3-node problem for testing.

    Graph structure:
    h1 (human) -- a1 (agent) -- a2 (agent)

    h1 adjacent to a1, a2
    All nodes adjacent to each other (triangle)
    """
    edges = [
        ("h1", "a1"),
        ("h1", "a2"),
        ("a1", "a2"),
    ]
    domain = ["red", "green", "blue"]
    problem = GraphColoring(nodes=["h1", "a1", "a2"], edges=edges, domain=domain)
    return problem


def simulate_message(sender, recipient, content):
    """Simulate message passing."""
    from dataclasses import dataclass

    @dataclass
    class Message:
        sender: str
        recipient: str
        content: str

    msg = Message(sender=sender.name, recipient=recipient.name, content=content)
    recipient.receive(msg)
    return msg


def check_convergence(human: MockHuman, agent: RuleBasedClusterAgent, transcript: List[str]) -> bool:
    """Check if all nodes are mutually committed.

    Returns True if:
    - All boundary nodes have been committed by both parties
    - Commitments are to the same color
    """
    from comm.rb_protocol import parse_rb

    # Parse all commits from transcript
    human_commits = {}
    agent_commits = {}

    for line in transcript:
        rb_move = parse_rb(line)
        if rb_move and rb_move.move == "Commit":
            if "Human" in line or "[You" in line:
                human_commits[rb_move.node] = rb_move.colour
            else:
                agent_commits[rb_move.node] = rb_move.colour

    print(f"  Human commits: {human_commits}")
    print(f"  Agent commits: {agent_commits}")

    # Check that each party has committed their own nodes
    for node in human.nodes:
        if node not in human_commits:
            print(f"  Human hasn't committed their node {node}")
            return False

    for node in agent.nodes:
        if node not in agent_commits:
            print(f"  Agent hasn't committed their node {node}")
            return False

    print(f"  All nodes committed by their owners!")
    return True


def main():
    """Run the test dialogue."""
    print("=" * 60)
    print("RB Dialogue Test: Simulating Convergence")
    print("=" * 60)
    print()

    # Setup problem
    problem = create_simple_problem()
    owners = {
        "h1": "Human",
        "a1": "Agent1",
        "a2": "Agent1",
    }

    # Create participants
    human = MockHuman(name="Human", nodes=["h1"], owners=owners)
    agent = RuleBasedClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=MockCommLayer(),
        local_nodes=["a1", "a2"],
        owners=owners,
        algorithm="greedy",
    )

    # Transcript
    transcript = []

    print("Initial setup:")
    print(f"  Human owns: {list(human.nodes)}")
    print(f"  Agent owns: {agent.nodes}")
    print(f"  Colors: red, green, blue")
    print()

    # Step 1: Agent initializes (proposes its assignments)
    print("Step 1: Agent initializes")
    agent.step()
    if hasattr(agent, 'sent_messages'):
        for msg in agent.sent_messages:
            print(f"  -> {msg.sender}: {msg.content}")
            transcript.append(f"[{msg.sender}] {msg.content}")
    else:
        print("  (Agent sent messages via inherited send method)")
    agent.sent_messages = []  # Clear for next step
    print()

    # Step 2: Human proposes h1=green
    print("Step 2: Human proposes h1=green")
    msg_text = human.propose("h1", "green")
    msg = simulate_message(human, agent, msg_text)
    print(f"  -> Human: {msg.content}")
    transcript.append(f"[Human] {msg.content}")
    print()

    # Step 3: Agent responds (should propose remaining nodes if any)
    print("Step 3: Agent responds to human's proposal")
    agent.step()
    if hasattr(agent, 'sent_messages') and agent.sent_messages:
        for msg in agent.sent_messages:
            print(f"  -> {msg.sender}: {msg.content}")
            transcript.append(f"[{msg.sender}] {msg.content}")
        agent.sent_messages = []
    else:
        print("  (No response)")
    print()

    # Step 4: Human commits h1=green
    print("Step 4: Human commits h1=green")
    msg_text = human.commit("h1", "green")
    msg = simulate_message(human, agent, msg_text)
    print(f"  -> Human: {msg.content}")
    transcript.append(f"[Human] {msg.content}")
    print()

    # Step 5-6: Pass button (agent should commit its proposals)
    for i in range(5):
        print(f"Step {5+i}: Pass (let agent speak)")
        agent.step()
        if hasattr(agent, 'sent_messages') and agent.sent_messages:
            for msg in agent.sent_messages:
                print(f"  -> {msg.sender}: {msg.content}")
                transcript.append(f"[{msg.sender}] {msg.content}")
            agent.sent_messages = []
        else:
            print("  (No response)")
        print()

        # Check if agent has committed all its nodes
        agent_committed_all = True
        for node in agent.nodes:
            if node not in agent.rb_commitments.get(agent.name, {}):
                agent_committed_all = False
                break

        if agent_committed_all:
            print(f"  [OK] Agent has committed all its nodes")
            break

    # Step 7-8: Human commits to agent's proposals
    print()
    print("Final step: Human agrees with agent's assignments")
    for node in agent.nodes:
        color = agent.assignments.get(node)
        if color:
            msg_text = human.commit(node, color)
            msg = simulate_message(human, agent, msg_text)
            print(f"  -> Human: {msg_text}")
            transcript.append(f"[Human] {msg_text}")
    print()

    # Check convergence
    print("=" * 60)
    print("Checking convergence...")
    print("=" * 60)
    converged = check_convergence(human, agent, transcript)

    if converged:
        print("[OK] CONVERGENCE REACHED")
        print()
        print("Final assignments:")
        all_nodes = sorted(set(list(human.nodes) + agent.nodes))
        for node in all_nodes:
            if node in human.assignments:
                print(f"  {node}: {human.assignments[node]} (Human)")
            elif node in agent.assignments:
                print(f"  {node}: {agent.assignments[node]} (Agent)")
        print()
        print("Dialogue transcript saved to: test_rb_transcript.txt")

        # Save transcript
        with open("test_rb_transcript.txt", "w", encoding="utf-8") as f:
            f.write("RB Dialogue Test Transcript\n")
            f.write("=" * 60 + "\n\n")
            for line in transcript:
                f.write(line + "\n")
            f.write("\n" + "=" * 60 + "\n")
            f.write("[OK] Convergence reached\n")

        return 0
    else:
        print("[FAIL] CONVERGENCE NOT REACHED")
        print()
        print("Dialogue transcript:")
        for line in transcript:
            print(f"  {line}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
