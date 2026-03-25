"""Node Layout Editor — researcher tool for configuring graph display positions.

Run from the repository root:

    python layout_editor.py

Two things are configurable per preset:

  Node positions   — drag the coloured circles to rearrange the graph topology.
  Overlay positions — drag the small labelled boxes to set where each boundary
                      node's info panel will appear in the experiment UI.
                      Overlays are only shown for boundary nodes (those with
                      cross-cluster edges), which are the nodes that actually
                      have info panels at runtime.

Saved data is written to ``ui/node_layouts.json`` and loaded automatically by
the experiment UI at startup.

Controls
--------
- Select a preset from the dropdown.
- Drag a coloured node circle to reposition the node.
- Drag an overlay handle (light box tethered to the node) to reposition the
  info panel for that node.
- "Load Saved"   — restore the last saved layout for the current preset.
- "Reset to Auto" — revert both nodes and overlays to algorithmic defaults.
- "Save Layout"  — write positions to ``ui/node_layouts.json``.
- Window is fully resizable; nodes scale proportionally on resize.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_experiment import _build_topology  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LAYOUT_FILE = Path(__file__).resolve().parent / "ui" / "node_layouts.json"

INIT_W = 900
INIT_H = 680
NODE_R = 18
OVERLAY_W = 170  # width of overlay handle box (wide enough for typical labels)
OVERLAY_H = 232  # height of overlay handle box (~15 lines at 14px/line + padding)

CLUSTER_FILL = {
    "Human":  "#aedff7",
    "Agent1": "#b8f0b8",
    "Agent2": "#ffd9a0",
}
CLUSTER_OUTLINE = {
    "Human":  "#2a7ab5",
    "Agent1": "#2a8a2a",
    "Agent2": "#c07000",
}
OVERLAY_FILL    = "#fffde7"
OVERLAY_OUTLINE = "#999900"

INTRA_EDGE_COLOR = "#999999"
CROSS_EDGE_COLOR = "#d05030"
CROSS_EDGE_WIDTH = 2

ALL_PRESETS = [
    "easy", "tight", "hard",
    "cx_easy", "cx_medium", "cx_hard",
    "cx_easy_8", "cx_easy_8_b", "cx_easy_8_c",
    "cx_hard_8", "cx_hard_8_b", "cx_hard_8_c",
]


# ---------------------------------------------------------------------------
# Layout editor
# ---------------------------------------------------------------------------

class LayoutEditor:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Node Layout Editor")
        self.root.geometry(f"{INIT_W}x{INIT_H + 80}")
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        # Current canvas dimensions (updated on resize)
        self._cw: int = INIT_W
        self._ch: int = INIT_H

        # Current graph state
        self.preset: str = ALL_PRESETS[0]
        self.nodes: list[str] = []
        self.edges: list[tuple[str, str]] = []
        self.owners: dict[str, str] = {}
        self.clusters: dict[str, list[str]] = {}
        self.node_pos: dict[str, tuple[int, int]] = {}

        # Overlay handle positions (boundary nodes only)
        # Key = node name, Value = (x, y) top-left of the handle box
        self.overlay_pos: dict[str, tuple[int, int]] = {}

        # Drag state — only one of these is set at a time
        self._drag_node: str | None = None
        self._drag_overlay: str | None = None
        self._drag_offset: tuple[int, int] = (0, 0)

        self._build_ui()
        self._load_preset(ALL_PRESETS[0])
        self.root.mainloop()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        top = tk.Frame(self.root, padx=10, pady=6)
        top.grid(row=0, column=0, sticky="ew")

        tk.Label(top, text="Preset:", font=("Arial", 11)).pack(side="left")
        self.preset_var = tk.StringVar(value=ALL_PRESETS[0])
        cb = ttk.Combobox(
            top, textvariable=self.preset_var,
            values=ALL_PRESETS, state="readonly", width=14,
        )
        cb.pack(side="left", padx=(4, 12))
        cb.bind("<<ComboboxSelected>>",
                lambda _e: self._load_preset(self.preset_var.get()))

        ttk.Button(top, text="Load Saved",    command=self._load_saved_cmd).pack(side="left", padx=2)
        ttk.Button(top, text="Reset to Auto", command=self._reset_to_auto).pack(side="left", padx=2)
        ttk.Button(top, text="Save Layout",   command=self._save_layout).pack(side="left", padx=(12, 2))

        tk.Label(top, text="  Copy from:", font=("Arial", 11)).pack(side="left")
        self.copy_from_var = tk.StringVar(value=ALL_PRESETS[0])
        ttk.Combobox(
            top, textvariable=self.copy_from_var,
            values=ALL_PRESETS, state="readonly", width=12,
        ).pack(side="left", padx=(4, 2))
        ttk.Button(top, text="Apply", command=self._copy_from_preset).pack(side="left", padx=2)

        self.status_var = tk.StringVar(value="")
        tk.Label(top, textvariable=self.status_var,
                 font=("Arial", 9), fg="#555").pack(side="left", padx=10)

        self.canvas = tk.Canvas(
            self.root, width=INIT_W, height=INIT_H,
            bg="#f5f5f5", relief="sunken", bd=1,
        )
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 4))
        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>",       self._on_canvas_resize)

        tk.Label(
            self.root,
            text="Drag coloured circles = node positions.  "
                 "Drag yellow boxes = info-panel positions (boundary nodes only).  "
                 "Red outline = outside viewport.",
            font=("Arial", 9), fg="#777",
        ).grid(row=2, column=0, pady=(0, 6))

    # ------------------------------------------------------------------
    # Resize handling
    # ------------------------------------------------------------------

    def _on_canvas_resize(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        new_w, new_h = event.width, event.height
        if new_w < 10 or new_h < 10:
            return
        if self._cw and self._ch:
            sx = new_w / self._cw
            sy = new_h / self._ch
            self.node_pos = {n: (int(x * sx), int(y * sy)) for n, (x, y) in self.node_pos.items()}
            self.overlay_pos = {n: (int(x * sx), int(y * sy)) for n, (x, y) in self.overlay_pos.items()}
        self._cw = new_w
        self._ch = new_h
        self._redraw()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _viewport_rect(self) -> tuple[int, int, int, int]:
        """Viewport rect centred in the canvas — approximates the experiment graph area.

        On a 16:9 screen the graph takes ~80% of the width, giving an aspect
        ratio of (0.8 × 16) : 9 ≈ 1.42 : 1.  Use that instead of 4:3.
        """
        margin = 24
        aw = self._cw - margin * 2
        ah = self._ch - margin * 2
        ratio = (0.8 * 16) / 9   # ≈ 1.422
        if aw / ah > ratio:
            rh = ah; rw = int(rh * ratio)
        else:
            rw = aw; rh = int(rw / ratio)
        cx, cy = self._cw // 2, self._ch // 2
        x0 = cx - rw // 2; y0 = cy - rh // 2
        return x0, y0, x0 + rw, y0 + rh

    def _boundary_nodes(self) -> set[str]:
        """Nodes with at least one cross-cluster edge."""
        return {
            n for n in self.nodes
            if any(self.owners.get(v) != self.owners.get(n) for v in
                   [v for u, v in self.edges if u == n] +
                   [u for u, v in self.edges if v == n])
        }

    # ------------------------------------------------------------------
    # Preset loading
    # ------------------------------------------------------------------

    def _load_preset(self, preset: str) -> None:
        self.preset = preset
        node_names, clusters, adjacency, owners, *_ = _build_topology(preset)

        self.nodes = node_names
        self.clusters = clusters
        self.owners = owners

        edges: list[tuple[str, str]] = []
        for u, nbrs in adjacency.items():
            for v in nbrs:
                if (v, u) not in edges:
                    edges.append((u, v))
        self.edges = edges

        self._auto_layout()
        if self._try_load_saved(silent=True):
            self.status_var.set(f"Loaded saved layout for '{preset}'")
        else:
            self.status_var.set(f"Auto layout for '{preset}' — drag nodes/overlays then Save")
        self._redraw()

    def _auto_layout(self) -> None:
        """Triangle layout inside the 4:3 viewport; overlays offset right of each boundary node."""
        vx0, vy0, vx1, vy1 = self._viewport_rect()
        vw = vx1 - vx0
        vh = vy1 - vy0
        cx = vx0 + vw / 2
        cy = vy0 + vh / 2
        cluster_centres: dict[str, tuple[float, float]] = {
            "Human":  (cx,             cy - vh * 0.31),
            "Agent1": (cx - vw * 0.27, cy + vh * 0.19),
            "Agent2": (cx + vw * 0.27, cy + vh * 0.19),
        }
        cluster_r = min(vw, vh) * 0.18

        self.node_pos = {}
        for cname, nodes_in_cluster in self.clusters.items():
            ccx, ccy = cluster_centres.get(cname, (cx, cy))
            n = len(nodes_in_cluster)
            for i, node in enumerate(nodes_in_cluster):
                ang = (2.0 * math.pi * i / n) - math.pi / 2
                x = ccx + cluster_r * math.cos(ang)
                y = ccy + cluster_r * math.sin(ang)
                self.node_pos[node] = (int(x), int(y))

        # Default overlay positions: offset to the right (or left) of boundary nodes
        self.overlay_pos = {}
        for node in self._boundary_nodes():
            if node not in self.node_pos:
                continue
            nx, ny = self.node_pos[node]
            # Prefer right; flip left if near the right edge of the viewport
            if nx + NODE_R + 8 + OVERLAY_W < vx1:
                bx = nx + NODE_R + 8
            else:
                bx = nx - NODE_R - 8 - OVERLAY_W
            by = ny - OVERLAY_H // 2
            self.overlay_pos[node] = (int(bx), int(by))

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _try_load_saved(self, silent: bool = False) -> bool:
        if not LAYOUT_FILE.exists():
            if not silent:
                self.status_var.set("No saved layouts file found.")
            return False
        try:
            with open(LAYOUT_FILE, encoding="utf-8") as f:
                all_layouts: dict = json.load(f)
        except Exception as exc:
            if not silent:
                self.status_var.set(f"Error reading layout file: {exc}")
            return False

        if self.preset not in all_layouts:
            if not silent:
                self.status_var.set(f"No saved layout for '{self.preset}'.")
            return False

        saved = all_layouts[self.preset]
        # Use v[0]/v[1] indexing — avoids unpacking crash when "__overlays__"
        # value is a dict rather than a [fx, fy] list
        loaded_nodes = {
            n: (int(v[0] * self._cw), int(v[1] * self._ch))
            for n, v in saved.items()
            if n != "__overlays__" and isinstance(v, list)
        }
        if not all(n in loaded_nodes for n in self.nodes):
            if not silent:
                self.status_var.set(f"Saved layout for '{self.preset}' is incomplete — using auto.")
            return False

        self.node_pos = loaded_nodes

        # Load overlay positions if saved
        if "__overlays__" in saved:
            self.overlay_pos = {
                n: (int(v[0] * self._cw), int(v[1] * self._ch))
                for n, v in saved["__overlays__"].items()
                if isinstance(v, list)
            }

        return True

    def _load_saved_cmd(self) -> None:
        if self._try_load_saved(silent=False):
            self.status_var.set(f"Loaded saved layout for '{self.preset}'.")
            self._redraw()

    def _reset_to_auto(self) -> None:
        self._auto_layout()
        self._redraw()
        self.status_var.set(f"Reset to auto layout for '{self.preset}'.")

    def _save_layout(self) -> None:
        all_layouts: dict = {}
        if LAYOUT_FILE.exists():
            try:
                with open(LAYOUT_FILE, encoding="utf-8") as f:
                    all_layouts = json.load(f)
            except Exception:
                pass

        preset_data: dict = {
            n: [round(x / self._cw, 4), round(y / self._ch, 4)]
            for n, (x, y) in self.node_pos.items()
        }
        if self.overlay_pos:
            preset_data["__overlays__"] = {
                n: [round(x / self._cw, 4), round(y / self._ch, 4)]
                for n, (x, y) in self.overlay_pos.items()
            }
        all_layouts[self.preset] = preset_data

        LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_layouts, f, indent=2)

        self.status_var.set(
            f"Saved '{self.preset}' → {LAYOUT_FILE.name}  "
            f"({len(self.node_pos)} nodes, {len(self.overlay_pos)} overlays)"
        )

    def _copy_from_preset(self) -> None:
        src = self.copy_from_var.get()
        if src == self.preset:
            self.status_var.set("Source and target are the same preset — nothing copied.")
            return
        if not LAYOUT_FILE.exists():
            self.status_var.set("No saved layouts file found.")
            return
        try:
            with open(LAYOUT_FILE, encoding="utf-8") as f:
                all_layouts: dict = json.load(f)
        except Exception as exc:
            self.status_var.set(f"Error reading layout file: {exc}")
            return
        if src not in all_layouts:
            self.status_var.set(f"No saved layout for '{src}' to copy from.")
            return
        saved = all_layouts[src]
        # Map positions by node name — only copy nodes that exist in current preset
        copied_nodes = {
            n: (int(v[0] * self._cw), int(v[1] * self._ch))
            for n, v in saved.items()
            if n != "__overlays__" and isinstance(v, list) and n in self.nodes
        }
        missing = [n for n in self.nodes if n not in copied_nodes]
        if missing:
            self.status_var.set(
                f"Topology mismatch — nodes not in '{src}': {', '.join(missing)}. Copy aborted."
            )
            return
        self.node_pos = copied_nodes
        if "__overlays__" in saved:
            self.overlay_pos = {
                n: (int(v[0] * self._cw), int(v[1] * self._ch))
                for n, v in saved["__overlays__"].items()
                if isinstance(v, list) and n in self.nodes
            }
        self._redraw()
        self.status_var.set(
            f"Copied layout from '{src}' → '{self.preset}'. Hit Save Layout to commit."
        )

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")

        vx0, vy0, vx1, vy1 = self._viewport_rect()

        # Background: grey outside viewport, white inside
        c.create_rectangle(0, 0, self._cw, self._ch, fill="#e8e8e8", outline="")
        c.create_rectangle(vx0, vy0, vx1, vy1, fill="#f5f5f5", outline="")
        c.create_rectangle(vx0, vy0, vx1, vy1, outline="#4488cc", width=2, dash=(8, 4))
        c.create_text(vx0 + 6, vy0 + 4,
                      text="← approx. graph viewport (80% of 16:9 screen)",
                      anchor="nw", font=("Arial", 8), fill="#4488cc")

        # Edges
        for u, v in self.edges:
            if u not in self.node_pos or v not in self.node_pos:
                continue
            x1, y1 = self.node_pos[u]
            x2, y2 = self.node_pos[v]
            cross = self.owners.get(u) != self.owners.get(v)
            c.create_line(x1, y1, x2, y2,
                          fill=CROSS_EDGE_COLOR if cross else INTRA_EDGE_COLOR,
                          width=CROSS_EDGE_WIDTH if cross else 1)

        # Overlay tether lines (drawn before boxes so boxes sit on top)
        for node, (bx, by) in self.overlay_pos.items():
            if node not in self.node_pos:
                continue
            nx, ny = self.node_pos[node]
            c.create_line(nx, ny, bx + OVERLAY_W // 2, by + OVERLAY_H // 2,
                          fill="#bbaa00", width=1, dash=(4, 3))

        # Nodes
        for node in self.nodes:
            if node not in self.node_pos:
                continue
            x, y = self.node_pos[node]
            owner = self.owners.get(node, "Human")
            outside = not (vx0 <= x <= vx1 and vy0 <= y <= vy1)
            c.create_oval(x - NODE_R, y - NODE_R, x + NODE_R, y + NODE_R,
                          fill=CLUSTER_FILL.get(owner, "#eee"),
                          outline="#cc3300" if outside else CLUSTER_OUTLINE.get(owner, "#555"),
                          width=3 if outside else 2)
            c.create_text(x, y, text=node, font=("Arial", 9, "bold"))

        # Overlay handles (boundary nodes)
        for node, (bx, by) in self.overlay_pos.items():
            outside = not (vx0 <= bx <= vx1 and vy0 <= by <= vy1)
            c.create_rectangle(bx, by, bx + OVERLAY_W, by + OVERLAY_H,
                               fill=OVERLAY_FILL,
                               outline="#cc3300" if outside else OVERLAY_OUTLINE,
                               width=2)
            c.create_text(bx + OVERLAY_W // 2, by + OVERLAY_H // 2,
                          text=f"⠿ {node} info",
                          font=("Arial", 8), fill="#666600")

        # Legend
        for i, (cname, fill) in enumerate(CLUSTER_FILL.items()):
            lx, ly = 12 + i * 140, 10
            c.create_oval(lx, ly, lx + 16, ly + 16,
                          fill=fill, outline=CLUSTER_OUTLINE.get(cname, "#555"), width=2)
            c.create_text(lx + 22, ly + 8, text=cname, anchor="w", font=("Arial", 9))
        lx = 12 + len(CLUSTER_FILL) * 140
        c.create_rectangle(lx, 10, lx + 16, 22, fill=OVERLAY_FILL,
                           outline=OVERLAY_OUTLINE, width=2)
        c.create_text(lx + 22, 16, text="info panel", anchor="w", font=("Arial", 9))
        lx2 = lx + 100
        c.create_line(lx2, 16, lx2 + 20, 16, fill=CROSS_EDGE_COLOR, width=CROSS_EDGE_WIDTH)
        c.create_text(lx2 + 26, 16, text="cross-cluster",
                      anchor="w", font=("Arial", 9), fill=CROSS_EDGE_COLOR)

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _overlay_at(self, x: int, y: int) -> str | None:
        for node, (bx, by) in self.overlay_pos.items():
            if bx <= x <= bx + OVERLAY_W and by <= y <= by + OVERLAY_H:
                return node
        return None

    def _node_at(self, x: int, y: int) -> str | None:
        for node, (nx, ny) in self.node_pos.items():
            if math.hypot(x - nx, y - ny) <= NODE_R + 4:
                return node
        return None

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def _on_press(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        # Check overlay handles first (they're on top visually)
        ov = self._overlay_at(event.x, event.y)
        if ov:
            self._drag_overlay = ov
            bx, by = self.overlay_pos[ov]
            self._drag_offset = (event.x - bx, event.y - by)
            return
        node = self._node_at(event.x, event.y)
        if node:
            self._drag_node = node
            nx, ny = self.node_pos[node]
            self._drag_offset = (event.x - nx, event.y - ny)

    def _on_drag(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        ox, oy = self._drag_offset
        if self._drag_overlay:
            new_x = max(0, min(self._cw - OVERLAY_W, event.x - ox))
            new_y = max(0, min(self._ch - OVERLAY_H, event.y - oy))
            self.overlay_pos[self._drag_overlay] = (new_x, new_y)
            self._redraw()
        elif self._drag_node:
            new_x = max(NODE_R, min(self._cw - NODE_R, event.x - ox))
            new_y = max(NODE_R, min(self._ch - NODE_R, event.y - oy))
            self.node_pos[self._drag_node] = (new_x, new_y)
            self._redraw()

    def _on_release(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._drag_node = None
        self._drag_overlay = None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    LayoutEditor()


if __name__ == "__main__":
    main()
