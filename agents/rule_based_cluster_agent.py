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
        # Conditional offer protocol state
        self.rb_commitments: Dict[str, Dict[str, Any]] = {}  # {sender: {node: color}} - agreed assignments
        self.rb_awaiting_response: Set[str] = set()  # Track who we need to respond to
        self.rb_proposed_nodes: Dict[str, Dict[str, Any]] = {}  # {recipient: {node: color}} - what we've already proposed
        self.rb_active_offers: Dict[str, Any] = {}  # {offer_id: RBMove}
        self.rb_accepted_offers: Set[str] = set()   # Set of accepted offer_ids

        # Two-phase workflow: configure → bargain
        self.rb_phase: str = "configure"  # "configure" or "bargain"
        self.rb_config_locked: bool = False  # Lock assignments during configuration announcement

    def step(self) -> None:
        """Perform deliberation turn using conditional offer protocol.

        Protocol:
        - ConditionalOffer (empty conditions): Unconditional proposal
        - ConditionalOffer (with conditions): "If you do X, I'll do Y"
        - Accept: Accept an offer and commit to the chain
        """
        # Compute new assignments using inherited method (unless locked)
        if not getattr(self, 'rb_config_locked', False):
            new_assignment = self.compute_assignments()
            changes = {n: v for n, v in new_assignment.items() if self.assignments.get(n) != v}

            if changes:
                self.assignments = new_assignment
                self.log(f"Updated assignments: {changes}")
            else:
                self.log(f"Assignments unchanged: {self.assignments}")
        else:
            changes = {}
            self.log(f"Assignments locked during configuration announcement")

        # Determine recipient clusters
        recipients = self._get_recipient_clusters()

        # In configure phase, don't send any moves - wait for __ANNOUNCE_CONFIG__
        if self.rb_phase == "configure":
            self.log(f"[RB Phase] In configure phase - not sending moves yet")
            return

        # Unlock assignments after first bargain step (config announcement sent)
        if getattr(self, 'rb_config_locked', False):
            self.rb_config_locked = False
            self.log(f"[RB Phase] Unlocking assignments after configuration announcement")

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

                # Log the sent move
                if move.move == "ConditionalOffer":
                    num_cond = len(move.conditions) if hasattr(move, 'conditions') and move.conditions else 0
                    num_assign = len(move.assignments) if hasattr(move, 'assignments') and move.assignments else 0
                    self.log(f"Sent ConditionalOffer {move.offer_id} to {recipient}: {num_cond} conditions, {num_assign} assignments")
                elif move.move == "Accept":
                    self.log(f"Sent Accept to {recipient}: {move.refers_to}")
                else:
                    self.log(f"Sent {move.move} to {recipient}")

                # Track conditional offers when we send them (so they appear in UI)
                if move.move == "ConditionalOffer" and move.offer_id:
                    self.rb_active_offers[move.offer_id] = move
                    num_cond = len(move.conditions) if hasattr(move, 'conditions') and move.conditions else 0
                    num_assign = len(move.assignments) if hasattr(move, 'assignments') and move.assignments else 0
                    self.log(f"[RB Track] Recorded outgoing ConditionalOffer: {move.offer_id} with {num_cond} conditions, {num_assign} assignments")

                # Track accepted offers when we accept them
                if move.move == "Accept" and hasattr(move, 'refers_to'):
                    self.rb_accepted_offers.add(move.refers_to)
                    self.log(f"[RB Track] Marked offer {move.refers_to} as accepted")

                # Mark as responded
                if recipient in self.rb_awaiting_response:
                    self.rb_awaiting_response.remove(recipient)
            elif recipient in self.rb_awaiting_response:
                # We received a message from this recipient but have no substantive response
                # In committed phase, just silently acknowledge (no need to send repeated Commits)
                self.log(f"[RB Response] No substantive response for {recipient}, silently acknowledged")
                # Mark as responded
                self.rb_awaiting_response.remove(recipient)

        # Check global satisfaction: satisfied if penalty=0 and all boundary nodes proposed correctly for ALL recipients
        current_penalty = self._compute_local_penalty()
        if current_penalty == 0.0:
            all_satisfied = True
            for recipient in recipients:
                boundary_nodes = self._get_boundary_nodes_for(recipient)
                proposed_nodes = self.rb_proposed_nodes.get(recipient, {})

                # Check if all boundary nodes for this recipient are proposed with correct colors
                for node in boundary_nodes:
                    if node not in proposed_nodes or proposed_nodes[node] != self.assignments.get(node):
                        all_satisfied = False
                        self.log(f"[Satisfaction] Not satisfied with {recipient}: {node} not proposed correctly")
                        break

                if not all_satisfied:
                    break

            if all_satisfied:
                self.satisfied = True
                self.log(f"[Satisfaction] Globally satisfied: penalty=0, all boundary nodes proposed to all recipients")
            else:
                self.satisfied = False
        else:
            self.satisfied = False
            self.log(f"[Satisfaction] Not satisfied: penalty={current_penalty:.3f}")

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
        """Generate next dialogue move using conditional offer protocol.

        New simplified protocol:
        - ConditionalOffer (empty conditions): Unconditional proposal "I'll do Y"
        - ConditionalOffer (with conditions): Conditional proposal "If you do X, I'll do Y"
        - Accept: Accept a conditional offer (commits to the chain)

        Returns
        -------
        RBMove or None
            The dialogue move to send, or None if no move is needed.
        """
        try:
            from comm.rb_protocol import RBMove, Condition, Assignment
            import time
        except ImportError:
            return None

        boundary_nodes = self._get_boundary_nodes_for(recipient)
        if not boundary_nodes:
            self.log(f"[RB Move Gen] No boundary nodes for {recipient}")
            return None

        current_penalty = self._compute_local_penalty()
        self.log(f"[RB Move Gen] Recipient: {recipient}, Boundary nodes: {boundary_nodes}, Changes: {changes}, Penalty: {current_penalty:.3f}")
        self.log(f"[RB Move Gen] Current rb_proposed_nodes: {self.rb_proposed_nodes}")
        self.log(f"[RB Move Gen] Current rb_phase: {self.rb_phase}")
        self.log(f"[RB Move Gen] Currently satisfied: {self.satisfied}")

        # Early satisfaction check: if already satisfied and all proposals sent, don't generate more moves
        if self.satisfied and current_penalty == 0.0:
            proposed_nodes = self.rb_proposed_nodes.get(recipient, {})
            all_proposed = all(
                node in proposed_nodes and proposed_nodes[node] == self.assignments.get(node)
                for node in boundary_nodes
            )
            if all_proposed:
                self.log(f"[RB Move Gen] Already satisfied with penalty=0 and all nodes proposed correctly - no more moves")
                return None

        # Get domain
        domain = getattr(self.problem, 'domain', ['red', 'green', 'blue', 'yellow'])

        # Priority 1: Evaluate ALL offers from recipient, accept BEST one
        pending_offers_from_recipient = [
            (offer_id, offer) for offer_id, offer in self.rb_active_offers.items()
            if offer_id not in self.rb_accepted_offers  # Not already accepted
            and (offer_id.split('_')[-1] if '_' in offer_id else None) == recipient
        ]

        if pending_offers_from_recipient:
            self.log(f"[RB Move Gen] Priority 1: Found {len(pending_offers_from_recipient)} pending offers from {recipient}")

            best_offer_id = None
            best_penalty = current_penalty
            best_offer = None

            # Evaluate ALL offers from this recipient
            for offer_id, offer in pending_offers_from_recipient:
                # Simulate accepting the offer:
                # - Conditions: what WE must do (change our own assignments)
                # - Assignments: what THEY will do (update neighbor beliefs)

                test_assignment = dict(self.assignments)  # Our assignments
                test_neighbors = dict(self.neighbour_assignments)  # Neighbor beliefs

                can_satisfy = True

                # Apply conditions: change OUR assignments to satisfy their conditions
                if hasattr(offer, 'conditions') and offer.conditions:
                    for cond in offer.conditions:
                        if hasattr(cond, 'node') and hasattr(cond, 'colour'):
                            if cond.node in self.nodes:
                                # This is our node - we must change it
                                test_assignment[cond.node] = cond.colour
                                self.log(f"[RB Move Gen] Condition requires us to set {cond.node}={cond.colour}")
                            else:
                                # Condition on a node we don't control - invalid offer
                                self.log(f"[RB Move Gen] Cannot satisfy condition: {cond.node} not in our cluster")
                                can_satisfy = False
                                break

                if not can_satisfy:
                    continue  # Skip this offer

                # Apply assignments: update beliefs about THEIR nodes
                if hasattr(offer, 'assignments') and offer.assignments:
                    for assign in offer.assignments:
                        if hasattr(assign, 'node') and hasattr(assign, 'colour'):
                            if assign.node not in self.nodes:
                                # This is their node - they promise to set it
                                test_neighbors[assign.node] = assign.colour
                                self.log(f"[RB Move Gen] They promise to set {assign.node}={assign.colour}")

                # Evaluate penalty with modified assignments + promised neighbor assignments
                combined = {**test_neighbors, **test_assignment}
                new_penalty = self.problem.evaluate_assignment(combined)

                self.log(f"[RB Move Gen] Evaluating offer {offer_id}: penalty {current_penalty:.3f} → {new_penalty:.3f}")

                # Track the best offer
                if new_penalty < best_penalty:
                    best_penalty = new_penalty
                    best_offer_id = offer_id
                    best_offer = offer
                    self.log(f"[RB Move Gen] -> New best offer: {offer_id} (penalty={new_penalty:.3f})")

            # Accept the best offer if it improves or maintains our situation
            # Accept if: penalty improves OR penalty stays same but we have pending offers (avoid deadlock)
            if best_offer_id and best_penalty <= current_penalty:
                self.rb_accepted_offers.add(best_offer_id)
                self.log(f"[RB Move Gen] -> Accepting offer {best_offer_id}: {current_penalty:.3f} → {best_penalty:.3f}")

                # Apply conditions: change OUR assignments to fulfill our side of the deal
                if hasattr(best_offer, 'conditions') and best_offer.conditions:
                    for cond in best_offer.conditions:
                        if hasattr(cond, 'node') and hasattr(cond, 'colour'):
                            if cond.node in self.nodes:
                                self.assignments[cond.node] = cond.colour
                                self.log(f"[RB Accept] Changed our assignment: {cond.node}={cond.colour}")
                                # Update proposed nodes to reflect new assignment (prevent re-proposing)
                                self.rb_proposed_nodes.setdefault(recipient, {})[cond.node] = cond.colour

                # Apply assignments: update beliefs about their nodes
                if hasattr(best_offer, 'assignments') and best_offer.assignments:
                    for assign in best_offer.assignments:
                        if hasattr(assign, 'node') and hasattr(assign, 'colour'):
                            if assign.node not in self.nodes:
                                self.neighbour_assignments[assign.node] = assign.colour
                                self.log(f"[RB Accept] Updated neighbor belief: {assign.node}={assign.colour}")

                return RBMove(
                    move="Accept",
                    refers_to=best_offer_id,
                    reasons=["accepted", f"penalty={current_penalty:.3f}→{best_penalty:.3f}"]
                )

        # Priority 2: Generate conditional offer with conditions (for conflicts)
        # If there are conflicts, try to find a mutually beneficial configuration
        conflicts = self._detect_conflicts(recipient)
        if conflicts and current_penalty > 0.0:
            self.log(f"[RB Move Gen] Priority 2: Conflicts detected, attempting conditional offer")

            # Check if we already have pending offers
            my_offers = [oid for oid in self.rb_active_offers.keys() if self.name in oid and oid not in self.rb_accepted_offers]
            if not my_offers:
                # Generate conditional offer via counterfactual reasoning
                conditional_offer = self._generate_conditional_offer(recipient)
                if conditional_offer:
                    self.log(f"[RB Move Gen] -> Generated ConditionalOffer with {len(conditional_offer.conditions)} conditions, {len(conditional_offer.assignments)} assignments")
                    return conditional_offer

        # Priority 3: REMOVED - No unconditional offers after configuration
        # Only configuration announcements should be unconditional
        # All bargaining must use conditional offers with IF conditions

        # Get proposed nodes for satisfaction tracking
        proposed_nodes = self.rb_proposed_nodes.get(recipient, {})

        # Priority 4: Try conditional offer even without conflicts (optimization)
        # If penalty > 0, try to find win-win configuration
        if current_penalty > 0.0 and len(boundary_nodes) >= 1:
            my_offers = [oid for oid in self.rb_active_offers.keys() if self.name in oid and oid not in self.rb_accepted_offers]
            if not my_offers:
                self.log(f"[RB Move Gen] Priority 4: Penalty > 0, attempting optimization conditional offer")
                conditional_offer = self._generate_conditional_offer(recipient)
                if conditional_offer:
                    self.log(f"[RB Move Gen] -> Generated optimization ConditionalOffer with {len(conditional_offer.conditions)} conditions, {len(conditional_offer.assignments)} assignments")
                    return conditional_offer

        # Don't mark as satisfied here - check globally after all recipients processed
        # Just return None (no more moves)
        self.log(f"[RB Move Gen] No move to send. Proposed: {list(proposed_nodes.keys())}, Boundary: {boundary_nodes}")
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

    def _generate_justification(self, node: str) -> str:
        """Generate justification for current assignment of a node.

        Parameters
        ----------
        node : str
            The node to justify.

        Returns
        -------
        str
            Justification reason string.
        """
        color = self.assignments.get(node)
        if not color:
            return "no_assignment"

        # Check if this assignment avoids conflicts
        has_conflicts = False
        for nbr in self.problem.get_neighbors(node):
            if nbr in self.neighbour_assignments:
                if self.neighbour_assignments[nbr] == color:
                    has_conflicts = True
                    break

        if not has_conflicts:
            return f"no_conflicts_with_{color}"

        # Check if it's locally optimal
        penalty = self._compute_local_penalty()
        if penalty == 0:
            return "locally_optimal_zero_penalty"

        # Otherwise just state it's current best local solution
        return f"best_local_solution_penalty_{penalty:.3f}"

    def _can_change_assignment(self, node: str) -> bool:
        """Check if node can be changed. Commits are soft-locked.

        Parameters
        ----------
        node : str
            Node to check.

        Returns
        -------
        bool
            True if the node can be changed, False otherwise.
        """
        # Cannot change fixed constraints
        if node in self.fixed_local_nodes:
            return False

        # Committed nodes can only change if challenged
        committed_nodes = self.rb_commitments.get(self.name, {})
        if node in committed_nodes:
            # Check if there's an active challenge/counter on this node
            has_active_challenge = any(
                attack.get("node") == node
                for attack in self.rb_pending_attacks
            )
            if not has_active_challenge:
                self.log(f"[Commit Guard] {node} committed, no active challenge")
                return False

        return True

    def _generate_conditional_offer(self, recipient: str) -> Optional[Any]:
        """Generate conditional offer from counterfactual reasoning.

        Enumerates possible configurations of the recipient's boundary nodes,
        finds our best response for each, and proposes the configuration that
        achieves zero penalty (if one exists).

        This implements argumentation-style reasoning: "If you do X, I can do Y,
        and we'll both be satisfied (penalty=0)."

        Parameters
        ----------
        recipient : str
            The recipient cluster name.

        Returns
        -------
        RBMove or None
            A conditional offer, or None if not applicable.
        """
        try:
            from comm.rb_protocol import RBMove, Condition, Assignment
            import time
            from itertools import product
        except ImportError:
            return None

        # Get boundary nodes for both sides
        our_boundary = self._get_boundary_nodes_for(recipient)
        if not our_boundary:
            return None

        # Get their boundary nodes (nodes they control that are adjacent to us)
        their_boundary = []
        for node in self.neighbour_assignments:
            if self.owners.get(node) == recipient:
                # Check if this node is adjacent to any of our nodes
                for nbr in self.problem.get_neighbors(node):
                    if nbr in self.nodes:
                        if node not in their_boundary:
                            their_boundary.append(node)
                        break

        if not their_boundary:
            return None

        self.log(f"[ConditionalOffer Gen] Our boundary: {our_boundary}, Their boundary: {their_boundary}")

        # Get the domain (available colors)
        domain = self.problem.domain if hasattr(self.problem, 'domain') else ['red', 'green', 'blue', 'yellow']

        # Current penalty baseline
        current_penalty = self._compute_local_penalty()
        self.log(f"[ConditionalOffer Gen] Current penalty: {current_penalty:.3f}")

        # If already at zero penalty, no need for conditional offer
        if current_penalty == 0.0:
            self.log(f"[ConditionalOffer Gen] Already at zero penalty, no offer needed")
            return None

        # Enumerate possible configurations for their boundary nodes
        # Limit search space: if too many nodes, sample or use current + alternatives
        if len(their_boundary) > 3:
            # Too many to enumerate exhaustively, use heuristic
            self.log(f"[ConditionalOffer Gen] Too many boundary nodes ({len(their_boundary)}), using current state")
            their_configs = [tuple(self.neighbour_assignments.get(n, domain[0]) for n in their_boundary)]
        else:
            # Enumerate all possible color combinations
            their_configs = list(product(domain, repeat=len(their_boundary)))
            self.log(f"[ConditionalOffer Gen] Enumerating {len(their_configs)} possible configurations")

        best_config = None
        best_our_assignment = None
        best_penalty = float('inf')

        # For each possible configuration of their nodes
        for config_idx, their_config in enumerate(their_configs):
            # Create hypothetical neighbor assignment
            hypothetical_neighbors = dict(self.neighbour_assignments)
            for i, node in enumerate(their_boundary):
                hypothetical_neighbors[node] = their_config[i]

            # Find our best response to this configuration
            # Try all possible assignments for our boundary nodes
            if len(our_boundary) > 3:
                # Use greedy for large boundary
                our_configs = [tuple(self.assignments.get(n, domain[0]) for n in our_boundary)]
            else:
                our_configs = list(product(domain, repeat=len(our_boundary)))

            for our_config in our_configs:
                # Build complete assignment
                test_assignment = dict(self.assignments)
                for i, node in enumerate(our_boundary):
                    test_assignment[node] = our_config[i]

                # Combine with hypothetical neighbor assignment
                combined = {**hypothetical_neighbors, **test_assignment}

                # Evaluate penalty
                penalty = self.problem.evaluate_assignment(combined)

                if penalty < best_penalty:
                    best_penalty = penalty
                    best_config = their_config
                    best_our_assignment = our_config

                    # If we found zero penalty, stop searching
                    if penalty == 0.0:
                        self.log(f"[ConditionalOffer Gen] Found zero-penalty configuration!")
                        break

            if best_penalty == 0.0:
                break

        # Only make an offer if we found a better configuration
        if best_config is None or best_penalty >= current_penalty:
            self.log(f"[ConditionalOffer Gen] No beneficial configuration found (best={best_penalty:.3f} vs current={current_penalty:.3f})")
            return None

        # Check if there's already a pending offer from recipient that achieves the same outcome
        # If so, accept it instead of making a duplicate counter-offer
        pending_from_recipient = [
            (offer_id, offer) for offer_id, offer in self.rb_active_offers.items()
            if offer_id not in self.rb_accepted_offers
            and (offer_id.split('_')[-1] if '_' in offer_id else None) == recipient
        ]

        for offer_id, offer in pending_from_recipient:
            # Check if this offer's conditions match what we would propose as assignments
            # and their assignments match what we would propose as conditions
            offer_matches = True

            # Their conditions should match our intended assignments
            if hasattr(offer, 'conditions') and offer.conditions:
                for cond in offer.conditions:
                    if hasattr(cond, 'node') and hasattr(cond, 'colour'):
                        if cond.node in our_boundary:
                            # Find what we would propose for this node
                            node_idx = our_boundary.index(cond.node)
                            our_proposed_color = best_our_assignment[node_idx]
                            if cond.colour != our_proposed_color:
                                offer_matches = False
                                break

            # Their assignments should match our intended conditions
            if offer_matches and hasattr(offer, 'assignments') and offer.assignments:
                for assign in offer.assignments:
                    if hasattr(assign, 'node') and hasattr(assign, 'colour'):
                        if assign.node in their_boundary:
                            # Find what we would propose for this node
                            node_idx = their_boundary.index(assign.node)
                            our_proposed_color = best_config[node_idx]
                            if assign.colour != our_proposed_color:
                                offer_matches = False
                                break

            if offer_matches:
                self.log(f"[ConditionalOffer Gen] Found matching offer from {recipient}: {offer_id}")
                self.log(f"[ConditionalOffer Gen] Instead of proposing duplicate, will accept their offer")
                # Don't generate a new offer - let Priority 1 accept this one next turn
                return None

        # Build the conditional offer
        conditions = []
        for i, node in enumerate(their_boundary):
            conditions.append(Condition(
                node=node,
                colour=best_config[i],
                owner=recipient
            ))

        assignments = []
        for i, node in enumerate(our_boundary):
            assignments.append(Assignment(
                node=node,
                colour=best_our_assignment[i]
            ))

        offer_id = f"offer_{int(time.time())}_{self.name}"

        self.log(f"[ConditionalOffer Gen] Generated offer: {len(conditions)} conditions, {len(assignments)} assignments, penalty={best_penalty:.3f}")

        return RBMove(
            move="ConditionalOffer",
            offer_id=offer_id,
            conditions=conditions,
            assignments=assignments,
            reasons=[f"penalty={best_penalty:.3f}", "mutual_benefit", "counterfactual_reasoning"]
        )

    def receive(self, message: Any) -> None:
        """Handle incoming messages, including RB protocol moves.

        Parameters
        ----------
        message : Message
            The incoming message to process.
        """
        # First call parent to handle standard message processing
        super().receive(message)

        print(f"[{self.name}] receive() called with message.content: {message.content}")
        print(f"[{self.name}] message.content type: {type(message.content)}")
        print(f"[{self.name}] Current rb_phase: {self.rb_phase}")

        # Handle special phase transition messages
        if isinstance(message.content, str) and message.content == "__ANNOUNCE_CONFIG__":
            print(f"[{self.name}] MATCHED __ANNOUNCE_CONFIG__!")
            self.log(f"[RB Phase] Received __ANNOUNCE_CONFIG__ from {message.sender}")
            self.log(f"[RB Phase] Transitioning to BARGAIN phase")
            self.rb_phase = "bargain"
            self.rb_config_locked = True  # Lock assignments during announcement

            # Immediately announce current configuration to all recipients
            try:
                from comm.rb_protocol import RBMove, Assignment
                import time
            except ImportError:
                return

            recipients = self._get_recipient_clusters()
            for recipient in recipients:
                boundary_nodes = self._get_boundary_nodes_for(recipient)
                if not boundary_nodes:
                    continue

                # Create list of all boundary assignments
                assignments = []
                for node in boundary_nodes:
                    color = self.assignments.get(node)
                    if color:
                        assignments.append(Assignment(node=node, colour=color))
                        self.log(f"[RB Phase] Including in config: {node}={color}")

                if assignments:
                    # Send as special ConfigAnnouncement move (unconditional offer with special marker)
                    offer_id = f"config_{int(time.time())}_{self.name}"
                    config_move = RBMove(
                        move="ConditionalOffer",
                        offer_id=offer_id,
                        conditions=[],  # Empty = unconditional
                        assignments=assignments,
                        reasons=["initial_configuration", "phase_transition"]
                    )

                    # Format and send immediately
                    try:
                        from comm.rb_protocol import format_rb, pretty_rb
                        msg_text = format_rb(config_move) + " " + pretty_rb(config_move)
                    except ImportError:
                        msg_text = str(config_move)

                    self.send(recipient, msg_text)
                    print(f"[{self.name}] SENT configuration announcement to {recipient}: {msg_text[:200]}")
                    self.log(f"[RB Phase] Announced configuration to {recipient}: {len(assignments)} assignments")

                    # Track this as an active offer
                    self.rb_active_offers[offer_id] = config_move
                    print(f"[{self.name}] Tracked offer {offer_id} in rb_active_offers")

                    # Mark all announced nodes as proposed so Priority 3 doesn't send them again
                    for assign in assignments:
                        self.rb_proposed_nodes.setdefault(recipient, {})[assign.node] = assign.colour
                        self.log(f"[RB Phase] Marked node {assign.node}={assign.colour} as proposed to {recipient}")
                    self.log(f"[RB Phase] Marked {len(assignments)} nodes as proposed to {recipient}")
                    self.log(f"[RB Phase] rb_proposed_nodes now: {self.rb_proposed_nodes}")

            print(f"[{self.name}] Finished processing __ANNOUNCE_CONFIG__, returning")
            return

        if isinstance(message.content, str) and message.content == "__IMPOSSIBLE__":
            self.log(f"[RB Phase] Received __IMPOSSIBLE__ signal from {message.sender}")
            self.log(f"[RB Phase] Human signaled configuration is impossible to work with")
            # Could reset or adjust strategy here
            return

        # Try to parse as RB protocol message
        try:
            from comm.rb_protocol import parse_rb
            rb_move = parse_rb(message.content)
            self.log(f"[RB Receive] Parsed RB move: {rb_move}")
            if rb_move:
                self._process_rb_move(message.sender, rb_move)
            else:
                self.log(f"[RB Receive] Failed to parse RB move from: {message.content}")
        except ImportError as e:
            self.log(f"[RB Receive] ImportError: {e}")
        except Exception as e:
            self.log(f"[RB Receive] Exception during RB parsing: {e}")

    def _process_rb_move(self, sender: str, move: Any) -> None:
        """Process received dialogue move using conditional offer protocol.

        Handles:
        - ConditionalOffer: Store offer and update beliefs from assignments
        - Accept: Mark offer as accepted and commit to our side of the deal

        Parameters
        ----------
        sender : str
            The agent who sent the move.
        move : RBMove
            The parsed dialogue move.
        """
        self.log(f"[RB Process] Processing {move.move} from {sender}")

        # Mark that we need to respond to this sender
        self.rb_awaiting_response.add(sender)

        if move.move == "ConditionalOffer":
            # They sent a conditional offer - store it for consideration
            if move.offer_id:
                self.rb_active_offers[move.offer_id] = move
                num_conditions = len(move.conditions) if hasattr(move, 'conditions') and move.conditions else 0
                num_assignments = len(move.assignments) if hasattr(move, 'assignments') and move.assignments else 0

                if num_conditions == 0:
                    self.log(f"[RB Process] Received unconditional offer {move.offer_id} from {sender} ({num_assignments} assignments)")
                else:
                    self.log(f"[RB Process] Received conditional offer {move.offer_id} from {sender} ({num_conditions} conditions, {num_assignments} assignments)")

                # Update beliefs about their assignments from the offer
                if hasattr(move, 'assignments') and move.assignments:
                    for assignment in move.assignments:
                        if hasattr(assignment, 'node') and hasattr(assignment, 'colour'):
                            if assignment.node not in self.nodes:
                                self.neighbour_assignments[assignment.node] = assignment.colour
                                self.log(f"[RB Process] -> Updated belief: {assignment.node}={assignment.colour}")

                # Track their proposed nodes from this offer
                if hasattr(move, 'assignments') and move.assignments:
                    for assignment in move.assignments:
                        if hasattr(assignment, 'node') and hasattr(assignment, 'colour'):
                            if assignment.node not in self.nodes:
                                self.rb_proposed_nodes.setdefault(sender, {})[assignment.node] = assignment.colour

        elif move.move == "Accept":
            # They accepted an offer - mark it as accepted and implement the chain
            if move.refers_to:
                self.rb_accepted_offers.add(move.refers_to)
                self.log(f"[RB Process] Offer {move.refers_to} accepted by {sender}")

                # If this was our offer, commit to our side of the deal
                if move.refers_to in self.rb_active_offers:
                    offer = self.rb_active_offers[move.refers_to]

                    # Commit to our assignments from the offer
                    if hasattr(offer, 'assignments') and offer.assignments:
                        for assignment in offer.assignments:
                            if hasattr(assignment, 'node') and hasattr(assignment, 'colour'):
                                if assignment.node in self.nodes:
                                    # This is our commitment from the offer
                                    self.rb_commitments.setdefault(self.name, {})[assignment.node] = assignment.colour
                                    self.log(f"[RB Process] -> Committing to our side of offer: {assignment.node}={assignment.colour}")

                    # Accept any conditions they specified (update our beliefs about their nodes)
                    if hasattr(offer, 'conditions') and offer.conditions:
                        for cond in offer.conditions:
                            if hasattr(cond, 'node') and hasattr(cond, 'colour'):
                                if cond.node not in self.nodes:
                                    self.neighbour_assignments[cond.node] = cond.colour
                                    # Also record as their commitment
                                    self.rb_commitments.setdefault(sender, {})[cond.node] = cond.colour
                                    self.log(f"[RB Process] -> Accepting condition: {cond.node}={cond.colour} (now committed by {sender})")

                    self.log(f"[RB Process] -> Chain acceptance complete for {move.refers_to}")