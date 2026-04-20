"""
ColourStudyWindow — the main per-attempt experiment window.

Handles both Mode 1 (Manual Collaborative) and Mode 2 (Autonomous Planning).
Constructed fresh for each attempt; calls on_attempt_complete when done.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional

from debug_log import dbg

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from study.config import StudyConfig
from study.session import SessionManager
from study.logger import StudyLogger
from problems.scoring import PointsScorer, ScoringResult
from agents.proposal_agent import ProposalAgent
from agents.planning_agent import Plan
from ui.graph_canvas import GraphCanvas, NeighborhoodCanvas
from ui.scoring_hud import ScoringHUD


class ColourStudyWindow:
    """
    Main experiment window for one attempt.

    Parameters
    ----------
    root:
        A Tk or Toplevel instance to use as the window.  If None, a new Tk
        is created.
    config:
        Study configuration.
    session:
        SessionManager (already reset for this attempt).
    scorer:
        PointsScorer built from config.
    logger:
        StudyLogger for the session.
    attempt_number:
        1-based attempt index.
    prior_attempts:
        Completed assignments from earlier attempts (may be empty).
    on_attempt_complete:
        Called with the final assignment dict when the human finishes.
    agents:
        List of ProposalAgents (Mode 1 only).
    plan:
        Pre-generated Plan (Mode 2 only).
    """

    def __init__(
        self,
        *,
        root: Optional["tk.Tk"] = None,
        config: StudyConfig,
        session: SessionManager,
        scorer: PointsScorer,
        logger: StudyLogger,
        attempt_number: int,
        prior_attempts: List[Dict[str, str]],
        on_attempt_complete: Callable[[Dict[str, str]], None],
        on_session_decision: Optional[Callable[[str], None]] = None,
        preloaded_assignment: Optional[Dict[str, str]] = None,
        can_replay: bool = True,
        agents: Optional[List[ProposalAgent]] = None,
        plan: Optional[Plan] = None,
    ) -> None:
        self._config = config
        self._session = session
        self._scorer = scorer
        self._logger = logger
        self._attempt = attempt_number
        self._prior_attempts = prior_attempts
        self._on_complete = on_attempt_complete
        self._on_session_decision = on_session_decision
        self._preloaded_assignment: Dict[str, str] = preloaded_assignment or {}
        self._can_replay = can_replay
        self._agents = agents or []
        self._plan = plan
        self._mode = config.mode    # "mode1" | "mode2a" | "mode2b"

        # Per-node state for current node
        self._agent_best_colours: Dict[str, str] = {}   # agent name → best colour (Mode 1)
        self._current_plan_step_index: int = 0
        self._explanation_clicked_this_node: bool = False
        self._attempt_start_time: float = time.time()

        # Build window
        if root is None:
            self._root = tk.Tk()
            self._owns_root = True
        else:
            self._root = root
            self._owns_root = False

        self._root.title(
            f"Graph Colouring — Attempt {attempt_number} of {config.max_attempts}"
        )
        self._root.minsize(1020, 660)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        cfg = self._config

        # Preferred colours for HUD (derived from the points config)
        pref_colours: Dict[str, str] = {}
        for ac in cfg.agent_configs:
            pref_colours[ac.name] = ac.preferred_colour
        human_pts = cfg.points_config.points_by_owner.get(cfg.human_name, {})
        pref_colours[cfg.human_name] = (
            max(human_pts, key=lambda c: human_pts.get(c, 0))
            if human_pts else cfg.colours[0]
        )

        participants = [cfg.human_name] + [ac.name for ac in cfg.agent_configs]

        # --- Top: HUD ---
        hud_frame = ttk.Frame(self._root, padding=4)
        hud_frame.pack(side=tk.TOP, fill=tk.X)

        attempt_lbl = ttk.Label(
            hud_frame,
            text=f"Attempt {self._attempt} of {cfg.max_attempts}",
            font=("TkDefaultFont", 10),
        )
        attempt_lbl.pack(side=tk.RIGHT, padx=8)

        self._hud = ScoringHUD(
            hud_frame,
            participants=participants,
            preferred_colours=pref_colours,
        )
        self._hud.pack(side=tk.LEFT)

        ttk.Separator(self._root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # --- Middle: left panel (overview + neighbourhood) + right interaction panel ---
        main_pane = ttk.PanedWindow(self._root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Left: stacked overview graph (small) + neighbourhood detail
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=3)

        ttk.Label(
            left_frame, text="Overview", font=("TkDefaultFont", 8, "italic"),
            foreground="#888888",
        ).pack(anchor="w", padx=4, pady=(2, 0))

        self._graph = GraphCanvas(
            left_frame,
            nodes=cfg.graph_def.nodes,
            edges=cfg.graph_def.edges,
            node_regions=cfg.node_regions,
            layout_preset=cfg.graph_def.layout_preset,
            on_node_click=None,
            width=440,
            height=280,
        )
        self._graph.pack(fill=tk.BOTH, expand=True)

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(2, 0))

        ttk.Label(
            left_frame, text="Current node", font=("TkDefaultFont", 8, "italic"),
            foreground="#888888",
        ).pack(anchor="w", padx=4)

        self._neighborhood = NeighborhoodCanvas(
            left_frame,
            node_regions=cfg.node_regions,
            layout_preset=cfg.graph_def.layout_preset,
            width=440,
            height=210,
        )
        self._neighborhood.pack(fill=tk.BOTH, expand=True)

        # Right: mode-specific interaction panel
        right_frame = ttk.Frame(main_pane, padding=8)
        main_pane.add(right_frame, weight=2)

        if self._mode == "mode1":
            self._build_mode1_panel(right_frame)
        else:
            self._build_mode2_panel(right_frame)

        # --- Bottom: node sequence bar ---
        seq_frame = ttk.Frame(self._root, padding=(4, 2))
        seq_frame.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Separator(self._root, orient=tk.HORIZONTAL).pack(side=tk.BOTTOM, fill=tk.X)
        self._build_sequence_bar(seq_frame)

        # Pre-load previous attempt's colouring so the human can see what was
        # chosen before.  Scheduled after initial layout so canvas coords exist.
        if self._preloaded_assignment:
            self._root.after(
                200,
                lambda a=self._preloaded_assignment: self._apply_preload(a),
            )

    def _apply_preload(self, assignment: Dict[str, str]) -> None:
        """Show the previous attempt's colours on the graph and sequence bar."""
        self._graph.set_all_assignments(assignment)
        for node, colour in assignment.items():
            lbl = self._seq_labels.get(node)
            if lbl:
                lbl.config(bg=self._colour_hex(colour), fg="#111111")

    def _build_sequence_bar(self, parent) -> None:
        """Breadcrumb bar showing all nodes in order."""
        ttk.Label(parent, text="Progress: ", font=("TkDefaultFont", 8)).pack(side=tk.LEFT)
        self._seq_labels: Dict[str, tk.Label] = {}
        for node in self._config.graph_def.node_order:
            lbl = tk.Label(
                parent,
                text=node,
                font=("TkDefaultFont", 8),
                bg="#dddddd",
                fg="#555555",
                relief="groove",
                padx=3,
                pady=1,
                width=3,
            )
            lbl.pack(side=tk.LEFT, padx=1)
            self._seq_labels[node] = lbl

    # ------------------------------------------------------------------
    # Mode 1 panel
    # ------------------------------------------------------------------

    def _build_mode1_panel(self, parent) -> None:
        """Per-node agent-proposal panel for Mode 1."""
        from ui.graph_canvas import _COLOUR_FILLS
        cfg = self._config

        # --- Your scoring key (always visible at top) ---
        human_pts = cfg.points_config.points_by_owner.get(cfg.human_name, {})
        best_colour = (max(human_pts, key=lambda c: human_pts.get(c, 0))
                       if human_pts else "")
        scoring_frame = ttk.LabelFrame(parent, text="Your rewards per node", padding=(8, 4))
        scoring_frame.pack(fill=tk.X, pady=(0, 10))
        chips_row = ttk.Frame(scoring_frame)
        chips_row.pack(fill=tk.X)
        for colour in cfg.colours:
            pts = human_pts.get(colour, 0)
            is_best = (colour == best_colour)
            col_cell = ttk.Frame(chips_row, padding=(0, 0, 16, 0))
            col_cell.pack(side=tk.LEFT)
            chip = tk.Canvas(col_cell, width=20, height=20,
                             bg=_COLOUR_FILLS.get(colour, "#dddddd"),
                             highlightthickness=1, highlightbackground="#888888")
            chip.pack(side=tk.LEFT, padx=(0, 5))
            suffix = "  (best)" if is_best else ""
            ttk.Label(
                col_cell,
                text=f"{colour.capitalize()} = {pts} pt{'s' if pts != 1 else ''}{suffix}",
                font=("TkDefaultFont", 11, "bold" if is_best else "normal"),
                foreground="#006600" if is_best else "#444444",
            ).pack(side=tk.LEFT)

        ttk.Label(
            parent,
            text="Agent Score Predictions",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            parent,
            text="For each colour you could pick, agents with an adjacent node show "
                 "their best possible total score if they respond optimally.",
            wraplength=320,
            font=("TkDefaultFont", 11),
            foreground="#444444",
        ).pack(anchor="w", pady=(0, 8))

        # Current node indicator
        self._current_node_var = tk.StringVar(value="—")
        node_frame = ttk.Frame(parent)
        node_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(node_frame, text="Current node:", font=("TkDefaultFont", 11)).pack(side=tk.LEFT)
        ttk.Label(
            node_frame,
            textvariable=self._current_node_var,
            font=("TkDefaultFont", 13, "bold"),
        ).pack(side=tk.LEFT, padx=6)

        # Predictions table (populated dynamically)
        self._proposals_frame = ttk.LabelFrame(parent, text="Agent predictions", padding=6)
        self._proposals_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        # Colour choice buttons (kept at the bottom, always visible)
        choice_frame = ttk.LabelFrame(parent, text="Your choice", padding=6)
        choice_frame.pack(fill=tk.X, pady=(4, 0))
        self._colour_buttons: Dict[str, ttk.Button] = {}
        for colour in self._config.colours:
            btn = ttk.Button(
                choice_frame,
                text=colour.capitalize(),
                command=lambda c=colour: self._on_human_choice_mode1(c),
                state=tk.DISABLED,
                width=12,
            )
            btn.pack(side=tk.LEFT, padx=6)
            self._colour_buttons[colour] = btn

    def _refresh_mode1_node(self) -> None:
        """Populate score predictions and enable buttons for the current node."""
        node = self._session.current_node
        if node is None:
            return
        self._current_node_var.set(node)
        self._refresh_neighborhood(node)

        # Clear old content
        for child in self._proposals_frame.winfo_children():
            child.destroy()

        current_assignment = self._session.assignment_so_far
        node_order = self._config.graph_def.node_order
        colours = self._config.colours

        # Use grid for reliable column alignment
        grid = ttk.Frame(self._proposals_frame)
        grid.pack(fill=tk.X, padx=4, pady=4)

        # Header row
        ttk.Label(grid, text="Agent", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 16), pady=(0, 4)
        )
        for col_idx, colour in enumerate(colours, start=1):
            ttk.Label(
                grid,
                text=colour.capitalize(),
                font=("TkDefaultFont", 10, "bold"),
                foreground="#333333",
            ).grid(row=0, column=col_idx, sticky="w", padx=12, pady=(0, 4))

        ttk.Separator(self._proposals_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=4)

        # Find which agents have at least one node directly adjacent to current node
        edges = self._config.graph_def.edges
        neighbours: set[str] = set()
        for u, v in edges:
            if u == node:
                neighbours.add(v)
            elif v == node:
                neighbours.add(u)

        adjacent_agents = [
            a for a in self._agents
            if any(
                self._config.node_regions.get(n) == a.name
                for n in neighbours
            )
        ]

        # One row per adjacent agent
        self._agent_best_colours = {}
        for row_idx, agent in enumerate(adjacent_agents, start=1):
            scores = agent.best_response_scores(
                current_node=node,
                node_order=node_order,
                edges=edges,
                current_assignment=current_assignment,
                node_regions=self._config.node_regions,
            )
            best = max(colours, key=lambda c: scores.get(c, 0))
            self._agent_best_colours[agent.name] = best

            ttk.Label(
                grid,
                text=agent.name,
                font=("TkDefaultFont", 10, "bold"),
            ).grid(row=row_idx, column=0, sticky="w", padx=(0, 16), pady=3)

            for col_idx, colour in enumerate(colours, start=1):
                pts = scores.get(colour, 0)
                is_best = (colour == best)
                ttk.Label(
                    grid,
                    text=f"{pts} pts" + ("  ★" if is_best else ""),
                    font=("TkDefaultFont", 10, "bold" if is_best else "normal"),
                    foreground="#006600" if is_best else "#444444",
                ).grid(row=row_idx, column=col_idx, sticky="w", padx=12, pady=3)

        if not adjacent_agents:
            ttk.Label(
                self._proposals_frame,
                text="No agent has a node adjacent to this one.",
                font=("TkDefaultFont", 10),
                foreground="#888888",
            ).pack(anchor="w", padx=4, pady=4)

        # Log which colour each adjacent agent most prefers
        self._logger.log_proposals_shown(
            attempt=self._attempt,
            node=node,
            proposals=[
                {"agent": a.name, "colour": self._agent_best_colours.get(a.name, "")}
                for a in adjacent_agents
            ],
        )

        # Enable colour buttons
        for btn in self._colour_buttons.values():
            btn.config(state=tk.NORMAL)

    def _on_human_choice_mode1(self, colour: str) -> None:
        node = self._session.current_node
        if node is None:
            return

        # Disable buttons immediately to prevent accidental double-clicks
        for btn in self._colour_buttons.values():
            btn.config(state=tk.DISABLED)

        # agents_agreed: True if majority of agents' preferred colour matches choice
        if self._agents:
            agreed_count = sum(
                1 for a in self._agents
                if self._agent_best_colours.get(a.name) == colour
            )
            majority = agreed_count > len(self._agents) / 2
        else:
            majority = False

        decision = self._session.record_decision(
            colour=colour,
            source="human",
            explanation_clicked=False,
            agents_agreed=majority,
        )
        self._logger.log_colour_chosen(
            attempt=self._attempt,
            node=node,
            colour=colour,
            source="human",
            decision_time_s=decision.decision_time_s,
            agents_agreed=majority,
        )

        self._post_decision(node, colour)

        if not self._session.is_complete:
            # Brief pause so the human can see their colour applied before agents fire
            self._root.after(200, self._advance_to_next_human_node)
        else:
            self._finish_attempt()

    # ------------------------------------------------------------------
    # Mode 2 panel
    # ------------------------------------------------------------------

    def _build_mode2_panel(self, parent) -> None:
        """Step-by-step plan presentation panel for Mode 2."""
        ttk.Label(
            parent,
            text="Autonomous Plan",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            parent,
            text="The assistant has proposed a complete colouring plan. "
                 "You can accept, request an explanation, or modify each step.",
            wraplength=320,
            font=("TkDefaultFont", 11),
            foreground="#444444",
        ).pack(anchor="w", pady=(0, 8))

        # Current step display
        step_frame = ttk.LabelFrame(parent, text="Current step", padding=8)
        step_frame.pack(fill=tk.X, pady=4)

        step_top = ttk.Frame(step_frame)
        step_top.pack(fill=tk.X)
        ttk.Label(step_top, text="Node:", font=("TkDefaultFont", 11)).pack(side=tk.LEFT)
        self._plan_node_var = tk.StringVar(value="—")
        ttk.Label(
            step_top, textvariable=self._plan_node_var,
            font=("TkDefaultFont", 13, "bold"),
        ).pack(side=tk.LEFT, padx=6)
        ttk.Label(step_top, text="  Proposed colour:", font=("TkDefaultFont", 11)).pack(side=tk.LEFT)
        self._plan_colour_var = tk.StringVar(value="—")
        self._plan_colour_lbl = ttk.Label(
            step_top, textvariable=self._plan_colour_var,
            font=("TkDefaultFont", 13, "bold"),
        )
        self._plan_colour_lbl.pack(side=tk.LEFT, padx=6)

        self._plan_rationale_var = tk.StringVar(value="")
        ttk.Label(
            step_frame,
            textvariable=self._plan_rationale_var,
            wraplength=310,
            font=("TkDefaultFont", 11),
            foreground="#222222",
        ).pack(anchor="w", pady=(6, 0))

        # Inline explanation panel (hidden by default, toggled by Explain button)
        self._plan_explain_frame = ttk.Frame(step_frame)
        self._plan_explain_text: Optional[tk.Text] = None
        # Not packed yet

        # Action buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=6)
        self._accept_btn = ttk.Button(
            btn_frame, text="Accept", width=11,
            command=self._on_plan_accept,
        )
        self._accept_btn.pack(side=tk.LEFT, padx=3)
        self._explain_btn = ttk.Button(
            btn_frame, text="▸ Explain", width=11,
            command=self._on_plan_explain,
        )
        self._explain_btn.pack(side=tk.LEFT, padx=3)

        # Modify sub-frame (hidden by default)
        self._modify_frame = ttk.LabelFrame(parent, text="Choose a different colour", padding=6)
        self._modify_buttons: Dict[str, ttk.Button] = {}
        for colour in self._config.colours:
            btn = ttk.Button(
                self._modify_frame,
                text=colour.capitalize(),
                width=11,
                command=lambda c=colour: self._on_plan_modify(c),
            )
            btn.pack(side=tk.LEFT, padx=4)
            self._modify_buttons[colour] = btn
        ttk.Button(
            self._modify_frame, text="Cancel", width=8,
            command=self._hide_modify_frame,
        ).pack(side=tk.LEFT, padx=3)

        modify_toggle_btn = ttk.Button(
            btn_frame, text="Modify", width=11,
            command=self._toggle_modify_frame,
        )
        modify_toggle_btn.pack(side=tk.LEFT, padx=3)

        # Deliberation log (collapsible)
        delib_frame = ttk.Frame(parent)
        delib_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self._delib_expanded = tk.BooleanVar(value=False)
        delib_toggle = ttk.Checkbutton(
            delib_frame,
            text="How was this plan made?",
            variable=self._delib_expanded,
            command=self._toggle_delib_log,
        )
        delib_toggle.pack(anchor="w")
        self._delib_text_frame = ttk.Frame(delib_frame)
        # Not packed yet — shown only when expanded

    def _toggle_delib_log(self) -> None:
        if self._delib_expanded.get():
            self._logger.log_deliberation_log_opened(self._attempt)
            if not hasattr(self, "_delib_text"):
                self._delib_text = tk.Text(
                    self._delib_text_frame,
                    wrap="word",
                    font=("Courier", 8),
                    height=10,
                    state=tk.DISABLED,
                )
                scroll = ttk.Scrollbar(
                    self._delib_text_frame, command=self._delib_text.yview
                )
                self._delib_text.config(yscrollcommand=scroll.set)
                self._delib_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scroll.pack(side=tk.RIGHT, fill=tk.Y)
                # Populate
                if self._plan:
                    self._delib_text.config(state=tk.NORMAL)
                    self._delib_text.insert("1.0", "\n".join(self._plan.deliberation_log))
                    self._delib_text.config(state=tk.DISABLED)
            self._delib_text_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self._delib_text_frame.pack_forget()

    def _toggle_modify_frame(self) -> None:
        if self._modify_frame.winfo_ismapped():
            self._hide_modify_frame()
        else:
            self._modify_frame.pack(fill=tk.X, pady=4)

    def _hide_modify_frame(self) -> None:
        self._modify_frame.pack_forget()

    def _refresh_mode2_step(self) -> None:
        """Update the panel to show the current plan step."""
        if self._plan is None:
            return
        idx = self._current_plan_step_index
        if idx >= len(self._plan.steps):
            return
        step = self._plan.steps[idx]
        node = step.node
        self._refresh_neighborhood(node)

        # Collapse inline explanation from previous step
        if hasattr(self, "_plan_explain_frame") and self._plan_explain_frame.winfo_ismapped():
            self._plan_explain_frame.pack_forget()
            self._explain_btn.config(text="▸ Explain")

        self._plan_node_var.set(node)
        self._plan_colour_var.set(step.colour.capitalize())
        self._plan_rationale_var.set(step.rationale_short)
        self._hide_modify_frame()
        self._explanation_clicked_this_node = False

        self._logger.log_plan_step_shown(
            attempt=self._attempt,
            node=node,
            plan_colour=step.colour,
        )

    def _on_plan_accept(self) -> None:
        if self._plan is None:
            return
        idx = self._current_plan_step_index
        if idx >= len(self._plan.steps):
            return
        step = self._plan.steps[idx]
        node = step.node
        colour = step.colour

        self._logger.log_plan_accepted(self._attempt, node)
        decision = self._session.record_decision(
            colour=colour,
            source="accepted_plan",
            explanation_clicked=self._explanation_clicked_this_node,
            agents_agreed=True,
        )
        self._logger.log_colour_chosen(
            attempt=self._attempt,
            node=node,
            colour=colour,
            source="accepted_plan",
            decision_time_s=decision.decision_time_s,
            agents_agreed=True,
        )
        self._post_decision(node, colour)
        self._advance_plan()

    def _on_plan_explain(self) -> None:
        if self._plan is None:
            return
        idx = self._current_plan_step_index
        if idx >= len(self._plan.steps):
            return
        step = self._plan.steps[idx]

        # Toggle the inline explanation panel
        if self._plan_explain_frame.winfo_ismapped():
            self._plan_explain_frame.pack_forget()
            self._explain_btn.config(text="▸ Explain")
            return

        self._logger.log_plan_explanation_clicked(self._attempt, step.node)
        self._explanation_clicked_this_node = True

        # Populate (or repopulate) the text widget
        if self._plan_explain_text is None:
            self._plan_explain_text = tk.Text(
                self._plan_explain_frame,
                wrap="word",
                font=("TkDefaultFont", 11),
                height=7,
                padx=6, pady=4,
                state=tk.DISABLED,
                relief="flat",
                bg="#f4f4f4",
            )
            self._plan_explain_text.pack(fill=tk.X)
        self._plan_explain_text.config(state=tk.NORMAL)
        self._plan_explain_text.delete("1.0", tk.END)
        self._plan_explain_text.insert("1.0", step.rationale_full)
        self._plan_explain_text.config(state=tk.DISABLED)

        self._plan_explain_frame.pack(fill=tk.X, pady=(6, 0))
        self._explain_btn.config(text="▾ Explain")

    def _on_plan_modify(self, colour: str) -> None:
        if self._plan is None:
            return
        idx = self._current_plan_step_index
        if idx >= len(self._plan.steps):
            return
        step = self._plan.steps[idx]
        node = step.node
        plan_colour = step.colour

        self._logger.log_plan_modified(self._attempt, node, plan_colour, colour)
        decision = self._session.record_decision(
            colour=colour,
            source="modified_plan",
            explanation_clicked=self._explanation_clicked_this_node,
            agents_agreed=False,
        )
        self._logger.log_colour_chosen(
            attempt=self._attempt,
            node=node,
            colour=colour,
            source="modified_plan",
            decision_time_s=decision.decision_time_s,
            agents_agreed=False,
        )
        self._hide_modify_frame()
        self._post_decision(node, colour)
        self._advance_plan()

    def _advance_plan(self) -> None:
        self._current_plan_step_index += 1
        if self._session.is_complete:
            self._finish_attempt()
        else:
            self._root.after(200, self._advance_to_next_human_plan_step)

    def _advance_to_next_human_plan_step(self) -> None:
        """
        Walk the plan forward, auto-applying agent-owned steps with a brief visual
        pause between each, until we reach a Human node or the end.
        """
        node = self._session.current_node
        if node is None:
            self._finish_attempt()
            return

        self._session.mark_node_ready()
        self._logger.log_node_ready(self._attempt, node, self._session.current_index)

        region = self._config.node_regions.get(node, "")
        if region == self._config.human_name:
            self._refresh_mode2_step()
        else:
            self._auto_apply_plan_step(node)
            if self._session.is_complete:
                self._root.after(300, self._finish_attempt)
            else:
                self._root.after(500, self._advance_to_next_human_plan_step)

    def _auto_apply_plan_step(self, node: str) -> None:
        """Apply the plan's colour for an agent-owned node without human interaction."""
        if self._plan is None or self._current_plan_step_index >= len(self._plan.steps):
            return
        step = self._plan.steps[self._current_plan_step_index]
        colour = step.colour

        decision = self._session.record_decision(
            colour=colour,
            source="agent_auto",
            explanation_clicked=False,
            agents_agreed=True,
        )
        self._logger.log_colour_chosen(
            attempt=self._attempt,
            node=node,
            colour=colour,
            source="agent_auto",
            decision_time_s=decision.decision_time_s,
            agents_agreed=True,
        )
        self._post_decision(node, colour)
        self._current_plan_step_index += 1

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _advance_to_next_human_node(self) -> None:
        """
        Walk the node sequence forward, auto-colouring agent-owned nodes with a
        short visual pause between each, until we reach a Human node or the end.
        """
        node = self._session.current_node
        dbg(f"  _advance_to_next_human_node: attempt={self._attempt} current_node={node} idx={self._session.current_index}")
        if node is None:
            dbg(f"  _advance_to_next_human_node: node is None → calling _finish_attempt")
            self._finish_attempt()
            return

        region = self._config.node_regions.get(node, "")

        if region == self._config.human_name:
            # Human's turn — start timer and show proposals
            dbg(f"  _advance_to_next_human_node: {node} is Human — enabling buttons")
            self._session.mark_node_ready()
            self._logger.log_node_ready(
                self._attempt, node, self._session.current_index
            )
            self._refresh_mode1_node()
        else:
            # Agent auto-colours this node, then immediately finish if done,
            # otherwise schedule the next step after a brief visual pause
            dbg(f"  _advance_to_next_human_node: {node} is agent ({region}) — auto-colouring")
            self._auto_colour_agent_node(node, region)
            if self._session.is_complete:
                dbg(f"  _advance_to_next_human_node: session complete after {node} — scheduling _finish_attempt")
                self._root.after(300, self._finish_attempt)
            else:
                self._root.after(500, self._advance_to_next_human_node)

    def _auto_colour_agent_node(self, node: str, region: str) -> None:
        """
        Auto-colour an agent-owned node using that agent's own best colour choice.
        Updates the graph display and logs the decision.
        """
        agent = next((a for a in self._agents if a.name == region), None)
        if agent is not None:
            colour = agent.colour_own_node(
                node=node,
                current_assignment=self._session.assignment_so_far,
                edges=self._config.graph_def.edges,
            )
        else:
            colour = self._config.colours[0]

        self._session.mark_node_ready()
        self._logger.log_node_ready(self._attempt, node, self._session.current_index)

        decision = self._session.record_decision(
            colour=colour,
            source=f"agent_auto",
            explanation_clicked=False,
            agents_agreed=True,
        )
        self._logger.log_colour_chosen(
            attempt=self._attempt,
            node=node,
            colour=colour,
            source=f"agent_auto",
            decision_time_s=decision.decision_time_s,
            agents_agreed=True,
        )

        # Update visuals
        self._graph.set_assignment(node, colour)
        self._graph.highlight_current_node(self._session.current_node)
        lbl = self._seq_labels.get(node)
        if lbl:
            lbl.config(bg=self._colour_hex(colour), fg="#111111")
        score = self._scorer.score_assignment(self._session.assignment_so_far)
        self._hud.update(score)

    def _refresh_neighborhood(self, node: str) -> None:
        """Rebuild the neighbourhood detail panel for *node* and highlight in overview."""
        edges = self._config.graph_def.edges
        neighbors: List[str] = []
        for u, v in edges:
            if u == node and v not in neighbors:
                neighbors.append(v)
            elif v == node and u not in neighbors:
                neighbors.append(u)
        visible = {node} | set(neighbors)
        sub_edges = [(u, v) for u, v in edges if u in visible and v in visible]
        # Highlight the neighbourhood in the overview
        self._graph.set_neighbourhood_highlight(visible)
        self._neighborhood.update_view(
            current_node=node,
            neighbors=neighbors,
            assignments=self._session.assignment_so_far,
            edges=sub_edges,
        )

    def _colour_hex(self, colour: str) -> str:
        from ui.graph_canvas import _COLOUR_FILLS, _UNCOLOURED_FILL
        return _COLOUR_FILLS.get(colour.lower(), _UNCOLOURED_FILL)

    def _post_decision(self, node: str, colour: str) -> None:
        """Update graph and score display after any colour decision."""
        self._graph.set_assignment(node, colour)
        self._graph.highlight_current_node(self._session.current_node)

        # Update sequence bar
        lbl = self._seq_labels.get(node)
        if lbl:
            lbl.config(bg=self._colour_hex(colour), fg="#111111")

        # Update score HUD
        score = self._scorer.score_assignment(self._session.assignment_so_far)
        self._hud.update(score)

    def _finish_attempt(self) -> None:
        """Called when all nodes have been coloured."""
        dbg(f"  _finish_attempt() called — attempt={self._attempt}, nodes_decided={self._session.current_index}")
        elapsed = time.time() - self._attempt_start_time
        final_assignment = self._session.assignment_so_far
        final_score = self._scorer.score_assignment(final_assignment)
        dbg(f"  _finish_attempt: {len(final_assignment)} nodes, score={final_score.total}")

        self._logger.log_attempt_complete(
            attempt=self._attempt,
            assignment=final_assignment,
            score=final_score,
            elapsed_s=elapsed,
        )

        self._on_complete(final_assignment)
        dbg(f"  _finish_attempt: _on_complete called, showing end panel")
        self._show_end_panel(final_assignment, final_score)

    def _show_end_panel(self, final_assignment: Dict[str, str], final_score) -> None:
        """Replace the colouring UI with an inline results panel."""
        dbg(f"  _show_end_panel: attempt={self._attempt}")

        # From here, X = finish session (not abandon — attempt IS complete)
        self._root.protocol("WM_DELETE_WINDOW", self._on_session_finish)

        # Clear the existing colouring UI
        for child in list(self._root.winfo_children()):
            child.destroy()

        cfg = self._config

        # Title
        ttk.Label(
            self._root,
            text=f"Attempt {self._attempt} of {cfg.max_attempts} Complete",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(pady=(14, 4))

        # Main: graph on left, scores on right
        content = ttk.Frame(self._root)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        graph_frame = ttk.LabelFrame(content, text="Final colouring", padding=4)
        graph_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        end_graph = GraphCanvas(
            graph_frame,
            nodes=cfg.graph_def.nodes,
            edges=cfg.graph_def.edges,
            node_regions=cfg.node_regions,
            layout_preset=cfg.graph_def.layout_preset,
            width=340,
            height=300,
        )
        end_graph.pack(fill=tk.BOTH, expand=True)
        self._root.after(80, lambda: end_graph.set_all_assignments(final_assignment))

        score_frame = ttk.LabelFrame(content, text="Scores", padding=8)
        score_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_end_score_table(score_frame, final_score)

        # Score trajectory (if more than one attempt done)
        all_attempts = list(self._prior_attempts) + [final_assignment]
        if len(all_attempts) > 1:
            traj_frame = ttk.LabelFrame(self._root, text="Score history", padding=6)
            traj_frame.pack(fill=tk.X, padx=10, pady=(0, 4))
            scores = [self._scorer.score_assignment(a).total for a in all_attempts]
            best = max(scores)
            for i, s in enumerate(scores, 1):
                marker = " ◀ this attempt" if i == len(scores) else ""
                star = " ★" if s == best else ""
                ttk.Label(
                    traj_frame,
                    text=f"Attempt {i}: {s} pts{marker}{star}",
                    font=("TkDefaultFont", 9, "bold" if i == len(scores) else "normal"),
                ).pack(side=tk.LEFT, padx=8)

        # Buttons
        btn_frame = ttk.Frame(self._root, padding=(0, 10))
        btn_frame.pack(side=tk.BOTTOM)

        if self._can_replay:
            ttk.Button(
                btn_frame,
                text="Start Next Attempt",
                command=self._on_session_continue,
                width=20,
            ).pack(side=tk.LEFT, padx=6)

        ttk.Button(
            btn_frame,
            text="Finish Session",
            command=self._on_session_finish,
            width=14,
        ).pack(side=tk.LEFT, padx=6)

    def _build_end_score_table(self, parent, score) -> None:
        cfg = self._config
        participants = [cfg.human_name] + [ac.name for ac in cfg.agent_configs]

        pref_colours: Dict[str, str] = {ac.name: ac.preferred_colour for ac in cfg.agent_configs}
        human_pts = cfg.points_config.points_by_owner.get(cfg.human_name, {})
        pref_colours[cfg.human_name] = (
            max(human_pts, key=lambda c: human_pts.get(c, 0)) if human_pts else "—"
        )

        ttk.Label(parent, text="Participant", font=("TkDefaultFont", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=4)
        ttk.Label(parent, text="Prefers", font=("TkDefaultFont", 9, "bold")).grid(
            row=0, column=1, sticky="w", padx=4)
        ttk.Label(parent, text="Score", font=("TkDefaultFont", 9, "bold")).grid(
            row=0, column=2, sticky="e", padx=4)
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=2)

        for i, p in enumerate(participants, start=2):
            pref = pref_colours.get(p, "—")
            pts = score.by_owner.get(p, 0)
            ttk.Label(parent, text=p).grid(row=i, column=0, sticky="w", padx=4)
            ttk.Label(parent, text=pref.capitalize()).grid(row=i, column=1, sticky="w", padx=4)
            ttk.Label(parent, text=str(pts), font=("TkDefaultFont", 10, "bold")).grid(
                row=i, column=2, sticky="e", padx=4)

        sep_row = len(participants) + 2
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=sep_row, column=0, columnspan=3, sticky="ew", pady=2)
        ttk.Label(parent, text="SHARED TOTAL", font=("TkDefaultFont", 9, "bold")).grid(
            row=sep_row + 1, column=0, columnspan=2, sticky="w", padx=4)
        ttk.Label(
            parent,
            text=str(score.total),
            font=("TkDefaultFont", 14, "bold"),
            foreground="#225511",
        ).grid(row=sep_row + 1, column=2, sticky="e", padx=4)

    def _on_session_continue(self) -> None:
        dbg(f"  _on_session_continue clicked (attempt={self._attempt})")
        if self._on_session_decision:
            self._on_session_decision("continue")

    def _on_session_finish(self) -> None:
        dbg(f"  _on_session_finish called (attempt={self._attempt})")
        if self._on_session_decision:
            self._on_session_decision("finish")
        else:
            self._root.destroy()

    def _on_close(self) -> None:
        """Window closed by user during colouring (abandonment)."""
        idx, total = self._session.progress
        dbg(f"  _on_close: attempt={self._attempt}, idx={idx}/{total} — abandonment")
        self._logger.log_abandonment(self._attempt, idx, reason="window_closed")
        if self._on_session_decision:
            self._on_session_decision("abandon")
        else:
            self._root.destroy()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Display the window and start the Tk event loop.

        Blocks until the attempt completes or the window is closed.
        """
        self._logger.log_attempt_start(self._attempt)

        if self._mode == "mode1":
            # Disable buttons until proposals are shown; advance handles mark_node_ready
            for btn in self._colour_buttons.values():
                btn.config(state=tk.DISABLED)
            self._root.after(100, self._advance_to_next_human_node)
        else:
            self._root.after(100, self._advance_to_next_human_plan_step)

        if self._owns_root:
            self._root.mainloop()
