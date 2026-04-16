"""
ScoringHUD — a Tkinter widget that displays the shared and individual scores.
"""
from __future__ import annotations

from typing import Dict, List, Optional

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from problems.scoring import ScoringResult


_COLOUR_CHIPS: Dict[str, str] = {
    "red":    "#ff6666",
    "blue":   "#6688ff",
    "green":  "#55cc55",
    "yellow": "#dddd22",
    "purple": "#aa66ff",
    "orange": "#ff9944",
}


class ScoringHUD(ttk.Frame):
    """
    Horizontal score display bar.

    Shows:
      - Large shared total on the left
      - One compact score card per participant on the right

    Parameters
    ----------
    parent:
        Parent Tk widget.
    participants:
        Ordered list of participant names (e.g. ["Human", "AgentA", "AgentB"]).
    preferred_colours:
        Maps participant name → their preferred / assigned colour (for the chip).
    """

    def __init__(
        self,
        parent,
        *,
        participants: List[str],
        preferred_colours: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(parent, relief="flat", padding=4)
        self._participants = participants
        self._preferred_colours: Dict[str, str] = preferred_colours or {}

        self._total_var = tk.StringVar(value="0")
        self._score_vars: Dict[str, tk.StringVar] = {
            p: tk.StringVar(value="0") for p in participants
        }
        self._build()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Left: big shared total
        shared_frame = ttk.Frame(self, padding=(8, 2))
        shared_frame.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(shared_frame, text="SHARED SCORE", font=("TkDefaultFont", 8)).pack()
        ttk.Label(
            shared_frame,
            textvariable=self._total_var,
            font=("TkDefaultFont", 24, "bold"),
            foreground="#225511",
        ).pack()

        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        # Right: per-participant score cards
        for p in self._participants:
            card = ttk.Frame(self, padding=(6, 2), relief="groove")
            card.pack(side=tk.LEFT, padx=4)

            # Colour chip (small coloured square)
            pref = self._preferred_colours.get(p, "")
            chip_colour = _COLOUR_CHIPS.get(pref.lower(), "#cccccc")
            chip = tk.Canvas(card, width=14, height=14, highlightthickness=0, bg=chip_colour)
            chip.grid(row=0, column=0, padx=(0, 4))

            ttk.Label(card, text=p, font=("TkDefaultFont", 8)).grid(row=0, column=1, sticky="w")
            ttk.Label(
                card,
                textvariable=self._score_vars[p],
                font=("TkDefaultFont", 14, "bold"),
            ).grid(row=1, column=0, columnspan=2)

    def update(self, result: ScoringResult) -> None:
        """Refresh displayed scores from a ScoringResult."""
        self._total_var.set(str(result.total))
        for p, var in self._score_vars.items():
            var.set(str(result.by_owner.get(p, 0)))
