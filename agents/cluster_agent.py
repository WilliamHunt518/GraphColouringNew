"""Cluster agent implementation for clustered multi-graph DCOPs.

This module defines the :class:`ClusterAgent` which extends the existing
``MultiNodeAgent`` to support clustered graph colouring experiments. Each
cluster agent controls a collection of nodes (a local subgraph) and can
choose between different internal optimisation algorithms as well as
customisable message formats.  The class demonstrates how to decouple
the choice of local solver from the choice of message representation.

The email in the revised graph colouring approach describes three
distinct message styles that agents may use:

1. ``cost_list`` – send, for each neighbouring node owned by another
   cluster, a mapping from each colour to the cost incurred on the
   connecting edge if the neighbour were to choose that colour.  This
   mirrors the structured utility messages used in Max–Sum and allows
   recipients to fold the costs directly into their own optimisation.

2. ``constraints`` – send, for each neighbouring node owned by another
   cluster, the set of colours that would lead to zero clash on the
   connecting edge.  Recipients may treat the constraints as hard or
   soft restrictions when searching for an assignment.

3. ``free_text`` – send a short natural‑language description of the
   current local assignment and advise neighbouring clusters which
   colours to avoid.  When used in conjunction with an LLM‑based
   communication layer, this can be reformulated into more readable
   prose.

The choice of message style and local optimisation algorithm is
configured at construction time.  Internally, ``ClusterAgent`` reuses
the exhaustive search from ``MultiNodeAgent`` when ``algorithm`` is
``"maxsum"``.  A simple greedy colouring heuristic is provided for
``"greedy"`` whereby nodes are coloured sequentially to minimise
conflicts with already assigned neighbours.  Additional algorithms
could be implemented by adding further branches in ``compute_assignments``.

Note
----
This implementation is intended as a starting point for the new
clustered multi‑graph setup.  It does not implement sophisticated
interpretation of incoming messages beyond updating neighbour
assignments.  For instance, when receiving a ``cost_list`` or
``constraints`` message, the agent currently records the neighbour’s
announced assignments (if present) but does not explicitly adjust its
local evaluation.  Future work could extend the ``receive`` method
to interpret and exploit richer message types.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple, Set

import itertools
import re

from .multi_node_agent import MultiNodeAgent
from .base_agent import Message


class ClusterAgent(MultiNodeAgent):
    """Agent controlling a cluster of nodes with configurable behaviour.

    Parameters
    ----------
    name : str
        Identifier for this cluster (typically the owner name).
    problem : GraphColoring
        The global colouring problem instance.
    comm_layer : BaseCommLayer
        Communication layer used to format and parse messages.
    local_nodes : list[str]
        Nodes belonging to this cluster.
    owners : dict
        Mapping from node to the owner controlling it.  Used to route
        messages to neighbouring clusters.
    algorithm : str, optional
        Name of the internal optimisation algorithm to use.  Supported
        values are ``"greedy"`` and ``"maxsum"``.  Defaults to
        ``"greedy"``.
    message_type : str, optional
        Message style used when communicating with neighbouring clusters.
        Supported values are ``"cost_list"``, ``"constraints"`` and
        ``"free_text"``.  Defaults to ``"cost_list"``.

    Attributes
    ----------
    assignments : dict[str, Any]
        Current colour assignments for nodes in this cluster.
    neighbour_assignments : dict[str, Any]
        Latest known assignments for external nodes.  Updated upon
        receipt of messages.
    """

    def __init__(
        self,
        name: str,
        problem: Any,
        comm_layer: Any,
        local_nodes: List[str],
        owners: Dict[str, str],
        algorithm: str = "greedy",
        message_type: str = "cost_list",
        counterfactual_utils: bool = True,
        initial_assignments: Optional[Dict[str, Any]] = None,
        fixed_local_nodes: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Call parent initialiser to set up assignments and neighbour tracking.
        super().__init__(
            name=name,
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=local_nodes,
            owners=owners,
            initial_assignments=initial_assignments,
        )
        self.algorithm = algorithm.lower()
        self.message_type = message_type.lower()
        # When True, the agent derives cost/constraint hints for boundary nodes
        # using a best-response counterfactual search ("If you pick colour c, my
        # best achievable local penalty would be …"). When False, it uses a
        # naive evaluation against the agent's *current* local assignment.
        self.counterfactual_utils: bool = bool(counterfactual_utils)

        # --- debug state for experimenter UI ---
        self.debug_incoming_raw: List[Any] = []
        self.debug_incoming_parsed: List[Any] = []
        self.debug_last_outgoing: Dict[str, Any] = {}
        self.debug_last_decision: Dict[str, Any] = {}

        # Soft convergence flag used by the study stopping criterion.
        # True means the agent believes its current assignment is locally optimal
        # given what it *believes* about neighbour assignments (from messages).
        self.satisfied: bool = False

        # Fixed nodes (immutable constraints set at initialization to force negotiation).
        # These take highest priority and cannot be changed by any algorithm or human input.
        self.fixed_local_nodes: Dict[str, Any] = dict(fixed_local_nodes) if fixed_local_nodes else {}

        # When the human explicitly requests a colour for one of this agent's
        # own nodes (e.g. "pick blue for b2"), we treat it as a *soft forced*
        # assignment that the local solver should respect.
        self.forced_local_assignments: Dict[str, str] = {}

        # Best-effort memory of the most recent human message. This lets the agent
        # decide when the human actually asked about *team/combined* utility.
        # Default behaviour is local: reason about feasibility and this agent's score.
        self._last_human_text: str = ""

        # Track previous boundary state for change detection (Fix 3)
        # Used to reset satisfaction when human changes boundary node colors
        self._previous_neighbour_assignments: Dict[str, Any] = {}

        # Track human-stated constraints on boundary nodes (Fix 4)
        # Format: {node_name: {"forbidden": [colors], "required": color_or_None}}
        # Example: {"h1": {"forbidden": ["green", "red"], "required": None}}
        self._human_stated_constraints: Dict[str, Dict[str, Any]] = {}

        # Message deduplication: track recent messages to avoid sending duplicates
        self._recent_messages: List[Tuple[str, str]] = []  # List of (recipient, message_hash)
        self._max_message_history = 5  # Remember last 5 messages

        # Track if human sent a message this turn (to force a response even if content is same)
        self._received_human_message_this_turn = False

        # Counterfactual caching system (Phase 5)
        # Stores computed counterfactual options for reuse in conversational responses
        self._cached_counterfactuals: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_boundary_state: Optional[Dict[str, Any]] = None

        # Message classification tracking (Phase 2)
        self._last_message_classification: Optional[Any] = None
        self._last_message_result: Optional[Dict[str, Any]] = None  # Stores handler results (counterfactuals, searches)

    # ------------------------------------------------------------------
    # Message deduplication helpers
    # ------------------------------------------------------------------

    def _hash_message(self, content: Any) -> str:
        """Create a hash of message content for deduplication.

        Parameters
        ----------
        content : Any
            Message content to hash

        Returns
        -------
        str
            Hash string for comparison
        """
        import hashlib
        import json

        try:
            # Convert content to a canonical string representation
            if isinstance(content, dict):
                # For dict content, extract key information only
                msg_type = content.get("type", "unknown")
                data = content.get("data", {})

                if msg_type == "cost_list" and isinstance(data, dict):
                    # For cost_list: hash the options (top configurations)
                    options = data.get("options", [])[:3]  # Only top 3 matter
                    key_info = {
                        "type": msg_type,
                        "num_options": len(options),
                        "top_options": str(sorted([str(o.get("human", {})) for o in options]))
                    }
                elif msg_type == "constraints" and isinstance(data, dict):
                    # For constraints: hash the valid configs
                    valid_configs = data.get("valid_configs", [])[:3]
                    per_node = data.get("per_node", {})
                    key_info = {
                        "type": msg_type,
                        "configs": str(sorted([str(c) for c in valid_configs])),
                        "per_node": str(sorted(per_node.items()))
                    }
                else:
                    # For other types: use string representation
                    key_info = {"type": msg_type, "data": str(data)[:200]}

                content_str = json.dumps(key_info, sort_keys=True)
            else:
                content_str = str(content)[:200]  # Truncate long strings

            return hashlib.md5(content_str.encode()).hexdigest()[:16]
        except Exception:
            # If hashing fails, use simple string hash
            return str(hash(str(content)))[:16]

    def _is_duplicate_message(self, recipient: str, content: Any) -> bool:
        """Check if this message is a duplicate of recently sent messages.

        Parameters
        ----------
        recipient : str
            Message recipient
        content : Any
            Message content

        Returns
        -------
        bool
            True if this is a duplicate message
        """
        msg_hash = self._hash_message(content)

        # Check if we recently sent the same message to this recipient
        for recent_recipient, recent_hash in self._recent_messages:
            if recent_recipient == recipient and recent_hash == msg_hash:
                return True

        return False

    def _record_message(self, recipient: str, content: Any) -> None:
        """Record a sent message for deduplication tracking.

        Parameters
        ----------
        recipient : str
            Message recipient
        content : Any
            Message content
        """
        msg_hash = self._hash_message(content)
        self._recent_messages.append((recipient, msg_hash))

        # Keep only last N messages
        if len(self._recent_messages) > self._max_message_history:
            self._recent_messages = self._recent_messages[-self._max_message_history:]

    # ------------------------------------------------------------------
    # Counterfactual caching helpers (Phase 5)
    # ------------------------------------------------------------------

    def _cache_counterfactuals(self, counterfactuals: Dict[str, Any]) -> None:
        """Cache computed counterfactual options for reuse in conversational responses.

        Parameters
        ----------
        counterfactuals : dict
            Computed counterfactual options (e.g., from cost_list or constraints generation)
        """
        import time
        self._cached_counterfactuals = counterfactuals
        self._cache_timestamp = time.time()
        # Store boundary state for cache invalidation
        self._cache_boundary_state = dict(self._get_boundary_assignments())

    def _get_cached_counterfactuals(self) -> Optional[Dict[str, Any]]:
        """Retrieve cached counterfactuals if valid.

        Returns
        -------
        dict or None
            Cached counterfactuals if cache is valid, None otherwise
        """
        if self._cached_counterfactuals is None:
            return None

        # Check if boundary state has changed (invalidates cache)
        current_boundary = self._get_boundary_assignments()
        if self._cache_boundary_state != current_boundary:
            self._invalidate_cache()
            return None

        return self._cached_counterfactuals

    def _invalidate_cache(self) -> None:
        """Invalidate the counterfactual cache."""
        self._cached_counterfactuals = None
        self._cache_timestamp = None
        self._cache_boundary_state = None

    def _get_boundary_assignments(self) -> Dict[str, Any]:
        """Get current boundary node assignments (neighbour nodes this agent sees).

        Returns
        -------
        dict
            Dictionary of boundary node assignments
        """
        # Boundary nodes are the neighbour nodes (nodes owned by other clusters)
        boundary_nodes = [n for n in self.neighbour_assignments.keys()]
        return {n: self.neighbour_assignments.get(n) for n in boundary_nodes}

    # ------------------------------------------------------------------
    # Color normalization helper
    # ------------------------------------------------------------------

    def _normalize_color(self, color: Any) -> Any:
        """Normalize a color value to match the domain's exact casing.

        This is critical because colors may be extracted from text as lowercase
        (e.g., "red" from regex), but the domain may use different casing (e.g., "Red"),
        and penalty calculations use exact equality checks.

        Parameters
        ----------
        color : Any
            Color value to normalize (may be string, etc.)

        Returns
        -------
        Any
            The matching domain color, or the original color if no match found
        """
        if color is None:
            return None
        color_str = str(color).lower()
        for domain_color in self.domain:
            if str(domain_color).lower() == color_str:
                return domain_color
        # No match found - return original (defensive)
        return color

    # ------------------------------------------------------------------
    # Assignment computation
    #
    # ``MultiNodeAgent`` uses exhaustive search to find the best joint
    # assignment.  In the clustered framework we allow agents to use
    # simpler heuristics locally.  The main entry point for computing
    # assignments is ``compute_assignments`` which returns a new mapping
    # for the cluster’s nodes.

    def compute_assignments(self) -> Dict[str, Any]:
        """Compute a new assignment for this cluster.

        Returns a dictionary mapping local nodes to colours.  The
        choice of algorithm is controlled by ``self.algorithm``.
        """
        if self.algorithm == "maxsum":
            # fall back to exhaustive search implemented in MultiNodeAgent
            # compute best assignment by evaluating all combinations
            best_assignment: Dict[str, Any] = dict(self.assignments)
            best_penalty: float = self.evaluate_candidate(best_assignment)
            # iterate over cartesian product of colours for local nodes
            # Priority: fixed (immutable) > forced (human-requested) > free (optimizable)
            fixed = dict(getattr(self, "fixed_local_nodes", {}) or {})
            forced = dict(getattr(self, "forced_local_assignments", {}) or {})
            # Merge fixed and forced (fixed takes precedence)
            constrained = dict(forced)
            constrained.update(fixed)
            free_nodes = [n for n in self.nodes if n not in constrained]
            for combo in itertools.product(self.domain, repeat=len(free_nodes)):
                candidate = dict(constrained)
                candidate.update({node: val for node, val in zip(free_nodes, combo)})
                penalty = self.evaluate_candidate(candidate)
                if penalty < best_penalty:
                    best_assignment = candidate
                    best_penalty = penalty
            return best_assignment
        elif self.algorithm == "greedy":
            # simple greedy algorithm: colour nodes sequentially
            new_assignment: Dict[str, Any] = {}
            # Debug: store the computed penalty for each colour option per node
            # so the experimenter can inspect the agent's decision process.
            try:
                self.debug_last_local_scores = {}  # type: ignore[attr-defined]
            except Exception:
                pass
            # Priority: fixed (immutable) > forced (human-requested) > free (optimizable)
            fixed = dict(getattr(self, "fixed_local_nodes", {}) or {})
            forced = dict(getattr(self, "forced_local_assignments", {}) or {})
            # Merge fixed and forced (fixed takes precedence)
            constrained = dict(forced)
            constrained.update(fixed)
            for node in self.nodes:
                if node in constrained:
                    new_assignment[node] = constrained[node]
                    try:
                        self.debug_last_local_scores[node] = {constrained[node]: 0.0}  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    continue
                best_val = None
                best_score = float("inf")
                local_scores: Dict[Any, float] = {}
                for val in self.domain:
                    # compute penalty for assigning val to node
                    penalty = 0.0
                    # internal conflicts with already coloured local nodes
                    for u, v in self.problem.edges:
                        if node == u and v in new_assignment:
                            if val == new_assignment[v]:
                                penalty += self.problem.conflict_penalty
                        elif node == v and u in new_assignment:
                            if val == new_assignment[u]:
                                penalty += self.problem.conflict_penalty
                    # conflicts with known external assignments
                    for u, v in self.problem.edges:
                        if node == u and v not in self.nodes:
                            ext_val = self.neighbour_assignments.get(v)
                            if ext_val is not None and ext_val == val:
                                penalty += self.problem.conflict_penalty
                        elif node == v and u not in self.nodes:
                            ext_val = self.neighbour_assignments.get(u)
                            if ext_val is not None and ext_val == val:
                                penalty += self.problem.conflict_penalty
                    # subtract preference (higher preference should lower penalty)
                    penalty -= self.problem.preferences[node][val]
                    local_scores[val] = penalty
                    if penalty < best_score:
                        best_score = penalty
                        best_val = val
                # assign best value found
                new_assignment[node] = best_val
                try:
                    self.debug_last_local_scores[node] = dict(local_scores)  # type: ignore[attr-defined]
                except Exception:
                    pass
            return new_assignment
        else:
            # default to random assignment if algorithm unknown
            import random

            return {node: random.choice(self.domain) for node in self.nodes}

    # ------------------------------------------------------------------
    # Soft convergence / satisfaction

    def _best_local_assignment_for(self, base: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """Return the best local assignment for a given neighbour-belief base.

        We evaluate *only* on edges where both endpoints are assigned.
        Unknown neighbour assignments are ignored (they contribute 0).

        Because cluster sizes are small (e.g., 5 nodes), an exhaustive
        search over the local domain is cheap (3^5 = 243 combinations).
        """
        import itertools

        base = dict(base or {})
        best_pen = float("inf")
        best_assign = dict(self.assignments)

        # Respect fixed and forced constraints
        fixed = dict(getattr(self, "fixed_local_nodes", {}) or {})
        forced = dict(getattr(self, "forced_local_assignments", {}) or {})
        constrained = dict(forced)
        constrained.update(fixed)
        free_nodes = [n for n in self.nodes if n not in constrained]

        for combo in itertools.product(self.domain, repeat=len(free_nodes)):
            cand = dict(constrained)
            cand.update({n: v for n, v in zip(free_nodes, combo)})
            pen = self.problem.evaluate_assignment({**base, **cand})
            if pen < best_pen:
                best_pen = pen
                best_assign = cand
        return best_pen, best_assign

    def _best_local_assignment(self) -> tuple[float, Dict[str, Any]]:
        """Return the best local assignment given current neighbour beliefs."""
        base = dict(getattr(self, "neighbour_assignments", {}) or {})
        return self._best_local_assignment_for(base)

    def _compute_valid_boundary_configs_with_constraints(self, max_configs=10):
        """
        Compute valid boundary configurations respecting human-stated constraints.

        Returns list of dicts representing valid boundary configurations.
        Example: [{"h2": "red", "h5": "blue"}, {"h2": "blue", "h5": "green"}, ...]

        Each configuration is tested to ensure the agent can achieve penalty=0.
        Uses exhaustive enumeration to find ALL valid combinations (not just per-node minimal).
        """
        import itertools

        # Get boundary nodes (neighbors we don't control)
        boundary_nodes = sorted([n for n in getattr(self, "neighbour_assignments", {}).keys()])
        if not boundary_nodes:
            return []

        # For each boundary node, collect allowed colors (respecting human constraints only)
        allowed_per_node = {}
        for node in boundary_nodes:
            allowed = []
            for color in self.domain:
                # Check human-stated constraints
                node_lower = str(node).lower()
                color_lower = str(color).lower()
                constraints = self._human_stated_constraints.get(node_lower, {})

                # Skip forbidden colors
                if color_lower in constraints.get("forbidden", []):
                    self.log(f"Skipping {node}={color} (forbidden by human constraint)")
                    continue

                # If required color is specified, only allow that
                required = constraints.get("required")
                if required and color_lower != str(required).lower():
                    continue

                allowed.append(color)

            allowed_per_node[node] = allowed
            if not allowed:
                self.log(f"WARNING: No allowed colors for boundary node {node} after constraints!")

        # If any node has no allowed colors, return empty (no valid configs)
        if any(len(allowed_per_node[n]) == 0 for n in boundary_nodes):
            return []

        # Enumerate ALL combinations and test each for penalty=0
        valid_configs = []
        base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})
        try:
            color_lists = [allowed_per_node[n] for n in boundary_nodes]
            for combo in itertools.product(*color_lists):
                config = {boundary_nodes[i]: combo[i] for i in range(len(boundary_nodes))}

                # Test if this combination achieves penalty=0
                tmp_beliefs = dict(base_beliefs)
                tmp_beliefs.update(config)
                try:
                    best_pen, _ = self._best_local_assignment_for(tmp_beliefs)
                    if best_pen < 1e-6:  # Valid configuration
                        valid_configs.append(config)
                        if len(valid_configs) >= max_configs:
                            break
                except Exception:
                    # Ignore errors when testing individual configs
                    continue
        except Exception as e:
            self.log(f"Error enumerating configs: {e}")

        self.log(f"Computed {len(valid_configs)} valid boundary configurations")
        return valid_configs

    def _compute_satisfied(self) -> bool:
        """Whether the agent is satisfied with its current assignment.

        Agent is satisfied ONLY if:
        1. There are NO conflicts (penalty = 0), AND
        2. Current assignment is as good as the best possible local assignment

        If there are boundary conflicts (penalty > 0), agent should NEVER be satisfied,
        even if it can't do better locally - the human needs to change boundary colors.
        """
        base = dict(getattr(self, "neighbour_assignments", {}) or {})
        current_pen = self.problem.evaluate_assignment({**base, **dict(self.assignments)})

        # DEFENSIVE: Verify penalty calculation matches conflict detection
        # This helps debug cases where agents claim to be conflict-free when they're not
        conflict_count = 0
        for my_node in self.nodes:
            my_color = self.assignments.get(my_node)
            for nbr in self.problem.get_neighbors(my_node):
                if nbr not in self.nodes:  # External neighbor (boundary)
                    nbr_color = base.get(nbr)
                    if nbr_color and my_color and str(nbr_color).lower() == str(my_color).lower():
                        conflict_count += 1
                        self.log(f"BOUNDARY CONFLICT DETECTED: {my_node}({my_color}) <-> {nbr}({nbr_color})")

        if conflict_count > 0 and current_pen < 1e-9:
            # BUG DETECTED: Conflicts exist but penalty is 0!
            self.log(f"BUG WARNING: {conflict_count} conflicts detected but penalty={current_pen:.6f}")
            self.log(f"  My assignments: {dict(self.assignments)}")
            self.log(f"  Neighbor assignments: {base}")
            # Force return False since we know there are conflicts
            return False

        # CRITICAL: Never satisfied if there are conflicts (penalty > 0)
        # Even if we can't do better given current boundary, we're not satisfied
        # because the boundary needs to change to achieve a valid coloring
        if current_pen > 1e-9:
            self.log(f"Not satisfied: current_penalty={current_pen:.3f} > 0")
            return False

        # No conflicts - check if we're at local optimum
        best_pen, _ = self._best_local_assignment()
        is_satisfied = current_pen <= best_pen + 1e-9
        self.log(f"Satisfaction check: penalty=0, at_optimum={is_satisfied}")
        return is_satisfied

    # ------------------------------------------------------------------
    # Message handlers (Phases 3, 4, 7)
    # ------------------------------------------------------------------

    def _handle_query(self, classification_result: Any) -> Dict[str, Any]:
        """Handle QUERY messages by computing counterfactuals and answering questions.

        Parameters
        ----------
        classification_result : ClassificationResult
            Classified message with extracted nodes/colors

        Returns
        -------
        dict
            Response data with counterfactual information
        """
        nodes = classification_result.extracted_nodes
        colors = classification_result.extracted_colors
        text_lower = classification_result.raw_text.lower()

        # Query type 1: "What could I set X to?" / "What should X be?"
        # MUST come before general options check (more specific pattern)
        # Detect queries asking for valid values of a specific boundary node
        asking_about_node_value = any(phrase in text_lower for phrase in [
            "what could i set", "what should i set", "what can i set",
            "what could i change", "what should i change", "what can i change",
            "what about", "could i set", "should i set", "can i set",
            "tell me what i can set"
        ])

        if asking_about_node_value and nodes:
            # Extract the node being asked about
            query_node = None
            for node in nodes:
                if node in self.neighbour_assignments:
                    query_node = node
                    break

            if query_node:
                # Keep other boundary nodes fixed, search for valid values of query_node
                fixed_boundary = {k: v for k, v in self.neighbour_assignments.items() if k != query_node}
                valid_colors = []

                self.log(f"Query handler: Searching valid values for {query_node} (keeping {fixed_boundary} fixed)")

                for color in self.domain:
                    test_boundary = dict(fixed_boundary)
                    test_boundary[query_node] = color

                    best_pen, best_asg = self._best_local_assignment_for(test_boundary)
                    if best_pen < 1e-6:  # Valid configuration
                        valid_colors.append(color)
                        self.log(f"  {query_node}={color} works (penalty=0)")
                    else:
                        self.log(f"  {query_node}={color} fails (penalty={best_pen:.2f})")

                return {
                    "query_type": "node_value_search",
                    "query_node": query_node,
                    "fixed_boundary": fixed_boundary,
                    "valid_colors": valid_colors,
                    "message": f"Given {', '.join([f'{k}={v}' for k, v in fixed_boundary.items()])}, you could set {query_node} to: {', '.join(valid_colors) if valid_colors else 'NO valid options'}"
                }

        # Query type 2: "What are my options?" / "What settings could I choose?"
        # General query for all boundary configuration options
        asking_for_options = any(phrase in text_lower for phrase in [
            "option", "settings", "configuration",
            "other configuration", "alternatives", "what else",
            "what would work"
        ])

        if asking_for_options:
            result = self._enumerate_boundary_options()
            self.log(f"Query handler: Enumerating boundary options (found {len(result.get('options', []))} configs)")
            return result

        # Query type 3: "Can you solve with X?"
        if ("can you" in text_lower or "can i" in text_lower) and nodes and colors:
            # Extract the hypothetical boundary configuration
            hypothetical = dict(self.neighbour_assignments)
            for node, color in zip(nodes, colors):
                if node in hypothetical:  # Only update boundary nodes
                    hypothetical[node] = self._normalize_color(color)

            # Compute counterfactual
            best_pen, best_asg = self._best_local_assignment_for(hypothetical)

            return {
                "query_type": "feasibility",
                "can_solve": best_pen < 1e-9,
                "penalty": float(best_pen),
                "agent_assignment": best_asg,
                "agent_score": self._score_for(best_asg, list(self.nodes))
            }

        # Query type 3: "What color is X?"
        if nodes and ("what" in text_lower or "which" in text_lower):
            node = nodes[0]
            if node in self.assignments:
                color = self.assignments[node]
                return {
                    "query_type": "state",
                    "node": node,
                    "color": color
                }
            elif node in self.neighbour_assignments:
                color = self.neighbour_assignments.get(node)
                return {
                    "query_type": "state",
                    "node": node,
                    "color": color,
                    "note": "boundary_node"
                }

        # Default: return current state
        return {
            "query_type": "general",
            "assignments": dict(self.assignments),
            "boundary": dict(self.neighbour_assignments)
        }

    def _handle_preference(self, classification_result: Any) -> Dict[str, Any]:
        """Handle PREFERENCE messages by exploring counterfactuals WITHOUT binding as constraint.

        Parameters
        ----------
        classification_result : ClassificationResult
            Classified message with extracted nodes/colors

        Returns
        -------
        dict
            Response data with counterfactual exploration and pattern analysis
        """
        nodes = classification_result.extracted_nodes
        colors = classification_result.extracted_colors

        if not nodes or not colors:
            # No specific preference extracted, enumerate general options
            return self._enumerate_boundary_options()

        # Extract preferred configuration from message
        preferred_config = dict(self.neighbour_assignments)
        for node, color in zip(nodes, colors):
            if node in preferred_config:  # Only update boundary nodes
                preferred_config[node] = self._normalize_color(color)

        # Compute counterfactual for preferred configuration
        pref_pen, pref_asg = self._best_local_assignment_for(preferred_config)
        pref_score = self._score_for(pref_asg, list(self.nodes))

        # Compute alternatives
        alternatives = self._enumerate_boundary_options()

        # Analyze patterns across alternatives
        pattern_analysis = self._analyze_option_patterns(alternatives.get("options", []))

        return {
            "preference_type": "counterfactual",
            "preferred": {
                "config": preferred_config,
                "penalty": float(pref_pen),
                "agent_score": int(pref_score),
                "feasible": pref_pen < 1e-9
            },
            "num_alternatives": len(alternatives.get("options", [])),
            "pattern": pattern_analysis,
            "alternatives": alternatives.get("options", [])[:5]  # Top 5 for reference
        }

    def _handle_information(self, classification_result: Any) -> Dict[str, Any]:
        """Handle INFORMATION messages by updating constraints.

        Parameters
        ----------
        classification_result : ClassificationResult
            Classified message with extracted constraint information

        Returns
        -------
        dict
            Acknowledgment with impact summary
        """
        text_lower = classification_result.raw_text.lower()
        nodes = classification_result.extracted_nodes
        colors = classification_result.extracted_colors

        if not nodes or not colors:
            return {"info_type": "general", "acknowledged": True}

        # Extract constraint type (negative or positive)
        node = nodes[0]
        color = self._normalize_color(colors[0]) if colors else None

        # Negative constraint: "h1 can never be green"
        if any(phrase in text_lower for phrase in ["can't be", "cannot be", "never", "avoid"]):
            if node not in self._human_stated_constraints:
                self._human_stated_constraints[node] = {"forbidden": [], "required": None}

            if color and color not in self._human_stated_constraints[node]["forbidden"]:
                self._human_stated_constraints[node]["forbidden"].append(color)

            # Invalidate cache since constraints changed
            self._invalidate_cache()

            return {
                "info_type": "negative_constraint",
                "node": node,
                "forbidden_color": color,
                "acknowledged": True,
                "impact": "Constraint updated, recomputing solutions"
            }

        # Positive constraint: "h1 must be red"
        elif any(phrase in text_lower for phrase in ["must be", "has to be", "needs to be"]):
            if node not in self._human_stated_constraints:
                self._human_stated_constraints[node] = {"forbidden": [], "required": None}

            self._human_stated_constraints[node]["required"] = color

            # Invalidate cache since constraints changed
            self._invalidate_cache()

            return {
                "info_type": "positive_constraint",
                "node": node,
                "required_color": color,
                "acknowledged": True,
                "impact": "Constraint updated, recomputing solutions"
            }

        # General information (e.g., "b2 is currently red")
        else:
            return {
                "info_type": "state_report",
                "node": node,
                "color": color,
                "acknowledged": True
            }

    def _handle_command(self, classification_result: Any) -> Dict[str, Any]:
        """Handle COMMAND messages by applying forced assignments.

        Parameters
        ----------
        classification_result : ClassificationResult
            Classified message with extracted command

        Returns
        -------
        dict
            Acknowledgment with execution status
        """
        nodes = classification_result.extracted_nodes
        colors = classification_result.extracted_colors

        if not nodes or not colors:
            return {"command_type": "invalid", "success": False, "error": "No node or color specified"}

        node = nodes[0]
        color = self._normalize_color(colors[0])

        # Check if node is in fixed_local_nodes (immutable)
        if node in self.fixed_local_nodes:
            return {
                "command_type": "forced_assignment",
                "success": False,
                "error": f"Node {node} is fixed and cannot be changed"
            }

        # Apply forced assignment (will be respected by next compute_assignments call)
        self.forced_local_assignments[node] = color

        # Invalidate cache since forced assignments changed
        self._invalidate_cache()

        return {
            "command_type": "forced_assignment",
            "node": node,
            "color": color,
            "success": True,
            "note": "Will be applied in next step"
        }

    def _enumerate_boundary_options(self) -> Dict[str, Any]:
        """Enumerate valid boundary configurations (used by query and preference handlers).

        Returns
        -------
        dict
            Dictionary with options list and metadata
        """
        import itertools

        base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})
        boundary_nodes = sorted([n for n in base_beliefs.keys()])

        if not boundary_nodes:
            return {"options": [], "boundary_nodes": []}

        options = []
        for colors in itertools.product(self.domain, repeat=len(boundary_nodes)):
            config = {boundary_nodes[i]: colors[i] for i in range(len(boundary_nodes))}

            # Skip if violates human-stated constraints
            if not self._config_respects_constraints(config):
                continue

            # Compute counterfactual
            tmp = dict(base_beliefs)
            tmp.update(config)
            best_pen, best_asg = self._best_local_assignment_for(tmp)

            agent_score = self._score_for(best_asg, list(self.nodes))

            options.append({
                "boundary_config": config,
                "penalty": float(best_pen),
                "agent_score": int(agent_score),
                "feasible": best_pen < 1e-9
            })

        # Sort: feasible first, then by agent score
        options.sort(key=lambda o: (not o["feasible"], -o["agent_score"]))

        return {
            "options": options,
            "boundary_nodes": boundary_nodes,
            "total_options": len(options),
            "feasible_count": sum(1 for o in options if o["feasible"])
        }

    def _analyze_option_patterns(self, options: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze patterns across feasible options to identify common constraints.

        Parameters
        ----------
        options : list
            List of option dictionaries with boundary configs

        Returns
        -------
        dict
            Pattern analysis with common constraints
        """
        if not options:
            return {"type": "none", "description": "No options available"}

        # Filter to feasible options only
        feasible = [o for o in options if o.get("feasible", False)]

        if not feasible:
            return {"type": "none", "description": "No feasible options"}

        if len(feasible) == 1:
            return {"type": "unique", "description": "Only one feasible option"}

        # Find common node assignments across all feasible options
        common_assignments = {}
        boundary_nodes = feasible[0].get("boundary_config", {}).keys()

        for node in boundary_nodes:
            colors_for_node = [opt["boundary_config"][node] for opt in feasible]
            unique_colors = set(colors_for_node)

            if len(unique_colors) == 1:
                # This node has the same color in all feasible options
                common_assignments[node] = list(unique_colors)[0]

        if common_assignments:
            # Describe common constraints
            constraint_strs = [f"{node}={color}" for node, color in common_assignments.items()]
            return {
                "type": "common_constraints",
                "description": f"All solutions require: {', '.join(constraint_strs)}",
                "constraints": common_assignments
            }

        return {
            "type": "flexible",
            "description": f"{len(feasible)} options available with no fixed requirements"
        }

    def _config_respects_constraints(self, config: Dict[str, Any]) -> bool:
        """Check if a boundary configuration respects human-stated constraints.

        Parameters
        ----------
        config : dict
            Boundary configuration to check

        Returns
        -------
        bool
            True if configuration respects all constraints
        """
        for node, color in config.items():
            if node in self._human_stated_constraints:
                constraints = self._human_stated_constraints[node]

                # Check forbidden colors
                forbidden = constraints.get("forbidden", [])
                if color in forbidden:
                    return False

                # Check required color
                required = constraints.get("required")
                if required is not None and color != required:
                    return False

        return True

    def _score_for(self, assignments: Dict[str, Any], nodes: List[str]) -> int:
        """Compute score for given assignments (number of nodes colored).

        Parameters
        ----------
        assignments : dict
            Node assignments
        nodes : list
            List of nodes to score

        Returns
        -------
        int
            Score (number of assigned nodes)
        """
        return sum(1 for n in nodes if n in assignments and assignments[n] is not None)

    def _respond_to_human_conversationally(self, assignments_changed: bool = False, old_assignments: Optional[Dict[str, Any]] = None) -> None:
        """Generate conversational response with conflict-aware suggestions.

        This method is called when the human has sent a message that needs a response.
        It uses the LLM to generate a natural conversational reply that:
        - Directly addresses the human's message/question
        - Detects conflicts and suggests SPECIFIC color changes
        - Mentions specific internal node changes (e.g., "I changed a2 from red to green")
        - Maintains a collaborative tone
        """
        if not hasattr(self.comm_layer, "_call_openai"):
            # Fallback if no LLM available - just acknowledge
            self.send("Human", {"type": "free_text", "data": "I received your message."})
            return

        # FIX 1: DEFENSIVE verification that assignments_changed matches reality
        if old_assignments:
            actual_changes = {}
            for node in self.nodes:
                old_val = old_assignments.get(node)
                new_val = self.assignments.get(node)
                if old_val != new_val:
                    actual_changes[node] = (old_val, new_val)

            reality_changed = bool(actual_changes)
            if assignments_changed != reality_changed:
                self.log(f"BUG: claimed changed={assignments_changed}, reality={reality_changed}")
                self.log(f"  Actual changes: {actual_changes}")
                # Override with reality
                assignments_changed = reality_changed

        # Build context about current state
        base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})

        # Get boundary nodes belonging to human
        human_boundary: List[str] = []
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes and self.owners.get(nbr) == "Human":
                    if nbr not in human_boundary:
                        human_boundary.append(nbr)

        # What we know about human's boundary
        known_human = {n: base_beliefs.get(n) for n in human_boundary if base_beliefs.get(n) is not None}

        # Track specific changes to internal nodes
        changes_list = []
        if assignments_changed and old_assignments:
            for node in self.nodes:
                old_color = old_assignments.get(node)
                new_color = self.assignments.get(node)
                if old_color != new_color:
                    changes_list.append(f"{node}: {old_color} → {new_color}")

        changes_summary = ""
        if changes_list:
            changes_summary = "\n\nCHANGES YOU MADE THIS TURN:\n" + "\n".join([f"- {c}" for c in changes_list])

        # DETECT CONFLICTS - check for same-color adjacent nodes
        conflicts = []
        for my_node in self.nodes:
            my_color = self.assignments.get(my_node)
            for nbr in self.problem.get_neighbors(my_node):
                if nbr not in self.nodes:  # External neighbor
                    nbr_color = base_beliefs.get(nbr)
                    if nbr_color and my_color and str(nbr_color).lower() == str(my_color).lower():
                        conflicts.append((my_node, nbr, my_color))

        # Generate conflict-specific suggestions
        conflict_summary = ""
        if conflicts:
            conflict_summary = "\n\nCONFLICTS DETECTED:\n"
            for my_node, human_node, clashing_color in conflicts[:3]:  # Top 3
                conflict_summary += f"- {my_node} ({clashing_color}) clashes with {human_node} ({clashing_color})\n"

            # Suggest specific changes - but prioritize suggesting changes to OUR OWN internal nodes first
            conflict_summary += "\nSUGGESTED CHANGES:\n"
            # First check if we can change our internal nodes
            internal_change_possible = False
            for my_node, human_node, clashing_color in conflicts[:3]:
                alternatives = [c for c in self.domain if str(c).lower() != str(clashing_color).lower()]
                if alternatives:
                    # Suggest changing OUR internal node if possible
                    conflict_summary += f"- I could change my node {my_node} to {alternatives[0]} (currently {clashing_color})\n"
                    internal_change_possible = True

            # If no internal changes suggested, suggest human boundary changes
            if not internal_change_possible:
                for my_node, human_node, clashing_color in conflicts[:3]:
                    alternatives = [c for c in self.domain if str(c).lower() != str(clashing_color).lower()]
                    if alternatives:
                        conflict_summary += f"- Change {human_node} to {alternatives[0]} to resolve clash with {my_node}\n"

        # Current penalty
        combined = {**base_beliefs, **dict(self.assignments)}
        current_penalty = self.problem.evaluate_assignment(combined)

        # Build prompt
        state_summary = (
            f"Your current assignments: {dict(self.assignments)}\n"
            f"Human's boundary nodes: {human_boundary}\n"
            f"What you know about human's boundary: {known_human}\n"
            f"Current penalty: {current_penalty:.2f}\n"
            f"Your assignments changed this turn: {assignments_changed}\n"
            f"{changes_summary}\n"
            f"{conflict_summary}"
        )

        # Build prompt emphasizing whether assignments actually changed
        if assignments_changed and changes_list:
            change_status = f"YOUR ASSIGNMENTS **DID** CHANGE THIS TURN. Specifically: {', '.join(changes_list)}"
        else:
            change_status = "YOUR ASSIGNMENTS **DID NOT** CHANGE THIS TURN. Your nodes are the same as before."

        # Check if human is asking a question
        text_lower = self._last_human_text.lower()
        is_question = "?" in self._last_human_text or any(q in text_lower for q in [
            "what", "why", "how", "can you", "are you", "do you", "is", "will you", "could you"
        ])

        # DEFENSIVE: Verify assignments match what we think they are
        assignment_verification = "VERIFIED: Assignments in self.assignments dict match the values shown above."
        for node in self.nodes:
            claimed_color = self.assignments.get(node)
            self.log(f"Verification: {node} = {claimed_color}")

        # Phase 6: DECISION TREE - What should the agent do/suggest?
        # Follow user's logic: 1) Good as is? 2) Can I fix alone? 3) Suggest boundary changes
        decision_analysis = "\n**DECISION TREE:**\n"

        # Step 1: Are we good as is?
        if current_penalty < 1e-6:
            decision_analysis += "✓ STEP 1: We are GOOD AS IS. Penalty=0, no conflicts.\n"
            decision_analysis += "  → ACTION: Acknowledge success. No changes needed.\n"
        else:
            decision_analysis += f"✗ STEP 1: Not good (penalty={current_penalty:.2f}). Need to fix.\n"

            # Step 2: Can I fix it alone by changing my internal nodes?
            # Try to find if there's a valid assignment for my nodes with current boundary
            best_pen, best_assign = self._best_local_assignment_for(base_beliefs)

            if best_pen < 1e-6:
                # I CAN fix it alone!
                decision_analysis += f"✓ STEP 2: I CAN fix this alone! Found internal assignment with penalty=0.\n"
                decision_analysis += f"  → Best internal assignment: {best_assign}\n"

                # Check if we already applied this
                if dict(self.assignments) == best_assign:
                    decision_analysis += "  → Already using this assignment. Should have penalty=0 but doesn't - BUG?\n"
                else:
                    decision_analysis += "  → ACTION: I should change my internal nodes to this assignment.\n"
                    decision_analysis += "  → DO NOT ask human to change boundary - I can solve this myself!\n"
            else:
                # I CANNOT fix it alone
                decision_analysis += f"✗ STEP 2: I CANNOT fix this alone (best I can do: penalty={best_pen:.2f}).\n"
                decision_analysis += "  → The current boundary doesn't work for me.\n"

                # Step 3: What boundary changes would work?
                # Compute valid boundary configs (respecting constraints)
                constrained_configs = self._compute_valid_boundary_configs_with_constraints(max_configs=10)

                if constrained_configs:
                    decision_analysis += f"✓ STEP 3: Found {len(constrained_configs)} boundary config(s) that WOULD work:\n"
                    for i, config in enumerate(constrained_configs[:5]):
                        config_str = ", ".join([f"{k}={v}" for k, v in config.items()])
                        decision_analysis += f"    {i+1}. {config_str}\n"
                    decision_analysis += "  → ACTION: Suggest these boundary changes to the human.\n"
                else:
                    decision_analysis += "✗ STEP 3: Found NO valid boundary configs (with constraints).\n"
                    decision_analysis += "  → ACTION: Tell human the problem may be unsolvable with their constraints.\n"

        decision_analysis += "\n"

        # Phase 7: Retrieve cached counterfactuals OR compute boundary options on-demand
        counterfactuals_section = ""

        # Check if human is asking for boundary configuration options
        text_lower = self._last_human_text.lower()
        asking_for_options = any(phrase in text_lower for phrase in [
            "option", "settings", "configuration", "what could i",
            "what can i", "what should i", "what would work",
            "other configuration", "alternatives", "what else",
            "what settings", "which settings"
        ])

        # Check if human is asking "what could I set X to?"
        asking_about_node_value = any(phrase in text_lower for phrase in [
            "what could i set", "what should i set", "what can i set",
            "what could i change", "what should i change", "what can i change",
            "what about", "could i set", "should i set", "can i set",
            "tell me what i can set"
        ])

        try:
            # If asking about specific node value, compute valid values for that node
            if asking_about_node_value and hasattr(self, '_last_message_result'):
                result = self._last_message_result
                if isinstance(result, dict) and result.get("query_type") == "node_value_search":
                    query_node = result.get("query_node")
                    valid_colors = result.get("valid_colors", [])
                    fixed_boundary = result.get("fixed_boundary", {})

                    if query_node and valid_colors:
                        counterfactuals_section = f"\n**VALID VALUES FOR {query_node.upper()}:**\n"
                        counterfactuals_section += f"Given that {', '.join([f'{k}={v}' for k, v in fixed_boundary.items()])}, "
                        counterfactuals_section += f"you could set {query_node} to:\n"
                        for i, color in enumerate(valid_colors):
                            counterfactuals_section += f"{i+1}. {query_node}={color} ✓ (this works for me!)\n"
                        counterfactuals_section += "\nWhen responding:\n"
                        counterfactuals_section += f"- Tell the human which values of {query_node} work for you\n"
                        counterfactuals_section += f"- Be specific: list the valid colors ({', '.join(valid_colors)})\n"
                        counterfactuals_section += "- Do NOT suggest changing nodes the human said they can't change\n"
                    elif query_node and not valid_colors:
                        counterfactuals_section = f"\n**NO VALID VALUES FOR {query_node.upper()}:**\n"
                        counterfactuals_section += f"Given {', '.join([f'{k}={v}' for k, v in fixed_boundary.items()])}, "
                        counterfactuals_section += f"there are NO valid values for {query_node} that would work for me.\n"
                        counterfactuals_section += "The human needs to change other boundary nodes to make progress.\n"

            # If asking for options, compute them now (don't rely on cache)
            elif asking_for_options:
                self.log(f"Human asking for options - computing boundary configurations")
                valid_configs = self._compute_valid_boundary_configs_with_constraints(max_configs=10)

                if valid_configs:
                    counterfactuals_section = "\n**BOUNDARY OPTIONS FOR HUMAN (what YOU can choose):**\n"
                    for i, config in enumerate(valid_configs[:5]):
                        config_str = ", ".join([f"{k}={v}" for k, v in config.items()])
                        counterfactuals_section += f"{i+1}. You could set: {config_str}\n"

                    counterfactuals_section += "\nWhen responding:\n"
                    counterfactuals_section += "- List these SPECIFIC boundary configurations for the human\n"
                    counterfactuals_section += "- These are the settings the HUMAN can choose (boundary nodes they control)\n"
                    counterfactuals_section += "- Don't list your own internal node assignments (b1, b2, etc.) - the human can't control those!\n"
                    counterfactuals_section += "- Be specific and enumerate the options clearly\n"
                else:
                    counterfactuals_section = "\n**NO VALID BOUNDARY OPTIONS FOUND**\n"
                    counterfactuals_section += "I cannot find any boundary configuration that would allow me to achieve zero conflicts.\n"
                    counterfactuals_section += "This may be due to constraints that make the problem unsolvable.\n"

            # CRITICAL: If there's a conflict (penalty > 0), ALWAYS compute what would work
            # Don't just rely on cache - the agent needs to know what's actually possible
            elif current_penalty > 1e-6 and not counterfactuals_section:
                self.log(f"Conflict detected (penalty={current_penalty:.2f}) - computing valid boundary configs")

                # Compute valid configs WITH constraints applied
                constrained_configs = self._compute_valid_boundary_configs_with_constraints(max_configs=10)

                # Also compute valid configs WITHOUT constraints to see what WOULD work
                # Temporarily clear constraints for this calculation
                saved_constraints = dict(self._human_stated_constraints)
                self._human_stated_constraints.clear()
                unconstrained_configs = self._compute_valid_boundary_configs_with_constraints(max_configs=10)
                self._human_stated_constraints = saved_constraints

                counterfactuals_section = "\n**BOUNDARY CONFIGURATION ANALYSIS:**\n"

                # Check if human's CURRENT boundary is one of the valid ones
                current_boundary = dict(getattr(self, "neighbour_assignments", {}) or {})
                current_is_valid = False
                if constrained_configs:
                    for config in constrained_configs:
                        if all(current_boundary.get(k) == v for k, v in config.items()):
                            current_is_valid = True
                            break

                if current_is_valid:
                    current_str = ", ".join([f"{k}={v}" for k, v in current_boundary.items()])
                    counterfactuals_section += f"✓✓ CURRENT boundary ({current_str}) IS VALID! This should work.\n"
                    counterfactuals_section += "  (If penalty > 0, there may be an internal issue - the boundary itself is correct)\n"

                if constrained_configs:
                    counterfactuals_section += f"✓ WITH your stated constraints, {len(constrained_configs)} config(s) would work:\n"
                    for i, config in enumerate(constrained_configs[:5]):
                        config_str = ", ".join([f"{k}={v}" for k, v in config.items()])
                        # Mark if this is the current config
                        is_current = all(current_boundary.get(k) == v for k, v in config.items())
                        marker = " ← CURRENT" if is_current else ""
                        counterfactuals_section += f"  {i+1}. {config_str}{marker}\n"
                else:
                    counterfactuals_section += "✗ WITH your stated constraints: NO valid configs found.\n"

                    if unconstrained_configs and len(unconstrained_configs) > len(constrained_configs):
                        counterfactuals_section += f"\n✓ WITHOUT those constraints, {len(unconstrained_configs)} config(s) WOULD work:\n"
                        for i, config in enumerate(unconstrained_configs[:5]):
                            config_str = ", ".join([f"{k}={v}" for k, v in config.items()])
                            # Highlight which nodes differ from constraints
                            constrained_nodes = list(self._human_stated_constraints.keys())
                            highlight = ""
                            for node, color in config.items():
                                if node.lower() in constrained_nodes:
                                    highlight = f" (requires {node} to change)"
                            counterfactuals_section += f"  {i+1}. {config_str}{highlight}\n"
                        counterfactuals_section += "\nThese show what WOULD work if constraints were relaxed.\n"

                counterfactuals_section += "\nWhen responding:\n"
                counterfactuals_section += "- Tell the human WHICH of their boundary settings would work (if any)\n"
                counterfactuals_section += "- If their current config is close to a working one, point that out\n"
                counterfactuals_section += "- Don't ask for changes the human said are impossible\n"
                counterfactuals_section += "- Be specific about what they need to change\n"

            # Otherwise, try to use cached counterfactuals if available
            elif not counterfactuals_section:
                cached_cf = self._get_cached_counterfactuals()
                if cached_cf:
                    # Format counterfactuals for LLM
                    if isinstance(cached_cf, dict):
                        options = cached_cf.get("options", [])
                        if options:
                            counterfactuals_section = "\n**AVAILABLE OPTIONS (counterfactuals I computed):**\n"
                            # Show top 5 options
                            for i, opt in enumerate(options[:5]):
                                if isinstance(opt, dict):
                                    config = opt.get("boundary_config") or opt.get("human", {})
                                    penalty = opt.get("penalty", 0)
                                    score = opt.get("agent_score", 0)
                                    feasible = opt.get("feasible", penalty < 1e-9)
                                    status = "✓ FEASIBLE" if feasible else "✗ HAS CONFLICTS"

                                    config_str = ", ".join([f"{k}={v}" for k, v in config.items()])
                                    counterfactuals_section += f"{i+1}. If you set {config_str}: {status}, my score={score}, penalty={penalty:.1f}\n"

                            counterfactuals_section += "\nWhen responding:\n"
                            counterfactuals_section += "- If human asked a query, reference these options to answer\n"
                            counterfactuals_section += "- If explaining why something won't work, suggest feasible alternatives from this list\n"
                            counterfactuals_section += "- Be concise: don't list all options unless specifically asked\n"
        except Exception as e:
            self.log(f"Failed to retrieve cached counterfactuals: {e}")

        # Handle empty messages (config updates) specially
        human_message_text = self._last_human_text if self._last_human_text and self._last_human_text.strip() else ""
        if human_message_text:
            human_context = f'The human just said: "{human_message_text}"'
        else:
            human_context = "The human just sent their current boundary configuration (no message text)"

        # Build constraints section to show at TOP of prompt
        constraints_section = ""
        if self._human_stated_constraints:
            constraints_section = "**🚫 IMMUTABLE CONSTRAINTS (you CANNOT suggest changing these):**\n"
            for node, constraint_dict in self._human_stated_constraints.items():
                required = constraint_dict.get("required")
                forbidden = constraint_dict.get("forbidden", [])
                if required:
                    constraints_section += f"- {node} MUST be {required} (human stated this is fixed)\n"
                if forbidden:
                    forbidden_str = ", ".join(forbidden)
                    constraints_section += f"- {node} CANNOT be {forbidden_str} (human ruled these out)\n"
            constraints_section += "\n**CRITICAL:** Never suggest changing these constrained nodes in your response!\n\n"

        prompt = (
            f"You are agent '{self.name}' collaborating with a human on a graph coloring task.\n\n"
            f"{constraints_section}"
            f"{human_context}\n\n"
            f"**CRITICAL FACT:** {change_status}\n\n"
            f"**VERIFICATION:** Before you respond, understand that:\n"
            f"- Current penalty = {current_penalty:.2f} (0 = no conflicts, >0 = conflicts exist)\n"
            f"- Number of detected conflicts = {len(conflicts)}\n"
            f"- If penalty > 0 OR conflicts exist, you CANNOT claim to have a good/valid solution\n"
            f"- If penalty > 0, you MUST acknowledge conflicts exist in your response\n"
            f"- {assignment_verification}\n\n"
            f"**CRITICAL - How to Propose Changes:**\n"
            f"- You can ONLY change your own nodes (nodes {', '.join(sorted(self.nodes))})\n"
            f"- You CANNOT directly change the human's nodes\n"
            f"- Frame proposals as CONDITIONAL agreements:\n"
            f"  ✓ GOOD: 'If you set h1=blue and h4=red, I can set my nodes to a1=green, a2=blue, a3=blue, a4=red, a5=green. This gives penalty=0.'\n"
            f"  ✗ BAD: 'Change h1 to blue' (sounds like a command, ignores human's autonomy)\n"
            f"- ALWAYS state your complete resultant coloring when proposing boundary changes\n"
            f"- ALWAYS verify penalty=0 in your proposal before claiming a solution works\n"
            f"- If human states a node is FIXED (e.g., 'h1 has to be red'), NEVER suggest changing it\n\n"
            f"Your current state:\n{state_summary}\n"
            f"{decision_analysis}"
            f"{counterfactuals_section}"
        )

        if not human_message_text:
            # Empty message = config update
            prompt += (
                "The human sent their current boundary configuration. Your response MUST:\n"
                "1. Acknowledge their config update\n"
                "2. Report your current node assignments\n"
                "3. State whether the current config works (penalty=0) or not\n"
                "4. If conflicts exist (penalty>0), suggest what boundary changes would help\n"
                "   ⚠️ NEVER suggest changing constrained nodes listed above!\n"
                "   ⚠️ Only suggest changing nodes that are NOT in the constraints list\n\n"
                "Examples:\n"
                "- If penalty=0: 'Received your config. My nodes: a1=green, a2=blue, a3=blue. No conflicts!'\n"
                "- If penalty>0 with unconstrained nodes: 'Received your config. Current penalty is 20.00. There's a clash between my a2 (red) and your h1 (red). Try changing h1 to blue.'\n"
                "- If penalty>0 with ALL nodes constrained: 'Received your config. Current penalty is 20.00. With your constraints (h1=red fixed), I cannot find a valid solution. This may not be solvable with those constraints.'\n\n"
                "Return ONLY the conversational response text (2-3 sentences max)."
            )
        elif is_question:
            prompt += (
                "The human asked you a QUESTION. Your response MUST:\n"
                "1. ANSWER THE QUESTION DIRECTLY first - don't dodge or change the subject\n"
                "2. If they ask about your nodes/colors, tell them your exact current assignments\n"
                "3. If they ask 'can you do X', answer yes/no FIRST, then explain\n"
                "4. If they ask 'why', explain the reasoning clearly\n"
                "5. Be specific and truthful - use actual node names and colors from your state\n\n"
                "Examples:\n"
                "Q: 'What color is b2?'\nA: 'b2 is currently red.'\n\n"
                "Q: 'Can you change b2 to green?'\nA: 'Yes, I changed b2 to green.' OR 'No, I cannot change b2 without creating internal conflicts.'\n\n"
                "Q: 'Why is there a clash?'\nA: 'There's a clash because my node b2 (red) neighbors your node h2 (red). Same colors on adjacent nodes create conflicts.'\n\n"
                "Return ONLY the conversational response text."
            )
        else:
            prompt += (
                "Generate a conversational response (2-3 sentences max) following the DECISION TREE above:\n\n"
                "**IF STEP 1 says we're GOOD (penalty=0):**\n"
                "- Acknowledge success: 'My nodes are optimized. No conflicts!'\n"
                "- Report your assignments\n"
                "- DO NOT suggest any changes\n\n"
                "**IF STEP 2 says you CAN fix it alone:**\n"
                "- Say 'I can resolve this by changing my internal nodes' OR 'I changed X to Y'\n"
                "- DO NOT ask human to change boundary - YOU can solve it yourself!\n"
                "- Only mention internal node changes, not boundary\n\n"
                "**IF STEP 3 applies (you CANNOT fix alone):**\n"
                "- Frame as conditional proposal: 'If you set [boundary config], I can set my nodes to [complete coloring]. This would give penalty=0.'\n"
                "- Be SPECIFIC: List your exact resultant coloring for ALL your nodes, not just boundary suggestions\n"
                "- VERIFY: Confirm the proposed solution actually achieves penalty=0 (check STEP 3 data)\n"
                "- ⚠️ CRITICAL: Only suggest configs that appear in STEP 3! Don't make up others.\n"
                "- ⚠️ Never suggest changing constrained nodes (see constraints at top)\n"
                "- Example: 'If you set h1=blue, I can set a1=green, a2=blue, a3=red, a4=green, a5=blue. This gives penalty=0.'\n\n"
                "**General rules:**\n"
                "- NEVER say 'I changed' if assignments didn't actually change (see CRITICAL FACT)\n"
                "- If penalty > 0, acknowledge conflicts exist\n"
                "- Be specific and truthful\n\n"
                "Examples:\n"
                "- STEP 1 good: 'Everything looks good! My nodes: a1=green, a2=blue, a3=red. No conflicts.'\n"
                "- STEP 2 can fix: 'I changed a2 to blue to resolve the clash. My nodes: a1=green, a2=blue, a3=red. Should work now.'\n"
                "- STEP 3 need boundary: 'If you set h1=blue and h4=red, I can set my nodes to a1=green, a2=blue, a3=red, a4=green, a5=blue. This would give penalty=0.'\n"
                "- STEP 3 constrained: 'With h1=red fixed, I found one solution: if you set h4=blue, I can color my nodes a1=green, a2=blue, a3=red, a4=red, a5=green. This gives penalty=0.'\n\n"
                "Return ONLY the conversational response text."
            )

        try:
            response_text = self.comm_layer._call_openai(prompt, max_tokens=200)

            if response_text and response_text.strip():
                # CRITICAL: Post-process to remove lies about changes
                final_response = response_text.strip()

                # CRITICAL: If penalty > 0 but LLM claims no conflicts, re-prompt with explicit conflict details
                self.log(f"Checking response accuracy: penalty={current_penalty:.2f}, response='{final_response[:80]}...'")
                if current_penalty > 1e-9:
                    self.log(f"Penalty > 0, checking if response acknowledges conflicts")
                    no_conflict_lies = ["no conflicts", "no clash", "zero conflicts", "conflict-free",
                                       "good coloring", "valid solution", "valid coloring", "all is well",
                                       "everything works", "no issues", "problem-free", "successful"]
                    final_lower = final_response.lower()
                    for lie in no_conflict_lies:
                        if lie in final_lower:
                            # LLM is not acknowledging conflicts - re-prompt with explicit details
                            self.log(f"!!! LLM response inaccurate: claimed '{lie}' but penalty={current_penalty:.2f} > 0. Re-prompting with explicit conflict details.")

                            # Build detailed conflict information
                            conflict_details = f"\n**CRITICAL - YOU HAVE CONFLICTS:**\n"
                            conflict_details += f"- Current penalty: {current_penalty:.2f} (GREATER THAN ZERO)\n"
                            if conflicts:
                                conflict_details += f"- Detected {len(conflicts)} boundary conflict(s):\n"
                                for i, (my_node, their_node, color) in enumerate(conflicts[:3]):
                                    conflict_details += f"  {i+1}. My node {my_node}={color} CLASHES with human's node {their_node}={color}\n"
                            conflict_details += "- You MUST acknowledge these conflicts in your response\n"
                            conflict_details += "- NEVER claim you have a 'valid solution' or 'no conflicts' when penalty > 0\n\n"

                            # Re-prompt with explicit conflict awareness
                            corrective_prompt = (
                                f"You are agent '{self.name}'. The human asked: \"{self._last_human_text}\"\n\n"
                                f"{conflict_details}"
                                f"Your state:\n{state_summary}\n"
                                f"{counterfactuals_section}\n"
                                f"Generate an HONEST response that:\n"
                                f"1. ACKNOWLEDGES the conflicts exist (penalty={current_penalty:.2f})\n"
                                f"2. Answers the human's question directly\n"
                                f"3. If appropriate, suggests what boundary changes would resolve conflicts\n"
                                f"4. NEVER claims to have a valid/good solution when conflicts exist\n\n"
                                f"Return ONLY the conversational response text."
                            )

                            final_response = self.comm_layer._call_openai(corrective_prompt, max_tokens=200).strip()
                            self.log(f"Re-prompted LLM with conflict details. New response: '{final_response}'")
                            break

                # Verify response uses conditional proposal structure when suggesting boundary changes
                if current_penalty > 1e-9:  # Has conflicts, might suggest boundary changes
                    response_lower = final_response.lower()
                    has_conditional = ("if you" in response_lower and "i can" in response_lower) or ("if you set" in response_lower)
                    has_resultant_coloring = any(f"{node}=" in response_lower for node in self.nodes)

                    if has_conditional and has_resultant_coloring:
                        self.log("✓ Response uses conditional proposal structure with resultant coloring")
                    elif "try" in response_lower or "change" in response_lower or "set" in response_lower:
                        # Suggests boundary changes but doesn't use conditional structure
                        self.log("⚠ Response suggests boundary changes but may not use ideal conditional proposal structure")

                else:
                    self.log(f"Penalty <= 0, no lie detection needed")

                # If assignments didn't change, strip out any claims of changing
                if not assignments_changed:
                    lies = ["i changed", "i've changed", "i have changed", "i resolved", "i've resolved",
                            "i switched", "i've switched", "i corrected", "i've corrected"]
                    final_lower = final_response.lower()
                    for lie in lies:
                        if lie in final_lower:
                            # LLM is lying - replace with honest fallback
                            if conflicts:
                                example = conflicts[0]
                                alternatives = [c for c in self.domain if str(c).lower() != str(example[2]).lower()]
                                final_response = f"I CANNOT resolve the clash at {example[0]} (clashing with {example[1]}). You need to change {example[1]} to {alternatives[0] if alternatives else 'a different color'}."
                            else:
                                final_response = f"My nodes did not change. Current penalty: {current_penalty:.2f}"
                            self.log(f"WARNING: LLM hallucinated changes when assignments_changed=False. Replaced with honest response.")
                            break

                # CRITICAL: Check if LLM suggested changing a constrained node (ignoring constraints!)
                violated_constraints = []
                for node, constraint_dict in self._human_stated_constraints.items():
                    required = constraint_dict.get("required")
                    if required and f"change {node}" in final_response.lower():
                        violated_constraints.append(f"{node}={required}")

                if violated_constraints:
                    self.log(f"!!! LLM suggested changing constrained nodes: {violated_constraints}. Overriding response.")
                    constraint_str = ", ".join(violated_constraints)
                    final_response = f"With your constraints ({constraint_str} fixed), I cannot find a valid solution. The problem may not be solvable with these constraints."
                    if current_penalty > 1e-6:
                        # Try to suggest changing unconstrained nodes if any exist
                        unconstrained_boundary = [n for n in getattr(self, "neighbour_assignments", {}).keys()
                                                 if n.lower() not in self._human_stated_constraints]
                        if unconstrained_boundary:
                            final_response += f" Try adjusting {unconstrained_boundary[0]} instead."

                self.send("Human", {"type": "free_text", "data": final_response})
                self.log(f"Sent conversational response to Human: {final_response[:80]}...")
            else:
                # Fallback if LLM returns nothing
                if changes_list:
                    fallback = f"I changed: {', '.join(changes_list)}."
                elif conflicts and not assignments_changed:
                    # CRITICAL: If we have conflicts but couldn't change, be honest!
                    example = conflicts[0]
                    alternatives = [c for c in self.domain if str(c).lower() != str(example[2]).lower()]
                    fallback = f"I CANNOT resolve the clash at {example[0]} (clashing with {example[1]}). All my alternatives are worse. You need to change {example[1]} to {alternatives[0] if alternatives else 'a different color'}."
                elif conflicts:
                    # We tried to change but still have conflicts
                    example = conflicts[0]
                    fallback = f"I still have a clash at {example[0]} with {example[1]}. I need you to change the boundary to resolve this."
                else:
                    fallback = f"My nodes are optimized. Current penalty: {current_penalty:.2f}"
                self.send("Human", {"type": "free_text", "data": fallback})

        except Exception as e:
            self.log(f"Error generating conversational response: {e}")
            # Fallback acknowledgment
            self.send("Human", {"type": "free_text", "data": f"I received your message: {self._last_human_text}"})

    def step(self) -> None:
        """Perform one iteration of the cluster agent's process.

        The cluster computes a new assignment for its local nodes using
        the configured algorithm and then sends a message to each
        neighbouring cluster summarising its impact on the neighbours.
        """
        # --- bookkeeping / debug ---
        try:
            self.debug_step_count = getattr(self, "debug_step_count", 0) + 1  # type: ignore[attr-defined]
        except Exception:
            pass

        iteration = getattr(self.problem, "iteration", None)
        if iteration is not None:
            try:
                self.log(f"Step called (iteration={iteration})")
            except Exception:
                pass

        # DON'T reset human message flag here - it needs to stay True until AFTER we send messages
        # Otherwise duplicate detection will kick in before we respond
        # Flag will be reset at the END of step() after messages are sent

        # compute new assignments FIRST
        # Store old assignments for detailed change tracking
        old_assignments = dict(self.assignments)

        # DEBUG: Log what we know about boundaries before computing
        base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})
        if base_beliefs:
            self.log(f"Known boundary colors before compute_assignments: {base_beliefs}")
        else:
            self.log(f"WARNING: No known boundary colors (neighbour_assignments is empty)")

        new_assignment = self.compute_assignments()
        assignments_changed = new_assignment != self.assignments
        if assignments_changed:
            self.log(f"Updated assignments from {self.assignments} to {new_assignment}")
        else:
            self.log(f"Assignments unchanged: {self.assignments}")
            # DEBUG: If we have boundary conflicts but didn't change, log why
            current_combined = {**base_beliefs, **dict(self.assignments)}
            current_penalty = self.problem.evaluate_assignment(current_combined)
            if current_penalty > 1e-9:
                self.log(f"WARNING: Assignments didn't change despite penalty={current_penalty:.3f}")
                self.log(f"Current boundary beliefs: {base_beliefs}")
                self.log(f"Current assignments: {self.assignments}")

        self.assignments = new_assignment

        # Check if forced assignments were just applied (before clearing them)
        forced_were_used = bool(hasattr(self, 'forced_local_assignments') and self.forced_local_assignments)

        # Clear forced assignments after they've been applied (one-time use)
        if forced_were_used:
            self.log(f"Clearing forced_local_assignments: {self.forced_local_assignments}")
            self.forced_local_assignments = {}

        # CRITICAL FIX: If greedy search got stuck, snap to the best local assignment (cluster sizes are small).
        # BUT: Only snap when appropriate to avoid overriding greedy's choices:
        # 1. Do NOT snap if forced assignments were just used - we must respect human intent
        # 2. Do NOT snap if greedy just changed assignments - trust its new solution
        # 3. Only snap if greedy got stuck (no change) AND there's a significantly better solution
        should_snap = False
        snap_reason = ""

        if forced_were_used:
            self.log(f"Skipping snap-to-best: forced assignments were just applied (respecting human intent).")
        elif assignments_changed:
            self.log(f"Skipping snap-to-best: greedy just found a new solution (trusting its choice).")
        else:
            # Greedy got stuck - check if snap would help significantly
            try:
                base = dict(getattr(self, "neighbour_assignments", {}) or {})
                current_pen = self.problem.evaluate_assignment({**base, **dict(self.assignments)})
                best_pen, best_assign = self._best_local_assignment_for(base)
                # Only snap if there's a SIGNIFICANT improvement (not just any tiny improvement)
                # This prevents snap from constantly overriding reasonable solutions
                improvement_threshold = 5.0  # Only snap if we can improve penalty by at least 5
                if current_pen > best_pen + improvement_threshold:
                    should_snap = True
                    snap_reason = f"greedy stuck and significant improvement available (pen {current_pen:.3f} -> {best_pen:.3f})"
                else:
                    self.log(f"Skipping snap-to-best: improvement too small (pen {current_pen:.3f} -> {best_pen:.3f}, threshold={improvement_threshold})")
            except Exception as e:
                self.log(f"Error checking snap condition: {e}")

        if should_snap:
            try:
                base = dict(getattr(self, "neighbour_assignments", {}) or {})
                current_pen = self.problem.evaluate_assignment({**base, **dict(self.assignments)})
                best_pen, best_assign = self._best_local_assignment_for(base)
                self.assignments = dict(best_assign)
                assignments_changed = True  # Mark that we changed
                self.log(f"Snapped to best local assignment: {snap_reason}")
            except Exception as e:
                self.log(f"Error during snap: {e}")

        # FIX 1: Recompute change detection AFTER snap-to-best completes
        # This ensures we report the ACTUAL final changes to the human
        final_assignments = dict(self.assignments)
        actual_changes = {}
        for node in self.nodes:
            old_val = old_assignments.get(node)
            new_val = final_assignments.get(node)
            if old_val != new_val:
                actual_changes[node] = (old_val, new_val)

        assignments_actually_changed = bool(actual_changes)

        if assignments_actually_changed:
            self.log(f"FINAL changes after all processing: {actual_changes}")
        else:
            self.log(f"FINAL: No changes after all processing")

        # update satisfaction flag (soft convergence)
        # If human is asking us to make changes, reconsider satisfaction even if we were satisfied before
        if self._last_human_text and self._last_human_text.strip():
            # Check if human is asking for changes (keywords like "change", "can you", "your end", etc.)
            text_lower = self._last_human_text.lower()
            asking_for_changes = any(phrase in text_lower for phrase in [
                "change", "can you", "your end", "your side", "adjust", "modify",
                "different", "try", "switch", "untick", "reconsider"
            ])
            if asking_for_changes and self.satisfied:
                self.log(f"Human requested changes - reconsidering satisfaction")
                # Force recalculation by not using cached value

        # FIX 3: Detect changes to neighbor boundary assignments
        # If boundaries change, reset satisfaction (agent needs to reassess)
        current_neighs = dict(getattr(self, "neighbour_assignments", {}) or {})
        prev_neighs = dict(getattr(self, "_previous_neighbour_assignments", {}) or {})

        neighbor_changed = False
        if current_neighs != prev_neighs:
            neighbor_changed = True
            changes = {}
            for node in set(current_neighs.keys()) | set(prev_neighs.keys()):
                old_val = prev_neighs.get(node)
                new_val = current_neighs.get(node)
                if old_val != new_val:
                    changes[node] = (old_val, new_val)

            self.log(f"NEIGHBOR BOUNDARY CHANGED: {changes}")

            # If we were satisfied, reset because boundary changed
            if self.satisfied:
                self.log(f"Resetting satisfied=False due to neighbor boundary changes")
                self.satisfied = False

        # Update previous state for next comparison
        self._previous_neighbour_assignments = dict(current_neighs)

        try:
            # Don't recompute if neighbor just changed (already reset to False above)
            # Let next iteration handle recomputation with stable boundary
            if neighbor_changed:
                # Neighbor changed, satisfaction already reset to False on line 1731
                # Don't recompute yet - let next iteration handle it
                pass
            else:
                # Neighbor unchanged, safe to recompute satisfaction
                self.satisfied = bool(self._compute_satisfied())

            self.log(f"Satisfied: {self.satisfied}")

            # DEFENSIVE: Double-check satisfaction claim matches reality
            if self.satisfied:
                base = dict(getattr(self, "neighbour_assignments", {}) or {})
                verify_pen = self.problem.evaluate_assignment({**base, **dict(self.assignments)})
                if verify_pen > 1e-9:
                    self.log(f"CRITICAL BUG: Agent claims satisfied=True but penalty={verify_pen:.6f} > 0!")
                    self.log(f"  Assignments: {dict(self.assignments)}")
                    self.log(f"  Neighbor beliefs: {base}")
                    # Force unsatisfied to prevent false positive
                    self.satisfied = False
        except Exception:
            self.satisfied = False

        # --- Handle conversational human messages AFTER computing assignments ---
        # This way we know if our assignments actually changed before responding.
        # CRITICAL: Also respond to empty messages (config updates) - don't check if text is non-empty
        if hasattr(self, '_last_human_text') and self._last_human_text is not None:
            try:
                # FIX 1: Use assignments_actually_changed which reflects FINAL state after snap
                self._respond_to_human_conversationally(assignments_actually_changed, old_assignments)
                # Clear after responding so we don't keep replying to the same message
                self._last_human_text = ""
            except Exception as e:
                self.log(f"Failed to generate conversational response: {e}")

        # debug snapshot of the decision
        try:
            self.debug_last_decision = {
                "iteration": iteration,
                "step_count": getattr(self, "debug_step_count", None),
                "algorithm": self.algorithm,
                "message_type": self.message_type,
                "assignments": dict(self.assignments),
                "known_neighbour_assignments": dict(self.neighbour_assignments),
                "local_scores": getattr(self, "debug_last_local_scores", None),
            }
        except Exception:
            pass

        # Append to a reasoning history for the experimenter debug view.
        # This keeps a compact per-step trace of (what was known) -> (what was computed) -> (what was chosen).
        try:
            hist = getattr(self, "debug_reasoning_history", None)
            if hist is None:
                self.debug_reasoning_history = []  # type: ignore[attr-defined]
            self.debug_reasoning_history.append({  # type: ignore[attr-defined]
                "iteration": iteration,
                "known_neighbour_assignments": dict(self.neighbour_assignments),
                "local_scores": getattr(self, "debug_last_local_scores", None),
                "chosen_assignments": dict(self.assignments),
            })
        except Exception:
            pass

        # determine recipient clusters (owners of neighbouring nodes)
        recipients: Set[str] = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    owner = self.owners.get(nbr)
                    if owner and owner != self.name:
                        recipients.add(owner)

        # build message content depending on message_type
        if self.message_type == "cost_list":
            # Utility-oriented (LLM-U) messages.
            #
            # We treat this as a *coordination* channel, not a solver.
            # The agent enumerates a small set of plausible human boundary assignments
            # (counterfactuals) and reports the best-response outcomes:
            #   - feasibility (penalty)
            #   - agent points
            #   - human points on boundary nodes involved in the counterfactual
            #   - combined points (agent + human-boundary)
            #
            # The communication layer (LLM) then rewrites this into concise natural
            # dialogue for the human.
            import itertools

            colour_points = {"blue": 1, "green": 2, "red": 3}

            def score_for(mapping: Dict[Any, Any], nodes: List[Any]) -> int:
                s = 0
                for n in nodes:
                    c = str(mapping.get(n, "")).lower()
                    s += int(colour_points.get(c, 0))
                return s

            base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})

            # Determine external neighbour nodes adjacent to our cluster.
            ext_neighs_all: Set[str] = set()
            for node in self.nodes:
                for nbr in self.problem.get_neighbors(node):
                    if nbr not in self.nodes:
                        ext_neighs_all.add(str(nbr))

            # We'll build per-recipient content later (because boundary nodes differ per recipient).
            content = {"type": "cost_list", "data": {}}
            content["_ext_neighs_all"] = sorted(ext_neighs_all)
            content["_base_beliefs"] = dict(base_beliefs)
            content["_note"] = "options"
        elif self.message_type == "constraints":
            # Constraint-oriented messages with STATUS-FIRST approach:
            # 1. FIRST: Check if human's CURRENT boundary settings work (penalty=0?)
            # 2. IF YES: Report success + show our coloring
            # 3. IF NO: Report failure + suggest working alternatives

            eps = 1e-6
            base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})

            # Get boundary nodes
            ext_neighs: Set[str] = set()
            for node in self.nodes:
                for nbr in self.problem.get_neighbors(node):
                    if nbr not in self.nodes:
                        ext_neighs.add(str(nbr))

            boundary_nodes_sorted = sorted(ext_neighs)

            # STEP 1: Check current state with human's actual boundary colors
            current_penalty = self.problem.evaluate_assignment({**base_beliefs, **dict(self.assignments)})
            current_works = current_penalty <= eps

            # Build current boundary config from what we know
            current_boundary = {n: base_beliefs.get(n) for n in boundary_nodes_sorted if base_beliefs.get(n) is not None}
            current_is_complete = len(current_boundary) == len(boundary_nodes_sorted)

            # STEP 2: If current works, report SUCCESS with our assignments
            if current_works and current_is_complete:
                content = {
                    "type": "constraints",
                    "data": {
                        "status": "SUCCESS",
                        "current_boundary": current_boundary,
                        "my_coloring": dict(self.assignments),
                        "message": f"✓ Your boundary settings work! I successfully colored my nodes with zero conflicts."
                    }
                }
                self.log(f"LLM_C: Current boundary {current_boundary} works! Penalty={current_penalty:.6f}")

            # STEP 3: If current doesn't work OR incomplete, compute alternatives
            else:
                self.log(f"LLM_C: Current boundary incomplete or doesn't work. Penalty={current_penalty:.6f}. Computing alternatives...")

                # CRITICAL FIX: Enumerate ALL boundary combinations (not just per-node minimal)
                # The old per-node filtering was too aggressive and missed valid combinations
                # that only work when multiple nodes change together.

                # Build list of allowed colors per node (respecting human constraints)
                import itertools
                data: Dict[str, List[Any]] = {}  # Keep for backwards compatibility
                allowed_colors_per_node = []
                for nbr in boundary_nodes_sorted:
                    allowed = []
                    for colour in self.domain:
                        # Check human-stated constraints
                        nbr_lower = str(nbr).lower()
                        colour_lower = str(colour).lower()

                        constraints = self._human_stated_constraints.get(nbr_lower)
                        if constraints:
                            if colour_lower in constraints.get("forbidden", []):
                                continue  # Skip forbidden colors
                            required = constraints.get("required")
                            if required and colour_lower != required:
                                continue  # Skip non-required colors

                        allowed.append(colour)

                    data[nbr] = allowed  # Store for per_node field
                    allowed_colors_per_node.append(allowed)

                # Enumerate ALL combinations and test each
                valid_configs = []
                if all(allowed_colors_per_node):
                    for color_combo in itertools.product(*allowed_colors_per_node):
                        config = {boundary_nodes_sorted[i]: color_combo[i] for i in range(len(boundary_nodes_sorted))}

                        # Verify this config achieves zero penalty
                        if self.counterfactual_utils:
                            tmp = dict(base_beliefs)
                            tmp.update(config)
                            best_pen, _ = self._best_local_assignment_for(tmp)
                            if best_pen <= eps:
                                valid_configs.append(config)
                        else:
                            valid_configs.append(config)

                # Limit to avoid overwhelming
                if len(valid_configs) > 10:
                    valid_configs = valid_configs[:10]

                # Build FAILURE message with alternatives
                if current_is_complete:
                    message = f"✗ I CANNOT color my nodes with your current boundary settings ({', '.join([f'{k}={v}' for k, v in current_boundary.items()])}). Penalty={current_penalty:.2f}."
                else:
                    missing = [n for n in boundary_nodes_sorted if n not in current_boundary]
                    message = f"I need boundary colors for: {', '.join(missing)}."

                if valid_configs:
                    message += f" I CAN work with these {len(valid_configs)} alternative boundary settings:"
                else:
                    message += " I found NO valid boundary configurations. Check constraints!"

                content = {
                    "type": "constraints",
                    "data": {
                        "status": "NEED_ALTERNATIVES",
                        "current_boundary": current_boundary,
                        "current_penalty": float(current_penalty),
                        "valid_configs": valid_configs,
                        "per_node": data,
                        "message": message
                    }
                }
                self.log(f"LLM_C: Found {len(valid_configs)} valid alternative boundary configs")

                # Phase 5: Cache constraints for reuse in conversational responses
                try:
                    if isinstance(content, dict) and "data" in content:
                        # Convert constraints to options format for caching
                        cache_data = {"options": []}
                        if valid_configs:
                            for config in valid_configs[:10]:
                                cache_data["options"].append({
                                    "boundary_config": config,
                                    "penalty": 0.0,
                                    "feasible": True
                                })
                        self._cache_counterfactuals(cache_data)
                        self.log(f"Cached {len(valid_configs)} constraint options for conversational responses")
                except Exception as e:
                    self.log(f"Failed to cache constraints: {e}")

        elif self.message_type == "api":
            # LLM_API mode: Hierarchical constraints + utilities
            # Prioritizes constraint information but includes utility scores
            content = self._generate_api_message()

        else:  # free_text
            # Generate strategic free-form message using LLM
            body = self._generate_free_text_strategic()
            content = {"type": "free_text", "data": body}

        # send message to each neighbouring cluster.
        # Include a "report" field containing this cluster's current assignments
        # for *boundary nodes* adjacent to the recipient. This allows the participant
        # UI to show neighbour colours only when explicitly reported by that neighbour.
        for recipient in recipients:
            # Build per-recipient utility options for LLM-U.
            if self.message_type == "cost_list" and isinstance(content, dict):
                try:
                    import itertools

                    colour_points = {"blue": 1, "green": 2, "red": 3}

                    def score_for(mapping: Dict[Any, Any], nodes: List[Any]) -> int:
                        s = 0
                        for n in nodes:
                            c = str(mapping.get(n, "")).lower()
                            s += int(colour_points.get(c, 0))
                        return s

                    base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})

                    # Decide whether to discuss/optimise *team/combined* outcomes.
                    # Default is local-only unless the human explicitly asks.
                    include_team = False
                    try:
                        t = (self._last_human_text or "").lower()
                        for kw in ("total", "team", "combined", "overall", "global"):
                            if kw in t:
                                include_team = True
                                break
                    except Exception:
                        include_team = False

                    # Only consider the boundary nodes that belong to this recipient.
                    boundary_nodes: List[str] = []
                    seen = set()
                    for u in self.nodes:
                        for nbr in self.problem.get_neighbors(u):
                            nbr = str(nbr)
                            if nbr in self.nodes:
                                continue
                            if self.owners.get(nbr) != recipient:
                                continue
                            if nbr not in seen:
                                seen.add(nbr)
                                boundary_nodes.append(nbr)
                    boundary_nodes = sorted(boundary_nodes)

                    # If no boundary coupling, fall back to a neutral message.
                    if not boundary_nodes:
                        content = {"type": "cost_list", "data": {"boundary_nodes": [], "options": []}}
                    else:
                        known = {n: base_beliefs.get(n) for n in boundary_nodes if base_beliefs.get(n) is not None}

                        # Enumerate counterfactual boundary assignments.
                        # Default behaviour is to consider *small changes around the human's current settings*
                        # (Hamming distance <= 1 on the boundary nodes), unless the human asks for total/team.
                        max_enum = 3 ** len(boundary_nodes)
                        # guardrail just in case a problem instance has too many boundary nodes
                        if max_enum > 3 ** 8:
                            boundary_nodes = boundary_nodes[:8]

                        opts: List[Dict[str, Any]] = []

                        # DEBUG counters
                        total_configs = 3 ** len(boundary_nodes)
                        skipped_by_distance = 0
                        skipped_by_constraint = 0

                        current_key = None
                        if len(known) == len(boundary_nodes):
                            current_key = {k: str(v).lower() for k, v in known.items()}
                        for colours in itertools.product(self.domain, repeat=len(boundary_nodes)):
                            human_cfg = {boundary_nodes[i]: colours[i] for i in range(len(boundary_nodes))}

                            # FIX 4: Filter out configurations that violate human-stated constraints
                            violates_constraint = False
                            for node, color in human_cfg.items():
                                node_lower = str(node).lower()
                                color_lower = str(color).lower()

                                constraints = self._human_stated_constraints.get(node_lower)
                                if constraints:
                                    # Check forbidden colors
                                    if color_lower in constraints.get("forbidden", []):
                                        violates_constraint = True
                                        break

                                    # Check required color
                                    required = constraints.get("required")
                                    if required and color_lower != required:
                                        violates_constraint = True
                                        break

                            if violates_constraint:
                                skipped_by_constraint += 1
                                continue  # Skip this configuration

                            # Filter to local neighbourhood around current settings when fully known.
                            # SKIP filtering entirely when conflicts exist - show ALL valid options!
                            if (current_key is not None) and (not include_team):
                                # Check if we have conflicts with current boundary settings
                                has_conflicts = False
                                for my_node in self.nodes:
                                    my_color = self.assignments.get(my_node)
                                    for nbr in self.problem.get_neighbors(my_node):
                                        if nbr not in self.nodes:  # External neighbor
                                            nbr_color = base_beliefs.get(nbr)
                                            if nbr_color and my_color and str(nbr_color).lower() == str(my_color).lower():
                                                has_conflicts = True
                                                break
                                    if has_conflicts:
                                        break

                                # If NO conflicts, only show nearby options (distance <= 1)
                                # If conflicts exist, show ALL options (skip distance filtering)
                                if not has_conflicts:
                                    dist = 0
                                    for n in boundary_nodes:
                                        if str(human_cfg.get(n)).lower() != str(current_key.get(n)).lower():
                                            dist += 1
                                    if dist > 1:
                                        skipped_by_distance += 1
                                        continue  # Skip distant options when no conflicts

                            tmp = dict(base_beliefs)
                            tmp.update(human_cfg)
                            best_pen, best_asg = self._best_local_assignment_for(tmp)
                            a_score = score_for(best_asg, list(self.nodes))
                            h_score = score_for(human_cfg, boundary_nodes)
                            opts.append(
                                {
                                    "human": {k: str(v).lower() for k, v in human_cfg.items()},
                                    "penalty": float(best_pen),
                                    "agent_score": int(a_score),
                                    "human_score": int(h_score),
                                    "combined": int(a_score) + int(h_score),
                                }
                            )

                        # Determine the "current" configuration if all boundary nodes are known.
                        current = None
                        if current_key is not None:
                            for o in opts:
                                if o.get("human") == current_key:
                                    current = o
                                    break

                            # CRITICAL FIX: Recompute penalty using ACTUAL current assignments, not best possible.
                            # The penalty in opts[] is for the BEST agent assignments given that boundary config.
                            # But we need to report the penalty for the agent's ACTUAL current assignments!
                            if current is not None:
                                # Build complete assignment: agent's ACTUAL assignments + human's known boundary
                                actual_combined = dict(base_beliefs)
                                actual_combined.update(dict(self.assignments))
                                actual_current_penalty = self.problem.evaluate_assignment(actual_combined)

                                # Replace the optimistic penalty with the ACTUAL penalty
                                current["penalty"] = float(actual_current_penalty)

                                # Also verify: check for explicit conflicts between agent nodes and boundary
                                conflict_count = 0
                                for my_node in self.nodes:
                                    my_color = self.assignments.get(my_node)
                                    for nbr in self.problem.get_neighbors(my_node):
                                        if nbr not in self.nodes:  # External neighbor (boundary)
                                            nbr_color = base_beliefs.get(nbr)
                                            if nbr_color and my_color and str(nbr_color).lower() == str(my_color).lower():
                                                conflict_count += 1

                                # If we detected conflicts, ensure penalty is positive
                                if conflict_count > 0 and actual_current_penalty < 1e-9:
                                    self.log(f"WARNING: Detected {conflict_count} boundary conflicts but penalty={actual_current_penalty}. Forcing penalty > 0.")
                                    current["penalty"] = float(conflict_count)  # At least count the conflicts

                        # DEBUG: Log enumeration statistics
                        self.log(f"LLM_U enumeration for {recipient}:")
                        self.log(f"  Total possible configs: {total_configs}")
                        self.log(f"  Skipped by constraint: {skipped_by_constraint}")
                        self.log(f"  Skipped by distance: {skipped_by_distance}")
                        self.log(f"  Enumerated (in opts): {len(opts)}")
                        feasible = [o for o in opts if o.get("penalty", 0.0) <= 1e-9]
                        self.log(f"  Feasible (penalty=0): {len(feasible)}")

                        # Rank: feasible first, then higher score.
                        # If the human asked for team/total, rank by combined, otherwise by agent_score.
                        if include_team:
                            opts_sorted = sorted(
                                opts,
                                key=lambda o: (
                                    1 if o.get("penalty", 0.0) > 0.0 else 0,
                                    -(o.get("combined", 0)),
                                    -(o.get("agent_score", 0)),
                                ),
                            )
                        else:
                            opts_sorted = sorted(
                                opts,
                                key=lambda o: (
                                    1 if o.get("penalty", 0.0) > 0.0 else 0,
                                    -(o.get("agent_score", 0)),
                                    -(o.get("human_score", 0)),
                                ),
                            )
                        # Show more options (up to 10) to give human more choices
                        top = opts_sorted[:10]

                        # DEBUG: Log how many options we found
                        self.log(f"LLM_U for {recipient}: Found {len(opts)} total options, showing top {len(top)}")
                        if len(opts) < 3:
                            self.log(f"  WARNING: Very few options! Full opts list: {opts}")

                        # NOTE: Satisfaction state is managed in step() method via _compute_satisfied()
                        # Don't set it here to maintain consistency across all message types
                        # Log diagnostic info for debugging
                        sat_pen = None
                        sat_score = None
                        if current is not None:
                            sat_pen = float(current.get("penalty", 0.0))
                            sat_score = int(current.get("agent_score", 0))
                        elif top:
                            sat_pen = float(top[0].get("penalty", 0.0))
                            sat_score = int(top[0].get("agent_score", 0))
                        if sat_pen is not None:
                            try:
                                self.debug_reasoning_history.append(
                                    f"LLM-U status vs {recipient}: penalty={sat_pen} score={sat_score} known={known}"
                                )
                            except Exception:
                                pass

                        advice = None
                        if len(known) < len(boundary_nodes):
                            miss = [n for n in boundary_nodes if n not in known]
                            advice = (
                                "I can't see all your boundary colours yet. "
                                f"Please tell me {', '.join(miss)} (or set them in the UI) and I'll adapt."
                            )

                        content = {
                            "type": "cost_list",
                            "data": {
                                "boundary_nodes": boundary_nodes,
                                "known": {k: str(v).lower() for k, v in known.items()},
                                "current": current,
                                "options": top,
                                "points": dict(colour_points),
                            },
                        }
                        if advice:
                            content["advice"] = advice

                        # Phase 5: Cache counterfactuals for reuse in conversational responses
                        try:
                            if isinstance(content, dict) and "data" in content:
                                self._cache_counterfactuals(content["data"])
                                self.log(f"Cached {len(top)} counterfactual options for conversational responses")
                        except Exception as e:
                            self.log(f"Failed to cache counterfactuals: {e}")

                except Exception:
                    # If anything goes wrong, fall back to the precomputed content
                    pass

            boundary_report: Dict[str, Any] = {}
            try:
                for node in self.nodes:
                    for nbr in self.problem.get_neighbors(node):
                        if self.owners.get(nbr) == recipient:
                            boundary_report[node] = self.assignments.get(node)
                            break
            except Exception:
                boundary_report = {}

            # Debug logging for boundary reports
            if boundary_report:
                self.log(f"Constructed boundary report for {recipient}: {boundary_report}")
            else:
                self.log(f"No boundary nodes to report to {recipient}")

            out_content = content
            if isinstance(content, dict):
                out_content = dict(content)
                if boundary_report:
                    out_content["report"] = boundary_report
                    self.log(f"Sending boundary report to {recipient}: {boundary_report}")

            try:
                self.debug_last_outgoing[recipient] = out_content
            except Exception:
                pass

            # Check for duplicate messages to avoid repetition
            # EXCEPT when human sent a message this turn - always respond to human
            skip_due_to_duplication = False
            if recipient.lower() == "human" and self._received_human_message_this_turn:
                # Always respond to human when they sent a message, even if content is same
                self.log(f"Human sent message this turn - responding even if content is duplicate")
            elif self._is_duplicate_message(recipient, out_content):
                self.log(f"Skipping duplicate message to {recipient} (same content recently sent)")
                skip_due_to_duplication = True

            if skip_due_to_duplication:
                continue

            # Send the message and record it
            self.send(recipient, out_content)
            self._record_message(recipient, out_content)

        # NOW reset the human message flag after all messages have been sent
        # This ensures duplicate detection doesn't block responses to config updates
        self._received_human_message_this_turn = False

    def _generate_api_message(self) -> Dict[str, Any]:
        """Generate hierarchical API message combining constraints and utilities.

        Implements LLM_API mode from the paper: constraints take priority,
        utilities provide secondary guidance for tie-breaking among feasible options.

        Returns
        -------
        Dict[str, Any]
            Message dict with structure:
            {
                "type": "api",
                "data": {
                    "status": "SUCCESS" | "NEED_ALTERNATIVES",
                    "current_boundary": {...},
                    "current_penalty": float,
                    "constraints": {
                        "valid_configs": [...],
                        "count": int
                    },
                    "utilities": {
                        "config_scores": [...],
                        "best_by_agent": {...},
                        "best_by_human": {...},
                        "best_by_combined": {...}
                    }
                }
            }
        """
        # Get current boundary state
        current_boundary = self._get_boundary_assignments()
        current_combined = {**self.neighbour_assignments, **self.assignments}
        current_penalty = self.problem.evaluate_assignment(current_combined)

        # PHASE 1: Check if current boundary works (like LLM_C)
        status = "SUCCESS" if current_penalty < 1e-6 else "NEED_ALTERNATIVES"

        # PHASE 2: Compute valid boundary configurations (constraints)
        valid_configs = self._compute_valid_boundary_configs_with_constraints(max_configs=20)

        self.log(f"[LLM_API] Found {len(valid_configs)} valid boundary configurations (penalty=0)")

        # PHASE 3: Calculate utilities for each valid config
        color_points = {"blue": 1, "green": 2, "red": 3}
        config_scores = []

        for config in valid_configs:
            # Test this boundary config
            test_beliefs = dict(self.neighbour_assignments)
            test_beliefs.update(config)

            try:
                # Find best local assignment for this boundary
                best_pen, best_local_assign = self._best_local_assignment_for(test_beliefs)

                if best_pen < 1e-6:  # Only include truly feasible configs
                    # Calculate scores
                    agent_score = sum(color_points.get(str(best_local_assign.get(n, "")).lower(), 0)
                                    for n in self.nodes)

                    # Human nodes (boundary nodes)
                    human_nodes = list(config.keys())
                    human_score = sum(color_points.get(str(config.get(n, "")).lower(), 0)
                                    for n in human_nodes)

                    combined_score = agent_score + human_score

                    config_scores.append({
                        "boundary_config": config,
                        "agent_score": agent_score,
                        "human_score": human_score,
                        "combined_score": combined_score,
                        "penalty": best_pen,
                        "agent_coloring": best_local_assign
                    })
            except Exception as e:
                self.log(f"[LLM_API] Error computing utilities for config {config}: {e}")
                continue

        # Sort by combined score (descending)
        config_scores.sort(key=lambda x: x["combined_score"], reverse=True)

        # Find best configs by different criteria
        best_by_agent = config_scores[0] if config_scores else None
        best_by_human = max(config_scores, key=lambda x: x["human_score"]) if config_scores else None
        best_by_combined = config_scores[0] if config_scores else None  # Already sorted by combined

        # Build utilities dict
        utilities = {
            "config_scores": config_scores[:10],  # Show top 10
            "best_by_agent": best_by_agent["boundary_config"] if best_by_agent else None,
            "best_by_human": best_by_human["boundary_config"] if best_by_human else None,
            "best_by_combined": best_by_combined["boundary_config"] if best_by_combined else None
        }

        data = {
            "status": status,
            "current_boundary": current_boundary,
            "current_penalty": current_penalty,
            "constraints": {
                "valid_configs": valid_configs[:10],  # Show top 10 for constraints
                "count": len(valid_configs)
            },
            "utilities": utilities,
            "message": self._format_api_message_hint(status, len(valid_configs), config_scores)
        }

        self.log(f"[LLM_API] Generated message: status={status}, valid_configs={len(valid_configs)}, scored_configs={len(config_scores)}")

        return {"type": "api", "data": data}

    def _format_api_message_hint(self, status: str, num_valid: int, config_scores: List[Dict]) -> str:
        """Format a brief hint message for API data.

        Parameters
        ----------
        status : str
            SUCCESS or NEED_ALTERNATIVES
        num_valid : int
            Number of valid configurations
        config_scores : List[Dict]
            Scored configurations

        Returns
        -------
        str
            Brief hint message
        """
        if status == "SUCCESS":
            return "Your current boundary works! See utilities for optimization."
        elif num_valid > 0:
            if config_scores:
                best = config_scores[0]
                return f"Found {num_valid} valid options. Best combined score: {best['combined_score']}"
            else:
                return f"Found {num_valid} valid options."
        else:
            return "No valid boundary configurations found. Check constraints."

    def _generate_free_text_strategic(self) -> str:
        """Generate strategic free-form message using LLM.

        This method creates contextually appropriate natural language messages
        that consider current penalty, satisfaction status, and strategic goals.

        Returns
        -------
        str
            Strategic message for the neighbour.
        """
        # Build context for LLM
        penalty = self.problem.evaluate_assignment({**self.neighbour_assignments, **self.assignments})

        context = {
            "my_cluster": self.name,
            "my_nodes": list(self.nodes),
            "my_assignments": dict(self.assignments),
            "known_neighbor_assignments": dict(self.neighbour_assignments),
            "current_penalty": penalty,
            "boundary_nodes": list(self.neighbour_assignments.keys()),
            "satisfied": self.satisfied
        }

        # Try LLM generation if available
        if hasattr(self.comm_layer, "_call_openai") and not getattr(self.comm_layer, "manual", False):
            try:
                prompt = f"""You are Agent {context['my_cluster']} in a graph coloring negotiation.

Your situation:
- Your nodes: {context['my_nodes']}
- Your colors: {context['my_assignments']}
- Known neighbor colors: {context['known_neighbor_assignments']}
- Current conflicts (penalty): {context['current_penalty']:.2f}
- Satisfied with solution: {context['satisfied']}

Task: Write a brief, strategic message to your neighbor about your coloring.
- If satisfied (penalty=0): Explain your coloring and confirm it works
- If conflicts exist: Suggest specific changes that would help resolve conflicts
- Be collaborative and specific (mention node names and colors)
- Maximum 2-3 sentences

Message:"""

                response = self.comm_layer._call_openai(prompt, max_tokens=100)
                if response and response.strip():
                    self.log("[LLM_F] Generated strategic message via LLM")
                    return response.strip()
            except Exception as e:
                self.log(f"[LLM_F] LLM generation failed: {e}, falling back to template")

        # Fallback to template
        return self._generate_free_text_template(context)

    def _generate_free_text_template(self, context: Dict[str, Any]) -> str:
        """Template-based free text generation (no LLM).

        Parameters
        ----------
        context : Dict[str, Any]
            Context dictionary with keys: my_nodes, my_assignments,
            known_neighbor_assignments, current_penalty, satisfied

        Returns
        -------
        str
            Template-based message.
        """
        penalty = context.get("current_penalty", 0.0)
        satisfied = context.get("satisfied", False)
        my_assignments = context.get("my_assignments", {})
        neighbor_assignments = context.get("known_neighbor_assignments", {})

        if satisfied or penalty < 1e-9:
            # No conflicts - confirm solution
            assignment_str = ", ".join([f"{k}={v}" for k, v in my_assignments.items()])
            return f"I've colored my nodes: {assignment_str}. This works with your current assignments (no conflicts)."
        else:
            # Conflicts detected - suggest changes
            messages: List[str] = []
            for node in context.get("my_nodes", []):
                assign = my_assignments.get(node)
                if not assign:
                    continue

                # Check for conflicts with neighbors
                neighbors = self.problem.get_neighbors(node)
                for nbr in neighbors:
                    if nbr not in context.get("my_nodes", []):
                        nbr_color = neighbor_assignments.get(nbr)
                        if nbr_color and str(nbr_color).lower() == str(assign).lower():
                            # Found conflict
                            messages.append(
                                f"My node {node} is {assign}, which conflicts with your {nbr}. "
                                f"Could you change {nbr} to avoid {assign}?"
                            )
                            break

            if messages:
                return " ".join(messages[:2])  # Limit to 2 conflicts
            else:
                # Generic message
                assignment_str = ", ".join([f"{k}={v}" for k, v in sorted(my_assignments.items())])
                return f"My nodes are: {assignment_str}. Current penalty: {penalty:.2f}. Let's coordinate to resolve conflicts."

    def receive(self, message: Message) -> None:
        """Handle incoming messages and update neighbour assignments.

        The cluster agent currently records any explicit assignments sent
        by neighbouring clusters but otherwise treats incoming messages
        as opaque hints.  Messages may contain different types; this
        implementation inspects the ``data`` field if present and
        extracts assignment information when a neighbour reports its
        assignments directly.  Future extensions could interpret
        ``cost_list`` or ``constraints`` messages to influence the local
        optimisation.
        """
        super().receive(message)

        # Remember the last human utterance (best-effort). The comm layer may wrap
        # messages with [mapping: ...] tags; keep the raw text for keyword checks.
        try:
            if str(message.sender).lower() == "human":
                self._last_human_text = str(message.content)
                # Flag that human sent a message this turn (forces response even if duplicate)
                self._received_human_message_this_turn = True

                # Classify the human message (Phase 2: Action Routing)
                try:
                    from agents.message_classifier import MessageClassifier
                    if not hasattr(self, '_message_classifier'):
                        # Create classifier with LLM call function from comm layer
                        llm_func = None
                        if hasattr(self.comm_layer, '_call_openai'):
                            llm_func = self.comm_layer._call_openai
                        self._message_classifier = MessageClassifier(llm_call_function=llm_func)

                    # Classify message with recent dialogue history
                    dialogue_history = [str(x) for x in list(getattr(self, "debug_incoming_raw", []))[-6:]]
                    classification = self._message_classifier.classify_message(
                        self._last_human_text,
                        dialogue_history=dialogue_history
                    )

                    # Store classification for use in step()
                    self._last_message_classification = classification

                    self.log(f"Message classified as: {classification.primary} (confidence: {classification.confidence:.2f})")

                    # Log classification for research analysis
                    from agents.message_classifier import log_classification
                    import os
                    # Try to get log file path from environment or use default
                    log_file = None
                    if hasattr(self, 'comm_layer') and hasattr(self.comm_layer, 'llm_trace_file'):
                        log_file = self.comm_layer.llm_trace_file
                    log_classification(classification, log_file=log_file)

                    # CRITICAL: Call message handlers to compute counterfactuals/search results
                    # Store results so they can be used in conversational response
                    try:
                        if classification.primary == "QUERY":
                            result = self._handle_query(classification)
                            self._last_message_result = result
                            self.log(f"Query handler result: {result.get('query_type', 'unknown')}")
                        elif classification.primary == "PREFERENCE":
                            result = self._handle_preference(classification)
                            self._last_message_result = result
                        elif classification.primary == "INFORMATION":
                            result = self._handle_information(classification)
                            self._last_message_result = result
                        else:
                            self._last_message_result = None
                    except Exception as handler_error:
                        self.log(f"Message handler failed: {handler_error}")
                        self._last_message_result = None

                except Exception as e:
                    self.log(f"Message classification failed: {e}")
                    self._last_message_classification = None
                    self._last_message_result = None

                # Parse human requests to change specific node colors
                # Look for patterns like "change b2 to green", "set b2 to green", "make b2 green"
                import re
                text_lower = self._last_human_text.lower()

                # Pattern: "change/set/make/switch NODE to/= COLOR"
                # Matches: "change b2 to green", "set b2=green", "make b2 blue", "switch b2 to red"
                patterns = [
                    r'\b(?:change|set|make|switch)\s+(\w+)\s+(?:to|=)\s+(\w+)',
                    r'\b(\w+)\s*=\s*(\w+)',  # "b2=green"
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, text_lower)
                    for node, color in matches:
                        # Check if this is actually one of our nodes
                        if node in self.nodes and color in [str(c).lower() for c in self.domain]:
                            # Force this assignment in the next step
                            if not hasattr(self, 'forced_local_assignments'):
                                self.forced_local_assignments = {}
                            # IMPORTANT: Normalize color to match domain casing
                            normalized_color = self._normalize_color(color)
                            # Check if this node is fixed (immutable)
                            if node in self.fixed_local_nodes:
                                fixed_color = self.fixed_local_nodes[node]
                                self.log(f"WARNING: Cannot force {node} to {normalized_color} - node is FIXED to {fixed_color}")
                            else:
                                self.forced_local_assignments[node] = normalized_color
                                self.log(f"Human requested: {node} -> {normalized_color}. Will force this assignment.")
        except Exception as e:
            self.log(f"Error parsing human message for forced assignments: {e}")
            pass
        content = message.content
        try:
            self.debug_incoming_raw.append(content)
        except Exception:
            pass
        # attempt to parse structured content via the communication layer
        structured = self.comm_layer.parse_content(message.sender, self.name, content)
        try:
            self.debug_incoming_parsed.append(structured)
        except Exception:
            pass
        # Record how the communication layer interpreted the message.
        # This is useful for debugging and for auditing partial observability.
        try:
            self.log(f"Parsed message from {message.sender}: {structured}")
        except Exception:
            pass
        # if the message explicitly contains assignments, update neighbour_assignments
        # structured data may include a mapping under the key 'assignments'
        if isinstance(structured, dict):
            # direct assignment messages (e.g. from legacy MultiNodeAgent)
            # will have raw mapping from node to value
            # we treat any keys that are nodes not in our cluster as assignments
            if "data" not in structured and "type" not in structured:
                for node, val in structured.items():
                    if node not in self.nodes:
                        self.neighbour_assignments[node] = val
                        self.log(f"Updated neighbour assignment: {node} -> {val}")
            else:
                # handle messages with explicit type
                m_type = structured.get("type")
                # data may be dictionary with neighbour nodes as keys
                data_field = structured.get("data")
                if isinstance(data_field, dict):
                    # if data contains assignments for neighbours, store them
                    for node, val in data_field.items():
                        # assignments encoded as strings or lists are ignored here
                        if node not in self.nodes:
                            # if neighbour provides a single colour assignment
                            if isinstance(val, str):
                                self.neighbour_assignments[node] = val
                                self.log(f"Updated neighbour assignment: {node} -> {val}")

        # If we didn't receive a typed/structured mapping, attempt to extract
        # neighbour assignments from free-form human text. This is a key part
        # of the study: agents may *only* learn the human's state if it is
        # communicated via language.
        if isinstance(structured, str):
            text = structured

            # CRITICAL FIX: Don't extract from complaints/references to agent's suggestions
            # When human says "You haven't proposed X" or "You keep suggesting X",
            # they're complaining about the agent, not stating their own assignments.
            complaint_patterns = [
                "you haven't", "you keep", "you said", "you proposed",
                "you suggested", "you mentioned", "you only", "you're saying",
                "you've said", "you've proposed", "you've suggested",
                "as you said", "like you said"
            ]
            is_complaint = any(phrase in text.lower() for phrase in complaint_patterns)

            if is_complaint:
                self.log(f"Skipping extraction from complaint/reference: {text[:80]}...")

            # Extract assignments from the CURRENT message only
            # CRITICAL: Don't use history for extraction - it causes old assignments to persist
            # History is for interpretation/classification, not for extracting what changed NOW
            extracted: Dict[str, str] = {}
            if not is_complaint and text.strip():  # Only extract from non-empty messages
                try:
                    if hasattr(self.comm_layer, "parse_assignments_from_text_llm"):
                        # Pass ONLY the current message for extraction, not the full history
                        # Otherwise empty config messages will extract from old messages
                        extracted = self.comm_layer.parse_assignments_from_text_llm(
                            sender=message.sender,
                            recipient=self.name,
                            history=[],  # Empty history - extract from current message only
                            text=text,
                        )
                except Exception:
                    extracted = {}

                # Fallback: heuristic extraction from current message
                if not extracted:
                    import re  # Import here for use in this block
                    pattern1 = re.compile(r"\b([A-Za-z]\w*)\s*(?:=|is|:)\s*(red|green|blue)\b", re.IGNORECASE)
                    pattern2 = re.compile(r"\b(red|green|blue)\s*(?:for)\s*([A-Za-z]\w*)\b", re.IGNORECASE)
                    for m in pattern1.finditer(text):
                        node, colour = m.group(1), m.group(2)
                        extracted[node.lower()] = colour.lower()
                    for m in pattern2.finditer(text):
                        colour, node = m.group(1), m.group(2)
                        extracted[node.lower()] = colour.lower()

            if extracted:
                for node, colour in extracted.items():
                    # IMPORTANT: Normalize color to match domain casing
                    normalized_colour = self._normalize_color(colour)
                    # If the human mentions one of *our* nodes, treat it as a
                    # (soft) directive to set that node. Otherwise, treat it as
                    # a belief about a neighbour-owned node.
                    if node in self.nodes:
                        # Check if this node is fixed (immutable)
                        if node in self.fixed_local_nodes:
                            fixed_color = self.fixed_local_nodes[node]
                            self.log(f"WARNING: Cannot force {node} to {normalized_colour} - node is FIXED to {fixed_color}")
                        else:
                            self.forced_local_assignments[node] = normalized_colour
                            try:
                                self.log(f"Forced local assignment requested: {node} -> {normalized_colour}")
                            except Exception:
                                pass
                    else:
                        # CRITICAL FIX: Don't update neighbour_assignments from PREFERENCE messages
                        # Preferences are aspirational ("I'd like X"), not statements of current state ("X is Y")
                        # Only update beliefs for INFORMATION, COMMAND, or unclassified messages
                        classification = getattr(self, "_last_message_classification", None)
                        if classification and classification.primary == "PREFERENCE":
                            self.log(f"Skipping neighbour assignment update from PREFERENCE message: {node} -> {normalized_colour}")
                            self.log(f"  (Human said they'd LIKE {node}={normalized_colour}, but hasn't actually changed it yet)")
                        else:
                            self.neighbour_assignments[node] = normalized_colour
                try:
                    self.log(f"Extracted assignments from text: {extracted} (normalized)")
                except Exception:
                    pass

            # FIX 4: Parse negative constraints ("X can't be Y", "X must not be Y")
            # These are soft constraints that influence utility calculations
            if isinstance(structured, str):
                negative_patterns = [
                    # "h1 can't be green", "h1 cannot be red"
                    r"\b(\w+)\s+(?:can'?t|cannot|must\s+not)\s+be\s+(red|green|blue)\b",
                    # "not green for h1"
                    r"\bnot\s+(red|green|blue)\s+(?:for|on)\s+(\w+)\b",
                    # "h1 should not be green"
                    r"\b(\w+)\s+should\s+not\s+be\s+(red|green|blue)\b",
                    # "avoid green for h1", "h1 avoid green"
                    r"\b(\w+)\s+avoid\s+(red|green|blue)\b",
                    r"\bavoid\s+(red|green|blue)\s+(?:for|on)\s+(\w+)\b",
                ]

                for pattern_str in negative_patterns:
                    pattern = re.compile(pattern_str, re.IGNORECASE)
                    for match in pattern.finditer(structured):
                        # Handle different pattern formats
                        if "not" in pattern_str and ("for|on" in pattern_str or "avoid" in pattern_str.lower()):
                            # Pattern: "not green for h1" or "avoid green for h1"
                            color, node = match.group(1), match.group(2)
                        else:
                            # Pattern: "h1 can't be green" or "h1 avoid green"
                            node, color = match.group(1), match.group(2)

                        node_lower = node.lower()
                        color_normalized = self._normalize_color(color)
                        color_lower = str(color_normalized).lower()

                        # Only track constraints on boundary nodes (not our own nodes)
                        if node_lower not in [n.lower() for n in self.nodes]:
                            if node_lower not in self._human_stated_constraints:
                                self._human_stated_constraints[node_lower] = {
                                    "forbidden": [], "required": None
                                }

                            if color_lower not in self._human_stated_constraints[node_lower]["forbidden"]:
                                self._human_stated_constraints[node_lower]["forbidden"].append(color_lower)
                                self.log(f"Human constraint: {node} CANNOT be {color_normalized}")

                # Parse "can't change X" or "X is fixed" - means X must stay at current value
                immutable_patterns = [
                    r"(?:can'?t|cannot)\s+change\s+(\w+)",  # "can't change h1"
                    r"(\w+)\s+(?:can'?t|cannot)\s+change",  # "h1 can't change"
                    r"(\w+)\s+(?:is|stays?|remains?)\s+fixed",  # "h1 is fixed"
                    r"(\w+)\s+(?:has to|must)\s+(?:stay|remain)",  # "h1 has to stay"
                ]

                for pattern_str in immutable_patterns:
                    pattern = re.compile(pattern_str, re.IGNORECASE)
                    for match in pattern.finditer(structured):
                        node = match.group(1)
                        node_lower = node.lower()

                        # This node can't change - record its CURRENT value as required
                        if node_lower not in [n.lower() for n in self.nodes]:
                            current_value = getattr(self, "neighbour_assignments", {}).get(node_lower)
                            if current_value:
                                if node_lower not in self._human_stated_constraints:
                                    self._human_stated_constraints[node_lower] = {
                                        "forbidden": [], "required": None
                                    }

                                self._human_stated_constraints[node_lower]["required"] = str(current_value).lower()
                                self.log(f"Human constraint: {node} is IMMUTABLE (must stay {current_value})")

                # Also parse positive requirements ("X must be Y", "X has to be Y")
                requirement_patterns = [
                    r"\b(\w+)\s+(?:must|has to|needs to)\s+be\s+(red|green|blue)\b",
                    # "I have to make X red", "I must make X red"
                    r"\b(?:must|have to|need to)\s+(?:make|set|keep)\s+(\w+)\s+(red|green|blue)\b",
                ]

                for pattern_str in requirement_patterns:
                    pattern = re.compile(pattern_str, re.IGNORECASE)
                    for match in pattern.finditer(structured):
                        node, color = match.group(1), match.group(2)
                        node_lower = node.lower()
                        color_normalized = self._normalize_color(color)
                        color_lower = str(color_normalized).lower()

                        if node_lower not in [n.lower() for n in self.nodes]:
                            if node_lower not in self._human_stated_constraints:
                                self._human_stated_constraints[node_lower] = {
                                    "forbidden": [], "required": None
                                }

                            self._human_stated_constraints[node_lower]["required"] = color_lower
                            self.log(f"Human constraint: {node} MUST be {color_normalized}")
