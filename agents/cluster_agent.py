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

        # When the human explicitly requests a colour for one of this agent's
        # own nodes (e.g. "pick blue for b2"), we treat it as a *soft forced*
        # assignment that the local solver should respect.
        self.forced_local_assignments: Dict[str, str] = {}

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
            forced = dict(getattr(self, "forced_local_assignments", {}) or {})
            free_nodes = [n for n in self.nodes if n not in forced]
            for combo in itertools.product(self.domain, repeat=len(free_nodes)):
                candidate = dict(forced)
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
            forced = dict(getattr(self, "forced_local_assignments", {}) or {})
            for node in self.nodes:
                if node in forced:
                    new_assignment[node] = forced[node]
                    try:
                        self.debug_last_local_scores[node] = {forced[node]: 0.0}  # type: ignore[attr-defined]
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
        for combo in itertools.product(self.domain, repeat=len(self.nodes)):
            cand = {n: v for n, v in zip(self.nodes, combo)}
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
        """Whether the agent is satisfied with its current assignment."""
        base = dict(getattr(self, "neighbour_assignments", {}) or {})
        current_pen = self.problem.evaluate_assignment({**base, **dict(self.assignments)})
        best_pen, _ = self._best_local_assignment()
        return current_pen <= best_pen + 1e-9

    def step(self) -> None:
        """Perform one iteration of the cluster agent’s process.

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

        # compute new assignments
        new_assignment = self.compute_assignments()
        if new_assignment != self.assignments:
            self.log(f"Updated assignments from {self.assignments} to {new_assignment}")
        else:
            self.log(f"Assignments unchanged: {self.assignments}")
        self.assignments = new_assignment

        # update satisfaction flag (soft convergence)
        try:
            self.satisfied = bool(self._compute_satisfied())
            self.log(f"Satisfied: {self.satisfied}")
        except Exception:
            self.satisfied = False

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
            # Utility-oriented messages.
            #
            # Two supported policies (toggleable for debugging / study variants):
            #
            #  - counterfactual_utils=True (default):
            #    For each external boundary node `nbr` and each colour choice, we
            #    estimate the *best achievable* local penalty in our cluster if the
            #    neighbour chose that colour (best-response counterfactual).
            #
            #  - counterfactual_utils=False:
            #    Naive utility hints measured against our *current* local assignment
            #    (how many boundary clashes would occur if `nbr` were colour c).
            data: Dict[str, Dict[Any, float]] = {}
            base_beliefs = dict(getattr(self, "neighbour_assignments", {}) or {})

            # collect unique external neighbours adjacent to any local node
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
                        # Naive: count boundary conflicts with our current local assignment.
                        conflicts = 0.0
                        for u in self.nodes:
                            try:
                                if nbr in self.problem.get_neighbors(u) and self.assignments.get(u) == colour:
                                    conflicts += 1.0
                            except Exception:
                                continue
                        per_colour_pen[colour] = conflicts
                # normalise
                m = min(per_colour_pen.values()) if per_colour_pen else 0.0
                cost_map = {c: (p - m) for c, p in per_colour_pen.items()}
                data[nbr] = cost_map

            # If we have not been told the human's current colours, the structured
            # table alone can be unhelpful (it may look like "do whatever"). In that
            # case we attach a short advice string prompting the human to share their
            # current boundary colours or avoid known clashes.
            advice = None
            try:
                known = {n: base_beliefs.get(n) for n in data.keys() if base_beliefs.get(n) is not None}
                if not known:
                    advice = (
                        "I don't yet know your current boundary colours. "
                        "If you tell me your colours for "
                        f"{', '.join(sorted(data.keys()))}, I can avoid clashes more directly."
                    )
                else:
                    # Identify any immediate clashes with our current boundary assignments.
                    clashes = []
                    for human_node, h_col in known.items():
                        for local_node in self.nodes:
                            if human_node in self.problem.get_neighbors(local_node):
                                if self.assignments.get(local_node) == h_col:
                                    clashes.append((human_node, h_col, local_node))
                    if clashes:
                        items = "; ".join([f"{hn}={hc} clashes with my {ln}={hc}" for hn, hc, ln in clashes])
                        advice = (
                            "We currently have a boundary clash: "
                            + items
                            + ". If possible, please change the human node colour away from that value, or tell me which node you prefer I should adjust."
                        )
            except Exception:
                advice = None

            content: Dict[str, Any] = {"type": "cost_list", "data": data}
            if isinstance(advice, str) and advice.strip():
                content["advice"] = advice.strip()
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