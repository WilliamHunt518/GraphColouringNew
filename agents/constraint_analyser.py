"""ConstraintAnalyser — pure algorithmic constraint analysis engine.

No Tkinter, no LLM, no comm layer.  Instantiated once per agent cluster.
The analyser is called reactively whenever the human changes a node colour.

Key design:
- ``compute_feasibility_set`` enumerates all valid agent assignments given the
  human's current (possibly partial) colouring.
- Projection methods marginalise the feasibility set to extract per-node
  colour domains and consequence counts for the UI.
- ``find_minimal_repair`` identifies the smallest set of human boundary nodes
  to remove from the colouring to restore feasibility.

Partial-observability guarantee: this class only ever accesses node colours
that belong to the human cluster (``human_nodes``) or the agent cluster
(``agent_nodes``).  It never reads or exposes colours from the *other* agent
cluster.
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional, Set, Tuple

from problems.graph_coloring import GraphColoring


class ConstraintAnalyser:
    """Analyses constraint structure between the human cluster and one agent cluster.

    Parameters
    ----------
    name : str
        Display name of the agent cluster (e.g. ``"Agent1"``).
    problem : GraphColoring
        The global graph-colouring problem object.  Used only for its
        ``is_valid()`` method and edge list — the analyser does not read
        global assignments from it.
    agent_nodes : list[str]
        All nodes owned by this agent cluster.
    human_nodes : list[str]
        All nodes owned by the human cluster.
    boundary_nodes : list[str]
        Human nodes that share at least one edge with a node in
        ``agent_nodes``.  These are the human nodes visible to this agent.
    domain : list[Any]
        Colour domain (e.g. ``["red", "green", "blue"]``).
    fixed_agent_nodes : dict[str, Any]
        Mapping of agent node → fixed colour.  These nodes are never
        enumerated; their colour is always the fixed value.
    """

    def __init__(
        self,
        name: str,
        problem: GraphColoring,
        agent_nodes: List[str],
        human_nodes: List[str],
        boundary_nodes: List[str],
        domain: List[Any],
        fixed_agent_nodes: Optional[Dict[str, Any]] = None,
        node_domains: Optional[Dict[str, List[Any]]] = None,
    ) -> None:
        self.name = name
        self._problem = problem
        self._agent_nodes: List[str] = list(agent_nodes)
        self._human_nodes: List[str] = list(human_nodes)
        self._boundary_nodes: List[str] = list(boundary_nodes)
        self._domain: List[Any] = list(domain)
        self._fixed: Dict[str, Any] = dict(fixed_agent_nodes) if fixed_agent_nodes else {}
        # Per-node domain restrictions (complex constraints).  Maps node →
        # allowed colours.  Nodes absent from this dict use self._domain.
        self._node_domains: Dict[str, List[Any]] = dict(node_domains) if node_domains else {}

        # Free agent nodes: agent nodes that are NOT fixed.
        self._free_agent_nodes: List[str] = [
            n for n in self._agent_nodes if n not in self._fixed
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_candidate(
        self,
        combo: Tuple[Any, ...],
        human_partial: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a full assignment dict for feasibility checking.

        Merges fixed agent assignments + free-node combo + human partial.
        Nodes with value ``None`` are omitted so that ``is_valid`` skips them.
        """
        assignment: Dict[str, Any] = {}
        # Fixed agent nodes
        for node, colour in self._fixed.items():
            assignment[node] = colour
        # Free agent nodes from combo
        for node, colour in zip(self._free_agent_nodes, combo):
            assignment[node] = colour
        # Human partial — ONLY include boundary nodes.
        # Non-boundary human nodes are internal to the human cluster; their
        # clashes don't affect this agent's feasibility at all.
        boundary_set = set(self._boundary_nodes)
        for node, colour in human_partial.items():
            if colour is not None and node in boundary_set:
                assignment[node] = colour
        return assignment

    def _is_feasible(self, assignment: Dict[str, Any]) -> bool:
        """Check feasibility via problem.is_valid (already skips None)."""
        return self._problem.is_valid(assignment)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_feasibility_set(
        self, human_partial: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Return all valid agent assignments consistent with human_partial.

        Parameters
        ----------
        human_partial : dict
            Mapping of human-node → colour (or ``None`` for unassigned).
            Only boundary nodes affect agent feasibility; non-boundary human
            nodes (internal clashes etc.) are ignored.

        Returns
        -------
        list[dict]
            Each element is a full assignment dict (agent nodes only) that
            is valid given the human's current colours.  Returns empty list
            if no valid assignment exists (infeasible state).
        """
        valid_configs: List[Dict[str, Any]] = []

        _per_node = [self._node_domains.get(n, self._domain) for n in self._free_agent_nodes]
        for combo in itertools.product(*_per_node):
            candidate = self._build_candidate(combo, human_partial)
            if self._is_feasible(candidate):
                # Return only agent-node assignments
                agent_assignment = {n: candidate[n] for n in self._agent_nodes}
                valid_configs.append(agent_assignment)

        return valid_configs

    def compute_domain_projection(
        self, feasibility_set: List[Dict[str, Any]]
    ) -> Dict[str, List[Any]]:
        """Marginalise a feasibility set to per-agent-node colour domains.

        Parameters
        ----------
        feasibility_set : list[dict]
            Output of ``compute_feasibility_set()``.

        Returns
        -------
        dict[str, list]
            Mapping of agent-node → sorted list of colours that appear in
            at least one valid configuration.  Empty list means no valid
            colour exists for that node (infeasible).
        """
        domains: Dict[str, Set[Any]] = {n: set() for n in self._agent_nodes}
        for config in feasibility_set:
            for node, colour in config.items():
                if node in domains:
                    domains[node].add(colour)
        return {node: sorted(colours, key=str) for node, colours in domains.items()}

    def compute_conditional_domains(
        self, human_partial: Dict[str, Any]
    ) -> Dict[str, Dict[Any, Dict[str, List[Any]]]]:
        """For each unassigned boundary node, compute per-colour projected domains.

        This shows "if boundary node v were colour c, agent nodes could be…".

        Parameters
        ----------
        human_partial : dict
            Current human colouring (None = unassigned).

        Returns
        -------
        dict
            ``{boundary_node: {colour: {agent_node: [feasible_colours]}}}``
            Only covers boundary nodes that are currently unassigned
            (value is ``None``).
        """
        result: Dict[str, Dict[Any, Dict[str, List[Any]]]] = {}
        for v in self._boundary_nodes:
            if human_partial.get(v) is not None:
                continue  # already assigned — not "conditional"
            result[v] = {}
            for c in self._node_domains.get(v, self._domain):
                override = dict(human_partial)
                override[v] = c
                fs = self.compute_feasibility_set(override)
                result[v][c] = self.compute_domain_projection(fs)
        return result

    def compute_agent_colour_conditions(
        self,
        domain_projection: Dict[str, List[Any]],
        conditional_domains: Dict[str, Dict[Any, Dict[str, List[Any]]]],
    ) -> Dict[str, Dict[str, Any]]:
        """Classify each agent node colour as certain or conditional.

        A colour is CERTAIN for agent node a if it is in domain_projection[a]
        and is never blocked by any unassigned boundary node setting.
        A colour is CONDITIONAL if there exists (h, h_col) such that a_col is
        absent from conditional_domains[h][h_col][a]; blocking conditions are
        expressed as "h \u2260 h_col" strings.

        Returns {agent_node: {"certain": [colours], "conditional": [(colour, [cond_str,...])]}}
        """
        result: Dict[str, Dict[str, Any]] = {}
        for agent_node, valid_colours in domain_projection.items():
            certain = []
            conditional = []
            for a_col in valid_colours:
                blocking = []
                for h_node, h_colour_map in conditional_domains.items():
                    for h_col, agent_domains in h_colour_map.items():
                        if a_col not in agent_domains.get(agent_node, []):
                            blocking.append(f"{h_node} \u2260 {h_col}")
                if blocking:
                    conditional.append((a_col, blocking))
                else:
                    certain.append(a_col)
            result[agent_node] = {"certain": certain, "conditional": conditional}
        return result

    def compute_boundary_joint_feasibility(
        self,
        human_partial: Dict[str, Any],
        max_combos: int = 81,
    ) -> List[Dict[str, Any]]:
        """Enumerate all joint colour combinations for boundary nodes.

        For each combination of boundary node colours, computes how many valid
        agent configurations exist.  This enables the LLM to identify patterns
        like "h1 and h2 must be different colours" or "h1 must be red or green".

        Parameters
        ----------
        human_partial : dict
            Current human colouring.  All boundary node values are OVERRIDDEN
            by the enumeration; non-boundary values are kept as context.
        max_combos : int
            If ``len(domain) ** len(boundary_nodes) > max_combos``, returns
            ``[]`` (too expensive to enumerate).

        Returns
        -------
        list[dict]
            Each entry: ``{'boundary_assignment': {node: colour},
            'feasibility_count': int}``.
            Sorted by feasibility_count descending (feasible combos first).
            Returns ``[]`` if too many combinations or no boundary nodes.
        """
        boundary = self._boundary_nodes
        if not boundary:
            return []

        _boundary_domains = [self._node_domains.get(n, self._domain) for n in boundary]
        n_combos = 1
        for d in _boundary_domains:
            n_combos *= len(d)
        if n_combos > max_combos:
            return []

        # Keep non-boundary human node values as context; override boundary nodes
        boundary_set = set(boundary)
        base_partial = {k: v for k, v in human_partial.items() if k not in boundary_set}

        results: List[Dict[str, Any]] = []
        _boundary_per_node = _boundary_domains
        for combo in itertools.product(*_boundary_per_node):
            override = dict(base_partial)
            for node, colour in zip(boundary, combo):
                override[node] = colour
            fs = self.compute_feasibility_set(override)
            results.append({
                "boundary_assignment": dict(zip(boundary, combo)),
                "feasibility_count": len(fs),
            })

        results.sort(key=lambda x: -x["feasibility_count"])
        return results

    def compute_consequence_sets(
        self, human_partial: Dict[str, Any]
    ) -> Dict[str, Dict[Any, List[Dict[str, Any]]]]:
        """For each assigned human boundary node, list valid agent configs per colour.

        Shows "if human boundary node v had colour c instead of its current
        colour, these agent configurations would be valid".

        Parameters
        ----------
        human_partial : dict
            Current human colouring (None = unassigned).

        Returns
        -------
        dict
            ``{human_node: {colour: [list_of_valid_agent_configs]}}``
            Only covers boundary nodes that are currently assigned.
            Each valid agent config is a dict ``{agent_node: colour}``.
        """
        result: Dict[str, Dict[Any, List[Dict[str, Any]]]] = {}
        for v in self._boundary_nodes:
            result[v] = {}
            for c in self._domain:
                override = dict(human_partial)
                override[v] = c
                fs = self.compute_feasibility_set(override)
                result[v][c] = fs
        return result

    def find_minimal_repair(
        self, human_partial: Dict[str, Any]
    ) -> Optional[List[str]]:
        """Find the smallest set of human boundary nodes to unassign to restore feasibility.

        Tries subsets of increasing size.  Returns the first (smallest) subset
        whose removal makes the feasibility set non-empty.  Returns ``None`` if
        already feasible, or ``[]`` (empty list) if no repair is possible even
        by removing all boundary nodes (which should never happen with a valid
        problem).

        Parameters
        ----------
        human_partial : dict
            Current human colouring.

        Returns
        -------
        list[str] or None
            List of boundary node names to unassign, or ``None`` if already feasible.
        """
        # Check if already feasible
        if self.compute_feasibility_set(human_partial):
            return None  # No repair needed

        # Get assigned boundary nodes
        assigned_boundary = [
            v for v in self._boundary_nodes
            if human_partial.get(v) is not None
        ]

        if not assigned_boundary:
            # All boundary nodes are unassigned but still infeasible — internal conflict
            return []

        # Try subsets of increasing size
        for size in range(1, len(assigned_boundary) + 1):
            for subset in itertools.combinations(assigned_boundary, size):
                override = dict(human_partial)
                for v in subset:
                    override[v] = None
                if self.compute_feasibility_set(override):
                    return list(subset)

        return []  # No repair found (should not happen for a solvable problem)

    def get_current_penalty(self, full_assignment: Dict[str, Any]) -> float:
        """Compute the current penalty for a full assignment dict.

        Parameters
        ----------
        full_assignment : dict
            Complete node → colour mapping (may include None for unassigned).

        Returns
        -------
        float
            Penalty from ``problem.evaluate_assignment`` (skips None entries).
        """
        filtered = {k: v for k, v in full_assignment.items() if v is not None}
        return self._problem.evaluate_assignment(filtered)

    @property
    def agent_nodes(self) -> List[str]:
        return list(self._agent_nodes)

    @property
    def nodes(self) -> List[str]:
        """Alias for agent_nodes — satisfies debug panel interface."""
        return list(self._agent_nodes)

    @property
    def boundary_nodes(self) -> List[str]:
        return list(self._boundary_nodes)

    @property
    def domain(self) -> List[Any]:
        return list(self._domain)

    @property
    def fixed_local_nodes(self) -> Dict[str, Any]:
        """Fixed node assignments — satisfies debug panel interface."""
        return dict(self._fixed)

    @property
    def problem(self) -> Any:
        """The underlying GraphColoring problem — satisfies debug panel interface."""
        return self._problem

    @property
    def assignments(self) -> Dict[str, Any]:
        """Agents don't hold assignments in constraint viz mode; returns empty dict."""
        return {}
