"""Multi‑node LLM‑first orchestrated agent (1B mode).

This class extends the multi‑node agent architecture to allow a large
language model (LLM) to orchestrate algorithmic primitives on a group
of variables.  It mirrors the single‑node :class:`LLMFirstAgent` but
operates over multiple nodes controlled by one owner.  At each step
the agent summarises its current assignments and the algorithm's
recommended joint assignment, constructs a prompt and queries the
LLM for instructions.  The LLM may instruct the agent to run the
algorithmic tool (which performs an exhaustive search for the best
assignment) and/or to adopt a specific assignment for one or more
nodes.  If no LLM is available the agent defaults to the algorithm's
recommendation.  After deciding on assignments the agent sends a
natural‑language summary to neighbouring agents via the communication
layer.  The summary includes the current assignment and a mapping
string so that algorithmic recipients can parse it back into a
dictionary.
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional, Tuple

from .multi_node_agent import MultiNodeAgent
from .base_agent import Message
from comm.communication_layer import BaseCommLayer, PassThroughCommLayer


class MultiNodeLLMFirstAgent(MultiNodeAgent):
    """Multi‑node agent implementing the LLM‑first architecture.

    Parameters
    ----------
    name : str
        Owner identifier (e.g. "Alice", "Bob").
    problem : GraphColoring
        Graph colouring problem definition shared by all agents.
    comm_layer : BaseCommLayer
        Communication layer used for sending and receiving messages.  The
        layer may employ an LLM to summarise outgoing messages and
        extract structured content from incoming ones.
    local_nodes : list of str
        List of nodes controlled by this agent.
    owners : dict
        Mapping from node identifiers to owner names.  Used to route
        messages to the appropriate neighbouring owner.
    initial_assignments : dict, optional
        Optional initial assignment for local nodes.  Missing nodes will
        be initialised randomly from the domain.
    """

    def __init__(
        self,
        name: str,
        problem: Any,
        comm_layer: BaseCommLayer,
        local_nodes: List[str],
        owners: Dict[str, str],
        initial_assignments: Optional[Dict[str, Any]] = None,
    ) -> None:
        # initialise the parent MultiNodeAgent to set up assignments and neighbour tracking
        super().__init__(
            name=name,
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=local_nodes,
            owners=owners,
            initial_assignments=initial_assignments,
        )
        # internal algorithmic tool (multi‑node) using pass‑through comm layer
        # This tool performs exhaustive search for the best assignment when
        # instructed by the LLM.  It uses the same set of local nodes and
        # owners as the orchestrating agent but operates independently.
        self.tool = MultiNodeAgent(
            name=name,
            problem=problem,
            comm_layer=PassThroughCommLayer(),
            local_nodes=local_nodes,
            owners=owners,
            initial_assignments=initial_assignments,
        )
        # keep the tool's assignments in sync with the agent's assignments
        self.tool.assignments = dict(self.assignments)
        # maintain a history of free‑form messages received from neighbours.  These messages
        # are used to provide additional context to the LLM when constructing prompts.  Each
        # entry is a tuple (sender, content).  Messages are appended as they arrive.
        self.neighbour_messages: List[Tuple[str, str]] = []

    def receive(self, message: Message) -> None:
        """Forward incoming messages to the internal tool and update neighbour assignments.

        Messages may contain either structured dictionaries or natural‑language
        strings.  Parsing is delegated to the communication layer when
        necessary.  Only assignments for nodes not controlled by this
        agent are recorded.
        """
        # log and store message at orchestrator level
        super().receive(message)
        # parse structured content via comm layer
        content = message.content
        # attempt to parse structured mapping
        structured = self.comm_layer.parse_content(message.sender, self.name, content)
        if isinstance(structured, dict):
            # the message contained a dictionary of assignments; update neighbour assignments
            for node, val in structured.items():
                if node not in self.nodes:
                    self.neighbour_assignments[node] = val
                    self.log(f"Updated neighbour assignment: {node} -> {val}")
            # forward the mapping to the internal tool via a Message object
            try:
                self.tool.receive(Message(message.sender, message.recipient, structured))
            except Exception:
                pass
        else:
            # the content is a free‑form message (string).  Record it for later inclusion
            # in the LLM prompt and do not forward it to the algorithmic tool.
            if isinstance(content, str):
                self.neighbour_messages.append((message.sender, content))
                self.log(f"Stored free‑form message from {message.sender}: {content}")

    def _evaluate_best_assignment(self) -> Dict[str, Any]:
        """Compute the best assignment for local nodes without committing to it.

        The method enumerates all possible assignments over the local
        domain and selects the one with the lowest global penalty when
        combined with the latest neighbour assignments.  The current
        assignment is used as the initial best candidate.  The method
        returns the mapping from node to colour that achieves the
        minimal penalty but does not update any internal state.
        """
        # start with current assignments
        best_assignment = dict(self.assignments)
        best_penalty = self.evaluate_candidate(best_assignment)
        # iterate over cartesian product of domain values
        for combo in itertools.product(self.domain, repeat=len(self.nodes)):
            candidate = {node: val for node, val in zip(self.nodes, combo)}
            penalty = self.evaluate_candidate(candidate)
            if penalty < best_penalty:
                best_assignment = candidate
                best_penalty = penalty
        return best_assignment

    def step(self) -> None:
        """Perform one iteration under LLM control.

        At each iteration the agent summarises its current assignments,
        computes the algorithm's recommended best assignment and prompts
        the LLM for instructions.  The LLM may instruct the agent to
        run a full algorithmic update (``run algorithm``) and/or to
        adopt a specific assignment for one or more local nodes.  If
        the LLM is unavailable, the agent defaults to the algorithm's
        recommended assignment.  After deciding on assignments the
        agent sends a natural‑language summary (including a mapping
        string for parsing) to all neighbouring agents.
        """
        # ensure we have an initial assignment (already handled in __init__)
        # compute algorithm's recommended assignment without updating the tool
        algorithm_suggestion = self._evaluate_best_assignment()
        # build prompt summarising current state
        current_assign = ", ".join(f"{n}={c}" for n, c in self.assignments.items())
        suggested_assign = ", ".join(f"{n}={c}" for n, c in algorithm_suggestion.items())
        domain_str = ", ".join(str(x) for x in self.domain)
        # compute current penalty for reporting
        current_penalty = self.evaluate_candidate(self.assignments)
        # collate recent free‑form messages from neighbours (limit to last 3 for brevity)
        recent_msgs = self.neighbour_messages[-3:] if self.neighbour_messages else []
        msgs_str = "".join([f"From {snd}: {txt}\n" for snd, txt in recent_msgs])
        # build natural language prompt; include neighbour messages if any
        prompt = (
            f"You are controlling nodes {self.nodes} for agent {self.name} in a graph colouring task. "
            f"Your current assignment is: {current_assign} (penalty {current_penalty:.3f}). "
            f"The algorithm recommends the assignment: {suggested_assign}. "
            f"Decide whether to run the algorithm step (reply with 'run algorithm' if needed) "
            f"and which colours to choose for your nodes from the domain {{ {domain_str} }}. "
            f"If you specify assignments, use the format 'node1=colour1,node2=colour2,...'. "
            f"\n"
        )
        if msgs_str:
            prompt += f"Recent messages from neighbours:\n{msgs_str}"
        # query the LLM if available
        decision: Optional[str] = None
        if hasattr(self.comm_layer, "_call_openai"):
            try:
                decision = self.comm_layer._call_openai(prompt, max_tokens=120)
            except Exception:
                decision = None
        run_algorithm = False
        chosen_assignments: Dict[str, Any] = {}
        if decision:
            low = decision.lower()
            if "run" in low and "algorithm" in low:
                run_algorithm = True
            # parse assignments specified in the response.  Accept patterns like
            # "1=red,2=green" or "assign 1 red, 2 green".  Use a simple regex.
            import re
            pairs = re.findall(r"(\w+)\s*=\s*([a-zA-Z]+)", decision)
            for node, val in pairs:
                # ensure node is one of our local nodes and val is in domain
                if node in self.nodes and val in self.domain:
                    chosen_assignments[node] = val
            self.log(f"LLM decision: {decision}")
        else:
            self.log("No LLM decision available; falling back to algorithm suggestion")
        # decide whether to run the algorithmic tool
        if run_algorithm:
            # ensure tool sees latest neighbour assignments
            self.tool.neighbour_assignments = dict(self.neighbour_assignments)
            self.tool.step()
            # update agent assignments from the tool
            self.assignments = dict(self.tool.assignments)
        # apply any assignment overrides from the LLM
        if chosen_assignments:
            for node, val in chosen_assignments.items():
                self.assignments[node] = val
            # keep tool in sync
            self.tool.assignments = dict(self.assignments)
        else:
            # if no overrides and we did not run the algorithm, adopt the suggestion
            if not run_algorithm:
                self.assignments = dict(algorithm_suggestion)
                self.tool.assignments = dict(self.assignments)
        # after assignments are updated, evaluate penalty for reporting
        final_penalty = self.evaluate_candidate(self.assignments)
        # determine neighbouring owners to send the updated assignments
        recipients: set[str] = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    owner = self.owners.get(nbr)
                    if owner and owner != self.name:
                        recipients.add(owner)
        # craft a natural-language explanation for neighbours
        explanation_parts: List[str] = []
        if run_algorithm:
            explanation_parts.append("I ran the algorithm step.")
        else:
            explanation_parts.append("I skipped the algorithm step.")
        if chosen_assignments:
            overrides = ", ".join(f"{n}={v}" for n, v in chosen_assignments.items())
            explanation_parts.append(f"I overrode the suggestion for: {overrides}.")
        # mention neighbour messages if any
        if self.neighbour_messages:
            # summarise up to the last two messages for brevity
            msgs = self.neighbour_messages[-2:]
            msgs_str = "; ".join(f"{snd} said: '{txt}'" for snd, txt in msgs)
            explanation_parts.append(f"I considered your messages: {msgs_str}.")
        # mention the final assignment in prose
        assignment_str = ", ".join(f"{node}={val}" for node, val in self.assignments.items())
        explanation_parts.append(f"My current assignment is {assignment_str} (penalty {final_penalty:.3f}).")
        explanation = " ".join(explanation_parts)
        # send the explanation and the structured assignment to each neighbour
        for recipient in recipients:
            # send explanation as free‑form message
            try:
                explanation_msg = self.comm_layer.format_content(self.name, recipient, explanation)
            except Exception:
                explanation_msg = explanation
            self.send(recipient, explanation_msg)
            # send structured assignment mapping with [mapping] tag for parsing
            try:
                mapping_msg = self.comm_layer.format_content(self.name, recipient, dict(self.assignments))
            except Exception:
                mapping_msg = dict(self.assignments)
            self.send(recipient, mapping_msg)