"""
GraphCanvas — a Tkinter widget that renders the graph.

Extracted and simplified from ui/human_turn_ui.py.  Supports:
  - Pan (middle-click drag or Shift+left drag)
  - Zoom (Ctrl+MouseWheel)
  - Node click callback (only fires for nodes in clickable_nodes)
  - Highlight ring on the current node
  - Clash highlighting (red edges between same-colour neighbours)
  - Visual region styling (node_regions: node -> owner name)
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None  # type: ignore
    ttk = None  # type: ignore

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

_COLOUR_FILLS: Dict[str, str] = {
    "red":    "#ffaaaa",
    "blue":   "#aaaaff",
    "green":  "#aaffaa",
    "yellow": "#ffffaa",
    "purple": "#ddaaff",
    "orange": "#ffcc88",
}
_UNCOLOURED_FILL = "#dddddd"
_HIGHLIGHT_COLOUR  = "#ffee44"   # ring around current node
_NEIGHBOURHOOD_RING = "#ff8800"  # ring around neighbourhood nodes in overview

_REGION_OUTLINES: Dict[str, str] = {
    "Human":  "#222222",
    "AgentA": "#0055cc",
    "AgentB": "#cc4400",
    "AgentC": "#880088",
}
_DEFAULT_OUTLINE = "#555555"


def colour_fill(c: Optional[str]) -> str:
    if c is None:
        return _UNCOLOURED_FILL
    return _COLOUR_FILLS.get(str(c).lower(), "#eeeeee")


# ---------------------------------------------------------------------------
# GraphCanvas
# ---------------------------------------------------------------------------

class GraphCanvas(ttk.Frame):
    """
    Self-contained Tkinter widget that displays a graph.

    Parameters
    ----------
    parent:
        Parent Tk widget.
    nodes:
        List of node names.
    edges:
        List of (u, v) undirected edge tuples.
    node_regions:
        Maps node name → owner/region name (for visual styling only).
    layout_preset:
        Key in ``ui/node_layouts.json``; if absent, falls back to circular.
    on_node_click:
        Called with the node name when the user clicks a clickable node.
    clickable_nodes:
        Set of node names that respond to clicks.  None = empty (no clicks).
    """

    NODE_RADIUS = 22
    CLICK_THRESHOLD_FACTOR = 1.8   # multiplier on radius for hit-test

    def __init__(
        self,
        parent,
        *,
        nodes: List[str],
        edges: List[Tuple[str, str]],
        node_regions: Optional[Dict[str, str]] = None,
        layout_preset: str = "",
        on_node_click: Optional[Callable[[str], None]] = None,
        clickable_nodes: Optional[Set[str]] = None,
        width: int = 550,
        height: int = 500,
    ) -> None:
        super().__init__(parent)
        self._nodes = list(nodes)
        self._edges = list(edges)
        self._node_regions: Dict[str, str] = node_regions or {}
        self._layout_preset = layout_preset
        self._on_node_click = on_node_click
        self._clickable_nodes: Set[str] = set(clickable_nodes) if clickable_nodes else set()

        self._assignments: Dict[str, str] = {}
        self._highlighted_node: Optional[str] = None
        self._neighbourhood_nodes: Set[str] = set()

        # Pan/zoom state
        self._scale: float = 1.0
        self._offset: Tuple[float, float] = (0.0, 0.0)
        self._pan_start: Optional[Tuple[int, int]] = None
        self._pan_offset_start: Optional[Tuple[float, float]] = None

        # Computed node positions (in canvas-native coords before pan/zoom)
        self._node_pos: Dict[str, Tuple[int, int]] = {}

        # Canvas item IDs
        self._node_items: Dict[str, int] = {}
        self._edge_items: List[Tuple[str, str, int]] = []
        self._label_items: Dict[str, int] = {}
        self._highlight_item: Optional[int] = None

        self._canvas_w = width
        self._canvas_h = height

        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self._canvas = tk.Canvas(
            self,
            width=self._canvas_w,
            height=self._canvas_h,
            bg="#f8f8f8",
            highlightthickness=1,
            highlightbackground="#cccccc",
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<ButtonPress-1>", self._on_left_press)
        self._canvas.bind("<ButtonPress-2>", self._on_pan_start)
        self._canvas.bind("<B2-Motion>", self._on_pan_drag)
        self._canvas.bind("<ButtonRelease-2>", self._on_pan_end)
        self._canvas.bind("<Shift-ButtonPress-1>", self._on_pan_start)
        self._canvas.bind("<Shift-B1-Motion>", self._on_pan_drag)
        self._canvas.bind("<Shift-ButtonRelease-1>", self._on_pan_end)
        self._canvas.bind("<Control-MouseWheel>", self._on_zoom)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

        self._canvas.after(50, self._delayed_layout)

    def _delayed_layout(self) -> None:
        """Layout after first render so winfo_width/height are valid."""
        self._compute_layout()
        self._redraw()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_assignment(self, node: str, colour: str) -> None:
        """Colour one node and redraw."""
        self._assignments[node] = colour
        self._redraw()

    def set_all_assignments(self, assignment: Dict[str, str]) -> None:
        """Replace entire assignment dict and redraw."""
        self._assignments = dict(assignment)
        self._redraw()

    def clear_assignments(self) -> None:
        self._assignments.clear()
        self._redraw()

    def highlight_current_node(self, node: Optional[str]) -> None:
        """Draw a highlight ring around ``node`` (or remove if None)."""
        self._highlighted_node = node
        self._redraw()

    def set_clickable_nodes(self, nodes: Set[str]) -> None:
        """Update which nodes respond to left-click."""
        self._clickable_nodes = set(nodes)

    def set_neighbourhood_highlight(self, nodes: Optional[Set[str]]) -> None:
        """Mark a set of nodes with an orange halo in the overview (current node + its neighbours)."""
        self._neighbourhood_nodes = set(nodes) if nodes else set()
        self._redraw()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _compute_layout(self) -> None:
        w = max(self._canvas.winfo_width(), self._canvas_w)
        h = max(self._canvas.winfo_height(), self._canvas_h)

        # Try loading from node_layouts.json
        if self._layout_preset:
            layout_file = Path(__file__).parent / "node_layouts.json"
            if layout_file.exists():
                try:
                    with open(layout_file) as f:
                        all_layouts = json.load(f)
                    if self._layout_preset in all_layouts:
                        saved = all_layouts[self._layout_preset]
                        visible = set(self._nodes)
                        # Reserve a margin so nodes near the edge don't clip
                        mx = self.NODE_RADIUS + 6
                        my = self.NODE_RADIUS + 6
                        loaded = {
                            n: (int(mx + v[0] * (w - 2 * mx)),
                                int(my + v[1] * (h - 2 * my)))
                            for n, v in saved.items()
                            if n in visible and isinstance(v, list)
                        }
                        if all(n in loaded for n in self._nodes):
                            self._node_pos.update(loaded)
                            return
                except Exception:
                    pass

        # Fallback: group by region, place each group in a circle
        self._circular_layout(w, h)

    def _circular_layout(self, w: int, h: int) -> None:
        """Place nodes in region-based circles, fallback to single circle."""
        cx, cy = w / 2.0, h / 2.0
        regions: Dict[str, List[str]] = {}
        for n in self._nodes:
            r = self._node_regions.get(n, "")
            regions.setdefault(r, []).append(n)

        unique_regions = [r for r in regions if r]
        if len(unique_regions) <= 1:
            # Single circle
            r_main = min(w, h) * 0.38
            for i, n in enumerate(self._nodes):
                ang = 2 * math.pi * i / max(len(self._nodes), 1)
                self._node_pos[n] = (
                    int(cx + r_main * math.cos(ang)),
                    int(cy + r_main * math.sin(ang)),
                )
        else:
            # Place region centres at vertices of a larger polygon
            n_regions = len(unique_regions)
            outer_r = min(w, h) * 0.30
            inner_r = min(w, h) * 0.12
            for ri, region in enumerate(unique_regions):
                ang_r = -math.pi / 2 + 2 * math.pi * ri / n_regions
                rcx = cx + outer_r * math.cos(ang_r)
                rcy = cy + outer_r * math.sin(ang_r)
                rnodes = regions[region]
                for ni, n in enumerate(rnodes):
                    ang_n = 2 * math.pi * ni / max(len(rnodes), 1)
                    self._node_pos[n] = (
                        int(rcx + inner_r * math.cos(ang_n)),
                        int(rcy + inner_r * math.sin(ang_n)),
                    )

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        canvas = self._canvas
        if not self._node_pos:
            return
        canvas.delete("all")
        self._node_items.clear()
        self._edge_items.clear()
        self._label_items.clear()
        self._highlight_item = None

        sc = self._scale
        ox, oy = self._offset

        def tx(x: int) -> float:
            return x * sc + ox

        def ty(y: int) -> float:
            return y * sc + oy

        # ---- Edges ----
        for u, v in self._edges:
            if u not in self._node_pos or v not in self._node_pos:
                continue
            x1, y1 = self._node_pos[u]
            x2, y2 = self._node_pos[v]
            cu = self._assignments.get(u)
            cv = self._assignments.get(v)
            clash = (cu is not None and cv is not None and cu == cv)
            color = "#dd0000" if clash else "#aaaaaa"
            width = max(1, int(3 * sc)) if clash else max(1, int(1 * sc))
            item = canvas.create_line(tx(x1), ty(y1), tx(x2), ty(y2), fill=color, width=width)
            self._edge_items.append((u, v, item))

        # ---- Neighbourhood halos (drawn behind nodes) ----
        r_base = self.NODE_RADIUS
        for n in self._neighbourhood_nodes:
            if n not in self._node_pos or n == self._highlighted_node:
                continue  # current node gets the yellow ring instead
            x, y = self._node_pos[n]
            r = max(8, int(r_base * sc))
            pad = max(2, int(4 * sc))
            canvas.create_oval(
                tx(x) - r - pad, ty(y) - r - pad,
                tx(x) + r + pad, ty(y) + r + pad,
                outline=_NEIGHBOURHOOD_RING, width=max(2, int(3 * sc)), fill="",
            )

        # ---- Nodes ----
        for n, (x, y) in self._node_pos.items():
            r = max(8, int(r_base * sc))
            col = self._assignments.get(n)
            fill = colour_fill(col)

            # Outline colour based on region
            region = self._node_regions.get(n, "")
            outline = _REGION_OUTLINES.get(region, _DEFAULT_OUTLINE)
            ow = max(1, int(2 * sc))

            # Clickable nodes get a thicker outline
            if n in self._clickable_nodes:
                ow = max(2, int(3 * sc))

            item = canvas.create_oval(
                tx(x) - r, ty(y) - r, tx(x) + r, ty(y) + r,
                fill=fill, outline=outline, width=ow,
            )
            self._node_items[n] = item

            fs = max(7, int(10 * sc))
            lbl = canvas.create_text(
                tx(x), ty(y),
                text=n,
                font=("TkDefaultFont", fs, "bold" if n in self._clickable_nodes else "normal"),
            )
            self._label_items[n] = lbl

        # ---- Highlight ring on current node ----
        if self._highlighted_node and self._highlighted_node in self._node_pos:
            n = self._highlighted_node
            x, y = self._node_pos[n]
            r = max(8, int(r_base * sc))
            pad = max(3, int(5 * sc))
            self._highlight_item = canvas.create_oval(
                tx(x) - r - pad, ty(y) - r - pad,
                tx(x) + r + pad, ty(y) + r + pad,
                outline=_HIGHLIGHT_COLOUR,
                width=max(2, int(4 * sc)),
                fill="",
            )
            # Bring node item to front
            if n in self._node_items:
                canvas.tag_raise(self._node_items[n])
            if n in self._label_items:
                canvas.tag_raise(self._label_items[n])

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_resize(self, event: "tk.Event") -> None:
        self._compute_layout()
        self._redraw()

    def _on_left_press(self, event: "tk.Event") -> None:
        if event.state & 0x0001:  # Shift held — panning
            return
        if self._on_node_click is None:
            return
        node = self._hit_test(event.x, event.y)
        if node and node in self._clickable_nodes:
            self._on_node_click(node)

    def _on_pan_start(self, event: "tk.Event") -> None:
        self._pan_start = (event.x, event.y)
        self._pan_offset_start = self._offset

    def _on_pan_drag(self, event: "tk.Event") -> None:
        if self._pan_start is None or self._pan_offset_start is None:
            return
        dx = event.x - self._pan_start[0]
        dy = event.y - self._pan_start[1]
        ox0, oy0 = self._pan_offset_start
        self._offset = (ox0 + dx, oy0 + dy)
        self._redraw()

    def _on_pan_end(self, event: "tk.Event") -> None:
        self._pan_start = None
        self._pan_offset_start = None

    def _on_zoom(self, event: "tk.Event") -> None:
        factor = 1.1 if event.delta > 0 else 0.9
        old_scale = self._scale
        self._scale = max(0.3, min(4.0, self._scale * factor))
        # Zoom toward mouse position
        mx, my = event.x, event.y
        ox, oy = self._offset
        self._offset = (
            mx - (mx - ox) * (self._scale / old_scale),
            my - (my - oy) * (self._scale / old_scale),
        )
        self._redraw()

    def _on_mousewheel(self, event: "tk.Event") -> None:
        # Regular mousewheel without Ctrl: do nothing (reserve for outer scroll)
        pass

    def _hit_test(self, mx: int, my: int) -> Optional[str]:
        """Return the nearest node within click threshold, or None."""
        sc = self._scale
        ox, oy = self._offset
        graph_x = (mx - ox) / sc
        graph_y = (my - oy) / sc

        threshold_sq = (self.NODE_RADIUS * self.CLICK_THRESHOLD_FACTOR) ** 2
        best: Optional[str] = None
        best_d = threshold_sq
        for n, (nx, ny) in self._node_pos.items():
            d = (nx - graph_x) ** 2 + (ny - graph_y) ** 2
            if d < best_d:
                best_d = d
                best = n
        return best


# ---------------------------------------------------------------------------
# NeighborhoodCanvas
# ---------------------------------------------------------------------------

class NeighborhoodCanvas(ttk.Frame):
    """
    Zoomed-in view of the current node and its immediate neighbours.

    Positions are loaded from node_layouts.json using the same fractional
    coordinates as the overview, then scaled/centred to fill this canvas.
    This preserves the relative angles and distances between nodes exactly
    as they appear in the overview.  Falls back to a circular arrangement
    when layout data is unavailable.
    """

    NODE_R_CENTER  = 30
    NODE_R_NEIGHBOR = 20
    _LABEL_H = 28    # px reserved at bottom for the "Deciding:" label
    _PADDING = 44    # px padding around the scaled subgraph

    def __init__(
        self,
        parent,
        *,
        node_regions: Optional[Dict[str, str]] = None,
        layout_preset: str = "",
        width: int = 380,
        height: int = 240,
    ) -> None:
        super().__init__(parent)
        self._node_regions: Dict[str, str] = node_regions or {}
        self._layout_preset = layout_preset
        self._canvas_w = width
        self._canvas_h = height

        self._current_node: Optional[str] = None
        self._neighbors: List[str] = []
        self._assignments: Dict[str, str] = {}
        self._sub_edges: List[Tuple[str, str]] = []

        # Cache of fractional positions from JSON (loaded once)
        self._frac_cache: Optional[Dict[str, Tuple[float, float]]] = None

        self._canvas = tk.Canvas(
            self,
            width=width,
            height=height,
            bg="#f0f4ff",
            highlightthickness=1,
            highlightbackground="#aabbcc",
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", lambda _e: self._redraw())
        self._canvas.after(50, self._redraw)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def update_view(
        self,
        current_node: str,
        neighbors: List[str],
        assignments: Dict[str, str],
        edges: Optional[List[Tuple[str, str]]] = None,
    ) -> None:
        """Redraw to show *current_node* and its neighbours."""
        self._current_node = current_node
        self._neighbors = list(neighbors)
        self._assignments = dict(assignments)
        self._sub_edges = list(edges) if edges else []
        self._redraw()

    def clear(self) -> None:
        self._current_node = None
        self._redraw()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _load_frac_cache(self) -> None:
        """Load fractional positions from node_layouts.json (once)."""
        if self._frac_cache is not None:
            return
        self._frac_cache = {}
        if not self._layout_preset:
            return
        layout_file = Path(__file__).parent / "node_layouts.json"
        if not layout_file.exists():
            return
        try:
            with open(layout_file) as f:
                all_layouts = json.load(f)
            preset = all_layouts.get(self._layout_preset, {})
            for node, v in preset.items():
                if isinstance(v, list) and len(v) >= 2:
                    self._frac_cache[node] = (float(v[0]), float(v[1]))
        except Exception:
            pass

    def _screen_positions(
        self, nodes: List[str], w: float, h: float
    ) -> Dict[str, Tuple[float, float]]:
        """
        Return pixel positions for *nodes* scaled to fit [0, w] x [0, h-_LABEL_H].

        Uses JSON fractional layout when available, preserving relative angles.
        Falls back to circular arrangement centred on the current node.
        """
        self._load_frac_cache()
        cache = self._frac_cache or {}

        frac = {n: cache[n] for n in nodes if n in cache}
        if len(frac) == len(nodes):
            return self._scale_frac(frac, w, h)

        # Fallback: circular
        return self._circular_fallback(nodes, w, h)

    def _scale_frac(
        self, frac: Dict[str, Tuple[float, float]], w: float, h: float
    ) -> Dict[str, Tuple[float, float]]:
        """Scale fractional positions to fit the canvas, preserving geometry."""
        P = self._PADDING
        L = self._LABEL_H
        xs = [v[0] for v in frac.values()]
        ys = [v[1] for v in frac.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)

        avail_w = w - 2 * P
        avail_h = h - 2 * P - L

        if len(frac) == 1:
            # Single node — centre it
            cx, cy = w / 2, (h - L) / 2
            return {n: (cx, cy) for n in frac}

        scale = min(avail_w / span_x, avail_h / span_y)
        scaled_w = span_x * scale
        scaled_h = span_y * scale
        off_x = (w - scaled_w) / 2 - min_x * scale
        off_y = ((h - L) - scaled_h) / 2 - min_y * scale
        return {n: (fx * scale + off_x, fy * scale + off_y) for n, (fx, fy) in frac.items()}

    def _circular_fallback(
        self, nodes: List[str], w: float, h: float
    ) -> Dict[str, Tuple[float, float]]:
        """Circular layout: current node at centre, neighbours in orbit."""
        L = self._LABEL_H
        cx, cy = w / 2, (h - L) / 2
        positions: Dict[str, Tuple[float, float]] = {}
        current = self._current_node
        if current:
            positions[current] = (cx, cy)
        nbrs = [n for n in nodes if n != current]
        orbit_r = min(w * 0.32, (h - L) * 0.35)
        for i, nbr in enumerate(nbrs):
            angle = -math.pi / 2 + 2 * math.pi * i / max(len(nbrs), 1)
            positions[nbr] = (cx + orbit_r * math.cos(angle), cy + orbit_r * math.sin(angle))
        return positions

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        canvas = self._canvas
        canvas.delete("all")
        w = max(canvas.winfo_width(), self._canvas_w)
        h = max(canvas.winfo_height(), self._canvas_h)

        if not self._current_node:
            canvas.create_text(
                w / 2, h / 2,
                text="No node selected",
                fill="#aaaaaa",
                font=("TkDefaultFont", 10),
            )
            return

        all_nodes = [self._current_node] + self._neighbors
        positions = self._screen_positions(all_nodes, w, h)

        # ---- Edges ----
        for u, v in self._sub_edges:
            if u not in positions or v not in positions:
                continue
            x1, y1 = positions[u]
            x2, y2 = positions[v]
            cu = self._assignments.get(u)
            cv = self._assignments.get(v)
            clash = cu is not None and cv is not None and cu == cv
            canvas.create_line(x1, y1, x2, y2,
                                fill="#dd0000" if clash else "#bbbbbb", width=2)

        # ---- Neighbour nodes ----
        for nbr in self._neighbors:
            if nbr not in positions:
                continue
            x, y = positions[nbr]
            r = self.NODE_R_NEIGHBOR
            col = self._assignments.get(nbr)
            fill = colour_fill(col)
            region = self._node_regions.get(nbr, "")
            outline = _REGION_OUTLINES.get(region, _DEFAULT_OUTLINE)
            canvas.create_oval(x - r, y - r, x + r, y + r,
                                fill=fill, outline=outline, width=2)
            canvas.create_text(x, y, text=nbr, font=("TkDefaultFont", 10, "bold"))

        # ---- Current node (highlight ring + larger circle on top) ----
        if self._current_node not in positions:
            return
        x, y = positions[self._current_node]
        r = self.NODE_R_CENTER
        col = self._assignments.get(self._current_node)
        fill = colour_fill(col)
        region = self._node_regions.get(self._current_node, "")
        outline = _REGION_OUTLINES.get(region, _DEFAULT_OUTLINE)

        pad = 7
        canvas.create_oval(x - r - pad, y - r - pad, x + r + pad, y + r + pad,
                            outline=_HIGHLIGHT_COLOUR, width=4, fill="")
        canvas.create_oval(x - r, y - r, x + r, y + r,
                            fill=fill, outline=outline, width=3)
        canvas.create_text(x, y, text=self._current_node,
                            font=("TkDefaultFont", 13, "bold"))

        # ---- Bottom label ----
        region_name = self._node_regions.get(self._current_node, "")
        label = f"Deciding: {self._current_node}"
        if region_name:
            label += f"  ({region_name})"
        canvas.create_text(
            w / 2, h - 10,
            text=label,
            font=("TkDefaultFont", 10, "bold"),
            fill="#333333",
        )
