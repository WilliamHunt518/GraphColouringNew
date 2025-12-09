"""Human-as-communication-layer agent (2A mode).

This agent represents the 2A configuration where the human
completely replaces the communication and reasoning components【685583168306604†L402-L431】.
The framework delegates all decision-making to a human operator via
standard input/output.  On each step the human sees messages from
neighbours, chooses a colour for their node, and optionally writes a
message to neighbours.

Because this mode relies on blocking user input, it is best used in
interactive contexts.  In automated testing you may supply an
``auto_response`` callback to bypass manual input.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .base_agent import BaseAgent, Message
from comm.communication_layer import BaseCommLayer


class HumanCLAgent(BaseAgent):
    """Agent where a human performs all reasoning and messaging."""

    def __init__(
        self,
        name: str,
        problem: 'GraphColoring',
        comm_layer: BaseCommLayer,
        initial_value: Optional[Any] = None,
        auto_response: Optional[Callable[[str], str]] = None,
    ) -> None:
        super().__init__(name, problem, comm_layer, initial_value)
        self.auto_response = auto_response
        # ensure some initial assignment for logging
        self.choose_initial_value()

    def receive(self, message: Message) -> None:
        """Display incoming messages to the human."""
        super().receive(message)
        print(f"[{self.name}] Received from {message.sender}: {message.content}")

    def prompt(self, prompt: str) -> str:
        """Prompt the user for input or use auto_response."""
        if self.auto_response is not None:
            return self.auto_response(prompt)
        try:
            return input(prompt)
        except EOFError:
            # in non-interactive environments return empty string
            return ""

    def step(self) -> None:
        """Interactively ask the human to choose a colour and message."""
        # display current assignment
        print(f"\n[{self.name}] Current colour: {self.assignment}")
        print(f"Available colours: {', '.join(self.domain)}")
        # ask human for new colour
        while True:
            colour = self.prompt(f"[{self.name}] Enter new colour (leave blank to keep {self.assignment}): ").strip()
            if not colour:
                colour = self.assignment  # keep existing
            if colour in self.domain:
                break
            print(f"Invalid colour. Choose from {self.domain}.")
        if colour != self.assignment:
            self.log(f"Human changed colour from {self.assignment} to {colour}")
            self.assignment = colour
        # ask human for message to neighbours
        msg_text = self.prompt(f"[{self.name}] Enter message to neighbours (optional): ").strip()
        if not msg_text:
            msg_text = f"I chose {self.assignment}."
        # send message to each neighbour via comm layer
        for neighbour in self.problem.get_neighbors(self.name):
            content = self.comm_layer.format_content(self.name, neighbour, msg_text)
            self.send(neighbour, content)