"""
Points-based scoring for the graph-colouring trust study.

Base points are earned for every coloured node regardless of adjacency.
A clash_penalty (from ColourPointsConfig) is deducted per clashing adjacent
pair, split equally between the two owners of the clashing nodes.
Edges are also used for visual clash highlighting in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from study.config import ColourPointsConfig


@dataclass
class ScoringResult:
    """Result of scoring a complete or partial node assignment."""
    total: int
    by_owner: Dict[str, int]    # participant name -> score (after penalties)
    by_node: Dict[str, int]     # node -> shared-score contribution (before penalty)
    clash_count: int = 0        # number of clashing adjacent pairs


class PointsScorer:
    """
    Computes shared and individual scores from a node colour assignment.

    Parameters
    ----------
    config:
        Colour point weights per participant.
    edges:
        All graph edges as (u, v) pairs.  Required for clash detection.
    node_regions:
        Maps every node name to its owner name.  Required for penalty splitting.
    """

    def __init__(
        self,
        config: ColourPointsConfig,
        edges: Optional[List[Tuple[str, str]]] = None,
        node_regions: Optional[Dict[str, str]] = None,
    ) -> None:
        self._config = config
        self._edges: List[Tuple[str, str]] = edges or []
        self._node_regions: Dict[str, str] = node_regions or {}
        self._owners = list(config.points_by_owner.keys())

    def score_assignment(
        self,
        assignment: Dict[str, str],
    ) -> ScoringResult:
        """
        Score a (possibly partial) assignment of nodes to colours.

        Parameters
        ----------
        assignment:
            ``{node: colour}`` for every node that has been coloured.
        """
        by_owner: Dict[str, int] = {owner: 0 for owner in self._owners}
        by_node: Dict[str, int] = {}

        # Base points
        for node, colour in assignment.items():
            node_total = 0
            for owner in self._owners:
                pts = self._config.points_by_owner[owner].get(colour, 0)
                by_owner[owner] += pts
                node_total += pts
            by_node[node] = node_total

        # Clash penalties
        penalty = self._config.clash_penalty
        clash_count = 0
        if penalty and self._edges:
            half = penalty // 2
            remainder = penalty - half * 2   # 0 when penalty is even

            for u, v in self._edges:
                if (
                    u in assignment
                    and v in assignment
                    and assignment[u] == assignment[v]
                ):
                    clash_count += 1
                    u_owner = self._node_regions.get(u)
                    v_owner = self._node_regions.get(v)

                    if u_owner == v_owner:
                        # Same owner pays the full penalty
                        if u_owner and u_owner in by_owner:
                            by_owner[u_owner] -= penalty
                    else:
                        # Split: each pays half (remainder goes to u's owner)
                        if u_owner and u_owner in by_owner:
                            by_owner[u_owner] -= half + remainder
                        if v_owner and v_owner in by_owner:
                            by_owner[v_owner] -= half

        return ScoringResult(
            total=sum(by_owner.values()),
            by_owner=by_owner,
            by_node=by_node,
            clash_count=clash_count,
        )

    def best_colour_for_node(self, node: str) -> str:
        """Return the colour that maximises shared-score contribution for one node."""
        totals = self._config.total_per_colour()
        return max(totals, key=lambda c: totals[c])

    def optimal_assignment(self, nodes: list[str]) -> Dict[str, str]:
        """
        Return the shared-score-optimal assignment for a list of nodes.
        (Colour each node with the colour that maximises shared contribution.)
        """
        best = self.best_colour_for_node("")  # same for every node given flat weights
        return {n: best for n in nodes}
