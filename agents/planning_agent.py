"""
PlanningAgent — used in Mode 2A and Mode 2B (Autonomous Planning).

Before colouring begins, the PlanningAgent runs a multi-agent deliberation
to produce a complete proposed colouring.  The quality parameter controls
how often the agent picks the shared-optimal colour vs a random one:

  quality=0.8  →  Mode 2A: picks optimal 80% of the time
  quality=0.3  →  Mode 2B: picks optimal only 30% of the time

Everything is deterministic given a seed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from study.config import AgentConfig, ColourPointsConfig
from agents.proposal_agent import ProposalAgent


@dataclass
class PlannedStep:
    """One step in the autonomous plan."""
    node: str
    colour: str
    proposer: str           # which agent "won" the vote for this step
    rationale_short: str    # shown inline in the plan step panel
    rationale_full: str     # expandable detail


@dataclass
class Plan:
    """Complete autonomous plan produced before colouring begins."""
    steps: List[PlannedStep]
    deliberation_log: List[str]     # shown in "how was this plan made?" panel
    total_expected_score: int
    attempt_number: int
    seed: int


class PlanningAgent:
    """
    Autonomous multi-agent planner.

    Parameters
    ----------
    agent_configs:
        List of AgentConfig objects (one per AI participant).
    points_config:
        Full scoring config (all participants' point weights).
    node_order:
        Mandatory sequential colouring order.
    quality:
        Probability of picking the shared-optimal colour at each step.
        0.8 = Mode 2A (high quality), 0.3 = Mode 2B (low quality).
    seed:
        Random seed for reproducibility.
    """

    def __init__(
        self,
        agent_configs: List[AgentConfig],
        points_config: ColourPointsConfig,
        node_order: List[str],
        edges: List[Tuple[str, str]],
        quality: float = 0.8,
        seed: int = 42,
    ) -> None:
        self._agents = [
            ProposalAgent(cfg, points_config) for cfg in agent_configs
        ]
        self._points = points_config
        self._node_order = node_order
        self._edges = edges
        self._quality = quality
        self._base_seed = seed
        self._shared_totals = points_config.total_per_colour()
        self._optimal_colour = max(
            self._shared_totals, key=lambda c: self._shared_totals[c]
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_plan(
        self,
        attempt_number: int,
        prior_attempts: List[Dict[str, str]],
        node_order: List[str] | None = None,
    ) -> Plan:
        """
        Run deliberation and return a complete Plan.

        Parameters
        ----------
        attempt_number:
            1-based; used so that later attempts may improve earlier ones.
        prior_attempts:
            Full assignments from previous attempts (may be empty).
        node_order:
            The actual colouring sequence for this attempt.  When random turn
            order is active this will differ from the graph's canonical order.
            Defaults to the order supplied at construction time.
        """
        effective_order = node_order if node_order is not None else self._node_order
        rng = random.Random(self._base_seed + attempt_number)
        steps: List[PlannedStep] = []
        deliberation_log: List[str] = [
            f"=== Autonomous planning — attempt {attempt_number} ===",
            f"Strategy: {'high-quality' if self._quality >= 0.5 else 'exploratory'}",
            f"Shared-optimal colour: {self._optimal_colour.capitalize()}",
            f"Turn order: {effective_order}",
            "",
        ]

        current_assignment: Dict[str, str] = {}

        for node in effective_order:
            step, log_lines = self._deliberate_node(
                node=node,
                rng=rng,
                current_assignment=current_assignment,
                attempt_number=attempt_number,
                prior_attempts=prior_attempts,
            )
            steps.append(step)
            current_assignment[node] = step.colour
            deliberation_log.extend(log_lines)

        # Compute expected score
        total = sum(
            self._shared_totals.get(s.colour, 0) for s in steps
        )

        deliberation_log.append("")
        deliberation_log.append(f"Total expected shared score: {total}")

        return Plan(
            steps=steps,
            deliberation_log=deliberation_log,
            total_expected_score=total,
            attempt_number=attempt_number,
            seed=self._base_seed + attempt_number,
        )

    # ------------------------------------------------------------------
    # Internal deliberation
    # ------------------------------------------------------------------

    def _deliberate_node(
        self,
        node: str,
        rng: random.Random,
        current_assignment: Dict[str, str],
        attempt_number: int,
        prior_attempts: List[Dict[str, str]],
    ) -> tuple[PlannedStep, List[str]]:
        """
        Run one round of deliberation for a single node.

        Each agent votes for its preferred colour (self-interested).
        The final colour is chosen as follows:
          - With probability ``quality``: pick the shared-optimal colour
          - With probability ``1 - quality``: pick a random colour (may
            happen to be optimal, but is not guided by shared score)

        This mimics a high-quality vs. low-quality autonomous system
        without exposing the mechanism to study participants.
        """
        log: List[str] = [f"  Node {node}:"]

        # Find colours already used by adjacent nodes (would cause a clash)
        adjacent_colours: set[str] = set()
        for u, v in self._edges:
            if u == node and v in current_assignment:
                adjacent_colours.add(current_assignment[v])
            elif v == node and u in current_assignment:
                adjacent_colours.add(current_assignment[u])

        all_colours = self._points.colours
        safe_colours = [c for c in all_colours if c not in adjacent_colours]
        candidates = safe_colours if safe_colours else list(all_colours)

        if adjacent_colours:
            log.append(f"    Adjacent colours already placed: {sorted(adjacent_colours)}")
            log.append(f"    Safe candidates: {candidates}")

        # Collect agent votes (self-interested)
        votes: Dict[str, int] = {c: 0 for c in all_colours}
        agent_votes: Dict[str, tuple] = {}   # name -> (colour, rationale)
        for agent in self._agents:
            colour, rationale = agent.vote_for_colour()
            votes[colour] += 1
            agent_votes[agent.name] = (colour, rationale)
            log.append(
                f"    {agent.name} votes {colour.capitalize()} "
                f"({agent.preferred_colour.capitalize()} preferred)"
            )

        # Best safe colour by shared score
        best_safe = max(candidates, key=lambda c: self._shared_totals.get(c, 0))

        # Quality-biased selection among safe candidates only
        if rng.random() < self._quality:
            chosen = best_safe
            selection_method = "shared-optimal (safe)"
        else:
            chosen = rng.choice(candidates)
            selection_method = "random exploration (safe)"

        shared_score = self._shared_totals.get(chosen, 0)
        log.append(
            f"    → Selected: {chosen.capitalize()} "
            f"(method: {selection_method}, shared pts: {shared_score})"
        )

        # Build rationale for plan display
        winning_agent = max(agent_votes, key=lambda n: agent_votes[n][0] == chosen)
        short = self._build_short_rationale(node, chosen, selection_method, shared_score)
        full = self._build_full_rationale(
            node, chosen, votes, agent_votes, shared_score, selection_method
        )

        step = PlannedStep(
            node=node,
            colour=chosen,
            proposer=winning_agent,
            rationale_short=short,
            rationale_full=full,
        )
        return step, log

    def _build_short_rationale(
        self,
        node: str,
        colour: str,
        method: str,
        shared_score: int,
    ) -> str:
        if method == "shared-optimal":
            return (
                f"{colour.capitalize()} gives the team {shared_score} pts on this node, "
                f"which maximises our shared score."
            )
        else:
            return (
                f"{colour.capitalize()} was selected for {node} after agent deliberation "
                f"(team score: {shared_score} pts)."
            )

    def _build_full_rationale(
        self,
        node: str,
        chosen: str,
        votes: Dict[str, int],
        agent_votes: Dict[str, tuple],
        shared_score: int,
        method: str,
    ) -> str:
        lines = [
            f"Node {node} — Autonomous plan decision: {chosen.capitalize()}",
            "",
            "Agent votes:",
        ]
        for name, (colour, rationale) in agent_votes.items():
            lines.append(f"  {name}: {colour.capitalize()} — {rationale}")
        lines += [
            "",
            "Vote tally:",
        ]
        for colour, count in votes.items():
            lines.append(f"  {colour.capitalize()}: {count} vote(s)")
        lines += [
            "",
            "Shared-score contributions per colour:",
        ]
        for colour in self._points.colours:
            s = self._shared_totals.get(colour, 0)
            marker = " ← optimal" if colour == self._optimal_colour else ""
            lines.append(f"  {colour.capitalize()}: {s} pts{marker}")
        lines += [
            "",
            f"Selection method: {method}",
            f"Final choice: {chosen.capitalize()} ({shared_score} pts for the team)",
        ]
        return "\n".join(lines)
