"""API library for graph coloring operations exposed to backend LLMs.

This module provides a clean API layer that exposes ClusterAgent's algorithmic
functions for use by LLM-based reasoning agents. The API separates the graph
coloring logic from the LLM reasoning layer, allowing backend LLMs to call
structured functions rather than generating arbitrary code.

The API supports two LLM reasoning patterns:
1. **LLM_TOOL**: OpenAI function calling with structured schemas
2. **LLM_REACT**: ReAct pattern (Reasoning and Acting) with thought→action→observation

Example usage:
    >>> api = ClusterAgentAPI(agent)
    >>> assignments = api.compute_assignments(algorithm="greedy")
    >>> penalty, conflicts = api.get_current_penalty()
    >>> alternatives = api.enumerate_alternatives(nodes=["a2", "a5"])
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import itertools


class ClusterAgentAPI:
    """API library for graph coloring operations exposed to backend LLM.

    This class wraps ClusterAgent's algorithmic functions in a clean API
    that backend LLMs can call via function/tool calling or ReAct patterns.

    Parameters
    ----------
    agent : ClusterAgent
        The cluster agent instance to expose API for

    Attributes
    ----------
    agent : ClusterAgent
        The underlying cluster agent
    """

    def __init__(self, agent: Any) -> None:
        """Initialize API library with reference to agent.

        Parameters
        ----------
        agent : ClusterAgent
            The cluster agent instance to wrap
        """
        self.agent = agent

    # ------------------------------------------------------------------
    # Core Assignment Operations
    # ------------------------------------------------------------------

    def compute_assignments(self, algorithm: str = "maxsum") -> Dict[str, str]:
        """Run local solver and return node assignments.

        Computes optimal color assignments for all nodes in this cluster
        using the specified algorithm. Respects fixed and forced constraints.

        Parameters
        ----------
        algorithm : str, optional
            Solver algorithm to use. Options:
            - "maxsum": Exhaustive search over all combinations (default, guarantees optimal)
            - "greedy": Fast sequential greedy coloring (may miss optimal solutions)

        Returns
        -------
        Dict[str, str]
            Dictionary mapping node names to colors
            Example: {"a1": "red", "a2": "blue", "a3": "green"}

        Notes
        -----
        - Fixed nodes (immutable constraints) are always respected
        - Forced nodes (human requests) are treated as soft constraints
        - Maxsum (exhaustive) guarantees optimal solution but runs in O(k^n)
        - For small clusters (5 nodes, 3 colors = 243 combinations), exhaustive is fast
        - Greedy runs in O(n*k) but may miss optimal solutions
        """
        # Temporarily override algorithm
        original_algorithm = self.agent.algorithm
        self.agent.algorithm = algorithm.lower()

        try:
            result = self.agent.compute_assignments()
            self.agent.log(f"[API] compute_assignments({algorithm}) -> {result}")
            return result
        finally:
            self.agent.algorithm = original_algorithm

    def get_current_penalty(self) -> Tuple[float, List[Tuple[str, str]]]:
        """Return current penalty and list of conflicts.

        Evaluates the current assignment and identifies all edge conflicts
        (adjacent nodes with the same color).

        Returns
        -------
        penalty : float
            Total penalty (number of conflicts * conflict_penalty)
        conflicts : List[Tuple[str, str]]
            List of conflicting edge pairs
            Example: [("a2", "h1"), ("a5", "h2")]

        Notes
        -----
        - Penalty is 0 if no conflicts exist (valid coloring)
        - Only counts conflicts on visible edges (respects partial observability)
        - External node colors are taken from neighbour_assignments
        """
        # Build combined assignment (local + known neighbours)
        combined = {**self.agent.neighbour_assignments, **self.agent.assignments}

        # Evaluate penalty using problem's evaluation function
        penalty = self.agent.problem.evaluate_assignment(combined)

        # Identify conflicts
        conflicts = []
        for u, v in self.agent.problem.edges:
            # Only count edges where both nodes are assigned
            if u in combined and v in combined:
                if combined[u] == combined[v]:
                    conflicts.append((u, v))

        self.agent.log(f"[API] get_current_penalty() -> penalty={penalty}, conflicts={len(conflicts)}")
        return penalty, conflicts

    def test_configuration(self, assignments: Dict[str, str]) -> Dict[str, Any]:
        """Test a proposed configuration and return penalty, conflicts, feasibility.

        Evaluates a hypothetical assignment without modifying the agent's state.
        Useful for exploring "what-if" scenarios.

        Parameters
        ----------
        assignments : Dict[str, str]
            Proposed node assignments to test
            Example: {"a2": "blue", "a5": "green"}

        Returns
        -------
        Dict[str, Any]
            Results dictionary with keys:
            - penalty: float - Total penalty
            - conflicts: List[Tuple[str, str]] - Conflicting edges
            - feasible: bool - True if penalty == 0
            - assignments: Dict[str, str] - The tested assignments

        Example
        -------
        >>> result = api.test_configuration({"a2": "blue", "a5": "green"})
        >>> if result["feasible"]:
        ...     print("Valid coloring!")
        """
        # Merge with current neighbour beliefs
        test_combined = {**self.agent.neighbour_assignments, **assignments}

        # Evaluate penalty
        penalty = self.agent.problem.evaluate_assignment(test_combined)

        # Identify conflicts
        conflicts = []
        for u, v in self.agent.problem.edges:
            if u in test_combined and v in test_combined:
                if test_combined[u] == test_combined[v]:
                    conflicts.append((u, v))

        result = {
            "penalty": penalty,
            "conflicts": conflicts,
            "feasible": penalty < 1e-6,
            "assignments": assignments
        }

        self.agent.log(f"[API] test_configuration({assignments}) -> feasible={result['feasible']}, penalty={penalty}")
        return result

    # ------------------------------------------------------------------
    # Counterfactual & Alternative Generation
    # ------------------------------------------------------------------

    def enumerate_alternatives(self, nodes: Optional[List[str]] = None, max_alternatives: int = 10) -> List[Dict[str, str]]:
        """Enumerate alternative colorings for specified nodes.

        Generates feasible alternative assignments by trying different color
        combinations for the specified nodes while keeping others fixed.

        Parameters
        ----------
        nodes : List[str], optional
            Nodes to generate alternatives for. If None, uses boundary nodes.
        max_alternatives : int, optional
            Maximum number of alternatives to return (default: 10)

        Returns
        -------
        List[Dict[str, str]]
            List of alternative assignments, sorted by penalty (best first)
            Example: [
                {"a2": "blue", "a5": "green"},
                {"a2": "green", "a5": "red"},
                ...
            ]

        Notes
        -----
        - Only returns assignments with penalty=0 (valid colorings)
        - If nodes=None, generates alternatives for boundary nodes
        - Computationally expensive: O(k^n) where k=colors, n=len(nodes)
        """
        if nodes is None:
            # Default: generate alternatives for boundary nodes
            nodes = [n for n in self.agent.nodes
                    if any((n, ext) in self.agent.problem.edges or (ext, n) in self.agent.problem.edges
                          for ext in self.agent.neighbour_assignments.keys())]

        # Filter to only nodes this agent controls
        nodes = [n for n in nodes if n in self.agent.nodes]

        if not nodes:
            self.agent.log("[API] enumerate_alternatives() -> No valid nodes to enumerate")
            return []

        # Respect fixed and forced constraints
        fixed = dict(getattr(self.agent, "fixed_local_nodes", {}) or {})
        forced = dict(getattr(self.agent, "forced_local_assignments", {}) or {})
        constrained = dict(forced)
        constrained.update(fixed)

        # Remove constrained nodes from enumeration
        free_nodes = [n for n in nodes if n not in constrained]

        if not free_nodes:
            self.agent.log("[API] enumerate_alternatives() -> All nodes are constrained")
            return [dict(constrained)]

        alternatives = []

        # Generate combinations
        for combo in itertools.product(self.agent.domain, repeat=len(free_nodes)):
            candidate = dict(self.agent.assignments)  # Start with current
            candidate.update(constrained)  # Apply constraints
            candidate.update({node: color for node, color in zip(free_nodes, combo)})

            # Test this candidate
            result = self.test_configuration(candidate)

            if result["feasible"]:
                alternatives.append(candidate)

                if len(alternatives) >= max_alternatives:
                    break

        self.agent.log(f"[API] enumerate_alternatives(nodes={nodes}, max={max_alternatives}) -> {len(alternatives)} alternatives")
        return alternatives

    def get_conflict_resolution_options(self, max_options: int = 5) -> List[Dict[str, Any]]:
        """Generate options for resolving current conflicts.

        Analyzes current conflicts and generates specific resolution options
        by identifying which node recolorings would eliminate conflicts.

        Parameters
        ----------
        max_options : int, optional
            Maximum number of options to return (default: 5)

        Returns
        -------
        List[Dict[str, Any]]
            List of resolution options, each containing:
            - changes: Dict[str, str] - Proposed node recolorings
            - resolves: List[Tuple[str, str]] - Conflicts this resolves
            - penalty: float - Resulting penalty
            - feasible: bool - Whether this achieves penalty=0

        Example
        -------
        >>> options = api.get_conflict_resolution_options()
        >>> for opt in options:
        ...     print(f"Change {opt['changes']} resolves {len(opt['resolves'])} conflicts")
        """
        penalty, conflicts = self.get_current_penalty()

        if not conflicts:
            self.agent.log("[API] get_conflict_resolution_options() -> No conflicts to resolve")
            return []

        # Identify nodes involved in conflicts
        conflict_nodes = set()
        for u, v in conflicts:
            if u in self.agent.nodes:
                conflict_nodes.add(u)
            if v in self.agent.nodes:
                conflict_nodes.add(v)

        if not conflict_nodes:
            self.agent.log("[API] get_conflict_resolution_options() -> No local nodes in conflicts")
            return []

        options = []

        # Try recoloring each conflict node
        for node in conflict_nodes:
            for color in self.agent.domain:
                if color == self.agent.assignments.get(node):
                    continue  # Skip current color

                # Test this change
                test_assign = dict(self.agent.assignments)
                test_assign[node] = color
                result = self.test_configuration(test_assign)

                # Check which original conflicts this resolves
                original_conflicts = set(conflicts)
                remaining_conflicts = set(result["conflicts"])
                resolved = original_conflicts - remaining_conflicts

                if resolved:  # Only include if it resolves something
                    options.append({
                        "changes": {node: color},
                        "resolves": list(resolved),
                        "penalty": result["penalty"],
                        "feasible": result["feasible"]
                    })

        # Sort by number of conflicts resolved (descending)
        options.sort(key=lambda x: len(x["resolves"]), reverse=True)

        result = options[:max_options]
        self.agent.log(f"[API] get_conflict_resolution_options(max={max_options}) -> {len(result)} options")
        return result

    # ------------------------------------------------------------------
    # Neighbor & Boundary Operations
    # ------------------------------------------------------------------

    def get_boundary_nodes(self, recipient: Optional[str] = None) -> List[str]:
        """Get boundary nodes for a specific neighbor or all boundary nodes.

        Boundary nodes are nodes owned by neighbors that connect to this cluster.

        Parameters
        ----------
        recipient : str, optional
            Name of specific neighbor. If None, returns all boundary nodes.

        Returns
        -------
        List[str]
            List of boundary node names
            Example: ["h1", "h2", "h5"]
        """
        if recipient is None:
            # Return all boundary nodes
            boundary = list(self.agent.neighbour_assignments.keys())
            self.agent.log(f"[API] get_boundary_nodes() -> {len(boundary)} nodes")
            return boundary

        # Filter by recipient
        boundary = []
        for node in self.agent.neighbour_assignments.keys():
            if self.agent.owners.get(node) == recipient:
                boundary.append(node)

        self.agent.log(f"[API] get_boundary_nodes(recipient={recipient}) -> {len(boundary)} nodes")
        return boundary

    def get_neighbor_constraints(self, recipient: str) -> Dict[str, Any]:
        """Get constraints from neighbor's perspective.

        Returns information about what colors would cause conflicts with
        the specified neighbor's boundary nodes.

        Parameters
        ----------
        recipient : str
            Name of neighbor agent

        Returns
        -------
        Dict[str, Any]
            Dictionary with keys:
            - boundary_nodes: List[str] - Neighbor's nodes
            - forbidden_colors: Dict[str, List[str]] - Colors to avoid per node
            - current_assignments: Dict[str, str] - Current boundary colors
        """
        boundary = self.get_boundary_nodes(recipient)

        # For each boundary node, identify forbidden colors
        forbidden = {}
        for ext_node in boundary:
            forbidden_colors = []
            # Check edges from external node to our nodes
            for u, v in self.agent.problem.edges:
                if u == ext_node and v in self.agent.nodes:
                    # ext_node can't have same color as our node v
                    our_color = self.agent.assignments.get(v)
                    if our_color and our_color not in forbidden_colors:
                        forbidden_colors.append(our_color)
                elif v == ext_node and u in self.agent.nodes:
                    # ext_node can't have same color as our node u
                    our_color = self.agent.assignments.get(u)
                    if our_color and our_color not in forbidden_colors:
                        forbidden_colors.append(our_color)

            forbidden[ext_node] = forbidden_colors

        result = {
            "boundary_nodes": boundary,
            "forbidden_colors": forbidden,
            "current_assignments": {n: self.agent.neighbour_assignments.get(n) for n in boundary}
        }

        self.agent.log(f"[API] get_neighbor_constraints(recipient={recipient}) -> {len(boundary)} nodes")
        return result

    def simulate_neighbor_change(self, neighbor_nodes: Dict[str, str]) -> Dict[str, Any]:
        """Simulate impact of neighbor changing their assignments.

        Tests what would happen if neighbor nodes were recolored,
        without modifying the agent's actual state.

        Parameters
        ----------
        neighbor_nodes : Dict[str, str]
            Proposed neighbor assignments
            Example: {"h1": "red", "h2": "blue"}

        Returns
        -------
        Dict[str, Any]
            Impact analysis with keys:
            - new_conflicts: List[Tuple[str, str]] - New conflicts created
            - resolved_conflicts: List[Tuple[str, str]] - Conflicts resolved
            - net_penalty_change: float - Change in penalty
            - would_need_recolor: bool - Whether we'd need to change our colors
        """
        # Get current state
        current_penalty, current_conflicts = self.get_current_penalty()

        # VALIDATION: Warn if incomplete neighbor set provided
        # This helps catch bugs where only partial neighbor configs are passed
        known_neighbors = set(self.agent.neighbour_assignments.keys())
        provided_neighbors = set(neighbor_nodes.keys())
        missing_neighbors = known_neighbors - provided_neighbors

        if missing_neighbors:
            self.agent.log(f"[API WARNING] simulate_neighbor_change called with incomplete neighbors.")
            self.agent.log(f"  Known neighbors: {sorted(known_neighbors)}")
            self.agent.log(f"  Provided: {sorted(provided_neighbors)}")
            self.agent.log(f"  Missing: {sorted(missing_neighbors)}")
            self.agent.log(f"  This may cause incorrect penalty calculations!")

        # Simulate new state
        original_neighbor_assignments = dict(self.agent.neighbour_assignments)
        try:
            # Temporarily update beliefs
            self.agent.neighbour_assignments.update(neighbor_nodes)
            new_penalty, new_conflicts = self.get_current_penalty()

            # Analyze differences
            current_conflict_set = set(current_conflicts)
            new_conflict_set = set(new_conflicts)

            result = {
                "new_conflicts": list(new_conflict_set - current_conflict_set),
                "resolved_conflicts": list(current_conflict_set - new_conflict_set),
                "net_penalty_change": new_penalty - current_penalty,
                "would_need_recolor": new_penalty > 1e-6,
                "new_penalty": new_penalty,
                "current_penalty": current_penalty
            }

            self.agent.log(f"[API] simulate_neighbor_change({neighbor_nodes}) -> delta_penalty={result['net_penalty_change']}")
            return result

        finally:
            # Restore original state
            self.agent.neighbour_assignments = original_neighbor_assignments

    # ------------------------------------------------------------------
    # Feasibility & Constraint Checking
    # ------------------------------------------------------------------

    def check_feasibility(self, node: str, color: str) -> bool:
        """Check if a specific assignment is locally feasible.

        Tests whether assigning a color to a node would create conflicts
        with current assignments.

        Parameters
        ----------
        node : str
            Node name to check
        color : str
            Color to test

        Returns
        -------
        bool
            True if assignment is feasible (no conflicts), False otherwise
        """
        if node not in self.agent.nodes:
            self.agent.log(f"[API] check_feasibility({node}, {color}) -> Node not in cluster")
            return False

        # Test assignment
        test_assign = dict(self.agent.assignments)
        test_assign[node] = color
        result = self.test_configuration(test_assign)

        self.agent.log(f"[API] check_feasibility({node}={color}) -> {result['feasible']}")
        return result["feasible"]

    def get_available_colors(self, node: str) -> List[str]:
        """Get available colors for a node given current constraints.

        Returns list of colors that don't create conflicts if assigned to node.

        Parameters
        ----------
        node : str
            Node name

        Returns
        -------
        List[str]
            List of feasible colors
            Example: ["blue", "green"]
        """
        if node not in self.agent.nodes:
            self.agent.log(f"[API] get_available_colors({node}) -> Node not in cluster")
            return []

        available = []
        for color in self.agent.domain:
            if self.check_feasibility(node, color):
                available.append(color)

        self.agent.log(f"[API] get_available_colors({node}) -> {available}")
        return available

    # ------------------------------------------------------------------
    # Utility & Scoring Operations
    # ------------------------------------------------------------------

    def compute_utility_score(self, assignments: Dict[str, str], scoring_function: str = "color_points") -> float:
        """Compute utility score for an assignment using specified function.

        Parameters
        ----------
        assignments : Dict[str, str]
            Node assignments to score
        scoring_function : str, optional
            Scoring function name (default: "color_points")
            - "color_points": blue=1, green=2, red=3
            - "preference": Use problem's preference values

        Returns
        -------
        float
            Utility score
        """
        if scoring_function == "color_points":
            color_points = {"blue": 1, "green": 2, "red": 3}
            score = sum(color_points.get(assignments.get(n, "").lower(), 0)
                       for n in self.agent.nodes)
        elif scoring_function == "preference":
            score = sum(self.agent.problem.preferences[n][assignments.get(n, "blue")]
                       for n in self.agent.nodes
                       if n in assignments)
        else:
            score = 0.0

        self.agent.log(f"[API] compute_utility_score(fn={scoring_function}) -> {score}")
        return score

    def get_best_response_to(self, neighbor_assignments: Dict[str, str] = None) -> Dict[str, str]:
        """Get best response to hypothetical neighbor assignments.

        Computes optimal local coloring given specific neighbor colors.

        Parameters
        ----------
        neighbor_assignments : Dict[str, str], optional
            Hypothetical neighbor assignments.
            If None (default), uses current neighbor assignments from agent.neighbour_assignments.

        Returns
        -------
        Dict[str, str]
            Best local assignment with 'penalty' key included
        """
        # Default to current neighbor assignments if not specified
        if neighbor_assignments is None:
            neighbor_assignments = dict(self.agent.neighbour_assignments)
            self.agent.log(f"[API] get_best_response_to() called without args, using current neighbors: {neighbor_assignments}")

        # Use _best_local_assignment_for helper
        penalty, best_assign = self.agent._best_local_assignment_for(neighbor_assignments)

        # Include penalty in result so LLM can see if config works
        result = dict(best_assign)
        result['penalty'] = penalty

        self.agent.log(f"[API] get_best_response_to({neighbor_assignments}) -> penalty={penalty}")
        return result
