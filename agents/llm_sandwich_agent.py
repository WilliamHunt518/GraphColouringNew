"""Hybrid LLM-sandwich agent (1C mode).

This agent demonstrates the hybrid "LLM sandwich" architecture【685583168306604†L336-L367】.
A deterministic control policy governs the sequence of algorithmic
steps, while an LLM orchestrator executes each step using the same
algorithmic tools as the algorithm‑first mode.  The orchestrator is
allowed to communicate with neighbours via natural language to convey
intentions and progress.

In this implementation the control policy is simply a fixed number of
iterations.  The agent runs the underlying Max–Sum tool for
``max_iterations`` steps, sending a detailed natural-language update to
each neighbour after each iteration.  Once the maximum number of
iterations is reached the agent finalises its choice and communicates
its final value.
"""

from __future__ import annotations

from typing import Any, Optional

from .base_agent import BaseAgent, Message
from .max_sum_agent import MaxSumAgent
from comm.communication_layer import BaseCommLayer, PassThroughCommLayer


class LLMSandwichAgent(BaseAgent):
    """Agent implementing the 1C hybrid sandwich architecture."""

    def __init__(
        self,
        name: str,
        problem: 'GraphColoring',
        comm_layer: BaseCommLayer,
        initial_value: Optional[Any] = None,
        max_iterations: int = 3,
    ) -> None:
        super().__init__(name, problem, comm_layer, initial_value)
        self.tool = MaxSumAgent(name, problem, PassThroughCommLayer(), initial_value)
        self.max_iterations = max_iterations
        self.iteration = 0
        self.finished = False

    def receive(self, message: Message) -> None:
        # log and forward to internal tool
        super().receive(message)
        self.tool.receive(message)

    def step(self) -> None:
        """Run one iteration under the control policy."""
        if self.finished:
            # no further actions, but could still respond to messages
            return
        self.iteration += 1
        self.tool.step()
        self.assignment = self.tool.assignment
        self.log(f"Iteration {self.iteration}: selected {self.assignment}")
        # send detailed update to neighbours
        utilities = self.tool.compute_local_utility()
        update_text = (
            f"Iteration {self.iteration}: choosing {self.assignment}. "
            f"Utilities: " + ", ".join(f"{k}:{v:.3f}" for k, v in utilities.items())
        )
        for neighbour in self.problem.get_neighbors(self.name):
            content = self.comm_layer.format_content(self.name, neighbour, update_text)
            self.send(neighbour, content)
        # check termination
        if self.iteration >= self.max_iterations:
            self.finished = True
            final_text = f"Finalise: my final value is {self.assignment}"
            for neighbour in self.problem.get_neighbors(self.name):
                content = self.comm_layer.format_content(self.name, neighbour, final_text)
                self.send(neighbour, content)