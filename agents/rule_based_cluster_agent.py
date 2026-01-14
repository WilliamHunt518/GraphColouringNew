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
        fixed_local_nodes: Optional[Dict[str, Any]] = None,
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
            fixed_local_nodes=fixed_local_nodes,
        )
        # Argumentation state for deliberation dialogue
        self.rb_commitments: Dict[str, Any] = {}
        self.rb_pending_attacks: List[Dict] = []
        self.rb_dialogue_state: Dict[str, str] = {}
        self.rb_last_move: Optional[Any] = None

    def step(self) -> None:
        """Perform rule-based deliberation turn using Parsons & Tang 2006 protocol.

        Implements PROPOSE/ATTACK/CONCEDE dialogue moves for argumentation-based
        negotiation over graph coloring assignments.
        """
        # Compute new assignments using inherited method
        new_assignment = self.compute_assignments()
        changes = {n: v for n, v in new_assignment.items() if self.assignments.get(n) != v}

        if changes:
            self.assignments = new_assignment
            self.log(f"Updated assignments: {changes}")
        else:
            self.log(f"Assignments unchanged: {self.assignments}")

        # Determine recipient clusters
        recipients = self._get_recipient_clusters()

        # Generate and send RB dialogue moves to each recipient
        for recipient in recipients:
            move = self._generate_rb_move(recipient, changes)
            if move:
                # Import here to avoid circular imports
                try:
                    from comm.rb_protocol import format_rb, pretty_rb
                    msg_text = format_rb(move) + " " + pretty_rb(move)
                except ImportError:
                    # Fallback if rb_protocol not available
                    msg_text = str(move)
                self.send(recipient, msg_text)
                self.log(f"Sent {move.move} to {recipient}: {move.node}={move.colour}")

    def _get_recipient_clusters(self) -> List[str]:
        """Get list of neighbouring clusters."""
        recipients: Set[str] = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    owner = self.owners.get(nbr)
                    if owner and owner != self.name:
                        recipients.add(owner)
        return list(recipients)

    def _generate_rb_move(self, recipient: str, changes: Dict[str, Any]) -> Optional[Any]:
        """Generate next RB dialogue move based on current state and dialogue phase.

        Returns
        -------
        RBMove or None
            The dialogue move to send, or None if no move is needed.
        """
        try:
            from comm.rb_protocol import RBMove
        except ImportError:
            return None

        boundary_nodes = self._get_boundary_nodes_for(recipient)
        if not boundary_nodes:
            return None

        phase = self.rb_dialogue_state.get(recipient, "init")

        # Priority 1: CONCEDE to pending attacks
        if self.rb_pending_attacks:
            attack = self.rb_pending_attacks.pop(0)
            if attack.get("sender") == recipient and attack.get("node") in self.nodes:
                node = attack["node"]
                # Accept the attack by proposing a different color
                current_color = self.assignments.get(node)
                reasons = attack.get("reasons", [])
                return RBMove(
                    move="CONCEDE",
                    node=node,
                    colour=current_color,
                    reasons=["accepted_constraint"] + reasons
                )

        # Priority 2: ATTACK on detected conflicts
        conflicts = self._detect_conflicts(recipient)
        if conflicts:
            node, expected_color = conflicts[0]
            return RBMove(
                move="ATTACK",
                node=node,
                colour=expected_color,
                reasons=[f"conflict_on_boundary", f"penalty={self._compute_local_penalty():.3f}"]
            )

        # Priority 3: PROPOSE changes on boundary nodes
        if phase == "init" or changes:
            for node in boundary_nodes:
                if node in changes:
                    return RBMove(
                        move="PROPOSE",
                        node=node,
                        colour=changes[node],
                        reasons=[f"local_optimal", f"penalty={self._compute_local_penalty():.3f}"]
                    )

            # Also propose current assignment if not changed but in init phase
            if phase == "init" and boundary_nodes:
                node = boundary_nodes[0]
                return RBMove(
                    move="PROPOSE",
                    node=node,
                    colour=self.assignments.get(node),
                    reasons=["initial_proposal"]
                )

        # Update dialogue phase
        if phase == "init":
            self.rb_dialogue_state[recipient] = "negotiating"

        return None

    def _get_boundary_nodes_for(self, recipient: str) -> List[str]:
        """Get nodes in this cluster adjacent to recipient's cluster."""
        boundary = []
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if self.owners.get(nbr) == recipient:
                    if node not in boundary:
                        boundary.append(node)
                    break
        return boundary

    def _detect_conflicts(self, recipient: str) -> List[tuple]:
        """Detect conflicts with recipient's believed assignments.

        Returns
        -------
        List[Tuple[str, Any]]
            List of (node, expected_color) tuples where conflicts exist.
        """
        conflicts = []
        for node in self.nodes:
            my_color = self.assignments.get(node)
            for nbr in self.problem.get_neighbors(node):
                if self.owners.get(nbr) == recipient:
                    nbr_color = self.neighbour_assignments.get(nbr)
                    if nbr_color is not None and nbr_color == my_color:
                        # Conflict detected: same color on adjacent nodes
                        conflicts.append((node, None))  # Will need to change our color
        return conflicts

    def _compute_local_penalty(self) -> float:
        """Compute penalty based on local and known neighbour assignments."""
        combined = {**self.neighbour_assignments, **self.assignments}
        return self.problem.evaluate_assignment(combined)

    def receive(self, message: Any) -> None:
        """Handle incoming messages, including RB protocol moves.

        Parameters
        ----------
        message : Message
            The incoming message to process.
        """
        # First call parent to handle standard message processing
        super().receive(message)

        # Try to parse as RB protocol message
        try:
            from comm.rb_protocol import parse_rb
            rb_move = parse_rb(message.content)
            if rb_move:
                self._process_rb_move(message.sender, rb_move)
        except ImportError:
            pass
        except Exception:
            pass

    def _process_rb_move(self, sender: str, move: Any) -> None:
        """Process received RB dialogue move.

        Parameters
        ----------
        sender : str
            The agent who sent the move.
        move : RBMove
            The parsed dialogue move.
        """
        if move.move == "PROPOSE":
            # Update our belief about their assignment
            if move.node and move.node not in self.nodes and move.colour:
                self.neighbour_assignments[move.node] = move.colour
                self.log(f"Received PROPOSE from {sender}: {move.node}={move.colour}")

        elif move.move == "ATTACK":
            # They are attacking our assignment - queue for response
            if move.node and move.node in self.nodes:
                self.rb_pending_attacks.append({
                    "sender": sender,
                    "node": move.node,
                    "colour": move.colour,
                    "reasons": move.reasons or []
                })
                self.log(f"Received ATTACK from {sender} on {move.node}, reasons: {move.reasons}")

        elif move.move == "CONCEDE":
            # They accepted our position or changed their assignment
            if move.node and move.node not in self.nodes and move.colour:
                self.neighbour_assignments[move.node] = move.colour
                self.log(f"Received CONCEDE from {sender}: {move.node}={move.colour}")