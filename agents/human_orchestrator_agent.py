"""Human-orchestrated agent with algorithmic tools (2B mode).

This agent corresponds to the 2B configuration【685583168306604†L435-L459】.  A human
operator directs the algorithm by invoking primitive operations, such as
running a Max–Sum iteration, inspecting utilities, or manually choosing
a colour.  The communication layer still packages outgoing messages
into natural language.

The class uses an internal :class:`~dcop_framework.agents.max_sum_agent.MaxSumAgent` as a
tool.  The human may call ``compute`` to perform one algorithmic
update or ``inspect`` to view current utility scores.  Messages can
then be crafted manually.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .base_agent import BaseAgent, Message
from .max_sum_agent import MaxSumAgent
from comm.communication_layer import BaseCommLayer, PassThroughCommLayer


class HumanOrchestratorAgent(BaseAgent):
    """Agent implementing the 2B human-orchestrated mode."""

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
        # ensure initial assignment
        self.assignment = self.tool.assignment

    def receive(self, message: Message) -> None:
        super().receive(message)
        # forward structured messages to the tool
        self.tool.receive(message)
        print(f"[{self.name}] Received from {message.sender}: {message.content}")

    def prompt(self, prompt: str) -> str:
        if self.auto_response is not None:
            return self.auto_response(prompt)
        try:
            return input(prompt)
        except EOFError:
            return ""

    def menu(self) -> None:
        print(f"\n[{self.name}] Current colour: {self.assignment}")
        print("Choose an action:")
        print("  1. Run algorithm step")
        print("  2. Inspect utilities")
        print("  3. Choose colour manually")
        print("  4. Send message")
        print("  5. End turn")

    def step(self) -> None:
        """Interactive control for the human orchestrator."""
        while True:
            self.menu()
            choice = self.prompt(f"[{self.name}] Enter choice: ").strip()
            if choice == "1":
                # run internal algorithm step
                self.tool.step()
                self.assignment = self.tool.assignment
                self.log(f"Algorithm step: new assignment {self.assignment}")
                print(f"[{self.name}] Tool updated colour to {self.assignment}")
            elif choice == "2":
                util = self.tool.compute_local_utility()
                print(f"[{self.name}] Utilities: " + ", ".join(f"{k}:{v:.3f}" for k, v in util.items()))
            elif choice == "3":
                # manual colour selection
                print(f"Available colours: {', '.join(self.domain)}")
                colour = self.prompt(f"[{self.name}] Enter colour: ").strip()
                if colour in self.domain:
                    self.assignment = colour
                    self.log(f"Manual change to {colour}")
                    print(f"[{self.name}] Colour set to {colour}")
                else:
                    print("Invalid colour")
            elif choice == "4":
                # send a message
                msg = self.prompt(f"[{self.name}] Enter message: ").strip()
                if not msg:
                    msg = f"My colour is {self.assignment}."
                for neighbour in self.problem.get_neighbors(self.name):
                    content = self.comm_layer.format_content(self.name, neighbour, msg)
                    self.send(neighbour, content)
                print(f"[{self.name}] Sent message to neighbours.")
            elif choice == "5" or choice == "":
                # end turn
                break
            else:
                print("Invalid choice. Try again.")