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

from typing import Any, Dict, List, Optional, Set, Tuple

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
        self.rb_rejected_offers: Set[str] = set()   # Set of rejected offer_ids
        self.rb_rejected_conditions: Dict[str, Set[tuple]] = {}  # {recipient: set of rejected condition tuples}
        self.rb_impossible_conditions: Dict[str, Set[Tuple[str, str]]] = {}  # {recipient: {(node, color), ...}}
        self.rb_impossible_combinations: Dict[str, Set[FrozenSet[Tuple[str, str]]]] = {}  # {recipient: {frozenset({(n1,c1), (n2,c2)}), ...}}
        self.rb_offer_timestamps: Dict[str, float] = {}  # {offer_id: timestamp} - track when offers were sent
        self.rb_offer_iteration: Dict[str, int] = {}  # {offer_id: iteration} - track iteration when offer was sent
        self.rb_iteration_counter: int = 0  # Track iterations for offer expiry

        # Two-phase workflow: configure -> bargain
        self.rb_phase: str = "configure"  # "configure" or "bargain"
        self.rb_config_locked: bool = False  # Lock assignments during configuration announcement

    def step(self) -> None:
        """Perform deliberation turn using conditional offer protocol.

        Protocol:
        - ConditionalOffer (empty conditions): Unconditional proposal
        - ConditionalOffer (with conditions): "If you do X, I'll do Y"
        - Accept: Accept an offer and commit to the chain
        """
        # Increment iteration counter for offer expiry tracking
        self.rb_iteration_counter += 1

        # Clean up expired offers (offers with no response after 5 iterations)
        self._expire_old_offers()

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
                    import time
                    self.rb_active_offers[move.offer_id] = move
                    self.rb_offer_timestamps[move.offer_id] = time.time()
                    self.rb_offer_iteration[move.offer_id] = self.rb_iteration_counter
                    num_cond = len(move.conditions) if hasattr(move, 'conditions') and move.conditions else 0
                    num_assign = len(move.assignments) if hasattr(move, 'assignments') and move.assignments else 0
                    self.log(f"[RB Track] Recorded outgoing ConditionalOffer: {move.offer_id} with {num_cond} conditions, {num_assign} assignments")

                    # Update rb_proposed_nodes to track what we told this recipient
                    # This prevents Priority 0 from repeatedly sending the same boundary update
                    if hasattr(move, 'assignments') and move.assignments:
                        for assign in move.assignments:
                            if hasattr(assign, 'node') and hasattr(assign, 'colour'):
                                # Only track our own nodes (boundary nodes)
                                if assign.node in self.nodes:
                                    self.rb_proposed_nodes.setdefault(recipient, {})[assign.node] = assign.colour
                                    self.log(f"[RB Track] Updated proposed: {recipient} now knows {assign.node}={assign.colour}")

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
        # BUT: We must still evaluate and respond to pending offers from the recipient!
        pending_offers_to_check = [
            offer_id for offer_id, offer in self.rb_active_offers.items()
            if offer_id not in self.rb_accepted_offers
            and offer_id not in self.rb_rejected_offers
            and f"_{recipient}" in offer_id
        ]

        if self.satisfied and current_penalty == 0.0 and not pending_offers_to_check:
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

        # Priority 0: Announce boundary node changes IMMEDIATELY
        # This is CRITICAL: if our boundary assignments differ from what we last told
        # this recipient, we MUST send an update. Otherwise they operate on stale information.
        # Check if ANY boundary node has changed since last proposal to this recipient
        proposed_nodes = self.rb_proposed_nodes.get(recipient, {})
        needs_update = False
        boundary_updates = {}

        self.log(f"[RB Move Gen] Priority 0 check: comparing current vs proposed for {recipient}")
        self.log(f"[RB Move Gen]   Boundary nodes: {boundary_nodes}")
        self.log(f"[RB Move Gen]   proposed_nodes: {proposed_nodes}")

        for node in boundary_nodes:
            current_color = self.assignments.get(node)
            proposed_color = proposed_nodes.get(node)
            self.log(f"[RB Move Gen]   {node}: current={current_color}, proposed={proposed_color}")
            if current_color != proposed_color:
                needs_update = True
                boundary_updates[node] = current_color
                self.log(f"[RB Move Gen] Boundary node {node} changed: {proposed_color} -> {current_color}")

        if needs_update:
            self.log(f"[RB Move Gen] Priority 0: Boundary state differs from last proposal")
            self.log(f"[RB Move Gen] Need to announce updates: {boundary_updates}")

            # Build a ConditionalOffer directly to announce our current boundary state
            # We can't use _generate_conditional_offer() because it returns None at penalty=0
            # But we MUST announce boundary changes regardless of penalty
            try:
                from comm.rb_protocol import RBMove, Assignment
                import time

                assignments = []
                for node in boundary_nodes:
                    current_color = self.assignments.get(node)
                    if current_color:
                        assignments.append(Assignment(node, current_color))

                if assignments:
                    offer_id = f"update_{int(time.time())}_{self.name}"
                    boundary_update_offer = RBMove(
                        move="ConditionalOffer",
                        offer_id=offer_id,
                        conditions=[],  # Unconditional announcement
                        assignments=assignments,
                        reasons=["boundary_update", f"penalty={current_penalty:.3f}"]
                    )

                    self.log(f"[RB Move Gen] -> Sending boundary update ConditionalOffer: {len(assignments)} assignments")
                    return boundary_update_offer
                else:
                    self.log(f"[RB Move Gen] No assignments to announce")
            except Exception as e:
                self.log(f"[RB Move Gen] Error building boundary update offer: {e}")

        # Priority 1: Evaluate ALL offers from recipient, accept BEST one
        # Find offers FROM this recipient (sender in message is the recipient we're responding to)
        # The offer_id format is "offer_<timestamp>_<SENDER>" or "config_<timestamp>_<SENDER>"
        # So we check if the recipient name appears in the offer_id as the sender
        pending_offers_from_recipient = [
            (offer_id, offer) for offer_id, offer in self.rb_active_offers.items()
            if offer_id not in self.rb_accepted_offers  # Not already accepted
            and offer_id not in self.rb_rejected_offers  # Not already rejected
            and f"_{recipient}" in offer_id  # Check if recipient name is in offer_id as sender
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

                self.log(f"[RB Move Gen] Evaluating offer {offer_id}: penalty {current_penalty:.3f} -> {new_penalty:.3f}")

                # Track the best offer (accept if improves OR maintains)
                if new_penalty <= best_penalty:
                    best_penalty = new_penalty
                    best_offer_id = offer_id
                    best_offer = offer
                    self.log(f"[RB Move Gen] -> New best offer: {offer_id} (penalty={new_penalty:.3f})")

            # Accept the best offer if it improves or maintains our situation
            # Accept if: penalty improves OR penalty stays same but we have pending offers (avoid deadlock)
            if best_offer_id and best_penalty <= current_penalty:
                self.rb_accepted_offers.add(best_offer_id)
                self.log(f"[RB Move Gen] -> Accepting offer {best_offer_id}: {current_penalty:.3f} -> {best_penalty:.3f}")

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
                    reasons=["accepted", f"penalty={current_penalty:.3f}->{best_penalty:.3f}"]
                )

            # If we had offers but couldn't accept any (they all worsen our situation),
            # explicitly reject the most recent one
            elif pending_offers_from_recipient:
                # We have offers but couldn't accept any - reject the most recent one
                latest_offer_id = pending_offers_from_recipient[-1][0]  # Get last offer

                self.log(f"[RB Move Gen] -> Rejecting offer {latest_offer_id} (all offers unacceptable)")

                # Mark as rejected so we don't keep evaluating it
                self.rb_rejected_offers.add(latest_offer_id)

                return RBMove(
                    move="Reject",
                    refers_to=latest_offer_id,
                    reasons=["unacceptable", "penalty_increase", "seeking_better_solution"]
                )

        # Priority 2: Generate conditional offer with conditions (for conflicts)
        # If there are conflicts, try to find a mutually beneficial configuration
        conflicts = self._detect_conflicts(recipient)
        if conflicts and current_penalty > 0.0:
            self.log(f"[RB Move Gen] Priority 2: Conflicts detected, attempting conditional offer")

            # Check if we already have pending CONDITIONAL offers (not status updates)
            # Status updates (update_xxx) don't count - they're just announcements
            my_offers = [
                oid for oid in self.rb_active_offers.keys()
                if self.name in oid
                and oid not in self.rb_accepted_offers
                and oid not in self.rb_rejected_offers  # Exclude rejected offers
                and not oid.startswith("update_")  # Exclude status updates
                and not oid.startswith("config_")  # Exclude initial configs
            ]
            if not my_offers:
                # Generate conditional offer via counterfactual reasoning
                conditional_offer = self._generate_conditional_offer(recipient)
                if conditional_offer:
                    self.log(f"[RB Move Gen] -> Generated ConditionalOffer with {len(conditional_offer.conditions)} conditions, {len(conditional_offer.assignments)} assignments")
                    return conditional_offer
            else:
                self.log(f"[RB Move Gen] ⏳ Skipping Priority 2 - already have {len(my_offers)} pending offer(s): {my_offers}")
                self.log(f"[RB Move Gen] ⏳ Waiting for response before generating new offers (offers expire after 5 iterations)")

        # Priority 3: REMOVED - No unconditional offers after configuration
        # Only configuration announcements should be unconditional
        # All bargaining must use conditional offers with IF conditions

        # Get proposed nodes for satisfaction tracking
        proposed_nodes = self.rb_proposed_nodes.get(recipient, {})

        # Priority 4: Try conditional offer even without conflicts (optimization)
        # If penalty > 0, try to find win-win configuration
        if current_penalty > 0.0 and len(boundary_nodes) >= 1:
            # Check if we already have pending CONDITIONAL offers (not status updates)
            my_offers = [
                oid for oid in self.rb_active_offers.keys()
                if self.name in oid
                and oid not in self.rb_accepted_offers
                and oid not in self.rb_rejected_offers  # Exclude rejected offers
                and not oid.startswith("update_")  # Exclude status updates
                and not oid.startswith("config_")  # Exclude initial configs
            ]
            if not my_offers:
                self.log(f"[RB Move Gen] Priority 4: Penalty > 0, attempting optimization conditional offer")
                conditional_offer = self._generate_conditional_offer(recipient)
                if conditional_offer:
                    self.log(f"[RB Move Gen] -> Generated optimization ConditionalOffer with {len(conditional_offer.conditions)} conditions, {len(conditional_offer.assignments)} assignments")
                    return conditional_offer
            else:
                self.log(f"[RB Move Gen] ⏳ Skipping Priority 4 - already have {len(my_offers)} pending offer(s): {my_offers}")
                self.log(f"[RB Move Gen] ⏳ Waiting for response before generating new offers (offers expire after 5 iterations)")

        # Don't mark as satisfied here - check globally after all recipients processed
        # Just return None (no more moves)
        self.log(f"[RB Move Gen] No move to send. Proposed: {list(proposed_nodes.keys())}, Boundary: {boundary_nodes}")

        # Diagnostic logging
        self.log(f"[RB Move Gen] 📊 State: penalty={current_penalty:.3f}, has_conflicts={current_penalty > 0.0}")
        self.log(f"[RB Move Gen] 📊 Active offers: {len(self.rb_active_offers)}, Rejected: {len(self.rb_rejected_offers)}")
        impossible_count = len(self.rb_impossible_conditions.get(recipient, set()))
        self.log(f"[RB Move Gen] 📊 Impossible conditions from {recipient}: {impossible_count}")

        if current_penalty > 0:
            self.log(f"[RB Move Gen] ⚠️ Agent has penalty > 0 but cannot generate offers")
            self.log(f"[RB Move Gen] ⚠️ This may indicate: blocked by pending offers, or all configs filtered")

        return None

    def _expire_old_offers(self) -> None:
        """Expire old offers that haven't received a response.

        This prevents deadlock where an agent sends an offer that goes unanswered,
        blocking new offers from being generated. After OFFER_EXPIRY_ITERATIONS
        iterations, unanswered offers are moved to rejected_offers.
        """
        OFFER_EXPIRY_ITERATIONS = 5  # Expire after 5 iterations with no response

        expired_offers = []
        for offer_id in list(self.rb_active_offers.keys()):
            # Skip if already accepted or rejected
            if offer_id in self.rb_accepted_offers or offer_id in self.rb_rejected_offers:
                continue

            # Only expire offers WE sent (not offers FROM others)
            if self.name not in offer_id:
                continue

            # Check if offer has expired (based on iteration counter)
            offer_iteration = self.rb_offer_iteration.get(offer_id, 0)
            iterations_since_offer = self.rb_iteration_counter - offer_iteration

            if iterations_since_offer >= OFFER_EXPIRY_ITERATIONS:
                expired_offers.append(offer_id)

        # Move expired offers to rejected set to allow new offers
        for offer_id in expired_offers:
            self.log(f"[RB Expiry] Offer {offer_id} expired after {OFFER_EXPIRY_ITERATIONS} iterations with no response - allowing new offers")
            self.rb_rejected_offers.add(offer_id)
            if offer_id in self.rb_active_offers:
                del self.rb_active_offers[offer_id]
            if offer_id in self.rb_offer_timestamps:
                del self.rb_offer_timestamps[offer_id]
            if offer_id in self.rb_offer_iteration:
                del self.rb_offer_iteration[offer_id]

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

        # NEW: Filter out configurations containing impossible conditions
        filtered_impossible = False
        if recipient in self.rb_impossible_conditions:
            impossible_set = self.rb_impossible_conditions[recipient]
            original_count = len(their_configs)

            filtered_configs = []
            for config in their_configs:
                config_pairs = [(their_boundary[i], config[i]) for i in range(len(their_boundary))]
                has_impossible = any(pair in impossible_set for pair in config_pairs)
                if not has_impossible:
                    filtered_configs.append(config)

            their_configs = filtered_configs
            self.log(f"[ConditionalOffer Gen] Filtered out {original_count - len(filtered_configs)} configs with impossible conditions")
            self.log(f"[ConditionalOffer Gen] Remaining configs: {len(their_configs)}")

            if original_count > len(filtered_configs):
                filtered_impossible = True

            if not their_configs:
                self.log(f"[ConditionalOffer Gen] All configurations contain impossible conditions - cannot generate offer")
                return None

        # NEW: Filter out configurations containing impossible combinations
        if recipient in self.rb_impossible_combinations:
            impossible_combos = self.rb_impossible_combinations[recipient]
            original_count = len(their_configs)

            filtered_configs = []
            for config in their_configs:
                config_set = frozenset((their_boundary[i], config[i]) for i in range(len(their_boundary)))

                # Check if ANY impossible combo is subset of this config
                has_impossible_combo = any(
                    impossible_combo.issubset(config_set)
                    for impossible_combo in impossible_combos
                )

                if not has_impossible_combo:
                    filtered_configs.append(config)

            their_configs = filtered_configs
            self.log(f"[ConditionalOffer Gen] Filtered {original_count - len(filtered_configs)} configs with impossible combos")

            if original_count > len(filtered_configs):
                filtered_impossible = True

            if not their_configs:
                self.log(f"[ConditionalOffer Gen] All configurations contain impossible combinations - cannot generate offer")
                return None

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

        # Allow offers that don't improve penalty if we have conflicts (need coordination)
        # This prevents agent from going silent when it can't improve alone
        has_conflicts = current_penalty > 0.0

        if has_conflicts:
            # When there are conflicts, accept same-penalty offers (coordination needed)
            penalty_threshold = current_penalty
            self.log(f"[ConditionalOffer Gen] Conflicts present - allowing coordination offers at same penalty")
        elif filtered_impossible:
            # After filtering impossible, also accept same-penalty
            penalty_threshold = current_penalty
        else:
            # Normal case: require improvement
            penalty_threshold = current_penalty - 0.01

        if best_config is None or best_penalty > penalty_threshold:
            if has_conflicts and best_config is not None and best_penalty == current_penalty:
                # Log but continue - we want coordination offers even at same penalty
                self.log(f"[ConditionalOffer Gen] Generating coordination offer (no solo improvement possible)")
                # Don't return None - allow the offer to be generated below
            else:
                # True failure - no valid offer to make
                if filtered_impossible:
                    self.log(f"[ConditionalOffer Gen] No beneficial configuration found after filtering impossible conditions (best={best_penalty:.3f} vs current={current_penalty:.3f})")
                else:
                    self.log(f"[ConditionalOffer Gen] No beneficial configuration found (best={best_penalty:.3f} vs current={current_penalty:.3f})")
                return None

        # Check if this proposal was already rejected by the recipient
        # Build tuple of conditions we're about to propose
        proposed_conditions_tuple = tuple(sorted((their_boundary[i], best_config[i]) for i in range(len(their_boundary))))

        # Check against rejected conditions from this recipient
        if recipient in self.rb_rejected_conditions:
            if proposed_conditions_tuple in self.rb_rejected_conditions[recipient]:
                self.log(f"[ConditionalOffer Gen] Skipping - conditions already rejected by {recipient}: {proposed_conditions_tuple}")
                self.log(f"[ConditionalOffer Gen] Finding alternative solution...")

                # Try to find second-best configuration
                # Sort all configurations by penalty and try the next best one
                all_configs_with_penalty = []
                for config_idx, their_config in enumerate(their_configs):
                    hypothetical_neighbors = dict(self.neighbour_assignments)
                    for i, node in enumerate(their_boundary):
                        hypothetical_neighbors[node] = their_config[i]

                    for our_config in (our_configs if len(our_boundary) <= 3 else [tuple(self.assignments.get(n, domain[0]) for n in our_boundary)]):
                        test_assignment = dict(self.assignments)
                        for i, node in enumerate(our_boundary):
                            test_assignment[node] = our_config[i]

                        combined = {**hypothetical_neighbors, **test_assignment}
                        penalty = self.problem.evaluate_assignment(combined)

                        # Check if this configuration was rejected
                        config_tuple = tuple(sorted((their_boundary[i], their_config[i]) for i in range(len(their_boundary))))
                        if config_tuple not in self.rb_rejected_conditions[recipient]:
                            # NEW: Also check if config contains impossible conditions
                            if recipient in self.rb_impossible_conditions:
                                config_pairs = [(their_boundary[i], their_config[i]) for i in range(len(their_boundary))]
                                has_impossible = any(pair in self.rb_impossible_conditions[recipient] for pair in config_pairs)
                                if has_impossible:
                                    continue  # Skip this config

                            all_configs_with_penalty.append((penalty, their_config, our_config))

                # Sort by penalty and pick the best non-rejected one
                if all_configs_with_penalty:
                    all_configs_with_penalty.sort(key=lambda x: x[0])
                    alt_penalty, alt_their_config, alt_our_config = all_configs_with_penalty[0]

                    # Accept alternatives even if they have same penalty (or worse, up to a threshold)
                    # After rejection, we need to explore other options even if suboptimal
                    penalty_threshold = current_penalty + 20.0  # Allow some slack for exploration

                    if alt_penalty <= penalty_threshold:
                        self.log(f"[ConditionalOffer Gen] Found alternative solution with penalty={alt_penalty:.3f} (was {current_penalty:.3f})")
                        best_penalty = alt_penalty
                        best_config = alt_their_config
                        best_our_assignment = alt_our_config
                    else:
                        self.log(f"[ConditionalOffer Gen] No acceptable alternative found (best_alt={alt_penalty:.3f} vs current={current_penalty:.3f}, threshold={penalty_threshold:.3f})")
                        return None
                else:
                    self.log(f"[ConditionalOffer Gen] All configurations have been rejected")
                    return None

        # Check if there's already a pending offer from recipient that achieves the same outcome
        # If so, accept it instead of making a duplicate counter-offer
        pending_from_recipient = [
            (offer_id, offer) for offer_id, offer in self.rb_active_offers.items()
            if offer_id not in self.rb_accepted_offers
            and f"_{recipient}" in offer_id  # Check if recipient name is in offer_id as sender
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

        # Check if we already have an identical PENDING offer to THIS recipient
        # (not just any identical offer ever made)
        our_pending_offers_to_recipient = [
            (offer_id, offer) for offer_id, offer in self.rb_active_offers.items()
            if offer_id not in self.rb_accepted_offers
            and offer_id not in self.rb_rejected_offers  # Exclude rejected
            and self.name in offer_id  # Our offers
            and offer_id not in [oid for oid, _ in pending_from_recipient]  # Not their offers to us
        ]

        for offer_id, offer in our_pending_offers_to_recipient:
            # Check if this offer has the same conditions and assignments
            offer_identical = True

            # Compare conditions
            if hasattr(offer, 'conditions') and offer.conditions:
                if len(offer.conditions) != len(their_boundary):
                    offer_identical = False
                else:
                    for cond in offer.conditions:
                        if hasattr(cond, 'node') and hasattr(cond, 'colour'):
                            if cond.node in their_boundary:
                                node_idx = their_boundary.index(cond.node)
                                if cond.colour != best_config[node_idx]:
                                    offer_identical = False
                                    break
            else:
                offer_identical = False

            # Compare assignments
            if offer_identical and hasattr(offer, 'assignments') and offer.assignments:
                if len(offer.assignments) != len(our_boundary):
                    offer_identical = False
                else:
                    for assign in offer.assignments:
                        if hasattr(assign, 'node') and hasattr(assign, 'colour'):
                            if assign.node in our_boundary:
                                node_idx = our_boundary.index(assign.node)
                                if assign.colour != best_our_assignment[node_idx]:
                                    offer_identical = False
                                    break
            else:
                if not (hasattr(offer, 'assignments') and offer.assignments):
                    offer_identical = False

            if offer_identical:
                self.log(f"[ConditionalOffer Gen] Already have identical offer {offer_id} outstanding, not creating duplicate")
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

            # CLEAN UP OLD OFFERS FROM PREVIOUS ROUND
            old_offer_count = len(self.rb_active_offers)
            self.rb_active_offers.clear()
            self.rb_accepted_offers.clear()
            self.rb_rejected_offers.clear()
            self.rb_rejected_conditions.clear()  # Clear rejected condition memory
            self.rb_impossible_conditions.clear()  # Clear impossible conditions
            self.rb_impossible_combinations.clear()  # Clear impossible combinations
            self.log(f"[RB Phase] Cleared {old_offer_count} old offers, rejected conditions, and impossible constraints from previous round")

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
                    self.rb_offer_timestamps[offer_id] = time.time()
                    self.rb_offer_iteration[offer_id] = self.rb_iteration_counter
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

        if move.move == "FeasibilityQuery":
            self.log(f"[RB Process] Received feasibility query from {sender}")

            if hasattr(move, 'conditions') and move.conditions:
                # Build hypothetical neighbor configuration
                test_neighbors = dict(self.neighbour_assignments)

                for cond in move.conditions:
                    if hasattr(cond, 'node') and hasattr(cond, 'colour'):
                        test_neighbors[cond.node] = cond.colour
                        self.log(f"[RB Feasibility] Evaluating with {cond.node}={cond.colour}")

                # Find if we can achieve penalty=0 with these neighbor conditions
                # We need to solve for our ENTIRE cluster, not just boundary nodes
                self.log(f"[RB Feasibility] Running exhaustive search for full cluster solution")

                # Temporarily set neighbor assignments to test conditions
                old_neighbors = dict(self.neighbour_assignments)
                self.neighbour_assignments.update(test_neighbors)

                # Run local solver to get best full coloring
                # CRITICAL: Must use EXHAUSTIVE search, not greedy!
                # Greedy can fail to find solution even when one exists
                old_algorithm = self.algorithm
                self.algorithm = "maxsum"  # Force exhaustive search

                try:
                    # Use the parent class's compute_assignments method
                    best_assignment = self.compute_assignments()

                    # Evaluate the penalty for this assignment
                    best_penalty = self.evaluate_candidate(best_assignment)

                    self.log(f"[RB Feasibility] Solver result: penalty={best_penalty}")

                finally:
                    # Restore original state
                    self.algorithm = old_algorithm
                    self.neighbour_assignments = old_neighbors

                # Build response - ONLY feasible if penalty is exactly 0
                is_feasible = (best_penalty == 0.0)

                if is_feasible:
                    details = "Yes, I can achieve a valid coloring (zero conflicts) with those conditions"
                else:
                    if best_penalty < float('inf'):
                        details = f"No valid coloring possible - best I can do has {int(best_penalty)} conflicts"
                    else:
                        details = "No valid coloring possible with those conditions"

                self.log(f"[RB Feasibility] Result: feasible={is_feasible}, penalty={best_penalty:.1f}")

                # Send response immediately
                try:
                    from comm.rb_protocol import RBMove, format_rb, pretty_rb

                    response = RBMove(
                        move="FeasibilityResponse",
                        refers_to=move.query_id if hasattr(move, 'query_id') else None,
                        is_feasible=is_feasible,
                        feasibility_penalty=best_penalty if is_feasible else None,
                        feasibility_details=details,
                        reasons=["feasibility_evaluation"]
                    )

                    msg_text = format_rb(response) + " " + pretty_rb(response)
                    self.send(sender, msg_text)
                    self.log(f"[RB Feasibility] Sent response to {sender}")

                    # Remove from awaiting response since we already responded
                    self.rb_awaiting_response.discard(sender)

                except Exception as e:
                    self.log(f"[RB Feasibility] Error building response: {e}")

            return

        if move.move == "ConditionalOffer":
            # If this is a counter-offer to one of our pending offers, mark ours as superseded
            # (They've moved on, so our old offer is no longer relevant in current context)
            our_offers_to_sender = [
                oid for oid in self.rb_active_offers.keys()
                if self.name in oid
                and oid not in self.rb_accepted_offers
                and oid not in self.rb_rejected_offers
            ]
            if our_offers_to_sender:
                for old_oid in our_offers_to_sender:
                    self.log(f"[RB Process] Superseding our old offer {old_oid} - {sender} sent new counter-offer")
                    # Move to rejected set so it's no longer considered
                    self.rb_rejected_offers.add(old_oid)
                    if old_oid in self.rb_active_offers:
                        del self.rb_active_offers[old_oid]

            # They sent a conditional offer - store it for consideration
            if move.offer_id:
                import time
                self.rb_active_offers[move.offer_id] = move
                self.rb_offer_timestamps[move.offer_id] = time.time()
                self.rb_offer_iteration[move.offer_id] = self.rb_iteration_counter
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

                # Note: We do NOT track their nodes in rb_proposed_nodes - that dict is only for
                # tracking what WE have proposed to THEM (our own boundary nodes), not what they
                # proposed to us (their boundary nodes). Tracking their nodes here was causing
                # the agent to incorrectly think it had already proposed everything.

        elif move.move == "Reject":
            self.log(f"[RB Process] Processing Reject from {sender}")
            if move.refers_to:
                # They rejected our offer - extract and remember the conditions
                if move.refers_to in self.rb_active_offers:
                    rejected_offer = self.rb_active_offers[move.refers_to]

                    # NEW: Process impossible conditions if specified
                    if hasattr(move, 'impossible_conditions') and move.impossible_conditions:
                        if sender not in self.rb_impossible_conditions:
                            self.rb_impossible_conditions[sender] = set()

                        for imp_cond in move.impossible_conditions:
                            node = imp_cond.get("node")
                            colour = imp_cond.get("colour")
                            if node and colour:
                                self.rb_impossible_conditions[sender].add((node, colour))
                                self.log(f"[RB Process] Stored IMPOSSIBLE condition from {sender}: {node}={colour}")

                        self.log(f"[RB Process] Total impossible conditions from {sender}: {len(self.rb_impossible_conditions[sender])}")

                    # NEW: Process impossible combinations if specified
                    if hasattr(move, 'impossible_combinations') and move.impossible_combinations:
                        if sender not in self.rb_impossible_combinations:
                            self.rb_impossible_combinations[sender] = set()

                        for combo in move.impossible_combinations:
                            combo_frozenset = frozenset(
                                (ic.get("node"), ic.get("colour"))
                                for ic in combo
                                if ic.get("node") and ic.get("colour")
                            )

                            if combo_frozenset:
                                self.rb_impossible_combinations[sender].add(combo_frozenset)
                                combo_str = " AND ".join(f"{n}={c}" for n, c in sorted(combo_frozenset))
                                self.log(f"[RB Process] Stored impossible COMBINATION: ({combo_str})")

                        self.log(f"[RB Process] Total combinations from {sender}: {len(self.rb_impossible_combinations[sender])}")

                    # EXISTING: Extract conditions that were rejected (full combination)
                    if hasattr(rejected_offer, 'conditions') and rejected_offer.conditions:
                        # Build tuple of (node, color) for rejected conditions
                        rejected_conditions_tuple = tuple(sorted(
                            (c.node, c.colour) for c in rejected_offer.conditions
                            if hasattr(c, 'node') and hasattr(c, 'colour')
                        ))

                        # Store so we don't propose this again
                        if rejected_conditions_tuple:
                            if sender not in self.rb_rejected_conditions:
                                self.rb_rejected_conditions[sender] = set()
                            self.rb_rejected_conditions[sender].add(rejected_conditions_tuple)
                            self.log(f"[RB Process] Stored rejected combination from {sender}: {rejected_conditions_tuple}")

                    # Remove from active offers
                    del self.rb_active_offers[move.refers_to]
                    self.log(f"[RB Process] Offer {move.refers_to} rejected by {sender}, removed from active offers")

                # Mark as rejected
                self.rb_rejected_offers.add(move.refers_to)

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
                                    # CRITICAL: Update actual assignment, not just commitment record!
                                    self.assignments[assignment.node] = assignment.colour
                                    self.rb_commitments.setdefault(self.name, {})[assignment.node] = assignment.colour
                                    self.log(f"[RB Process] -> Committing to our side of offer: {assignment.node}={assignment.colour}")
                                    self.log(f"[RB Process] -> UPDATED self.assignments[{assignment.node}] = {assignment.colour}")

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