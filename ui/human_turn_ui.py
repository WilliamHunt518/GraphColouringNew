"""Tkinter UI for a human-controlled cluster.

Design goals (matching the study protocol):

* The human sets colours by **clicking nodes on the graph** (cycling
  through the domain), not via dropdowns.
* Neighbour assignments are **not shown directly**. Only messages are.
* Messages are presented **per neighbour** (incoming + outgoing boxes).
* UI elements (fonts, node sizes) are scaled up for in-person use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class HumanTurnResult:
    assignments: Dict[str, Any]
    messages_by_neighbour: Dict[str, str]
    human_satisfied: bool = False


class HumanTurnUI:
    """Blocking UI that returns the human's choices for the current iteration."""

    def __init__(self, title: str = "Human Turn") -> None:
        self.title = title
        # Keep a stable layout across turns.
        self._cached_pos: Dict[str, Tuple[float, float]] | None = None

        # Persistent window state (created on first use)
        self._root = None
        self._submit_var = None
        self._result: HumanTurnResult | None = None

        # Widgets we update each turn
        self._header_lbl = None
        self._canvas = None
        self._graph_frame = None
        self._msg_frame = None

        # Per-neighbour UI state
        self._incoming_hist: Dict[str, List[str]] = {}
        self._incoming_idx: Dict[str, int] = {}
        self._incoming_box = {}
        self._incoming_page_lbl: Dict[str, Any] = {}
        self._outgoing_box = {}
        self._last_outgoing: Dict[str, str] = {}

        # Current turn state
        self._human_nodes: List[str] = []
        self._domain: List[Any] = []
        self._assignments: Dict[str, Any] = {}
        self._vis_nodes: List[str] = []
        self._vis_edges: List[Tuple[str, str]] = []
        self._owners: Dict[str, str] = {}
        # Last reported assignments from neighbours (node -> colour).
        # These are only updated when a neighbour explicitly reports them in a message.
        self._reported_assignments: Dict[str, Any] = {}
        self._pos: Dict[str, Tuple[float, float]] = {}
        self._node_hit: Dict[str, Tuple[float, float, float]] = {}

        # Experimenter debug window (optional)
        self._debug_win = None

    def get_turn(
        self,
        *,
        nodes: List[str],
        domain: List[Any],
        current_assignments: Dict[str, Any],
        iteration: int,
        neighbour_owners: List[str],
        visible_graph: Tuple[List[str], List[Tuple[str, str]]] | None = None,
        owners: Dict[str, str] | None = None,
        incoming_messages: List[Tuple[str, Any]] | None = None,
        agent_satisfied: bool | None = None,
        debug_agents: List[Any] | None = None,
        get_visible_graph_fn: Any | None = None,
    ) -> HumanTurnResult:
        """Show (or update) a persistent window, block until Submit, and return choices."""

        import tkinter as tk
        from tkinter import ttk

        # -------- styling / scaling --------
        FONT_BODY = ("Arial", 15)
        FONT_HEADER = ("Arial", 22, "bold")
        FONT_SECTION = ("Arial", 15, "bold")
        FONT_SMALL = ("Arial", 13)

        # Create window once (persistent)
        if self._root is None:
            root = tk.Tk()
            root.geometry("1280x860")
            root.title(self.title)
            self._root = root
            self._submit_var = tk.BooleanVar(value=False)

            # Header
            self._header_lbl = ttk.Label(root, text="", font=FONT_HEADER)
            self._header_lbl.pack(pady=12)

            # Small toolbar (experimenter controls)
            toolbar = ttk.Frame(root)
            toolbar.pack(fill="x", padx=16)

            def on_debug() -> None:
                # Lazily create the debug window when requested.
                if debug_agents is None or get_visible_graph_fn is None:
                    return
                if self._debug_win is None:
                    from ui.debug_window import DebugWindow

                    self._debug_win = DebugWindow(
                        self._root,
                        agents=debug_agents,
                        owners=dict(self._owners),
                        get_visible_graph_fn=get_visible_graph_fn,
                    )
                else:
                    try:
                        self._debug_win.refresh()
                    except Exception:
                        pass

            ttk.Button(toolbar, text="Open debug", command=on_debug).pack(side="right")

            # Top layout
            top = ttk.Frame(root)
            top.pack(fill="both", expand=True, padx=16, pady=10)

            self._graph_frame = ttk.LabelFrame(top, text="Your observable graph")
            self._graph_frame.pack(side="left", fill="both", expand=True, padx=(0, 12))

            self._msg_frame = ttk.Frame(top)
            self._msg_frame.pack(side="left", fill="y", expand=False)

            ttk.Label(self._msg_frame, text="Messages", font=FONT_SECTION).pack(anchor="w", pady=(0, 8))

            # Graph canvas
            self._canvas = tk.Canvas(
                self._graph_frame,
                width=860,
                height=640,
                background="white",
                highlightthickness=0,
            )
            self._canvas.pack(fill="both", expand=False, padx=12, pady=12)

            # Submit button
            def on_submit() -> None:
                # Collect outgoing text per neighbour
                messages_out: Dict[str, str] = {}
                for neigh, box in self._outgoing_box.items():
                    messages_out[neigh] = box.get("1.0", "end").strip()
                    # remember last message for prefill next time
                    if messages_out[neigh].strip():
                        self._last_outgoing[neigh] = messages_out[neigh].strip()

                self._result = HumanTurnResult(
                    assignments=dict(self._assignments),
                    messages_by_neighbour=messages_out,
                    human_satisfied=bool(getattr(self, "_human_done_var", None).get()) if getattr(self, "_human_done_var", None) is not None else False,
                )
                if self._submit_var is not None:
                    self._submit_var.set(True)

            btn = ttk.Button(root, text="Submit turn", command=on_submit)
            btn.pack(pady=14)

            # Satisfaction controls
            sat = ttk.Frame(root)
            sat.pack(fill="x", padx=16, pady=(0, 10))

            self._human_done_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                sat,
                text="I'm satisfied / done",
                variable=self._human_done_var,
            ).pack(side="left")

            # Agent satisfaction indicator (read-only)
            self._agent_done_var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(
                sat,
                text="Agent satisfied",
                variable=self._agent_done_var,
            )
            try:
                cb.state(["disabled"])  # type: ignore[attr-defined]
            except Exception:
                pass
            cb.pack(side="left", padx=(24, 0))

            # Debug button (experimenter)
            def on_debug() -> None:
                try:
                    from ui.debug_window import DebugWindow

                    if self._debug_win is not None:
                        # already open
                        self._debug_win.refresh()
                        return
                    if debug_agents is None or get_visible_graph_fn is None:
                        return
                    self._debug_win = DebugWindow(
                        root,
                        agents=debug_agents,
                        owners=self._owners,
                        get_visible_graph_fn=get_visible_graph_fn,
                    )
                except Exception:
                    return

            ttk.Button(root, text="Open debug (experimenter)", command=on_debug).pack(pady=(0, 8))

            # Clicking nodes cycles colours
            def on_click(event: tk.Event) -> None:
                x, y = float(event.x), float(event.y)
                for n, (cx, cy, r) in self._node_hit.items():
                    if n not in self._human_nodes:
                        continue
                    if (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2:
                        self._cycle_colour(n)
                        self._redraw(FONT_BODY, FONT_SMALL)
                        break

            self._canvas.bind("<Button-1>", on_click)

        # Update turn state
        self._human_nodes = list(nodes)
        self._domain = list(domain)
        self._assignments = dict(current_assignments)
        self._owners = dict(owners or {})
        self._vis_nodes, self._vis_edges = visible_graph if visible_graph is not None else ([], [])

        # Participant-facing observability rule:
        # - The human can see neighbour nodes that are adjacent to their local nodes.
        # - The human must NOT see edges *between* neighbour nodes (i.e., neighbour-internal topology).
        #   This prevents learning extra structure beyond what boundary observations imply.
        if self._vis_edges:
            human_set = set(self._human_nodes)
            self._vis_edges = [
                (u, v)
                for (u, v) in self._vis_edges
                if (u in human_set) or (v in human_set)
            ]

        # Update title + header
        self._root.title(f"{self.title} — Iteration {iteration}")
        if self._header_lbl is not None:
            self._header_lbl.configure(text=f"Iteration {iteration}: click your nodes to cycle colours")

        # Update agent satisfaction indicator (experimenter-visible but participant-safe)
        try:
            if agent_satisfied is not None and getattr(self, "_agent_done_var", None) is not None:
                self._agent_done_var.set(bool(agent_satisfied))  # type: ignore[attr-defined]
        except Exception:
            pass

        # Update message history and rebuild message panels if neighbour set changed
        self._update_message_panels(
            neighbour_owners=neighbour_owners,
            incoming_messages=incoming_messages or [],
            font_body=FONT_BODY,
            font_small=FONT_SMALL,
        )

        # Update layout
        self._compute_layout()
        self._redraw(FONT_BODY, FONT_SMALL)

        # If the experimenter debug window is open, refresh it each turn.
        if self._debug_win is not None:
            try:
                self._debug_win.refresh()
            except Exception:
                pass

        # refresh debug window if open
        try:
            if self._debug_win is not None:
                self._debug_win.refresh()
        except Exception:
            pass

        # Block until submit
        if self._submit_var is not None:
            self._submit_var.set(False)
            self._root.wait_variable(self._submit_var)
        res = self._result
        if res is None:
            return HumanTurnResult(assignments=dict(current_assignments), messages_by_neighbour={n: "" for n in neighbour_owners})
        return res

    # -------- internal helpers --------

    def _cycle_colour(self, node: str) -> None:
        if node not in self._human_nodes:
            return
        current = self._assignments.get(node, self._domain[0] if self._domain else None)
        dom = list(self._domain)
        if not dom:
            return
        try:
            idx = dom.index(current)
        except ValueError:
            idx = 0
        self._assignments[node] = dom[(idx + 1) % len(dom)]

    def _compute_layout(self) -> None:
        # Layout is computed for the visible nodes/edges and cached.
        self._pos = {}
        if not self._vis_nodes:
            return
        try:
            import networkx as nx

            G = nx.Graph()
            G.add_nodes_from(self._vis_nodes)
            G.add_edges_from(self._vis_edges)
            if self._cached_pos is None or set(self._cached_pos.keys()) != set(self._vis_nodes):
                self._cached_pos = nx.spring_layout(G, seed=42)
            self._pos = dict(self._cached_pos)
        except Exception:
            for i, n in enumerate(self._vis_nodes):
                self._pos[n] = (float(i), 0.0)

    def _redraw(self, font_body, font_small) -> None:
        if self._canvas is None:
            return
        canvas = self._canvas
        canvas.delete("all")
        self._node_hit.clear()

        CANVAS_W = int(canvas.winfo_reqwidth())
        CANVAS_H = int(canvas.winfo_reqheight())
        NODE_R = 30

        def to_canvas(p: Tuple[float, float]) -> Tuple[float, float]:
            x, y = p
            x = (x + 1.2) / 2.4
            y = (y + 1.2) / 2.4
            cx = 60 + x * (CANVAS_W - 120)
            cy = 60 + y * (CANVAS_H - 120)
            return cx, cy

        def fill_for(n: str) -> str:
            if n in self._human_nodes:
                c = str(self._assignments.get(n, self._domain[0] if self._domain else ""))
                return c if c in {"red", "green", "blue", "orange", "yellow", "purple"} else "lightgrey"
            # neighbours: show last reported colour if available, else unknown
            c = str(self._reported_assignments.get(n, ""))
            if c in {"red", "green", "blue", "orange", "yellow", "purple"}:
                return c
            return "lightgrey"

        # edges
        for u, v in self._vis_edges:
            if u not in self._pos or v not in self._pos:
                continue
            x1, y1 = to_canvas(self._pos[u])
            x2, y2 = to_canvas(self._pos[v])
            canvas.create_line(x1, y1, x2, y2, width=3)

        # nodes
        for n in self._vis_nodes:
            if n not in self._pos:
                continue
            cx, cy = to_canvas(self._pos[n])
            item = canvas.create_oval(
                cx - NODE_R,
                cy - NODE_R,
                cx + NODE_R,
                cy + NODE_R,
                fill=fill_for(n),
                outline="black",
                width=4 if n in self._human_nodes else 3,
            )
            self._node_hit[n] = (cx, cy, NODE_R)
            owner = self._owners.get(n, "")
            label = f"{n}\n({owner})" if owner else n
            canvas.create_text(cx, cy + NODE_R + 22, text=label, font=font_small)

        canvas.create_text(14, 14, anchor="nw", text="Click your nodes to cycle colours", font=font_small)

    def _update_message_panels(self, *, neighbour_owners, incoming_messages, font_body, font_small) -> None:
        """Maintain per-neighbour inbox history + outgoing boxes.

        Layout: for each neighbour, show (a) inbox with prev/next, (b) outgoing box.
        Prefill outgoing with last sent message (grey placeholder).
        """

        import tkinter as tk
        from tkinter import ttk

        if self._msg_frame is None:
            return

        def _display_text(content: Any) -> str:
            """Render an incoming message for the human.

            The comm layer appends a machine-readable mapping tag like:
            "... [mapping: Mapping from A to B -> ...]".
            Humans should not see that internal payload.
            """
            text = str(content)
            # Extract neighbour-reported assignments, if present.
            if "[report:" in text:
                head, tail = text.split("[report:", 1)
                report_part = tail
                if "]" in report_part:
                    report_str = report_part.split("]", 1)[0].strip()
                    try:
                        import ast

                        report_obj = ast.literal_eval(report_str)
                        if isinstance(report_obj, dict):
                            # Update last reported assignments (node -> colour)
                            for k, v in report_obj.items():
                                self._reported_assignments[str(k)] = v
                    except Exception:
                        pass
                # Remove report tag from what the human sees
                text = head + report_part.split("]", 1)[1] if "]" in report_part else head

            # Hide machine-readable mapping payload from the participant.
            if "[mapping:" in text:
                text = text.split("[mapping:", 1)[0].rstrip()
            return text.strip()

        # Group incoming messages by sender (HUMAN-FACING ONLY)
        incoming_by_sender: Dict[str, List[str]] = {}
        for sender, content in incoming_messages:
            incoming_by_sender.setdefault(str(sender), []).append(_display_text(content))

        # If the set of neighbours changed, rebuild panels completely.
        if set(neighbour_owners) != set(self._incoming_box.keys()):
            for child in list(self._msg_frame.winfo_children()):
                # keep the first "Messages" label (index 0)
                if isinstance(child, ttk.Label):
                    continue
                child.destroy()
            self._incoming_box.clear()
            self._outgoing_box.clear()

        for neigh in neighbour_owners:
            # update history
            hist = self._incoming_hist.setdefault(neigh, [])
            new_msgs = incoming_by_sender.get(neigh, [])
            if new_msgs:
                hist.extend(new_msgs)
            if neigh not in self._incoming_idx:
                self._incoming_idx[neigh] = max(0, len(hist) - 1)
            else:
                # jump to latest when new messages arrive
                if new_msgs:
                    self._incoming_idx[neigh] = len(hist) - 1

            # create panel if missing
            if neigh not in self._incoming_box:
                panel = ttk.LabelFrame(self._msg_frame, text=f"Neighbour: {neigh}")
                panel.pack(fill="x", expand=False, padx=6, pady=8)

                # inbox header row with nav
                row = ttk.Frame(panel)
                row.pack(fill="x", padx=8, pady=(8, 2))
                ttk.Label(row, text="Incoming", font=font_body).pack(side="left")

                # Page indicator (e.g., "2/5")
                page_lbl = ttk.Label(row, text="0/0", font=font_small)
                page_lbl.pack(side="left", padx=(10, 0))
                self._incoming_page_lbl[neigh] = page_lbl

                def mk_nav(delta: int, who: str):
                    def _go():
                        idx = self._incoming_idx.get(who, 0)
                        idx = max(0, min(idx + delta, len(self._incoming_hist.get(who, [])) - 1))
                        self._incoming_idx[who] = idx
                        self._refresh_inbox(who)
                    return _go

                # Buttons: ◀ = previous (older), ▶ = next (newer)
                # Pack left-to-right to avoid Tk right-pack reversing visual order.
                ttk.Button(row, text="◀", width=3, command=mk_nav(-1, neigh)).pack(side="left", padx=(10, 2))
                ttk.Button(row, text="▶", width=3, command=mk_nav(+1, neigh)).pack(side="left")

                inbox = tk.Text(panel, height=6, wrap="word", font=font_small)
                inbox.pack(fill="x", expand=False, padx=8, pady=(0, 8))
                inbox.configure(state="disabled")
                self._incoming_box[neigh] = inbox

                ttk.Label(panel, text="Your message to this neighbour", font=font_body).pack(anchor="w", padx=8)
                out = tk.Text(panel, height=4, wrap="word", font=font_small)
                out.pack(fill="x", expand=False, padx=8, pady=(2, 10))
                self._outgoing_box[neigh] = out

                # prefill placeholder = last message
                self._set_outgoing_placeholder(neigh)
            else:
                # existing: update placeholder if empty
                self._set_outgoing_placeholder(neigh)

            # refresh inbox display
            self._refresh_inbox(neigh)

    def _refresh_inbox(self, neigh: str) -> None:
        box = self._incoming_box.get(neigh)
        if box is None:
            return
        hist = self._incoming_hist.get(neigh, [])
        if not hist:
            text = "(none)"
            page_text = "0/0"
        else:
            idx = self._incoming_idx.get(neigh, len(hist) - 1)
            idx = max(0, min(idx, len(hist) - 1))
            self._incoming_idx[neigh] = idx
            text = hist[idx]
            page_text = f"{idx + 1}/{len(hist)}"
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("end", text)
        box.configure(state="disabled")

        # Update page indicator if present
        lbl = self._incoming_page_lbl.get(neigh)
        if lbl is not None:
            try:
                lbl.configure(text=page_text)
            except Exception:
                pass

    def _set_outgoing_placeholder(self, neigh: str) -> None:
        """Prefill last message in grey if box empty; clears on focus."""
        box = self._outgoing_box.get(neigh)
        if box is None:
            return
        current = box.get("1.0", "end").strip()
        if current:
            return
        last = self._last_outgoing.get(neigh, "")
        if not last:
            return
        # Insert grey placeholder
        box.delete("1.0", "end")
        box.insert("1.0", last)
        try:
            box.tag_add("placeholder", "1.0", "end")
            box.tag_configure("placeholder", foreground="#888888")
        except Exception:
            pass

        def _clear_placeholder(_evt=None):
            # only clear if it's still the placeholder
            txt = box.get("1.0", "end").strip()
            if txt == last:
                box.delete("1.0", "end")
                try:
                    box.tag_remove("placeholder", "1.0", "end")
                except Exception:
                    pass

        # Bind once per box
        box.bind("<FocusIn>", _clear_placeholder)
