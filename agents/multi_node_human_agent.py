"""Multi‑node human agents for DCOP problems.

This module defines interactive agents for use in multi‑node mode.
Two classes are provided:

* :class:`MultiNodeHumanAgent` implements the 2A mode where a
  human operator controls all nodes of a given owner.  On each
  iteration, the agent displays its current assignments and the
  latest neighbour assignments, prompts the human to choose new
  colour assignments for each local node, and then optionally
  sends a free‑form message to neighbouring agents.  When run in
  non‑interactive contexts (e.g. automated tests), an
  ``auto_response`` callback may be supplied to return the
  operator’s inputs programmatically.

* :class:`MultiNodeHumanOrchestrator` implements the 2B mode in
  which a human directs an internal algorithmic tool.  The agent
  enumerates candidate assignments for its local nodes and
  proposes the best one based on the global penalty.  The human
  may accept the suggestion, choose a different assignment, or
  perform multiple algorithmic steps via a simple menu.  Messages
  are still routed through the communication layer, allowing
  integration with LLM or heuristic summaries.

These classes are intentionally verbose in their prompts to help
humans understand the state of the system and how to interact with
it.  They can also operate in non‑interactive mode by providing
an ``auto_response`` function that accepts a prompt and returns
the operator’s response.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, Dict, List, Optional

from .base_agent import BaseAgent, Message
from .multi_node_agent import MultiNodeAgent
from .max_sum_agent import MaxSumAgent
from comm.communication_layer import BaseCommLayer, PassThroughCommLayer


class MultiNodeHumanAgent(BaseAgent):
    """Multi‑node agent controlled entirely by a human (2A).

    On each iteration the agent displays its current assignments
    for the local nodes and any known assignments for neighbouring
    nodes.  The human is prompted to provide a new assignment for
    each node in the form ``node=value``.  If left blank, the
    existing assignment is kept.  After updating assignments, the
    agent prompts for an optional message to neighbours.  The
    message is passed through the communication layer before being
    sent.  Incoming messages are displayed to the human and stored
    for neighbour assignment tracking.

    Parameters
    ----------
    name : str
        Name of the agent (owner).  This label is used in logs and
        message routing.
    problem : GraphColoring
        The colouring problem definition shared by all agents.
    comm_layer : BaseCommLayer
        Communication layer used to format outgoing messages and
        parse incoming ones.
    local_nodes : list of str
        Identifiers of the nodes controlled by this agent.
    owners : dict
        Mapping from node identifiers to owner names.  Used to route
        messages to the correct neighbouring owner.
    initial_assignments : dict, optional
        Initial colour assignments for local nodes.  Missing nodes
        are initialised randomly from the domain.
    auto_response : Callable[[str], str], optional
        Function returning a response for a given prompt.  Used in
        non‑interactive tests to bypass ``input()``.
    """

    def __init__(
        self,
        name: str,
        problem: Any,
        comm_layer: BaseCommLayer,
        local_nodes: List[str],
        owners: Dict[str, str],
        initial_assignments: Optional[Dict[str, Any]] = None,
        auto_response: Optional[Callable[[str], str]] = None,
    ) -> None:
        super().__init__(name=name, problem=problem, comm_layer=comm_layer, initial_value=None)
        # store node ownership info
        self.nodes: List[str] = list(local_nodes)
        self.owners: Dict[str, str] = dict(owners)
        self.auto_response = auto_response
        # current assignments for local nodes
        self.assignments: Dict[str, Any] = {}
        # assignments received from neighbouring owners
        self.neighbour_assignments: Dict[str, Any] = {}
        # initialise assignments
        import random
        for node in self.nodes:
            if initial_assignments and node in initial_assignments:
                self.assignments[node] = initial_assignments[node]
            else:
                self.assignments[node] = random.choice(self.domain)
        self.log(f"Initial multi‑node assignments: {self.assignments}")

    # override assignment property for logging compatibility
    @property
    def assignment(self) -> Any:
        return str(self.assignments)

    @assignment.setter
    def assignment(self, value: Any) -> None:
        # assignments are managed per-node; ignore direct assignment
        if hasattr(self, "logs"):
            self.log(f"Ignoring assignment setter for multi‑node human agent: {value}")

    def receive(self, message: Message) -> None:
        """Handle an incoming message.

        Displays the message to the human and updates neighbour
        assignments for nodes not controlled by this agent.  Parsing is
        delegated to the communication layer; non‑dict messages are
        ignored for the purpose of neighbour assignments.
        """
        super().receive(message)
        print(f"[{self.name}] Received from {message.sender}: {message.content}")
        content = message.content
        # attempt to parse structured content via comm layer
        structured = self.comm_layer.parse_content(message.sender, self.name, content)
        if isinstance(structured, dict):
            for node, val in structured.items():
                if node not in self.nodes:
                    self.neighbour_assignments[node] = val
                    self.log(f"Updated neighbour assignment: {node} -> {val}")

    def prompt(self, prompt: str) -> str:
        """Prompt the human or auto_response for input."""
        if self.auto_response is not None:
            return self.auto_response(prompt)
        try:
            return input(prompt)
        except EOFError:
            # non‑interactive environment; return empty string
            return ""

    def step(self) -> None:
        """Perform an interactive step for the human agent.

        The agent displays current assignments and neighbour assignments,
        prompts the user to update assignments, and optionally sends
        a message to neighbours.
        """
        # display current assignments
        print(f"\n[{self.name}] You control nodes {self.nodes}.")
        print(f"Current assignments: {self.assignments}")
        if self.neighbour_assignments:
            print(f"Known neighbour assignments: {self.neighbour_assignments}")
        else:
            print("No neighbour assignments known yet.")
        print(f"Available colours: {', '.join(self.domain)}")
        print("Enter new assignments for your nodes as comma‑separated pairs (e.g. '1=red,2=green').")
        print("Press Enter to keep current assignments.")
        inp = self.prompt(f"[{self.name}] New assignments: ").strip()
        if inp:
            # parse node=value pairs
            updates: Dict[str, Any] = {}
            for part in inp.split(','):
                part = part.strip()
                if not part:
                    continue
                if '=' not in part:
                    print(f"Ignored malformed entry '{part}'. Expected 'node=value'.")
                    continue
                node, val = part.split('=', 1)
                node = node.strip()
                val = val.strip()
                if node not in self.nodes:
                    print(f"Ignored assignment for unknown node '{node}'.")
                    continue
                if val not in self.domain:
                    print(f"Ignored invalid colour '{val}' for node '{node}'. Valid colours: {self.domain}.")
                    continue
                updates[node] = val
            # apply updates
            if updates:
                for node, val in updates.items():
                    self.assignments[node] = val
                self.log(f"Human updated assignments: {updates}")
        # prompt for message
        msg = self.prompt(f"[{self.name}] Enter a message to neighbours (optional): ").strip()
        if not msg:
            msg = f"My assignments: {self.assignments}"
        # determine neighbouring owners and send message
        recipients: set[str] = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    owner = self.owners.get(nbr)
                    if owner and owner != self.name:
                        recipients.add(owner)
        for recipient in recipients:
            # format the human message via the communication layer for display and send it as free‑form content
            # to allow LLM agents to consider human suggestions.  We include this message separately from the
            # structured assignments so that receiving agents can distinguish between the two.
            formatted_msg = self.comm_layer.format_content(self.name, recipient, msg)
            self.log(f"Human message to {recipient}: {formatted_msg}")
            # send the free‑form message first
            self.send(recipient, formatted_msg)
            # then send the assignments as a natural‑language mapping string so that neighbours know our colours.
            assignment_msg = self.comm_layer.format_content(self.name, recipient, dict(self.assignments))
            self.log(f"Sent assignment to {recipient}: {assignment_msg}")
            self.send(recipient, assignment_msg)


class MultiNodeHumanOrchestrator(MultiNodeHumanAgent):
    """Multi‑node human orchestrator agent (2B).

    This agent allows a human operator to interactively control an
    internal algorithmic tool.  The operator can run algorithm steps,
    inspect candidate assignments and penalties, accept the tool’s
    proposed assignment, or manually enter assignments.  At the end
    of each iteration the user may send a message to neighbours.
    """

    def __init__(
        self,
        name: str,
        problem: Any,
        comm_layer: BaseCommLayer,
        local_nodes: List[str],
        owners: Dict[str, str],
        initial_assignments: Optional[Dict[str, Any]] = None,
        auto_response: Optional[Callable[[str], str]] = None,
    ) -> None:
        super().__init__(
            name=name,
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=local_nodes,
            owners=owners,
            initial_assignments=initial_assignments,
            auto_response=auto_response,
        )
        # create an internal multi‑node algorithmic tool using PassThrough
        # comm layer to avoid nested LLM calls
        self.tool = MultiNodeAgent(
            name=name,
            problem=problem,
            comm_layer=PassThroughCommLayer(),
            local_nodes=local_nodes,
            owners=owners,
            initial_assignments=initial_assignments,
        )
        # sync initial assignments with tool
        self.assignments = dict(self.tool.assignments)

    def menu(self) -> None:
        print(f"\n[{self.name}] You control nodes {self.nodes}.")
        print(f"Current assignments: {self.assignments}")
        if self.neighbour_assignments:
            print(f"Known neighbour assignments: {self.neighbour_assignments}")
        else:
            print("No neighbour assignments known yet.")
        print("Choose an action:")
        print("  1. Run internal algorithm step")
        print("  2. Propose best assignment")
        print("  3. Accept proposed assignment")
        print("  4. Enter manual assignments")
        print("  5. Send message")
        print("  6. End turn")

    def step(self) -> None:
        """Interactive control for the human orchestrator in multi‑node mode."""
        while True:
            self.menu()
            choice = self.prompt(f"[{self.name}] Enter choice: ").strip()
            if choice == "1":
                # run tool step once
                self.tool.neighbour_assignments = dict(self.neighbour_assignments)
                self.tool.step()
                self.assignments = dict(self.tool.assignments)
                self.log(f"Algorithm step: new assignments {self.assignments}")
                print(f"[{self.name}] Tool updated assignments to {self.assignments}")
            elif choice == "2":
                # propose best assignment by evaluating all candidates
                # copy from tool; compute candidate assignments and penalties
                candidate_penalties: List[tuple[Dict[str, Any], float]] = []
                for combo in itertools.product(self.domain, repeat=len(self.nodes)):
                    cand = {node: val for node, val in zip(self.nodes, combo)}
                    pen = self.tool.evaluate_candidate(cand)
                    candidate_penalties.append((cand, pen))
                # find best
                best_cand, best_pen = min(candidate_penalties, key=lambda x: x[1])
                print(f"[{self.name}] Proposed assignment {best_cand} with penalty {best_pen:.3f}")
                # store suggestion for later acceptance
                self._proposed_assignment = best_cand
            elif choice == "3":
                # accept previously proposed assignment if available
                prop = getattr(self, "_proposed_assignment", None)
                if prop is None:
                    print(f"[{self.name}] No proposed assignment available. Choose option 2 first.")
                else:
                    self.assignments = dict(prop)
                    self.tool.assignments = dict(prop)
                    self.log(f"Human accepted proposed assignment {prop}")
                    print(f"[{self.name}] Accepted assignment {prop}")
                    # clear proposed assignment
                    self._proposed_assignment = None
            elif choice == "4":
                # manual assignments (reuse from base human agent)
                # display instructions and call base class update logic
                print(f"Assign colours to your nodes {self.nodes}.")
                print(f"Available colours: {', '.join(self.domain)}")
                inp = self.prompt(f"[{self.name}] Enter assignments (e.g. '1=red,2=blue'): ").strip()
                if inp:
                    updates: Dict[str, Any] = {}
                    for part in inp.split(','):
                        part = part.strip()
                        if not part or '=' not in part:
                            print(f"Ignored malformed entry '{part}'.")
                            continue
                        node, val = part.split('=', 1)
                        node = node.strip()
                        val = val.strip()
                        if node not in self.nodes:
                            print(f"Ignored assignment for unknown node '{node}'.")
                            continue
                        if val not in self.domain:
                            print(f"Ignored invalid colour '{val}' for node '{node}'.")
                            continue
                        updates[node] = val
                    if updates:
                        for node, val in updates.items():
                            self.assignments[node] = val
                            self.tool.assignments[node] = val
                        self.log(f"Human manually set assignments: {updates}")
                        print(f"[{self.name}] Updated assignments to {self.assignments}")
                else:
                    print(f"[{self.name}] No changes made.")
            elif choice == "5":
                # send message to neighbours
                msg = self.prompt(f"[{self.name}] Enter message to neighbours: ").strip()
                if not msg:
                    msg = f"My assignments: {self.assignments}"
                # determine recipients and send assignments mapping
                recipients: set[str] = set()
                for node in self.nodes:
                    for nbr in self.problem.get_neighbors(node):
                        if nbr not in self.nodes:
                            owner = self.owners.get(nbr)
                            if owner and owner != self.name:
                                recipients.add(owner)
                for recipient in recipients:
                    # format the human message via the communication layer for display
                    formatted = self.comm_layer.format_content(self.name, recipient, msg)
                    self.log(f"Human message to {recipient}: {formatted}")
                    # send the free‑form message first
                    self.send(recipient, formatted)
                    # then send the assignments as a natural‑language mapping string
                    assignment_msg = self.comm_layer.format_content(self.name, recipient, dict(self.assignments))
                    self.log(f"Sent assignment to {recipient}: {assignment_msg}")
                    self.send(recipient, assignment_msg)
                print(f"[{self.name}] Sent message to neighbours.")
            elif choice == "6" or choice == "":
                # end turn
                break
            else:
                print("Invalid choice. Please choose a number between 1 and 6.")