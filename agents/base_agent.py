"""Base class for DCOP agents.

This module defines the :class:`BaseAgent`, which provides common
attributes and methods for all agent implementations.  It tracks the
agent's identity, current assignment, message history, and
communication layer.  Subclasses should implement the
:meth:`step` method to perform one iteration of their algorithm and
update the agent's internal state accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from problems.graph_coloring import GraphColoring
from comm.communication_layer import BaseCommLayer


@dataclass
class Message:
    """Simple container for messages exchanged between agents.

    Attributes
    ----------
    sender : str
        Identifier of the sending agent.
    recipient : str
        Identifier of the receiving agent.
    content : Any
        Payload of the message.  In algorithmic modes this may be
        structured data (e.g., dictionaries of scores); in human or
        LLM modes it may be natural-language strings.
    """

    sender: str
    recipient: str
    content: Any


class BaseAgent:
    """Abstract base class for DCOP agents.

    Parameters
    ----------
    name : str
        Unique identifier for the agent.  Should correspond to a node
        name in the underlying problem.
    problem : GraphColoring
        The problem instance that defines the graph structure and
        domain.  Agents use this to query neighbours and domain
        information.
    comm_layer : BaseCommLayer
        Communication layer used to translate between internal
        representations and natural language.  Can be an LLM-based
        module, a human interface, or a mock pass-through.
    initial_value : Optional[Any], default None
        Initial colour assigned to this agent.  If None, one will be
        chosen randomly from the domain when the agent first runs.
    """

    def __init__(
        self,
        name: str,
        problem: GraphColoring,
        comm_layer: BaseCommLayer,
        initial_value: Optional[Any] = None,
    ) -> None:
        self.name = name
        self.problem = problem
        self.comm_layer = comm_layer
        self.domain = problem.domain
        self.assignment: Optional[Any] = initial_value
        # history of messages (sender, recipient, content)
        self.sent_messages: List[Message] = []
        self.received_messages: List[Message] = []
        # internal log of actions and reasoning steps
        self.logs: List[str] = []

    def log(self, message: str) -> None:
        """Append a line to the agent's internal log."""
        self.logs.append(message)

    def receive(self, message: Message) -> None:
        """Handle an incoming message.

        By default this simply stores the message in ``received_messages``.
        Subclasses may override to implement parsing and state updates.
        """
        self.received_messages.append(message)
        self.log(f"Received message from {message.sender}: {message.content}")

    def send(self, recipient: str, content: Any) -> Message:
        """Create and record a message destined for another agent.

        Before a message is dispatched, the raw ``content`` is passed
        through the communication layer.  This allows algorithmic
        messages (e.g., dictionaries of utilities) to be converted
        into a natural language string via an LLM or other mechanism.
        For modes that assume a shared protocol (e.g. mode 1Z), the
        ``PassThroughCommLayer`` will simply return the content
        unchanged.  The resulting formatted content is stored in the
        message's ``content`` field and appended to
        ``self.sent_messages``.
        """
        # use the communication layer to format the content prior to sending
        try:
            formatted = self.comm_layer.format_content(self.name, recipient, content)
        except Exception:
            # fallback to raw content if formatting fails
            formatted = content
        msg = Message(sender=self.name, recipient=recipient, content=formatted)
        self.sent_messages.append(msg)
        self.log(f"Sent message to {recipient}: {formatted}")
        return msg

    def choose_initial_value(self) -> None:
        """Select an initial colour randomly if none has been assigned yet."""
        import random

        if self.assignment is None and self.domain:
            self.assignment = random.choice(self.domain)
            self.log(f"Initial value chosen: {self.assignment}")

    def step(self) -> None:
        """Perform one iteration of the agent's decision process.

        Must be implemented by subclasses.  A typical implementation
        will involve reading received messages, updating internal
        variables, sending messages to neighbours via the communication
        layer, and selecting a new assignment when enough information is
        available.
        """
        raise NotImplementedError

    def get_logs(self) -> List[str]:
        """Return the accumulated log lines for this agent."""
        return list(self.logs)