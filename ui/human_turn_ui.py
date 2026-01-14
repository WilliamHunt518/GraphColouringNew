"""HumanTurnUI - flat repo layout

A Tkinter UI for the human participant in clustered graph colouring with:
- per-neighbour chat panes (WhatsApp-style)
- async send/receive (agent calls in background thread)
- per-neighbour satisfaction checkbox (human) + optional agent satisfied indicator
- score HUD (top-left) and simple conflict highlighting
- debug button/window (optional) showing provided debug text

This module is designed to be tolerant of extra kwargs passed from the simulation
(e.g., debug_get_visible_graph_fn). Unknown kwargs are ignored.
"""

from __future__ import annotations

import threading
import time
import random
import math
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
import inspect
import re
import ast


@dataclass
class HumanTurnResult:
    assignments: Dict[str, Any]
    messages_by_neighbour: Dict[str, str]


class HumanTurnUI:
    def __init__(self, title: str = "Human Turn") -> None:
        self._title = title
        self._root: Optional[tk.Tk] = None

        # termination
        self.end_reason: str = ""  # set to "consensus" when all parties tick satisfied

        # state
        self._domain: List[Any] = []
        self._nodes: List[str] = []
        self._edges: List[Tuple[str, str]] = []
        self._owners: Dict[str, str] = {}
        self._assignments: Dict[str, Any] = {}
        self._neighs: List[str] = []

        # neighbour colour knowledge
        self._known_neighbour_colours: Dict[str, Any] = {}

        # chat data
        self._transcripts: Dict[str, List[str]] = {}
        self._incoming_queue: Dict[str, List[str]] = {}
        self._outgoing_box: Dict[str, tk.Text] = {}
        self._transcript_box: Dict[str, tk.Text] = {}
        self._status_var: Dict[str, tk.StringVar] = {}
        self._send_btn: Dict[str, ttk.Button] = {}
        self._human_sat: Dict[str, tk.BooleanVar] = {}
        self._agent_sat: Dict[str, tk.StringVar] = {}
        self._placeholder_active: Dict[str, bool] = {}  # Track if placeholder is shown

        # callbacks set by run_async_chat
        # Different versions of cluster_simulation.py have used different on_send signatures:
        #   on_send(neigh, msg)
        #   on_send(neigh, msg, assignments)
        self._on_send: Optional[Callable[..., Optional[str]]] = None
        self._on_colour_change: Optional[Callable[[Dict[str, Any]], None]] = None
        self._get_agent_satisfied_fn: Optional[Callable[[str], bool]] = None
        self._debug_get_text_fn: Optional[Callable[[], str]] = None
        self._debug_get_visible_graph_fn: Optional[Callable[[str], str]] = None

        # canvas
        self._canvas: Optional[tk.Canvas] = None
        self._node_pos: Dict[str, Tuple[int, int]] = {}
        self._node_items: Dict[str, int] = {}
        self._edge_items: List[Tuple[str, str, int]] = []
        self._hud_var: Optional[tk.StringVar] = None

        # debug window
        self._debug_win: Optional[tk.Toplevel] = None

        # resize debounce
        self._resize_after_id: Optional[str] = None

        # points (default)
        self._points = {"blue": 1, "green": 2, "red": 3}

        # done flag for async session
        self._done = threading.Event()

    def _ensure_root(self) -> tk.Tk:
        """Ensure a Tk root exists before creating any tk.Variable."""
        if self._root is None:
            self._root = tk.Tk()
        return self._root

    # -------------------- Public API expected by simulation --------------------

    def add_incoming(self, neigh: str, text: str) -> None:
        """Thread-safe: queue an incoming message to show in UI."""
        self._incoming_queue.setdefault(neigh, []).append(text)
        if self._root is not None:
            self._root.after(0, lambda n=neigh: self._flush_incoming(n))

    def run_async_chat(
        self,
        *,
        nodes: List[str],
        domain: List[Any],
        owners: Dict[str, str],
        current_assignments: Dict[str, Any],
        neighbour_owners: List[str],
        visible_graph: Optional[Tuple[List[str], List[Tuple[str, str]]]] = None,
        debug_agents: Optional[List[Any]] = None,
        get_visible_graph_fn: Optional[Callable[[str], Any]] = None,
        on_send: Optional[Callable[..., Optional[str]]] = None,
        on_colour_change: Optional[Callable[[Dict[str, Any]], None]] = None,
        get_agent_satisfied_fn: Optional[Callable[[str], bool]] = None,
        debug_get_text_fn: Optional[Callable[[], str]] = None,
        debug_get_visible_graph_fn: Optional[Callable[[str], str]] = None,
        points: Optional[Dict[str, int]] = None,
        fixed_nodes: Optional[Dict[str, Any]] = None,
        problem: Optional[Any] = None,
        structured_rb_mode: bool = False,
        **_ignored_kwargs: Any,
    ) -> None:
        """Start the UI mainloop and block until Finish or consensus."""
        self.problem = problem
        self._rb_structured_mode = structured_rb_mode
        # Prefer visible_graph nodes when available: owned + neighbour boundary nodes.
        if visible_graph is not None and len(visible_graph) >= 1:
            try:
                self._nodes = list(visible_graph[0])
            except Exception:
                self._nodes = list(nodes)
        else:
            self._nodes = list(nodes)

        self._domain = list(domain)
        self._owners = dict(owners)
        self._assignments = dict(current_assignments)
        self._neighs = list(neighbour_owners)
        self._on_send = on_send
        self._on_colour_change = on_colour_change
        self._get_agent_satisfied_fn = get_agent_satisfied_fn
        self._debug_get_text_fn = debug_get_text_fn
        self._debug_get_visible_graph_fn = debug_get_visible_graph_fn
        self._fixed_nodes = dict(fixed_nodes) if fixed_nodes else {}

        if points:
            self._points = dict(points)

        if visible_graph is None:
            self._edges = []
        else:
            _, edges = visible_graph
            self._edges = list(edges)

        root = self._ensure_root()

        # init transcripts and tk vars
        for n in self._neighs:
            self._transcripts.setdefault(n, [])
            self._incoming_queue.setdefault(n, [])
            self._human_sat.setdefault(n, tk.BooleanVar(master=root, value=False))
            self._agent_sat.setdefault(n, tk.StringVar(master=root, value=""))

        self._build_ui(debug_agents=debug_agents, get_visible_graph_fn=get_visible_graph_fn)

        # coin flip starters (independent)
        for neigh in self._neighs:
            if random.random() < 0.5:
                delay_ms = random.randint(250, 900)
                self._root.after(delay_ms, lambda n=neigh: self._agent_start(n))

        # periodic refresh
        self._root.after(400, self._periodic_refresh)

        self._root.mainloop()

    # -------------------- UI construction --------------------

    def _build_ui(self, debug_agents: Optional[List[Any]], get_visible_graph_fn: Optional[Callable[[str], Any]]) -> None:
        root = self._ensure_root()
        root.title(self._title)
        root.geometry("1320x820")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=8, pady=6)

        self._hud_var = tk.StringVar(master=root, value=self._hud_text())
        ttk.Label(top, textvariable=self._hud_var).pack(side="left")

        # Checkpoint button bar
        checkpoint_frame = ttk.Frame(top)
        checkpoint_frame.pack(side="left", padx=20)
        ttk.Label(checkpoint_frame, text="Checkpoints:").pack(side="left")
        self._checkpoint_frame = checkpoint_frame
        self._checkpoint_buttons: List[ttk.Button] = []
        self._checkpoints: List[Dict] = []

        btns = ttk.Frame(top)
        btns.pack(side="right")

        ttk.Button(btns, text="Debug", command=lambda: self._open_debug(debug_agents, get_visible_graph_fn)).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Finish", command=self._finish).pack(side="right")

        main = ttk.Frame(root)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

        right = ttk.Frame(main)
        right.pack(side="right", fill="y", padx=(4, 8), pady=8)

        canvas = tk.Canvas(left, bg="white", highlightthickness=1, highlightbackground="#ccc")
        canvas.pack(fill="both", expand=True)
        self._canvas = canvas
        canvas.bind("<Button-1>", self._on_canvas_click)
        canvas.bind("<Configure>", self._on_canvas_resize)

        for neigh in self._neighs:
            pane = ttk.LabelFrame(right, text=f"{neigh}")
            pane.pack(fill="both", expand=False, pady=6)

            tbox = tk.Text(pane, height=10, wrap="word", state="disabled")
            tbox.pack(fill="x", padx=6, pady=(6, 4))
            self._transcript_box[neigh] = tbox

            row = ttk.Frame(pane)
            row.pack(fill="x", padx=6)

            self._status_var[neigh] = tk.StringVar(master=root, value="idle")
            ttk.Label(row, text="Status:").pack(side="left")
            ttk.Label(row, textvariable=self._status_var[neigh]).pack(side="left", padx=(4, 0))

            sat_row = ttk.Frame(pane)
            sat_row.pack(fill="x", padx=6, pady=(2, 4))

            ttk.Checkbutton(
                sat_row,
                text="I'm satisfied",
                variable=self._human_sat[neigh],
                command=lambda n=neigh: self._on_human_sat_change(n),
            ).pack(side="left")

            ttk.Label(sat_row, textvariable=self._agent_sat[neigh]).pack(side="right")

            # Add RB message builder if in RB/LLM_RB mode - NO TEXT BOX, ONLY DROPDOWNS
            rb_mode = getattr(self, '_rb_structured_mode', False)
            if rb_mode:
                # Structured RB interface - dropdowns only, no text box
                rb_frame = ttk.LabelFrame(pane, text="Send RB Message")
                rb_frame.pack(fill="x", padx=6, pady=(2, 4))

                # Move type dropdown
                move_row = ttk.Frame(rb_frame)
                move_row.pack(fill="x", padx=4, pady=2)
                ttk.Label(move_row, text="Move:").pack(side="left", padx=(0, 4))
                move_var = tk.StringVar(value="PROPOSE")
                move_combo = ttk.Combobox(move_row, textvariable=move_var,
                                         values=["PROPOSE", "ATTACK", "CONCEDE"],
                                         state="readonly", width=15)
                move_combo.pack(side="left", fill="x", expand=True)

                # Node dropdown
                node_row = ttk.Frame(rb_frame)
                node_row.pack(fill="x", padx=4, pady=2)
                ttk.Label(node_row, text="Node:").pack(side="left", padx=(0, 4))
                node_var = tk.StringVar()
                my_nodes = [n for n in self._nodes if self._owners.get(n) == "Human"]
                node_combo = ttk.Combobox(node_row, textvariable=node_var,
                                         values=my_nodes, state="readonly", width=15)
                node_combo.pack(side="left", fill="x", expand=True)
                if my_nodes:
                    node_var.set(my_nodes[0])

                # Color dropdown
                color_row = ttk.Frame(rb_frame)
                color_row.pack(fill="x", padx=4, pady=2)
                ttk.Label(color_row, text="Color:").pack(side="left", padx=(0, 4))
                color_var = tk.StringVar()
                color_combo = ttk.Combobox(color_row, textvariable=color_var,
                                          values=self._domain, state="readonly", width=15)
                color_combo.pack(side="left", fill="x", expand=True)
                if self._domain:
                    color_var.set(self._domain[0])

                # Send button - directly sends structured RB message (NO TEXT BOX)
                def send_rb_message(n=neigh, mv=move_var, nv=node_var, cv=color_var):
                    """Send structured RB message directly from dropdowns."""
                    move = mv.get()
                    node = nv.get()
                    color = cv.get()

                    if not node or not color:
                        print(f"[RB UI] Cannot send: node='{node}' color='{color}'")
                        return

                    # Build structured RB protocol message
                    rb_msg = f'[rb:{{"move": "{move}", "node": "{node}", "colour": "{color}", "reasons": []}}]'

                    # Append to transcript for display
                    try:
                        self._transcripts.setdefault(n, []).append(f"[You → {n}] {move} {node}={color}")
                        self._update_transcript_display(n)
                    except Exception:
                        pass

                    # Send message directly (no text box involved)
                    if self._on_send:
                        self._status_var[n].set("sending...")
                        root.update_idletasks()

                        def _threaded_send():
                            try:
                                sig = inspect.signature(self._on_send)
                                params = sig.parameters
                                if len(params) >= 3:
                                    self._on_send(n, rb_msg, dict(self._assignments))
                                else:
                                    self._on_send(n, rb_msg)
                            except Exception as e:
                                print(f"[RB UI] Send error: {e}")
                            finally:
                                if self._root:
                                    self._root.after(0, lambda: self._status_var[n].set("idle"))

                        threading.Thread(target=_threaded_send, daemon=True).start()

                btn_frame = ttk.Frame(rb_frame)
                btn_frame.pack(fill="x", padx=4, pady=6)
                send = ttk.Button(btn_frame, text="Send RB Message", command=lambda: send_rb_message())
                send.pack(anchor="center")
                self._send_btn[neigh] = send
            else:
                # Normal text-based interface for non-RB modes
                obox = tk.Text(pane, height=3, wrap="word")
                obox.pack(fill="x", padx=6, pady=(2, 4))
                self._outgoing_box[neigh] = obox
                self._set_outgoing_placeholder(neigh)

                def _send_on_enter(ev, n=neigh):
                    self._send_message(n)
                    return "break"

                def _newline_on_shift_enter(ev, box=obox):
                    box.insert("insert", "\n")
                    return "break"

                obox.bind("<Return>", _send_on_enter)
                obox.bind("<Shift-Return>", _newline_on_shift_enter)

                send = ttk.Button(pane, text="Send", command=lambda n=neigh: self._send_message(n))
                send.pack(anchor="e", padx=6, pady=(0, 6))
                self._send_btn[neigh] = send

        root.update_idletasks()
        self._compute_layout()
        self._redraw()

    def _on_canvas_resize(self, _ev: tk.Event) -> None:
        if self._root is None:
            return
        if self._resize_after_id is not None:
            try:
                self._root.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self._root.after(120, self._reflow_after_resize)

    def _reflow_after_resize(self) -> None:
        self._resize_after_id = None
        self._compute_layout()
        self._redraw()

    # -------------------- Graph rendering --------------------

    def _compute_layout(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        w = max(canvas.winfo_width(), 900)
        h = max(canvas.winfo_height(), 700)
        cx, cy = w / 2.0, h / 2.0

        owned = [n for n in self._nodes if self._owners.get(n) == "Human"]
        other = [n for n in self._nodes if n not in owned]

        inner_r = min(w, h) * 0.30
        outer_r = min(w, h) * 0.46

        def place(nodes: List[str], radius: float) -> None:
            if not nodes:
                return
            for i, n in enumerate(nodes):
                ang = (2.0 * math.pi * i) / float(len(nodes))
                x = cx + radius * math.cos(ang)
                y = cy + radius * math.sin(ang)
                self._node_pos[n] = (int(x), int(y))

        place(owned, inner_r)
        place(other, outer_r)

    def _colour_fill(self, c: Any) -> str:
        if c is None:
            return "#dddddd"
        s = str(c).lower()
        if "red" in s:
            return "#ffcccc"
        if "green" in s:
            return "#ccffcc"
        if "blue" in s:
            return "#ccccff"
        return "#eeeeee"

    def _outline_width_for_colour(self, c: Any) -> int:
        s = str(c).lower()
        return 2 + int(self._points.get(s, 1))

    def _redraw(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        canvas.delete("all")
        self._edge_items.clear()
        self._node_items.clear()

        for u, v in self._edges:
            if u not in self._node_pos or v not in self._node_pos:
                continue
            x1, y1 = self._node_pos[u]
            x2, y2 = self._node_pos[v]

            cu = self._assignments.get(u)
            cv = self._assignments.get(v)
            if cv is None and v in self._known_neighbour_colours:
                cv = self._known_neighbour_colours[v]
            if cu is None and u in self._known_neighbour_colours:
                cu = self._known_neighbour_colours[u]

            clash = (cu is not None and cv is not None and str(cu) == str(cv))
            color = "#cc0000" if clash else "#999999"
            width = 3 if clash else 1
            item = canvas.create_line(x1, y1, x2, y2, fill=color, width=width)
            self._edge_items.append((u, v, item))

        for n, (x, y) in self._node_pos.items():
            is_owned = (self._owners.get(n) == "Human")
            r = 24 if is_owned else 18
            col = self._assignments.get(n)
            if col is None and n in self._known_neighbour_colours:
                col = self._known_neighbour_colours[n]

            fill = self._colour_fill(col)
            outline = "#222222" if is_owned else "#666666"
            ow = self._outline_width_for_colour(col) if col is not None else 2
            item = canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=outline, width=ow)
            self._node_items[n] = item
            canvas.create_text(x, y, text=f"{n}", font=("TkDefaultFont", 10 if is_owned else 9))

            # Visual indicators for fixed (immutable) nodes
            if hasattr(self, '_fixed_nodes') and n in self._fixed_nodes:
                # Orange dashed ring around fixed nodes
                canvas.create_oval(x - r - 4, y - r - 4, x + r + 4, y + r + 4,
                                 outline="#FF8C00", width=3, dash=(3, 2), fill="")
                # Lock icon
                canvas.create_text(x + r - 8, y - r + 8, text="🔒",
                                 font=("TkDefaultFont", 10))

    def _on_canvas_click(self, ev: tk.Event) -> None:
        x, y = ev.x, ev.y
        best = None
        best_d = 10**9
        for n, (nx, ny) in self._node_pos.items():
            d = (nx - x) ** 2 + (ny - y) ** 2
            if d < best_d:
                best_d = d
                best = n
        if best is None:
            return
        if self._owners.get(best) != "Human":
            return

        # Prevent clicking fixed nodes (immutable constraints)
        if hasattr(self, '_fixed_nodes') and best in self._fixed_nodes:
            return

        r = 24
        if best_d > (r * r):
            return

        self._cycle_colour(best)
        if self._on_colour_change:
            try:
                self._on_colour_change(dict(self._assignments))
            except Exception:
                pass
        self._redraw()
        if self._hud_var:
            self._hud_var.set(self._hud_text())

    def _cycle_colour(self, node: str) -> None:
        if node not in self._assignments:
            self._assignments[node] = self._domain[0] if self._domain else "blue"
            return
        try:
            idx = self._domain.index(self._assignments[node])
        except ValueError:
            idx = 0
        if not self._domain:
            return
        self._assignments[node] = self._domain[(idx + 1) % len(self._domain)]

    # -------------------- Chat behaviour --------------------

    def _set_outgoing_placeholder(self, neigh: str) -> None:
        """Set placeholder text in message box. Handles focus events to clear/restore placeholder."""
        box = self._outgoing_box.get(neigh)
        if box is None:
            return

        placeholder = "Type a message…"
        current_text = box.get("1.0", "end-1c").strip()

        # Only set placeholder if box is truly empty (not just whitespace)
        if current_text == "" or current_text == placeholder:
            box.delete("1.0", "end")
            box.insert("1.0", placeholder)
            box.configure(fg="#777777")
            self._placeholder_active[neigh] = True
        else:
            # User has actual content - don't touch it
            self._placeholder_active[neigh] = False
            return

        def on_focus_in(_ev=None):
            """Clear placeholder when user clicks in the box."""
            if self._placeholder_active.get(neigh, False):
                current = box.get("1.0", "end-1c").strip()
                if current == placeholder:
                    box.delete("1.0", "end")
                    box.configure(fg="#000000")
                    self._placeholder_active[neigh] = False

        def on_focus_out(_ev=None):
            """Restore placeholder if box is empty when user clicks away."""
            current = box.get("1.0", "end-1c").strip()
            if current == "" or current == placeholder:
                box.delete("1.0", "end")
                box.insert("1.0", placeholder)
                box.configure(fg="#777777")
                self._placeholder_active[neigh] = True

        # Unbind previous handlers to prevent multiple bindings
        box.unbind("<FocusIn>")
        box.unbind("<FocusOut>")

        # Bind new handlers
        box.bind("<FocusIn>", on_focus_in)
        box.bind("<FocusOut>", on_focus_out)

    def _append_to_transcript(self, neigh: str, line: str) -> None:
        self._transcripts.setdefault(neigh, []).append(line)
        if self._root is not None:
            self._root.after(0, lambda n=neigh: self._refresh_transcript(n))

    def _refresh_transcript(self, neigh: str) -> None:
        tbox = self._transcript_box.get(neigh)
        if tbox is None:
            return
        tbox.configure(state="normal")
        tbox.delete("1.0", "end")
        for ln in self._transcripts.get(neigh, []):
            tbox.insert("end", ln + "\n")
        tbox.configure(state="disabled")
        tbox.see("end")

    def _set_status(self, neigh: str, status: str) -> None:
        if neigh in self._status_var:
            self._status_var[neigh].set(status)
        btn = self._send_btn.get(neigh)
        if btn is not None:
            btn["state"] = "disabled" if status.startswith("waiting") else "normal"

    def _flush_incoming(self, neigh: str) -> None:
        q = self._incoming_queue.get(neigh, [])
        while q:
            msg = q.pop(0)
            clean, report = self._extract_and_apply_reports(msg)
            self._append_to_transcript(neigh, f"[{neigh}] {self._humanise(clean)}")
            if report:
                self._redraw()
        self._set_status(neigh, "idle")
        if self._hud_var:
            self._hud_var.set(self._hud_text())

    def _send_message(self, neigh: str) -> None:
        box = self._outgoing_box.get(neigh)
        if box is None:
            return
        msg = box.get("1.0", "end-1c").strip()
        if msg == "Type a message…":
            msg = ""
        box.delete("1.0", "end")
        self._set_outgoing_placeholder(neigh)

        shown = msg if msg.strip() else "(status update)"
        self._append_to_transcript(neigh, f"[You] {shown}")
        self._set_status(neigh, "waiting for reply…")

        def worker():
            reply = None
            try:
                if self._on_send:
                    reply = self._invoke_on_send(neigh, msg)
            except Exception as e:
                reply = f"[System] Error sending: {e}"
            if reply:
                self.add_incoming(neigh, reply)

        threading.Thread(target=worker, daemon=True).start()

    def _humanise(self, text: str) -> str:
        for tag in ("[mapping:", "[report:"):
            idx = text.find(tag)
            if idx != -1:
                text = text[:idx].rstrip()
        return text.strip()

    def _extract_and_apply_reports(self, text: str) -> Tuple[str, Dict[str, Any]]:
        report: Dict[str, Any] = {}
        try:
            m = re.search(r"\[report:\s*(\{.*?\})\s*\]", text)
            if m:
                rep = ast.literal_eval(m.group(1))
                if isinstance(rep, dict):
                    report.update(rep)

            m2 = re.search(r"\[mapping:\s*(\{.*\})\s*\]", text)
            if m2:
                mp = ast.literal_eval(m2.group(1))
                if isinstance(mp, dict):
                    rep2 = mp.get("report") or mp.get("data", {}).get("report")
                    if isinstance(rep2, dict):
                        report.update(rep2)
        except Exception:
            report = {}

        for node, col in report.items():
            self._known_neighbour_colours[str(node)] = col

        return text, report

    def _agent_start(self, neigh: str) -> None:
        self._append_to_transcript(neigh, "[System] Waiting for agent to start…")
        self._set_status(neigh, "waiting for reply…")

        def worker():
            reply = None
            try:
                if self._on_send:
                    reply = self._invoke_on_send(neigh, "")
            except Exception as e:
                reply = f"[System] Agent start error: {e}"
            if reply:
                self.add_incoming(neigh, reply)
            else:
                if self._root is not None:
                    self._root.after(0, lambda: self._set_status(neigh, "idle"))

        threading.Thread(target=worker, daemon=True).start()

    def _invoke_on_send(self, neigh: str, msg: str) -> Optional[str]:
        fn = self._on_send
        if fn is None:
            return None

        try:
            sig = inspect.signature(fn)
            nparams = len([p for p in sig.parameters.values()
                           if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
        except Exception:
            nparams = None

        assignments = dict(self._assignments)

        if nparams == 2:
            return fn(neigh, msg)  # type: ignore[misc]
        if nparams == 3:
            return fn(neigh, msg, assignments)  # type: ignore[misc]

        try:
            return fn(neigh, msg, assignments)  # type: ignore[misc]
        except TypeError:
            return fn(neigh, msg)  # type: ignore[misc]

    def _on_human_sat_change(self, neigh: str) -> None:
        self._check_consensus()

    def _check_consensus(self) -> None:
        """End the UI when the human and all neighbour agents are satisfied."""
        if self._get_agent_satisfied_fn is None:
            return
        if not self._neighs:
            return
        for n in self._neighs:
            try:
                human_ok = bool(self._human_sat[n].get())
            except Exception:
                human_ok = False
            try:
                agent_ok = bool(self._get_agent_satisfied_fn(n))
            except Exception:
                agent_ok = False
            if not (human_ok and agent_ok):
                return

        self.end_reason = "consensus"
        self._finish()

    # -------------------- Debug window --------------------

    def _open_debug(self, debug_agents: Optional[List[Any]], get_visible_graph_fn: Optional[Callable[[str], Any]]) -> None:
        if self._root is None:
            return
        if self._debug_win is not None and tk.Toplevel.winfo_exists(self._debug_win):
            self._debug_win.lift()
            return

        win = tk.Toplevel(self._root)
        win.title("Debug")
        win.geometry("980x620")
        self._debug_win = win

        outer = ttk.Frame(win, padding=8)
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer)
        left.pack(side="left", fill="y")
        right = ttk.Frame(outer)
        right.pack(side="right", fill="both", expand=True)

        ttk.Label(left, text="Participant").pack(anchor="w")
        lb = tk.Listbox(left, height=10, exportselection=False)
        lb.pack(fill="y", expand=False)

        name_to_obj: Dict[str, Any] = {}
        if debug_agents:
            for a in debug_agents:
                try:
                    name_to_obj[str(getattr(a, "name", str(a)))] = a
                except Exception:
                    pass
        name_to_obj.setdefault("Human", None)

        names = sorted(name_to_obj.keys())
        for nm in names:
            lb.insert("end", nm)

        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x", pady=(8, 0))
        refresh_btn = ttk.Button(btn_row, text="Refresh")
        refresh_btn.pack(side="left")

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)

        txt_summary = tk.Text(nb, wrap="word")
        txt_state = tk.Text(nb, wrap="none")
        global_graph_canvas = tk.Canvas(nb, bg="white", highlightthickness=1, highlightbackground="#ccc")
        nb.add(txt_summary, text="Summary")
        nb.add(txt_state, text="State")
        nb.add(global_graph_canvas, text="Global Graph")

        def render(name: str) -> None:
            obj = name_to_obj.get(name)

            summary_lines: List[str] = []
            try:
                if get_visible_graph_fn is not None:
                    vg = get_visible_graph_fn(name)
                    if isinstance(vg, tuple) and len(vg) == 2:
                        vn, ve = vg
                        summary_lines.append(f"Visible graph: |V|={len(vn)}  |E|={len(ve)}")
                        summary_lines.append(f"Nodes: {sorted(list(vn))}")
                    else:
                        summary_lines.append(f"Visible graph: {vg}")
            except Exception as e:
                summary_lines.append(f"(visible graph error: {e})")

            if obj is not None:
                for attr in ("satisfied", "score", "last_score", "iteration"):
                    if hasattr(obj, attr):
                        try:
                            summary_lines.append(f"{attr}: {getattr(obj, attr)}")
                        except Exception:
                            pass

                hist = getattr(obj, "debug_reasoning_history", None)
                if hist:
                    summary_lines.append("")
                    summary_lines.append("Reasoning history (tail):")
                    try:
                        tail = list(hist)[-12:]
                    except Exception:
                        tail = hist
                    for h in tail:
                        summary_lines.append(f"- {h}")

            txt_summary.configure(state="normal")
            txt_summary.delete("1.0", "end")
            txt_summary.insert("end", "\n".join(summary_lines).strip() + "\n")
            txt_summary.configure(state="disabled")

            state_obj: Any = {}
            if obj is None:
                state_obj = {
                    "human_assignments": dict(self._assignments),
                    "human_satisfied": {k: bool(v.get()) for k, v in self._human_sat.items()},
                    "known_neighbour_colours": dict(self._known_neighbour_colours),
                }
            else:
                snap = getattr(obj, "debug_state_snapshot", None)
                if isinstance(snap, dict):
                    state_obj = snap
                else:
                    try:
                        state_obj = {
                            "name": getattr(obj, "name", None),
                            "assignments": dict(getattr(obj, "assignments", {}) or {}),
                            "neighbour_assignments": dict(getattr(obj, "neighbour_assignments", {}) or {}),
                            "forced_local_assignments": dict(getattr(obj, "forced_local_assignments", {}) or {}),
                            "satisfied": bool(getattr(obj, "satisfied", False)),
                        }
                    except Exception:
                        state_obj = str(obj)

            import json as _json
            try:
                state_txt = _json.dumps(state_obj, indent=2, default=str)
            except Exception:
                state_txt = str(state_obj)

            txt_state.configure(state="normal")
            txt_state.delete("1.0", "end")
            txt_state.insert("end", state_txt + "\n")
            txt_state.configure(state="disabled")

            # Render global graph view
            global_graph_lines = []
            global_graph_lines.append("=" * 60)
            global_graph_lines.append("GLOBAL GRAPH VIEW - All Clusters")
            global_graph_lines.append("=" * 60)
            global_graph_lines.append("")

            # Collect all nodes from all agents
            all_agents_nodes = set()
            all_agents_edges = set()
            all_assignments = {}
            all_fixed_nodes = set()

            for agent_name, agent_obj in name_to_obj.items():
                if agent_obj is None:
                    continue
                try:
                    agent_nodes = list(getattr(agent_obj, "nodes", []))
                    all_agents_nodes.update(agent_nodes)

                    # Get assignments
                    assignments = dict(getattr(agent_obj, "assignments", {}))
                    all_assignments.update(assignments)

                    # Get fixed nodes
                    fixed_local = dict(getattr(agent_obj, "fixed_local_nodes", {}))
                    all_fixed_nodes.update(fixed_local.keys())

                    # Try to get edges from problem
                    problem = getattr(agent_obj, "problem", None)
                    if problem:
                        for node in agent_nodes:
                            neighbors = getattr(problem, "get_neighbors", lambda x: [])(node)
                            for nbr in neighbors:
                                edge = tuple(sorted([node, nbr]))
                                all_agents_edges.add(edge)
                except Exception:
                    pass

            # Group nodes by owner/cluster
            nodes_by_owner = {}
            for agent_name, agent_obj in name_to_obj.items():
                if agent_obj is None:
                    continue
                try:
                    nodes = list(getattr(agent_obj, "nodes", []))
                    if nodes:
                        nodes_by_owner[agent_name] = nodes
                except Exception:
                    pass

            # Display cluster information
            global_graph_lines.append(f"Total Clusters: {len(nodes_by_owner)}")
            global_graph_lines.append(f"Total Nodes: {len(all_agents_nodes)}")
            global_graph_lines.append(f"Total Edges: {len(all_agents_edges)}")
            global_graph_lines.append(f"Fixed Nodes: {len(all_fixed_nodes)}")
            global_graph_lines.append("")

            # Display each cluster
            for cluster_name in sorted(nodes_by_owner.keys()):
                cluster_nodes = nodes_by_owner[cluster_name]
                global_graph_lines.append(f"--- {cluster_name} ---")
                for node in sorted(cluster_nodes):
                    color = all_assignments.get(node, "unassigned")
                    fixed_marker = " [FIXED]" if node in all_fixed_nodes else ""
                    global_graph_lines.append(f"  {node}: {color}{fixed_marker}")
                global_graph_lines.append("")

            # Display all edges
            if all_agents_edges:
                global_graph_lines.append("--- All Edges ---")
                for u, v in sorted(all_agents_edges):
                    # Determine if cross-cluster
                    u_owner = None
                    v_owner = None
                    for owner, nodes in nodes_by_owner.items():
                        if u in nodes:
                            u_owner = owner
                        if v in nodes:
                            v_owner = owner

                    edge_type = " (cross-cluster)" if u_owner != v_owner else ""
                    u_color = all_assignments.get(u, "?")
                    v_color = all_assignments.get(v, "?")
                    conflict = " [CONFLICT!]" if u_color == v_color and u_color != "?" else ""

                    global_graph_lines.append(f"  {u}({u_color}) -- {v}({v_color}){edge_type}{conflict}")

            # Render visual global graph on canvas
            self._render_global_graph_visual(
                global_graph_canvas,
                debug_agents if debug_agents else [],
                all_assignments,
                all_fixed_nodes,
                nodes_by_owner,
                all_agents_edges
            )

        def on_select(_ev=None):
            try:
                sel = lb.curselection()
                if not sel:
                    return
                name = lb.get(sel[0])
                render(name)
            except Exception:
                pass

        lb.bind("<<ListboxSelect>>", on_select)
        refresh_btn.configure(command=lambda: on_select())

        if names:
            lb.selection_set(0)
            render(names[0])

    # -------------------- Checkpoint restore system --------------------

    def update_checkpoints(self, checkpoints: List[Dict]) -> None:
        """Update checkpoint button list with new checkpoints."""
        self._checkpoints = list(checkpoints)

        # Clear existing buttons
        for btn in self._checkpoint_buttons:
            btn.destroy()
        self._checkpoint_buttons.clear()

        # Create buttons for each checkpoint
        for cp in checkpoints:
            btn_text = f"#{cp['id']}: {cp.get('score', 0):.1f}"
            btn = ttk.Button(
                self._checkpoint_frame,
                text=btn_text,
                command=lambda cid=cp['id']: self._restore_checkpoint(cid),
                width=12
            )
            btn.pack(side="left", padx=2)
            self._checkpoint_buttons.append(btn)
            self._create_checkpoint_tooltip(btn, cp)

    def _restore_checkpoint(self, cp_id: int) -> None:
        """Restore assignments from a specific checkpoint."""
        for cp in self._checkpoints:
            if cp["id"] == cp_id:
                self._assignments = dict(cp["assignments"])
                self._redraw()
                if self._on_colour_change:
                    self._on_colour_change(dict(self._assignments))
                print(f"[UI] Restored checkpoint #{cp_id} from iteration {cp['iteration']}")
                break

    def _create_checkpoint_tooltip(self, button: ttk.Button, checkpoint: Dict) -> None:
        """Create hover tooltip showing checkpoint details."""
        def show_tooltip(event):
            tooltip = tk.Toplevel(self._root)
            tooltip.wm_overrideredirect(True)
            tooltip.geometry(f"+{event.x_root+10}+{event.y_root+10}")

            # Build tooltip text
            lines = [
                f"Checkpoint #{checkpoint['id']}",
                f"Iteration: {checkpoint['iteration']}",
                f"Penalty: {checkpoint.get('penalty', 0):.6f}",
                f"Score: {checkpoint.get('score', 0):.2f}",
                "",
                "Assignments:"
            ]
            for node, color in sorted(checkpoint['assignments'].items()):
                lines.append(f"  {node}: {color}")

            label = tk.Label(
                tooltip,
                text="\n".join(lines),
                bg="lightyellow",
                fg="black",
                relief="solid",
                borderwidth=1,
                font=("TkDefaultFont", 9),
                justify="left",
                padx=8,
                pady=6
            )
            label.pack()
            button._tooltip = tooltip

        def hide_tooltip(event):
            if hasattr(button, '_tooltip'):
                try:
                    button._tooltip.destroy()
                    delattr(button, '_tooltip')
                except:
                    pass

        button.bind("<Enter>", show_tooltip)
        button.bind("<Leave>", hide_tooltip)

    def _render_global_graph_visual(
        self,
        canvas: tk.Canvas,
        agents: List[Any],
        all_assignments: Dict[str, Any],
        all_fixed: set,
        nodes_by_owner: Dict[str, List[str]],
        all_edges: set
    ) -> None:
        """Render complete global graph on canvas with all clusters visible."""
        canvas.delete("all")

        # Get canvas dimensions
        canvas.update_idletasks()
        w = max(canvas.winfo_width(), 600)
        h = max(canvas.winfo_height(), 500)
        cx, cy = w / 2.0, h / 2.0

        # Layout: multi-ring circular (one ring per cluster)
        node_positions = {}
        cluster_names = sorted(nodes_by_owner.keys())
        num_clusters = len(cluster_names)

        if num_clusters == 0:
            canvas.create_text(cx, cy, text="No agents available", font=("Arial", 14))
            return

        for cluster_idx, cluster_name in enumerate(cluster_names):
            cluster_nodes = sorted(nodes_by_owner[cluster_name])
            num_nodes = len(cluster_nodes)

            if num_nodes == 0:
                continue

            # Determine radius based on cluster index
            if cluster_name == "Human":
                radius = min(w, h) * 0.20  # Innermost ring
            else:
                # Outer rings for agents
                ring_offset = 0.30 + ((cluster_idx - 1) * 0.15) if cluster_name != "Human" else 0.30
                radius = min(w, h) * ring_offset

            # Position nodes around circle
            for i, node in enumerate(cluster_nodes):
                angle = (2.0 * math.pi * i) / float(num_nodes) if num_nodes > 0 else 0
                x = cx + radius * math.cos(angle)
                y = cy + radius * math.sin(angle)
                node_positions[node] = (int(x), int(y))

        # Draw edges first (so they're behind nodes)
        for edge in all_edges:
            if isinstance(edge, tuple) and len(edge) >= 2:
                u, v = edge[0], edge[1]
            else:
                continue

            if u not in node_positions or v not in node_positions:
                continue

            x1, y1 = node_positions[u]
            x2, y2 = node_positions[v]

            # Check for conflict (same color on adjacent nodes)
            u_color = all_assignments.get(u)
            v_color = all_assignments.get(v)

            if u_color and v_color and str(u_color).lower() == str(v_color).lower():
                # CONFLICT - thick red line
                canvas.create_line(x1, y1, x2, y2, fill="#dd0000", width=3, tags="edge")
            else:
                # Normal edge
                canvas.create_line(x1, y1, x2, y2, fill="#999999", width=1, tags="edge")

        # Draw nodes
        for node, (x, y) in node_positions.items():
            color = all_assignments.get(node)

            # Color fill
            fill_color = self._colour_fill(color)

            # Radius
            radius = 20

            # Draw circle
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=fill_color,
                outline="#333",
                width=2,
                tags="node"
            )

            # Fixed node indicator (orange dashed ring + lock)
            if node in all_fixed:
                canvas.create_oval(
                    x - radius - 4, y - radius - 4, x + radius + 4, y + radius + 4,
                    outline="#FF8C00",
                    width=3,
                    dash=(3, 2),
                    tags="fixed"
                )
                canvas.create_text(
                    x + radius - 8, y - radius + 8,
                    text="🔒",
                    font=("TkDefaultFont", 10),
                    tags="fixed"
                )

            # Node label
            canvas.create_text(
                x, y,
                text=str(node),
                font=("Arial", 10, "bold"),
                tags="label"
            )

        # Add legend
        legend_x = 20
        legend_y = 20
        for i, cluster_name in enumerate(cluster_names):
            y_offset = legend_y + (i * 25)
            canvas.create_text(
                legend_x, y_offset,
                text=f"● {cluster_name}",
                anchor="w",
                font=("Arial", 11, "bold"),
                tags="legend"
            )

    # -------------------- Periodic refresh --------------------

    def _periodic_refresh(self) -> None:
        if self._done.is_set():
            return

        if self._get_agent_satisfied_fn:
            for neigh in self._neighs:
                try:
                    sat = bool(self._get_agent_satisfied_fn(neigh))
                    self._agent_sat[neigh].set("Agent ✓" if sat else "")
                except Exception:
                    pass

        if self._hud_var:
            self._hud_var.set(self._hud_text())

        # Update checkpoints if available from problem object
        try:
            if hasattr(self, 'problem') and self.problem is not None:
                if hasattr(self.problem, 'checkpoints'):
                    checkpoints = getattr(self.problem, 'checkpoints', [])
                    # Update if checkpoint list has changed (length or content)
                    if checkpoints:
                        # Check if we need to update (length changed or list is different)
                        if len(checkpoints) != len(self._checkpoints):
                            print(f"[UI] Updating checkpoints: {len(checkpoints)} available")
                            self.update_checkpoints(checkpoints)
                        # Also check if IDs have changed (in case checkpoints were reset)
                        elif checkpoints:
                            current_ids = [cp.get('id') for cp in self._checkpoints]
                            new_ids = [cp.get('id') for cp in checkpoints]
                            if current_ids != new_ids:
                                print(f"[UI] Checkpoint IDs changed, updating")
                                self.update_checkpoints(checkpoints)
        except Exception as e:
            print(f"[UI] Error updating checkpoints: {e}")

        self._check_consensus()

        if self._root is not None:
            self._root.after(400, self._periodic_refresh)

    def _hud_text(self) -> str:
        score = 0
        for n, c in self._assignments.items():
            if self._owners.get(n) != "Human":
                continue
            score += self._points.get(str(c).lower(), 0)
        return f"Score: {score}"

    # -------------------- Finish --------------------

    def _finish(self) -> None:
        self._done.set()
        if self._root is not None:
            try:
                self._root.quit()
            except Exception:
                pass
            try:
                self._root.destroy()
            except Exception:
                pass
