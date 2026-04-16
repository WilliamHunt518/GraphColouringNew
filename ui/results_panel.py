"""
AttemptResultsWindow — shown at the end of each attempt.

Displays the final colouring, score breakdown across all attempts,
and offers "Play Again" / "Finish" buttons.
"""
from __future__ import annotations

from typing import Dict, List, Optional

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from study.config import StudyConfig
from problems.scoring import PointsScorer, ScoringResult
from ui.graph_canvas import GraphCanvas
from debug_log import dbg


class AttemptResultsWindow:
    """
    Modal results window for one completed attempt.

    Parameters
    ----------
    parent:
        Parent Tk window.
    config:
        Study configuration.
    scorer:
        PointsScorer instance.
    attempt_number:
        Just-completed attempt number (1-based).
    all_attempts:
        All completed assignments so far (including this one).
    can_replay:
        Whether a "Play Again" button should be shown.
    """

    def __init__(
        self,
        parent,
        *,
        config: StudyConfig,
        scorer: PointsScorer,
        attempt_number: int,
        all_attempts: List[Dict[str, str]],
        can_replay: bool,
    ) -> None:
        self._parent = parent
        self._config = config
        self._scorer = scorer
        self._attempt = attempt_number
        self._all_attempts = all_attempts
        self._can_replay = can_replay
        # Default to continuing if it's not the last attempt; only the last
        # attempt's explicit "Finish Session" click sets this to False.
        self._replay_requested: bool = can_replay

        dbg(f"AttemptResultsWindow.__init__: attempt={attempt_number} can_replay={can_replay}")
        self._win = tk.Toplevel(parent)
        self._win.title(f"Attempt {attempt_number} Complete")
        self._win.geometry("700x520")
        self._win.transient(parent)
        self._win.grab_set()
        self._win.protocol("WM_DELETE_WINDOW", self._on_finish)
        dbg(f"  results win created, grab_set done, building UI")
        self._build()
        dbg(f"  results _build() done, window ready")

    # ------------------------------------------------------------------

    def _build(self) -> None:
        cfg = self._config
        current_assignment = self._all_attempts[-1]
        current_score = self._scorer.score_assignment(current_assignment)

        # --- Title ---
        ttk.Label(
            self._win,
            text=f"Attempt {self._attempt} Results",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(pady=(12, 4))

        # --- Main content: graph on left, scores on right ---
        content = ttk.Frame(self._win)
        content.pack(fill=tk.BOTH, expand=True, padx=10)

        # Graph with final colouring
        graph_frame = ttk.LabelFrame(content, text="Final colouring", padding=4)
        graph_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        graph = GraphCanvas(
            graph_frame,
            nodes=cfg.graph_def.nodes,
            edges=cfg.graph_def.edges,
            node_regions=cfg.node_regions,
            layout_preset=cfg.graph_def.layout_preset,
            width=340,
            height=300,
        )
        graph.pack(fill=tk.BOTH, expand=True)
        self._win.after(80, lambda: graph.set_all_assignments(current_assignment))

        # Score table
        score_frame = ttk.LabelFrame(content, text="Scores", padding=8)
        score_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_score_table(score_frame, current_score)

        # --- Attempt trajectory (if > 1 attempt) ---
        if len(self._all_attempts) > 1:
            self._build_trajectory(self._win)

        # --- Buttons ---
        btn_frame = ttk.Frame(self._win, padding=(0, 8))
        btn_frame.pack(side=tk.BOTTOM)

        if self._can_replay:
            ttk.Button(
                btn_frame,
                text="Continue to Next Attempt",
                command=self._on_replay,
                width=22,
            ).pack(side=tk.LEFT, padx=6)
        else:
            ttk.Button(
                btn_frame,
                text="Finish Session",
                command=self._on_finish,
                width=14,
            ).pack(side=tk.LEFT, padx=6)

    def _build_score_table(self, parent, score: ScoringResult) -> None:
        cfg = self._config
        participants = [cfg.human_name] + [ac.name for ac in cfg.agent_configs]

        # Header
        ttk.Label(parent, text="Participant", font=("TkDefaultFont", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=4
        )
        ttk.Label(parent, text="Prefers", font=("TkDefaultFont", 9, "bold")).grid(
            row=0, column=1, sticky="w", padx=4
        )
        ttk.Label(parent, text="Score", font=("TkDefaultFont", 9, "bold")).grid(
            row=0, column=2, sticky="e", padx=4
        )
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=2
        )

        # Per-participant rows
        pref_colours: Dict[str, str] = {}
        for ac in cfg.agent_configs:
            pref_colours[ac.name] = ac.preferred_colour
        pref_colours[cfg.human_name] = cfg.colours[0]

        for i, p in enumerate(participants, start=2):
            pref = pref_colours.get(p, "—")
            pts = score.by_owner.get(p, 0)
            ttk.Label(parent, text=p).grid(row=i, column=0, sticky="w", padx=4)
            ttk.Label(parent, text=pref.capitalize()).grid(row=i, column=1, sticky="w", padx=4)
            ttk.Label(parent, text=str(pts), font=("TkDefaultFont", 10, "bold")).grid(
                row=i, column=2, sticky="e", padx=4
            )

        # Clash penalty row (if any)
        sep_row = len(participants) + 2
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=sep_row, column=0, columnspan=3, sticky="ew", pady=2
        )
        next_row = sep_row + 1
        if score.clash_count > 0:
            penalty_per = self._config.points_config.clash_penalty
            total_deduction = score.clash_count * penalty_per
            clash_label = (
                f"{score.clash_count} clash{'es' if score.clash_count != 1 else ''}"
            )
            ttk.Label(
                parent, text=clash_label, foreground="#aa2200",
                font=("TkDefaultFont", 9),
            ).grid(row=next_row, column=0, columnspan=2, sticky="w", padx=4)
            ttk.Label(
                parent, text=f"−{total_deduction}", foreground="#aa2200",
                font=("TkDefaultFont", 10, "bold"),
            ).grid(row=next_row, column=2, sticky="e", padx=4)
            next_row += 1

        ttk.Label(parent, text="SHARED TOTAL", font=("TkDefaultFont", 9, "bold")).grid(
            row=next_row, column=0, columnspan=2, sticky="w", padx=4
        )
        ttk.Label(
            parent,
            text=str(score.total),
            font=("TkDefaultFont", 14, "bold"),
            foreground="#225511",
        ).grid(row=next_row, column=2, sticky="e", padx=4)

    def _build_trajectory(self, parent) -> None:
        """Show attempt-by-attempt score history."""
        traj_frame = ttk.LabelFrame(parent, text="Score history", padding=6)
        traj_frame.pack(fill=tk.X, padx=10, pady=(0, 4))

        scores = [
            self._scorer.score_assignment(a).total
            for a in self._all_attempts
        ]
        for i, s in enumerate(scores, 1):
            marker = " ◀ this attempt" if i == len(scores) else ""
            best_marker = " ★" if s == max(scores) and i == len(scores) else ""
            ttk.Label(
                traj_frame,
                text=f"Attempt {i}: {s} pts{marker}{best_marker}",
                font=("TkDefaultFont", 9, "bold" if i == len(scores) else "normal"),
            ).pack(side=tk.LEFT, padx=8)

    # ------------------------------------------------------------------

    def _on_replay(self) -> None:
        dbg(f"  AttemptResultsWindow._on_replay clicked (attempt={self._attempt})")
        self._replay_requested = True
        self._win.destroy()

    def _on_finish(self) -> None:
        dbg(f"  AttemptResultsWindow._on_finish called (attempt={self._attempt}, via button or X)")
        self._replay_requested = False
        self._win.destroy()

    def run(self) -> bool:
        """
        Show the results window and wait for user decision.

        Returns True if the user requested a replay, False otherwise.
        """
        dbg(f"  AttemptResultsWindow.run(): entering wait_window, _replay_requested default={self._replay_requested}")
        self._parent.wait_window(self._win)
        dbg(f"  AttemptResultsWindow.run(): wait_window returned, _replay_requested={self._replay_requested}")
        return self._replay_requested
