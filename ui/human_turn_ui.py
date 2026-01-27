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
import json
import tkinter as tk
import logging
from datetime import datetime
from tkinter import ttk
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
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

        # Setup detailed logging for conditional builder debugging
        log_file = f"conditional_builder_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._debug_logger = logging.getLogger('conditional_builder')
        self._debug_logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        self._debug_logger.addHandler(fh)
        self._debug_logger.info(f"=== Conditional Builder Debug Session Started ===")
        self._debug_logger.info(f"Log file: {log_file}")

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

        # RB mode argument tracking (structured dialogue moves)
        self._rb_arguments: Dict[str, List[Dict[str, Any]]] = {}  # Store parsed RB moves per neighbour
        self._rb_pending_justification_refs: Dict[str, List[int]] = {}  # Temporary storage for justification refs

        # Conditionals tracking (new protocol)
        self._active_conditionals: List[Dict[str, Any]] = []  # List of active conditional offers (from agents)
        self._human_sent_offers: List[Dict[str, Any]] = []    # Track human's own sent offers
        self._conditionals_frame: Optional[ttk.Frame] = None
        self._conditionals_cards_inner: Optional[tk.Frame] = None
        self._committed_nodes: Set[str] = set()  # Track committed nodes for visualization

        # Per-neighbor conditional builder frames (so each neighbor has independent UI)
        self._conditional_builder_frames: Dict[str, ttk.Frame] = {}
        self._condition_rows: Dict[str, List] = {}  # {neighbor: [(frame, var), ...]}
        self._assignment_rows: Dict[str, List] = {}  # {neighbor: [(frame, node_var, color_var), ...]}

        # Two-phase workflow: configure → bargain
        self._phase: str = "configure"  # "configure" or "bargain"
        self._initial_configs: Dict[str, Dict[str, str]] = {}  # {agent_name: {node: color}}
        self._agent_configurations: Dict[str, Dict[str, str]] = {}  # {agent_name: {node: color}} - current announced configs

        # Zoom and pan state for RB argument canvas
        self._rb_canvas_scale: Dict[str, float] = {}  # Zoom level per neighbour
        self._rb_canvas_offset: Dict[str, Tuple[int, int]] = {}  # Pan offset per neighbour
        self._rb_drag_start: Dict[str, Optional[Tuple[int, int]]] = {}  # Drag start position

        # Zoom and pan state for graph canvas
        self._graph_canvas_scale: float = 1.0
        self._graph_canvas_offset: Tuple[int, int] = (0, 0)
        self._graph_drag_start: Optional[Tuple[int, int]] = None

        # LLM_RB live translation
        self._llm_rb_translation_labels: Dict[str, tk.Label] = {}
        self._llm_rb_debounce_ids: Dict[str, Optional[str]] = {}
        self._llm_rb_animation_ids: Dict[str, Optional[str]] = {}
        self._llm_rb_translation_sequence: Dict[str, int] = {}  # Track translation versions to prevent stale updates

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
        print(f"[UI] add_incoming called for {neigh}: {text[:200]}")
        self._incoming_queue.setdefault(neigh, []).append(text)
        if self._root is not None:
            self._root.after(0, lambda n=neigh: self._flush_incoming(n))
        else:
            print(f"[UI] WARNING: _root is None, cannot flush incoming messages")

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
        comm_layer: Optional[Any] = None,
        **_ignored_kwargs: Any,
    ) -> None:
        """Start the UI mainloop and block until Finish or consensus."""
        self.problem = problem
        self._rb_structured_mode = structured_rb_mode
        self._comm_layer = comm_layer
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

        # Phase status (for RB structured mode only)
        if getattr(self, '_rb_structured_mode', False):
            self._phase_label = ttk.Label(btns, text="Phase: Configure", font=("Arial", 10, "bold"))
            self._phase_label.pack(side="left", padx=(0, 10))

            self._announce_config_btn = ttk.Button(btns, text="(Re-)Announce Configuration",
                                                   command=self._announce_configuration)
            self._announce_config_btn.pack(side="left", padx=(0, 6))

            self._impossible_btn = ttk.Button(btns, text="Impossible to Continue",
                                              command=self._signal_impossible, state="disabled")
            self._impossible_btn.pack(side="left", padx=(0, 6))

        ttk.Button(btns, text="Debug", command=lambda: self._open_debug(debug_agents, get_visible_graph_fn)).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Finish", command=self._finish).pack(side="right")

        main = ttk.Frame(root)
        main.pack(fill="both", expand=True)

        # Use PanedWindow for adjustable split between graph, arguments, and conditionals
        paned = tk.PanedWindow(main, orient=tk.HORIZONTAL, sashrelief=tk.RAISED,
                               sashwidth=5, bg="#ddd")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(paned)
        paned.add(left, width=400, minsize=250)  # Graph panel: default 400px, min 250px

        # Middle panel with scrollbar for chat panes
        middle_container = ttk.Frame(paned)
        paned.add(middle_container, width=600, minsize=350)  # Argument panel: default 600px, min 350px

        # Create canvas and scrollbar for middle panel
        middle_canvas = tk.Canvas(middle_container, highlightthickness=0)
        middle_scrollbar = ttk.Scrollbar(middle_container, orient="vertical", command=middle_canvas.yview)
        middle_scrollbar.pack(side="right", fill="y")
        middle_canvas.pack(side="left", fill="both", expand=True)
        middle_canvas.configure(yscrollcommand=middle_scrollbar.set)

        # Frame inside canvas to hold chat panes
        right = ttk.Frame(middle_canvas)
        middle_canvas_window = middle_canvas.create_window((0, 0), window=right, anchor="nw")

        # Update scroll region when content changes
        def on_right_configure(event):
            middle_canvas.configure(scrollregion=middle_canvas.bbox("all"))
        right.bind("<Configure>", on_right_configure)

        # Bind canvas width to inner frame width
        def on_canvas_configure(event):
            middle_canvas.itemconfig(middle_canvas_window, width=event.width)
        middle_canvas.bind("<Configure>", on_canvas_configure)

        # Bind mousewheel to scrolling
        def on_mousewheel(event):
            middle_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        middle_canvas.bind_all("<MouseWheel>", on_mousewheel)

        # Add conditionals sidebar (only visible in RB mode)
        conditionals_frame = ttk.Frame(paned)
        paned.add(conditionals_frame, width=320, minsize=250)  # Conditionals: default 320px, min 250px

        # Store reference for later use
        self._conditionals_frame = conditionals_frame
        self._conditionals_cards_inner = None  # Will be set when building conditionals UI

        # Build conditionals sidebar UI
        self._build_conditionals_sidebar(conditionals_frame)

        canvas = tk.Canvas(left, bg="white", highlightthickness=1, highlightbackground="#ccc")
        canvas.pack(fill="both", expand=True)
        self._canvas = canvas
        canvas.bind("<Button-1>", self._on_canvas_click)
        canvas.bind("<Configure>", self._on_canvas_resize)

        # Add zoom with mouse wheel
        def _on_graph_zoom(event):
            # Get mouse position
            x, y = event.x, event.y

            # Zoom in or out
            if event.delta > 0:
                scale_factor = 1.1
            else:
                scale_factor = 0.9

            old_scale = self._graph_canvas_scale
            new_scale = old_scale * scale_factor

            # Clamp scale between 0.3 and 3.0
            new_scale = max(0.3, min(3.0, new_scale))

            self._graph_canvas_scale = new_scale

            # Adjust offset to zoom toward mouse position
            offset_x, offset_y = self._graph_canvas_offset
            offset_x = x - (x - offset_x) * (new_scale / old_scale)
            offset_y = y - (y - offset_y) * (new_scale / old_scale)
            self._graph_canvas_offset = (offset_x, offset_y)

            self._redraw_graph()

        canvas.bind("<MouseWheel>", _on_graph_zoom)

        # Add pan with middle mouse or shift+drag
        def _on_graph_drag_start(event):
            self._graph_drag_start = (event.x, event.y)

        def _on_graph_drag_move(event):
            if self._graph_drag_start:
                start_x, start_y = self._graph_drag_start
                dx = event.x - start_x
                dy = event.y - start_y

                offset_x, offset_y = self._graph_canvas_offset
                self._graph_canvas_offset = (offset_x + dx, offset_y + dy)

                self._graph_drag_start = (event.x, event.y)
                self._redraw_graph()

        def _on_graph_drag_end(event):
            self._graph_drag_start = None

        # Bind middle click for panning
        canvas.bind("<ButtonPress-2>", _on_graph_drag_start)
        canvas.bind("<B2-Motion>", _on_graph_drag_move)
        canvas.bind("<ButtonRelease-2>", _on_graph_drag_end)

        # Bind shift+left click for panning (alternative)
        def _on_graph_shift_drag_start(event):
            if event.state & 0x0001:  # Shift key
                self._graph_drag_start = (event.x, event.y)
                return "break"  # Prevent normal click behavior
            return None

        def _on_graph_shift_drag_move(event):
            if (event.state & 0x0001) and self._graph_drag_start:  # Shift key
                start_x, start_y = self._graph_drag_start
                dx = event.x - start_x
                dy = event.y - start_y

                offset_x, offset_y = self._graph_canvas_offset
                self._graph_canvas_offset = (offset_x + dx, offset_y + dy)

                self._graph_drag_start = (event.x, event.y)
                self._redraw_graph()
                return "break"

        # Note: We need to check shift state in _on_canvas_click to not interfere with node clicking
        canvas.bind("<B1-Motion>", _on_graph_shift_drag_move)

        for neigh in self._neighs:
            # Check if we're in structured RB mode to use argument graph instead of text transcript
            is_structured_rb = getattr(self, '_rb_structured_mode', False)

            pane = ttk.LabelFrame(right, text=f"{neigh}")
            # In RB mode, allow panes to expand vertically to fill available space
            pane.pack(fill="both", expand=is_structured_rb, pady=6)

            if is_structured_rb:
                # Use canvas for visual argument graph - tree layout with zoom/pan
                arg_frame = ttk.Frame(pane)
                arg_frame.pack(fill="both", expand=True, padx=6, pady=(6, 4))

                # Remove height constraint - let canvas expand to fill available space
                arg_canvas = tk.Canvas(arg_frame, bg="white", highlightthickness=1, highlightbackground="#ccc")
                arg_canvas.pack(fill="both", expand=True)

                # Initialize zoom/pan state for this neighbour
                self._rb_canvas_scale[neigh] = 1.0
                self._rb_canvas_offset[neigh] = (0, 0)
                self._rb_drag_start[neigh] = None

                # Bind zoom with mouse wheel
                def _on_zoom(event, n=neigh, canvas=arg_canvas):
                    # Get mouse position
                    x, y = event.x, event.y

                    # Zoom in or out
                    if event.delta > 0:
                        scale_factor = 1.1
                    else:
                        scale_factor = 0.9

                    old_scale = self._rb_canvas_scale[n]
                    new_scale = old_scale * scale_factor

                    # Clamp scale between 0.2 and 5.0
                    new_scale = max(0.2, min(5.0, new_scale))

                    self._rb_canvas_scale[n] = new_scale

                    # Adjust offset to zoom toward mouse position
                    offset_x, offset_y = self._rb_canvas_offset[n]
                    offset_x = x - (x - offset_x) * (new_scale / old_scale)
                    offset_y = y - (y - offset_y) * (new_scale / old_scale)
                    self._rb_canvas_offset[n] = (offset_x, offset_y)

                    self._render_argument_graph(n, canvas)

                arg_canvas.bind("<MouseWheel>", _on_zoom)

                # Bind pan with middle mouse or Shift+drag
                def _on_drag_start(event, n=neigh):
                    self._rb_drag_start[n] = (event.x, event.y)

                def _on_drag_move(event, n=neigh, canvas=arg_canvas):
                    if self._rb_drag_start[n]:
                        start_x, start_y = self._rb_drag_start[n]
                        dx = event.x - start_x
                        dy = event.y - start_y

                        offset_x, offset_y = self._rb_canvas_offset[n]
                        self._rb_canvas_offset[n] = (offset_x + dx, offset_y + dy)

                        self._rb_drag_start[n] = (event.x, event.y)
                        self._render_argument_graph(n, canvas)

                def _on_drag_end(event, n=neigh):
                    self._rb_drag_start[n] = None

                # Bind middle click or shift+left click for panning
                arg_canvas.bind("<ButtonPress-2>", _on_drag_start)  # Middle click
                arg_canvas.bind("<B2-Motion>", _on_drag_move)
                arg_canvas.bind("<ButtonRelease-2>", _on_drag_end)

                # Also bind shift+left click for panning
                def _on_shift_drag_start(event, n=neigh):
                    if event.state & 0x0001:  # Shift key
                        self._rb_drag_start[n] = (event.x, event.y)

                def _on_shift_drag_move(event, n=neigh, canvas=arg_canvas):
                    if (event.state & 0x0001) and self._rb_drag_start[n]:  # Shift key
                        start_x, start_y = self._rb_drag_start[n]
                        dx = event.x - start_x
                        dy = event.y - start_y

                        offset_x, offset_y = self._rb_canvas_offset[n]
                        self._rb_canvas_offset[n] = (offset_x + dx, offset_y + dy)

                        self._rb_drag_start[n] = (event.x, event.y)
                        self._render_argument_graph(n, canvas)

                arg_canvas.bind("<ButtonPress-1>", _on_shift_drag_start)
                arg_canvas.bind("<B1-Motion>", _on_shift_drag_move)
                arg_canvas.bind("<ButtonRelease-1>", _on_drag_end)

                self._transcript_box[neigh] = arg_canvas  # Store in same dict for compatibility
            else:
                # Use text box for other modes
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

            # Check for LLM_RB live translation mode first
            llm_rb_mode = getattr(self, '_llm_rb_mode', False)

            if llm_rb_mode:
                # LLM_RB mode: Text box with live translation preview
                obox = tk.Text(pane, height=3, wrap="word")
                obox.pack(fill="x", padx=6, pady=(2, 4))
                self._outgoing_box[neigh] = obox
                self._set_outgoing_placeholder(neigh)

                # Live translation preview
                preview_frame = ttk.LabelFrame(pane, text="Live Translation Preview")
                preview_frame.pack(fill="x", padx=6, pady=(2, 4))

                preview_label = tk.Label(preview_frame, text="(type to see translation)",
                                        fg="gray", anchor="w", justify="left",
                                        padx=8, pady=4, wraplength=400)
                preview_label.pack(fill="both", expand=True)
                self._llm_rb_translation_labels[neigh] = preview_label
                self._llm_rb_debounce_ids[neigh] = None

                # Bind keypress to trigger debounced translation
                def on_keyrelease(ev, n=neigh):
                    self._schedule_llm_rb_translation(n)

                obox.bind("<KeyRelease>", on_keyrelease)

                def _send_on_enter(ev, n=neigh):
                    self._send_message(n)
                    return "break"

                def _newline_on_shift_enter(ev, box=obox):
                    box.insert("insert", "\n")
                    return "break"

                obox.bind("<Return>", _send_on_enter)
                obox.bind("<Shift-Return>", _newline_on_shift_enter)

                # Button frame
                btn_frame = ttk.Frame(pane)
                btn_frame.pack(anchor="e", padx=6, pady=(0, 6))

                send_config = ttk.Button(btn_frame, text="Send Config",
                                        command=lambda n=neigh: self._send_config(n))
                send_config.pack(side="left", padx=(0, 4))

                send = ttk.Button(btn_frame, text="Send", command=lambda n=neigh: self._send_message(n))
                send.pack(side="left")
                self._send_btn[neigh] = send

            # Add RB message builder if in pure RB mode - SIMPLIFIED FOR CONDITIONAL OFFERS ONLY
            elif getattr(self, '_rb_structured_mode', False):
                # Simplified conditional offer interface
                print(f"[UI Build] Creating conditional builder for neighbor '{neigh}' (type={type(neigh)})")
                rb_frame = ttk.LabelFrame(pane, text=f"Make Offer to {neigh}")
                rb_frame.pack(fill="x", padx=6, pady=(2, 4))

                # Phase-aware help text
                if self._phase == "configure":
                    help_text = "CONFIGURE PHASE: Set up your graph, then click 'Announce Configuration' to begin bargaining"
                    help_fg = "#d9534f"  # Red
                else:
                    help_text = "BARGAIN PHASE: Build conditional offers: 'If they do X, I'll do Y' (both IF and THEN required)"
                    help_fg = "#555"

                help_label = tk.Label(rb_frame, text=help_text,
                                     fg=help_fg, font=("Arial", 8, "italic"),
                                     wraplength=400, justify="left", anchor="w")
                help_label.pack(fill="x", padx=4, pady=4)
                self._rb_help_labels = getattr(self, '_rb_help_labels', {})
                self._rb_help_labels[neigh] = help_label

                # Conditional builder frame (disabled in configure phase)
                conditional_builder_frame = ttk.Frame(rb_frame)
                self._conditional_builder_frames[neigh] = conditional_builder_frame
                conditional_builder_frame.pack(fill="both", expand=True, padx=4, pady=4)

                # Disable builder in configure phase
                if self._phase == "configure":
                    for child in conditional_builder_frame.winfo_children():
                        if hasattr(child, 'config'):
                            child.config(state="disabled")

                self._debug_logger.info(f"--- Created ALWAYS-VISIBLE conditional builder for {neigh} ---")
                self._debug_logger.info(f"  Frame object id: {id(conditional_builder_frame)}")
                self._debug_logger.info(f"  Packed and always visible")

                # Store condition and assignment rows per neighbor
                self._condition_rows[neigh] = []
                self._assignment_rows[neigh] = []

                # Conditions section (IF part)
                conditions_label = ttk.Label(conditional_builder_frame, text="IF (conditions):", font=("Arial", 9, "bold"))
                conditions_label.pack(anchor="w", padx=4, pady=(4, 2))

                # Instruction label
                ttk.Label(conditional_builder_frame, text="Select statements from agent's proposals to use as conditions",
                         font=("Arial", 7, "italic"), foreground="#666").pack(anchor="w", padx=4)

                conditions_container = ttk.Frame(conditional_builder_frame)
                conditions_container.pack(fill="x", padx=4, pady=2)

                def add_condition_row(n=neigh, container=conditions_container):
                    """Add a new condition row for selecting previous statements."""
                    print(f"[UI] Adding condition row for neighbor '{n}' (type={type(n)})")
                    print(f"[UI] Current _rb_arguments keys: {list(self._rb_arguments.keys())}")
                    row_frame = ttk.Frame(container)
                    row_frame.pack(fill="x", pady=2)

                    # Dropdown to select from previous statements
                    statement_var = tk.StringVar(value="(select statement)")
                    statement_combo = ttk.Combobox(row_frame, textvariable=statement_var,
                                                  state="readonly", width=40)

                    # Populate with previous statements from this neighbor
                    def update_statement_options():
                        recent_args = self._rb_arguments.get(n, [])
                        options = ["(select statement)"]

                        if not recent_args:
                            print(f"[UI Dropdown] No args found for neighbor '{n}'")
                            print(f"[UI Dropdown] Available keys: {list(self._rb_arguments.keys())}")

                        for i, arg in enumerate(recent_args):
                            arg_sender = arg.get('sender')
                            if arg_sender == n:
                                move = arg.get('move', '')
                                if move == 'ConditionalOffer':
                                    assignments = arg.get('assignments', [])
                                    for assign in assignments:
                                        node = assign.get('node', '')
                                        color = assign.get('colour', '')
                                        summary = f"#{i}: {node}={color}"
                                        options.append(summary)
                                else:
                                    summary = f"#{i}: {arg['node']}={arg['color']} ({move})"
                                    options.append(summary)
                            else:
                                print(f"[UI Dropdown] Skipping arg {i}: sender '{arg_sender}' != neighbor '{n}'")

                        statement_combo['values'] = options
                        print(f"[UI Dropdown] Final options count: {len(options)-1}")  # -1 for placeholder

                    update_statement_options()
                    statement_combo.bind('<Button-1>', lambda e: update_statement_options())
                    statement_combo.pack(side="left", padx=2)

                    # Remove button
                    def remove_row():
                        print(f"[UI] Removing condition row for {n}")
                        row_frame.destroy()
                        if (row_frame, statement_var) in self._condition_rows[n]:
                            self._condition_rows[n].remove((row_frame, statement_var))
                        print(f"[UI] {n} now has {len(self._condition_rows[n])} condition rows")

                    remove_btn = ttk.Button(row_frame, text="✗", width=3, command=remove_row)
                    remove_btn.pack(side="left", padx=2)

                    self._condition_rows[n].append((row_frame, statement_var))
                    return row_frame

                add_condition_btn = ttk.Button(conditional_builder_frame, text="+ Add Condition",
                                              command=lambda n=neigh, c=conditions_container: add_condition_row(n, c))
                add_condition_btn.pack(anchor="w", padx=4, pady=2)

                # Assignments section (THEN part)
                assignments_label = ttk.Label(conditional_builder_frame, text="THEN (my commitments):", font=("Arial", 9, "bold"))
                assignments_label.pack(anchor="w", padx=4, pady=(8, 2))

                # Instruction label
                ttk.Label(conditional_builder_frame, text="Specify what you'll commit to if conditions are met",
                         font=("Arial", 7, "italic"), foreground="#666").pack(anchor="w", padx=4)

                assignments_container = ttk.Frame(conditional_builder_frame)
                assignments_container.pack(fill="x", padx=4, pady=2)

                def add_assignment_row(n=neigh, container=assignments_container):
                    """Add a new assignment row for specifying commitments."""
                    print(f"[UI] Adding assignment row for {n}")
                    row_frame = ttk.Frame(container)
                    row_frame.pack(fill="x", pady=2)

                    # Node selector (my owned nodes only)
                    ttk.Label(row_frame, text="Node:").pack(side="left", padx=2)
                    node_var = tk.StringVar()
                    my_nodes = [node for node in self._nodes if self._owners.get(node) == "Human"]
                    node_combo = ttk.Combobox(row_frame, textvariable=node_var,
                                             values=my_nodes, state="readonly", width=8)
                    node_combo.pack(side="left", padx=2)
                    if my_nodes:
                        node_var.set(my_nodes[0])

                    # Color selector
                    ttk.Label(row_frame, text="=").pack(side="left", padx=2)
                    color_var = tk.StringVar()
                    color_combo = ttk.Combobox(row_frame, textvariable=color_var,
                                              values=self._domain, state="readonly", width=8)
                    color_combo.pack(side="left", padx=2)
                    if self._domain:
                        color_var.set(self._domain[0])

                    # Remove button
                    def remove_row():
                        print(f"[UI] Removing assignment row for {n}")
                        row_frame.destroy()
                        if (row_frame, node_var, color_var) in self._assignment_rows[n]:
                            self._assignment_rows[n].remove((row_frame, node_var, color_var))
                        print(f"[UI] {n} now has {len(self._assignment_rows[n])} assignment rows")

                    remove_btn = ttk.Button(row_frame, text="✗", width=3, command=remove_row)
                    remove_btn.pack(side="left", padx=2)

                    self._assignment_rows[n].append((row_frame, node_var, color_var))
                    return row_frame

                add_assignment_btn = ttk.Button(conditional_builder_frame, text="+ Add Assignment",
                                               command=lambda n=neigh, c=assignments_container: add_assignment_row(n, c))
                add_assignment_btn.pack(anchor="w", padx=4, pady=2)

                # Initialize with one assignment row (conditions can be empty for unconditional offers)
                add_assignment_row(neigh)
                self._debug_logger.info(f"  Initialized with 0 condition rows and 1 assignment row")

                # Send button - sends conditional offer
                def send_rb_message(n=neigh):
                    """Send conditional offer from builder."""
                    import time

                    # Get condition and assignment rows for this neighbor
                    cond_rows = self._condition_rows.get(n, [])
                    assign_rows = self._assignment_rows.get(n, [])

                    # Extract conditions from condition rows (can be empty for unconditional)
                    conditions = []
                    for row_frame, stmt_var in cond_rows:
                        stmt = stmt_var.get()
                        if stmt and stmt != "(select statement)":
                            # Parse statement: "#3: h1=red"
                            match = re.match(r'#(\d+): (\w+)=(\w+)', stmt)
                            if match:
                                idx, node_name, color_name = match.groups()
                                # Get owner of this node
                                owner = self._owners.get(node_name, "Unknown")
                                conditions.append({
                                    "node": node_name,
                                    "colour": color_name,
                                    "owner": owner
                                })

                    # Extract assignments from assignment rows
                    assignments = []
                    for row_frame, node_v, color_v in assign_rows:
                        node_name = node_v.get()
                        color_name = color_v.get()
                        if node_name and color_name:
                            assignments.append({
                                "node": node_name,
                                "colour": color_name
                            })

                    # Must have at least one assignment
                    if not assignments:
                        print(f"[RB UI] Cannot send offer: no assignments specified (THEN part is required)")
                        return

                    # Must have at least one condition (IF part required)
                    if not conditions:
                        print(f"[RB UI] Cannot send offer: no conditions specified (IF part is required)")
                        print(f"[RB UI] Use '(Re-)Announce Configuration' button to announce assignments without conditions")
                        return

                    # Build conditional offer message
                    offer_id = f"offer_{int(time.time())}_Human"
                    rb_payload = {
                        "move": "ConditionalOffer",
                        "offer_id": offer_id,
                        "conditions": conditions,
                        "assignments": assignments,
                        "reasons": ["human_proposed"]
                    }
                    rb_msg = f'[rb:{json.dumps(rb_payload)}]'

                    print(f"[RB UI] Sending conditional offer: {len(conditions)} conditions, {len(assignments)} assignments")

                    # Track human's sent offer
                    self._human_sent_offers.append({
                        "offer_id": offer_id,
                        "sender": "Human",
                        "recipient": n,
                        "conditions": conditions,
                        "assignments": assignments,
                        "status": "pending"
                    })
                    # Update sidebar to show it
                    if self._root:
                        self._root.after(0, self._render_conditional_cards)

                    # Append to transcript for display
                    try:
                        if conditions:
                            cond_str = " AND ".join([f"{c['node']}={c['colour']}" for c in conditions])
                            assign_str = " AND ".join([f"{a['node']}={a['colour']}" for a in assignments])
                            display_msg = f"[You → {n}] IF {cond_str} THEN {assign_str}"
                        else:
                            assign_str = " AND ".join([f"{a['node']}={a['colour']}" for a in assignments])
                            display_msg = f"[You → {n}] Offer: {assign_str}"
                        self._append_to_transcript(n, display_msg)
                    except Exception as e:
                        print(f"[RB UI] Transcript update error: {e}")

                    # Send message directly (no text box involved)
                    if self._on_send:
                        self._status_var[n].set("waiting for reply...")
                        root.update_idletasks()

                        def _threaded_send():
                            reply = None
                            try:
                                print(f"[RB UI] Calling on_send for {n}")
                                sig = inspect.signature(self._on_send)
                                params = sig.parameters
                                if len(params) >= 3:
                                    reply = self._on_send(n, rb_msg, dict(self._assignments))
                                else:
                                    reply = self._on_send(n, rb_msg)
                                print(f"[RB UI] on_send returned: {reply[:100] if reply else 'None'}")
                            except Exception as e:
                                print(f"[RB UI] Send error: {e}")
                                import traceback
                                traceback.print_exc()
                            finally:
                                if self._root:
                                    # Add reply to incoming queue if present
                                    if reply:
                                        self._root.after(0, lambda: self.add_incoming(n, reply))
                                    else:
                                        self._root.after(0, lambda: self._status_var[n].set("idle"))

                        threading.Thread(target=_threaded_send, daemon=True).start()
                    else:
                        print(f"[RB UI] ERROR: No on_send callback registered!")

                btn_frame = ttk.Frame(rb_frame)
                btn_frame.pack(fill="x", padx=4, pady=6)

                # Pass button - lets agent speak without human input
                def pass_turn(n=neigh):
                    """Pass turn to agent without sending a message."""
                    print(f"[RB UI] Human passed turn to {n}")
                    if self._on_send:
                        self._status_var[n].set("...thinking...")

                        def _threaded_pass():
                            reply = None
                            try:
                                # Send special __PASS__ token - agent will step without receiving human message
                                sig = inspect.signature(self._on_send)
                                params = sig.parameters
                                if len(params) >= 3:
                                    reply = self._on_send(n, "__PASS__", dict(self._assignments))
                                else:
                                    reply = self._on_send(n, "__PASS__")
                            except Exception as e:
                                print(f"[RB UI] Pass error: {e}")
                            finally:
                                if self._root:
                                    if reply:
                                        self._root.after(0, lambda: self.add_incoming(n, reply))
                                    else:
                                        self._root.after(0, lambda: self._status_var[n].set("idle"))

                        threading.Thread(target=_threaded_pass, daemon=True).start()

                pass_btn = ttk.Button(btn_frame, text="Pass (let agent speak)", command=lambda fn=pass_turn: fn())
                pass_btn.pack(side="left", padx=(0, 5))

                # Send offer button
                send = ttk.Button(btn_frame, text="Send Offer", command=lambda fn=send_rb_message: fn())
                send.pack(side="left")
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

                # Button frame to hold Send and Send Config buttons
                btn_frame = ttk.Frame(pane)
                btn_frame.pack(anchor="e", padx=6, pady=(0, 6))

                # Send Config button - broadcasts actual current assignments (no message)
                send_config = ttk.Button(btn_frame, text="Send Config",
                                        command=lambda n=neigh: self._send_config(n))
                send_config.pack(side="left", padx=(0, 4))

                # Send message button
                send = ttk.Button(btn_frame, text="Send", command=lambda n=neigh: self._send_message(n))
                send.pack(side="left")
                self._send_btn[neigh] = send

        root.update_idletasks()
        self._compute_layout()
        self._redraw_graph()

    def _build_conditionals_sidebar(self, parent: ttk.Frame) -> None:
        """Build the conditionals sidebar UI for displaying active conditional offers."""

        # Configuration Status Section (at top)
        config_section = ttk.LabelFrame(parent, text="Configuration Status")
        config_section.pack(fill="x", padx=5, pady=(5, 10))

        config_inner = tk.Frame(config_section, bg="white")
        config_inner.pack(fill="x", padx=5, pady=5)
        self._config_status_frame = config_inner

        # Conditionals Section (below configurations)
        title_label = tk.Label(
            parent,
            text="Active Conditionals",
            font=("Arial", 12, "bold"),
            bg="#f8f8f8"
        )
        title_label.pack(pady=5, padx=5, anchor="w")

        # Scrollable container for conditional cards
        canvas_container = ttk.Frame(parent)
        canvas_container.pack(fill="both", expand=True, padx=5, pady=5)

        canvas = tk.Canvas(canvas_container, bg="white", highlightthickness=1, highlightbackground="#ccc")
        scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Inner frame for cards
        inner_frame = tk.Frame(canvas, bg="white")
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        # Store reference for later updates
        self._conditionals_cards_inner = inner_frame
        self._conditionals_canvas = canvas

        # Bind resize to update scroll region
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind("<Configure>", on_frame_configure)

        # Bind canvas width to inner frame width
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", on_canvas_configure)

        # Add info label when no conditionals
        no_conditionals_label = tk.Label(
            inner_frame,
            text="No active conditional offers",
            fg="gray",
            font=("Arial", 10, "italic"),
            bg="white"
        )
        no_conditionals_label.pack(pady=20)
        self._no_conditionals_label = no_conditionals_label

    def _render_configuration_status(self) -> None:
        """Render configuration announcements compactly in the status section."""
        if not hasattr(self, '_config_status_frame') or self._config_status_frame is None:
            return

        # Clear existing
        for widget in self._config_status_frame.winfo_children():
            widget.destroy()

        if not self._agent_configurations:
            tk.Label(
                self._config_status_frame,
                text="No configurations announced yet",
                fg="gray",
                font=("Arial", 9, "italic"),
                bg="white"
            ).pack(pady=5)
            return

        # Show each agent's configuration compactly
        for agent, config in self._agent_configurations.items():
            agent_frame = tk.Frame(self._config_status_frame, bg="#e8f4f8",
                                   relief=tk.SOLID, borderwidth=1)
            agent_frame.pack(fill="x", pady=2)

            # Agent name
            tk.Label(
                agent_frame,
                text=f"📢 {agent}:",
                font=("Arial", 9, "bold"),
                bg="#e8f4f8"
            ).pack(side="left", padx=5, pady=3)

            # Compact assignment list
            config_text = ", ".join([f"{node}={color}" for node, color in config.items()])
            tk.Label(
                agent_frame,
                text=config_text,
                font=("Arial", 9),
                bg="#e8f4f8"
            ).pack(side="left", padx=5, pady=3)

    def _render_conditional_cards(self) -> None:
        """Render conditional offers as cards in the sidebar."""
        if self._conditionals_cards_inner is None:
            return

        # Clear existing cards
        for widget in self._conditionals_cards_inner.winfo_children():
            widget.destroy()

        # Combine both incoming and outgoing offers
        all_offers = []

        # Add human's sent offers (outgoing) - only conditional ones
        for offer in self._human_sent_offers:
            conditions = offer.get("conditions", [])
            # Skip unconditional offers (no IF part) - only show conditional bargaining
            if not conditions or len(conditions) == 0:
                print(f"[UI Cards] Skipping human unconditional offer: {offer.get('offer_id')}")
                continue
            all_offers.append({
                **offer,
                "direction": "outgoing"
            })

        # Add agent's offers (incoming), but FILTER OUT configurations and unconditionals
        for offer in self._active_conditionals:
            sender = offer.get("sender", "")
            conditions = offer.get("conditions", [])

            # Skip unconditional offers (no IF part) - only show conditional bargaining
            if not conditions or len(conditions) == 0:
                print(f"[UI Cards] Skipping agent unconditional offer from {sender}: {offer.get('offer_id')}")
                continue

            # Check if this offer matches a configuration announcement
            # If sender has a config and all offer assignments match the config, skip it
            if sender in self._agent_configurations:
                offer_assigns = offer.get("assignments", [])
                config_assigns = self._agent_configurations[sender]

                # Check if ALL assignments in this offer match the configuration
                is_config = all(
                    a.get("node") in config_assigns and
                    config_assigns[a.get("node")] == a.get("colour")
                    for a in offer_assigns
                )

                if is_config and len(offer_assigns) == len(config_assigns):
                    # This is the configuration announcement - skip it
                    continue

            all_offers.append({
                **offer,
                "direction": "incoming"
            })

        # Show "no conditionals" message if empty
        if not all_offers:
            no_label = tk.Label(
                self._conditionals_cards_inner,
                text="No active conditional offers",
                fg="gray",
                font=("Arial", 10, "italic"),
                bg="white"
            )
            no_label.pack(pady=20)
            return

        # Render each conditional as a card
        for idx, cond in enumerate(all_offers):
            direction = cond.get("direction", "incoming")

            # Determine card color based on direction and status
            if direction == "outgoing":
                if cond.get("status") == "accepted":
                    card_bg = "#90ee90"  # Light green (accepted)
                else:
                    card_bg = "#e6f3ff"  # Light blue (your offer, pending)
            else:
                if cond.get("status") == "accepted":
                    card_bg = "#90ee90"  # Light green (accepted)
                else:
                    card_bg = "#fffacd"  # Light yellow (their offer, pending)

            # Create card frame
            card = tk.Frame(
                self._conditionals_cards_inner,
                bg=card_bg,
                relief=tk.RAISED,
                borderwidth=2
            )
            card.pack(fill="x", padx=5, pady=5)

            # Offer ID header with direction indicator
            if direction == "outgoing":
                direction_arrow = "→"
                recipient = cond.get('recipient', 'Agent')
                header_text = f"Offer #{idx+1} {direction_arrow} {recipient}"
            else:
                direction_arrow = "←"
                sender = cond.get('sender', 'Unknown')
                header_text = f"Offer #{idx+1} {direction_arrow} {sender}"

            tk.Label(
                card,
                text=header_text,
                font=("Arial", 9, "bold"),
                bg=card_bg
            ).pack(anchor="w", padx=5, pady=2)

            # Conditions section (IF)
            if "conditions" in cond and cond["conditions"]:
                tk.Label(
                    card,
                    text="IF:",
                    font=("Arial", 8, "bold"),
                    bg=card_bg
                ).pack(anchor="w", padx=10, pady=(5, 0))

                for condition in cond["conditions"]:
                    cond_text = f"  • {condition.get('node', '?')} = {condition.get('colour', '?')}"
                    tk.Label(
                        card,
                        text=cond_text,
                        font=("Arial", 8),
                        bg=card_bg
                    ).pack(anchor="w", padx=15)

            # Assignments section (THEN)
            if "assignments" in cond and cond["assignments"]:
                tk.Label(
                    card,
                    text="THEN:",
                    font=("Arial", 8, "bold"),
                    bg=card_bg
                ).pack(anchor="w", padx=10, pady=(5, 0))

                for assignment in cond["assignments"]:
                    assign_text = f"  • {assignment.get('node', '?')} = {assignment.get('colour', '?')}"
                    tk.Label(
                        card,
                        text=assign_text,
                        font=("Arial", 8),
                        bg=card_bg
                    ).pack(anchor="w", padx=15)

            # Action buttons (only for incoming offers)
            btn_frame = tk.Frame(card, bg=card_bg)
            btn_frame.pack(fill="x", padx=5, pady=5)

            if direction == "outgoing":
                # For outgoing offers, just show status
                if cond.get("status") == "accepted":
                    tk.Label(
                        btn_frame,
                        text="✓ They accepted",
                        fg="green",
                        font=("Arial", 9, "bold"),
                        bg=card_bg
                    ).pack(side="left")
                else:
                    tk.Label(
                        btn_frame,
                        text="⏳ Waiting for response...",
                        fg="#666",
                        font=("Arial", 9, "italic"),
                        bg=card_bg
                    ).pack(side="left")
            else:
                # For incoming offers, show Accept/Counter buttons
                if cond.get("status") == "pending":
                    ttk.Button(
                        btn_frame,
                        text="Accept",
                        command=lambda oid=cond.get("offer_id"): self._accept_offer(oid)
                    ).pack(side="left", padx=2)

                    ttk.Button(
                        btn_frame,
                        text="Counter",
                        command=lambda oid=cond.get("offer_id"): self._counter_offer(oid)
                    ).pack(side="left", padx=2)
                else:
                    tk.Label(
                        btn_frame,
                        text="✓ Accepted",
                        fg="green",
                        font=("Arial", 9, "bold"),
                        bg=card_bg
                    ).pack(side="left")

        # Update scroll region
        if self._conditionals_cards_inner and self._conditionals_canvas:
            self._conditionals_cards_inner.update_idletasks()
            self._conditionals_canvas.configure(
                scrollregion=self._conditionals_canvas.bbox("all")
            )

    def update_conditionals(self, conditionals: List[Dict[str, Any]]) -> None:
        """Update sidebar with latest conditionals from agents.

        This method should be called from the simulation to update the UI.
        """
        self._active_conditionals = conditionals
        if self._root is not None:
            self._root.after(0, self._render_conditional_cards)

    def update_configurations(self, configurations: List[Dict[str, Any]]) -> None:
        """Update agent configurations from announcements.

        Parameters
        ----------
        configurations : list
            List of configuration announcement dicts with sender, assignments fields.
        """
        # Convert list to dict keyed by agent name
        self._agent_configurations = {}
        for config in configurations:
            agent = config.get("sender", "")
            assignments = config.get("assignments", [])

            if agent not in self._agent_configurations:
                self._agent_configurations[agent] = {}

            for assign in assignments:
                node = assign.get("node", "")
                colour = assign.get("colour", "")
                if node and colour:
                    self._agent_configurations[agent][node] = colour

        # Trigger UI refresh
        if self._root is not None:
            self._root.after(0, self._render_configuration_status)

    def _accept_offer(self, offer_id: str) -> None:
        """Handle accepting a conditional offer."""
        # Find the offer and determine which neighbor sent it
        sender = None
        offer = None
        for cond in self._active_conditionals:
            if cond.get("offer_id") == offer_id:
                sender = cond.get("sender")
                offer = cond
                break

        if sender and offer:
            # Apply conditions: change OUR assignments to fulfill our side of the deal
            conditions = offer.get("conditions", [])
            for cond in conditions:
                node = cond.get("node")
                colour = cond.get("colour")
                if node and colour and node in self._assignments:
                    self._assignments[node] = colour
                    print(f"[Human Accept] Changed assignment: {node}={colour}")

            # Update graph display
            self._redraw_graph()

            # Mark offer as accepted in UI
            offer["status"] = "accepted"
            self._render_conditional_cards()

            # Send Accept message via RB protocol
            try:
                from comm.rb_protocol import RBMove, format_rb, pretty_rb
                accept_move = RBMove(
                    move="Accept",
                    refers_to=offer_id,
                    reasons=["human_accepted"]
                )
                msg_text = format_rb(accept_move) + " " + pretty_rb(accept_move)

                # Append to transcript
                self._append_to_transcript(sender, f"[You → {sender}] Accept offer #{offer_id}")

                # Send via the normal message pipeline
                if self._on_send:
                    threading.Thread(
                        target=lambda: self._invoke_on_send(sender, msg_text),
                        daemon=True
                    ).start()
                    self._set_status(sender, "sending...")
            except Exception as e:
                print(f"Error accepting offer: {e}")

    def _counter_offer(self, offer_id: str) -> None:
        """Handle countering a conditional offer."""
        # For now, just show a message - full counter-offer UI would be more complex
        # In a real implementation, this would open a dialog to build a counter-proposal
        print(f"Counter offer for {offer_id} - UI not yet implemented")
        # TODO: Open dialog to build counter-proposal

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
        self._redraw_graph()

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

    def _redraw_graph(self) -> None:
        """Redraw graph with zoom and pan transformations applied."""
        canvas = self._canvas
        if canvas is None:
            return
        canvas.delete("all")
        self._edge_items.clear()
        self._node_items.clear()

        # Get current transformations
        scale = self._graph_canvas_scale
        offset_x, offset_y = self._graph_canvas_offset

        # Draw edges with transformations
        for u, v in self._edges:
            if u not in self._node_pos or v not in self._node_pos:
                continue
            x1, y1 = self._node_pos[u]
            x2, y2 = self._node_pos[v]

            # Apply transformations
            x1 = x1 * scale + offset_x
            y1 = y1 * scale + offset_y
            x2 = x2 * scale + offset_x
            y2 = y2 * scale + offset_y

            cu = self._assignments.get(u)
            cv = self._assignments.get(v)
            if cv is None and v in self._known_neighbour_colours:
                cv = self._known_neighbour_colours[v]
            if cu is None and u in self._known_neighbour_colours:
                cu = self._known_neighbour_colours[u]

            clash = (cu is not None and cv is not None and str(cu) == str(cv))
            color = "#cc0000" if clash else "#999999"
            width = max(1, int((3 if clash else 1) * scale))
            item = canvas.create_line(x1, y1, x2, y2, fill=color, width=width)
            self._edge_items.append((u, v, item))

        # Draw nodes with transformations
        for n, (x, y) in self._node_pos.items():
            # Apply transformations
            tx = x * scale + offset_x
            ty = y * scale + offset_y

            is_owned = (self._owners.get(n) == "Human")
            r = int((24 if is_owned else 18) * scale)
            col = self._assignments.get(n)
            if col is None and n in self._known_neighbour_colours:
                col = self._known_neighbour_colours[n]
                print(f"[Graph] Using announced color for {n}: {col}")

            fill = self._colour_fill(col)
            outline = "#222222" if is_owned else "#666666"
            ow = self._outline_width_for_colour(col) if col is not None else 2
            ow = max(1, int(ow * scale))
            item = canvas.create_oval(tx - r, ty - r, tx + r, ty + r, fill=fill, outline=outline, width=ow)
            self._node_items[n] = item

            font_size = max(6, int((10 if is_owned else 9) * scale))
            canvas.create_text(tx, ty, text=f"{n}", font=("TkDefaultFont", font_size))

            # Visual indicators for fixed (immutable) nodes
            if hasattr(self, '_fixed_nodes') and n in self._fixed_nodes:
                # Orange dashed ring around fixed nodes
                ring_offset = int(4 * scale)
                canvas.create_oval(tx - r - ring_offset, ty - r - ring_offset,
                                 tx + r + ring_offset, ty + r + ring_offset,
                                 outline="#FF8C00", width=max(1, int(3 * scale)),
                                 dash=(3, 2), fill="")
                # Lock icon
                lock_font_size = max(6, int(10 * scale))
                canvas.create_text(tx + r - int(8 * scale), ty - r + int(8 * scale),
                                 text="🔒", font=("TkDefaultFont", lock_font_size))
            # Visual indicators for committed (soft-locked) nodes
            elif hasattr(self, '_committed_nodes') and n in self._committed_nodes:
                # Gold ring around committed nodes (thicker than fixed, solid)
                ring_offset = int(2 * scale)
                canvas.create_oval(tx - r - ring_offset, ty - r - ring_offset,
                                 tx + r + ring_offset, ty + r + ring_offset,
                                 outline="#FFD700", width=max(1, int(3 * scale)), fill="")
                # Small lock icon (different from fixed - smaller and in corner)
                lock_font_size = max(5, int(8 * scale))
                canvas.create_text(tx + r - int(5 * scale), ty - r + int(5 * scale),
                                 text="🔒", font=("TkDefaultFont", lock_font_size))

    def _on_canvas_click(self, ev: tk.Event) -> None:
        # Skip if shift is held (panning mode)
        if ev.state & 0x0001:
            return

        x, y = ev.x, ev.y

        # Transform mouse coordinates to graph space
        offset_x, offset_y = self._graph_canvas_offset
        scale = self._graph_canvas_scale
        graph_x = (x - offset_x) / scale
        graph_y = (y - offset_y) / scale

        best = None
        best_d = 10**9
        for n, (nx, ny) in self._node_pos.items():
            d = (nx - graph_x) ** 2 + (ny - graph_y) ** 2
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
        self._redraw_graph()
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
        print(f"[Transcript] Appending to transcript for neighbor '{neigh}': {line[:100]}")

        # In structured RB mode, also parse and store the argument structure
        is_structured_rb = getattr(self, '_rb_structured_mode', False)
        print(f"[Transcript] is_structured_rb: {is_structured_rb}")
        if is_structured_rb:
            print(f"[Transcript] Calling _parse_and_store_rb_move for neighbor '{neigh}'")
            self._parse_and_store_rb_move(neigh, line)

        if self._root is not None:
            self._root.after(0, lambda n=neigh: self._refresh_transcript(n))

    def _refresh_transcript(self, neigh: str) -> None:
        widget = self._transcript_box.get(neigh)
        if widget is None:
            return

        # Check if this is structured RB mode (canvas) or text mode
        is_structured_rb = getattr(self, '_rb_structured_mode', False)

        if is_structured_rb and isinstance(widget, tk.Canvas):
            # Render argument graph on canvas
            self._render_argument_graph(neigh, widget)
        else:
            # Standard text transcript
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            for ln in self._transcripts.get(neigh, []):
                widget.insert("end", ln + "\n")
            widget.configure(state="disabled")
            widget.see("end")

    def _parse_and_store_rb_move(self, neigh: str, line: str) -> None:
        """Parse an RB move from transcript line and store it in the argument structure."""
        import re
        import json

        print(f"[RB UI] Parsing line: {line[:120]}")

        # Extract sender from line format: "[You → Agent1] Propose h1=red" or "[Agent1] Propose a2=blue"
        sender = "You"
        if line.startswith("[You"):
            sender = "You"
        elif line.startswith("["):
            match = re.match(r'\[([^\]]+)\]', line)
            if match:
                full_sender = match.group(1)
                # Strip arrow recipient if present: "Agent1 → Human" → "Agent1"
                if '→' in full_sender:
                    sender = full_sender.split('→')[0].strip()
                else:
                    sender = full_sender.strip()
                print(f"[RB UI Parse] Extracted sender: '{sender}' from bracket content: '{full_sender}'")
        else:
            print(f"[RB UI Parse] Extracted sender: '{sender}' from line starting with: {line[:50]}")

        # Try to extract from RB protocol tag first: [rb:{"move":"Propose","node":"h1","colour":"red","reasons":[]}]
        # Updated to handle ConditionalOffer with nested JSON
        rb_match = re.search(r'\[rb:(\{.+\})\]', line, re.DOTALL)
        if rb_match:
            try:
                rb_data = json.loads(rb_match.group(1))
                move_type = rb_data.get("move", "")

                # Handle ConditionalOffer specially (has conditions/assignments, not single node/color)
                if move_type == "ConditionalOffer":
                    print(f"[RB UI] Processing ConditionalOffer from {sender}")
                    conditions = rb_data.get("conditions", [])
                    assignments = rb_data.get("assignments", [])
                    offer_id = rb_data.get("offer_id", "")
                    print(f"[RB UI] ConditionalOffer details: conditions={len(conditions)}, assignments={len(assignments)}, offer_id={offer_id}")

                    arg = {
                        "sender": sender,
                        "move": "ConditionalOffer",
                        "node": "conditional",  # Placeholder for layout
                        "color": "",
                        "conditions": conditions,
                        "assignments": assignments,
                        "offer_id": offer_id,
                        "reasons": rb_data.get("reasons", []),  # Store reasons for filtering
                        "index": len(self._rb_arguments.get(neigh, [])),
                        "justification_refs": []
                    }
                    print(f"[RB UI] Parsed ConditionalOffer: sender='{sender}', neigh='{neigh}', {len(conditions)} conditions, {len(assignments)} assignments")
                    self._rb_arguments.setdefault(neigh, []).append(arg)
                    print(f"[RB UI] Added arg to _rb_arguments['{neigh}'], now has {len(self._rb_arguments[neigh])} args")
                    print(f"[RB UI] STORED ARG: {arg}")
                    print(f"[RB UI] ALL _rb_arguments KEYS: {list(self._rb_arguments.keys())}")
                    for key, val in self._rb_arguments.items():
                        print(f"[RB UI]   Key '{key}' has {len(val)} args, senders: {[a.get('sender') for a in val]}")

                    # Update known neighbor colors from assignments
                    # (So graph shows their announced colors)
                    for assignment in assignments:
                        node = assignment.get("node", "")
                        colour = assignment.get("colour", "")
                        if node and colour:
                            # Only update if it's not our node
                            if self._owners.get(node) != "Human":
                                self._known_neighbour_colours[node] = colour
                                print(f"[RB UI] Updated neighbor color: {node}={colour}")

                    # Debug: Show all known colors after update
                    print(f"[RB UI] All known colors: {self._known_neighbour_colours}")

                    # Redraw graph to show updated colors (immediate call, not scheduled)
                    self._redraw_graph()

                    # If this looks like initial configuration (all assignments, no conditions, reasons include "initial_configuration")
                    reasons = rb_data.get("reasons", [])
                    if not conditions and assignments and "initial_configuration" in reasons:
                        # Replace the transcript entry with a pretty announcement
                        config_summary = ", ".join([f"{a['node']}={a['colour']}" for a in assignments])
                        announcement_text = f"[{sender}] 📢 Configuration Announced: {config_summary}"

                        # Replace the last transcript entry (which was the technical message) with pretty version
                        if neigh in self._transcripts and self._transcripts[neigh]:
                            self._transcripts[neigh][-1] = announcement_text

                        print(f"[RB UI] Configuration announced by {sender}: {config_summary}")

                    # Check for auto-convergence
                    if hasattr(self, '_rb_mode') and self._rb_mode:
                        self._check_consensus()

                    return

                # Standard moves (Propose, CounterProposal, Commit, etc.)
                arg = {
                    "sender": sender,
                    "move": move_type,
                    "node": rb_data.get("node", ""),
                    "color": rb_data.get("colour", ""),
                    "index": len(self._rb_arguments.get(neigh, [])),
                    "justification_refs": self._rb_pending_justification_refs.get(neigh, [])
                }
                # Clear pending justification refs after use
                self._rb_pending_justification_refs[neigh] = []
                print(f"[RB UI] Parsed RB protocol: {arg}")
                self._rb_arguments.setdefault(neigh, []).append(arg)

                # Check for auto-convergence in RB mode
                if hasattr(self, '_rb_mode') and self._rb_mode:
                    self._check_consensus()

                return
            except Exception as e:
                print(f"[RB UI] Failed to parse RB protocol: {e}")

        # Fallback: Extract move, node, color from line like "Propose h1=red"
        # Format: "[sender] Move node=color"
        parts = line.split("] ", 1)
        if len(parts) < 2:
            print(f"[RB UI] Could not split line into sender and content")
            return

        content = parts[1].strip()
        # Parse "Propose h1=red" or "Challenge a2=blue" etc
        move_match = re.match(r'(\w+)\s+(\w+)=(\w+)', content)
        if not move_match:
            print(f"[RB UI] Could not parse content: {content[:80]}")
            return

        move_type = move_match.group(1)
        node = move_match.group(2)
        color = move_match.group(3)

        # Store the argument
        arg = {
            "sender": sender,
            "move": move_type,
            "node": node,
            "color": color,
            "index": len(self._rb_arguments.get(neigh, [])),
            "justification_refs": self._rb_pending_justification_refs.get(neigh, [])
        }

        # Clear pending justification refs after use
        self._rb_pending_justification_refs[neigh] = []

        print(f"[RB UI] Parsed fallback format: {arg}")
        self._rb_arguments.setdefault(neigh, []).append(arg)

        # Check for auto-convergence in RB mode
        if hasattr(self, '_rb_mode') and self._rb_mode:
            self._check_consensus()

    def _render_argument_graph(self, neigh: str, canvas: tk.Canvas) -> None:
        """Render the argument graph as a tree with zoom/pan support."""
        canvas.delete("all")
        args = self._rb_arguments.get(neigh, [])

        # Store current neighbor for helper methods
        self._current_neigh_for_render = neigh

        # Get zoom/pan state
        scale = self._rb_canvas_scale.get(neigh, 1.0)
        offset_x, offset_y = self._rb_canvas_offset.get(neigh, (0, 0))

        move_colors = {
            "Propose": "#d0e8ff",   # Light blue
            "Challenge": "#ffd0d0",  # Light red
            "Justify": "#d0ffd0",    # Light green
            "Commit": "#ffe0b0",     # Light orange
            "ConditionalOffer": "#e8d0ff",  # Light purple
            "CounterProposal": "#ffe0d0",   # Light peach
            "Accept": "#d0ffe0"      # Light mint
        }

        # Draw legend (not scaled, fixed position) - Multiple rows for new moves
        legend_y = 5
        legend_x = 10
        canvas.create_text(legend_x, legend_y, text="Legend:", font=("Arial", 8, "bold"), anchor="nw", fill="#333", tags="legend")

        # Row 1: Original moves
        legend_items_row1 = [
            ("Propose", move_colors["Propose"]),
            ("Commit", move_colors["Commit"]),
            ("CounterProp", move_colors["CounterProposal"])
        ]
        for i, (label, color) in enumerate(legend_items_row1):
            x_pos = legend_x + 50 + (i * 90)
            canvas.create_rectangle(x_pos, legend_y, x_pos + 12, legend_y + 12, fill=color, outline="#666", tags="legend")
            canvas.create_text(x_pos + 16, legend_y + 6, text=label, font=("Arial", 7), anchor="w", fill="#000", tags="legend")

        # Row 2: New moves
        legend_y2 = legend_y + 16
        legend_items_row2 = [
            ("Conditional", move_colors["ConditionalOffer"]),
            ("Accept", move_colors["Accept"])
        ]
        for i, (label, color) in enumerate(legend_items_row2):
            x_pos = legend_x + 50 + (i * 90)
            canvas.create_rectangle(x_pos, legend_y2, x_pos + 12, legend_y2 + 12, fill=color, outline="#666", tags="legend")
            canvas.create_text(x_pos + 16, legend_y2 + 6, text=label, font=("Arial", 7), anchor="w", fill="#000", tags="legend")

        # Add justification link legend (second row)
        just_legend_y = legend_y + 18
        canvas.create_text(legend_x + 50, just_legend_y,
                         text="⚡ = Justification link (cross-node)",
                         font=("Arial", 7), anchor="w", fill="#9933cc", tags="legend")

        # Draw zoom indicator
        canvas.create_text(canvas.winfo_width() - 60, legend_y,
                         text=f"Zoom: {scale:.1f}x",
                         font=("Arial", 8), anchor="ne", fill="#555", tags="legend")

        if not args:
            canvas.create_text(150, 100,
                             text="No arguments yet\n(scroll wheel to zoom, shift+drag to pan)",
                             font=("Arial", 10), fill="gray", justify="center", tags="legend")
            return

        # Group arguments by node (column-based layout)
        box_width = 180
        box_height = 60
        column_spacing = 220  # Space between node columns
        v_spacing = 30  # Vertical space between arguments

        positions = self._layout_by_node_columns(args, box_width, box_height, column_spacing, v_spacing)

        # Draw column headers for each node
        node_groups = {}
        node_order = []
        for idx, arg in enumerate(args):
            node = arg.get("node")
            if not node:
                continue
            if node not in node_groups:
                node_order.append(node)
                node_groups[node] = []
            node_groups[node].append(idx)

        base_x = 100
        for col_idx, node in enumerate(node_order):
            x = base_x + col_idx * column_spacing
            header_x = x * scale + offset_x
            header_y = 50  # Fixed position above arguments
            canvas.create_text(header_x, header_y,
                             text=f"Node: {node}",
                             font=("Arial", 12, "bold"), fill="#333",
                             tags="header")

        # Draw parent-child edges (only within same node column)
        for idx, arg in enumerate(args):
            if arg.get("parent_idx") is not None:
                parent_idx = arg["parent_idx"]
                if idx in positions and parent_idx in positions:
                    # Only draw edge if both are about the same node
                    if args[idx]["node"] == args[parent_idx]["node"]:
                        # Get positions
                        x1, y1 = positions[parent_idx]
                        x2, y2 = positions[idx]

                        # Apply scale and offset
                        x1 = x1 * scale + offset_x
                        y1 = y1 * scale + offset_y + 30  # Offset for legend
                        x2 = x2 * scale + offset_x
                        y2 = y2 * scale + offset_y + 30

                        # Edge from bottom of parent to top of child
                        parent_bottom_y = y1 + (box_height * scale) / 2
                        child_top_y = y2 - (box_height * scale) / 2

                        # Arrow color based on move type
                        move = arg["move"]
                        arrow_color = "#cc0000" if move == "Challenge" else "#00aa00" if move == "Justify" else "#0066cc"
                        arrow_width = max(1, int(2 * scale))

                        # Draw edge
                        canvas.create_line(x1, parent_bottom_y, x1, (parent_bottom_y + child_top_y) / 2,
                                         x2, (parent_bottom_y + child_top_y) / 2, x2, child_top_y,
                                         smooth=False, arrow="last", fill=arrow_color, width=arrow_width, tags="edge")

        # Draw justification edges (cross-node causal links)
        for idx, arg in enumerate(args):
            justification_refs = arg.get("justification_refs", [])
            if justification_refs and idx in positions:
                for ref_idx in justification_refs:
                    if ref_idx < len(args) and ref_idx in positions:
                        # Get positions
                        x1, y1 = positions[idx]  # Source (current argument)
                        x2, y2 = positions[ref_idx]  # Target (justification)

                        # Apply scale and offset
                        x1 = x1 * scale + offset_x
                        y1 = y1 * scale + offset_y + 30
                        x2 = x2 * scale + offset_x
                        y2 = y2 * scale + offset_y + 30

                        # Draw dashed purple arrow from source to justification
                        # Use different routing from parent edges to avoid overlap
                        arrow_width = max(1, int(2 * scale))

                        # Draw curved dashed line
                        canvas.create_line(x1, y1, (x1 + x2) / 2, (y1 + y2) / 2, x2, y2,
                                         smooth=True, arrow="last", fill="#9933cc",
                                         width=arrow_width, dash=(8, 4), tags="justification")

        # Draw argument boxes
        for idx, arg in enumerate(args):
            if idx not in positions:
                continue

            move = arg["move"]
            node = arg["node"]
            color = arg["color"]
            sender = arg["sender"]

            # Get position and apply transformations
            x, y = positions[idx]
            x = x * scale + offset_x
            y = y * scale + offset_y + 30  # Offset for legend

            # Draw box
            box_color = move_colors.get(move, "#f0f0f0")
            w = box_width * scale
            h = box_height * scale
            x1, y1 = x - w/2, y - h/2
            x2, y2 = x + w/2, y + h/2

            canvas.create_rectangle(x1, y1, x2, y2,
                                  fill=box_color, outline="#666", width=max(1, int(2 * scale)), tags="box")

            # Draw text (scale font sizes)
            font_size_move = max(7, int(10 * scale))
            font_size_sender = max(6, int(8 * scale))
            font_size_content = max(8, int(11 * scale))

            # Move type (top left)
            canvas.create_text(x1 + 8*scale, y1 + 8*scale,
                             text=f"{move}",
                             font=("Arial", font_size_move, "bold"),
                             anchor="nw", fill="#000", tags="text")

            # Sender (top right)
            canvas.create_text(x2 - 8*scale, y1 + 8*scale,
                             text=f"({sender})",
                             font=("Arial", font_size_sender),
                             anchor="ne", fill="#555", tags="text")

            # Node and color (center) - special handling for ConditionalOffer
            if move == "ConditionalOffer":
                conditions = arg.get("conditions", [])
                assignments = arg.get("assignments", [])
                # Show summary: "If X conds → Y assigns"
                text = f"IF: {len(conditions)} conds\n→ THEN: {len(assignments)} assigns"
                canvas.create_text(x, y,
                                 text=text,
                                 font=("Arial", max(7, int(9 * scale))),
                                 anchor="center", fill="#000", tags="text")
            else:
                # Standard moves: show node = color
                canvas.create_text(x, y + 5*scale,
                                 text=f"{node} = {color}",
                                 font=("Arial", font_size_content, "bold"),
                                 anchor="center", fill="#000", tags="text")

            # Justification refs (bottom, if present)
            justification_refs = arg.get("justification_refs", [])
            if justification_refs:
                font_size_refs = max(6, int(7 * scale))
                refs_text = "⚡ Refs: " + ", ".join(f"#{r}" for r in justification_refs)
                canvas.create_text(x, y2 - 8*scale,
                                 text=refs_text,
                                 font=("Arial", font_size_refs),
                                 anchor="s", fill="#9933cc", tags="text")

    def _build_argument_tree(self, args: List[Dict[str, Any]]) -> Dict[int, List[int]]:
        """Build tree structure from flat argument list.

        Returns
        -------
        Dict[int, List[int]]
            Mapping from parent index to list of child indices.
        """
        tree = {}
        for idx, arg in enumerate(args):
            move = arg["move"]
            node = arg["node"]

            # Find parent: most recent Propose/Challenge on same node
            parent_idx = None
            if move in ("Challenge", "Justify", "Commit"):
                for prev_idx in range(idx - 1, -1, -1):
                    prev_arg = args[prev_idx]
                    if prev_arg["node"] == node and prev_arg["move"] in ("Propose", "Challenge"):
                        parent_idx = prev_idx
                        break

            # Store parent relationship
            arg["parent_idx"] = parent_idx

            # Build tree mapping
            if parent_idx is not None:
                tree.setdefault(parent_idx, []).append(idx)

        return tree

    def _layout_by_node_columns(self, args: List[Dict], box_width: int, box_height: int,
                                column_spacing: int, v_spacing: int) -> Dict[int, Tuple[int, int]]:
        """Layout arguments in columns by node.

        Each node gets its own column, and arguments about that node are stacked vertically.
        This makes it clear which arguments pertain to which node.

        Returns dict mapping argument index to (x, y) position.
        """
        if not args:
            return {}

        # Group arguments by node
        node_groups = {}  # {node: [arg_indices]}
        node_order = []  # Track order of first appearance

        for idx, arg in enumerate(args):
            node = arg.get("node")
            if not node:
                continue
            if node not in node_groups:
                node_order.append(node)
                node_groups[node] = []
            node_groups[node].append(idx)

        # Assign columns to nodes
        positions = {}
        base_x = 100  # Start position

        for col_idx, node in enumerate(node_order):
            arg_indices = node_groups[node]
            x = base_x + col_idx * column_spacing

            # Stack arguments vertically in this column
            for local_idx, arg_idx in enumerate(arg_indices):
                y = 80 + local_idx * (box_height + v_spacing)
                positions[arg_idx] = (x, y)

        return positions

    def _layout_tree(self, tree: Dict[int, List[int]], box_width: int, box_height: int,
                    h_spacing: int, v_spacing: int) -> Dict[int, Tuple[int, int]]:
        """Compute positions for tree layout.

        Uses a simple layered tree layout where each level is placed vertically,
        and siblings are spread horizontally.

        Returns
        -------
        Dict[int, Tuple[int, int]]
            Mapping from argument index to (x, y) position.
        """
        positions = {}

        # Get ALL argument indices (including orphans with no parent/children)
        args = self._rb_arguments.get(self._current_neigh_for_render, [])
        all_indices = set(range(len(args)))

        # Find root nodes (nodes with no parent in the tree)
        roots = []
        for idx in all_indices:
            # Check if this index appears as a child in the tree
            has_parent = any(idx in children for children in tree.values())
            if not has_parent:
                roots.append(idx)

        # Layout each subtree
        x_offset = 100
        for root_idx in roots:
            self._layout_subtree(root_idx, tree, positions, x_offset, 50, box_width, box_height, h_spacing, v_spacing)
            # Get rightmost x position of this subtree
            if positions:
                max_x = max(x for x, y in positions.values())
                x_offset = max_x + box_width + h_spacing * 2

        return positions

    def _layout_subtree(self, node_idx: int, tree: Dict[int, List[int]], positions: Dict[int, Tuple[int, int]],
                       x: int, y: int, box_width: int, box_height: int, h_spacing: int, v_spacing: int) -> Tuple[int, int]:
        """Recursively layout a subtree.

        Returns
        -------
        Tuple[int, int]
            The (min_x, max_x) bounds of this subtree.
        """
        children = tree.get(node_idx, [])

        if not children:
            # Leaf node
            positions[node_idx] = (x, y)
            return (x, x)

        # Layout children first
        child_y = y + box_height + v_spacing
        child_positions = []
        total_width = 0

        for i, child_idx in enumerate(children):
            child_x = x + total_width
            min_x, max_x = self._layout_subtree(child_idx, tree, positions, child_x, child_y,
                                               box_width, box_height, h_spacing, v_spacing)
            child_positions.append((min_x + max_x) // 2)  # Center of child subtree
            total_width = max_x - x + box_width + h_spacing

        # Position this node centered above its children
        if child_positions:
            node_x = (child_positions[0] + child_positions[-1]) // 2
            positions[node_idx] = (node_x, y)
            return (min(child_positions[0], node_x), max(child_positions[-1], node_x))
        else:
            positions[node_idx] = (x, y)
            return (x, x)

    def _set_status(self, neigh: str, status: str) -> None:
        if neigh in self._status_var:
            self._status_var[neigh].set(status)
        btn = self._send_btn.get(neigh)
        if btn is not None:
            # ONLY disable during "waiting" - never based on satisfaction
            btn["state"] = "disabled" if status.startswith("waiting") else "normal"

        # DEFENSIVE: Ensure outgoing box is never disabled based on satisfaction
        obox = self._outgoing_box.get(neigh)
        if obox is not None and hasattr(obox, 'cget'):
            try:
                current_state = obox.cget('state')
                if current_state == 'disabled':
                    # Log warning but don't crash
                    print(f"WARNING: Outgoing box for {neigh} was disabled! Re-enabling.")
                    obox.configure(state='normal')
            except Exception:
                pass  # Fail silently if cget/configure not available

    def _flush_incoming(self, neigh: str) -> None:
        q = self._incoming_queue.get(neigh, [])
        print(f"[UI] _flush_incoming for {neigh}: {len(q)} messages in queue")
        while q:
            msg = q.pop(0)
            print(f"[UI] Processing message: {msg[:200]}")
            clean, report = self._extract_and_apply_reports(msg)
            print(f"[UI] After extract_and_apply_reports: clean={clean[:200]}, report={report}")
            self._append_to_transcript(neigh, f"[{neigh}] {self._humanise(clean)}")
            if report:
                self._redraw_graph()
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
        # Don't immediately set placeholder - let focus handlers manage it
        # Otherwise the gray placeholder text appears even if user still has focus

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

    def _send_config(self, neigh: str) -> None:
        """Send current assignments to agent, optionally with a chat message.

        This broadcasts the human's actual current node colors. If there's a message
        typed in the text box, it sends both the config and the message together.
        This avoids confusion between hypothetical discussion and actual state.
        """
        # Get any typed message from the text box
        box = self._outgoing_box.get(neigh)
        msg = ""
        if box:
            msg = box.get("1.0", "end-1c").strip()
            if msg == "Type a message…":
                msg = ""
            box.delete("1.0", "end")

        # Show in transcript what was sent
        boundary_nodes = [n for n in self._assignments.keys() if self._owners.get(n) == "Human"]
        config_str = ", ".join([f"{n}={self._assignments[n]}" for n in sorted(boundary_nodes)])

        if msg:
            shown = f"[Config: {config_str}] {msg}"
        else:
            shown = f"[Config: {config_str}]"

        self._append_to_transcript(neigh, f"[You] {shown}")
        self._set_status(neigh, "waiting for reply…")

        def worker():
            reply = None
            try:
                if self._on_send:
                    # Send message with current assignments
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

        # RB mode: Auto-converge when all shared nodes are mutually committed
        if hasattr(self, '_rb_mode') and self._rb_mode:
            if self._check_rb_full_commitment():
                print("[RB Convergence] All shared nodes mutually committed - auto-ending")
                self.end_reason = "consensus"
                self._finish()
                return

        # LLM modes: Use satisfaction checkboxes
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

    def _check_rb_full_commitment(self) -> bool:
        """Check if human and all agents are mutually satisfied.

        Returns True if:
        - Human has ticked "satisfied" checkbox for each neighbor
        - Each agent reports satisfied == True
        """
        print(f"[RB Convergence] Checking commitment for {len(self._neighs)} neighbors")

        if not hasattr(self, '_human_sat'):
            print(f"[RB Convergence] No _human_sat attribute")
            return False

        # Check all neighbors
        for neigh in self._neighs:
            # Check human satisfaction checkbox
            try:
                human_satisfied = bool(self._human_sat[neigh].get())
                print(f"[RB Convergence] Human satisfied with {neigh}: {human_satisfied}")
            except Exception as e:
                human_satisfied = False
                print(f"[RB Convergence] Error checking human satisfaction for {neigh}: {e}")

            if not human_satisfied:
                print(f"[RB Convergence] Human not satisfied with {neigh} - not ready")
                return False

            # Check agent satisfaction
            if self._get_agent_satisfied_fn:
                try:
                    agent_satisfied = bool(self._get_agent_satisfied_fn(neigh))
                    print(f"[RB Convergence] {neigh} satisfied: {agent_satisfied}")
                except Exception as e:
                    agent_satisfied = False
                    print(f"[RB Convergence] Error checking {neigh} satisfaction: {e}")

                if not agent_satisfied:
                    print(f"[RB Convergence] {neigh} not satisfied - not ready")
                    return False

        # All parties mutually satisfied
        print("[RB Convergence] All parties satisfied - consensus reached!")
        return True

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
                self._redraw_graph()
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

        # CRITICAL: Do NOT disable chat boxes when agents mark satisfied
        # The human must be able to continue messaging even after marking satisfied
        # This is essential for:
        # 1. Changing their mind about satisfaction
        # 2. Asking questions after reaching consensus
        # 3. Negotiating further improvements
        # Only the send button should be disabled during "waiting for reply" status

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

    # -------------------- Two-Phase Workflow --------------------

    def _announce_configuration(self) -> None:
        """Announce configuration to agents (can be called multiple times to refresh)."""
        print("[UI] ===== ANNOUNCING CONFIGURATION =====")
        print(f"[UI] Human assignments: {self._assignments}")
        print(f"[UI] Current phase: {self._phase}")

        # Store initial human configuration
        self._initial_configs["Human"] = dict(self._assignments)

        # Send special message to trigger agents to announce their configurations
        for neigh in self._neighs:
            if self._on_send:
                print(f"[UI] Requesting {neigh} to announce configuration...")

                def _threaded_announce(n=neigh):
                    try:
                        print(f"[UI] _threaded_announce starting for {n}")
                        # Send special __ANNOUNCE_CONFIG__ token
                        # Check signature to handle both 2-arg and 3-arg versions
                        sig = inspect.signature(self._on_send)
                        params = sig.parameters
                        print(f"[UI] on_send signature has {len(params)} parameters")
                        if len(params) >= 3:
                            print(f"[UI] Calling on_send with 3 args")
                            reply = self._on_send(n, "__ANNOUNCE_CONFIG__", dict(self._assignments))
                        else:
                            print(f"[UI] Calling on_send with 2 args")
                            reply = self._on_send(n, "__ANNOUNCE_CONFIG__")
                        print(f"[UI] on_send returned reply: {reply[:200] if reply else 'None'}")
                        if reply and self._root:
                            print(f"[UI] Adding reply to incoming for {n}")
                            self._root.after(0, lambda: self.add_incoming(n, reply))
                        else:
                            print(f"[UI] No reply received from {n}")
                    except Exception as e:
                        print(f"[UI] Error announcing config to {n}: {e}")
                        import traceback
                        traceback.print_exc()

                import threading
                threading.Thread(target=_threaded_announce, daemon=True).start()

        # Transition to bargain phase (only on first announcement)
        if self._phase == "configure":
            self._phase = "bargain"
            if hasattr(self, '_phase_label'):
                self._phase_label.config(text="Phase: Bargain")
            if hasattr(self, '_impossible_btn'):
                self._impossible_btn.config(state="normal")
            # Keep announce button enabled for re-announcements

        # Enable conditional builders and update help text
        for neigh in self._neighs:
            if neigh in self._rb_help_labels:
                self._rb_help_labels[neigh].config(
                    text="BARGAIN PHASE: Build conditional offers: 'If they do X, I'll do Y' (both IF and THEN required)",
                    fg="#555"
                )
            if neigh in self._conditional_builder_frames:
                frame = self._conditional_builder_frames[neigh]
                # Enable all widgets in the frame
                def enable_frame(widget):
                    if hasattr(widget, 'config'):
                        try:
                            widget.config(state="normal")
                        except:
                            pass
                    for child in widget.winfo_children():
                        enable_frame(child)
                enable_frame(frame)

        print("[UI] Now in BARGAIN phase - conditional offers enabled")

    def _signal_impossible(self) -> None:
        """Signal that the current configuration is impossible to work with."""
        print("[UI] ===== IMPOSSIBLE TO CONTINUE =====")
        print("[UI] Human signaled that current configuration cannot be resolved")

        # Send special message to agents
        for neigh in self._neighs:
            if self._on_send:
                def _threaded_impossible(n=neigh):
                    try:
                        # Send special __IMPOSSIBLE__ token
                        # Check signature to handle both 2-arg and 3-arg versions
                        sig = inspect.signature(self._on_send)
                        params = sig.parameters
                        if len(params) >= 3:
                            self._on_send(n, "__IMPOSSIBLE__", dict(self._assignments))
                        else:
                            self._on_send(n, "__IMPOSSIBLE__")
                    except Exception as e:
                        print(f"[UI] Error sending impossible signal to {n}: {e}")
                        import traceback
                        traceback.print_exc()

                import threading
                threading.Thread(target=_threaded_impossible, daemon=True).start()

        # Optionally go back to configure phase or end session
        # For now, just log it
        print("[UI] Consider restarting or adjusting initial configurations")

    # -------------------- LLM_RB Live Translation --------------------

    def _schedule_llm_rb_translation(self, neigh: str) -> None:
        """Schedule debounced NL→RB translation for LLM_RB mode."""
        if self._root is None:
            return

        # Cancel existing debounce timer if any
        existing_id = self._llm_rb_debounce_ids.get(neigh)
        if existing_id:
            try:
                self._root.after_cancel(existing_id)
            except Exception:
                pass

        # Schedule new translation after 1.5 seconds of no typing
        new_id = self._root.after(1500, lambda: self._perform_llm_rb_translation(neigh))
        self._llm_rb_debounce_ids[neigh] = new_id

    def _perform_llm_rb_translation(self, neigh: str) -> None:
        """Perform NL→RB translation and update preview label."""
        if self._root is None:
            return

        self._llm_rb_debounce_ids[neigh] = None

        # Get current text from input box
        box = self._outgoing_box.get(neigh)
        if not box:
            return

        text = box.get("1.0", "end-1c").strip()
        if not text or text == "Type a message…":
            # Clear preview
            label = self._llm_rb_translation_labels.get(neigh)
            if label:
                label.configure(text="(type to see translation)", fg="gray")
            return

        # Perform translation using comm layer
        if not self._comm_layer:
            label = self._llm_rb_translation_labels.get(neigh)
            if label:
                label.configure(text="(no translation layer available)", fg="red")
            return

        # Increment sequence number for this translation request
        current_seq = self._llm_rb_translation_sequence.get(neigh, 0) + 1
        self._llm_rb_translation_sequence[neigh] = current_seq

        # Show loading indicator immediately
        label = self._llm_rb_translation_labels.get(neigh)
        if label:
            label.configure(text="Translating...", fg="blue")

        # Start loading animation
        self._start_loading_animation(neigh)

        # Run translation in background thread to avoid blocking UI
        def worker():
            try:
                # Call the translation function
                if hasattr(self._comm_layer, '_nl_to_rbmove'):
                    rb_move = self._comm_layer._nl_to_rbmove("Human", neigh, text)
                    if rb_move:
                        # Format the RBMove for display
                        move_str = self._format_rbmove_preview(rb_move)
                        if self._root:
                            self._root.after(0, lambda: self._update_translation_result(neigh, move_str, "blue", current_seq))
                    else:
                        if self._root:
                            self._root.after(0, lambda: self._update_translation_result(neigh, "(could not parse as RB move)", "orange", current_seq))
                else:
                    if self._root:
                        self._root.after(0, lambda: self._update_translation_result(neigh, "(translation not available)", "red", current_seq))
            except Exception as e:
                if self._root:
                    error_msg = f"(translation error: {str(e)[:50]})"
                    self._root.after(0, lambda: self._update_translation_result(neigh, error_msg, "red", current_seq))

        threading.Thread(target=worker, daemon=True).start()

    def _format_rbmove_preview(self, rb_move: Any) -> str:
        """Format RBMove object for preview display."""
        try:
            move_type = getattr(rb_move, 'move', '?')
            node = getattr(rb_move, 'node', '?')
            colour = getattr(rb_move, 'colour', None)

            if move_type == "PROPOSE":
                if colour:
                    return f"→ PROPOSE: {node} = {colour}"
                return f"→ PROPOSE: {node}"
            elif move_type == "ATTACK":
                return f"→ ATTACK: {node}"
            elif move_type == "CONCEDE":
                if colour:
                    return f"→ CONCEDE: {node} = {colour}"
                return f"→ CONCEDE: {node}"
            else:
                return f"→ {move_type}: {node}" + (f" = {colour}" if colour else "")
        except Exception:
            return f"→ {str(rb_move)[:50]}"

    def _start_loading_animation(self, neigh: str) -> None:
        """Start animated loading indicator for translation."""
        if self._root is None:
            return

        # Cancel any existing animation
        existing_id = self._llm_rb_animation_ids.get(neigh)
        if existing_id:
            try:
                self._root.after_cancel(existing_id)
            except Exception:
                pass

        # Start new animation
        dots_count = [0]  # Use list to allow mutation in closure

        def animate():
            if self._root is None:
                return

            label = self._llm_rb_translation_labels.get(neigh)
            if label:
                current_text = label.cget('text')
                # Only animate if still showing "Translating..."
                if current_text.startswith("Translating"):
                    dots_count[0] = (dots_count[0] % 3) + 1
                    dots = "." * dots_count[0]
                    label.configure(text=f"Translating{dots}")

                    # Schedule next frame
                    animation_id = self._root.after(400, animate)
                    self._llm_rb_animation_ids[neigh] = animation_id

        animate()

    def _update_translation_result(self, neigh: str, text: str, color: str, seq: int) -> None:
        """Update translation preview label with result and stop animation.

        Parameters
        ----------
        neigh : str
            Neighbour identifier
        text : str
            Translation result text to display
        color : str
            Text color
        seq : int
            Sequence number of this translation request. Only updates if this matches current sequence.
        """
        # Check if this is still the current translation request (not superseded by newer one)
        current_seq = self._llm_rb_translation_sequence.get(neigh, 0)
        if seq != current_seq:
            # This is a stale translation result, ignore it
            return

        # Stop animation
        existing_id = self._llm_rb_animation_ids.get(neigh)
        if existing_id:
            try:
                if self._root:
                    self._root.after_cancel(existing_id)
            except Exception:
                pass
        self._llm_rb_animation_ids[neigh] = None

        # Update label
        label = self._llm_rb_translation_labels.get(neigh)
        if label:
            label.configure(text=text, fg=color)

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
