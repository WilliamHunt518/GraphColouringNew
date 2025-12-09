"""Human-governed hybrid agent (2C mode).

This agent implements the 2C configuration【685583168306604†L468-L489】.  A human sets
high-level goals or criteria for the algorithmic control policy.  The
agent then executes a series of Max–Sum iterations accordingly and
reports its progress.  This design allows the human to supervise
autonomous optimisation without manually micromanaging each step.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .base_agent import BaseAgent, Message
from .max_sum_agent import MaxSumAgent
from comm.communication_layer import BaseCommLayer, PassThroughCommLayer


class HumanHybridAgent(BaseAgent):
    """Agent implementing the 2C human-governed hybrid mode."""

    def __init__(
        self,
        name: str,
        problem: 'GraphColoring',
        comm_layer: BaseCommLayer,
        initial_value: Optional[Any] = None,
        auto_response: Optional[Callable[[str], str]] = None,
    ) -> None:
        super().__init__(name, problem, comm_layer, initial_value)
        self.tool = MaxSumAgent(name, problem, PassThroughCommLayer(), initial_value)
        self.auto_response = auto_response
        # initial assignment from the tool
        self.assignment = self.tool.assignment

    def receive(self, message: Message) -> None:
        super().receive(message)
        self.tool.receive(message)
        print(f"[{self.name}] Received from {message.sender}: {message.content}")

    def prompt(self, prompt: str) -> str:
        if self.auto_response is not None:
            return self.auto_response(prompt)
        try:
            return input(prompt)
        except EOFError:
            return ""

    def step(self) -> None:
        """Ask the human for a high-level goal and execute accordingly."""
        print(f"\n[{self.name}] Current colour: {self.assignment}")
        # ask for number of iterations to run
        goal = self.prompt(
            f"[{self.name}] Enter number of algorithm steps to run this turn (0 to skip): "
        ).strip()
        try:
            n_steps = int(goal)
        except ValueError:
            n_steps = 0
        if n_steps > 0:
            for i in range(n_steps):
                self.tool.step()
            self.assignment = self.tool.assignment
            self.log(f"Ran {n_steps} steps, assignment now {self.assignment}")
            print(f"[{self.name}] After {n_steps} steps assignment = {self.assignment}")
        # send update message
        msg = self.prompt(f"[{self.name}] Enter message to neighbours (optional): ").strip()
        if not msg:
            msg = f"Now at colour {self.assignment}."
        for neighbour in self.problem.get_neighbors(self.name):
            content = self.comm_layer.format_content(self.name, neighbour, msg)
            self.send(neighbour, content)