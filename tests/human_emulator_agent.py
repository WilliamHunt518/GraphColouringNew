"""Human Emulator Agent for Testing.

This agent emulates human behavior in the graph coloring task:
- Makes color changes based on agent suggestions
- Sends messages with questions and constraints
- Responds to agent proposals reasonably
- Marks satisfaction when appropriate
"""

import random
import re
from typing import Dict, List, Any, Set, Optional
from agents.cluster_agent import ClusterAgent


class HumanEmulatorAgent(ClusterAgent):
    """An agent that emulates human behavior for automated testing."""

    def __init__(self, *args, **kwargs):
        """Initialize the human emulator agent.

        Parameters
        ----------
        *args, **kwargs
            Arguments passed to ClusterAgent.
        """
        super().__init__(*args, **kwargs)

        # Emulator-specific state
        self.turns_taken = 0
        self.last_suggestions = {}  # Track suggestions from other agents
        self.acceptance_rate = 0.6  # 60% chance to accept a suggestion
        self.constraint_rate = 0.3  # 30% chance to impose a constraint
        self.question_rate = 0.2  # 20% chance to ask a question
        self.max_turns = 30  # Don't let emulator run forever

    def step(self, incoming_messages: List[Any] = None) -> None:
        """Execute one turn of the human emulator.

        The emulator:
        1. Reads incoming messages from agents
        2. Extracts suggestions and constraints
        3. Decides whether to accept suggestions, ask questions, or impose constraints
        4. Updates assignments accordingly
        5. Checks satisfaction

        Parameters
        ----------
        incoming_messages : list, optional
            Messages received from neighbor agents.
        """
        self.turns_taken += 1
        self.log(f"\n{'='*60}")
        self.log(f"Human Emulator Turn {self.turns_taken}")
        self.log(f"{'='*60}")

        # Process incoming messages
        if incoming_messages:
            for msg in incoming_messages:
                self._process_agent_message(msg)

        # Decide on actions based on current state
        action = self._decide_action()

        if action == "accept_suggestion":
            self._accept_suggestion()
        elif action == "impose_constraint":
            self._impose_constraint()
        elif action == "ask_question":
            self._ask_question()
        elif action == "random_change":
            self._make_random_change()
        elif action == "wait":
            self.log("Waiting for more information from agents")

        # Check satisfaction
        penalty = self.problem.evaluate_assignment(
            {**self.assignments, **getattr(self, "neighbour_assignments", {})}
        )

        if penalty == 0.0:
            self.satisfied = True
            self.log("✓ SATISFIED: Zero penalty achieved")
        else:
            self.satisfied = False
            self.log(f"✗ NOT SATISFIED: Current penalty = {penalty}")

        # Safety: Mark satisfied if we've been running too long
        if self.turns_taken >= self.max_turns:
            self.log(f"Reached max turns ({self.max_turns}), marking satisfied")
            self.satisfied = True

    def _process_agent_message(self, msg: Dict[str, Any]) -> None:
        """Parse and store suggestions from agent messages.

        Parameters
        ----------
        msg : dict
            Message from an agent containing suggestions or constraints.
        """
        sender = msg.get("sender", "Unknown")
        content = msg.get("content", {})
        msg_type = content.get("type", "unknown")
        data = content.get("data", {})

        self.log(f"Processing message from {sender}: type={msg_type}")

        if msg_type == "cost_list":
            # LLM_U style: extract options
            options = data.get("options", [])
            if options:
                # Store top 3 options
                self.last_suggestions[sender] = options[:3]
                self.log(f"  Stored {len(options[:3])} options from {sender}")

        elif msg_type == "constraints":
            # LLM_C style: extract valid configs
            valid_configs = data.get("valid_configs", [])
            per_node = data.get("per_node", {})

            if valid_configs:
                self.last_suggestions[sender] = [
                    {"human": config, "type": "constraint"} for config in valid_configs[:3]
                ]
                self.log(f"  Stored {len(valid_configs[:3])} constraint configs from {sender}")
            elif per_node:
                # Just per-node constraints, convert to suggestion
                self.last_suggestions[sender] = [
                    {"human": per_node, "type": "constraint_per_node"}
                ]
                self.log(f"  Stored per-node constraints from {sender}")

    def _decide_action(self) -> str:
        """Decide what action to take this turn.

        Returns
        -------
        str
            Action to take: "accept_suggestion", "impose_constraint",
            "ask_question", "random_change", or "wait"
        """
        # If we have suggestions, maybe accept one
        if self.last_suggestions and random.random() < self.acceptance_rate:
            return "accept_suggestion"

        # Maybe impose a constraint
        if random.random() < self.constraint_rate:
            return "impose_constraint"

        # Maybe ask a question
        if random.random() < self.question_rate:
            return "ask_question"

        # Make a random change
        if random.random() < 0.3:
            return "random_change"

        # Otherwise wait
        return "wait"

    def _accept_suggestion(self) -> None:
        """Accept a suggestion from one of the agents."""
        if not self.last_suggestions:
            return

        # Pick a random agent's suggestion
        sender = random.choice(list(self.last_suggestions.keys()))
        options = self.last_suggestions[sender]

        if not options:
            return

        # Pick the first (best) option
        option = options[0]
        suggested_assignment = option.get("human", {})

        if not isinstance(suggested_assignment, dict):
            return

        # Apply the suggested assignments
        changes_made = []
        for node, color in suggested_assignment.items():
            if node in self.nodes and self.assignments.get(node) != color:
                old_color = self.assignments.get(node)
                self.assignments[node] = color
                changes_made.append(f"{node}: {old_color} → {color}")

        if changes_made:
            self.log(f"Accepted suggestion from {sender}:")
            for change in changes_made:
                self.log(f"  {change}")
        else:
            self.log(f"Suggestion from {sender} matches current assignment")

    def _impose_constraint(self) -> None:
        """Impose a constraint on boundary nodes."""
        # Get boundary nodes
        boundary_nodes = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    boundary_nodes.add(nbr)

        if not boundary_nodes:
            return

        # Pick a random boundary node and forbid a color
        node = random.choice(list(boundary_nodes))
        forbidden_color = random.choice(self.domain)

        self.log(f"Imposing constraint: {node} cannot be {forbidden_color}")
        # This would be sent as a message in real scenario

    def _ask_question(self) -> None:
        """Ask a question to one of the agents."""
        questions = [
            "Can you improve your score?",
            "Why did you change that color?",
            "What happens if I change this boundary node?",
            "Are you satisfied with this solution?",
        ]

        question = random.choice(questions)
        self.log(f"Asking question: '{question}'")
        # This would be sent as a message in real scenario

    def _make_random_change(self) -> None:
        """Make a random color change to explore the space."""
        if not self.nodes:
            return

        # Pick a random node and color
        node = random.choice(list(self.nodes))
        old_color = self.assignments.get(node)
        new_color = random.choice([c for c in self.domain if c != old_color])

        self.assignments[node] = new_color
        self.log(f"Random exploration: changed {node} from {old_color} to {new_color}")
