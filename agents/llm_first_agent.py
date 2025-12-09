"""LLM-first orchestrated agent (1B mode).

This agent illustrates the LLM-first architecture【685583168306604†L305-L334】.  Rather than
executing the Max–Sum algorithm in a fixed loop, an LLM (simulated
here) acts as an orchestrator that invokes algorithmic primitives as
tools.  The orchestrator may choose to communicate directly in natural
language instead of forwarding detailed algorithmic messages.

In this simplified implementation we use a :class:`~dcop_framework.agents.max_sum_agent.MaxSumAgent`
internally as a callable tool.  On each step the orchestrator:

1. Calls the internal Max–Sum tool to update its belief state and
   compute new preferences and assignments.
2. Copies the tool's assignment as its own.
3. Sends a high‑level natural‑language message to each neighbour
   summarising its chosen value and, optionally, utility scores.  This
   demonstrates how an LLM could bypass the structured messaging API
   when it deems it unnecessary【685583168306604†L318-L334】.

Note that this mode sacrifices some procedural stability in favour of
flexibility.  Other agents may ignore the free‑form messages if they
cannot parse them as structured data, but they can still respond
through the shared natural‑language channel.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base_agent import BaseAgent, Message
from .max_sum_agent import MaxSumAgent
from comm.communication_layer import BaseCommLayer, PassThroughCommLayer


class LLMFirstAgent(BaseAgent):
    """Agent implementing the 1B LLM-first architecture."""

    def __init__(
        self,
        name: str,
        problem: 'GraphColoring',
        comm_layer: BaseCommLayer,
        initial_value: Optional[Any] = None,
    ) -> None:
        super().__init__(name, problem, comm_layer, initial_value)
        # internal Max–Sum tool with a pass-through communication layer.  We
        # do not want the tool to format messages because the LLM
        # orchestrator will decide how to communicate.
        self.tool = MaxSumAgent(name, problem, PassThroughCommLayer(), initial_value)

    def receive(self, message: Message) -> None:
        """Forward incoming messages to the internal tool for processing."""
        # also log message at orchestrator level
        super().receive(message)
        # parse message with the tool's simple pass-through layer
        self.tool.receive(message)

    def step(self) -> None:
        """Invoke the internal tool and then communicate via the LLM."""
        # run one iteration of the underlying algorithmic tool
        self.tool.step()
        # copy assignment
        self.assignment = self.tool.assignment
        self.log(f"Internal tool selected {self.assignment}")
        # decide what to communicate.  The orchestrator may choose to
        # summarise its choice instead of relaying detailed scores.
        # We construct a message that contains the selected value and
        # local utilities for transparency.
        utilities = self.tool.compute_local_utility()
        summary = (
            f"I plan to choose {self.assignment}. "
            f"Utilities: " + ", ".join(f"{k}:{v:.3f}" for k, v in utilities.items())
        )
        # send to all neighbours
        for neighbour in self.problem.get_neighbors(self.name):
            content = self.comm_layer.format_content(self.name, neighbour, summary)
            self.send(neighbour, content)