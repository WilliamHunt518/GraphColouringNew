"""Rule-based argumentation-style cluster agent.

This implements the RB baseline as a *structured dialogue protocol* rather
than free-form text or LLM-mediated translation.

Key properties:
  * No LLM usage.
  * Messages follow a simple argumentation dialogue game (Parsons/Jennings style).
  * The human UI can compose moves via dropdowns/buttons.
  * The agent uses deterministic, transparent rules grounded in local penalties.

The RB protocol itself is in :mod:`comm.rb_protocol`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from .cluster_agent import ClusterAgent
from .base_agent import Message
from comm.rb_protocol import RBMove, parse_rb, format_rb, pretty_rb


@dataclass
class _DialogueState:
    last_human: Optional[RBMove] = None
    last_agent: Optional[RBMove] = None
    # Human commitments we treat as facts (only set on human CONCEDE)
    human_commitments: Dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.human_commitments is None:
            self.human_commitments = {}


class RuleBasedClusterAgent(ClusterAgent):
    """Baseline agent implementing a structured argumentation protocol."""

    REASON_CODES = (
        "avoids_boundary_conflict",
        "improves_local_consistency",
        "helps_you_move",
        "reduces_global_penalty",
    )

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
        # Initialise parent with a placeholder message_type (not used in RB)
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

        # Per-neighbour dialogue state
        self._dlg: Dict[str, _DialogueState] = {}
        # Pending RB move received this iteration
        self._pending: Dict[str, RBMove] = {}

    # ----------------------------
    # RB parsing / state updates
    # ----------------------------
    def receive(self, message: Message) -> None:
        """Handle incoming RB messages.

        RB messages do *not* automatically update neighbour assignments unless
        the human explicitly commits (CONCEDE).
        """
        rb = parse_rb(message.content)
        if rb is None:
            # Fall back to normal behaviour for non-RB content.
            super().receive(message)
            return

        # Base bookkeeping
        try:
            self.debug_incoming_raw.append(message.content)
            self.debug_incoming_parsed.append(rb.to_dict())
        except Exception:
            pass
        self.log(f"RB received from {message.sender}: {pretty_rb(rb)}")

        st = self._dlg.setdefault(str(message.sender), _DialogueState())
        st.last_human = rb
        self._pending[str(message.sender)] = rb

        # If the human is committing to an assignment, treat as knowledge.
        if rb.move == "CONCEDE" and rb.colour:
            st.human_commitments[rb.node] = rb.colour
            # Only update neighbour_assignments on commitment.
            if rb.node not in self.nodes:
                self.neighbour_assignments[rb.node] = rb.colour
                self.log(f"Human commitment recorded: {rb.node} -> {rb.colour}")

        # If the human makes a request about an agent-owned node, treat it like
        # a forced local assignment (this is still rule-based and transparent).
        if rb.colour and rb.node in self.nodes and rb.move in {"PROPOSE", "ARGUE", "REQUEST"}:
            self.forced_local_assignments[rb.node] = rb.colour
            self.log(f"RB forced local assignment requested: {rb.node} -> {rb.colour}")

    # ----------------------------
    # Utility helpers (no LLM)
    # ----------------------------
    def _boundary_map(self, other_owner: str) -> Dict[str, List[str]]:
        """Map human boundary nodes -> list of our local nodes adjacent to them."""
        m: Dict[str, List[str]] = {}
        for u in self.nodes:
            for nbr in self.problem.get_neighbors(u):
                if nbr in self.nodes:
                    continue
                if self.owners.get(nbr) != other_owner:
                    continue
                # nbr is external node belonging to other_owner
                m.setdefault(nbr, []).append(u)
        return m

    def _boundary_cost(self, ext_node: str, ext_colour: str, *, adj_local: List[str]) -> int:
        """Boundary conflict cost for a given external node colour."""
        cost = 0
        for u in adj_local:
            if self.assignments.get(u) == ext_colour:
                cost += 1
        return cost

    def _local_penalty(self) -> int:
        """Compute penalty internal to this cluster only."""
        # Use the problem's evaluate_assignment but restricted to local edges.
        penalty = 0
        local_set = set(self.nodes)
        for u in self.nodes:
            for v in self.problem.get_neighbors(u):
                if v not in local_set:
                    continue
                if u < v and self.assignments.get(u) == self.assignments.get(v):
                    penalty += 1
        return penalty

    def _choose_best_colour(self, ext_node: str, adj_local: List[str]) -> Tuple[str, int]:
        best_c = str(self.domain[0])
        best_cost = 10**9
        for c in self.domain:
            cc = str(c)
            cost = self._boundary_cost(ext_node, cc, adj_local=adj_local)
            if cost < best_cost:
                best_cost = cost
                best_c = cc
        return best_c, int(best_cost)

    def _reasons_for(self, ext_node: str, chosen_colour: str, *, best_cost: int, adj_local: List[str]) -> List[str]:
        reasons: List[str] = []
        if best_cost == 0:
            reasons.append("avoids_boundary_conflict")
        else:
            reasons.append("helps_you_move")
        if self._local_penalty() > 0:
            reasons.append("improves_local_consistency")
        # Keep reasons list short and deterministic.
        return reasons[:2]

    # ----------------------------
    # Main RB step
    # ----------------------------
    def step(self) -> None:
        """Compute local assignment and send one RB move per neighbour."""

        # 1) Optimise locally (respecting any forced_local_assignments)
        new_assignment = self.compute_assignments()
        if new_assignment != self.assignments:
            self.log(f"Updated assignments from {self.assignments} to {new_assignment}")
        else:
            self.log(f"Assignments unchanged: {self.assignments}")
        self.assignments = new_assignment

        # 2) Determine neighbouring owners
        recipients: Set[str] = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    owner = self.owners.get(nbr)
                    if owner and owner != self.name:
                        recipients.add(owner)

        # 3) Prepare a report payload for UI partial observability
        boundary_assignments: Dict[str, Any] = {}
        for node in self.nodes:
            # only report nodes that touch boundary
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    boundary_assignments[node] = self.assignments.get(node)
                    break

        # 4) For each neighbour, respond to pending human move if present, else
        #    proactively propose on a boundary node where we have conflicts.
        for recipient in sorted(recipients):
            st = self._dlg.setdefault(recipient, _DialogueState())
            bmap = self._boundary_map(recipient)

            pending = self._pending.pop(recipient, None)
            outgoing: Optional[RBMove] = None

            if pending is not None:
                # Respond to human move
                ext_node = pending.node
                adj_local = bmap.get(ext_node, [])
                if not adj_local:
                    # Not a boundary node we can reason about; acknowledge.
                    outgoing = RBMove(move="QUERY", node=ext_node, colour=None, reasons=["helps_you_move"])
                else:
                    best_c, best_cost = self._choose_best_colour(ext_node, adj_local)
                    reasons = self._reasons_for(ext_node, best_c, best_cost=best_cost, adj_local=adj_local)

                    if pending.move in {"PROPOSE", "ARGUE"} and pending.colour:
                        proposed = pending.colour
                        prop_cost = self._boundary_cost(ext_node, proposed, adj_local=adj_local)
                        if prop_cost == best_cost:
                            # Accept the human's proposal
                            outgoing = RBMove(move="CONCEDE", node=ext_node, colour=proposed, reasons=reasons)
                        else:
                            # Counter-propose (attack + propose best)
                            outgoing = RBMove(move="PROPOSE", node=ext_node, colour=best_c, reasons=reasons)
                    elif pending.move == "REQUEST":
                        outgoing = RBMove(move="PROPOSE", node=ext_node, colour=best_c, reasons=reasons)
                    elif pending.move == "QUERY":
                        # Provide justification for our last proposal if any
                        if st.last_agent and st.last_agent.node == ext_node and st.last_agent.colour:
                            outgoing = RBMove(move="ARGUE", node=ext_node, colour=st.last_agent.colour, reasons=reasons)
                        else:
                            outgoing = RBMove(move="PROPOSE", node=ext_node, colour=best_c, reasons=reasons)
                    elif pending.move == "CONCEDE" and pending.colour:
                        # Human accepted something; acknowledge by arguing for it.
                        outgoing = RBMove(move="ARGUE", node=ext_node, colour=pending.colour, reasons=reasons)
                    elif pending.move == "ATTACK":
                        # Respond with our best alternative.
                        outgoing = RBMove(move="PROPOSE", node=ext_node, colour=best_c, reasons=reasons)

            if outgoing is None:
                # Proactive move: pick a boundary node where there is a current
                # boundary conflict under known commitments.
                worst_node = None
                worst_cost = 0
                for ext_node, adj_local in bmap.items():
                    ext_colour = self.neighbour_assignments.get(ext_node)
                    if isinstance(ext_colour, str):
                        c = self._boundary_cost(ext_node, ext_colour, adj_local=adj_local)
                        if c > worst_cost:
                            worst_cost = c
                            worst_node = ext_node
                if worst_node is None:
                    # If no beliefs, just pick the first boundary node.
                    worst_node = next(iter(bmap.keys()), None)
                if worst_node is not None:
                    adj_local = bmap.get(worst_node, [])
                    best_c, best_cost = self._choose_best_colour(worst_node, adj_local)
                    reasons = self._reasons_for(worst_node, best_c, best_cost=best_cost, adj_local=adj_local)
                    outgoing = RBMove(move="PROPOSE", node=worst_node, colour=best_c, reasons=reasons)

            # If still none (e.g. no boundary), do not message.
            if outgoing is None:
                continue

            st.last_agent = outgoing
            msg = format_rb(outgoing)
            # Attach report payload for UI colouring (participant-safe)
            msg = msg + f" [report:{boundary_assignments}]"
            self.log(f"RB -> {recipient}: {pretty_rb(outgoing)}")
            self.send(recipient, msg)
