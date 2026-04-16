"""
Session state for one colouring attempt.

SessionManager tracks which node the user is currently on, records each
decision, and provides the assignment-so-far.  It has no Tkinter dependency.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class NodeDecision:
    """Record of one node-colouring decision."""
    node: str
    colour: str
    source: str                  # "human" | "accepted_plan" | "modified_plan"
    started_at: float            # unix timestamp when node became current
    decided_at: float            # unix timestamp when colour was chosen
    explanation_clicked: bool = False
    agents_agreed: bool = False  # majority of agents agreed with the chosen colour

    @property
    def decision_time_s(self) -> float:
        return self.decided_at - self.started_at


class SessionManager:
    """
    Manages in-progress state for one colouring attempt.

    Parameters
    ----------
    node_order:
        The complete mandatory colouring sequence.
    """

    def __init__(self, node_order: List[str]) -> None:
        self.node_order: List[str] = list(node_order)
        self.current_index: int = 0
        self.decisions: List[NodeDecision] = []
        self._node_start_time: float = time.time()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_node(self) -> Optional[str]:
        """The node currently awaiting a colour decision, or None if done."""
        if self.current_index < len(self.node_order):
            return self.node_order[self.current_index]
        return None

    @property
    def assignment_so_far(self) -> Dict[str, str]:
        """Partial assignment for all decided nodes."""
        return {d.node: d.colour for d in self.decisions}

    @property
    def is_complete(self) -> bool:
        """True when all nodes have been coloured."""
        return self.current_index >= len(self.node_order)

    @property
    def progress(self) -> tuple[int, int]:
        """Return (decided, total) node counts."""
        return (self.current_index, len(self.node_order))

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def mark_node_ready(self) -> None:
        """Call when a new node becomes the active node (starts the timer)."""
        self._node_start_time = time.time()

    def record_decision(
        self,
        colour: str,
        source: str,
        explanation_clicked: bool = False,
        agents_agreed: bool = False,
    ) -> NodeDecision:
        """
        Record the colour decision for the current node and advance the sequence.

        Returns the completed NodeDecision.
        """
        node = self.current_node
        if node is None:
            raise RuntimeError("record_decision called but no node is active")

        decision = NodeDecision(
            node=node,
            colour=colour,
            source=source,
            started_at=self._node_start_time,
            decided_at=time.time(),
            explanation_clicked=explanation_clicked,
            agents_agreed=agents_agreed,
        )
        self.decisions.append(decision)
        self.current_index += 1

        # Prime the timer for the next node
        self._node_start_time = time.time()
        return decision

    def reset(self, node_order: Optional[List[str]] = None) -> None:
        """Reset for a new attempt, optionally with a different node order."""
        if node_order is not None:
            self.node_order = list(node_order)
        self.current_index = 0
        self.decisions = []
        self._node_start_time = time.time()
