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
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .base_agent import BaseAgent, Message
from .multi_node_agent import MultiNodeAgent
from .max_sum_agent import MaxSumAgent
from comm.communication_layer import BaseCommLayer, PassThroughCommLayer

if TYPE_CHECKING:
    from ui.human_turn_ui import HumanTurnUI


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
        ui: Optional["HumanTurnUI"] = None,
        send_assignments: bool = False,
    ) -> None:
        super().__init__(name=name, problem=problem, comm_layer=comm_layer, initial_value=None)
        # store node ownership info
        self.nodes: List[str] = list(local_nodes)
        self.owners: Dict[str, str] = dict(owners)
        self.auto_response = auto_response
        self.ui = ui
        # If True, the human's current assignments are sent as a structured message.
        # For the main study we keep this False to preserve partial observability:
        # agents should not directly observe the human's internal state unless the
        # human chooses to describe it in text.
        self.send_assignments = bool(send_assignments)
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
        # Store messages for UI display (and optionally print for CLI runs).
        if not hasattr(self, "inbox"):
            self.inbox = []  # type: ignore[attr-defined]
        self.inbox.append((message.sender, message.content))  # type: ignore[attr-defined]
        if self.ui is None:
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
        # If a GUI is provided, use it and avoid any CLI prompts.
        if self.ui is not None:
            # Build a 
            iteration = getattr(self.problem, "iteration", 0)
            # Determine neighbouring owners (recipients) and compute a visible subgraph:
            # own nodes + boundary neighbours.
            recipients: set[str] = set()
            for node in self.nodes:
                for nbr in self.problem.get_neighbors(node):
                    if nbr not in self.nodes:
                        owner = self.owners.get(nbr)
                        if owner and owner != self.name:
                            recipients.add(owner)

            visible_nodes = set(self.nodes)
            for node in self.nodes:
                for nbr in self.problem.get_neighbors(node):
                    visible_nodes.add(nbr)

            visible_edges = set()
            for u in visible_nodes:
                for v in self.problem.get_neighbors(u):
                    if v in visible_nodes and u != v:
                        visible_edges.add(tuple(sorted((u, v))))

            # Debug helper: visible graph for any owner (cluster + 1-hop boundary).
            # This is used by the experimenter debug window.
            def get_visible_graph_for(owner: str):
                local = [n for n, o in self.owners.items() if o == owner]
                vis = set(local)
                for n in list(local):
                    for nbr in self.problem.get_neighbors(n):
                        vis.add(nbr)
                e = set()
                for u2 in vis:
                    for v2 in self.problem.get_neighbors(u2):
                        if v2 in vis and u2 != v2:
                            e.add(tuple(sorted((u2, v2))))
                return (sorted(vis), sorted(e))

            inbox = getattr(self, "inbox", [])

            # Determine neighbour cluster satisfaction (for UI indicator)
            agent_sat = None
            try:
                # Choose the first non-human cluster as the "agent" counterpart
                for a in getattr(self.problem, "debug_agents", []) or []:
                    if getattr(a, "name", None) != self.name:
                        agent_sat = bool(getattr(a, "satisfied", False))
                        break
            except Exception:
                agent_sat = None
            # RB UI mode is enabled only for the pure RB condition (not LLM_RB).
            rb_mode = bool(getattr(self, "message_type", "").lower() == "rule_based")
            rb_boundary_nodes_by_neigh: Dict[str, List[str]] = {}
            if rb_mode:
                # For each neighbour owner, list the human boundary nodes connected to that neighbour.
                human_set = set(self.nodes)
                for neigh in sorted(recipients):
                    bn = set()
                    for (u, v) in visible_edges:
                        if u in human_set and self.owners.get(v) == neigh:
                            bn.add(u)
                        elif v in human_set and self.owners.get(u) == neigh:
                            bn.add(v)
                    rb_boundary_nodes_by_neigh[neigh] = sorted(bn)
            res = self.ui.get_turn(
                nodes=list(self.nodes),
                domain=list(self.domain),
                current_assignments=dict(self.assignments),
                iteration=iteration,
                neighbour_owners=sorted(recipients),
                visible_graph=(sorted(visible_nodes), sorted(visible_edges)),
                owners=dict(self.owners),
                incoming_messages=list(inbox),
                agent_satisfied=agent_sat,
                debug_agents=getattr(self.problem, "debug_agents", None),
                get_visible_graph_fn=get_visible_graph_for,
                rb_mode=rb_mode,
                rb_boundary_nodes_by_neigh=rb_boundary_nodes_by_neigh,
            )
            # clear inbox once shown
            self.inbox = []  # type: ignore[attr-defined]

            self.assignments = dict(res.assignments)
            messages_by_neigh = getattr(res, "messages_by_neighbour", {})
            # record participant satisfaction (soft convergence)
            self.satisfied = bool(getattr(res, "human_satisfied", False))
            self.log(f"Human satisfaction: {self.satisfied}")
        else:
            # ---- CLI path ----
            print(f"\n[{self.name}] You control nodes {self.nodes}.")
            print(f"Current assignments: {self.assignments}")
            if self.neighbour_assignments:
                print(f"Known neighbour assignments: {self.neighbour_assignments}")
            else:
                print("No neighbour assignments known yet.")
            print(f"Available colours: {', '.join(self.domain)}")
            print("Enter new assignments for your nodes as comma‑separated pairs (e.g. 'h1=red,h2=green').")
            print("Press Enter to keep current assignments.")
            inp = self.prompt(f"[{self.name}] New assignments: ").strip()
            if inp:
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
                if updates:
                    for node, val in updates.items():
                        self.assignments[node] = val
                    self.log(f"Human updated assignments: {updates}")
                msg = self.prompt(f"[{self.name}] Enter a message to neighbours (optional): ").strip()
                if not msg:
                    msg = f"My assignments: {self.assignments}"
            else:
                msg = f"My assignments: {self.assignments}"
        # Determine neighbouring owners and send per-neighbour messages.
        recipients: set[str] = set()
        for node in self.nodes:
            for nbr in self.problem.get_neighbors(node):
                if nbr not in self.nodes:
                    owner = self.owners.get(nbr)
                    if owner and owner != self.name:
                        recipients.add(owner)

        for recipient in sorted(recipients):
            # When running with the GUI, we support a different outgoing message per neighbour.
            # In CLI mode, `msg` is a single string broadcast to all recipients.
            out_text = ""
            if self.ui is not None:
                out_text = (messages_by_neigh.get(recipient) or "").strip()
            else:
                out_text = msg.strip()

            # Send free-form message only if provided.
            if out_text:
                formatted_msg = self.comm_layer.format_content(self.name, recipient, out_text)
                self.log(f"Human message to {recipient}: {formatted_msg}")
                self.send(recipient, formatted_msg)

            # Optionally send assignments as a structured message.
            # NOTE: For the main study protocol we keep this OFF so that the
            # agent cannot see the human's internal state unless the human
            # communicates it explicitly via text.
            if self.send_assignments:
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