"""
ProposalAgent — used in Mode 1 (Manual Collaborative).

At each node in the sequential colouring order, a ProposalAgent may propose
a colour with a short template-based rationale.  No LLM is used.

An agent only has an opinion when it owns at least one node that is a direct
neighbour of the node currently being decided.  If it has no adjacent node,
it returns None (no opinion).

When it does have an adjacent node the recommendation is driven by
coordination: the agent announces what colour it intends to use on its own
adjacent node and asks the human to choose the complementary colour so the
two neighbours don't clash.  If the adjacent node is already coloured the
suggestion simply avoids the existing colour.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from study.config import AgentConfig, ColourPointsConfig


@dataclass
class NodeProposal:
    """A proposal from one agent for a single node."""
    agent_name: str
    node: str
    colour: str
    rationale_short: str    # 1-2 sentences shown inline
    rationale_full: str     # expandable detail
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class ProposalAgent:
    """
    Rule-based agent that proposes a colour for each node in turn.

    Parameters
    ----------
    config:
        Agent configuration (name, preferred_colour).
    points_config:
        Full scoring config (all participants' point weights).
    """

    def __init__(
        self,
        config: AgentConfig,
        points_config: ColourPointsConfig,
    ) -> None:
        self._config = config
        self._points = points_config
        self.name = config.name
        self.preferred_colour = config.preferred_colour

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def propose_for_node(
        self,
        node: str,
        node_order: List[str],
        edges: List[Tuple[str, str]],
        current_assignment: Dict[str, str],
        node_regions: Dict[str, str],
        attempt_number: int,
        prior_attempts: List[Dict[str, str]],
    ) -> Optional[NodeProposal]:
        """
        Return a colour proposal for *node*, or None if this agent has no
        adjacent node and therefore no opinion.

        Parameters
        ----------
        node:
            The node currently being decided.
        node_order:
            Complete sequential colouring order.
        edges:
            All edges in the graph as (u, v) pairs.
        current_assignment:
            Nodes already coloured in this attempt ``{node: colour}``.
        node_regions:
            Maps every node name → region/owner name (e.g. "AgentA").
        attempt_number:
            1-based attempt index.
        prior_attempts:
            Full assignments from previous attempts (may be empty).
        """
        colours = self._points.colours

        # Find nodes this agent owns that are direct neighbours of ``node``
        my_nodes = {n for n, region in node_regions.items() if region == self.name}
        neighbours_of_node: set[str] = set()
        for u, v in edges:
            if u == node:
                neighbours_of_node.add(v)
            elif v == node:
                neighbours_of_node.add(u)
        my_adjacent = sorted(my_nodes & neighbours_of_node)   # sorted for determinism

        if not my_adjacent:
            return None  # no opinion — not connected to this node

        # Pick the most relevant adjacent node (prefer already-coloured ones so
        # the advice is immediately actionable)
        adj_coloured = [n for n in my_adjacent if n in current_assignment]
        adj_node = adj_coloured[0] if adj_coloured else my_adjacent[0]
        adj_colour = current_assignment.get(adj_node)

        # Determine recommended colour -----------------------------------------
        if adj_colour is not None:
            # Adjacent node is already coloured — avoid a clash
            avoid = adj_colour
            suggestion_reason = "clash_avoidance"
        else:
            # Adjacent node not yet coloured — we plan to use our preferred colour
            # there, so ask the human to pick the other colour now
            avoid = self.preferred_colour
            suggestion_reason = "future_planning"

        # Pick the first colour that is not ``avoid``; fall back if only one colour
        best = next((c for c in colours if c != avoid), colours[0])

        short, full = self._build_rationale(
            node=node,
            chosen=best,
            adj_node=adj_node,
            adj_colour=adj_colour,
            suggestion_reason=suggestion_reason,
            attempt_number=attempt_number,
            prior_attempts=prior_attempts,
            node_order=node_order,
            current_assignment=current_assignment,
        )

        return NodeProposal(
            agent_name=self.name,
            node=node,
            colour=best,
            rationale_short=short,
            rationale_full=full,
        )

    def colour_own_node(
        self,
        node: str,
        current_assignment: Dict[str, str],
        edges: List[Tuple[str, str]],
    ) -> str:
        """
        Choose the best colour for one of this agent's *own* nodes.

        Priority: (1) avoid clashing with already-coloured adjacent nodes,
        (2) maximise own points among non-clashing options.
        If every colour clashes, fall back to score-maximisation.
        """
        my_pts = self._points.points_by_owner.get(self.name, {})
        colours = self._points.colours

        adjacent_colours: set[str] = set()
        for u, v in edges:
            if u == node and v in current_assignment:
                adjacent_colours.add(current_assignment[v])
            elif v == node and u in current_assignment:
                adjacent_colours.add(current_assignment[u])

        non_clashing = [c for c in colours if c not in adjacent_colours]
        candidates = non_clashing if non_clashing else list(colours)
        return max(candidates, key=lambda c: my_pts.get(c, 0))

    def best_response_scores(
        self,
        current_node: str,
        node_order: List[str],
        edges: List[Tuple[str, str]],
        current_assignment: Dict[str, str],
        node_regions: Dict[str, str],
    ) -> Dict[str, int]:
        """
        For each colour the human could assign to *current_node*, return this
        agent's expected total score assuming:
          - The agent plays its own remaining nodes greedily (clash avoidance,
            then score maximisation).
          - Every other undecided node is played greedily by its owner.

        Already-decided nodes contribute their locked-in points.
        """
        my_pts = self._points.points_by_owner.get(self.name, {})
        colours = self._points.colours
        results: Dict[str, int] = {}

        penalty = self._points.clash_penalty
        half_penalty = penalty // 2
        remainder = penalty - half_penalty * 2

        for chosen_colour in colours:
            # Simulate forward from this choice
            simulated: Dict[str, str] = dict(current_assignment)
            simulated[current_node] = chosen_colour

            for node in node_order:
                if node in simulated:
                    continue
                region = node_regions.get(node, "")
                owner_pts = self._points.points_by_owner.get(region, {})

                adj_colours: set[str] = set()
                for u, v in edges:
                    if u == node and v in simulated:
                        adj_colours.add(simulated[v])
                    elif v == node and u in simulated:
                        adj_colours.add(simulated[u])

                candidates = [c for c in colours if c not in adj_colours] or list(colours)
                simulated[node] = max(candidates, key=lambda c: owner_pts.get(c, 0))

            # Base score for this agent
            score = sum(my_pts.get(c, 0) for c in simulated.values())

            # Deduct this agent's share of clash penalties
            if penalty:
                for u, v in edges:
                    if (
                        u in simulated
                        and v in simulated
                        and simulated[u] == simulated[v]
                    ):
                        u_owner = node_regions.get(u)
                        v_owner = node_regions.get(v)
                        if u_owner == v_owner:
                            if u_owner == self.name:
                                score -= penalty
                        else:
                            if u_owner == self.name:
                                score -= half_penalty + remainder
                            elif v_owner == self.name:
                                score -= half_penalty

            results[chosen_colour] = score

        return results

    def vote_for_colour(self) -> tuple[str, str]:
        """
        Simple self-interested vote used by PlanningAgent deliberation.

        Returns (colour, short_rationale) based purely on own point-maximisation,
        with no adjacency logic.
        """
        my_pts = self._points.points_by_owner.get(self.name, {})
        colours = self._points.colours
        best = max(colours, key=lambda c: my_pts.get(c, 0))
        pts = my_pts.get(best, 0)
        return best, f"Votes {best.capitalize()} (earns {pts} pts/node for {self.name})."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_rationale(
        self,
        node: str,
        chosen: str,
        adj_node: str,
        adj_colour: Optional[str],
        suggestion_reason: str,
        attempt_number: int,
        prior_attempts: List[Dict[str, str]],
        node_order: List[str],
        current_assignment: Dict[str, str],
    ) -> tuple[str, str]:
        """Return (short, full) rationale strings."""
        colours = self._points.colours
        my_pts = self._points.points_by_owner.get(self.name, {})
        shared = self._points.total_per_colour()

        # Short sentence
        if suggestion_reason == "clash_avoidance":
            short = (
                f"My node {adj_node} is already {adj_colour.capitalize()} — "
                f"I recommend {chosen.capitalize()} here so our adjacent nodes don't clash."
            )
        else:
            # future_planning: we intend to use preferred_colour on adj_node
            planned = self.preferred_colour
            short = (
                f"My node {adj_node} is next to this one and I plan to colour it "
                f"{planned.capitalize()} — so I recommend {chosen.capitalize()} here "
                f"to keep our nodes well-coordinated."
            )

        # Prior-attempt note
        prior_note = ""
        if attempt_number > 1 and prior_attempts:
            last = prior_attempts[-1]
            if node in last:
                prev_col = last[node]
                if prev_col != chosen:
                    prior_note = (
                        f" Last attempt this was {prev_col.capitalize()}; "
                        f"my recommendation is {chosen.capitalize()} this time."
                    )
                else:
                    prior_note = f" Same recommendation as last attempt."

        # Full rationale
        full_lines = [
            f"Node {node} — {self.name} recommendation: {chosen.capitalize()}",
            "",
            f"Relevant adjacent node: {adj_node}",
        ]
        if adj_colour is not None:
            full_lines += [
                f"  Status: already coloured {adj_colour.capitalize()}.",
                f"  Choosing {chosen.capitalize()} for {node} avoids a colour clash "
                f"between {adj_node} and {node}.",
            ]
        else:
            full_lines += [
                f"  Status: not yet coloured.",
                f"  I intend to colour {adj_node} {self.preferred_colour.capitalize()} "
                f"(earns me {my_pts.get(self.preferred_colour, 0)} pts per node).",
                f"  Choosing {chosen.capitalize()} for {node} now means {adj_node} "
                f"and {node} will have different colours.",
            ]

        full_lines += [
            "",
            "Point values per node (for all participants):",
        ]
        for colour in colours:
            my_p = my_pts.get(colour, 0)
            sh_p = shared.get(colour, 0)
            full_lines.append(
                f"  {colour.capitalize()}: {my_p} pts for {self.name}, "
                f"{sh_p} pts shared total"
            )

        remaining = [n for n in node_order if n not in current_assignment and n != node]
        full_lines += [
            "",
            f"Nodes still to decide after this one: {len(remaining)}",
        ]

        if prior_note:
            full_lines += ["", prior_note.strip()]

        return short + prior_note, "\n".join(full_lines)
