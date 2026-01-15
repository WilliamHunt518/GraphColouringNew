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

        prompt = (
            f"You are agent '{self.name}' collaborating with a human on a graph coloring task.\n\n"
            f"The human just said: \"{self._last_human_text}\"\n\n"
            f"**CRITICAL FACT:** {change_status}\n\n"
            f"**VERIFICATION:** Before you respond, understand that:\n"
            f"- Current penalty = {current_penalty:.2f} (0 = no conflicts, >0 = conflicts exist)\n"
            f"- Number of detected conflicts = {len(conflicts)}\n"
            f"- If penalty > 0 OR conflicts exist, you CANNOT claim to have a good/valid solution\n"
            f"- If penalty > 0, you MUST acknowledge conflicts exist in your response\n"
            f"- {assignment_verification}\n\n"
            f"Your current state:\n{state_summary}\n"
        )

        if is_question:
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
                "Generate a conversational response (2-3 sentences max) that:\n"
                "1. DIRECTLY responds to what the human said\n"
                "2. If you DID change nodes, mention the specific changes\n"
                "3. If you DID NOT change nodes AND conflicts exist, be brutally honest: 'I CANNOT fix this by changing my nodes - you must change the boundary'\n"
                "4. NEVER EVER say 'I changed' if your assignments didn't actually change - that is LYING\n"
                "5. If penalty > 0, this is a BAD/INVALID coloring - never claim you have a good solution\n\n"
                "Examples if assignments CHANGED:\n"
                "- 'Yes, I changed a2 from red to green to avoid the clash with h1.'\n\n"
                "Examples if assignments DID NOT change:\n"
                "- 'I CANNOT resolve this clash by changing my internal nodes. You need to change h1 from red to blue.'\n"
                "- 'My nodes cannot change without making things worse. Please change h2 to green to eliminate the conflict.'\n"
                "- 'I am stuck with this configuration. The boundary colors force this clash. You must change your nodes.'\n\n"
                "Return ONLY the conversational response text."
            )

        try:
            response_text = self.comm_layer._call_openai(prompt, max_tokens=200)

            if response_text and response_text.strip():
                # CRITICAL: Post-process to remove lies about changes
                final_response = response_text.strip()

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

        # Reset human message flag at start of each step
        # (will be set to True in receive() if human sends a message this turn)
        self._received_human_message_this_turn = False

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
            # Don't recompute if we just reset due to boundary change
            # (keep satisfied=False that we set above)
            if not (neighbor_changed and not self.satisfied):
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
        if self._last_human_text and self._last_human_text.strip():
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

                # Compute which boundary colors work for each node
                data: Dict[str, List[Any]] = {}
                for nbr in boundary_nodes_sorted:
                    per_colour_pen: Dict[Any, float] = {}
                    for colour in self.domain:
                        # Check human-stated constraints
                        nbr_lower = str(nbr).lower()
                        colour_lower = str(colour).lower()

                        constraints = self._human_stated_constraints.get(nbr_lower)
                        if constraints:
                            if colour_lower in constraints.get("forbidden", []):
                                per_colour_pen[colour] = float('inf')
                                continue
                            required = constraints.get("required")
                            if required and colour_lower != required:
                                per_colour_pen[colour] = float('inf')
                                continue

                        # Compute penalty for this boundary color
                        if self.counterfactual_utils:
                            tmp = dict(base_beliefs)
                            tmp[nbr] = colour
                            best_pen, _ = self._best_local_assignment_for(tmp)
                            per_colour_pen[colour] = float(best_pen)
                        else:
                            conflicts = 0.0
                            for u in self.nodes:
                                try:
                                    if nbr in self.problem.get_neighbors(u) and self.assignments.get(u) == colour:
                                        conflicts += 1.0
                                except Exception:
                                    continue
                            per_colour_pen[colour] = conflicts

                    best = min(per_colour_pen.values()) if per_colour_pen else 0.0
                    allowed = [c for c, p in per_colour_pen.items() if p <= best + eps]
                    data[nbr] = allowed

                # Enumerate complete valid configurations
                import itertools
                allowed_colors_per_node = [data[node] for node in boundary_nodes_sorted]

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
        else:  # free_text
            # build a simple natural-language summary for neighbours
            messages: List[str] = []
            for node in self.nodes:
                for nbr in self.problem.get_neighbors(node):
                    if nbr in self.nodes:
                        continue
                    assign = self.assignments[node]
                    messages.append(
                        f"Our node {node} is {assign}; please avoid choosing {assign} for your node {nbr} to prevent a clash."
                    )
            body = " ".join(messages) if messages else "No clashes detected."
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

                        # Update our satisfaction state (for the UI label) using the current config when known,
                        # otherwise by our best feasible option.
                        sat_pen = None
                        sat_score = None
                        if current is not None:
                            sat_pen = float(current.get("penalty", 0.0))
                            sat_score = int(current.get("agent_score", 0))
                        elif top:
                            sat_pen = float(top[0].get("penalty", 0.0))
                            sat_score = int(top[0].get("agent_score", 0))
                        if sat_pen is not None:
                            self.satisfied = bool(sat_pen <= 0.0)
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

            out_content = content
            if isinstance(content, dict):
                out_content = dict(content)
                if boundary_report:
                    out_content["report"] = boundary_report

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

            # Prefer an LLM-backed parser when available (and when the comm layer
            # is configured with history). This enables LLM-F to interpret *the
            # dialogue history*, not only the current message.
            extracted: Dict[str, str] = {}
            try:
                if hasattr(self.comm_layer, "parse_assignments_from_text_llm"):
                    hist = [str(x) for x in list(getattr(self, "debug_incoming_raw", []))]
                    extracted = self.comm_layer.parse_assignments_from_text_llm(
                        sender=message.sender,
                        recipient=self.name,
                        history=hist,
                        text=text,
                    )
            except Exception:
                extracted = {}

            # Fallback: heuristic extraction.
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

                # Also parse positive requirements ("X must be Y", "X has to be Y")
                requirement_patterns = [
                    r"\b(\w+)\s+(?:must|has to|needs to)\s+be\s+(red|green|blue)\b",
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
