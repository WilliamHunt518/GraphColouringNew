"""Implementation of a basic Max–Sum agent.

This class encapsulates the inference-based Max–Sum algorithm for a
variable node in a factor graph【685583168306604†L150-L216】.  It maintains
incoming messages from neighbours (interpreted as ``R`` messages in
Max–Sum terminology) and computes outgoing messages to neighbours
(``Q`` messages).  After aggregating incoming messages it selects a
colour that maximises its local utility【685583168306604†L206-L217】.

The agent can operate in conjunction with a communication layer
implemented by an LLM or a human.  The internal algorithm remains
separate from the communication layer: structured messages are
converted to natural language when sending, and parsed from natural
language when receiving.  This illustrates the algorithm‑first
architecture described in Section 3.2.1【685583168306604†L267-L294】.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent, Message
from comm.communication_layer import BaseCommLayer


class MaxSumAgent(BaseAgent):
    """A variable-node agent implementing the Max–Sum algorithm.

    This implementation follows the standard message-passing equations
    for Max–Sum【685583168306604†L150-L216】.  Each agent maintains a mapping
    ``r_messages`` from neighbour names to dictionaries mapping domain
    values to real-valued scores.  On each iteration the agent:

    1. Parses and stores any received messages from neighbours.
    2. Computes its local utility for each value by summing its own
       preference and incoming ``r_messages`` from all neighbours.
    3. Selects the value with maximal utility.
    4. Constructs an outgoing message for each neighbour.  For a
       neighbour ``j``, the message is a dictionary mapping each
       value in the domain to the maximal utility attainable if the
       neighbour were to choose that value, given the current
       ``r_messages`` from other neighbours.
    5. Normalises each outgoing message by subtracting its maximum to
       prevent unbounded growth (the ``α`` constant in the literature【685583168306604†L186-L196】).

    The outgoing structured messages are passed through the
    communication layer for formatting before they are stored as
    :class:`~dcop_framework.agents.base_agent.Message` objects for
    delivery.
    """

    def __init__(
        self,
        name: str,
        problem: 'GraphColoring',
        comm_layer: BaseCommLayer,
        initial_value: Optional[Any] = None,
    ) -> None:
        super().__init__(name, problem, comm_layer, initial_value)
        # store incoming r-messages from neighbours: neighbour -> {value: score}
        self.r_messages: Dict[str, Dict[Any, float]] = {
            n: {val: 0.0 for val in self.domain} for n in self.problem.get_neighbors(name)
        }
        # outgoing messages from previous iteration (optional debug)
        self.q_messages: Dict[str, Dict[Any, float]] = {}
        # ensure we have an initial assignment
        self.choose_initial_value()

    def receive(self, message: Message) -> None:
        """Parse an incoming message into an ``r_message``.

        Uses the communication layer to interpret the content.  If the
        content is a dictionary it is stored directly; otherwise the
        message is ignored.  This allows the agent to gracefully
        ignore human comments or other free-form messages.
        """
        super().receive(message)
        structured = self.comm_layer.parse_content(message.sender, self.name, message.content)
        if isinstance(structured, dict):
            # ensure the dictionary contains all domain values; fill missing with zero
            msg_dict = {val: structured.get(val, 0.0) for val in self.domain}
            self.r_messages[message.sender] = msg_dict
            self.log(f"Parsed structured message from {message.sender}: {msg_dict}")
        else:
            # non-dict messages may come from human agents; ignore for algorithmic update
            self.log(f"Ignored non-structured message from {message.sender}: {structured}")

    def compute_local_utility(self) -> Dict[Any, float]:
        """Compute local utility for each value given current ``r_messages``."""
        utilities: Dict[Any, float] = {}
        for val in self.domain:
            # start with own preference
            pref = self.problem.preferences[self.name][val]
            utilities[val] = pref
            # sum messages from all neighbours
            for neighbour in self.r_messages:
                utilities[val] += self.r_messages[neighbour].get(val, 0.0)
        return utilities

    def select_best_value(self) -> Any:
        """Select the value with the highest computed utility."""
        utilities = self.compute_local_utility()
        # identify the maximum utility
        max_util = max(utilities.values())
        # gather all values achieving the maximum
        best_values = [v for v, u in utilities.items() if u == max_util]
        # tie‑break randomly among best values; this prevents agents from
        # repeatedly selecting the same colour when utilities are identical
        import random
        best_val = random.choice(best_values)
        self.log(f"Utilities: {utilities}, selected {best_val}")
        return best_val

    def compute_q_message(self, neighbour: str) -> Dict[Any, float]:
        """Compute the outgoing Q-message for a given neighbour.

        The Q-message is a dictionary mapping each value in the
        neighbour's domain to the maximal utility obtainable if the
        neighbour were to choose that value, given the current
        ``r_messages`` from all other neighbours.  The computation
        corresponds to Eq. (5) in the Max–Sum formulation【685583168306604†L181-L199】.
        """
        result: Dict[Any, float] = {}
        # for each possible value of neighbour j
        for v_j in self.domain:
            # compute max over our values
            best = -math.inf
            for v_i in self.domain:
                # penalty (negative reward) if colours clash
                reward = 0.0
                if v_i == v_j:
                    reward = -self.problem.conflict_penalty
                # aggregated utility from other neighbours (excluding j)
                agg = self.problem.preferences[self.name][v_i]
                for other in self.r_messages:
                    if other == neighbour:
                        continue
                    agg += self.r_messages[other].get(v_i, 0.0)
                # combine
                val = reward + agg
                if val > best:
                    best = val
            result[v_j] = best
        # We intentionally avoid adding per-iteration random noise to all
        # message values.  Tie breaking is achieved via agents’ personal
        # preferences (randomised once at problem creation) and random
        # choice among values with equal utility in ``select_best_value``.
        # normalise by subtracting max value to prevent diverging sums
        max_val = max(result.values()) if result else 0.0
        for key in result:
            result[key] -= max_val
        return result

    def step(self) -> None:
        """Perform one iteration of the Max–Sum algorithm.

        This method updates the agent's assignment based on incoming
        messages and sends new messages to all neighbours.  It should
        be called once per algorithmic iteration by the simulation
        environment.
        """
        # update current assignment based on r-messages
        new_value = self.select_best_value()
        if new_value != self.assignment:
            self.log(f"Changing value from {self.assignment} to {new_value}")
            self.assignment = new_value
        # compute and send Q-messages to neighbours
        self.q_messages = {}
        for neighbour in self.r_messages:
            q_msg = self.compute_q_message(neighbour)
            self.q_messages[neighbour] = q_msg
            # wrap message via comm layer
            # send the raw Q-message; BaseAgent.send will apply the
            # communication layer formatting.  This avoids double
            # formatting when using LLMCommLayer.
            self.send(neighbour, q_msg)