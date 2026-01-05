"""Rule‑based cluster agent for graph colouring experiments.

This module defines the :class:`RuleBasedClusterAgent`, a simple
baseline agent that uses a deterministic communication protocol
instead of free‑form or LLM‑mediated messages.  The agent controls
multiple nodes (a cluster) and computes a local assignment using
either a greedy heuristic or exhaustive search, identical to
``ClusterAgent``.  However, rather than summarising its state via a
message style like ``cost_list`` or ``constraints``, it simply
transmits its current assignments to neighbouring clusters.  Incoming
assignment messages are parsed by the base classes and used to update
neighbour assignments.

The intention of this baseline is to mirror the structured,
template‑based dialogue in argumentation‑style deliberation systems.
Messages contain direct proposals (assignments) without the overhead
of natural‑language generation or interpretation.  This enables
experiments comparing free‑form communication against a simple,
transparent alternative.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from .cluster_agent import ClusterAgent


class RuleBasedClusterAgent(ClusterAgent):
    """Baseline agent that transmits explicit assignments to neighbours.

    Parameters
    ----------
    name : str
        Identifier for this cluster (typically the owner name).
    problem : GraphColoring
        The global colouring problem instance.
    comm_layer : BaseCommLayer
        Communication layer used to send and receive messages.  For
        rule‑based agents, a ``PassThroughCommLayer`` should be used
        so that structured content is not converted into natural
        language.  However, any ``BaseCommLayer`` instance is
        accepted; outgoing messages are dictionaries regardless of the
        communication layer.
    local_nodes : list[str]
        Nodes belonging to this cluster.
    owners : dict
        Mapping from node to the owner controlling it.  Used to route
        messages to neighbouring clusters.
    algorithm : str, optional
        Name of the internal optimisation algorithm to use.  Supported
        values are ``"greedy"`` and ``"maxsum"``.  Defaults to
        ``"greedy"``.
    initial_assignments : dict, optional
        Initial assignments for this cluster's nodes.  Defaults to
        random assignments.

    Notes
    -----
    This class reuses the assignment computation from ``ClusterAgent``
    via ``compute_assignments``.  It overrides ``step`` to send
    direct assignment mappings rather than cost lists, constraints or
    free‑text messages.  Incoming messages are handled by the base
    class (``ClusterAgent.receive``), which updates
    ``neighbour_assignments`` when the message contains assignments.
    """

    def __init__(
        self,
        name: str,
        problem: Any,
        comm_layer: Any,
        local_nodes: List[str],
        owners: Dict[str, str],
        algorithm: str = "greedy",
        initial_assignments: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Initialise parent with a placeholder message_type (not used)
        super().__init__(
            name=name,
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=local_nodes,
            owners=owners,
            algorithm=algorithm,
            message_type="cost_list",
            initial_assignments=initial_assignments,
        )

    def step(self) -> None:
        """Perform one iteration of the rule‑based agent's process.

        The agent computes a new assignment for its local nodes using
        the configured algorithm and then broadcasts the assignments to
        each neighbouring cluster.  Messages contain only direct
        assignments, avoiding any natural‑language formatting.
        """
        # compute new assignments using inherited method
        new_assignment = self.compute_assignments()
        if new_assignment != self.assignments:
            self.log(f"Updated assignments from {self.assignments} to {new_assignment}")
        else:
            self.log(f"Assignments unchanged: {self.assignments}")
        self.assignments = new_assignment

        # determine recipient clusters: owners of neighbouring nodes outside this cluster
        recipients: Set[str] = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    owner = self.owners.get(nbr)
                    if owner and owner != self.name:
                        recipients.add(owner)

        # build assignment dictionary for boundary nodes only
        boundary_assignments: Dict[str, Any] = {}
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    boundary_assignments[node] = self.assignments[node]
                    break
        # send assignments to each recipient
        for recipient in recipients:
            # include a message type key to ensure correct parsing on the receiving side
            self.send(recipient, {"type": "assignments", "data": boundary_assignments})