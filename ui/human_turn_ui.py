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

import os
import glob
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

        # graph preset (set externally before setup(); used to load saved node layouts)
        self._graph_preset: str = ""

        # termination
        self.end_reason: str = ""  # set to "consensus" when all parties tick satisfied

        # Optional external callback fired on every satisfaction checkbox change.
        # Signature: cb(neighbour: str, satisfied: bool, assignments: dict) -> None
        self._submission_cb: Optional[Callable] = None

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
        self._card_widgets: Dict[str, tk.Frame] = {}  # {offer_id: card_frame} - for incremental updates

        # Feasibility queries tracking
        self._feasibility_queries: Dict[str, List[Dict[str, Any]]] = {}  # {neighbor: [query_dicts]}

        # Per-neighbor conditional builder frames (so each neighbor has independent UI)
        self._conditional_builder_frames: Dict[str, ttk.Frame] = {}
        self._condition_rows: Dict[str, List] = {}  # {neighbor: [(frame, var), ...]}
        self._assignment_rows: Dict[str, List] = {}  # {neighbor: [(frame, node_var, color_var), ...]}
        self._conditions_containers: Dict[str, ttk.Frame] = {}  # {neighbor: container frame}
        self._assignments_containers: Dict[str, ttk.Frame] = {}  # {neighbor: container frame}
        self._add_condition_funcs: Dict[str, Callable] = {}  # {neighbor: add_condition_row function}
        self._add_assignment_funcs: Dict[str, Callable] = {}  # {neighbor: add_assignment_row function}

        # Two-phase workflow: configure -> bargain
        self._phase: str = "configure"  # "configure" or "bargain"
        self._initial_configs: Dict[str, Dict[str, str]] = {}  # {agent_name: {node: color}}
        self._agent_configurations: Dict[str, Dict[str, str]] = {}  # {agent_name: {node: color}} - current announced configs
        self._phase_banner: Optional[tk.Frame] = None
        self._phase_banner_label: Optional[tk.Label] = None
        self._llm_rb_help_labels: Dict[str, tk.Label] = {}  # LLM_RB mode help labels by neighbor
        self._rb_help_labels: Dict[str, tk.Label] = {}  # RB mode help labels by neighbor

        # Auto-suggestion system
        self._auto_suggest_enabled: bool = False
        self._auto_suggest_timer_id: Optional[str] = None
        self._auto_suggest_interval_ms: int = 3000  # 3 seconds - agents wait for responses
        self._auto_suggest_slow_interval: int = 12000  # 12 seconds - slow down after agent offers
        self._last_agent_offer_time: Dict[str, float] = {}  # Track when agents sent offers
        self._pending_human_offers: Set[str] = set()  # offer_ids awaiting response
        self._last_auto_suggest_time: float = 0

        # Removed: Zoom and pan state for RB argument canvas (no longer used)

        # Zoom and pan state for graph canvas
        self._graph_canvas_scale: float = 1.0
        self._graph_canvas_offset: Tuple[int, int] = (0, 0)
        self._graph_drag_start: Optional[Tuple[int, int]] = None

        # Overlay drag guard: True while user is dragging an overlay panel.
        # Prevents _draw_constraint_overlays from destroying a widget mid-drag.
        self._overlay_drag_active: bool = False

        # Node cooldown (prevents rapid colour switching)
        self._node_cooldowns: Dict[str, float] = {}   # {node: expiry_timestamp}
        self._cooldown_seconds: int = 5
        self._cooldown_ticker_active: bool = False
        self._colour_popup: Optional[tk.Toplevel] = None

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
        self._on_constraint_update: Optional[Callable] = None  # constraint viz mode
        self._condition: str = "C1"  # constraint viz condition
        self._output_dir: Optional[str] = None
        self._get_agent_satisfied_fn: Optional[Callable[[str], bool]] = None
        self._debug_get_text_fn: Optional[Callable[[], str]] = None
        self._debug_get_visible_graph_fn: Optional[Callable[[str], str]] = None

        # Constraint viz mode flag and state
        self._constraint_viz_mode: bool = False
        self._constraint_panel_frames: Dict[str, tk.Frame] = {}
        self._constraint_status_vars: Dict[str, tk.StringVar] = {}
        self._constraint_card_areas: Dict[str, tk.Canvas] = {}
        self._constraint_card_inner: Dict[str, tk.Frame] = {}
        self._constraint_data: Dict[str, Any] = {}
        self._feasibility_status_vars: Dict[str, tk.StringVar] = {}
        self._feasibility_labels: Dict[str, tk.Label] = {}
        self._feasibility_canvas_areas: Dict[str, tuple] = {}   # agent → (scroll_canvas, inner_frame)
        self._feasibility_count_vars: Dict[str, tk.StringVar] = {}

        # Status tracking for loading indicators
        self._agent_status: Dict[str, str] = {}  # {agent_name: current_status}
        self._status_spinner_state: Dict[str, int] = {}  # {agent_name: spinner_frame}
        self._spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        # Transcript loading indicators
        self._loading_transcripts: Dict[str, bool] = {}  # {neigh: is_loading}
        self._loading_dots_frame: Dict[str, int] = {}  # {neigh: animation frame}

        # Move counter
        self._move_count: int = 0
        self._move_count_var: Optional[tk.StringVar] = None
        self._move_count_label: Optional[tk.Label] = None

        # canvas
        self._canvas: Optional[tk.Canvas] = None
        self._node_pos: Dict[str, Tuple[int, int]] = {}
        self._node_items: Dict[str, int] = {}
        self._edge_items: List[Tuple[str, str, int]] = []
        self._label_text_items: Dict[str, int] = {}   # canvas item IDs for node labels
        self._timer_text_items: Dict[str, int] = {}   # canvas item IDs for cooldown timers
        self._hud_var: Optional[tk.StringVar] = None

        # debug window
        self._debug_win: Optional[tk.Toplevel] = None

        # resize debounce
        self._resize_after_id: Optional[str] = None

        # points (default)
        self._points = {"blue": 1, "green": 2, "red": 3}

        # done flag for async session
        self._done = threading.Event()

        # Synchronous submission history (constraint viz mode)
        self._submission_history: List[Dict] = []        # [{num, timestamp, assignments, responses}]
        self._submit_btn: Optional[ttk.Button] = None
        self._history_bar: Optional[tk.Frame] = None
        self._has_pending_changes: bool = False
        self._last_submitted_assignments: Optional[Dict] = None
        self._submission_computing: bool = False          # True while bg threads are running

    def _ensure_root(self) -> tk.Tk:
        """Ensure a Tk root exists before creating any tk.Variable."""
        if self._root is None:
            self._root = tk.Tk()
        return self._root

    def _write_ui_debug(self, message: str) -> None:
        """Write debug message to ui_debug.log file."""
        try:
            with open("E:\\Files\\PhD-Main\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                f.write(f"{message}\n")
        except Exception as e:
            # Silently fail if we can't write to the log
            pass

    def update_agent_status(self, agent_name: str, status: str) -> None:
        """Update the status display for an agent (thread-safe)."""
        if self._root is not None:
            def _update():
                self._agent_status[agent_name] = status
                if agent_name in self._status_var:
                    # Add spinner if status is not empty
                    if status:
                        spinner_frame = self._status_spinner_state.get(agent_name, 0)
                        spinner_char = self._spinner_chars[spinner_frame % len(self._spinner_chars)]
                        self._status_var[agent_name].set(f"{spinner_char} {status}")
                        # Advance spinner for next update
                        self._status_spinner_state[agent_name] = spinner_frame + 1
                    else:
                        self._status_var[agent_name].set("")
                        self._status_spinner_state[agent_name] = 0
            self._root.after(0, _update)

    def clear_agent_status(self, agent_name: str) -> None:
        """Clear the status display for an agent (thread-safe)."""
        self.update_agent_status(agent_name, "")

    # -------------------- Public API expected by simulation --------------------

    def add_incoming(self, neigh: str, text: str) -> None:
        """Thread-safe: queue an incoming message to show in UI."""
        print(f"[UI] add_incoming called for {neigh}: {text[:200]}")
        self._write_ui_debug(f"[UI add_incoming] Called for {neigh}")
        self._write_ui_debug(f"[UI add_incoming] Text: {text[:200]}")
        self._incoming_queue.setdefault(neigh, []).append(text)
        self._write_ui_debug(f"[UI add_incoming] Added to queue, total messages for {neigh}: {len(self._incoming_queue[neigh])}")
        if self._root is not None:
            self._write_ui_debug(f"[UI add_incoming] Scheduling _flush_incoming for {neigh}")
            self._root.after(0, lambda n=neigh: self._flush_incoming(n))
        else:
            print(f"[UI] WARNING: _root is None, cannot flush incoming messages")
            self._write_ui_debug(f"[UI add_incoming] ERROR: _root is None!")

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
        on_constraint_update: Optional[Callable] = None,
        on_human_domain_update: Optional[Callable] = None,
        condition: str = "C1",
        get_agent_satisfied_fn: Optional[Callable[[str], bool]] = None,
        debug_get_text_fn: Optional[Callable[[], str]] = None,
        debug_get_visible_graph_fn: Optional[Callable[[str], str]] = None,
        points: Optional[Dict[str, int]] = None,
        fixed_nodes: Optional[Dict[str, Any]] = None,
        problem: Optional[Any] = None,
        structured_rb_mode: bool = False,
        comm_layer: Optional[Any] = None,
        output_dir: Optional[str] = None,
        node_domains: Optional[Dict[str, List[Any]]] = None,
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
        self._on_constraint_update = on_constraint_update
        self._on_human_domain_update = on_human_domain_update
        self._human_domain_data: Dict[str, Any] = {}
        self._condition = condition
        self._get_agent_satisfied_fn = get_agent_satisfied_fn
        self._debug_get_text_fn = debug_get_text_fn
        self._debug_get_visible_graph_fn = debug_get_visible_graph_fn
        self._fixed_nodes = dict(fixed_nodes) if fixed_nodes else {}
        # Per-node colour domain restrictions (complex constraints).
        # Maps node → list of allowed colours.  Empty = unconstrained.
        self._node_domains: Dict[str, List[Any]] = dict(node_domains) if node_domains else {}
        # True only for complex constraint modes (cx_easy / cx_medium / cx_hard).
        # Controls whether arc rings are drawn on human-owned nodes.
        self._complex_constraints: bool = bool(self._node_domains)
        # Also treat 1-colour domain nodes as fixed (they cannot be changed)
        for _n, _dom in self._node_domains.items():
            if len(_dom) == 1 and _n not in self._fixed_nodes:
                self._fixed_nodes[_n] = _dom[0]
        self._output_dir = output_dir

        # Track per-agent feasibility for Finish button gating.
        # Starts False; updated each time update_constraint_display is called.
        self._agent_feasibility: Dict[str, bool] = {}

        if points:
            self._points = dict(points)

        if visible_graph is None:
            self._edges = []
        else:
            _, edges = visible_graph
            self._edges = list(edges)

        # Build adjacency dictionary for determining affected neighbors
        self._adjacency = {}
        for u, v in self._edges:
            self._adjacency.setdefault(u, set()).add(v)
            self._adjacency.setdefault(v, set()).add(u)

        root = self._ensure_root()

        # init transcripts and tk vars
        for n in self._neighs:
            self._transcripts.setdefault(n, [])
            self._incoming_queue.setdefault(n, [])
            self._human_sat.setdefault(n, tk.BooleanVar(master=root, value=False))
            self._agent_sat.setdefault(n, tk.StringVar(master=root, value=""))

        self._build_ui(debug_agents=debug_agents, get_visible_graph_fn=get_visible_graph_fn)

        if getattr(self, '_constraint_viz_mode', False):
            # Constraint viz mode: populate constraint panels after 200ms
            self._root.after(200, self._initial_populate)
        else:
            # Legacy negotiation mode: coin flip starters
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
        if getattr(self, '_constraint_viz_mode', False):
            # Start maximised so the sash percentage fires on the full-size window
            root.state('zoomed')
        else:
            root.geometry("1320x820")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=8, pady=6)

        self._hud_var = tk.StringVar(master=root, value=self._hud_text())
        ttk.Label(top, textvariable=self._hud_var).pack(side="left")

        # Move counter (top-right corner)
        self._move_count_var = tk.StringVar(master=root, value="Moves: 0")
        self._move_count_label = tk.Label(
            top,
            textvariable=self._move_count_var,
            font=("TkDefaultFont", 20, "bold"),
            bg="#22bb44",
            fg="white",
            relief="raised",
            padx=14,
            pady=4,
        )
        self._move_count_label.pack(side="right", padx=(8, 0))

        # Checkpoint button bar
        checkpoint_frame = ttk.Frame(top)
        checkpoint_frame.pack(side="left", padx=20)
        ttk.Label(checkpoint_frame, text="Checkpoints:").pack(side="left")
        self._checkpoint_frame = checkpoint_frame
        self._checkpoint_buttons: List[ttk.Button] = []
        self._checkpoints: List[Dict] = []

        btns = ttk.Frame(top)
        btns.pack(side="right")

        # Phase status (for RB structured mode, LLM_RB mode, and all other modes with announcement phase)
        has_announcement = getattr(self, '_has_announcement_phase', False) or getattr(self, '_rb_structured_mode', False) or getattr(self, '_llm_rb_mode', False)
        if has_announcement:
            self._announce_config_btn = ttk.Button(btns, text="(Re-)Announce Configuration",
                                                   command=self._announce_configuration)
            self._announce_config_btn.pack(side="left", padx=(0, 6))

        # Impossible button only for structured RB mode
        if getattr(self, '_rb_structured_mode', False):
            self._impossible_btn = ttk.Button(btns, text="Impossible to Continue",
                                              command=self._signal_impossible, state="disabled")
            self._impossible_btn.pack(side="left", padx=(0, 6))

        ttk.Button(btns, text="Debug", command=lambda: self._open_debug(debug_agents, get_visible_graph_fn)).pack(side="right", padx=(6, 0))
        self._finish_btn = ttk.Button(btns, text="Finish", command=self._finish, state="disabled")
        self._finish_btn.pack(side="right")

        # Constraint viz mode: Submit button (synchronous step trigger)
        if getattr(self, '_constraint_viz_mode', False):
            self._submit_btn = ttk.Button(
                btns, text="Submit Configuration",
                command=self._submit_configuration,
                style="Submit.TButton",
            )
            self._submit_btn.pack(side="left", padx=(0, 10))
            # Style: green when pending changes, grey when up-to-date
            style = ttk.Style()
            style.configure("Submit.TButton", font=("TkDefaultFont", 10, "bold"))
            style.configure("SubmitPending.TButton", font=("TkDefaultFont", 10, "bold"),
                            foreground="white", background="#2a9d2a")

        # Create phase banner frame (for all modes with announcement phase)
        if has_announcement:
            phase_banner = tk.Frame(root, height=50, relief=tk.RAISED, borderwidth=2)
            phase_banner.pack(fill="x", padx=0, pady=(0, 5))

            self._phase_banner_label = tk.Label(
                phase_banner,
                text="⚙️ STEP 1: INTENTION SETTING - Configure your graph",
                font=("Arial", 14, "bold"),
                fg="white",
                bg="#d9534f",  # Red for configure phase
                pady=12
            )
            self._phase_banner_label.pack(fill="both", expand=True)
            self._phase_banner = phase_banner

        # Constraint viz mode: history bar (shown below top bar)
        if getattr(self, '_constraint_viz_mode', False):
            history_outer = tk.Frame(root, bg="#1e1e2e", pady=4)
            history_outer.pack(fill="x", padx=0)
            tk.Label(
                history_outer, text="  Attempts:", font=("TkDefaultFont", 9, "bold"),
                bg="#1e1e2e", fg="#aaaacc",
            ).pack(side="left", padx=(6, 4))
            # Scrollable inner frame
            hist_canvas = tk.Canvas(history_outer, height=180, bg="#1e1e2e",
                                    highlightthickness=0)
            hist_canvas.pack(side="left", fill="x", expand=True)
            hist_inner = tk.Frame(hist_canvas, bg="#1e1e2e")
            hist_win = hist_canvas.create_window((0, 0), window=hist_inner, anchor="nw")
            def _hist_inner_cfg(ev, c=hist_canvas, w=hist_win):
                c.configure(scrollregion=c.bbox("all"))
                c.itemconfig(w, height=ev.height)
            hist_inner.bind("<Configure>", _hist_inner_cfg)
            # horizontal scrollbar (hidden by default — only appears if many attempts)
            hist_scroll = ttk.Scrollbar(history_outer, orient="horizontal",
                                        command=hist_canvas.xview)
            hist_canvas.configure(xscrollcommand=hist_scroll.set)
            # Only show scrollbar when content overflows
            def _maybe_show_scroll(ev, c=hist_canvas, s=hist_scroll):
                bbox = c.bbox("all")
                if bbox and bbox[2] > c.winfo_width():
                    s.pack(side="bottom", fill="x")
                else:
                    try:
                        s.pack_forget()
                    except Exception:
                        pass
            hist_inner.bind("<Configure>", lambda ev: _maybe_show_scroll(ev))
            self._history_bar = hist_inner
            tk.Label(history_outer, text="(no attempts yet)",
                     bg="#1e1e2e", fg="#555577",
                     font=("TkDefaultFont", 9, "italic")).pack(side="left", padx=4)
            self._history_placeholder = history_outer.winfo_children()[-1]

        main = ttk.Frame(root)
        main.pack(fill="both", expand=True)

        # Store main frame and create paned window
        self._main_frame = main

        # Use PanedWindow for adjustable split between graph, arguments, and conditionals
        paned = tk.PanedWindow(main, orient=tk.HORIZONTAL, sashrelief=tk.RAISED,
                               sashwidth=5, bg="#ddd")
        self._paned_window = paned

        # Always pack the paned window
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # In configure phase (all modes with announcement), don't add middle panel yet
        rb_mode = getattr(self, '_rb_structured_mode', False)
        llm_rb_mode = getattr(self, '_llm_rb_mode', False)
        has_announcement_phase = getattr(self, '_has_announcement_phase', False) or rb_mode or llm_rb_mode
        _cviz = getattr(self, '_constraint_viz_mode', False)

        # Create left panel for graph (always present)
        # Constraint-viz mode uses an 80/20 split, so give the graph panel a larger initial hint
        left = ttk.Frame(paned)
        paned.add(left, width=900 if _cviz else 400, minsize=250)

        # Middle panel with scrollbar for chat panes
        middle_container = ttk.Frame(paned)

        if not (has_announcement_phase and self._phase == "configure") and not _cviz:
            paned.add(middle_container, width=400, minsize=300)

        # Store for later
        self._middle_container = middle_container

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

        # Bind mousewheel to scrolling only when mouse is over the canvas
        def on_mousewheel(event):
            middle_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        def on_enter(event):
            middle_canvas.bind("<MouseWheel>", on_mousewheel)

        def on_leave(event):
            middle_canvas.unbind("<MouseWheel>")

        middle_canvas.bind("<Enter>", on_enter)
        middle_canvas.bind("<Leave>", on_leave)

        # Add right panel: constraint panels (constraint viz mode) or conditionals sidebar (legacy)
        right_panel_frame = ttk.Frame(paned)

        if getattr(self, '_constraint_viz_mode', False):
            # Constraint viz: always show constraint panels (20% of window)
            paned.add(right_panel_frame, width=200, minsize=180)
            self._conditionals_frame = right_panel_frame
            self._conditionals_cards_inner = None
            self._build_feasibility_sidebar(right_panel_frame)
        else:
            # Legacy mode: conditionals sidebar
            conditionals_frame = right_panel_frame
            # In configure phase (all modes with announcement), don't add conditionals panel yet
            if not (has_announcement_phase and self._phase == "configure"):
                paned.add(conditionals_frame, width=400, minsize=250)
            # Store reference for later use
            self._conditionals_frame = conditionals_frame
            self._conditionals_cards_inner = None
            # Build conditionals sidebar UI
            self._build_conditionals_sidebar(conditionals_frame)

        # Schedule sash positioning — retry until the window is actually mapped
        # (winfo_width can return 1 or 0 if called before the WM maps the window)
        _sash_retries = [0]

        def _set_sash_positions():
            try:
                paned.update_idletasks()
                total_width = paned.winfo_width()
                if total_width <= 100:
                    # Window not mapped yet — retry up to ~3 seconds
                    _sash_retries[0] += 1
                    if _sash_retries[0] < 15:
                        root.after(200, _set_sash_positions)
                    return
                if getattr(self, '_constraint_viz_mode', False):
                    # 2 panels: graph 80%, info panel 20%
                    paned.sash_place(0, int(total_width * 0.80), 0)
                else:
                    # 3 panels: equal 1/3 each
                    paned.sash_place(0, int(total_width // 3), 0)
                    if len(paned.panes()) > 2:
                        paned.sash_place(1, int(2 * total_width // 3), 0)
            except Exception:
                pass

        root.after(100, _set_sash_positions)

        # Re-apply the sash ratio whenever the window is resized (e.g. maximise/restore).
        # Debounced 300ms so it doesn't fight the user while they drag the window border.
        # Sash drags do NOT trigger root <Configure>, so manual panel resizing still works.
        if getattr(self, '_constraint_viz_mode', False):
            _resize_pending = [None]

            def _on_root_resize(event):
                if event.widget is not root:
                    return
                if _resize_pending[0] is not None:
                    root.after_cancel(_resize_pending[0])
                _resize_pending[0] = root.after(300, _set_sash_positions)

            root.bind('<Configure>', _on_root_resize)

        # Create canvas in left panel (always)
        canvas = tk.Canvas(left, bg="white", highlightthickness=1, highlightbackground="#ccc")
        canvas.pack(fill="both", expand=True)
        self._canvas = canvas

        # In configure phase (all modes with announcement), add big button below graph
        if has_announcement_phase and self._phase == "configure":
            button_container = ttk.Frame(left)
            button_container.pack(fill="x", side="bottom", pady=(10, 10))

            instruction = tk.Label(
                button_container,
                text="Configure your graph by clicking on nodes, then announce to begin negotiation",
                font=("Arial", 11),
                fg="#555"
            )
            instruction.pack(pady=(0, 10))

            big_announce_btn = ttk.Button(
                button_container,
                text="🚀 Announce Configuration & Begin Negotiation",
                command=self._announce_configuration,
            )
            big_announce_btn.pack(pady=10, ipadx=40, ipady=20)

            # Store for later removal
            self._step1_button_container = button_container
        canvas.bind("<Button-1>", self._on_canvas_click)
        canvas.bind("<Button-3>", self._on_canvas_right_click)
        canvas.bind("<Configure>", self._on_canvas_resize)

        # Add zoom with Ctrl + mouse wheel
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

        # Bind Ctrl+MouseWheel for zoom (not plain mousewheel)
        canvas.bind("<Control-MouseWheel>", _on_graph_zoom)

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

        # In configure phase (all modes with announcement), show big announce button instead of chat panes
        rb_mode = getattr(self, '_rb_structured_mode', False)
        if has_announcement_phase and self._phase == "configure":
            # Create a prominent announce configuration UI
            configure_container = ttk.Frame(right)
            configure_container.pack(fill="both", expand=True, padx=20, pady=20)

            # Large instruction label
            instruction = tk.Label(
                configure_container,
                text="STEP 1: INTENTION SETTING\n\nConfigure your graph coloring by clicking on nodes.\nWhen ready, announce your configuration to begin negotiation.",
                font=("Arial", 12),
                fg="#333",
                justify="center",
                wraplength=400
            )
            instruction.pack(pady=(40, 20))

            # Large announce button
            big_announce_btn = ttk.Button(
                configure_container,
                text="Announce Configuration",
                command=self._announce_configuration,
            )
            big_announce_btn.pack(pady=20, ipadx=30, ipady=15)

            # Store reference for later phase transitions
            self._configure_container = configure_container

        # Constraint viz mode: skip chat panes (constraints shown as graph overlays)
        if getattr(self, '_constraint_viz_mode', False):
            return

        # Build chat panes for each neighbor (hidden during configure phase in RB/LLM_RB modes)
        for neigh in self._neighs:
            pane = ttk.LabelFrame(right, text=f"{neigh}")

            # Hide panes during configure phase (all modes with announcement)
            if has_announcement_phase and self._phase == "configure":
                # Don't pack yet - will be shown after phase transition
                pass
            else:
                pane.pack(fill="both", expand=False, pady=6)

            # Store pane reference for later
            if not hasattr(self, '_neighbor_panes'):
                self._neighbor_panes = {}
            self._neighbor_panes[neigh] = pane

            # Skip transcript box in RB mode (not needed - use conditionals sidebar instead)
            if not rb_mode:
                tbox = tk.Text(pane, height=10, wrap="word", state="disabled")
                tbox.pack(fill="x", padx=6, pady=(6, 4))
                self._transcript_box[neigh] = tbox

            row = ttk.Frame(pane)
            row.pack(fill="x", padx=6)

            self._status_var[neigh] = tk.StringVar(master=root, value="")
            status_label = tk.Label(
                row,
                textvariable=self._status_var[neigh],
                font=("Arial", 9, "italic"),
                fg="#666",
                anchor="w"
            )
            status_label.pack(side="left", fill="x", expand=True, padx=(4, 0))

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
                # Phase-aware help text for LLM_RB mode
                if self._phase == "configure":
                    help_text = "CONFIGURE PHASE: Set up your graph, then click 'Announce Configuration' to begin bargaining"
                    help_fg = "#d9534f"  # Red
                else:
                    help_text = "BARGAIN PHASE: Type natural language messages (e.g., 'I think h1 should be red')"
                    help_fg = "#555"

                help_label = tk.Label(pane, text=help_text,
                                     fg=help_fg, font=("Arial", 8, "italic"),
                                     wraplength=400, justify="left", anchor="w")
                help_label.pack(fill="x", padx=6, pady=(4, 4))
                self._llm_rb_help_labels[neigh] = help_label
                print(f"[UI] Created LLM_RB help label for {neigh}, phase={self._phase}")

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
                ttk.Label(conditional_builder_frame, text="Select from agent's offers OR check 'Custom' to propose your own conditions on agent's boundary nodes",
                         font=("Arial", 7, "italic"), foreground="#666").pack(anchor="w", padx=4)

                conditions_container = ttk.Frame(conditional_builder_frame)
                conditions_container.pack(fill="x", padx=4, pady=2)
                self._conditions_containers[neigh] = conditions_container

                def add_condition_row(n=neigh, container=conditions_container):
                    """Add a new condition row for selecting previous statements or entering custom conditions."""
                    print(f"[UI] Adding condition row for neighbor '{n}' (type={type(n)})")
                    print(f"[UI] Current _rb_arguments keys: {list(self._rb_arguments.keys())}")
                    row_frame = ttk.Frame(container)
                    row_frame.pack(fill="x", pady=2)

                    # Create a frame to hold both modes
                    mode_frame = ttk.Frame(row_frame)
                    mode_frame.pack(side="left", fill="x", expand=True)

                    # Mode 1: Dropdown (default)
                    dropdown_frame = ttk.Frame(mode_frame)
                    statement_var = tk.StringVar(value="(select statement)")
                    statement_combo = ttk.Combobox(dropdown_frame, textvariable=statement_var,
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

                    # Mode 2: Custom entry
                    custom_frame = ttk.Frame(mode_frame)
                    node_var_custom = tk.StringVar()

                    # Get human's boundary nodes (my nodes adjacent to this agent's cluster)
                    human_boundary_nodes = []
                    for node in self._nodes:
                        if self._owners.get(node) == "Human":
                            # Check if this human node has a neighbor owned by this agent
                            for nbr in self.problem.get_neighbors(node):
                                if self._owners.get(nbr) == n:
                                    if node not in human_boundary_nodes:
                                        human_boundary_nodes.append(node)
                                    break

                    ttk.Label(custom_frame, text="Node:").pack(side="left", padx=2)
                    node_combo_custom = ttk.Combobox(custom_frame, textvariable=node_var_custom,
                                                    values=human_boundary_nodes, state="readonly", width=10)
                    node_combo_custom.pack(side="left", padx=2)

                    ttk.Label(custom_frame, text="=").pack(side="left", padx=2)
                    color_var_custom = tk.StringVar()
                    color_combo_custom = ttk.Combobox(custom_frame, textvariable=color_var_custom,
                                                      values=self._domain, state="readonly", width=10)
                    color_combo_custom.pack(side="left", padx=2)

                    # Toggle button
                    use_custom_var = tk.BooleanVar(value=False)
                    def toggle_mode():
                        if use_custom_var.get():
                            dropdown_frame.pack_forget()
                            custom_frame.pack(side="left", fill="x")
                        else:
                            custom_frame.pack_forget()
                            dropdown_frame.pack(side="left", fill="x")

                    toggle_btn = ttk.Checkbutton(row_frame, text="Custom",
                                                 variable=use_custom_var,
                                                 command=toggle_mode)
                    toggle_btn.pack(side="left", padx=4)

                    # Show dropdown by default
                    dropdown_frame.pack(side="left", fill="x")

                    # Remove button
                    def remove_row():
                        print(f"[UI] Removing condition row for {n}")
                        row_frame.destroy()
                        # Check both old and new formats
                        for item in list(self._condition_rows[n]):
                            if len(item) >= 2 and item[0] == row_frame:
                                self._condition_rows[n].remove(item)
                                break
                        print(f"[UI] {n} now has {len(self._condition_rows[n])} condition rows")

                    remove_btn = ttk.Button(row_frame, text="✗", width=3, command=remove_row)
                    remove_btn.pack(side="left", padx=2)

                    # Store all vars in condition rows for later parsing (new format with 5 elements)
                    self._condition_rows[n].append((row_frame, statement_var, node_var_custom, color_var_custom, use_custom_var))
                    return row_frame

                self._add_condition_funcs[neigh] = add_condition_row

                add_condition_btn = ttk.Button(conditional_builder_frame, text="+ Add Condition",
                                              command=add_condition_row)
                add_condition_btn.pack(anchor="w", padx=4, pady=2)

                # Assignments section (THEN part)
                assignments_label = ttk.Label(conditional_builder_frame, text="THEN (my commitments):", font=("Arial", 9, "bold"))
                assignments_label.pack(anchor="w", padx=4, pady=(8, 2))

                # Instruction label
                ttk.Label(conditional_builder_frame, text="Specify what you'll commit to if conditions are met",
                         font=("Arial", 7, "italic"), foreground="#666").pack(anchor="w", padx=4)

                assignments_container = ttk.Frame(conditional_builder_frame)
                assignments_container.pack(fill="x", padx=4, pady=2)
                self._assignments_containers[neigh] = assignments_container

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

                self._add_assignment_funcs[neigh] = add_assignment_row

                add_assignment_btn = ttk.Button(conditional_builder_frame, text="+ Add Assignment",
                                               command=add_assignment_row)
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
                    for row_data in cond_rows:
                        if len(row_data) == 2:
                            # Old format: (row_frame, statement_var)
                            row_frame, stmt_var = row_data
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
                        elif len(row_data) == 5:
                            # New format: (row_frame, statement_var, node_var_custom, color_var_custom, use_custom_var)
                            row_frame, stmt_var, node_custom, color_custom, use_custom = row_data
                            if use_custom.get():
                                # Parse custom entry
                                node_name = node_custom.get()
                                color_name = color_custom.get()
                                if node_name and color_name:
                                    owner = self._owners.get(node_name, "Unknown")
                                    conditions.append({
                                        "node": node_name,
                                        "colour": color_name,
                                        "owner": owner
                                    })
                            else:
                                # Parse dropdown selection
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

                    # Warn if no conditions (becomes unconditional announcement)
                    if not conditions:
                        print(f"[RB UI] Warning: No conditions specified - sending as unconditional announcement")
                        print(f"[RB UI] Agent will treat this as a bare proposal, not a conditional offer")
                        # Continue anyway - don't return

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
                    self._pending_human_offers.add(offer_id)
                    print(f"[Offer Tracking] Sent offer {offer_id} to {n} - marked as pending")

                    # Update sidebar to show it
                    if self._root:
                        self._root.after(0, self._render_conditional_cards)

                    # Append to transcript for display
                    try:
                        if conditions:
                            cond_str = " AND ".join([f"{c['node']}={c['colour']}" for c in conditions])
                            assign_str = " AND ".join([f"{a['node']}={a['colour']}" for a in assignments])
                            display_msg = f"[You -> {n}] IF {cond_str} THEN {assign_str}"
                        else:
                            assign_str = " AND ".join([f"{a['node']}={a['colour']}" for a in assignments])
                            display_msg = f"[You -> {n}] Offer: {assign_str}"
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

                # Check Feasibility function
                def check_feasibility(n=neigh):
                    """Send feasibility query to agent."""
                    self._write_ui_debug(f"[UI check_feasibility] Button clicked for {n}")
                    # Get conditions from conditional builder
                    cond_rows = self._condition_rows.get(n, [])
                    self._write_ui_debug(f"[UI check_feasibility] Found {len(cond_rows)} condition rows")
                    conditions = []

                    # Extract conditions (same logic as send_rb_message)
                    for row_data in cond_rows:
                        if len(row_data) == 5:  # New format
                            row_frame, stmt_var, node_custom, color_custom, use_custom = row_data
                            if use_custom.get():
                                node_name = node_custom.get()
                                color_name = color_custom.get()
                                if node_name and color_name:
                                    owner = self._owners.get(node_name, "Unknown")
                                    conditions.append({"node": node_name, "colour": color_name, "owner": owner})
                            else:
                                stmt = stmt_var.get()
                                if stmt and stmt != "(select statement)":
                                    match = re.match(r'#(\d+): (\w+)=(\w+)', stmt)
                                    if match:
                                        idx, node_name, color_name = match.groups()
                                        owner = self._owners.get(node_name, "Unknown")
                                        conditions.append({"node": node_name, "colour": color_name, "owner": owner})
                        elif len(row_data) == 2:  # Old format
                            row_frame, stmt_var = row_data
                            stmt = stmt_var.get()
                            if stmt and stmt != "(select statement)":
                                match = re.match(r'#(\d+): (\w+)=(\w+)', stmt)
                                if match:
                                    idx, node_name, color_name = match.groups()
                                    owner = self._owners.get(node_name, "Unknown")
                                    conditions.append({"node": node_name, "colour": color_name, "owner": owner})

                    if not conditions:
                        # Show warning dialog
                        self._write_ui_debug(f"[UI check_feasibility] No conditions extracted - showing warning")
                        import tkinter.messagebox as messagebox
                        messagebox.showwarning("No Conditions", "Please add at least one condition to check feasibility")
                        return

                    # Build query message
                    self._write_ui_debug(f"[UI check_feasibility] Extracted {len(conditions)} conditions: {conditions}")
                    import time
                    query_id = f"query_{int(time.time() * 1000)}_Human_{n}"
                    rb_payload = {
                        "move": "FeasibilityQuery",
                        "query_id": query_id,
                        "conditions": conditions,
                        "reasons": ["feasibility_check"]
                    }
                    rb_msg = f'[rb:{json.dumps(rb_payload)}]'
                    self._write_ui_debug(f"[UI check_feasibility] Built query with ID: {query_id}")
                    self._write_ui_debug(f"[UI check_feasibility] Message: {rb_msg}")

                    # Display in transcript
                    cond_str = " AND ".join([f"{c['node']}={c['colour']}" for c in conditions])
                    display_msg = f"Query: IF {cond_str} THEN feasible?"
                    self._append_to_transcript(n, f"[You -> {n}] {display_msg}")

                    # Store query for tracking
                    query_dict = {
                        "query_id": query_id,
                        "conditions": conditions,
                        "is_feasible": None,  # Will be updated when response arrives
                        "feasibility_penalty": None,
                        "feasibility_details": None
                    }

                    if n not in self._feasibility_queries:
                        self._feasibility_queries[n] = []
                    self._feasibility_queries[n].append(query_dict)
                    self._write_ui_debug(f"[UI check_feasibility] Stored query {query_id} in _feasibility_queries[{n}]")
                    self._write_ui_debug(f"[UI check_feasibility] Total queries for {n}: {len(self._feasibility_queries[n])}")
                    self._write_ui_debug(f"[UI check_feasibility] Calling _render_conditional_cards()")
                    self._render_conditional_cards()

                    # Send query via threading (same pattern as send_rb_message)
                    if self._on_send:
                        self._write_ui_debug(f"[UI check_feasibility] Sending query to {n} via _on_send")
                        self._status_var[n].set("checking feasibility...")

                        def _threaded_query():
                            reply = None
                            try:
                                sig = inspect.signature(self._on_send)
                                params = sig.parameters
                                if len(params) >= 3:
                                    reply = self._on_send(n, rb_msg, dict(self._assignments))
                                else:
                                    reply = self._on_send(n, rb_msg)
                                self._write_ui_debug(f"[UI check_feasibility] Got reply from {n}: {reply[:200] if reply else 'None'}")
                            except Exception as e:
                                print(f"[RB UI] Query error: {e}")
                                self._write_ui_debug(f"[UI check_feasibility] ERROR: {e}")
                            finally:
                                if self._root:
                                    if reply:
                                        self._write_ui_debug(f"[UI check_feasibility] Adding reply to incoming queue for {n}")
                                        self._root.after(0, lambda: self.add_incoming(n, reply))
                                    else:
                                        self._write_ui_debug(f"[UI check_feasibility] No reply received, setting status to idle")
                                        self._root.after(0, lambda: self._status_var[n].set("idle"))

                        threading.Thread(target=_threaded_query, daemon=True).start()
                    else:
                        self._write_ui_debug(f"[UI check_feasibility] ERROR: No _on_send callback!")

                btn_frame = ttk.Frame(rb_frame)
                btn_frame.pack(fill="x", padx=6, pady=(8, 6))

                # Configure grid for equal-width columns
                btn_frame.columnconfigure(0, weight=1)
                btn_frame.columnconfigure(1, weight=1)

                # Check Feasibility button (left column)
                feasibility_btn = ttk.Button(
                    btn_frame,
                    text="🔍 Check Feasibility",
                    command=lambda fn=check_feasibility: fn()
                )
                feasibility_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

                # Send Offer button (right column)
                send_offer_btn = ttk.Button(
                    btn_frame,
                    text="📤 Suggest Conditional Offer",
                    command=lambda fn=send_rb_message: fn()
                )
                send_offer_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

                # Store references
                self._send_btn[neigh] = send_offer_btn
                if not hasattr(self, '_feasibility_btn'):
                    self._feasibility_btn = {}
                self._feasibility_btn[neigh] = feasibility_btn
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

        # Add mousewheel scrolling to conditionals sidebar
        def on_conditionals_scroll(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        def on_cond_enter(event):
            canvas.bind("<MouseWheel>", on_conditionals_scroll)

        def on_cond_leave(event):
            canvas.unbind("<MouseWheel>")

        canvas.bind("<Enter>", on_cond_enter)
        canvas.bind("<Leave>", on_cond_leave)

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

    def _compute_offers_signature(self, offers: List[Dict[str, Any]], queries: Dict[str, List[Dict]] = None) -> str:
        """Compute a signature (hash) of the offers list to detect changes.

        This allows us to avoid re-rendering cards when nothing has changed,
        reducing UI flicker.

        Parameters
        ----------
        offers : List[Dict[str, Any]]
            List of conditional offers
        queries : Dict[str, List[Dict]], optional
            Feasibility queries dict (neighbor -> list of queries)
        """
        import hashlib

        # Build a stable representation of the offers
        signature_parts = []
        for offer in offers:
            # Include key fields that would affect rendering
            parts = [
                str(offer.get("offer_id", "")),
                str(offer.get("direction", "")),
                str(offer.get("status", "")),
                str(offer.get("sender", "")),
                str(offer.get("recipient", "")),
                str(sorted([(c.get("node", ""), c.get("colour", ""))
                           for c in offer.get("conditions", [])])),
                str(sorted([(a.get("node", ""), a.get("colour", ""))
                           for a in offer.get("assignments", [])])),
                str(sorted(offer.get("reasons", []))),
            ]
            signature_parts.append("|".join(parts))

        # Include feasibility queries in signature
        if queries:
            for neigh, query_list in sorted(queries.items()):
                for query in query_list:
                    query_parts = [
                        str(query.get("query_id", "")),
                        str(sorted([(c.get("node", ""), c.get("colour", ""))
                                   for c in query.get("conditions", [])])),
                        str(query.get("is_feasible", "")),
                        str(query.get("feasibility_penalty", "")),
                        str(query.get("feasibility_details", "")),
                    ]
                    signature_parts.append("QUERY|" + "|".join(query_parts))

        # Hash the combined representation
        combined = "::".join(signature_parts)
        return hashlib.md5(combined.encode()).hexdigest()

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
        print(f"[UI _render_conditional_cards] ENTRY - active_conditionals: {len(self._active_conditionals)}")

        if self._conditionals_cards_inner is None:
            print(f"[UI _render_conditional_cards] No cards container - returning")
            return

        # Safety check: Don't render if UI is closing
        if self._root is None or not self._root.winfo_exists():
            print(f"[UI _render_conditional_cards] UI closing - returning")
            return

        # Combine both incoming and outgoing offers (build the expected state)
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
            reasons = offer.get("reasons", [])
            offer_id = offer.get("offer_id", "")

            # Write to log
            try:
                with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                    f.write(f"[UI Cards] Processing offer {offer_id} from {sender}: {len(conditions)} conds\n")
            except:
                pass

            # EXCEPTION: Always show boundary_update offers even if unconditional
            # These represent important state changes the human needs to see
            is_boundary_update = any("boundary_update" in str(r) for r in reasons)

            # Skip unconditional offers UNLESS they're boundary updates
            if (not conditions or len(conditions) == 0) and not is_boundary_update:
                print(f"[UI Cards] Skipping agent unconditional offer from {sender}: {offer.get('offer_id')}")
                try:
                    with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                        f.write(f"[UI Cards] FILTERED (unconditional): {offer_id}\n")
                except:
                    pass
                continue

            # Check if this offer matches a configuration announcement
            # If sender has a config and all offer assignments match the config, skip it
            # BUT: Only skip if it's also UNCONDITIONAL (no conditions)
            # Conditional offers should always be shown, even if assignments match config
            if sender in self._agent_configurations and (not conditions or len(conditions) == 0):
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
                    try:
                        with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                            f.write(f"[UI Cards] FILTERED (config match): {offer_id}\n")
                    except:
                        pass
                    continue

            try:
                with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                    f.write(f"[UI Cards] ADDED to render list: {offer_id}\n")
            except:
                pass

            all_offers.append({
                **offer,
                "direction": "incoming"
            })

        # Write to log file
        try:
            with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                f.write(f"[UI _render_conditional_cards] After filtering: {len(all_offers)} offers to render\n")
                for i, offer in enumerate(all_offers[:5]):
                    f.write(f"  [{i}] {offer.get('offer_id')}: {offer.get('direction')}, {len(offer.get('conditions', []))} conds\n")
        except:
            pass

        print(f"[UI _render_conditional_cards] After filtering: {len(all_offers)} offers to render")
        for i, offer in enumerate(all_offers[:3]):
            print(f"  [{i}] {offer.get('offer_id')}: {offer.get('direction')}, {len(offer.get('conditions', []))} conds")

        # Check if the offers have actually changed since last render
        # This prevents unnecessary flickering when nothing has changed
        # Include feasibility queries in signature so responses trigger re-render
        offers_signature = self._compute_offers_signature(all_offers, self._feasibility_queries)

        # Write signature info to log
        try:
            with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                f.write(f"[UI Cards] Computed signature: {offers_signature[:16]}... for {len(all_offers)} offers\n")
                if hasattr(self, '_last_offers_signature'):
                    f.write(f"[UI Cards] Last signature: {self._last_offers_signature[:16]}...\n")
                    f.write(f"[UI Cards] Signatures match: {self._last_offers_signature == offers_signature}\n")
        except:
            pass

        if hasattr(self, '_last_offers_signature') and self._last_offers_signature == offers_signature:
            # No changes detected, skip re-rendering
            print(f"[UI _render_conditional_cards] Offers signature unchanged - skipping render")
            try:
                with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                    f.write(f"[UI Cards] SKIPPING render - signature unchanged\n")
            except:
                pass
            return

        print(f"[UI _render_conditional_cards] Offers signature changed - rendering {len(all_offers)} cards")
        try:
            with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                f.write(f"[UI Cards] RENDERING {len(all_offers)} cards - signature changed\n")
        except:
            pass
        # Store the new signature
        self._last_offers_signature = offers_signature

        # Clear existing cards (only if we're actually going to rebuild)
        try:
            for widget in self._conditionals_cards_inner.winfo_children():
                widget.destroy()
        except Exception:
            return  # UI is being destroyed, skip rendering

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

            # Check if this is a status update (unconditional THEN-only)
            reasons = cond.get("reasons", [])
            is_boundary_update = any("boundary_update" in str(r) for r in reasons)
            conditions = cond.get("conditions", [])
            is_status_update = (is_boundary_update or (not conditions or len(conditions) == 0))

            # Create card frame
            card = tk.Frame(
                self._conditionals_cards_inner,
                bg=card_bg,
                relief=tk.RAISED,
                borderwidth=2
            )
            card.pack(fill="x", padx=5, pady=5)

            # For status updates, use compact inline format
            if is_status_update and direction == "incoming":
                sender = cond.get('sender', 'Unknown')
                assignments = cond.get("assignments", [])

                if assignments:
                    assign_str = ", ".join([f"{a.get('node')}={a.get('colour')}" for a in assignments])
                    tk.Label(
                        card,
                        text=f"📍 {sender}: {assign_str}",
                        font=("Arial", 9),
                        bg=card_bg
                    ).pack(anchor="w", padx=8, pady=4)
                else:
                    tk.Label(
                        card,
                        text=f"📍 {sender}: (no assignments)",
                        font=("Arial", 9),
                        bg=card_bg
                    ).pack(anchor="w", padx=8, pady=4)

                # Skip the detailed IF/THEN sections for status updates
                continue

            # Offer ID header with direction indicator (for conditional offers)
            if direction == "outgoing":
                direction_arrow = "->"
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
                # For incoming offers, show Accept/Reject/Counter buttons
                # BUT: boundary updates are just informational, don't need buttons
                if is_boundary_update:
                    tk.Label(
                        btn_frame,
                        text="ℹ Agent's current state",
                        fg="#666",
                        font=("Arial", 9, "italic"),
                        bg=card_bg
                    ).pack(side="left")
                elif cond.get("status") == "pending":
                    ttk.Button(
                        btn_frame,
                        text="Accept",
                        command=lambda oid=cond.get("offer_id"): self._accept_offer(oid)
                    ).pack(side="left", padx=2)

                    ttk.Button(
                        btn_frame,
                        text="Reject",
                        command=lambda oid=cond.get("offer_id"): self._reject_offer(oid)
                    ).pack(side="left", padx=2)

                    ttk.Button(
                        btn_frame,
                        text="Counter",
                        command=lambda oid=cond.get("offer_id"): self._counter_offer(oid)
                    ).pack(side="left", padx=2)
                elif cond.get("status") == "rejected":
                    tk.Label(
                        btn_frame,
                        text="✗ Rejected",
                        fg="red",
                        font=("Arial", 9, "bold"),
                        bg=card_bg
                    ).pack(side="left")
                else:
                    tk.Label(
                        btn_frame,
                        text="✓ Accepted",
                        fg="green",
                        font=("Arial", 9, "bold"),
                        bg=card_bg
                    ).pack(side="left")

        # Render feasibility queries
        for neigh in self._neighs:
            if neigh in self._feasibility_queries and self._feasibility_queries[neigh]:
                # Add section header
                tk.Label(
                    self._conditionals_cards_inner,
                    text=f"Feasibility Queries - {neigh}:",
                    font=("Arial", 10, "bold"),
                    bg="white"
                ).pack(anchor="w", padx=5, pady=(10, 5))

                for query in self._feasibility_queries[neigh]:
                    # Create query card
                    query_card = tk.Frame(
                        self._conditionals_cards_inner,
                        bg="#f0f0f0",
                        relief=tk.RIDGE,
                        borderwidth=2
                    )
                    query_card.pack(fill="x", padx=5, pady=3)

                    # Header
                    header_text = f"Query {query['query_id'][-8:]}"
                    tk.Label(
                        query_card,
                        text=header_text,
                        font=("Arial", 9, "bold"),
                        bg="#f0f0f0"
                    ).pack(anchor="w", padx=5, pady=2)

                    # Conditions
                    cond_str = " AND ".join([f"{c['node']}={c['colour']}" for c in query['conditions']])
                    tk.Label(
                        query_card,
                        text=f"IF {cond_str}",
                        font=("Arial", 9),
                        bg="#f0f0f0"
                    ).pack(anchor="w", padx=10)

                    # Result
                    if query.get('is_feasible') is not None:
                        if query['is_feasible']:
                            result_text = "✓ Valid Coloring Possible"
                            result_color = "green"
                        else:
                            result_text = "✗ No Valid Coloring"
                            result_color = "red"

                        tk.Label(
                            query_card,
                            text=result_text,
                            fg=result_color,
                            font=("Arial", 9, "bold"),
                            bg="#f0f0f0"
                        ).pack(anchor="w", padx=10, pady=2)

                        if query.get('feasibility_details'):
                            tk.Label(
                                query_card,
                                text=query['feasibility_details'],
                                font=("Arial", 8),
                                wraplength=200,
                                bg="#f0f0f0"
                            ).pack(anchor="w", padx=10, pady=2)

                        # Add buttons for required assignments if feasible
                        if query['is_feasible']:
                            required_assigns = query.get('required_assignments', [])

                            if required_assigns:
                                # Show individual buttons for each required assignment option
                                tk.Label(
                                    query_card,
                                    text="Required boundary colors:",
                                    font=("Arial", 8, "bold"),
                                    bg="#f0f0f0"
                                ).pack(anchor="w", padx=10, pady=(8, 2))

                                choose_frame = tk.Frame(query_card, bg="#f0f0f0")
                                choose_frame.pack(pady=(2, 4))

                                # Create a button for choosing this specific configuration
                                assign_str = ", ".join([f"{a['node']}={a['colour']}" for a in required_assigns])
                                ttk.Button(
                                    choose_frame,
                                    text=f"✓ Set {assign_str}",
                                    command=lambda q=query, n=neigh: self._apply_feasibility_config(q, n)
                                ).pack()
                            else:
                                # No specific requirements - just a general accept button
                                choose_frame = tk.Frame(query_card, bg="#f0f0f0")
                                choose_frame.pack(pady=(8, 4))

                                ttk.Button(
                                    choose_frame,
                                    text="✓ Any configuration works",
                                    command=lambda q=query, n=neigh: self._apply_feasibility_conditions(q, n)
                                ).pack()
                    else:
                        tk.Label(
                            query_card,
                            text="⏳ Waiting for response...",
                            font=("Arial", 9, "italic"),
                            bg="#f0f0f0"
                        ).pack(anchor="w", padx=10, pady=2)

                    # Dismiss button
                    def dismiss_query(n=neigh, qid=query['query_id']):
                        self._feasibility_queries[n] = [q for q in self._feasibility_queries[n] if q['query_id'] != qid]
                        self._render_conditional_cards()

                    ttk.Button(
                        query_card,
                        text="Dismiss",
                        command=dismiss_query
                    ).pack(anchor="e", padx=5, pady=2)

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
        # CRITICAL FIX: Debounce updates to prevent flashing
        # Only update if conditionals actually changed
        import hashlib
        import json

        # Write to log file for debugging
        try:
            with open("E:\\Files\\PhD-Main\\GC-New\\GIT_LOCAL_ROOT\\GraphColouringNew\\results\\rb\\ui_debug.log", "a") as f:
                f.write(f"\n[UI update_conditionals] Called with {len(conditionals)} conditionals\n")
                for i, cond in enumerate(conditionals[:5]):
                    f.write(f"  [{i}] {cond.get('offer_id', 'no_id')}: {len(cond.get('conditions', []))} conds, {len(cond.get('assignments', []))} assigns\n")
        except:
            pass

        print(f"[UI update_conditionals] Called with {len(conditionals)} conditionals")
        for i, cond in enumerate(conditionals[:3]):  # Print first 3
            print(f"  [{i}] {cond.get('offer_id', 'no_id')}: {len(cond.get('conditions', []))} conds")

        # Compute signature of incoming conditionals
        try:
            conditionals_str = json.dumps(conditionals, sort_keys=True, default=str)
            new_signature = hashlib.md5(conditionals_str.encode()).hexdigest()
        except:
            new_signature = str(conditionals)

        # Check if conditionals actually changed
        if hasattr(self, '_last_conditionals_signature') and self._last_conditionals_signature == new_signature:
            # No change - skip update to prevent unnecessary re-renders
            print(f"[UI update_conditionals] Signature unchanged - skipping render")
            return

        print(f"[UI update_conditionals] Signature changed - triggering render")
        self._last_conditionals_signature = new_signature
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
        print(f"[UI update_configurations] Called with {len(configurations)} configurations")
        print(f"[UI update_configurations] Current phase: {self._phase}")
        print(f"[UI update_configurations] Neighbors: {self._neighs}")

        # Convert list to dict keyed by agent name
        self._agent_configurations = {}
        for config in configurations:
            agent = config.get("sender", "")
            assignments = config.get("assignments", [])
            print(f"[UI update_configurations] Processing config from {agent} with {len(assignments)} assignments")

            if agent not in self._agent_configurations:
                self._agent_configurations[agent] = {}

            for assign in assignments:
                node = assign.get("node", "")
                colour = assign.get("colour", "")
                if node and colour:
                    self._agent_configurations[agent][node] = colour

        print(f"[UI update_configurations] Agent configurations keys: {list(self._agent_configurations.keys())}")

        # Check if all agents have announced (auto-transition to Step 2)
        if self._phase == "configure":
            all_configured = all(n in self._agent_configurations for n in self._neighs)
            print(f"[UI update_configurations] all_configured check: {all_configured}")
            print(f"[UI update_configurations] Checking: {[(n, n in self._agent_configurations) for n in self._neighs]}")

            if all_configured:
                print("[UI] Auto-transition: All agents configured - transitioning to bargain phase")
                # Transition to bargain phase
                self._phase = "bargain"

                # Update phase banner
                if self._phase_banner_label:
                    self._phase_banner_label.config(
                        text="💬 STEP 2: BARGAINING - Negotiate with agents",
                        bg="#5cb85c"  # Green for bargain
                    )

                # Enable conditional builders
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

                # Enable impossible button
                if hasattr(self, '_impossible_btn'):
                    self._impossible_btn.config(state="normal")

                # DISABLE auto-suggestion for all modes with announcement phase
                # Agents should respond to human messages, not auto-suggest
                has_announcement = getattr(self, '_has_announcement_phase', False) or getattr(self, '_llm_rb_mode', False)
                if not has_announcement and not self._auto_suggest_enabled:
                    print("[AutoSuggest] All agents configured - enabling auto-suggestions")
                    self._auto_suggest_enabled = True
                    self._schedule_auto_suggest()
                elif has_announcement:
                    print("[AutoSuggest] Disabled in announcement-based modes")

        # Trigger UI refresh
        if self._root is not None:
            self._root.after(0, self._render_configuration_status)

    def _get_affected_neighbors(self, changed_nodes: List[str]) -> List[str]:
        """Determine which neighbors are affected by changes to specific nodes.

        A neighbor is affected if any of the changed nodes is adjacent to
        a node owned by that neighbor.

        Parameters
        ----------
        changed_nodes : list of str
            List of node names that changed

        Returns
        -------
        list of str
            List of neighbor names that are affected by the changes
        """
        affected = set()

        for node in changed_nodes:
            # Get all nodes adjacent to this changed node
            if node in self._adjacency:
                for adjacent_node in self._adjacency[node]:
                    # Check who owns the adjacent node
                    owner = self._owners.get(adjacent_node)
                    if owner and owner != "Human" and owner in self._neighs:
                        affected.add(owner)
                        print(f"[Affected Check] {node} is adjacent to {adjacent_node} (owned by {owner})")

        return list(affected)

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
            assignments = offer.get("assignments", [])

            print(f"\n[Human Accept] ===== ACCEPTING OFFER {offer_id} =====")
            print(f"[Human Accept] From: {sender}")
            print(f"[Human Accept] CONDITIONS (what YOU will do):")
            for cond in conditions:
                print(f"[Human Accept]   • {cond.get('node')} = {cond.get('colour')}")
            print(f"[Human Accept] ASSIGNMENTS (what THEY will do):")
            for assign in assignments:
                print(f"[Human Accept]   • {assign.get('node')} = {assign.get('colour')}")

            changed_nodes = []
            for cond in conditions:
                node = cond.get("node")
                colour = cond.get("colour")
                if node and colour and node in self._assignments:
                    old_colour = self._assignments.get(node)
                    self._assignments[node] = colour
                    changed_nodes.append((node, colour))
                    print(f"[Human Accept] ✓ Applied to YOUR node: {node}: {old_colour} -> {colour}")
                elif node and colour:
                    print(f"[Human Accept] ⚠️  WARNING: Condition on node '{node}' not in your assignments!")

            print(f"[Human Accept] Total nodes changed: {len(changed_nodes)}")
            print(f"[Human Accept] ===== END ACCEPT =====\n")

            # Update graph display
            self._redraw_graph()

            # Update HUD score display
            if self._hud_var:
                self._hud_var.set(self._hud_text())

            # Update move counter
            if changed_nodes:
                self._move_count += len(changed_nodes)
                self._refresh_move_counter()

            # Notify callback for color changes
            if changed_nodes and self._on_colour_change:
                self._on_colour_change(dict(self._assignments))

            # CLEAR all offers and messages from this sender
            # Remove all conditionals from this sender
            self._active_conditionals = [c for c in self._active_conditionals if c.get("sender") != sender]
            self._render_conditional_cards()

            # Clear the transcript for this neighbor and add acceptance message
            self._transcripts[sender] = []
            self._append_to_transcript(sender, f"[You] ✓ Accepted offer #{offer_id} - reconsidering...")
            self._refresh_transcript(sender)

            # Send Accept message via RB protocol
            try:
                from comm.rb_protocol import RBMove, format_rb, pretty_rb
                accept_move = RBMove(
                    move="Accept",
                    refers_to=offer_id,
                    reasons=["human_accepted"]
                )
                msg_text = format_rb(accept_move) + " " + pretty_rb(accept_move)

                # Send via the normal message pipeline and capture response
                if self._on_send:
                    def _send_accept():
                        try:
                            reply = self._invoke_on_send(sender, msg_text)
                            if reply and self._root:
                                # Add the agent's response to the UI
                                self._root.after(0, lambda r=reply, s=sender: self.add_incoming(s, r))
                        except Exception as e:
                            print(f"Error in accept send: {e}")
                            import traceback
                            traceback.print_exc()

                    threading.Thread(target=_send_accept, daemon=True).start()
                    self._set_status(sender, "sending...")
            except Exception as e:
                print(f"Error accepting offer: {e}")

            # CRITICAL FIX #12: Notify agents when human fulfills conditions
            # When accepting an offer, agents need to know the human's colors changed!
            # Without this, agents see stale neighbour_assignments and have penalty>0.
            if changed_nodes or sender:
                # Determine which neighbors are affected by the changed nodes
                affected_neighbors = set()

                if changed_nodes:
                    affected_neighbors = set(self._get_affected_neighbors([node for node, _ in changed_nodes]))

                # ALWAYS include the sender of the offer (they need to know their offer was accepted)
                if sender and sender in self._neighs:
                    affected_neighbors.add(sender)

                if affected_neighbors:
                    print(f"[Human Accept] Notifying {list(affected_neighbors)} of color changes: {[node for node, _ in changed_nodes]}")

                    for n in affected_neighbors:
                        def _send_announcement(neigh=n):
                            try:
                                import inspect
                                sig = inspect.signature(self._on_send)
                                if len(sig.parameters) >= 3:
                                    # New signature with current_assignments
                                    reply = self._on_send(neigh, "__ANNOUNCE_CONFIG__", dict(self._assignments))
                                else:
                                    # Old signature without current_assignments
                                    reply = self._on_send(neigh, "__ANNOUNCE_CONFIG__")

                                # Add the agent's response to the UI
                                if reply and self._root:
                                    self._root.after(0, lambda r=reply, n=neigh: self.add_incoming(n, r))
                            except Exception as e:
                                print(f"[Human Accept ERROR] Failed to notify {neigh}: {e}")
                                import traceback
                                traceback.print_exc()

                        threading.Thread(target=_send_announcement, daemon=True).start()

    def _apply_feasibility_conditions(self, query: Dict[str, Any], neighbor: str) -> None:
        """Apply feasibility query conditions to human assignments and announce.

        When feasibility check returns feasible, clicking "Choose This" instantly
        adopts those conditions as the human's configuration.
        """
        print(f"\n[Choose This] ===== APPLYING FEASIBILITY CONDITIONS =====")
        print(f"[Choose This] Query structure: {query}")
        conditions = query.get("conditions", [])
        print(f"[Choose This] Found {len(conditions)} conditions")

        # Apply each condition to human's assignments
        changes = {}
        for cond in conditions:
            node = cond.get("node")
            colour = cond.get("colour")
            print(f"[Choose This] Processing condition: {node}={colour}")
            if node and colour:
                # Verify this is a human-owned node
                owner = self._owners.get(node)
                print(f"[Choose This]   Node owner: {owner}")
                if owner == "Human":
                    old_color = self._assignments.get(node)
                    self._assignments[node] = colour
                    changes[node] = (old_color, colour)
                    print(f"[Choose This]   ✓ Changed {node}: {old_color} -> {colour}")
                else:
                    print(f"[Choose This]   ✗ Skipping (not Human-owned)")
            else:
                print(f"[Choose This]   ✗ Skipping (missing node or colour)")

        if not changes:
            print("[Choose This] ⚠️  WARNING: No changes to apply!")
            print("[Choose This] This means either:")
            print("[Choose This]   - No conditions in the query")
            print("[Choose This]   - Conditions are for non-Human nodes")
            print("[Choose This]   - Conditions are missing node/colour data")
            print(f"[Choose This] ===== END (NO CHANGES) =====\n")
            return

        print(f"[Choose This] Successfully changed {len(changes)} nodes")
        print(f"[Choose This] ===== END =====\n")

        # CLEAR all offers and messages from this neighbor
        # Remove all conditionals from this neighbor
        self._active_conditionals = [c for c in self._active_conditionals if c.get("sender") != neighbor]

        # CRITICAL FIX #17: Remove query from _feasibility_queries so signature changes
        query_id = query.get('query_id')
        if query_id and neighbor in self._feasibility_queries:
            self._feasibility_queries[neighbor] = [
                q for q in self._feasibility_queries[neighbor]
                if q.get('query_id') != query_id
            ]

        self._render_conditional_cards()

        # Log to transcript
        change_str = ", ".join([f"{n}: {old}->{new}" for n, (old, new) in changes.items()])

        # Clear the transcript for this neighbor and add acceptance message
        self._transcripts[neighbor] = []
        self._append_to_transcript(
            neighbor,
            f"[You] ✓ Applied feasibility conditions: {change_str} - reconsidering..."
        )
        self._refresh_transcript(neighbor)

        # Redraw graph with new assignments
        self._redraw_graph()

        # Update HUD score display
        if self._hud_var:
            self._hud_var.set(self._hud_text())

        # Update move counter
        if changes:
            self._move_count += len(changes)
            self._refresh_move_counter()

        # Notify callback for color changes
        if self._on_colour_change:
            self._on_colour_change(dict(self._assignments))

        # Announce to AFFECTED neighbors only
        # ALWAYS include the neighbor who sent the feasibility response
        changed_node_list = list(changes.keys())
        affected_neighbors = set(self._get_affected_neighbors(changed_node_list))

        # Add the neighbor who provided this feasibility check
        if neighbor and neighbor in self._neighs:
            affected_neighbors.add(neighbor)
            print(f"[Choose This] Including feasibility sender '{neighbor}' in affected neighbors")

        if affected_neighbors:
            print(f"[Choose This] Announcing to affected neighbors: {list(affected_neighbors)}")

            for n in affected_neighbors:
                def _send_announcement(neigh=n):
                    try:
                        import inspect
                        sig = inspect.signature(self._on_send)
                        if len(sig.parameters) >= 3:
                            reply = self._on_send(neigh, "__ANNOUNCE_CONFIG__", dict(self._assignments))
                        else:
                            reply = self._on_send(neigh, "__ANNOUNCE_CONFIG__")

                        if reply and self._root:
                            self._root.after(0, lambda r=reply, n=neigh: self.add_incoming(n, r))
                    except Exception as e:
                        print(f"[Choose This] Error announcing to {neigh}: {e}")

                threading.Thread(target=_send_announcement, daemon=True).start()

            print(f"[Choose This] Applied {len(changes)} changes and announced to {len(affected_neighbors)} affected neighbors")
        else:
            print(f"[Choose This] Applied {len(changes)} changes (no neighbors affected)")

    def _apply_feasibility_config(self, query: Dict[str, Any], neighbor: str) -> None:
        """Apply feasibility query conditions AND required assignments to human's nodes.

        When feasibility check returns "Yes, if X=Y", clicking the button
        adopts both the queried conditions and the required boundary assignments.

        CRITICAL: This ensures BOTH the human's query (conditions) AND the agent's
        requirements (required_assignments) are applied, creating a clash-free configuration.
        """
        print(f"\n[Apply Config] ===== APPLYING FEASIBILITY CONFIG =====")
        print(f"[Apply Config] Neighbor: {neighbor}")
        print(f"[Apply Config] Query structure: {query}")
        print(f"[Apply Config] Current human assignments: {self._assignments}")
        conditions = query.get("conditions", [])
        required_assigns = query.get("required_assignments", [])
        print(f"[Apply Config] Found {len(conditions)} conditions (human's query), {len(required_assigns)} required assignments (agent's requirements)")

        # Apply queried conditions
        changes = {}
        for cond in conditions:
            node = cond.get("node")
            colour = cond.get("colour")
            print(f"[Apply Config] Processing condition: {node}={colour}")
            if node and colour:
                owner = self._owners.get(node)
                if owner == "Human":
                    old_color = self._assignments.get(node)
                    self._assignments[node] = colour
                    changes[node] = (old_color, colour)
                    print(f"[Apply Config]   ✓ Changed {node}: {old_color} -> {colour}")
                else:
                    print(f"[Apply Config]   ✗ Skipping (owner={owner})")

        # Apply required assignments
        for assign in required_assigns:
            node = assign.get("node")
            colour = assign.get("colour")
            print(f"[Apply Config] Processing required: {node}={colour}")
            if node and colour:
                owner = self._owners.get(node)
                if owner == "Human":
                    old_color = self._assignments.get(node)
                    self._assignments[node] = colour
                    changes[node] = (old_color, colour)
                    print(f"[Apply Config]   ✓ Required: {node}: {old_color} -> {colour}")
                else:
                    print(f"[Apply Config]   ✗ Skipping (owner={owner})")

        if not changes:
            print("[Apply Config] ⚠️  WARNING: No changes to apply!")
            print(f"[Apply Config] ===== END (NO CHANGES) =====\n")
            return

        print(f"[Apply Config] Successfully changed {len(changes)} nodes")
        print(f"[Apply Config] Final human assignments: {self._assignments}")
        print(f"[Apply Config] Changes applied: {changes}")
        print(f"[Apply Config] ===== END =====\n")

        # CLEAR all offers and messages from this neighbor
        # Remove all conditionals from this neighbor
        self._active_conditionals = [c for c in self._active_conditionals if c.get("sender") != neighbor]

        # CRITICAL FIX #17: Remove query from _feasibility_queries so signature changes
        query_id = query.get('query_id')
        if query_id and neighbor in self._feasibility_queries:
            self._feasibility_queries[neighbor] = [
                q for q in self._feasibility_queries[neighbor]
                if q.get('query_id') != query_id
            ]

        self._render_conditional_cards()

        # Log to transcript
        change_str = ", ".join([f"{n}: {old}->{new}" for n, (old, new) in changes.items()])

        # Clear the transcript for this neighbor and add acceptance message
        self._transcripts[neighbor] = []
        self._append_to_transcript(
            neighbor,
            f"[You] ✓ Applied feasibility configuration: {change_str} - reconsidering..."
        )
        self._refresh_transcript(neighbor)

        # Redraw graph with new assignments
        self._redraw_graph()

        # Update HUD score display
        if self._hud_var:
            self._hud_var.set(self._hud_text())

        # Update move counter
        if changes:
            self._move_count += len(changes)
            self._refresh_move_counter()

        # Notify callback for color changes
        if self._on_colour_change:
            self._on_colour_change(dict(self._assignments))

        # Announce to AFFECTED neighbors only
        # ALWAYS include the neighbor who sent the feasibility response
        changed_node_list = list(changes.keys())
        affected_neighbors = set(self._get_affected_neighbors(changed_node_list))

        # Add the neighbor who provided this feasibility check
        if neighbor and neighbor in self._neighs:
            affected_neighbors.add(neighbor)
            print(f"[Apply Config] Including feasibility sender '{neighbor}' in affected neighbors")

        if affected_neighbors:
            print(f"[Apply Config] Announcing to affected neighbors: {list(affected_neighbors)}")

            for n in affected_neighbors:
                def _send_announcement(neigh=n):
                    try:
                        import inspect
                        sig = inspect.signature(self._on_send)
                        if len(sig.parameters) >= 3:
                            reply = self._on_send(neigh, "__ANNOUNCE_CONFIG__", dict(self._assignments))
                        else:
                            reply = self._on_send(neigh, "__ANNOUNCE_CONFIG__")

                        if reply and self._root:
                            self._root.after(0, lambda r=reply, n=neigh: self.add_incoming(n, r))
                    except Exception as e:
                        print(f"[Apply Config] Error announcing to {neigh}: {e}")

                threading.Thread(target=_send_announcement, daemon=True).start()

            print(f"[Apply Config] Applied {len(changes)} changes and announced to {len(affected_neighbors)} affected neighbors")
        else:
            print(f"[Apply Config] Applied {len(changes)} changes (no neighbors affected)")

    def _reject_offer_with_dialog(self, offer_id: str, sender: str, offer: Dict) -> Optional[Any]:
        """Enhanced dialog to mark individual conditions or combinations as impossible.

        Returns RBMove for rejection, or None if cancelled.
        """
        dialog = tk.Toplevel(self._root)
        dialog.title(f"Reject Offer from {sender}")
        dialog.geometry("600x600")
        dialog.transient(self._root)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        result = {
            "cancelled": False,
            "impossible_individuals": [],
            "impossible_combinations": []
        }

        # Header
        tk.Label(dialog, text="Mark conditions as IMPOSSIBLE", font=("Arial", 11, "bold"), pady=10).pack()

        # Main scrollable area
        canvas = tk.Canvas(dialog, height=420)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y")

        conditions = offer.get("conditions", [])
        condition_options = [(c.get("node", "?"), c.get("colour", "?")) for c in conditions]

        # SECTION 1: Individual Conditions
        tk.Label(scrollable_frame, text="Individual conditions (NEVER acceptable):",
                 font=("Arial", 9, "bold")).pack(anchor="w", pady=(5, 5))

        tk.Label(scrollable_frame, text="Check if the condition is impossible by itself",
                 font=("Arial", 8, "italic"), fg="#666").pack(anchor="w", padx=10, pady=(0, 5))

        individual_vars = []

        if conditions:
            for node, colour in condition_options:
                var = tk.BooleanVar(value=False)
                individual_vars.append((var, node, colour))
                tk.Checkbutton(scrollable_frame, text=f"{node} = {colour}", variable=var,
                              font=("Arial", 10)).pack(anchor="w", padx=20, pady=2)
        else:
            tk.Label(scrollable_frame, text="This offer has no conditions.",
                    font=("Arial", 9, "italic")).pack(anchor="w", padx=20, pady=5)

        # Separator
        ttk.Separator(scrollable_frame, orient='horizontal').pack(fill='x', pady=15)

        # SECTION 2: Combinations
        tk.Label(scrollable_frame, text="Combinations (only impossible TOGETHER):",
                 font=("Arial", 9, "bold")).pack(anchor="w", pady=(5, 5))

        tk.Label(scrollable_frame, text="Select 2+ conditions that are impossible together (but OK separately)",
                 font=("Arial", 8, "italic"), fg="#666").pack(anchor="w", padx=10, pady=(0, 5))

        # Combination builder frame
        combo_builder_frame = ttk.Frame(scrollable_frame)
        combo_builder_frame.pack(fill="x", padx=20, pady=5)

        # Dropdown selectors for building combinations
        combo_selections = []  # List of StringVars for dropdowns
        combo_dropdown_frame = ttk.Frame(combo_builder_frame)
        combo_dropdown_frame.pack(fill="x", pady=5)

        def add_combo_dropdown():
            """Add another dropdown to select conditions for combination."""
            row = ttk.Frame(combo_dropdown_frame)
            row.pack(fill="x", pady=2)

            tk.Label(row, text=f"Condition {len(combo_selections)+1}:", font=("Arial", 9)).pack(side="left", padx=2)

            var = tk.StringVar(value="(select)")
            options = ["(select)"] + [f"{n}={c}" for n, c in condition_options]
            combo = ttk.Combobox(row, textvariable=var, values=options, state="readonly", width=20)
            combo.pack(side="left", padx=2)

            combo_selections.append(var)

            # Remove button
            def remove_dropdown():
                row.destroy()
                combo_selections.remove(var)

            ttk.Button(row, text="✗", width=3, command=remove_dropdown).pack(side="left", padx=2)

        # Start with 2 dropdowns
        if len(conditions) >= 2:
            add_combo_dropdown()
            add_combo_dropdown()

            ttk.Button(combo_builder_frame, text="+ Add Another Condition", command=add_combo_dropdown).pack(anchor="w", pady=2)

            # List of marked combinations
            marked_combos_label = tk.Label(scrollable_frame, text="Marked combinations:", font=("Arial", 9, "bold"))
            marked_combos_label.pack(anchor="w", padx=20, pady=(10, 5))

            marked_combos_frame = ttk.Frame(scrollable_frame)
            marked_combos_frame.pack(fill="x", padx=20, pady=5)

            marked_combinations = []  # List of frozenset tuples

            def update_marked_combos_display():
                """Refresh the list of marked combinations."""
                for widget in marked_combos_frame.winfo_children():
                    widget.destroy()

                if not marked_combinations:
                    tk.Label(marked_combos_frame, text="(none yet)", font=("Arial", 8, "italic"), fg="#999").pack(anchor="w")
                else:
                    for combo in marked_combinations:
                        row = ttk.Frame(marked_combos_frame)
                        row.pack(fill="x", pady=2)

                        combo_str = " AND ".join([f"{n}={c}" for n, c in sorted(combo)])
                        tk.Label(row, text=f"• ({combo_str})", font=("Arial", 9)).pack(side="left")

                        def remove_combo(c=combo):
                            marked_combinations.remove(c)
                            update_marked_combos_display()

                        ttk.Button(row, text="✗ Remove", command=remove_combo).pack(side="left", padx=5)

            def add_combination():
                """Add selected conditions to marked combinations list."""
                selected_conds = []
                for var in combo_selections:
                    val = var.get()
                    if val and val != "(select)":
                        # Parse "h1=red" format
                        match = re.match(r'(\w+)=(\w+)', val)
                        if match:
                            node, colour = match.groups()
                            selected_conds.append((node, colour))

                if len(selected_conds) < 2:
                    import tkinter.messagebox as messagebox
                    messagebox.showwarning("Invalid Combination", "Please select at least 2 conditions for a combination")
                    return

                combo_set = frozenset(selected_conds)
                if combo_set not in marked_combinations:
                    marked_combinations.append(combo_set)
                    update_marked_combos_display()

                    # Reset dropdowns
                    for var in combo_selections:
                        var.set("(select)")
                else:
                    import tkinter.messagebox as messagebox
                    messagebox.showinfo("Duplicate", "This combination is already marked")

            ttk.Button(combo_builder_frame, text="✓ Add to List", command=add_combination).pack(anchor="w", pady=5)

            update_marked_combos_display()
        else:
            tk.Label(scrollable_frame, text="(Need 2+ conditions for combinations)",
                    font=("Arial", 8, "italic"), fg="#999").pack(anchor="w", padx=20, pady=5)
            marked_combinations = []

        # Buttons
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(side="bottom", pady=10)

        def on_reject():
            """User confirmed rejection."""
            result["cancelled"] = False

            # Collect individual impossibilities
            result["impossible_individuals"] = [
                {"node": node, "colour": colour}
                for var, node, colour in individual_vars
                if var.get()
            ]

            # Collect combination impossibilities
            result["impossible_combinations"] = [
                [{"node": node, "colour": colour} for node, colour in combo]
                for combo in marked_combinations
            ]

            dialog.destroy()

        def on_cancel():
            result["cancelled"] = True
            dialog.destroy()

        ttk.Button(btn_frame, text="Reject Offer", command=on_reject).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side="left", padx=5)

        dialog.wait_window()

        if result["cancelled"]:
            return None

        # Build rejection move
        from comm.rb_protocol import RBMove

        reject_move = RBMove(
            move="Reject",
            refers_to=offer_id,
            reasons=["human_rejected", "unacceptable_terms"]
        )

        if result["impossible_individuals"]:
            reject_move.impossible_conditions = result["impossible_individuals"]
            print(f"[Reject Dialog] Marked {len(result['impossible_individuals'])} individual conditions")

        if result["impossible_combinations"]:
            reject_move.impossible_combinations = result["impossible_combinations"]
            print(f"[Reject Dialog] Marked {len(result['impossible_combinations'])} combinations")

        return reject_move

    def _reject_offer(self, offer_id: str) -> None:
        """Handle rejecting a conditional offer."""
        # Find the offer
        offer = None
        for cond in self._active_conditionals:
            if cond.get("offer_id") == offer_id:
                offer = cond
                break

        if not offer:
            print(f"[Reject] Could not find offer {offer_id}")
            return

        sender = offer.get("sender")
        if not sender:
            print(f"[Reject] No sender for offer {offer_id}")
            return

        print(f"[Reject] Rejecting offer {offer_id} from {sender}")

        # NEW: Show dialog to let user mark impossible conditions
        reject_move = self._reject_offer_with_dialog(offer_id, sender, offer)

        if reject_move is None:
            print(f"[Reject] User cancelled rejection")
            return

        # Mark offer as rejected in UI
        offer["status"] = "rejected"
        self._render_conditional_cards()

        # Build message
        try:
            from comm.rb_protocol import format_rb, pretty_rb

            msg_text = format_rb(reject_move) + " " + pretty_rb(reject_move)

            # Append to transcript
            impossible_count = len(reject_move.impossible_conditions) if reject_move.impossible_conditions else 0
            if impossible_count > 0:
                self._append_to_transcript(
                    sender,
                    f"[You -> {sender}] Reject offer {offer_id} ({impossible_count} conditions marked impossible)"
                )
            else:
                self._append_to_transcript(sender, f"[You -> {sender}] Reject offer {offer_id}")

            # Send rejection message
            if self._on_send:
                def _send_reject():
                    try:
                        import inspect
                        sig = inspect.signature(self._on_send)
                        params = sig.parameters
                        if len(params) >= 3:
                            reply = self._on_send(sender, msg_text, dict(self._assignments))
                        else:
                            reply = self._on_send(sender, msg_text)

                        if self._root and reply:
                            self._root.after(0, lambda: self.add_incoming(sender, reply))
                    except Exception as e:
                        print(f"Error sending rejection: {e}")

                threading.Thread(target=_send_reject, daemon=True).start()
                self._set_status(sender, "sending rejection...")
        except Exception as e:
            print(f"Error rejecting offer: {e}")
            import traceback
            traceback.print_exc()

    def _counter_offer(self, offer_id: str) -> None:
        """Handle countering a conditional offer by pre-populating the builder."""
        # Find the offer in active conditionals
        offer = None
        for cond in self._active_conditionals:
            if cond.get("offer_id") == offer_id:
                offer = cond
                break

        if not offer:
            print(f"[Counter] Could not find offer {offer_id}")
            return

        sender = offer.get("sender")
        if not sender:
            print(f"[Counter] No sender for offer {offer_id}")
            return

        print(f"[Counter] Preparing counter-offer to {sender} for offer {offer_id}")

        # Clear existing rows for this neighbor
        self._clear_conditional_builder(sender)

        # Pre-populate with counter-proposal:
        # - Their assignments become our conditions (what they WILL do if we agree)
        # - Leave assignments empty for user to fill (what WE will do)
        assignments = offer.get("assignments", [])

        # Add condition rows for each of their assignments
        for assign in assignments:
            node = assign.get("node")
            colour = assign.get("colour")
            if node and colour:
                self._add_condition_row(sender, f"{node}={colour}")

        print(f"[Counter] Pre-populated {len(assignments)} conditions for counter-offer to {sender}")
        print(f"[Counter] User should now specify what they will do in the THEN section")

    def _clear_conditional_builder(self, neighbor: str) -> None:
        """Clear all condition and assignment rows for a neighbor."""
        # Clear condition rows
        if neighbor in self._condition_rows:
            for row_frame, _ in list(self._condition_rows[neighbor]):
                row_frame.destroy()
            self._condition_rows[neighbor] = []

        # Clear assignment rows
        if neighbor in self._assignment_rows:
            for row_frame, _, _ in list(self._assignment_rows[neighbor]):
                row_frame.destroy()
            self._assignment_rows[neighbor] = []

    def _add_condition_row(self, neighbor: str, statement: str) -> None:
        """Add a condition row pre-populated with the given statement."""
        if neighbor not in self._add_condition_funcs:
            print(f"[Counter] No add_condition function for {neighbor}")
            return

        add_func = self._add_condition_funcs[neighbor]
        row_frame = add_func()

        # Find the statement variable and set it
        # The row contains (frame, statement_var)
        if neighbor in self._condition_rows and len(self._condition_rows[neighbor]) > 0:
            last_row = self._condition_rows[neighbor][-1]
            _, statement_var = last_row

            # Parse the statement to match the format "#X: node=color"
            # We need to find a matching statement in the dropdown
            # For now, let's search through the recent arguments to find a match
            from comm.rb_protocol import parse_rb
            recent_args = self._rb_arguments.get(neighbor, [])

            # Find statement that matches "node=color"
            target_match = statement  # e.g., "h4=blue"
            for i, arg in enumerate(recent_args):
                # Check if this argument matches
                node = arg.get("node")
                colour = arg.get("colour")
                if node and colour:
                    stmt_text = f"{node}={colour}"
                    if stmt_text == target_match:
                        statement_var.set(f"#{i}: {stmt_text}")
                        print(f"[Counter] Set condition to #{i}: {stmt_text}")
                        return

            # If no match found, just set it directly (may not work with dropdown validation)
            print(f"[Counter] Could not find matching statement for {statement}, setting placeholder")
            statement_var.set(f"(select statement)")

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

        # Try to load a saved layout for this preset
        if self._graph_preset:
            from pathlib import Path as _Path
            layout_file = _Path(__file__).parent / "node_layouts.json"
            if layout_file.exists():
                try:
                    import json as _json
                    with open(layout_file) as _f:
                        all_layouts = _json.load(_f)
                    if self._graph_preset in all_layouts:
                        saved = all_layouts[self._graph_preset]
                        visible = set(self._nodes)
                        # Use v[0]/v[1] indexing — avoids unpacking crash when
                        # "__overlays__" value is a dict rather than a [fx, fy] list
                        loaded = {
                            n: (int(v[0] * w), int(v[1] * h))
                            for n, v in saved.items()
                            if n in visible and isinstance(v, list)
                        }
                        if all(n in loaded for n in self._nodes):
                            self._node_pos.update(loaded)
                            # Also load saved overlay positions if present
                            if "__overlays__" in saved:
                                self._overlay_positions = {
                                    n: (int(v[0] * w), int(v[1] * h))
                                    for n, v in saved["__overlays__"].items()
                                    if isinstance(v, list)
                                }
                            return
                except Exception:
                    pass  # fall through to algorithmic layout

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
        self._label_text_items.clear()
        self._timer_text_items.clear()

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
            if is_owned and n in self._node_cooldowns:
                remaining = self._node_cooldowns[n] - time.time()
                if remaining > 0:
                    lbl = canvas.create_text(x, y - 6, text=f"{n}", font=("TkDefaultFont", 10 if is_owned else 9))
                    self._label_text_items[n] = lbl
                    tmr = canvas.create_text(x, y + 8, text=f"\u23f1{math.ceil(remaining)}s",
                                             font=("TkDefaultFont", 8), fill="#cc6600")
                    self._timer_text_items[n] = tmr
                else:
                    lbl = canvas.create_text(x, y, text=f"{n}", font=("TkDefaultFont", 10 if is_owned else 9))
                    self._label_text_items[n] = lbl
            else:
                lbl = canvas.create_text(x, y, text=f"{n}", font=("TkDefaultFont", 10 if is_owned else 9))
                self._label_text_items[n] = lbl


    def _redraw_graph(self) -> None:
        """Redraw graph with zoom and pan transformations applied."""
        canvas = self._canvas
        if canvas is None:
            return
        canvas.delete("all")
        self._edge_items.clear()
        self._node_items.clear()
        self._label_text_items.clear()
        self._timer_text_items.clear()

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
            if is_owned and n in self._node_cooldowns:
                remaining = self._node_cooldowns[n] - time.time()
                if remaining > 0:
                    lbl = canvas.create_text(tx, ty - int(6 * scale), text=f"{n}", font=("TkDefaultFont", font_size))
                    self._label_text_items[n] = lbl
                    timer_fs = max(5, int(8 * scale))
                    tmr = canvas.create_text(tx, ty + int(8 * scale), text=f"\u23f1{math.ceil(remaining)}s",
                                             font=("TkDefaultFont", timer_fs), fill="#cc6600")
                    self._timer_text_items[n] = tmr
                else:
                    lbl = canvas.create_text(tx, ty, text=f"{n}", font=("TkDefaultFont", font_size))
                    self._label_text_items[n] = lbl
            else:
                lbl = canvas.create_text(tx, ty, text=f"{n}", font=("TkDefaultFont", font_size))
                self._label_text_items[n] = lbl

            # Visual indicators for committed (soft-locked) nodes
            if hasattr(self, '_committed_nodes') and n in self._committed_nodes:
                # Gold ring around committed nodes (thicker than fixed, solid)
                ring_offset = int(2 * scale)
                canvas.create_oval(tx - r - ring_offset, ty - r - ring_offset,
                                 tx + r + ring_offset, ty + r + ring_offset,
                                 outline="#FFD700", width=max(1, int(3 * scale)), fill="")
                # Small lock icon (different from fixed - smaller and in corner)
                lock_font_size = max(5, int(8 * scale))
                canvas.create_text(tx + r - int(5 * scale), ty - r + int(5 * scale),
                                 text="🔒", font=("TkDefaultFont", lock_font_size))

            # Domain arc ring — only on human-owned nodes in complex constraint modes.
            if is_owned and getattr(self, '_complex_constraints', False):
                self._draw_domain_arcs(canvas, tx, ty, r, n, scale)

        # Constraint viz overlays drawn on top of graph
        if getattr(self, '_constraint_viz_mode', False):
            self._draw_constraint_overlays()

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

        # In complex-constraints mode, "fixed" nodes are domain-restricted (e.g. only
        # one colour allowed). Allow clicking so the picker shows the single option;
        # the colour picker itself enforces the restriction via _node_domains.
        # In simple modes, truly fixed nodes remain unclickable.
        if hasattr(self, '_fixed_nodes') and best in self._fixed_nodes:
            if not getattr(self, '_complex_constraints', False):
                return

        r = 24
        if best_d > (r * r):
            return

        # Check cooldown before allowing colour change (not used in constraint viz mode)
        if not getattr(self, '_constraint_viz_mode', False):
            if best in self._node_cooldowns and time.time() < self._node_cooldowns[best]:
                return

        # Compute node canvas position for popup placement
        nx, ny = self._node_pos[best]
        node_canvas_x = int(nx * self._graph_canvas_scale + self._graph_canvas_offset[0])
        node_canvas_y = int(ny * self._graph_canvas_scale + self._graph_canvas_offset[1])
        self._show_colour_picker(best, node_canvas_x, node_canvas_y)

    def _on_canvas_right_click(self, ev: tk.Event) -> None:
        """Right-click on a human-owned node resets it to grey (unassigned)."""
        if not getattr(self, '_constraint_viz_mode', False):
            return

        offset_x, offset_y = self._graph_canvas_offset
        scale = self._graph_canvas_scale
        graph_x = (ev.x - offset_x) / scale
        graph_y = (ev.y - offset_y) / scale

        best = None
        best_d = 10**9
        for n, (nx, ny) in self._node_pos.items():
            d = (nx - graph_x) ** 2 + (ny - graph_y) ** 2
            if d < best_d:
                best_d = d
                best = n
        if best is None or self._owners.get(best) != "Human":
            return
        if hasattr(self, '_fixed_nodes') and best in self._fixed_nodes:
            return
        r = 24
        if best_d > (r * r):
            return

        # Check cooldown (not used in constraint viz mode)
        if not getattr(self, '_constraint_viz_mode', False):
            if best in self._node_cooldowns and time.time() < self._node_cooldowns[best]:
                return

        # Reset to unassigned
        if self._assignments.get(best) is None:
            return  # already grey, nothing to do
        self._assignments[best] = None
        self._move_count += 1
        self._refresh_move_counter()
        if self._on_colour_change:
            try:
                self._on_colour_change(dict(self._assignments))
            except Exception:
                pass
        self._redraw_graph()
        if self._hud_var:
            self._hud_var.set(self._hud_text())

        # Constraint viz mode: mark pending changes (updates happen on Submit, not live)
        if getattr(self, '_constraint_viz_mode', False):
            self._has_pending_changes = True
            self._refresh_submit_button()

    def _cycle_colour(self, node: str) -> None:
        # In constraint viz mode, cycle includes None (grey/unassigned) as first step.
        # In legacy mode, cycle skips None.
        if getattr(self, '_constraint_viz_mode', False):
            cycle = [None] + list(self._domain)
        else:
            cycle = list(self._domain)
        if not cycle:
            return
        current = self._assignments.get(node)
        try:
            idx = cycle.index(current)
        except ValueError:
            idx = -1  # will wrap to 0
        self._assignments[node] = cycle[(idx + 1) % len(cycle)]

    # -------------------- Colour picker & cooldown --------------------

    def _apply_colour_change(self, node: str, colour: Any) -> None:
        """Assign colour to node, start cooldown, fire all downstream callbacks."""
        # No-op if the colour hasn't changed — re-selecting the same colour
        # should not count as a move or trigger a cooldown.
        current = self._assignments.get(node)
        if current is not None and str(current).lower() == str(colour).lower():
            return
        self._assignments[node] = colour
        self._move_count += 1
        self._refresh_move_counter()

        # Start cooldown (skipped in constraint viz mode)
        if not getattr(self, '_constraint_viz_mode', False):
            self._node_cooldowns[node] = time.time() + self._cooldown_seconds
            if not self._cooldown_ticker_active and self._root:
                self._cooldown_ticker_active = True
                self._root.after(1000, self._tick_cooldowns)

        if self._on_colour_change:
            try:
                self._on_colour_change(dict(self._assignments))
            except Exception:
                pass
        self._redraw_graph()
        if self._hud_var:
            self._hud_var.set(self._hud_text())
        self._update_finish_button()

        # Constraint viz mode: mark pending changes (updates happen on Submit, not live)
        if getattr(self, '_constraint_viz_mode', False):
            self._has_pending_changes = True
            self._refresh_submit_button()

    def _show_colour_picker(self, node: str, canvas_x: int, canvas_y: int) -> None:
        """Show a colour-picker popup above the clicked node."""
        # Close any existing popup first
        if self._colour_popup is not None:
            try:
                if self._colour_popup.winfo_exists():
                    self._colour_popup.destroy()
            except Exception:
                pass
            self._colour_popup = None

        popup = tk.Toplevel(self._root)
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)

        # Build colour options — restrict to node's allowed domain if complex constraints active
        _allowed = self._node_domains.get(node, self._domain) if hasattr(self, '_node_domains') else self._domain
        _allowed_set = set(str(c).lower() for c in _allowed)
        if getattr(self, '_constraint_viz_mode', False):
            options: List[Any] = [None] + [c for c in self._domain if str(c).lower() in _allowed_set]
        else:
            options = [c for c in self._domain if str(c).lower() in _allowed_set]

        # Colour maps
        _FILL = {"red": "#ffcccc", "green": "#ccffcc", "blue": "#ccccff"}
        _OUTLINE = {"red": "#cc4444", "green": "#44aa44", "blue": "#4444cc"}

        outer = tk.Frame(popup, bg="#2d2d2d", bd=2, relief="solid")
        outer.pack(padx=1, pady=1)

        tk.Label(outer, text=f"Set colour for  {node}",
                 bg="#2d2d2d", fg="#eeeeee",
                 font=("TkDefaultFont", 9, "bold")).pack(pady=(5, 3), padx=8)

        swatch_row = tk.Frame(outer, bg="#2d2d2d")
        swatch_row.pack(padx=6, pady=(0, 6))

        def _pick(colour: Any) -> None:
            self._colour_popup = None
            try:
                popup.destroy()
            except Exception:
                pass
            self._apply_colour_change(node, colour)

        for colour in options:
            s = str(colour).lower() if colour is not None else ""
            fill = _FILL.get(s, "#dddddd") if colour is not None else "#dddddd"
            outline = _OUTLINE.get(s, "#999999") if colour is not None else "#999999"
            label = (str(colour)[:1].upper() if colour is not None else "—")

            c = tk.Canvas(swatch_row, width=38, height=38, bg="#2d2d2d",
                          highlightthickness=0, cursor="hand2")
            c.pack(side="left", padx=3)
            c.create_oval(3, 3, 35, 35, fill=fill, outline=outline, width=2)
            c.create_text(19, 19, text=label, font=("TkDefaultFont", 10, "bold"), fill="#333333")
            c.bind("<Button-1>", lambda _e, col=colour: _pick(col))

        # Position popup above the node on screen
        canvas_widget = self._canvas
        if canvas_widget is None:
            popup.destroy()
            return
        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        root_x = canvas_widget.winfo_rootx() + canvas_x
        root_y = canvas_widget.winfo_rooty() + canvas_y

        r_px = int(24 * self._graph_canvas_scale)
        px = root_x - pw // 2
        py = root_y - r_px - ph - 8  # 8 px gap above node

        # Keep on screen
        sw = popup.winfo_screenwidth()
        px = max(0, min(px, sw - pw))
        py = max(0, py)

        popup.geometry(f"+{px}+{py}")

        def _close_popup(_e: Any = None) -> None:
            if self._colour_popup is popup:
                self._colour_popup = None
            try:
                popup.destroy()
            except Exception:
                pass

        popup.bind("<FocusOut>", _close_popup)
        popup.bind("<Escape>", _close_popup)
        popup.focus_set()
        self._colour_popup = popup

    def _tick_cooldowns(self) -> None:
        """1-second tick: update only timer text items in-place (no full redraw)."""
        if not self._root:
            self._cooldown_ticker_active = False
            return
        canvas = self._canvas
        if canvas is None:
            self._cooldown_ticker_active = False
            return

        now = time.time()
        scale = self._graph_canvas_scale
        offset_x, offset_y = self._graph_canvas_offset

        # Expire cooldowns and remove their timer items from the canvas
        expired = [n for n, exp in list(self._node_cooldowns.items()) if exp <= now]
        for n in expired:
            del self._node_cooldowns[n]
            # Remove timer text item
            tid = self._timer_text_items.pop(n, None)
            if tid is not None:
                try:
                    canvas.delete(tid)
                except Exception:
                    pass
            # Move node label back to vertical centre
            lid = self._label_text_items.get(n)
            if lid is not None and n in self._node_pos:
                nx, ny = self._node_pos[n]
                tx = nx * scale + offset_x
                ty = ny * scale + offset_y
                try:
                    canvas.coords(lid, tx, ty)
                except Exception:
                    pass

        # Update still-active timer texts
        for n, exp in self._node_cooldowns.items():
            remaining = exp - now
            secs = math.ceil(remaining)
            tid = self._timer_text_items.get(n)
            if tid is not None:
                try:
                    canvas.itemconfigure(tid, text=f"\u23f1{secs}s")
                except Exception:
                    pass

        if self._node_cooldowns:
            self._root.after(1000, self._tick_cooldowns)
        else:
            self._cooldown_ticker_active = False

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

        # Configure loading tag on first use
        try:
            widget.tag_configure("loading", foreground="#888888")
        except Exception:
            pass

        # Standard text transcript (canvas mode removed)
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for ln in self._transcripts.get(neigh, []):
            if ln.startswith("__LOADING__"):
                widget.insert("end", ln[len("__LOADING__"):] + "\n", "loading")
            else:
                widget.insert("end", ln + "\n")
        widget.configure(state="disabled")
        widget.see("end")

    def _start_transcript_loading(self, neigh: str) -> None:
        """Add an animated loading placeholder to the transcript immediately."""
        self._remove_loading_placeholder(neigh)
        self._transcripts.setdefault(neigh, []).append(f"__LOADING__[{neigh}] ·")
        self._loading_transcripts[neigh] = True
        self._loading_dots_frame[neigh] = 0
        if self._root is not None:
            self._root.after(0, lambda n=neigh: self._refresh_transcript(n))
            self._root.after(400, lambda n=neigh: self._animate_transcript_loading(n))

    def _animate_transcript_loading(self, neigh: str) -> None:
        """Cycle the loading dots in the transcript placeholder."""
        if not self._loading_transcripts.get(neigh, False):
            return
        transcripts = self._transcripts.get(neigh, [])
        for i in range(len(transcripts) - 1, -1, -1):
            if transcripts[i].startswith("__LOADING__"):
                frame = (self._loading_dots_frame.get(neigh, 0) + 1) % 3
                self._loading_dots_frame[neigh] = frame
                dots = "·" * (frame + 1)
                transcripts[i] = f"__LOADING__[{neigh}] {dots}"
                if self._root is not None:
                    self._root.after(0, lambda n=neigh: self._refresh_transcript(n))
                    self._root.after(400, lambda n=neigh: self._animate_transcript_loading(n))
                break

    def _stop_transcript_loading(self, neigh: str) -> None:
        """Remove the loading placeholder; call before showing the real reply."""
        self._loading_transcripts[neigh] = False
        self._remove_loading_placeholder(neigh)

    def _remove_loading_placeholder(self, neigh: str) -> None:
        """Remove any __LOADING__ entry from the transcript list (no redraw)."""
        transcripts = self._transcripts.get(neigh, [])
        for i in range(len(transcripts) - 1, -1, -1):
            if transcripts[i].startswith("__LOADING__"):
                transcripts.pop(i)
                break

    def _parse_and_store_rb_move(self, neigh: str, line: str) -> None:
        """Parse an RB move from transcript line and store it in the argument structure."""
        import re
        import json

        print(f"[RB UI] Parsing line: {line[:120]}")

        # Extract sender from line format: "[You -> Agent1] Propose h1=red" or "[Agent1] Propose a2=blue"
        sender = "You"
        if line.startswith("[You"):
            sender = "You"
        elif line.startswith("["):
            match = re.match(r'\[([^\]]+)\]', line)
            if match:
                full_sender = match.group(1)
                # Strip arrow recipient if present: "Agent1 -> Human" -> "Agent1"
                if '->' in full_sender:
                    sender = full_sender.split('->')[0].strip()
                else:
                    sender = full_sender.strip()
                print(f"[RB UI Parse] Extracted sender: '{sender}' from bracket content: '{full_sender}'")
        else:
            print(f"[RB UI Parse] Extracted sender: '{sender}' from line starting with: {line[:50]}")

        # Try to extract from RB protocol tag first: [rb:{"move":"Propose","node":"h1","colour":"red","reasons":[]}]
        # Use parse_rb() which has proper brace-counting logic for nested JSON
        try:
            from comm.rb_protocol import parse_rb
            rb_move = parse_rb(line)
            if rb_move:
                rb_data = {
                    "move": rb_move.move,
                    "node": rb_move.node,
                    "colour": rb_move.colour,
                    "reasons": rb_move.reasons,
                    "conditions": [{"node": c.node, "colour": c.colour, "owner": c.owner} for c in (rb_move.conditions or [])],
                    "assignments": [{"node": a.node, "colour": a.colour} for a in (rb_move.assignments or [])],
                    "offer_id": rb_move.offer_id,
                    "refers_to": rb_move.refers_to
                }
                move_type = rb_data.get("move", "")

                # Handle ConditionalOffer specially (has conditions/assignments, not single node/color)
                if move_type == "ConditionalOffer":
                    print(f"[RB UI] Processing ConditionalOffer from {sender}")
                    conditions = rb_data.get("conditions", [])
                    assignments = rb_data.get("assignments", [])
                    offer_id = rb_data.get("offer_id", "")
                    print(f"[RB UI] ConditionalOffer details: conditions={len(conditions)}, assignments={len(assignments)}, offer_id={offer_id}")

                    # Track when agent sent an offer (for auto-suggest slow-down)
                    if offer_id and "offer_" in offer_id:
                        import time
                        self._last_agent_offer_time[neigh] = time.time()
                        print(f"[RB UI] Tracked agent offer time for {neigh}")

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
                # Show summary: "If X conds -> Y assigns"
                text = f"IF: {len(conditions)} conds\n-> THEN: {len(assignments)} assigns"
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
        # Use the new status system with spinner animation
        if status:
            self.update_agent_status(neigh, status)
        else:
            self.clear_agent_status(neigh)

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
        self._write_ui_debug(f"[UI _flush_incoming] Called for {neigh}: {len(q)} messages")
        if q:
            self._stop_transcript_loading(neigh)
        while q:
            msg = q.pop(0)
            print(f"[UI] Processing message: {msg[:200]}")
            self._write_ui_debug(f"[UI _flush_incoming] Processing message: {msg[:200]}")

            # Check for FeasibilityResponse in RB/LLM_RB modes (both use RB protocol)
            if getattr(self, '_rb_structured_mode', False) or getattr(self, '_llm_rb_mode', False):
                self._write_ui_debug(f"[UI _flush_incoming] In RB mode, checking for FeasibilityResponse")
                try:
                    from comm.rb_protocol import parse_rb
                    rb_move = parse_rb(msg)
                    self._write_ui_debug(f"[UI _flush_incoming] Parsed RB move: {rb_move.move if rb_move else 'None'}")
                    if rb_move and rb_move.move == "FeasibilityResponse":
                        self._write_ui_debug(f"[UI _flush_incoming] ✓ FeasibilityResponse detected!")
                        refers_to = rb_move.refers_to if hasattr(rb_move, 'refers_to') else None
                        self._write_ui_debug(f"[UI _flush_incoming] refers_to: {refers_to}")
                        self._write_ui_debug(f"[UI _flush_incoming] neigh in queries: {neigh in self._feasibility_queries}")
                        if neigh in self._feasibility_queries:
                            self._write_ui_debug(f"[UI _flush_incoming] Queries for {neigh}: {len(self._feasibility_queries[neigh])}")
                        if refers_to and neigh in self._feasibility_queries:
                            for i, query in enumerate(self._feasibility_queries[neigh]):
                                self._write_ui_debug(f"[UI _flush_incoming] Checking query {i}: {query.get('query_id')}")
                                if query['query_id'] == refers_to:
                                    self._write_ui_debug(f"[UI _flush_incoming] ✓ MATCH! Updating query {refers_to}")
                                    query['is_feasible'] = rb_move.is_feasible if hasattr(rb_move, 'is_feasible') else None
                                    query['feasibility_penalty'] = rb_move.feasibility_penalty if hasattr(rb_move, 'feasibility_penalty') else None
                                    query['feasibility_details'] = rb_move.feasibility_details if hasattr(rb_move, 'feasibility_details') else None
                                    query['required_assignments'] = rb_move.required_assignments if hasattr(rb_move, 'required_assignments') else None
                                    self._write_ui_debug(f"[UI _flush_incoming] Updated query: is_feasible={query['is_feasible']}, penalty={query['feasibility_penalty']}, details={query['feasibility_details']}, required={query['required_assignments']}")
                                    self._write_ui_debug(f"[UI _flush_incoming] Calling _render_conditional_cards()")
                                    self._render_conditional_cards()
                                    break
                        else:
                            self._write_ui_debug(f"[UI _flush_incoming] No match: refers_to={refers_to}, neigh_in_queries={neigh in self._feasibility_queries}")

                    # Track Accept/Reject responses for human's sent offers
                    if rb_move:
                        if rb_move.move == "Accept" and hasattr(rb_move, 'refers_to'):
                            # Agent accepted an offer
                            refers_to = rb_move.refers_to
                            if refers_to:
                                for offer in self._human_sent_offers:
                                    if offer.get("offer_id") == refers_to:
                                        offer["status"] = "accepted"
                                        self._pending_human_offers.discard(refers_to)
                                        print(f"[Offer Tracking] Offer {refers_to} accepted - removed from pending")
                                        break

                        elif rb_move.move == "Reject" and hasattr(rb_move, 'refers_to'):
                            # Agent rejected an offer
                            refers_to = rb_move.refers_to
                            if refers_to:
                                for offer in self._human_sent_offers:
                                    if offer.get("offer_id") == refers_to:
                                        offer["status"] = "rejected"
                                        self._pending_human_offers.discard(refers_to)
                                        print(f"[Offer Tracking] Offer {refers_to} rejected - removed from pending")
                                        break
                except Exception as e:
                    print(f"[UI] Error processing FeasibilityResponse: {e}")

            clean, report = self._extract_and_apply_reports(msg)
            print(f"[UI] After extract_and_apply_reports: clean={clean[:200]}, report={report}")

            # Skip displaying silent messages (e.g., initial config announcements)
            # These update UI colors via report tag but don't appear in chat
            if not clean.startswith("__SILENT__"):
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
        self._start_transcript_loading(neigh)

        def worker():
            reply = None
            try:
                if self._on_send:
                    reply = self._invoke_on_send(neigh, msg)
            except Exception as e:
                reply = f"[System] Error sending: {e}"
            finally:
                # Clear status after agent responds (or on error)
                self.clear_agent_status(neigh)

            if reply:
                self.add_incoming(neigh, reply)
            else:
                # No reply - remove loading placeholder anyway
                if self._root is not None:
                    self._root.after(0, lambda n=neigh: self._stop_transcript_loading(n))

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
        self._start_transcript_loading(neigh)

        def worker():
            reply = None
            try:
                if self._on_send:
                    # Send message with current assignments
                    reply = self._invoke_on_send(neigh, msg)
            except Exception as e:
                reply = f"[System] Error sending: {e}"
            finally:
                # Clear status after agent responds (or on error)
                self.clear_agent_status(neigh)

            if reply:
                self.add_incoming(neigh, reply)
            else:
                if self._root is not None:
                    self._root.after(0, lambda n=neigh: self._stop_transcript_loading(n))

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
        # In all modes with announcement phase, agents shouldn't auto-announce at startup
        # The human announces first by clicking "Announce Configuration" button
        has_announcement = (hasattr(self, '_has_announcement_phase') and self._has_announcement_phase) or \
                          (hasattr(self, '_rb_structured_mode') and self._rb_structured_mode) or \
                          (hasattr(self, '_llm_rb_mode') and self._llm_rb_mode)
        if has_announcement:
            # Don't start agents automatically in modes with announcement phase
            return

        self._set_status(neigh, "waiting for reply…")
        self._start_transcript_loading(neigh)

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
                    self._root.after(0, lambda n=neigh: self._stop_transcript_loading(n))
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
        if self._submission_cb is not None:
            try:
                sat_val = bool(self._human_sat[neigh].get())
                self._submission_cb(
                    neigh,
                    sat_val,
                    dict(getattr(self, "_assignments", {})),
                )
            except Exception:
                pass
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
        # Removed verbose logging - only log when convergence achieved
        # print(f"[RB Convergence] Checking commitment for {len(self._neighs)} neighbors")

        if not hasattr(self, '_human_sat'):
            # print(f"[RB Convergence] No _human_sat attribute")
            return False

        # Check all neighbors
        for neigh in self._neighs:
            # Check human satisfaction checkbox
            try:
                human_satisfied = bool(self._human_sat[neigh].get())
                # print(f"[RB Convergence] Human satisfied with {neigh}: {human_satisfied}")
            except Exception as e:
                human_satisfied = False
                print(f"[RB Convergence] Error checking human satisfaction for {neigh}: {e}")

            if not human_satisfied:
                # print(f"[RB Convergence] Human not satisfied with {neigh} - not ready")
                return False

            # Check agent satisfaction
            if self._get_agent_satisfied_fn:
                try:
                    agent_satisfied = bool(self._get_agent_satisfied_fn(neigh))
                    # print(f"[RB Convergence] {neigh} satisfied: {agent_satisfied}")
                except Exception as e:
                    agent_satisfied = False
                    print(f"[RB Convergence] Error checking {neigh} satisfaction: {e}")

                if not agent_satisfied:
                    # print(f"[RB Convergence] {neigh} not satisfied - not ready")
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

        # Create LLM trace viewer with scrollbar
        llm_trace_frame = ttk.Frame(nb)
        llm_scrollbar = ttk.Scrollbar(llm_trace_frame, orient="vertical")
        txt_llm_trace = tk.Text(llm_trace_frame, wrap="word", yscrollcommand=llm_scrollbar.set)
        llm_scrollbar.config(command=txt_llm_trace.yview)
        llm_scrollbar.pack(side="right", fill="y")
        txt_llm_trace.pack(side="left", fill="both", expand=True)

        nb.add(txt_summary, text="Summary")
        nb.add(txt_state, text="State")
        nb.add(global_graph_canvas, text="Global Graph")
        nb.add(llm_trace_frame, text="LLM Traces")

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

            # Collect all nodes from all agents (and human)
            all_agents_nodes = set()
            all_agents_edges = set()
            all_assignments = {}
            all_fixed_nodes = set()

            for agent_name, agent_obj in name_to_obj.items():
                if agent_obj is None:
                    # "Human" entry: use UI's current assignments
                    human_assigns = {k: v for k, v in self._assignments.items()
                                     if v is not None}
                    all_assignments.update(human_assigns)
                    human_ns = [n for n, o in self._owners.items() if o == "Human"]
                    all_agents_nodes.update(human_ns)
                    # Edges from adjacency if available
                    if hasattr(self, '_edges'):
                        for u, v in self._edges:
                            if u in human_ns or v in human_ns:
                                all_agents_edges.add(tuple(sorted([u, v])))
                    # Fixed human nodes
                    if hasattr(self, '_fixed_nodes'):
                        all_fixed_nodes.update(self._fixed_nodes.keys())
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
            nodes_by_owner: Dict[str, List[str]] = {}
            # Always include Human
            human_ns = sorted([n for n, o in self._owners.items() if o == "Human"])
            if human_ns:
                nodes_by_owner["Human"] = human_ns
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

            # Render LLM traces
            self._render_llm_traces(txt_llm_trace, obj, name)

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
        """Render complete global graph on canvas with all clusters visible using clustered layout."""
        canvas.delete("all")

        # Get canvas dimensions
        canvas.update_idletasks()
        w = max(canvas.winfo_width(), 600)
        h = max(canvas.winfo_height(), 500)

        cluster_names = sorted(nodes_by_owner.keys())
        num_clusters = len(cluster_names)

        if num_clusters == 0:
            canvas.create_text(w / 2, h / 2, text="No agents available", font=("Arial", 14))
            return

        # Calculate cluster positions (triangular layout like H2O molecule)
        cluster_centers = {}
        padding = 100  # Space from edges

        if num_clusters == 1:
            # Single cluster: center
            cluster_centers[cluster_names[0]] = (w / 2, h / 2)
        elif num_clusters == 2:
            # Two clusters: side by side with vertical offset
            cluster_centers[cluster_names[0]] = (w / 3, h / 2)
            cluster_centers[cluster_names[1]] = (2 * w / 3, h / 2)
        elif num_clusters == 3:
            # Three clusters: triangular arrangement (like H2O molecule)
            # Find Human cluster and put it at bottom center
            human_idx = next((i for i, name in enumerate(cluster_names) if name == "Human"), 1)
            other_indices = [i for i in range(3) if i != human_idx]

            # Human at bottom center
            cluster_centers[cluster_names[human_idx]] = (w / 2, 2 * h / 3 + 20)
            # Other two agents at top left and top right
            cluster_centers[cluster_names[other_indices[0]]] = (w / 3, h / 3 - 20)
            cluster_centers[cluster_names[other_indices[1]]] = (2 * w / 3, h / 3 - 20)
        else:
            # Four or more clusters: fall back to grid layout
            cols = 2 if num_clusters <= 4 else 3
            rows = (num_clusters + cols - 1) // cols
            cell_w = (w - 2 * padding) / cols
            cell_h = (h - 2 * padding) / rows
            for idx, cluster_name in enumerate(cluster_names):
                row = idx // cols
                col = idx % cols
                cx = padding + (col + 0.5) * cell_w
                cy = padding + (row + 0.5) * cell_h
                cluster_centers[cluster_name] = (cx, cy)

        # Position nodes within each cluster using circular layout
        node_positions = {}
        for cluster_idx, cluster_name in enumerate(cluster_names):
            cluster_nodes = sorted(nodes_by_owner[cluster_name])
            num_nodes = len(cluster_nodes)

            if num_nodes == 0:
                continue

            cx, cy = cluster_centers[cluster_name]

            # Adjust cluster radius based on number of nodes
            # Use smaller of width/height for base sizing
            base_radius = min(w / 8, h / 6, 70)  # Reasonable default for triangular layout
            cluster_radius = max(base_radius, base_radius * (num_nodes / 5) ** 0.5)

            # Position nodes in circle within cluster
            if num_nodes == 1:
                # Single node at center
                node_positions[cluster_nodes[0]] = (int(cx), int(cy))
            else:
                # Multiple nodes in circle
                for i, node in enumerate(cluster_nodes):
                    angle = (2.0 * math.pi * i) / float(num_nodes)
                    x = cx + cluster_radius * math.cos(angle)
                    y = cy + cluster_radius * math.sin(angle)
                    node_positions[node] = (int(x), int(y))

        # Draw cluster boundaries (light background circles)
        for cluster_name in cluster_names:
            cluster_nodes = sorted(nodes_by_owner[cluster_name])
            if not cluster_nodes:
                continue

            cx, cy = cluster_centers[cluster_name]
            num_nodes = len(cluster_nodes)

            # Calculate boundary radius (slightly larger than node positions)
            base_radius = min(w / 8, h / 6, 70)  # Same as node positioning
            cluster_radius = max(base_radius, base_radius * (num_nodes / 5) ** 0.5)
            boundary_radius = cluster_radius + 35  # Add padding for boundary

            # Draw boundary circle with cluster label
            canvas.create_oval(
                cx - boundary_radius, cy - boundary_radius,
                cx + boundary_radius, cy + boundary_radius,
                outline="#cccccc", width=2, dash=(5, 3), tags="cluster_boundary"
            )

            # Draw cluster label at top
            canvas.create_text(
                cx, cy - boundary_radius - 15,
                text=cluster_name,
                font=("Arial", 12, "bold"),
                fill="#666666",
                tags="cluster_label"
            )

        # Draw edges (so they're behind nodes)
        for edge in all_edges:
            if isinstance(edge, tuple) and len(edge) >= 2:
                u, v = edge[0], edge[1]
            else:
                continue

            if u not in node_positions or v not in node_positions:
                continue

            x1, y1 = node_positions[u]
            x2, y2 = node_positions[v]

            # Determine if cross-cluster edge
            u_owner = None
            v_owner = None
            for owner, nodes in nodes_by_owner.items():
                if u in nodes:
                    u_owner = owner
                if v in nodes:
                    v_owner = owner

            is_cross_cluster = (u_owner != v_owner)

            # Check for conflict (same color on adjacent nodes)
            u_color = all_assignments.get(u)
            v_color = all_assignments.get(v)

            if u_color and v_color and str(u_color).lower() == str(v_color).lower():
                # CONFLICT - thick red line
                canvas.create_line(x1, y1, x2, y2, fill="#dd0000", width=3, tags="edge")
            elif is_cross_cluster:
                # Cross-cluster edge - thicker blue line
                canvas.create_line(x1, y1, x2, y2, fill="#4682B4", width=2, tags="edge")
            else:
                # Intra-cluster edge - thin gray line
                canvas.create_line(x1, y1, x2, y2, fill="#CCCCCC", width=1, tags="edge")

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

            # Domain constraint arcs (only for nodes with restricted domains)
            if self._node_domains and node in self._node_domains:
                self._draw_domain_arcs(canvas, x, y, radius, node, 1.0)

            # Node label
            canvas.create_text(
                x, y,
                text=str(node),
                font=("Arial", 10, "bold"),
                tags="label"
            )

        # Add legend explaining visual encoding
        legend_x = 10
        legend_y = h - 80
        legend_items = [
            ("━━", "#dd0000", "Conflict (same color)", 3),
            ("━━", "#4682B4", "Cross-cluster edge", 2),
            ("━━", "#CCCCCC", "Intra-cluster edge", 1),
        ]

        # Domain arc legend (only shown when there are constrained nodes)
        if self._node_domains:
            canvas.create_text(
                legend_x, legend_y + len(legend_items) * 20 + 8,
                text="Coloured ring = domain constraint (arc per allowed colour)",
                anchor="w",
                font=("Arial", 9),
                fill="#555555",
                tags="legend"
            )

        canvas.create_text(
            legend_x, legend_y - 15,
            text="Legend:",
            anchor="w",
            font=("Arial", 10, "bold"),
            tags="legend"
        )

        for i, (symbol, color, label, width) in enumerate(legend_items):
            y_pos = legend_y + (i * 20)
            # Draw sample line
            canvas.create_line(
                legend_x + 5, y_pos,
                legend_x + 25, y_pos,
                fill=color, width=width, tags="legend"
            )
            # Draw label
            canvas.create_text(
                legend_x + 30, y_pos,
                text=label,
                anchor="w",
                font=("Arial", 9),
                tags="legend"
            )

    def _render_llm_traces(self, text_widget: tk.Text, agent_obj: Any, agent_name: str) -> None:
        """Render LLM reasoning traces for the selected agent."""
        text_widget.configure(state="normal")
        text_widget.delete("1.0", "end")

        # Check if this is an LLM agent
        is_llm_agent = False
        agent_type = ""

        if agent_obj and hasattr(agent_obj, '__class__'):
            class_name = agent_obj.__class__.__name__
            if 'ToolCalling' in class_name or 'LLM_TOOL' in str(agent_obj):
                is_llm_agent = True
                agent_type = "LLM_TOOL (Function Calling)"
            elif 'ReAct' in class_name or 'LLM_REACT' in str(agent_obj):
                is_llm_agent = True
                agent_type = "LLM_REACT (Reasoning Traces)"

        if not is_llm_agent:
            text_widget.insert("end", f"{agent_name} is not using an LLM backend.\n\n")
            text_widget.insert("end", "LLM traces are only available for:\n")
            text_widget.insert("end", "  - LLM_TOOL mode (function calling agents)\n")
            text_widget.insert("end", "  - LLM_REACT mode (ReAct reasoning agents)\n\n")
            text_widget.insert("end", "To see LLM reasoning, select an agent in LLM_TOOL or LLM_REACT mode.")
            text_widget.configure(state="disabled")
            return

        text_widget.insert("end", f"=== LLM Traces for {agent_name} ({agent_type}) ===\n\n", "header")

        # Try to read trace file from results directory
        trace_data = []
        trace_file = None
        trace_filename = "llm_trace.jsonl" if "LLM_TOOL" in agent_type or "Function" in agent_type else "react_trace.jsonl"

        # Look for trace files in multiple locations
        import glob
        search_paths = [
            f"results/*/{trace_filename}",  # In subdirectories
            f"results/{trace_filename}",     # In results root
            f"test_output/{trace_filename}", # In test output
            trace_filename,                  # In current directory
        ]

        text_widget.insert("end", f"Searching for {trace_filename}...\n\n")

        for pattern in search_paths:
            files = sorted(glob.glob(pattern), key=lambda x: os.path.getmtime(x), reverse=True)
            if files:
                trace_file = files[0]  # Use most recent
                text_widget.insert("end", f"Found: {trace_file}\n\n")
                break

        if not trace_file or not os.path.exists(trace_file):
            text_widget.insert("end", f"No trace file found.\n\n")
            text_widget.insert("end", f"Searched in:\n")
            for pattern in search_paths:
                text_widget.insert("end", f"  - {pattern}\n")
            text_widget.insert("end", "\nTrace files are generated during agent execution.\n")
            text_widget.insert("end", "Make sure you're running in LLM_TOOL or LLM_REACT mode.")
            text_widget.configure(state="disabled")
            return

        # Read and parse trace file
        all_entries = []
        agent_names_found = set()
        try:
            with open(trace_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            all_entries.append(entry)
                            # Track agent names we see
                            if 'agent' in entry:
                                agent_names_found.add(entry['agent'])
                            if 'name' in entry:
                                agent_names_found.add(entry['name'])
                            # Filter for this agent's traces (flexible matching)
                            entry_agent = entry.get('agent', '') or entry.get('name', '')
                            if entry_agent == agent_name or agent_name in entry_agent or entry_agent in agent_name:
                                trace_data.append(entry)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            text_widget.insert("end", f"Error reading trace file: {e}\n")
            text_widget.configure(state="disabled")
            return

        text_widget.insert("end", f"Total entries in file: {len(all_entries)}\n")
        text_widget.insert("end", f"Agent names found: {', '.join(sorted(agent_names_found)) or 'none'}\n")
        text_widget.insert("end", f"Matches for '{agent_name}': {len(trace_data)}\n\n")

        if not trace_data:
            text_widget.insert("end", f"No traces found for agent '{agent_name}'.\n\n")
            if all_entries:
                text_widget.insert("end", "Showing all traces instead:\n\n")
                trace_data = all_entries[-20:]  # Show last 20 entries
            else:
                text_widget.insert("end", "No traces in file.")
                text_widget.configure(state="disabled")
                return

        text_widget.insert("end", f"Found {len(trace_data)} trace entries\n\n", "count")
        text_widget.insert("end", "=" * 80 + "\n\n")

        # Render traces based on type
        for idx, entry in enumerate(trace_data[-20:], 1):  # Show last 20 traces
            text_widget.insert("end", f"[Trace #{idx}]\n", "trace_header")

            # Show timestamp if available
            if 'timestamp' in entry:
                text_widget.insert("end", f"Time: {entry['timestamp']}\n")

            # Show event type
            if 'event' in entry:
                text_widget.insert("end", f"Event: {entry['event']}\n", "event")

            # For tool calling agents: show function calls
            if 'function_name' in entry:
                text_widget.insert("end", f"\nFunction: {entry['function_name']}\n", "function")
                if 'arguments' in entry:
                    text_widget.insert("end", f"Arguments: {json.dumps(entry['arguments'], indent=2)}\n")
                if 'result' in entry:
                    text_widget.insert("end", f"Result: {json.dumps(entry['result'], indent=2)}\n")

            # For ReAct agents: show thought/action/observation
            if 'thought' in entry:
                text_widget.insert("end", f"\nThought: {entry['thought']}\n", "thought")
            if 'action' in entry:
                text_widget.insert("end", f"Action: {entry['action']}\n", "action")
            if 'observation' in entry:
                text_widget.insert("end", f"Observation: {entry['observation']}\n")

            # Show prompt/response if available
            if 'prompt' in entry:
                prompt_preview = entry['prompt'][:200] + "..." if len(entry['prompt']) > 200 else entry['prompt']
                text_widget.insert("end", f"\nPrompt (preview): {prompt_preview}\n", "prompt")
            if 'response' in entry:
                response_preview = entry['response'][:200] + "..." if len(entry['response']) > 200 else entry['response']
                text_widget.insert("end", f"Response (preview): {response_preview}\n", "response")

            text_widget.insert("end", "\n" + "-" * 80 + "\n\n")

        # Configure text tags for styling
        text_widget.tag_config("header", font=("Arial", 12, "bold"), foreground="#2c3e50")
        text_widget.tag_config("count", font=("Arial", 10, "bold"), foreground="#27ae60")
        text_widget.tag_config("trace_header", font=("Arial", 10, "bold"), foreground="#3498db")
        text_widget.tag_config("event", foreground="#e74c3c")
        text_widget.tag_config("function", font=("Courier", 10, "bold"), foreground="#9b59b6")
        text_widget.tag_config("thought", foreground="#f39c12")
        text_widget.tag_config("action", foreground="#16a085")
        text_widget.tag_config("prompt", foreground="#7f8c8d")
        text_widget.tag_config("response", foreground="#34495e")

        text_widget.configure(state="disabled")

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

        # Animate spinners for agents with active status
        for agent_name, status in list(self._agent_status.items()):
            if status and agent_name in self._status_var:
                # Update spinner animation
                spinner_frame = self._status_spinner_state.get(agent_name, 0)
                spinner_char = self._spinner_chars[spinner_frame % len(self._spinner_chars)]
                self._status_var[agent_name].set(f"{spinner_char} {status}")
                self._status_spinner_state[agent_name] = spinner_frame + 1

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
            if c is None:
                continue
            score += self._points.get(str(c).lower(), 0)
        return f"Score: {score}"

    def _moves_colour(self, count: int) -> str:
        """Return a hex colour on a green→yellow→red scale.

        Green at 0 moves, yellow at N moves, red at 2N moves,
        where N = number of human-owned nodes.
        """
        n_human = sum(1 for o in self._owners.values() if o == "Human") or 1
        t = min(count / max(2 * n_human, 1), 1.0)
        if t <= 0.5:
            s = t / 0.5
            r = int(0x22 + s * (0xf0 - 0x22))
            g = int(0xbb + s * (0xc0 - 0xbb))
            b = int(0x44 + s * (0x00 - 0x44))
        else:
            s = (t - 0.5) / 0.5
            r = int(0xf0 + s * (0xcc - 0xf0))
            g = int(0xc0 + s * (0x22 - 0xc0))
            b = int(0x00 + s * (0x22 - 0x00))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _refresh_move_counter(self) -> None:
        """Update the move counter label text and background colour."""
        if self._move_count_label is None or self._move_count_var is None:
            return
        self._move_count_var.set(f"Moves: {self._move_count}")
        self._move_count_label.configure(bg=self._moves_colour(self._move_count))

    # -------------------- Constraint Visualisation Methods --------------------

    def _build_constraint_panels(self, parent: tk.Frame) -> None:
        """Build constraint information panels (one per agent) for constraint viz mode."""
        # Store references for updates
        self._constraint_panel_frames: Dict[str, tk.Frame] = {}
        self._constraint_status_vars: Dict[str, tk.StringVar] = {}
        self._constraint_card_areas: Dict[str, tk.Canvas] = {}
        self._constraint_card_inner: Dict[str, tk.Frame] = {}
        self._constraint_data: Dict[str, Any] = {}

        root = self._root
        for neigh in self._neighs:
            label_frame = ttk.LabelFrame(parent, text=f"{neigh} — Constraint Info")
            label_frame.pack(fill="both", expand=True, pady=6, padx=4)

            # Status label (feasibility summary)
            status_var = tk.StringVar(master=root, value="Waiting for first colour change…")
            self._constraint_status_vars[neigh] = status_var
            self._status_var[neigh] = status_var  # reuse existing spinner infrastructure

            status_lbl = tk.Label(
                label_frame,
                textvariable=status_var,
                font=("Arial", 10, "italic"),
                fg="#555",
                anchor="w",
            )
            status_lbl.pack(fill="x", padx=6, pady=(4, 2))

            # Scrollable card area
            card_canvas = tk.Canvas(label_frame, highlightthickness=0)
            card_scrollbar = ttk.Scrollbar(label_frame, orient="vertical", command=card_canvas.yview)
            card_scrollbar.pack(side="right", fill="y")
            card_canvas.pack(side="left", fill="both", expand=True, padx=4, pady=4)
            card_canvas.configure(yscrollcommand=card_scrollbar.set)

            inner = tk.Frame(card_canvas, bg="white")
            win_id = card_canvas.create_window((0, 0), window=inner, anchor="nw")

            def _on_inner_configure(ev, c=card_canvas):
                c.configure(scrollregion=c.bbox("all"))
            inner.bind("<Configure>", _on_inner_configure)

            def _on_canvas_configure(ev, c=card_canvas, wid=win_id):
                c.itemconfig(wid, width=ev.width)
            card_canvas.bind("<Configure>", _on_canvas_configure)

            self._constraint_card_areas[neigh] = card_canvas
            self._constraint_card_inner[neigh] = inner
            self._constraint_panel_frames[neigh] = label_frame

    def _build_feasibility_sidebar(self, parent: ttk.Frame) -> None:
        """Build the right-hand panel: scrollable mini-subgraph configs per agent."""
        self._feasibility_canvas_areas = {}
        self._feasibility_count_vars = {}

        root = self._root
        title = tk.Label(
            parent,
            text="Valid Configurations",
            font=("Arial", 12, "bold"),
            anchor="w",
        )
        title.pack(fill="x", padx=8, pady=(8, 4))

        sep = ttk.Separator(parent, orient="horizontal")
        sep.pack(fill="x", padx=8, pady=4)

        for neigh in self._neighs:
            frame = ttk.LabelFrame(parent, text=neigh)
            frame.pack(fill="both", expand=True, padx=8, pady=6)

            count_var = tk.StringVar(master=root, value="Waiting…")
            self._feasibility_count_vars[neigh] = count_var
            count_lbl = tk.Label(
                frame,
                textvariable=count_var,
                font=("Arial", 9, "italic"),
                fg="#555",
                anchor="w",
            )
            count_lbl.pack(fill="x", padx=4, pady=(2, 0))

            # Scrollable area for mini-config canvases
            scroll_canvas = tk.Canvas(frame, highlightthickness=0, bg="white")
            scrollbar = ttk.Scrollbar(frame, orient="vertical", command=scroll_canvas.yview)
            scrollbar.pack(side="right", fill="y")
            scroll_canvas.pack(side="left", fill="both", expand=True)
            scroll_canvas.configure(yscrollcommand=scrollbar.set)

            inner = tk.Frame(scroll_canvas, bg="white")
            wid = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")

            def _on_inner_cfg(ev, c=scroll_canvas):
                c.configure(scrollregion=c.bbox("all"))
            inner.bind("<Configure>", _on_inner_cfg)

            def _on_canvas_cfg(ev, c=scroll_canvas, w=wid):
                c.itemconfig(w, width=ev.width)
            scroll_canvas.bind("<Configure>", _on_canvas_cfg)

            # Mouse-wheel scrolling
            def _on_mwheel(ev, c=scroll_canvas):
                c.yview_scroll(int(-1 * (ev.delta / 120)), "units")
            scroll_canvas.bind("<MouseWheel>", _on_mwheel)

            self._feasibility_canvas_areas[neigh] = (scroll_canvas, inner)

    def update_constraint_display(self, agent_name: str, data: Dict[str, Any]) -> None:
        """Public API: update constraint panels for one agent. Thread-safe via root.after."""
        if self._root is None:
            return
        self._constraint_data[agent_name] = data
        self._root.after(0, lambda: self._render_constraint_panel(agent_name))

    def update_human_domain_display(self, data: Dict[str, Any]) -> None:
        """Public API: update human-domain overlay (C5/C6). Thread-safe via root.after."""
        if self._root is None:
            return
        self._human_domain_data = data
        self._root.after(0, self._draw_constraint_overlays)

    def _check_finish_ready(self) -> bool:
        """Return True when the Finish button should be enabled."""
        # All human-owned nodes must be assigned
        human_nodes = [n for n in self._nodes if self._owners.get(n) == "Human"]
        if any(self._assignments.get(n) is None for n in human_nodes):
            return False
        # No internal clashes among human nodes
        human_set = set(human_nodes)
        for u, v in self._edges:
            if u in human_set and v in human_set:
                if (self._assignments.get(u) is not None
                        and self._assignments.get(u) == self._assignments.get(v)):
                    return False
        # All agents must have reported feasible configurations
        if not self._neighs:
            return True
        return all(self._agent_feasibility.get(n, False) for n in self._neighs)

    def _update_finish_button(self) -> None:
        """Enable or disable the Finish button based on current readiness."""
        btn = getattr(self, '_finish_btn', None)
        if btn is None:
            return
        try:
            btn.config(state="normal" if self._check_finish_ready() else "disabled")
        except Exception:
            pass

    def _render_constraint_panel(self, agent_name: str) -> None:
        """Redraw constraint cards for one agent panel. Must run on the Tk thread."""
        data = self._constraint_data.get(agent_name, {})

        # Update per-agent feasibility for Finish button gating
        feasibility_count = data.get("feasibility_count", 0)
        is_feasible = data.get("is_feasible", feasibility_count > 0)
        self._agent_feasibility[agent_name] = bool(is_feasible)
        self._update_finish_button()

        # Always update the right-hand mini-graph sidebar and canvas overlays
        self._render_feasibility_panel(agent_name, data)
        self._draw_constraint_overlays()

        inner = self._constraint_card_inner.get(agent_name)
        if inner is None:
            return  # No card panel (constraint viz mode uses overlays instead)

        # Clear existing cards
        for widget in inner.winfo_children():
            widget.destroy()

        feasibility_count = data.get("feasibility_count", 0)
        is_feasible = data.get("is_feasible", feasibility_count > 0)
        condition = getattr(self, '_condition', 'C1')

        # Update status label
        status_var = self._constraint_status_vars.get(agent_name)
        if status_var:
            if feasibility_count < 0:
                status_var.set(f"Error: {data.get('error', 'unknown')}")
            elif is_feasible:
                status_var.set(f"{feasibility_count} valid configuration(s)")
            else:
                status_var.set("INFEASIBLE — no valid configuration")

        # Infeasible card (all conditions)
        if not is_feasible:
            repair = data.get("repair_suggestion", [])
            card = tk.Frame(inner, bg="#ffcccc", relief=tk.RAISED, bd=1)
            card.pack(fill="x", padx=4, pady=4)
            tk.Label(
                card,
                text="No valid configuration exists!",
                font=("Arial", 10, "bold"),
                fg="#cc0000",
                bg="#ffcccc",
                anchor="w",
            ).pack(fill="x", padx=6, pady=(6, 2))
            if repair:
                tk.Label(
                    card,
                    text=f"Try unassigning: {', '.join(repair)}",
                    font=("Arial", 9),
                    fg="#880000",
                    bg="#ffcccc",
                    anchor="w",
                    wraplength=320,
                ).pack(fill="x", padx=6, pady=(0, 6))
            else:
                tk.Label(
                    card,
                    text="Internal conflict — cannot repair by unassigning boundary nodes.",
                    font=("Arial", 9),
                    fg="#880000",
                    bg="#ffcccc",
                    anchor="w",
                    wraplength=320,
                ).pack(fill="x", padx=6, pady=(0, 6))

        # C4 / C5: NL summary card
        if condition in ("C4", "C5") and "nl_summary" in data:
            card = tk.Frame(inner, bg="#eef4ff", relief=tk.GROOVE, bd=1)
            card.pack(fill="x", padx=4, pady=4)
            tk.Label(
                card,
                text=data["nl_summary"],
                font=("Arial", 10),
                bg="#eef4ff",
                anchor="w",
                justify="left",
                wraplength=320,
            ).pack(fill="x", padx=8, pady=8)
            if condition == "C5":
                return  # C5 shows only the NL paragraph

        # C1 / C4 (user-centric): consequence sets — show actual configs per colour choice
        if condition in ("C1", "C4") and is_feasible:
            consequence_sets = data.get("consequence_sets", {})
            if consequence_sets:
                # Detect pre-game state: no boundary node has been assigned yet
                any_assigned = any(
                    self._assignments.get(n) is not None
                    for n in consequence_sets
                )

                if not any_assigned:
                    # Pre-game summary card: show the full space of possibilities
                    pre_card = tk.Frame(inner, bg="#e8f4e8", relief=tk.GROOVE, bd=1)
                    pre_card.pack(fill="x", padx=4, pady=(6, 2))
                    tk.Label(
                        pre_card,
                        text=f"✓ {feasibility_count} valid configuration(s) available — everything is open",
                        font=("Arial", 10, "bold"),
                        bg="#e8f4e8",
                        fg="#1a6b1a",
                        anchor="w",
                        wraplength=320,
                    ).pack(fill="x", padx=8, pady=(6, 2))
                    tk.Label(
                        pre_card,
                        text="No constraints active yet. Click one of your nodes to see how each colour choice narrows the agent's options.",
                        font=("Arial", 9),
                        bg="#e8f4e8",
                        fg="#2a5a2a",
                        anchor="w",
                        wraplength=320,
                        justify="left",
                    ).pack(fill="x", padx=8, pady=(0, 6))

                section_lbl = tk.Label(
                    inner,
                    text=(
                        "Options per colour for each of your boundary nodes:"
                        if not any_assigned
                        else "How your colour choices affect agent options:"
                    ),
                    font=("Arial", 9, "bold"),
                    anchor="w",
                )
                section_lbl.pack(fill="x", padx=4, pady=(4, 2))

                COLOUR_FG = {"red": "#cc0000", "green": "#006600", "blue": "#0000cc"}

                for node, colour_configs in sorted(consequence_sets.items()):
                    card = tk.Frame(inner, bg="#f8f8f8", relief=tk.GROOVE, bd=1)
                    card.pack(fill="x", padx=4, pady=2)
                    current_colour = self._assignments.get(node)
                    tk.Label(
                        card,
                        text=f"Node {node}:",
                        font=("Arial", 9, "bold"),
                        bg="#f8f8f8",
                        anchor="w",
                    ).pack(fill="x", padx=6, pady=(4, 0))

                    # colour_configs is {colour: [list_of_agent_assignment_dicts]}
                    for colour, configs in sorted(
                        colour_configs.items(),
                        key=lambda kv: -len(kv[1])
                    ):
                        count = len(configs)
                        is_current = (colour == str(current_colour).lower() if current_colour else False)
                        header_bg = self._colour_fill(colour) if is_current else "#eeeeee"
                        marker = " ◀ current" if is_current else ""
                        feasible_str = f"{count} valid option(s)" if count > 0 else "no valid options"

                        hdr = tk.Frame(card, bg=header_bg)
                        hdr.pack(fill="x", padx=8, pady=(2, 0))
                        tk.Label(
                            hdr,
                            text=f"{colour}: {feasible_str}{marker}",
                            font=("Arial", 9, "bold" if is_current else "normal"),
                            bg=header_bg,
                            anchor="w",
                        ).pack(side="left", padx=4, pady=2)

                        # C1: show AND/OR config list for the current colour.
                        # In pre-game (nothing assigned), show configs for the top-ranked
                        # colour (most options) so the panel has real content to read.
                        show_configs = condition == "C1" and configs and (
                            is_current or (
                                not any_assigned and count == max(
                                    len(v) for v in colour_configs.values()
                                )
                            )
                        )
                        if show_configs:
                            configs_frame = tk.Frame(card, bg="#f8f8f8")
                            configs_frame.pack(fill="x", padx=12, pady=(0, 2))
                            if not any_assigned:
                                tk.Label(
                                    configs_frame,
                                    text=f"(best-case: {colour} gives the most options — example configs)",
                                    font=("Arial", 8, "italic"),
                                    bg="#f8f8f8",
                                    fg="#888",
                                    anchor="w",
                                ).pack(anchor="w")
                            MAX_PREGAME_CONFIGS = 4 if not any_assigned else len(configs)
                            for c_idx, cfg in enumerate(configs[:MAX_PREGAME_CONFIGS]):
                                row = tk.Frame(configs_frame, bg="#f8f8f8")
                                row.pack(anchor="w")
                                parts = sorted(cfg.items())
                                for p_idx, (anode, acolour) in enumerate(parts):
                                    fg = COLOUR_FG.get(str(acolour).lower(), "#333")
                                    tk.Label(row, text=f"{anode}=",
                                             font=("Arial", 8), bg="#f8f8f8",
                                             fg="#555").pack(side="left")
                                    tk.Label(row, text=str(acolour),
                                             font=("Arial", 8, "bold"),
                                             bg="#f8f8f8", fg=fg).pack(side="left")
                                    if p_idx < len(parts) - 1:
                                        tk.Label(row, text=" AND ",
                                                 font=("Arial", 8), bg="#f8f8f8",
                                                 fg="#555").pack(side="left")
                                if c_idx < min(MAX_PREGAME_CONFIGS, len(configs)) - 1:
                                    tk.Label(configs_frame, text="OR",
                                             font=("Arial", 8, "italic"),
                                             bg="#f8f8f8", fg="#888",
                                             anchor="w").pack(anchor="w", padx=4)
                            if not any_assigned and len(configs) > MAX_PREGAME_CONFIGS:
                                tk.Label(
                                    configs_frame,
                                    text=f"… and {len(configs) - MAX_PREGAME_CONFIGS} more",
                                    font=("Arial", 8, "italic"),
                                    bg="#f8f8f8",
                                    fg="#888",
                                ).pack(anchor="w", padx=4)

                    # Small spacer
                    tk.Frame(card, height=4, bg="#f8f8f8").pack()
            else:
                tk.Label(
                    inner,
                    text="No boundary nodes found — check configuration.",
                    font=("Arial", 9, "italic"),
                    fg="#777",
                    anchor="w",
                    wraplength=320,
                ).pack(fill="x", padx=8, pady=8)

        # C2 (agent-centric): boundary joint feasibility — which neighbour combos work
        if condition in ("C2",) and is_feasible:
            boundary_joint = data.get("boundary_joint_feasibility", [])
            boundary_nodes = data.get("boundary_nodes", [])
            if boundary_joint:
                nodes_str = ", ".join(sorted(boundary_nodes))
                section_lbl = tk.Label(
                    inner,
                    text=f"Which of your colour combinations allow the agent to succeed ({nodes_str}):",
                    font=("Arial", 9, "bold"),
                    anchor="w",
                    wraplength=320,
                )
                section_lbl.pack(fill="x", padx=4, pady=(4, 2))

                for entry in boundary_joint:
                    ba = entry.get("boundary_assignment", {})
                    count = entry.get("feasibility_count", 0)
                    combo_str = ", ".join(f"{n}={c}" for n, c in sorted(ba.items()))
                    ok = count > 0
                    card_bg = "#e8ffe8" if ok else "#ffe8e8"
                    marker = "✓" if ok else "✗"
                    card = tk.Frame(inner, bg=card_bg, relief=tk.GROOVE, bd=1)
                    card.pack(fill="x", padx=4, pady=1)
                    tk.Label(
                        card,
                        text=f"{marker}  {combo_str}",
                        font=("Arial", 9),
                        bg=card_bg,
                        anchor="w",
                    ).pack(fill="x", padx=8, pady=2)
            else:
                # Fallback: just show feasibility count
                tk.Label(
                    inner,
                    text=f"Agent has {data.get('feasibility_count', 0)} valid configuration(s) with current boundary choices.",
                    font=("Arial", 9),
                    anchor="w",
                    wraplength=320,
                ).pack(fill="x", padx=8, pady=8)

    # ------------------------------------------------------------------ #
    #  Mini-subgraph sidebar helpers                                       #
    # ------------------------------------------------------------------ #

    def _draw_mini_config(
        self,
        parent_frame: tk.Frame,
        cfg: Dict[str, Any],
        nodes: list,
        edges: list,
        fixed_nodes: Optional[Dict[str, Any]] = None,
        width: int = 160,
        height: int = 100,
        node_positions: Optional[Dict[str, Tuple]] = None,
    ) -> tk.Canvas:
        """Return a small Tk Canvas showing one valid colouring.

        If ``node_positions`` is supplied (a dict of node→(x,y) in the same
        coordinate space as self._node_pos) the positions are scaled to fit
        the canvas, mirroring the main graph layout.  Otherwise nodes are
        arranged in a circle.  Fixed nodes get a thicker outline.
        The canvas is *not* packed/gridded — the caller handles layout.
        """
        import math

        canvas = tk.Canvas(
            parent_frame, width=width, height=height,
            bg="white", highlightthickness=1, highlightbackground="#ccc",
        )

        n = len(nodes)
        if n == 0:
            return canvas

        pos: Dict[str, tuple] = {}
        margin = 18

        if node_positions:
            # Scale the supplied positions to fit the mini-canvas
            valid = {nd: node_positions[nd] for nd in nodes if nd in node_positions}
            if valid:
                xs = [x for x, _ in valid.values()]
                ys = [y for _, y in valid.values()]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                span_x = max(max_x - min_x, 1)
                span_y = max(max_y - min_y, 1)
                scale = min((width - 2 * margin) / span_x,
                            (height - 2 * margin) / span_y)
                off_x = (width - span_x * scale) / 2
                off_y = (height - span_y * scale) / 2
                for nd, (x, y) in valid.items():
                    pos[nd] = (off_x + (x - min_x) * scale,
                               off_y + (y - min_y) * scale)
        else:
            # Circular layout fallback
            cx, cy = width // 2, height // 2
            r = max(min(cx, cy) - margin, 10)
            sorted_nodes_circ = sorted(nodes)
            for i, nd in enumerate(sorted_nodes_circ):
                angle = 2 * math.pi * i / n - math.pi / 2
                pos[nd] = (cx + r * math.cos(angle), cy + r * math.sin(angle))

        sorted_nodes = sorted(nodes)

        # Draw edges
        for u, v in edges:
            if u in pos and v in pos:
                x1, y1 = pos[u]
                x2, y2 = pos[v]
                canvas.create_line(x1, y1, x2, y2, fill="#aaa", width=1)

        # Colour map (matches main graph's _colour_fill palette)
        _FILL = {"red": "#ffcccc", "green": "#ccffcc", "blue": "#ccccff"}
        nr = 11  # node-circle radius

        for node in sorted_nodes:
            if node not in pos:
                continue
            x, y = pos[node]
            colour = cfg.get(node)
            fill = _FILL.get(str(colour).lower(), "#dddddd") if colour else "#dddddd"
            is_fixed = bool((fixed_nodes or {}).get(node))
            outline_w = 2 if is_fixed else 1
            outline_c = "#000000" if is_fixed else "#555555"
            canvas.create_oval(
                x - nr, y - nr, x + nr, y + nr,
                fill=fill, outline=outline_c, width=outline_w,
            )
            canvas.create_text(x, y, text=node, font=("Arial", 7, "bold"), fill="#000")

        return canvas

    def _render_feasibility_panel(self, agent_name: str, data: Dict[str, Any]) -> None:
        """Redraw the right-hand mini-subgraph panel for one agent.

        Shows each valid agent configuration as a small coloured graph.
        """
        areas = self._feasibility_canvas_areas
        if agent_name not in areas:
            return

        _scroll_canvas, inner = areas[agent_name]

        # Clear old content
        for w in inner.winfo_children():
            w.destroy()

        # NL summary card (C4/C5 only) — shown at top of the sidebar before mini-graphs
        nl_summary = data.get("nl_summary")
        condition = getattr(self, '_condition', 'C1')
        if condition in ("C4", "C5") and nl_summary:
            nl_frame = tk.Frame(inner, bg="#eef4ff", relief=tk.GROOVE, bd=1)
            nl_frame.pack(fill="x", padx=4, pady=(4, 6))
            tk.Label(
                nl_frame,
                text=nl_summary,
                font=("Arial", 10),
                bg="#eef4ff",
                fg="#222",
                anchor="w",
                justify="left",
                wraplength=320,
            ).pack(fill="x", padx=8, pady=8)

        feasibility_set = data.get("feasibility_set", [])
        agent_fixed = data.get("fixed_agent_nodes", {})
        is_feasible = data.get("is_feasible", len(feasibility_set) > 0)

        # Build the human's visible graph: own nodes + visible neighbour nodes + all visible edges.
        human_nodes = [n for n in self._nodes if self._owners.get(n) == "Human"]
        visible_agent_nodes = [n for n in self._nodes if self._owners.get(n) != "Human"]
        display_nodes = list(self._nodes)
        display_edges = list(self._edges)
        human_current = {n: self._assignments.get(n) for n in human_nodes}
        human_fixed = getattr(self, '_fixed_nodes', {})
        display_fixed = {
            **{n: True for n in human_nodes if n in human_fixed},
            **{n: True for n in visible_agent_nodes if n in agent_fixed},
        }

        # Update count label
        count_var = self._feasibility_count_vars.get(agent_name)
        if count_var:
            if is_feasible:
                count_var.set(f"{len(feasibility_set)} valid configuration(s)")
            else:
                count_var.set("INFEASIBLE — no valid configuration")

        if not is_feasible:
            lbl = tk.Label(
                inner, text="No valid configuration exists.",
                fg="#cc0000", font=("Arial", 9, "bold"),
                bg="white", anchor="w", wraplength=180,
            )
            lbl.pack(fill="x", padx=6, pady=8)
            repair = data.get("repair_suggestion", [])
            if repair:
                tk.Label(
                    inner,
                    text=f"Try unassigning: {', '.join(repair)}",
                    font=("Arial", 8), fg="#880000", bg="white",
                    anchor="w", wraplength=180,
                ).pack(fill="x", padx=6, pady=(0, 4))
            return

        COLOUR_FG = {"red": "#cc0000", "green": "#006600", "blue": "#0000cc"}
        CARD_BG   = "white"
        HOVER_BG  = "#eef4ff"
        MAX_SHOWN = 12

        # Main graph layout positions (raw, unzoomed) for mini-graph mirroring
        main_pos = dict(self._node_pos)

        def _bind_tree(widget, event, func):
            """Bind func to widget and every descendant."""
            widget.bind(event, func, add=True)
            for child in widget.winfo_children():
                _bind_tree(child, event, func)

        def _set_bg_tree(widget, colour):
            """Recursively set background colour (skip Canvas widgets)."""
            try:
                widget.config(bg=colour)
            except Exception:
                pass
            for child in widget.winfo_children():
                _set_bg_tree(child, colour)

        for idx, cfg in enumerate(feasibility_set[:MAX_SHOWN]):
            # display_cfg: human nodes at current colour, visible agent nodes from this config
            display_cfg = {
                **human_current,
                **{n: cfg.get(n) for n in visible_agent_nodes if n in cfg},
            }

            card = tk.Frame(inner, bg=CARD_BG, bd=1, relief=tk.GROOVE,
                            cursor="hand2")
            card.pack(fill="x", padx=4, pady=3)

            # ---- Side-by-side layout ----
            txt_side = tk.Frame(card, bg=CARD_BG)
            txt_side.pack(side="left", fill="both", expand=True, padx=(6, 2), pady=4)

            graph_side = tk.Frame(card, bg=CARD_BG)
            graph_side.pack(side="right", padx=(2, 4), pady=4)

            # ---- Text: config number + per-line assignments ----
            tk.Label(txt_side, text=f"#{idx + 1}",
                     font=("Arial", 10, "bold"), bg=CARD_BG,
                     fg="#555", anchor="w").pack(anchor="w")

            for nd in sorted(display_cfg):
                colour = display_cfg.get(nd)
                if colour is None:
                    continue
                row = tk.Frame(txt_side, bg=CARD_BG)
                row.pack(anchor="w")
                tk.Label(row, text=f"  {nd} = ", font=("Arial", 10),
                         bg=CARD_BG, fg="#555").pack(side="left")
                fg = COLOUR_FG.get(str(colour).lower(), "#333")
                tk.Label(row, text=str(colour),
                         font=("Arial", 10, "bold"), fg=fg,
                         bg=CARD_BG).pack(side="left")

            # ---- Mini-graph (right side, main layout) ----
            mini = self._draw_mini_config(
                graph_side, display_cfg, display_nodes, display_edges, display_fixed,
                width=160, height=120,
                node_positions=main_pos,
            )
            mini.pack()

            # ---- Hover highlight ----
            def _enter(e, w=card): _set_bg_tree(w, HOVER_BG)
            def _leave(e, w=card): _set_bg_tree(w, CARD_BG)
            _bind_tree(card, "<Enter>", _enter)
            _bind_tree(card, "<Leave>", _leave)

            # ---- Click: preview this agent config in the main graph ----
            dcfg_snap = dict(display_cfg)
            visible_set = set(visible_agent_nodes)

            def _click(e, dcfg=dcfg_snap, vs=visible_set):
                for nd2, col2 in dcfg.items():
                    if nd2 in vs and col2 is not None:
                        self._known_neighbour_colours[nd2] = col2
                if self._root:
                    self._root.after(0, self._redraw_graph)

            _bind_tree(card, "<Button-1>", _click)

        if len(feasibility_set) > MAX_SHOWN:
            tk.Label(
                inner,
                text=f"… and {len(feasibility_set) - MAX_SHOWN} more",
                font=("Arial", 8, "italic"), fg="#777", bg="white",
            ).pack(pady=4)

    # ------------------------------------------------------------------ #
    #  Graph canvas constraint overlays                                    #
    # ------------------------------------------------------------------ #

    def _draw_constraint_overlays(self) -> None:
        """Overlay per-node info boxes on the graph canvas (C1/C3 constraint viz mode).

        Called at the end of _redraw_graph and after each constraint data update.
        Destroys old overlay widgets and recreates them, restoring any positions
        the user has dragged them to (stored in self._overlay_positions).
        """
        if not getattr(self, '_constraint_viz_mode', False):
            return
        canvas = self._canvas
        if canvas is None:
            return

        # If an overlay is currently being dragged, defer the redraw until the
        # drag ends.  Destroying the widget mid-drag would reset the drag state
        # (xr/yr) to 0 on the replacement widget, causing a huge jump.
        if getattr(self, '_overlay_drag_active', False):
            self._root.after(150, self._draw_constraint_overlays)
            return

        # Destroy previous overlay Tk widgets and canvas items
        for w in getattr(self, '_overlay_widgets', []):
            try:
                w.destroy()
            except Exception:
                pass
        for cid in getattr(self, '_overlay_item_ids', []) + getattr(self, '_overlay_tether_ids', []):
            try:
                canvas.delete(cid)
            except Exception:
                pass
        self._overlay_widgets = []
        self._overlay_item_ids = []
        self._overlay_tether_ids = []

        condition = getattr(self, '_condition', 'C1')

        scale = self._graph_canvas_scale
        off_x, off_y = self._graph_canvas_offset
        canvas_w = canvas.winfo_width() or 600

        # Persistent positions: survive redraws (user drags are remembered)
        if not hasattr(self, '_overlay_positions'):
            self._overlay_positions: Dict[str, Tuple[int, int]] = {}

        # Build list of (node, box_factory_fn) to create overlays for
        overlay_items: list = []  # each entry: (node_key, box_widget)

        # Use the submitted snapshot for overlay content so panels only update on Submit
        submitted = self._last_submitted_assignments or self._assignments

        if condition == 'C1':
            # C1: overlays for ALL boundary nodes (assigned or not)
            seen_nodes_c1: set = set()
            for agent_name in self._neighs:
                data = self._constraint_data.get(agent_name, {})
                if not data:
                    continue
                consequence_sets = data.get('consequence_sets', {})
                for node in data.get('boundary_nodes', consequence_sets.keys()):
                    if node in seen_nodes_c1 or node not in self._node_pos:
                        continue
                    seen_nodes_c1.add(node)
                    current_colour = submitted.get(node)
                    colour_map = consequence_sets.get(node, {})
                    box = self._make_constraint_overlay_box(node, current_colour, colour_map)
                    overlay_items.append((node, box))

        elif condition == 'C4':
            # C4: overlays for ALL boundary nodes (even unassigned); NL text in Means
            seen_nodes: set = set()
            for agent_name in self._neighs:
                data = self._constraint_data.get(agent_name, {})
                if not data:
                    continue
                consequence_sets = data.get('consequence_sets', {})
                node_nl = data.get('node_summaries', {})
                # boundary_nodes includes ALL boundary nodes (assigned or not)
                for node in data.get('boundary_nodes', consequence_sets.keys()):
                    if node in seen_nodes or node not in self._node_pos:
                        continue
                    seen_nodes.add(node)
                    current_colour = submitted.get(node)
                    colour_map = consequence_sets.get(node, {})
                    nl_text = node_nl.get(node)
                    box = self._make_constraint_overlay_box(
                        node, current_colour, colour_map, nl_text=nl_text
                    )
                    overlay_items.append((node, box))

        elif condition in ('C2', 'C5'):
            # Agent node overlays using domain_projection
            for agent_name in self._neighs:
                data = self._constraint_data.get(agent_name, {})
                if not data:
                    continue
                domain_proj = data.get('domain_projection', {})
                full_domain = data.get('full_domain', [])
                node_nl = data.get('node_summaries', {})
                for node, dom in domain_proj.items():
                    if node not in self._node_pos:
                        continue  # only visible (boundary) agent nodes
                    nl_text = node_nl.get(node) if condition == 'C5' else None
                    acc = data.get('agent_colour_conditions', {}).get(node, {}) if condition == 'C2' else {}
                    box = self._make_agent_node_overlay_box(
                        node, dom, full_domain, nl_text=nl_text,
                        agent_colour_conditions=acc,
                    )
                    overlay_items.append((node, box))

        elif condition in ('C3', 'C6'):
            # Human-node overlays: valid colour domains for the human's own nodes
            hd = getattr(self, '_human_domain_data', {})
            human_domain = hd.get('human_domain', {})
            full_domain = hd.get('full_domain', list(self._domain))
            node_nl = hd.get('node_summaries', {})
            seen_nodes_hd: set = set()
            for node, node_info in human_domain.items():
                if node in seen_nodes_hd or node not in self._node_pos:
                    continue
                seen_nodes_hd.add(node)
                nl_text = node_nl.get(node) if condition == 'C6' else None
                box = self._make_human_domain_overlay_box(
                    node, node_info, full_domain, nl_text=nl_text
                )
                overlay_items.append((node, box))

        if not overlay_items:
            return

        for node, box in overlay_items:
            if node not in self._node_pos:
                continue

            # Screen coordinates of the node centre
            nx, ny = self._node_pos[node]
            tx = int(nx * scale + off_x)
            ty = int(ny * scale + off_y)
            node_r = int(24 * scale)

            # Use saved position if available, otherwise default (right/left of node)
            if node in self._overlay_positions:
                bx, by = self._overlay_positions[node]
            else:
                box_w = 240
                if tx + node_r + 8 + box_w < canvas_w:
                    bx = tx + node_r + 8
                else:
                    bx = tx - node_r - 8 - box_w
                by = ty - node_r

            # Tether line drawn first so it sits behind the box
            tether = canvas.create_line(
                tx, ty, bx, by + 12,
                fill="#aaaaaa", width=1, dash=(5, 3),
            )
            self._overlay_tether_ids.append(tether)

            item = canvas.create_window(bx, by, window=box, anchor='nw')
            self._overlay_item_ids.append(item)
            self._overlay_widgets.append(box)

            # ---- Drag binding on the header label ----
            handle = getattr(box, '_drag_handle', box)
            drag = {'xr': 0, 'yr': 0, 'cx': bx, 'cy': by}

            def _press(ev, d=drag):
                d['xr'] = ev.x_root
                d['yr'] = ev.y_root
                self._overlay_drag_active = True

            def _release(ev):
                self._overlay_drag_active = False

            def _move(ev, d=drag, wi=item, ti=tether, ntx=tx, nty=ty, nd=node,
                      pos=self._overlay_positions):
                dx = ev.x_root - d['xr']
                dy = ev.y_root - d['yr']
                d['xr'] = ev.x_root
                d['yr'] = ev.y_root
                d['cx'] += dx
                d['cy'] += dy
                canvas.move(wi, dx, dy)
                canvas.coords(ti, ntx, nty, d['cx'], d['cy'] + 12)
                # Persist the new position so redraws restore it
                pos[nd] = (d['cx'], d['cy'])

            handle.bind('<Button-1>', _press)
            handle.bind('<ButtonRelease-1>', _release)
            handle.bind('<B1-Motion>', _move)

    def _draw_domain_arcs(
        self,
        canvas: tk.Canvas,
        tx: float,
        ty: float,
        r: int,
        node: str,
        scale: float,
    ) -> None:
        """Draw a full-circle domain ring around a human-owned node.

        The ring is divided into equal arcs — one per allowed colour.
        Arcs fill the full 360° with no gaps:
          1 colour  → 360° single arc
          2 colours → 180° each
          3 colours → 120° each

        Canonical clockwise colour order starting from the top: red, green, blue.
        Unconstrained nodes (not in _node_domains) show all three colours.
        """
        COLOUR_ORDER = ["red", "green", "blue"]
        COLOUR_HEX   = {"red": "#cc2222", "green": "#22aa22", "blue": "#2244cc"}

        # Determine which colours are allowed (in canonical order)
        node_dom = self._node_domains.get(node)
        if node_dom is not None:
            allowed_lower = set(str(c).lower() for c in node_dom)
            allowed = [c for c in COLOUR_ORDER if c in allowed_lower]
        else:
            allowed = list(COLOUR_ORDER)  # unconstrained — show all three

        if not allowed:
            return

        n_colours = len(allowed)
        arc_span  = 360.0 / n_colours   # each arc fills an equal share

        ring_r = r + max(7, int(9 * scale))
        arc_w  = max(4, int(6 * scale))

        # Start at 90° (top), sweep clockwise (negative extent in Tkinter).
        # Tkinter drops a full 360° arc entirely, so clamp to 359.9° for the
        # single-colour case to guarantee the ring is always visible.
        start = 90.0
        extent = -min(arc_span, 359.9)
        for colour in allowed:
            canvas.create_arc(
                tx - ring_r, ty - ring_r,
                tx + ring_r, ty + ring_r,
                start=start,
                extent=extent,
                style=tk.ARC,
                outline=COLOUR_HEX.get(colour, "#888888"),
                width=arc_w,
            )
            start -= arc_span

    def _make_constraint_overlay_box(
        self,
        node: str,
        current_colour: Any,
        colour_map: Dict[str, Any],
        nl_text: Optional[str] = None,
    ) -> tk.Frame:
        """Build the floating constraint info box for one boundary node.

        Shows:
          Because: node=Colour
          Means:   NL summary (if nl_text provided) OR config1 OR config2 … (enumeration)
        """
        COLOUR_FG = {"red": "#cc0000", "green": "#006600", "blue": "#0000cc"}

        outer = tk.Frame(self._canvas, bg="#888888", bd=1, relief=tk.RAISED)

        # Drag handle header (dark bar with node name + move cursor)
        header = tk.Label(outer, text=f"⠿ {node}", font=("Arial", 8, "bold"),
                          bg="#444444", fg="white", padx=6, pady=2,
                          cursor="fleur", anchor="w")
        header.pack(fill="x")
        outer._drag_handle = header  # used by _draw_constraint_overlays

        inner = tk.Frame(outer, bg="white", padx=5, pady=4)
        inner.pack(fill="both", expand=True)

        # ---- Because ----
        tk.Label(inner, text="Because:", font=("Arial", 8, "bold"),
                 bg="white", anchor="w").pack(anchor="w")
        if current_colour:
            fg = COLOUR_FG.get(str(current_colour).lower(), "#333")
            row = tk.Frame(inner, bg="white")
            row.pack(anchor="w")
            tk.Label(row, text=f"  {node}=", font=("Arial", 8),
                     bg="white", fg="#333").pack(side="left")
            tk.Label(row, text=str(current_colour),
                     font=("Arial", 8, "bold"), fg=fg,
                     bg="white").pack(side="left")
        else:
            n_open = sum(1 for cfgs in colour_map.values() if cfgs) if colour_map else 0
            not_assigned_text = "  (not yet assigned — all colours viable)" if n_open == len(colour_map) and colour_map else "  (not yet assigned)"
            tk.Label(inner, text=not_assigned_text,
                     font=("Arial", 8, "italic"), fg="#999",
                     bg="white", anchor="w").pack(anchor="w")

        # ---- Means ----
        tk.Label(inner, text="Means:", font=("Arial", 8, "bold"),
                 bg="white", anchor="w").pack(anchor="w", pady=(4, 0))

        if nl_text:
            # NL summary mode (C3/C4): show LLM-generated sentence
            tk.Label(inner, text=nl_text, font=("Arial", 8),
                     bg="white", fg="#1a1a6e", wraplength=220,
                     justify="left", anchor="w").pack(anchor="w", pady=(2, 0))
        else:
            # Formulaic mode (C1/C2): show count + visible-neighbour constraints only.
            # Filter configs to nodes visible in the graph (_node_pos) to avoid
            # naming agent-internal nodes the human cannot see.
            cur_key = str(current_colour).lower() if current_colour else ""
            configs = colour_map.get(cur_key) or colour_map.get(str(current_colour), [])
            visible_nodes = set(self._node_pos.keys())
            MAX_SHOW = 6
            if configs:
                total = len(configs)
                # Build visible-only filtered configs and deduplicate
                filtered_cfgs = []
                seen_sigs = set()
                for cfg in configs:
                    vis_cfg = {n2: c2 for n2, c2 in cfg.items()
                               if n2 in visible_nodes and n2 != node}
                    sig = tuple(sorted(vis_cfg.items()))
                    if sig not in seen_sigs:
                        seen_sigs.add(sig)
                        filtered_cfgs.append(vis_cfg)

                # Count summary
                tk.Label(inner, text=f"  {total} valid option(s)",
                         font=("Arial", 8), fg="#1a6e1a",
                         bg="white", anchor="w").pack(anchor="w")

                # Show other colours that are also valid
                other_valid = [
                    (col, len(cfgs))
                    for col, cfgs in sorted(colour_map.items())
                    if col != cur_key and cfgs and len(cfgs) > 0
                ]
                if other_valid:
                    also_row = tk.Frame(inner, bg="white")
                    also_row.pack(anchor="w", pady=(1, 0))
                    tk.Label(also_row, text="  Also OK: ",
                             font=("Arial", 7, "italic"), fg="#555",
                             bg="white").pack(side="left")
                    for i, (col, cnt) in enumerate(other_valid):
                        fg_col = COLOUR_FG.get(col, "#333")
                        lbl_text = col if i == len(other_valid) - 1 else col + ","
                        tk.Label(also_row, text=lbl_text,
                                 font=("Arial", 7, "bold"), fg=fg_col,
                                 bg="white").pack(side="left")

                # Show visible-neighbour entries if informative
                if filtered_cfgs and any(filtered_cfgs):
                    tk.Label(inner, text="Neighbour constraints:",
                             font=("Arial", 7, "italic"), fg="#555",
                             bg="white", anchor="w").pack(anchor="w", pady=(3, 0))
                    for i, vis_cfg in enumerate(filtered_cfgs[:MAX_SHOW]):
                        if not vis_cfg:
                            continue
                        row = tk.Frame(inner, bg="white")
                        row.pack(anchor="w")
                        first = True
                        for n2, c2 in sorted(vis_cfg.items()):
                            if not first:
                                tk.Label(row, text=" AND ", font=("Arial", 7),
                                         bg="white", fg="#555").pack(side="left")
                            tk.Label(row, text=f"  {n2}=" if first else f"{n2}=",
                                     font=("Arial", 7), bg="white",
                                     fg="#333").pack(side="left")
                            fg2 = COLOUR_FG.get(str(c2).lower(), "#333")
                            tk.Label(row, text=str(c2),
                                     font=("Arial", 7, "bold"), fg=fg2,
                                     bg="white").pack(side="left")
                            first = False
                        if i < min(len(filtered_cfgs), MAX_SHOW) - 1:
                            tk.Label(inner, text=" OR", font=("Arial", 7),
                                     bg="white", fg="#555",
                                     anchor="w").pack(anchor="w")
                    if len(filtered_cfgs) > MAX_SHOW:
                        tk.Label(inner, text=f"  … ({len(filtered_cfgs)} combinations)",
                                 font=("Arial", 7, "italic"), fg="#777",
                                 bg="white", anchor="w").pack(anchor="w")
            elif current_colour:
                tk.Label(inner, text="  No valid configs — try a different colour",
                         font=("Arial", 8), fg="#cc0000",
                         bg="white", anchor="w").pack(anchor="w")
            else:
                # Unassigned: show per-colour option counts + example configs for best colour
                if colour_map:
                    colour_counts = {col: len(cfgs) for col, cfgs in colour_map.items() if cfgs is not None}
                    if any(n > 0 for n in colour_counts.values()):
                        # Summary row: counts per colour
                        total_all = sum(colour_counts.values())
                        count_parts = "  ".join(
                            f"{col}: {cnt}"
                            for col, cnt in sorted(colour_counts.items(), key=lambda kv: -kv[1])
                        )
                        tk.Label(inner, text=f"  All colours open — options per colour:",
                                 font=("Arial", 7, "italic"), fg="#555",
                                 bg="white", anchor="w").pack(anchor="w")
                        tk.Label(inner, text=f"  {count_parts}",
                                 font=("Arial", 8, "bold"), fg="#1a6e1a",
                                 bg="white", anchor="w").pack(anchor="w")

                        # Show top 3 configs for the colour with most options
                        best_col = max(colour_counts, key=lambda c: colour_counts[c])
                        best_configs = colour_map.get(best_col, [])
                        filtered_cfgs = []
                        seen_sigs: set = set()
                        for cfg in best_configs:
                            vis_cfg = {n2: c2 for n2, c2 in cfg.items()
                                       if n2 in visible_nodes and n2 != node}
                            sig = tuple(sorted(vis_cfg.items()))
                            if sig not in seen_sigs and vis_cfg:
                                seen_sigs.add(sig)
                                filtered_cfgs.append(vis_cfg)

                        if filtered_cfgs:
                            tk.Label(inner,
                                     text=f"e.g. if {node}={best_col}:",
                                     font=("Arial", 7, "italic"), fg="#555",
                                     bg="white", anchor="w").pack(anchor="w", pady=(3, 0))
                            MAX_EG = 3
                            for i, vis_cfg in enumerate(filtered_cfgs[:MAX_EG]):
                                row = tk.Frame(inner, bg="white")
                                row.pack(anchor="w")
                                first = True
                                for n2, c2 in sorted(vis_cfg.items()):
                                    if not first:
                                        tk.Label(row, text=" AND ", font=("Arial", 7),
                                                 bg="white", fg="#555").pack(side="left")
                                    tk.Label(row, text=f"  {n2}=" if first else f"{n2}=",
                                             font=("Arial", 7), bg="white",
                                             fg="#333").pack(side="left")
                                    fg2 = COLOUR_FG.get(str(c2).lower(), "#333")
                                    tk.Label(row, text=str(c2),
                                             font=("Arial", 7, "bold"), fg=fg2,
                                             bg="white").pack(side="left")
                                    first = False
                                if i < min(len(filtered_cfgs), MAX_EG) - 1:
                                    tk.Label(inner, text=" OR", font=("Arial", 7),
                                             bg="white", fg="#555",
                                             anchor="w").pack(anchor="w")
                            if len(filtered_cfgs) > MAX_EG:
                                tk.Label(inner,
                                         text=f"  … ({colour_counts[best_col]} total)",
                                         font=("Arial", 7, "italic"), fg="#777",
                                         bg="white", anchor="w").pack(anchor="w")
                    else:
                        tk.Label(inner, text="  No valid options available",
                                 font=("Arial", 7, "italic"), fg="#cc0000",
                                 bg="white", anchor="w").pack(anchor="w")
                else:
                    tk.Label(inner, text="  Assign this node to see options",
                             font=("Arial", 7, "italic"), fg="#777",
                             bg="white", anchor="w").pack(anchor="w")

        return outer

    def _make_agent_node_overlay_box(
        self,
        node: str,
        domain: list,
        full_domain: list,
        nl_text: Optional[str] = None,
        agent_colour_conditions: Optional[dict] = None,
    ) -> tk.Frame:
        """Build a floating overlay box for an agent node (C2/C4 conditions).

        Shows the valid colour domain for that agent node.
        If nl_text is provided (C4), shows LLM summary instead of raw domain.
        """
        COLOUR_FG = {"red": "#cc0000", "green": "#006600", "blue": "#0000cc"}
        COLOUR_BG = {"red": "#ffe0e0", "green": "#e0ffe0", "blue": "#e0e0ff"}
        constrained = domain and (len(domain) < len(full_domain))

        outer = tk.Frame(self._canvas, bg="#666688", bd=1, relief=tk.RAISED)

        # Drag handle header
        header = tk.Label(outer, text=f"⠿ {node}", font=("Arial", 8, "bold"),
                          bg="#334466", fg="white", padx=6, pady=2,
                          cursor="fleur", anchor="w")
        header.pack(fill="x")
        outer._drag_handle = header

        inner = tk.Frame(outer, bg="white", padx=5, pady=4)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="Agent node:", font=("Arial", 8, "bold"),
                 bg="white", anchor="w").pack(anchor="w")
        tk.Label(inner, text=f"  {node}", font=("Arial", 8),
                 bg="white", fg="#333", anchor="w").pack(anchor="w")

        tk.Label(inner, text="Can be:", font=("Arial", 8, "bold"),
                 bg="white", anchor="w").pack(anchor="w", pady=(4, 0))

        if nl_text:
            # NL summary mode (C4)
            tk.Label(inner, text=nl_text, font=("Arial", 8),
                     bg="white", fg="#1a1a6e", wraplength=220,
                     justify="left", anchor="w").pack(anchor="w", pady=(2, 0))
        else:
            # C2 formulaic: Possible / Conditional sections
            acc = agent_colour_conditions or {}
            certain = acc.get("certain", [])
            conditional = acc.get("conditional", [])  # [(colour, [cond_str,...])]

            if not domain:
                tk.Label(inner, text="(no valid colours)", font=("Arial", 7, "italic"),
                         fg="#cc0000", bg="white", anchor="w").pack(anchor="w")
            elif not acc:
                # acc not yet computed (first render): fall back to plain swatches
                swatch_row = tk.Frame(inner, bg="white")
                swatch_row.pack(anchor="w", pady=2)
                for col in sorted(domain, key=str):
                    tk.Label(swatch_row, text=f" {col} ",
                             font=("Arial", 7, "bold"), fg=COLOUR_FG.get(col, "#333"),
                             bg=COLOUR_BG.get(col, "#eee"), relief=tk.GROOVE, bd=1,
                             padx=2, pady=1).pack(side="left", padx=2)
            else:
                if certain:
                    tk.Label(inner, text="Possible:", font=("Arial", 7, "bold"),
                             bg="white", fg="#006600", anchor="w").pack(anchor="w", pady=(4, 0))
                    row = tk.Frame(inner, bg="white")
                    row.pack(anchor="w", padx=4)
                    for i, col in enumerate(sorted(certain, key=str)):
                        if i > 0:
                            tk.Label(row, text=" OR ", font=("Arial", 7),
                                     bg="white", fg="#555").pack(side="left")
                        tk.Label(row, text=f" {col} ",
                                 font=("Arial", 7, "bold"),
                                 fg=COLOUR_FG.get(col, "#333"), bg=COLOUR_BG.get(col, "#eee"),
                                 relief=tk.GROOVE, bd=1, padx=2, pady=1).pack(side="left", padx=1)

                if conditional:
                    tk.Label(inner, text="Conditional:", font=("Arial", 7, "bold"),
                             bg="white", fg="#884400", anchor="w").pack(anchor="w", pady=(4, 0))
                    for col, cond_strs in conditional:
                        cond_display = " AND ".join(sorted(set(cond_strs)))
                        cond_row = tk.Frame(inner, bg="white")
                        cond_row.pack(anchor="w", padx=4)
                        tk.Label(cond_row, text=f" {col} ",
                                 font=("Arial", 7, "bold"),
                                 fg=COLOUR_FG.get(col, "#333"), bg=COLOUR_BG.get(col, "#eee"),
                                 relief=tk.GROOVE, bd=1, padx=2, pady=1).pack(side="left")
                        tk.Label(cond_row, text=f" IF {cond_display}",
                                 font=("Arial", 7), fg="#555", bg="white").pack(side="left")

        return outer

    def _make_human_domain_overlay_box(
        self,
        node: str,
        node_info: dict,
        full_domain: list,
        nl_text: Optional[str] = None,
    ) -> tk.Frame:
        """Build a floating overlay for a human node (C3/C6): shows valid colours.

        node_info keys: valid, blocked_agents, current.
        blocked_agents: {colour: [agent_names]} — colours that break agent feasibility.
        """
        COLOUR_FG = {"red": "#cc0000", "green": "#006600", "blue": "#0000cc"}
        COLOUR_BG = {"red": "#ffe0e0", "green": "#e0ffe0", "blue": "#e0e0ff"}

        valid = node_info.get("valid", [])
        blocked_agents = node_info.get("blocked_agents", {})
        current = node_info.get("current")
        all_blocked = (not valid)
        all_free = (len(valid) == len(full_domain))

        header_bg = "#446644" if not all_blocked else "#884422"
        outer = tk.Frame(self._canvas, bg=header_bg, bd=1, relief=tk.RAISED)

        header = tk.Label(outer, text=f"⠿ {node}", font=("Arial", 8, "bold"),
                          bg=header_bg, fg="white", padx=6, pady=2,
                          cursor="fleur", anchor="w")
        header.pack(fill="x")
        outer._drag_handle = header

        inner = tk.Frame(outer, bg="white", padx=5, pady=4)
        inner.pack(fill="both", expand=True)

        # Current colour indicator
        if current:
            tk.Label(inner, text="Current:", font=("Arial", 8, "bold"),
                     bg="white", anchor="w").pack(anchor="w")
            fg = COLOUR_FG.get(str(current).lower(), "#333")
            bg = COLOUR_BG.get(str(current).lower(), "#eee")
            row = tk.Frame(inner, bg="white")
            row.pack(anchor="w", padx=4, pady=(0, 3))
            tk.Label(row, text=f" {current} ", font=("Arial", 8, "bold"),
                     fg=fg, bg=bg, relief=tk.GROOVE, bd=1,
                     padx=2, pady=1).pack(side="left")

        tk.Label(inner, text="Can pick:", font=("Arial", 8, "bold"),
                 bg="white", anchor="w").pack(anchor="w", pady=(2, 0))

        if nl_text:
            # C6: LLM summary
            tk.Label(inner, text=nl_text, font=("Arial", 8),
                     bg="white", fg="#1a1a6e", wraplength=220,
                     justify="left", anchor="w").pack(anchor="w", pady=(2, 0))
        elif all_blocked:
            tk.Label(inner, text="(nothing — change a neighbour)",
                     font=("Arial", 7, "italic"), fg="#cc0000",
                     bg="white", anchor="w").pack(anchor="w")
        elif all_free:
            tk.Label(inner, text="Any colour works here",
                     font=("Arial", 7, "italic"), fg="#006600",
                     bg="white", anchor="w").pack(anchor="w")
        else:
            # Formulaic: show valid swatches + briefly note blocked
            swatch_row = tk.Frame(inner, bg="white")
            swatch_row.pack(anchor="w", pady=2)
            for i, col in enumerate(sorted(valid, key=str)):
                if i > 0:
                    tk.Label(swatch_row, text=" or ", font=("Arial", 7),
                             bg="white", fg="#555").pack(side="left")
                tk.Label(swatch_row, text=f" {col} ",
                         font=("Arial", 7, "bold"),
                         fg=COLOUR_FG.get(col, "#333"), bg=COLOUR_BG.get(col, "#eee"),
                         relief=tk.GROOVE, bd=1, padx=2, pady=1).pack(side="left", padx=1)

            # Show blocked colours with reason (agent constraints only)
            if blocked_agents:
                tk.Label(inner, text="Avoid:", font=("Arial", 7, "bold"),
                         bg="white", fg="#884400", anchor="w").pack(anchor="w", pady=(3, 0))
                for col in sorted(blocked_agents.keys()):
                    reason_row = tk.Frame(inner, bg="white")
                    reason_row.pack(anchor="w", padx=4)
                    tk.Label(reason_row, text=f" {col} ",
                             font=("Arial", 7, "bold"),
                             fg=COLOUR_FG.get(col, "#888"),
                             bg="#f0f0f0",
                             relief=tk.GROOVE, bd=1, padx=2, pady=1).pack(side="left")
                    tk.Label(reason_row, text=" breaks agent",
                             font=("Arial", 7, "italic"), fg="#888",
                             bg="white").pack(side="left")

        return outer

    def _initial_populate(self) -> None:
        """Trigger initial constraint computation before the user has clicked anything.

        Treated as submission #0 (the starting state) and recorded in history.
        """
        if not getattr(self, '_constraint_viz_mode', False):
            return
        snapshot = dict(self._assignments)

        if not getattr(self, '_on_constraint_update', None):
            return

        # Create a history entry for the initial state
        entry: Dict[str, Any] = {
            "num": 0,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "assignments": snapshot,
            "responses": {},
            "is_feasible": {},
        }
        self._submission_history.append(entry)
        self._last_submitted_assignments = snapshot
        self._has_pending_changes = False
        self._submission_computing = True
        self._refresh_submit_button()
        # Don't add #0 to the history bar — it's the pre-game initial state

        total = len(self._neighs)
        done_count = [0]

        def _bg_update(neigh: str) -> None:
            try:
                data = self._on_constraint_update(neigh, snapshot)
                entry["responses"][neigh] = data
                entry["is_feasible"][neigh] = data.get(
                    "is_feasible", data.get("feasibility_count", 0) > 0
                )
                self.update_constraint_display(neigh, data)
            except Exception as _exc:
                print(f"[ConstraintViz] initial_populate error for {neigh}: {_exc}")
            finally:
                done_count[0] += 1
                if done_count[0] >= total:
                    if self._root:
                        self._root.after(0, lambda: self._on_submission_complete(entry))

        for neigh in self._neighs:
            threading.Thread(target=_bg_update, args=(neigh,), daemon=True).start()

        if getattr(self, '_on_human_domain_update', None):
            def _bg_hd() -> None:
                try:
                    data = self._on_human_domain_update(snapshot)
                    self.update_human_domain_display(data)
                except Exception as _exc:
                    print(f"[ConstraintViz] initial_populate human_domain error: {_exc}")
            threading.Thread(target=_bg_hd, daemon=True).start()

    # -------------------- Synchronous Submit & History (Constraint Viz) --------------------

    def _all_human_nodes_assigned(self) -> bool:
        """Return True when every human-owned node has a colour assigned."""
        human_nodes = [n for n in self._nodes if self._owners.get(n) == "Human"
                       and n not in getattr(self, '_fixed_nodes', {})]
        return all(self._assignments.get(n) is not None for n in human_nodes)

    def _refresh_submit_button(self) -> None:
        """Update the Submit button label/style to reflect pending state."""
        btn = self._submit_btn
        if btn is None:
            return
        if self._submission_computing:
            btn.config(text="Computing…", state="disabled")
        elif not self._all_human_nodes_assigned():
            btn.config(text="Assign all nodes first", state="disabled")
        elif self._has_pending_changes:
            btn.config(text="Submit Configuration  ▶", state="normal")
        else:
            btn.config(text="Configuration Submitted", state="normal")

    def _submit_configuration(self) -> None:
        """Save current assignments to history and fire all constraint-update callbacks."""
        if self._submission_computing:
            return
        if not getattr(self, '_on_constraint_update', None):
            return

        snapshot = dict(self._assignments)
        num = len(self._submission_history) + 1
        entry: Dict[str, Any] = {
            "num": num,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "assignments": snapshot,
            "responses": {},
            "is_feasible": {},
        }
        self._submission_history.append(entry)
        self._last_submitted_assignments = snapshot
        self._has_pending_changes = False
        self._submission_computing = True
        self._refresh_submit_button()

        # Add history bar button immediately (shows "computing" state)
        self._add_to_history_bar(entry, computing=True)

        total = len(self._neighs)
        if total == 0:
            self._submission_computing = False
            self._refresh_submit_button()
            return

        done_count = [0]

        def _bg_update(neigh: str) -> None:
            try:
                self.update_agent_status(neigh, "Computing…")
                data = self._on_constraint_update(neigh, snapshot)
                entry["responses"][neigh] = data
                entry["is_feasible"][neigh] = data.get("is_feasible",
                                                        data.get("feasibility_count", 0) > 0)
                self.update_constraint_display(neigh, data)
                self.clear_agent_status(neigh)

                # Also fire human-domain update if available
                if getattr(self, '_on_human_domain_update', None):
                    try:
                        hd_data = self._on_human_domain_update(snapshot)
                        self.update_human_domain_display(hd_data)
                    except Exception as hd_exc:
                        print(f"[Submit] human_domain update error: {hd_exc}")
            except Exception as exc:
                print(f"[Submit] error for {neigh}: {exc}")
                self.clear_agent_status(neigh)
            finally:
                done_count[0] += 1
                if done_count[0] >= total:
                    if self._root:
                        self._root.after(0, lambda: self._on_submission_complete(entry))

        for neigh in self._neighs:
            threading.Thread(target=_bg_update, args=(neigh,), daemon=True).start()

    def _on_submission_complete(self, entry: Dict) -> None:
        """Called on the Tk thread once all agents have responded to a submission."""
        self._submission_computing = False
        self._refresh_submit_button()
        # Refresh the history bar button with final feasibility result (#0 is silent)
        if entry.get("num", 0) > 0:
            self._add_to_history_bar(entry, computing=False, refresh=True)

    def _draw_history_mini_graph(self, canvas: "tk.Canvas", assignments: Dict,
                                  w: int, h: int) -> None:
        """Draw a small graph of human-owned nodes onto *canvas* (w×h pixels)."""
        COLOUR_FILL = {"red": "#ff6666", "green": "#44bb44", "blue": "#4466ff"}
        COLOUR_OUT  = {"red": "#aa0000", "green": "#006600", "blue": "#0000aa"}

        human_nodes = [n for n in self._nodes if self._owners.get(n) == "Human"]
        if not human_nodes:
            return

        positions = {n: self._node_pos[n] for n in human_nodes if n in self._node_pos}
        if not positions:
            return

        # Normalise positions to fit in canvas with padding, then centre
        pad = 16
        xs = [p[0] for p in positions.values()]
        ys = [p[1] for p in positions.values()]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        span_x = max(x_max - x_min, 1)
        span_y = max(y_max - y_min, 1)
        avail_w = w - 2 * pad
        avail_h = h - 2 * pad
        scale = min(avail_w / span_x, avail_h / span_y)

        # Centre the fitted content in the available space
        fitted_w = span_x * scale
        fitted_h = span_y * scale
        off_x = pad + (avail_w - fitted_w) / 2
        off_y = pad + (avail_h - fitted_h) / 2

        def to_canvas(nx, ny):
            cx = off_x + (nx - x_min) * scale
            cy = off_y + (ny - y_min) * scale
            return cx, cy

        # Draw edges between human nodes
        human_set = set(human_nodes)
        for u, v in self._edges:
            if u in human_set and v in human_set and u in positions and v in positions:
                x1, y1 = to_canvas(*positions[u])
                x2, y2 = to_canvas(*positions[v])
                canvas.create_line(x1, y1, x2, y2, fill="#666666", width=1)

        # Draw nodes
        r = max(8, int(scale * 0.35))
        r = min(r, 18)
        for node in human_nodes:
            if node not in positions:
                continue
            cx, cy = to_canvas(*positions[node])
            col = assignments.get(node)
            col_str = str(col).lower() if col is not None else ""
            fill = COLOUR_FILL.get(col_str, "#888888")
            outline = COLOUR_OUT.get(col_str, "#444444")
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                               fill=fill, outline=outline, width=1)
            canvas.create_text(cx, cy, text=node,
                               font=("TkDefaultFont", 8, "bold"), fill="white")

    def _add_to_history_bar(self, entry: Dict, computing: bool = False,
                             refresh: bool = False) -> None:
        """Add or refresh a card for *entry* in the history bar."""
        bar = self._history_bar
        if bar is None:
            return

        # Hide the placeholder label on first entry
        if hasattr(self, '_history_placeholder') and self._history_placeholder is not None:
            try:
                self._history_placeholder.pack_forget()
            except Exception:
                pass
            self._history_placeholder = None

        tag = f"_hist_btn_{entry['num']}"

        # If refreshing an existing button, destroy the old one
        if refresh:
            for w in bar.winfo_children():
                if getattr(w, '_hist_tag', None) == tag:
                    w.destroy()
                    break

        feasible_all = all(entry["is_feasible"].values()) if entry["is_feasible"] else None
        if computing:
            status_text = f"#{entry['num']}  ⏳"
            bg = "#333355"
            fg = "#aaaacc"
        elif feasible_all is True:
            status_text = f"#{entry['num']}  ✓"
            bg = "#1a4d1a"
            fg = "#88ff88"
        elif feasible_all is False:
            status_text = f"#{entry['num']}  ✗"
            bg = "#4d1a1a"
            fg = "#ff8888"
        else:
            status_text = f"#{entry['num']}"
            bg = "#333355"
            fg = "#aaaacc"

        MINI_W, MINI_H = 90, 150

        # Outer frame acts as the clickable card
        card = tk.Frame(bar, bg=bg, relief="raised", bd=1, cursor="hand2")
        card._hist_tag = tag  # type: ignore[attr-defined]
        card.pack(side="left", padx=3, pady=2)

        # Mini graph canvas
        mini = tk.Canvas(card, width=MINI_W, height=MINI_H, bg=bg,
                         highlightthickness=0)
        mini.pack(padx=2, pady=(3, 0))
        self._draw_history_mini_graph(mini, entry["assignments"], MINI_W, MINI_H)

        # Status label below graph
        tk.Label(card, text=status_text, bg=bg, fg=fg,
                 font=("TkDefaultFont", 8)).pack(pady=(1, 3))

        # Bind click on all children
        callback = lambda e, ent=entry: self._view_history_entry(ent)
        for w in (card, mini) + tuple(card.winfo_children()):
            w.bind("<Button-1>", callback)

    def _view_history_entry(self, entry: Dict) -> None:
        """Open a popup showing a past submission: assignments, responses, restore option."""
        popup = tk.Toplevel(self._root)
        popup.title(f"Attempt #{entry['num']} — {entry['timestamp']}")
        popup.geometry("520x480")
        popup.resizable(True, True)
        popup.attributes("-topmost", True)

        # ---- Header ----
        hdr = tk.Frame(popup, bg="#1e1e2e", pady=6)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"Attempt #{entry['num']}",
                 font=("TkDefaultFont", 13, "bold"),
                 bg="#1e1e2e", fg="white").pack(side="left", padx=10)
        tk.Label(hdr, text=entry["timestamp"],
                 font=("TkDefaultFont", 11), bg="#1e1e2e", fg="#aaaacc").pack(side="left")

        # ---- Assignments table ----
        f_assign = ttk.LabelFrame(popup, text="Your Assignment")
        f_assign.pack(fill="x", padx=10, pady=(8, 4))

        COLOUR_BG = {"red": "#ffcccc", "green": "#ccffcc", "blue": "#ccccff"}
        COLOUR_FG = {"red": "#880000", "green": "#005500", "blue": "#000088"}

        assignments = entry["assignments"]
        human_nodes = sorted(
            n for n, o in self._owners.items() if o == "Human" and n in assignments
        )
        row_frame = tk.Frame(f_assign)
        row_frame.pack(fill="x", padx=6, pady=4)
        for node in human_nodes:
            col = assignments.get(node)
            col_str = str(col) if col is not None else "—"
            bg = COLOUR_BG.get(col_str, "#eeeeee") if col is not None else "#dddddd"
            fg = COLOUR_FG.get(col_str, "#333333")
            cell = tk.Frame(row_frame, bg=bg, relief="groove", bd=1)
            cell.pack(side="left", padx=3, pady=2, ipadx=4, ipady=2)
            tk.Label(cell, text=node, font=("TkDefaultFont", 9, "bold"),
                     bg=bg, fg=fg).pack()
            tk.Label(cell, text=col_str, font=("TkDefaultFont", 9),
                     bg=bg, fg=fg).pack()

        # ---- Responses per agent ----
        responses = entry.get("responses", {})
        if responses:
            f_resp = ttk.LabelFrame(popup, text="Agent Responses")
            f_resp.pack(fill="both", expand=True, padx=10, pady=4)
            resp_text = tk.Text(f_resp, height=10, font=("Courier", 9),
                                wrap="word", state="normal")
            resp_text.pack(fill="both", expand=True, padx=4, pady=4)

            for agent, data in sorted(responses.items()):
                feas_count = data.get("feasibility_count", "?")
                is_feas = data.get("is_feasible", feas_count != 0)
                status_icon = "✓" if is_feas else "✗"
                resp_text.insert("end", f"{status_icon} {agent}: {feas_count} valid config(s)\n",
                                 "bold" if is_feas else "bad")
                nl_summary = data.get("nl_summary", "")
                if nl_summary:
                    resp_text.insert("end", f"   {nl_summary}\n")
                resp_text.insert("end", "\n")

            resp_text.tag_config("bold", foreground="#006600", font=("Courier", 9, "bold"))
            resp_text.tag_config("bad", foreground="#cc0000", font=("Courier", 9, "bold"))
            resp_text.config(state="disabled")
        else:
            tk.Label(popup, text="(No responses recorded — attempt may still be computing)",
                     fg="#888888", font=("TkDefaultFont", 9, "italic")).pack(pady=6)

        # ---- Restore button ----
        def _restore() -> None:
            fixed = getattr(self, '_fixed_nodes', {})
            for node, colour in assignments.items():
                if node in fixed:
                    continue  # never overwrite fixed nodes
                if self._owners.get(node) == "Human":
                    self._assignments[node] = colour
            self._has_pending_changes = True
            self._redraw_graph()
            if self._hud_var:
                self._hud_var.set(self._hud_text())
            self._refresh_submit_button()
            popup.destroy()

        btn_row = tk.Frame(popup)
        btn_row.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(btn_row, text="Restore this configuration",
                  command=_restore,
                  bg="#2255aa", fg="white",
                  font=("TkDefaultFont", 10, "bold"),
                  padx=10, pady=4).pack(side="left")
        tk.Button(btn_row, text="Close",
                  command=popup.destroy,
                  padx=10, pady=4).pack(side="right")

    # -------------------- Two-Phase Workflow --------------------

    def _announce_configuration(self) -> None:
        """Announce configuration to agents (can be called multiple times to refresh)."""
        print("[UI] ===== ANNOUNCING CONFIGURATION =====")
        print(f"[UI] Human assignments: {self._assignments}")
        print(f"[UI] Current phase: {self._phase}")

        # Store initial human configuration
        self._initial_configs["Human"] = dict(self._assignments)

        # Track whether this is the first announcement (before phase changes)
        _is_first_announce = (self._phase == "configure")

        # Transition to bargain phase and show panels BEFORE starting any LLM threads
        # so that panels appear immediately (empty with loading indicator) rather than
        # only becoming visible once the LLM has finished generating.
        if _is_first_announce:
            self._phase = "bargain"

            if getattr(self, '_rb_structured_mode', False):
                if hasattr(self, '_step1_button_container'):
                    self._step1_button_container.pack_forget()
                if hasattr(self, '_paned_window'):
                    paned = self._paned_window
                    if hasattr(self, '_middle_container'):
                        paned.add(self._middle_container, width=400, minsize=300)
                    if hasattr(self, '_conditionals_frame'):
                        paned.add(self._conditionals_frame, width=400, minsize=250)
                if hasattr(self, '_configure_container'):
                    self._configure_container.pack_forget()
                if hasattr(self, '_neighbor_panes'):
                    for neigh, pane in self._neighbor_panes.items():
                        pane.pack(fill="both", expand=False, pady=6)

            elif getattr(self, '_llm_rb_mode', False):
                if hasattr(self, '_step1_button_container'):
                    self._step1_button_container.pack_forget()
                if hasattr(self, '_paned_window') and hasattr(self, '_middle_container'):
                    paned = self._paned_window
                    paned.add(self._middle_container, width=400, minsize=300)
                if hasattr(self, '_configure_container'):
                    self._configure_container.pack_forget()
                if hasattr(self, '_neighbor_panes'):
                    for neigh, pane in self._neighbor_panes.items():
                        pane.pack(fill="both", expand=False, pady=6)

            else:
                if hasattr(self, '_step1_button_container'):
                    self._step1_button_container.pack_forget()
                if hasattr(self, '_paned_window') and hasattr(self, '_middle_container'):
                    paned = self._paned_window
                    paned.add(self._middle_container, width=400, minsize=300)
                if hasattr(self, '_conditionals_frame'):
                    paned.add(self._conditionals_frame, width=400, minsize=250)
                if hasattr(self, '_configure_container'):
                    self._configure_container.pack_forget()
                if hasattr(self, '_neighbor_panes'):
                    for neigh, pane in self._neighbor_panes.items():
                        pane.pack(fill="both", expand=False, pady=6)

            # Force geometry update so panels are rendered before LLM threads return
            if self._root:
                self._root.update_idletasks()

            # Add loading indicators immediately so panels show activity right away
            for neigh in self._neighs:
                self._start_transcript_loading(neigh)

        # Send special message to trigger agents to announce their configurations
        for neigh in self._neighs:
            if self._on_send:
                print(f"[UI] Requesting {neigh} to announce configuration...")

                def _threaded_announce(n=neigh):
                    try:
                        print(f"[UI] _threaded_announce starting for {n}")
                        # Set status: agent is computing initial configuration
                        self.update_agent_status(n, "computing initial configuration...")

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

                        # Clear status after response received
                        self.clear_agent_status(n)

                        if reply and self._root:
                            print(f"[UI] Adding reply to incoming for {n}")
                            self._root.after(0, lambda: self.add_incoming(n, reply))
                        else:
                            print(f"[UI] No reply received from {n}")
                    except Exception as e:
                        print(f"[UI] Error announcing config to {n}: {e}")
                        import traceback
                        traceback.print_exc()
                        # Clear status on error
                        self.clear_agent_status(n)

                import threading
                threading.Thread(target=_threaded_announce, daemon=True).start()

        # After agents announce, send human's configuration to them
        # Schedule this after a delay to let agent announcements complete
        def _send_human_announcements():
            print("[UI] Sending human announcements to agents...")
            for neigh in self._neighs:
                if self._on_send:
                    # Build human's announcement message
                    boundary_nodes = [n for n in self._assignments.keys()]
                    if boundary_nodes:
                        config_str = ", ".join(f"{n}={self._assignments[n]}" for n in sorted(boundary_nodes))
                        import json
                        human_announcement = f"Here's my configuration: {config_str} [report: {json.dumps(self._assignments)}]"

                        # Send in background thread to avoid UI freeze
                        def _threaded_human_announce(n=neigh, msg=human_announcement, cfg=config_str):
                            try:
                                print(f"[UI] Sending human announcement to {n}: {cfg}")
                                self.update_agent_status(n, "processing announcement...")
                                reply = self._on_send(n, msg)
                                self.clear_agent_status(n)
                                print(f"[UI] Got reply from {n}: {reply[:100] if reply else 'None'}...")
                                if reply and self._root:
                                    self._root.after(0, lambda: self.add_incoming(n, reply))
                            except Exception as e:
                                print(f"[UI] Error sending human announcement to {n}: {e}")
                                import traceback
                                traceback.print_exc()
                                self.clear_agent_status(n)

                        import threading
                        threading.Thread(target=_threaded_human_announce, daemon=True).start()

        # Schedule human announcement after 1 second (let agent announcements complete)
        if self._root:
            self._root.after(1000, _send_human_announcements)

        # On first announcement: update banner, sash positions, conditional builders.
        # Panel packing was already done above (before threads started).
        if _is_first_announce:
            # Update phase banner
            if self._phase_banner_label:
                self._phase_banner_label.config(
                    text="💬 STEP 2: BARGAINING - Negotiate with agents",
                    bg="#5cb85c"  # Green for bargain
                )
            if hasattr(self, '_impossible_btn'):
                self._impossible_btn.config(state="normal")

            # Set sash positions to enforce equal panel widths after transition
            if hasattr(self, '_paned_window'):
                def _set_sash_positions_after_transition():
                    try:
                        paned = self._paned_window
                        paned.update_idletasks()
                        total_width = paned.winfo_width()
                        if total_width > 100 and len(paned.panes()) >= 3:
                            paned.sash_place(0, int(total_width / 3), 0)
                            paned.sash_place(1, int(2 * total_width / 3), 0)
                            print(f"[UI] Set sash positions: {int(total_width / 3)}, {int(2 * total_width / 3)} (total: {total_width})")
                    except Exception as e:
                        print(f"[UI] Error setting sash positions: {e}")
                if self._root:
                    self._root.after(800, _set_sash_positions_after_transition)

            # Enable conditional builders and update help text
            for neigh in self._neighs:
                if neigh in self._rb_help_labels:
                    self._rb_help_labels[neigh].config(
                        text="BARGAIN PHASE: Build conditional offers: 'If they do X, I'll do Y' (both IF and THEN required)",
                        fg="#555"
                    )
                if hasattr(self, '_llm_rb_help_labels') and neigh in self._llm_rb_help_labels:
                    label = self._llm_rb_help_labels[neigh]
                    label.config(
                        text="BARGAIN PHASE: Type natural language messages (e.g., 'I think h1 should be red')",
                        fg="#555"
                    )
                    label.update_idletasks()
                if neigh in self._conditional_builder_frames:
                    frame = self._conditional_builder_frames[neigh]
                    def enable_frame(widget):
                        if hasattr(widget, 'config'):
                            try:
                                widget.config(state="normal")
                            except Exception:
                                pass
                        for child in widget.winfo_children():
                            enable_frame(child)
                    enable_frame(frame)

            # Disable auto-suggestion in announcement-based modes
            has_announcement = getattr(self, '_has_announcement_phase', False) or getattr(self, '_llm_rb_mode', False)
            if has_announcement:
                print("[AutoSuggest] Disabled in announcement-based modes - agents wait for human response")
                self._auto_suggest_enabled = False
            elif not self._auto_suggest_enabled:
                print("[AutoSuggest] Human announced - enabling auto-suggestions")
                self._auto_suggest_enabled = True
                self._schedule_auto_suggest()

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
        """Schedule debounced NL->RB translation for LLM_RB mode."""
        if self._root is None:
            return

        # Cancel existing debounce timer if any
        existing_id = self._llm_rb_debounce_ids.get(neigh)
        if existing_id:
            try:
                self._root.after_cancel(existing_id)
            except Exception:
                pass

        # Schedule new translation after 2.5 seconds of no typing
        new_id = self._root.after(2500, lambda: self._perform_llm_rb_translation(neigh))
        self._llm_rb_debounce_ids[neigh] = new_id

    def _perform_llm_rb_translation(self, neigh: str) -> None:
        """Perform NL->RB translation and update preview label."""
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
            node = getattr(rb_move, 'node', None)
            colour = getattr(rb_move, 'colour', None)

            # Handle Reject moves specially - show impossible_conditions
            if move_type == "Reject":
                parts = [f"-> Reject"]

                # Check for impossible_conditions
                impossible = getattr(rb_move, 'impossible_conditions', None)
                if impossible and isinstance(impossible, list) and len(impossible) > 0:
                    constraints = []
                    for item in impossible:
                        if isinstance(item, dict):
                            n = item.get('node', '?')
                            c = item.get('colour', '?')
                            constraints.append(f"{n}≠{c}")
                    if constraints:
                        parts.append(" [" + ", ".join(constraints) + "]")

                # Check for impossible_combinations
                combos = getattr(rb_move, 'impossible_combinations', None)
                if combos and isinstance(combos, list) and len(combos) > 0:
                    for combo in combos:
                        if isinstance(combo, list):
                            cond_strs = []
                            for item in combo:
                                if isinstance(item, dict):
                                    n = item.get('node', '?')
                                    c = item.get('colour', '?')
                                    cond_strs.append(f"{n}={c}")
                            if cond_strs:
                                parts.append(" [NOT " + " WHEN ".join(cond_strs) + "]")

                if len(parts) == 1:
                    parts.append(" (no constraints extracted)")

                return "".join(parts)

            # Handle ConditionalOffer - show conditions and assignments
            elif move_type == "ConditionalOffer":
                parts = [f"-> ConditionalOffer"]

                conditions = getattr(rb_move, 'conditions', None)
                if conditions and isinstance(conditions, list) and len(conditions) > 0:
                    cond_strs = []
                    for c in conditions:
                        if hasattr(c, 'node') and hasattr(c, 'colour'):
                            cond_strs.append(f"{c.node}={c.colour}")
                    if cond_strs:
                        parts.append(" IF [" + ", ".join(cond_strs) + "]")

                assignments = getattr(rb_move, 'assignments', None)
                if assignments and isinstance(assignments, list) and len(assignments) > 0:
                    assign_strs = []
                    for a in assignments:
                        if hasattr(a, 'node') and hasattr(a, 'colour'):
                            assign_strs.append(f"{a.node}={a.colour}")
                    if assign_strs:
                        parts.append(" THEN [" + ", ".join(assign_strs) + "]")

                return "".join(parts)

            # Handle Accept/Commit
            elif move_type in ("Accept", "Commit"):
                if node:
                    return f"-> {move_type}: {node}" + (f" = {colour}" if colour else "")
                return f"-> {move_type}"

            # Handle FeasibilityQuery
            elif move_type == "FeasibilityQuery":
                if node and colour:
                    return f"-> Query: {node} = {colour}"
                elif node:
                    return f"-> Query: {node}"
                return f"-> FeasibilityQuery"

            # Handle legacy moves
            elif move_type == "PROPOSE":
                if colour:
                    return f"-> PROPOSE: {node} = {colour}"
                return f"-> PROPOSE: {node}"
            elif move_type == "ATTACK":
                return f"-> ATTACK: {node}"
            elif move_type == "CONCEDE":
                if colour:
                    return f"-> CONCEDE: {node} = {colour}"
                return f"-> CONCEDE: {node}"

            # Generic fallback
            else:
                if node:
                    return f"-> {move_type}: {node}" + (f" = {colour}" if colour else "")
                return f"-> {move_type}"

        except Exception as e:
            return f"-> Parse error: {str(e)[:40]}"

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

    def _schedule_auto_suggest(self) -> None:
        """Schedule next auto-suggestion check."""
        if not self._auto_suggest_enabled or self._root is None:
            return

        # Use slower interval if agent recently sent an offer (give human time to read)
        import time
        current_time = time.time()
        use_slow_interval = any(
            current_time - offer_time < 12.0
            for offer_time in self._last_agent_offer_time.values()
        )

        interval = self._auto_suggest_slow_interval if use_slow_interval else self._auto_suggest_interval_ms

        self._auto_suggest_timer_id = self._root.after(
            interval,
            self._auto_suggest_tick
        )

    def _auto_suggest_tick(self) -> None:
        """Timer callback: trigger agent suggestions if not waiting for response."""
        if not self._auto_suggest_enabled:
            return

        # Check if human has pending offers/checks awaiting responses
        has_pending = self._has_pending_responses()

        if not has_pending:
            # No pending responses - safe to trigger agent suggestions
            print(f"[AutoSuggest] Triggering agent suggestions (no pending offers)")
            self._trigger_agent_suggestions()
        else:
            print(f"[AutoSuggest] Skipping - pending offers await response")

        # Schedule next tick
        self._schedule_auto_suggest()

    def _has_pending_responses(self) -> bool:
        """Check if human has sent offers/queries awaiting agent responses."""
        # Check feasibility queries without responses
        for neigh, queries in self._feasibility_queries.items():
            for query in queries:
                if query.get('is_feasible') is None:
                    # Query sent but no response received yet
                    print(f"[AutoSuggest] Pending feasibility query: {query.get('query_id')}")
                    return True

        # Check human's sent offers that haven't been accepted/rejected
        for offer in self._human_sent_offers:
            status = offer.get("status", "pending")
            if status == "pending":
                print(f"[AutoSuggest] Pending human offer: {offer.get('offer_id')}")
                return True

        return False

    def _trigger_agent_suggestions(self) -> None:
        """Trigger each agent to make a suggestion by calling their step()."""
        import time
        self._last_auto_suggest_time = time.time()

        for neigh in self._neighs:
            def _agent_step(n=neigh):
                try:
                    if self._on_send:
                        import inspect
                        sig = inspect.signature(self._on_send)
                        # Send __PASS__ token to trigger agent step without human message
                        if len(sig.parameters) >= 3:
                            reply = self._on_send(n, "__PASS__", dict(self._assignments))
                        else:
                            reply = self._on_send(n, "__PASS__")

                        if reply and self._root:
                            self._root.after(0, lambda: self.add_incoming(n, reply))
                except Exception as e:
                    print(f"[AutoSuggest] Error triggering {n}: {e}")
                    import traceback
                    traceback.print_exc()

            # Trigger in background thread
            threading.Thread(target=_agent_step, daemon=True).start()

    def _finish(self) -> None:
        # Stop auto-suggestion timer
        self._auto_suggest_enabled = False
        if self._auto_suggest_timer_id and self._root:
            try:
                self._root.after_cancel(self._auto_suggest_timer_id)
                print("[AutoSuggest] Timer cancelled")
            except:
                pass

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
