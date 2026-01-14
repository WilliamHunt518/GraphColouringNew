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

        # CRITICAL: Never satisfied if there are conflicts (penalty > 0)
        # Even if we can't do better given current boundary, we're not satisfied
        # because the boundary needs to change to achieve a valid coloring
        if current_pen > 1e-9:
            return False

        # No conflicts - check if we're at local optimum
        best_pen, _ = self._best_local_assignment()
        return current_pen <= best_pen + 1e-9

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

        prompt = (
            f"You are agent '{self.name}' collaborating with a human on a graph coloring task.\n\n"
            f"The human just said: \"{self._last_human_text}\"\n\n"
            f"**CRITICAL FACT:** {change_status}\n\n"
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

        # Clear forced assignments after they've been applied (one-time use)
        if hasattr(self, 'forced_local_assignments') and self.forced_local_assignments:
            self.log(f"Clearing forced_local_assignments: {self.forced_local_assignments}")
            self.forced_local_assignments = {}

        # If greedy search got stuck, snap to the best local assignment (cluster sizes are small).
        try:
            base = dict(getattr(self, "neighbour_assignments", {}) or {})
            current_pen = self.problem.evaluate_assignment({**base, **dict(self.assignments)})
            best_pen, best_assign = self._best_local_assignment_for(base)
            if current_pen > best_pen + 1e-9:
                self.assignments = dict(best_assign)
                assignments_changed = True  # Mark that we changed
                try:
                    self.log(f"Snapped to best local assignment (pen {current_pen} -> {best_pen}).")
                except Exception:
                    pass
        except Exception:
            pass


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

        try:
            self.satisfied = bool(self._compute_satisfied())
            self.log(f"Satisfied: {self.satisfied}")
        except Exception:
            self.satisfied = False

        # --- Handle conversational human messages AFTER computing assignments ---
        # This way we know if our assignments actually changed before responding.
        if self._last_human_text and self._last_human_text.strip():
            try:
                self._respond_to_human_conversationally(assignments_changed, old_assignments)
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
            # Constraint-oriented messages.
            # If counterfactual_utils=True, allowed colours are those that achieve
            # best-response penalty (within eps). If False, allowed colours are those
            # that minimise immediate boundary clashes with the current local assignment.
            eps = 1e-6
            data: Dict[str, List[Any]] = {}
            base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})

            ext_neighs: Set[str] = set()
            for node in self.nodes:
                for nbr in self.problem.get_neighbors(node):
                    if nbr not in self.nodes:
                        ext_neighs.add(str(nbr))

            for nbr in sorted(ext_neighs):
                per_colour_pen: Dict[Any, float] = {}
                for colour in self.domain:
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
            content = {"type": "constraints", "data": data}
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

                        current_key = None
                        if len(known) == len(boundary_nodes):
                            current_key = {k: str(v).lower() for k, v in known.items()}
                        for colours in itertools.product(self.domain, repeat=len(boundary_nodes)):
                            human_cfg = {boundary_nodes[i]: colours[i] for i in range(len(boundary_nodes))}

                            # Filter to local neighbourhood around current settings when fully known.
                            # Allow larger Hamming distance when conflicts exist to explore more options.
                            if (current_key is not None) and (not include_team):
                                dist = 0
                                for n in boundary_nodes:
                                    if str(human_cfg.get(n)).lower() != str(current_key.get(n)).lower():
                                        dist += 1

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

                                # Only filter to distance 1 if NO conflicts
                                # Allow larger changes (distance 2) when conflicts exist
                                max_distance = 2 if has_conflicts else 1
                                if dist > max_distance:
                                    continue

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
                        top = opts_sorted[:4]

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
            self.send(recipient, out_content)

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
                            self.forced_local_assignments[node] = color
                            self.log(f"Human requested: {node} -> {color}. Will force this assignment.")
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
                    # If the human mentions one of *our* nodes, treat it as a
                    # (soft) directive to set that node. Otherwise, treat it as
                    # a belief about a neighbour-owned node.
                    if node in self.nodes:
                        self.forced_local_assignments[node] = colour
                        try:
                            self.log(f"Forced local assignment requested: {node} -> {colour}")
                        except Exception:
                            pass
                    else:
                        self.neighbour_assignments[node] = colour
                try:
                    self.log(f"Extracted assignments from text: {extracted}")
                except Exception:
                    pass
