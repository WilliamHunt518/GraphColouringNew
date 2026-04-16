"""
launch_menu.py — simplified launcher for the graph-colouring trust study.

Run from the repository root:

    python launch_menu.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from study.graphs import GRAPH_CONFIGS

_MODES = {
    "Mode 1 — Manual Collaborative": "mode1",
    "Mode 2A — Autonomous (High Quality)": "mode2a",
    "Mode 2B — Autonomous (Low Quality)": "mode2b",
}


def main() -> None:
    root = tk.Tk()
    root.title("Graph Colouring Study — Launcher")
    root.resizable(False, False)

    pad = {"padx": 10, "pady": 5}

    # --- Participant ID ---
    ttk.Label(root, text="Participant ID:").grid(row=0, column=0, sticky="e", **pad)
    pid_var = tk.StringVar(value="")
    ttk.Entry(root, textvariable=pid_var, width=20).grid(row=0, column=1, sticky="w", **pad)

    # --- Mode ---
    ttk.Label(root, text="Mode:").grid(row=1, column=0, sticky="e", **pad)
    mode_var = tk.StringVar(value=list(_MODES)[0])
    mode_combo = ttk.Combobox(
        root,
        textvariable=mode_var,
        values=list(_MODES),
        state="readonly",
        width=36,
    )
    mode_combo.grid(row=1, column=1, sticky="w", **pad)

    # --- Graph preset ---
    ttk.Label(root, text="Graph:").grid(row=2, column=0, sticky="e", **pad)
    graph_var = tk.StringVar(value=list(GRAPH_CONFIGS)[0])
    graph_combo = ttk.Combobox(
        root,
        textvariable=graph_var,
        values=list(GRAPH_CONFIGS),
        state="readonly",
        width=20,
    )
    graph_combo.grid(row=2, column=1, sticky="w", **pad)

    # --- Max attempts ---
    ttk.Label(root, text="Max attempts:").grid(row=3, column=0, sticky="e", **pad)
    attempts_var = tk.IntVar(value=3)
    ttk.Spinbox(root, from_=1, to=5, textvariable=attempts_var, width=5).grid(
        row=3, column=1, sticky="w", **pad
    )

    # --- Seed ---
    ttk.Label(root, text="Seed:").grid(row=4, column=0, sticky="e", **pad)
    seed_var = tk.IntVar(value=42)
    ttk.Entry(root, textvariable=seed_var, width=8).grid(row=4, column=1, sticky="w", **pad)

    ttk.Separator(root, orient=tk.HORIZONTAL).grid(
        row=5, column=0, columnspan=2, sticky="ew", pady=6
    )

    # --- Start button ---
    def start() -> None:
        pid = pid_var.get().strip()
        if not pid:
            pid = datetime.now().strftime("P%Y%m%d_%H%M%S")

        mode_key = mode_var.get()
        mode = _MODES[mode_key]
        graph = graph_var.get()
        seed = seed_var.get()
        max_attempts = attempts_var.get()

        from study.config import DEFAULT_COLOURS, DEFAULT_POINTS, DEFAULT_AGENTS
        from study.graphs import get_graph, get_node_regions

        graph_def = get_graph(graph)
        node_regions = get_node_regions(graph)

        # Use per-graph overrides when present, else fall back to defaults
        colours       = graph_def.colours       or DEFAULT_COLOURS
        points_cfg    = graph_def.points_config  or DEFAULT_POINTS
        agent_cfgs    = graph_def.agent_configs  or DEFAULT_AGENTS

        # Build serialisable config dict
        config_dict = {
            "participant_id": pid,
            "mode": mode,
            "graph_def": {
                "name": graph_def.name,
                "nodes": graph_def.nodes,
                "edges": [list(e) for e in graph_def.edges],
                "node_order": graph_def.node_order,
                "layout_preset": graph_def.layout_preset,
            },
            "colours": colours,
            "points_config": {
                "points_by_owner": points_cfg.points_by_owner,
                "colours": points_cfg.colours,
            },
            "node_regions": node_regions,
            "agent_configs": [
                {"name": a.name, "preferred_colour": a.preferred_colour}
                for a in agent_cfgs
            ],
            "max_attempts": max_attempts,
            "seed": seed,
            "output_dir": "results/participants",
        }

        config_json = json.dumps(config_dict)
        import os
        project_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.Popen(
            [sys.executable, "run_experiment.py", "--config", config_json],
            cwd=project_dir,
        )
        root.destroy()

    ttk.Button(root, text="Start Session", command=start, width=18).grid(
        row=6, column=0, columnspan=2, pady=8
    )

    root.mainloop()


if __name__ == "__main__":
    main()
