"""End-of-trial results window (participant-facing).

This window is shown when a run ends (human-confirmed stop or timeout).
It renders the **full graph** with the final assignments, and a short
summary of what happened (stop reason, iterations, penalty trend).

Design goals:
* Participant can verify the final colouring across clusters.
* Summary is readable and suitable for in-person use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class RunSummary:
    stop_reason: str
    iterations: int
    penalties: List[float]
    total_messages: int


class ResultsWindow:
    def __init__(
        self,
        master,
        *,
        title: str,
        nodes: List[str],
        edges: List[Tuple[str, str]],
        owners: Dict[str, str],
        final_assignments: Dict[str, Any],
        summary: RunSummary,
        domain: List[Any],
    ) -> None:
        import tkinter as tk
        from tkinter import ttk
        import math

        self._top = tk.Toplevel(master)
        self._top.title(title)
        self._top.geometry("1280x860")

        FONT_HEADER = ("Arial", 22, "bold")
        FONT_BODY = ("Arial", 15)
        FONT_SMALL = ("Arial", 13)

        ttk.Label(self._top, text="Trial complete", font=FONT_HEADER).pack(pady=12)

        body = ttk.Frame(self._top)
        body.pack(fill="both", expand=True, padx=16, pady=10)

        # ---- Graph ----
        graph_frame = ttk.LabelFrame(body, text="Full graph (final)")
        graph_frame.pack(side="left", fill="both", expand=True, padx=(0, 12))

        canvas_w, canvas_h = 900, 700
        canvas = tk.Canvas(graph_frame, width=canvas_w, height=canvas_h, background="white", highlightthickness=0)
        canvas.pack(padx=12, pady=12)

        # Layout: deterministic ring (simple and stable)
        n = max(1, len(nodes))
        angle_step = 2 * math.pi / n
        pos = {name: (math.cos(i * angle_step), math.sin(i * angle_step)) for i, name in enumerate(nodes)}

        def to_canvas(xy):
            x, y = xy
            x = (x + 1.2) / 2.4
            y = (y + 1.2) / 2.4
            cx = 60 + x * (canvas_w - 120)
            cy = 60 + y * (canvas_h - 120)
            return cx, cy

        allowed_colours = {str(c) for c in domain} | {"red", "green", "blue", "orange", "yellow", "purple"}

        # edges
        for u, v in edges:
            if u not in pos or v not in pos:
                continue
            x1, y1 = to_canvas(pos[u])
            x2, y2 = to_canvas(pos[v])
            canvas.create_line(x1, y1, x2, y2, width=3)

        # nodes
        NODE_R = 24
        for name in nodes:
            if name not in pos:
                continue
            cx, cy = to_canvas(pos[name])
            c = str(final_assignments.get(name, ""))
            fill = c if c in allowed_colours else "lightgrey"
            owner = owners.get(name, "")
            outline = "black"
            width = 4 if owner.lower().startswith("human") else 2
            canvas.create_oval(cx - NODE_R, cy - NODE_R, cx + NODE_R, cy + NODE_R, fill=fill, outline=outline, width=width)
            canvas.create_text(cx, cy + NODE_R + 18, text=f"{name}\n({owner})", font=FONT_SMALL)

        # ---- Summary ----
        sum_frame = ttk.LabelFrame(body, text="Summary")
        sum_frame.pack(side="left", fill="y", expand=False)

        pen_str = ", ".join([f"{p:.0f}" if abs(p - round(p)) < 1e-9 else f"{p:.2f}" for p in summary.penalties[-10:]])
        if len(summary.penalties) > 10:
            pen_str = "... " + pen_str

        text = (
            f"Stop reason: {summary.stop_reason}\n"
            f"Iterations: {summary.iterations}\n"
            f"Total messages: {summary.total_messages}\n\n"
            f"Penalty (last values):\n{pen_str}\n"
        )

        lbl = ttk.Label(sum_frame, text=text, font=FONT_BODY, justify="left")
        lbl.pack(anchor="w", padx=12, pady=12)

        ttk.Button(self._top, text="Close", command=self._top.destroy).pack(pady=10)
