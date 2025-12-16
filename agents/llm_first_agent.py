"""LLM-first orchestrated agent (1B mode).

This agent illustrates the LLM‑first architecture【685583168306604†L305-L334】.  In the full
framework an LLM is responsible for deciding when to invoke
algorithmic primitives (e.g., running a Max–Sum iteration) and for
selecting the agent's colour.  The model operates on a prompt that
encodes the agent's current assignment, local utility scores and
recommended actions from the underlying algorithm.  Based on this
context it can instruct the agent to run another algorithm step,
override the algorithm's suggestion, or simply communicate its current
intent to neighbours.

This implementation uses an internal :class:`~dcop_framework.agents.max_sum_agent.MaxSumAgent`
as a tool but defers control to an LLM.  At each step the agent:

1. Computes local utilities and the algorithm's recommended colour
   without performing a full algorithmic update.
2. Constructs a prompt describing its state and asks the LLM for
   instructions.  If an LLM is available, its response may instruct
   the agent to run the algorithm tool (``run algorithm``) and/or
   choose a particular colour from the domain.  When no LLM is
   available the agent defaults to the algorithm's recommendation.
3. If the LLM instructs to run the algorithm, ``tool.step()`` is
   executed to update internal beliefs and outgoing messages.
4. If the LLM names a colour, that colour is adopted as both the
   agent's assignment and the internal tool's assignment, overriding
   the algorithm if necessary.  Otherwise the assignment from the tool
   is used.
5. The agent communicates its chosen colour and optionally utility
   information to neighbours via the communication layer.  A natural
   language summary is produced so that other agents (human or LLM)
   can interpret its decision.【685583168306604†L318-L334】

Enabling history mode in the communication layer causes successive
prompts and responses to be appended to a shared conversation, so the
LLM can condition its decisions on previous context.  When disabled,
each call to the LLM is stateless.
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
        """Perform one iteration under LLM control.

        The agent queries the language model for instructions on whether to
        run an algorithmic update and which colour to choose.  The prompt
        summarises the current assignment, local utility scores and the
        algorithm's recommended value.  On receiving a response the agent
        interprets keywords to decide its actions.  When no LLM is
        available the agent falls back to the algorithm's recommendation.
        """
        # ensure an initial value if none selected yet
        if self.assignment is None:
            self.tool.choose_initial_value()
            self.assignment = self.tool.assignment
        # compute local utilities without advancing the algorithm
        utilities = self.tool.compute_local_utility()
        # algorithm's recommended value (do not update assignment yet)
        try:
            algorithm_suggestion = self.tool.select_best_value()
        except Exception:
            # if selection fails (e.g., empty domain), fall back to current assignment
            algorithm_suggestion = self.assignment
        # build a natural-language prompt for the LLM
        domain_str = ", ".join(str(x) for x in self.domain)
        util_str = ", ".join(f"{k}:{v:.3f}" for k, v in utilities.items())
        prompt = (
            f"You are controlling agent {self.name} in a graph colouring task. "
            f"Your current assignment is {self.assignment}. "
            f"The local utility scores for each colour are: {util_str}. "
            f"The algorithm recommends choosing {algorithm_suggestion}. "
            f"Decide whether to run the algorithm step (reply with 'run algorithm' if needed) "
            f"and which colour to choose from the domain {{ {domain_str} }}. "
            f"Provide a brief response including any colour you select."
        )
        # query the LLM via the communication layer's internal API if available
        decision: Optional[str] = None
        # only attempt a call if the communication layer exposes _call_openai
        if hasattr(self.comm_layer, "_call_openai"):
            try:
                decision = self.comm_layer._call_openai(prompt, max_tokens=80)
            except Exception:
                decision = None
        # interpret the decision
        run_algorithm = False
        chosen_colour: Optional[Any] = None
        if decision:
            # simple heuristics: check for "run" and colour names
            low = decision.lower()
            if "run" in low and "algorithm" in low:
                run_algorithm = True
            # search for any domain value in the response
            for colour in self.domain:
                if str(colour).lower() in low:
                    chosen_colour = colour
                    break
            self.log(f"LLM decision: {decision}")
        else:
            self.log("No LLM decision available; falling back to algorithm suggestion")
        # decide whether to run the algorithmic tool
        if run_algorithm:
            self.tool.step()
            self.assignment = self.tool.assignment
        # if LLM specified a colour, override assignment for both agent and tool
        if chosen_colour is not None:
            self.assignment = chosen_colour
            self.tool.assignment = chosen_colour  # keep tool in sync
        else:
            # if no override and we have not run the algorithm, adopt algorithm suggestion
            if not run_algorithm:
                self.assignment = algorithm_suggestion
                self.tool.assignment = algorithm_suggestion
        # compute fresh utilities after potential algorithm update for reporting
        utilities_after = self.tool.compute_local_utility()
        util_after_str = ", ".join(f"{k}:{v:.3f}" for k, v in utilities_after.items())
        # craft summary message
        summary = (
            f"I choose {self.assignment}. "
            f"Utilities: {util_after_str}."
        )
        # send to all neighbours
        for neighbour in self.problem.get_neighbors(self.name):
            try:
                content = self.comm_layer.format_content(self.name, neighbour, summary)
            except Exception:
                content = summary
            self.send(neighbour, content)