"""
ChannelAdvisor — imperfect greedy channel assignment for the drone swarm task.

Given a selected subset of drones, proposes channel assignments that attempt to
minimise clashes in the current interference graph.  With probability epsilon
(default 0.20), each drone's optimal assignment is independently replaced by a
uniformly random channel, making the agent useful but not perfectly reliable.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Set, Tuple

from robot_world import CHANNELS


class ChannelAdvisor:
    """
    Greedy colouring with epsilon-random noise.

    Parameters
    ----------
    epsilon:
        Per-drone probability of substituting the optimal channel with a
        uniformly random one.  0 = perfect; 1 = fully random.
    seed:
        RNG seed for reproducibility.  None = non-deterministic.
    """

    def __init__(self, epsilon: float = 0.20, seed: Optional[int] = None) -> None:
        self.epsilon = epsilon
        self._rng = random.Random(seed)

    def suggest(
        self,
        selected_ids: List[int],
        current_channels: Dict[int, str],
        edges: List[Tuple[int, int]],
        near_pairs: Optional[List[Tuple[int, int]]] = None,
    ) -> Tuple[Dict[int, str], bool]:
        """
        Propose a channel assignment for the selected drones.

        Parameters
        ----------
        selected_ids:
            IDs of drones to assign channels to.
        current_channels:
            Current channel of every drone (keyed by drone id).
            Drones that are switching may have a stale channel here.
        edges:
            All active interference edges as (id_i, id_j) pairs.
        near_pairs:
            Pairs of drones in approach range (not yet in comm range) that
            the agent treats as likely future edges when planning assignments.

        Returns
        -------
        proposal:
            Maps each selected drone id → proposed channel string.
        infeasible:
            True if at least one selected drone could not be assigned a
            clash-free channel (i.e., the local subgraph needs > 3 colours).
        """
        if not selected_ids:
            return {}, False

        selected_set: Set[int] = set(selected_ids)

        # Combine confirmed edges with anticipated near-range links
        all_edges = list(edges)
        if near_pairs:
            all_edges.extend(near_pairs)

        # Within-group adjacency
        adj: Dict[int, Set[int]] = {i: set() for i in selected_ids}
        # Channels blocked by already-fixed (non-selected) neighbours
        fixed_blocked: Dict[int, Set[str]] = {i: set() for i in selected_ids}

        for u, v in all_edges:
            u_in = u in selected_set
            v_in = v in selected_set
            if u_in and v_in:
                adj[u].add(v)
                adj[v].add(u)
            elif u_in:
                ch = current_channels.get(v)
                if ch:
                    fixed_blocked[u].add(ch)
            elif v_in:
                ch = current_channels.get(u)
                if ch:
                    fixed_blocked[v].add(ch)

        # Greedy order: most constrained first (degree within group + fixed blocks)
        order = sorted(
            selected_ids,
            key=lambda i: len(adj[i]) + len(fixed_blocked[i]),
            reverse=True,
        )

        proposal: Dict[int, str] = {}
        infeasible = False

        for drone_id in order:
            blocked: Set[str] = set(fixed_blocked[drone_id])
            for nbr in adj[drone_id]:
                if nbr in proposal:
                    blocked.add(proposal[nbr])

            free = [c for c in CHANNELS if c not in blocked]

            if free:
                optimal = free[0]
            else:
                # Locally infeasible: pick the colour that creates fewest clashes
                infeasible = True

                def _clashes(ch: str) -> int:
                    n = 1 if ch in fixed_blocked[drone_id] else 0
                    n += sum(1 for nb in adj[drone_id] if proposal.get(nb) == ch)
                    return n

                optimal = min(CHANNELS, key=_clashes)

            # Apply epsilon noise independently per drone
            if self._rng.random() < self.epsilon:
                proposal[drone_id] = self._rng.choice(CHANNELS)
            else:
                proposal[drone_id] = optimal

        return proposal, infeasible
