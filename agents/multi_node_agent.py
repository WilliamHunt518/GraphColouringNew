"""Multi‑node agent implementation for DCOP problems.

This module defines the :class:`MultiNodeAgent`, which represents an
agent controlling multiple variables (nodes) in a distributed
constraint optimisation problem.  Rather than treating each node
individually, a multi‑node agent chooses a joint assignment for all
its local variables by evaluating candidate assignments against the
current assignments of neighbouring nodes.  After selecting a new
assignment, it broadcasts the assignments of its local nodes to
neighbouring agents.

The current implementation uses a simple exhaustive search over the
Cartesian product of the colour domain for the local nodes.  This is
sufficient for small groups of variables (e.g. three nodes per
owner).  For larger groups, more sophisticated local optimisation
methods (e.g. local search) could be substituted.

The agent relies on an ``owners`` mapping passed at construction to
determine the owner (agent name) of each node in the problem.  It
uses this information to route messages: assignments are sent only to
neighbouring agents (those controlling nodes connected to the agent's
nodes).  Messages contain a mapping from node identifiers to their
current colour assignments.  Receiving agents update their
``neighbour_assignments`` accordingly and use this information to
evaluate candidate assignments.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

import itertools

from .base_agent import BaseAgent, Message


class MultiNodeAgent(BaseAgent):
    """Agent controlling multiple nodes in a DCOP.

    Parameters
    ----------
    name : str
        Identifier of the agent (typically the owner's name, e.g.
        "Alice" or "Bob").
    problem : GraphColoring
        The colouring problem instance defining the nodes, edges and
        domain.
    comm_layer : BaseCommLayer
        Communication layer used for sending and receiving messages.
    local_nodes : list of str
        List of node identifiers controlled by this agent.
    owners : dict
        Mapping from node identifiers to the owner name (agent name) that
        controls the node.  Used to determine the recipient of outgoing
        messages.
    initial_assignments : dict, optional
        Mapping from node identifiers to initial colour assignments for
        those nodes.  Any nodes not present will be initialised
        randomly from the domain.

    Notes
    -----
    ``MultiNodeAgent`` evaluates the global penalty of candidate
    assignments by merging the candidate assignments for its own nodes
    with the most recently received assignments for neighbouring nodes.
    Missing assignments are treated as uncoloured and incur no
    penalty.  The agent seeks the assignment with the lowest global
    penalty.
    """

    def __init__(
        self,
        name: str,
        problem: Any,
        comm_layer: Any,
        local_nodes: List[str],
        owners: Dict[str, str],
        initial_assignments: Optional[Dict[str, Any]] = None,
    ) -> None:
        # initialise as a BaseAgent with no single-node initial value
        super().__init__(name=name, problem=problem, comm_layer=comm_layer, initial_value=None)
        self.nodes: List[str] = list(local_nodes)
        self.owners: Dict[str, str] = dict(owners)
        # current assignments for each local node
        self.assignments: Dict[str, Any] = {}
        # assignments received from neighbours for external nodes
        self.neighbour_assignments: Dict[str, Any] = {}
        # initialise assignments
        for node in self.nodes:
            if initial_assignments and node in initial_assignments:
                self.assignments[node] = initial_assignments[node]
            else:
                # choose a random colour from the domain
                import random
                self.assignments[node] = random.choice(self.domain)
        self.log(f"Initial multi-node assignments: {self.assignments}")

    def receive(self, message: Message) -> None:
        """Handle an incoming message.

        Messages are expected to contain a mapping from node identifiers
        to assigned values.  For each node not controlled by this agent,
        the assignment is recorded in ``neighbour_assignments``.  If
        the message contains entries for this agent's own nodes, they are
        ignored (the agent does not update its assignment from
        neighbours).
        """
        super().receive(message)
        content = message.content
        if isinstance(content, dict):
            for node, val in content.items():
                # only record assignments for nodes not controlled by this agent
                if node not in self.nodes:
                    self.neighbour_assignments[node] = val
                    self.log(f"Updated neighbour assignment: {node} -> {val}")

    def evaluate_candidate(self, candidate_assign: Dict[str, Any]) -> float:
        """Compute the global penalty of a candidate assignment for local nodes.

        The candidate assignment is merged with the most recently
        received assignments for neighbouring nodes.  Missing
        assignments are ignored (treated as uncoloured and incur no
        penalty).

        Parameters
        ----------
        candidate_assign : dict
            Mapping from local node identifiers to proposed colour
            assignments.

        Returns
        -------
        float
            The global penalty (lower is better).
        """
        # merge candidate assignments with neighbour assignments
        merged: Dict[str, Any] = dict(self.neighbour_assignments)
        merged.update(candidate_assign)
        return self.problem.evaluate_assignment(merged)

    def step(self) -> None:
        """Perform one iteration of the agent's decision process.

        The agent enumerates all possible assignments for its local
        nodes, selects the one with the lowest global penalty, updates
        its internal assignment, logs the decision, and sends the
        assignment to neighbouring agents.
        """
        # ensure we have at least one domain value
        if not self.domain:
            return
        # exhaustive search over all combinations of colours for local nodes
        best_assignment: Dict[str, Any] = dict(self.assignments)
        best_penalty: float = self.evaluate_candidate(best_assignment)
        # generate cartesian product of domain values
        for combo in itertools.product(self.domain, repeat=len(self.nodes)):
            candidate = {node: val for node, val in zip(self.nodes, combo)}
            penalty = self.evaluate_candidate(candidate)
            if penalty < best_penalty:
                best_assignment = candidate
                best_penalty = penalty
        # update assignments if changed
        if best_assignment != self.assignments:
            self.log(
                f"Updated assignments from {self.assignments} to {best_assignment} (penalty {best_penalty})"
            )
        else:
            self.log(f"Assignments unchanged: {self.assignments} (penalty {best_penalty})")
        self.assignments = best_assignment
        # broadcast assignments to neighbouring agents
        # determine neighbour owners: for each local node, check its neighbours in the problem
        recipients: set[str] = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    # send to owner of neighbour
                    owner = self.owners.get(nbr)
                    if owner and owner != self.name:
                        recipients.add(owner)
        # send message to each recipient with assignments mapping
        for recipient in recipients:
            # send the raw assignment mapping; BaseAgent.send will
            # route this through the communication layer.  This ensures
            # that modes like 1A (which require translation) and 1Z
            # (shared syntax) behave correctly.
            self.send(recipient, dict(self.assignments))

    # override assignment property from BaseAgent to prevent misuse
    @property
    def assignment(self) -> Any:
        """Return a representative assignment for logging purposes.

        For multi‑node agents, there is no single assignment; this
        property returns a string summarising the local assignments for
        convenience when included in global assignments.  If a specific
        node's assignment is required, refer to ``self.assignments``.
        """
        return str(self.assignments)

    @assignment.setter
    def assignment(self, value: Any) -> None:
        """Dummy setter to satisfy BaseAgent initialisation.

        The base class expects to set ``self.assignment`` during
        initialisation.  For multi‑node agents this value is unused,
        but defining a setter prevents an ``AttributeError`` when
        assigning to this property.  The setter does nothing.
        """
        # no-op: assignments are managed per-node via self.assignments
        # Logging only after the base class has initialised the logs attribute
        if hasattr(self, "logs"):
            self.log(f"Ignoring assignment setter for multi-node agent: {value}")
