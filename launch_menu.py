"""
launch_menu.py — launcher for the Drone Channel Assignment game.

    python launch_menu.py
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from robot_world import COMPLEXITY_PRESETS, SPEED_MIN, SPEED_MAX


def main() -> None:
    root = tk.Tk()
    root.title("Drone Channel Assignment — Launcher")
    root.resizable(False, False)

    pad = {"padx": 12, "pady": 5}
    row = 0

    # ── Complexity ────────────────────────────────────────────────────────────
    ttk.Label(root, text="Complexity:").grid(row=row, column=0, sticky="e", **pad)
    complexity_var = tk.StringVar(value="medium")
    ttk.Combobox(
        root, textvariable=complexity_var,
        values=list(COMPLEXITY_PRESETS), state="readonly", width=10,
    ).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # ── Seed ──────────────────────────────────────────────────────────────────
    ttk.Label(root, text="Seed:").grid(row=row, column=0, sticky="e", **pad)
    seed_var = tk.IntVar(value=42)
    ttk.Spinbox(root, from_=0, to=99999, textvariable=seed_var, width=8).grid(
        row=row, column=1, sticky="w", **pad)
    row += 1

    # ── Duration ─────────────────────────────────────────────────────────────
    ttk.Label(root, text="Duration (s):").grid(row=row, column=0, sticky="e", **pad)
    duration_var = tk.DoubleVar(value=90.0)
    ttk.Spinbox(root, from_=30, to=300, increment=10, textvariable=duration_var, width=8).grid(
        row=row, column=1, sticky="w", **pad)
    row += 1

    # ── Epsilon ───────────────────────────────────────────────────────────────
    ttk.Label(root, text="Agent noise (ε):").grid(row=row, column=0, sticky="e", **pad)
    epsilon_var = tk.DoubleVar(value=0.20)
    ttk.Spinbox(
        root, from_=0.0, to=1.0, increment=0.05, format="%.2f",
        textvariable=epsilon_var, width=8,
    ).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # ── Switch delay ──────────────────────────────────────────────────────────
    ttk.Label(root, text="Switch delay (s):").grid(row=row, column=0, sticky="e", **pad)
    switch_delay_var = tk.DoubleVar(value=3.0)
    ttk.Spinbox(
        root, from_=0.0, to=10.0, increment=0.5, format="%.1f",
        textvariable=switch_delay_var, width=8,
    ).grid(row=row, column=1, sticky="w", **pad)
    ttk.Label(root, text="(0 = instant)", foreground="gray").grid(
        row=row, column=1, sticky="e", padx=(0, 12))
    row += 1

    ttk.Separator(root, orient=tk.HORIZONTAL).grid(
        row=row, column=0, columnspan=2, sticky="ew", pady=4)
    row += 1

    # ── Advanced overrides ────────────────────────────────────────────────────
    adv_frame = ttk.LabelFrame(root, text="Override (leave blank for preset defaults)")
    adv_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=4)
    row += 1

    ttk.Label(adv_frame, text="Drones:").grid(row=0, column=0, sticky="e", padx=8, pady=3)
    robots_var = tk.StringVar(value="")
    ttk.Entry(adv_frame, textvariable=robots_var, width=6).grid(row=0, column=1, sticky="w")

    ttk.Label(adv_frame, text="v-min:").grid(row=0, column=2, sticky="e", padx=8)
    vmin_var = tk.StringVar(value="")
    ttk.Entry(adv_frame, textvariable=vmin_var, width=6).grid(row=0, column=3, sticky="w")

    ttk.Label(adv_frame, text="v-max:").grid(row=0, column=4, sticky="e", padx=8)
    vmax_var = tk.StringVar(value="")
    ttk.Entry(adv_frame, textvariable=vmax_var, width=6).grid(row=0, column=5, sticky="w", padx=(0, 8))

    ttk.Separator(root, orient=tk.HORIZONTAL).grid(
        row=row, column=0, columnspan=2, sticky="ew", pady=4)
    row += 1

    # ── Start ─────────────────────────────────────────────────────────────────
    def start() -> None:
        complexity = complexity_var.get()
        n_default, vmin_default, vmax_default = COMPLEXITY_PRESETS[complexity]

        seed          = seed_var.get()
        duration      = duration_var.get()
        epsilon       = epsilon_var.get()
        switch_delay  = switch_delay_var.get()

        n_robots = int(robots_var.get()) if robots_var.get().strip() else n_default
        v_min    = float(vmin_var.get()) if vmin_var.get().strip()   else vmin_default
        v_max    = float(vmax_var.get()) if vmax_var.get().strip()   else vmax_default

        root.destroy()

        from robot_game import run_game
        run_game(
            seed=seed,
            n_robots=n_robots,
            duration=duration,
            v_min=v_min,
            v_max=v_max,
            epsilon=epsilon,
            complexity=complexity,
            switch_duration=switch_delay,
        )

    ttk.Button(root, text="Start Game", command=start, width=16).grid(
        row=row, column=0, columnspan=2, pady=8)

    root.mainloop()


if __name__ == "__main__":
    main()
