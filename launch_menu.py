"""Small launcher UI for running the clustered graph-colouring study.

This is intended for quick experiment setup in PyCharm:

    python launch_menu.py

You can choose the condition (RB / LLM_*), whether to use the Tkinter
participant UI, the agent's internal algorithm, stopping rules, and the
maximum number of iterations. Clicking **Start** runs the experiment and
writes results under ./results/<condition>/
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def main() -> None:
    # IMPORTANT: Do not run the experiment inside the same Tk mainloop as this
    # launcher. The participant UI also uses Tk, and nested roots/mainloops can
    # freeze or break event handling. We therefore spawn a fresh Python process
    # with CLI args.
    import subprocess
    import sys

    root = tk.Tk()
    root.title("Graph Colouring Study Launcher")
    root.geometry("520x420")

    FONT = ("Arial", 13)
    root.option_add("*TLabel.Font", FONT)
    root.option_add("*TButton.Font", FONT)
    root.option_add("*TCheckbutton.Font", FONT)
    root.option_add("*TCombobox.Font", FONT)

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)

    # --- variables ---
    method_var = tk.StringVar(value="RB")
    use_ui_var = tk.BooleanVar(value=True)
    manual_var = tk.BooleanVar(value=False)
    alg_var = tk.StringVar(value="greedy")
    max_iter_var = tk.IntVar(value=10)
    k_var = tk.IntVar(value=2)
    stop_soft_var = tk.BooleanVar(value=True)
    # Study default: do not auto-end purely because penalty=0.
    stop_hard_var = tk.BooleanVar(value=False)

    # --- widgets ---
    ttk.Label(frm, text="Condition").grid(row=0, column=0, sticky="w", pady=(0, 6))
    ttk.Combobox(
        frm,
        textvariable=method_var,
        values=["RB", "LLM_U", "LLM_C", "LLM_F"],
        state="readonly",
        width=18,
    ).grid(row=0, column=1, sticky="w", pady=(0, 6))

    ttk.Label(frm, text="Agent algorithm").grid(row=1, column=0, sticky="w", pady=(0, 6))
    ttk.Combobox(
        frm,
        textvariable=alg_var,
        values=["greedy", "maxsum"],
        state="readonly",
        width=18,
    ).grid(row=1, column=1, sticky="w", pady=(0, 6))

    ttk.Checkbutton(frm, text="Use participant UI", variable=use_ui_var).grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(4, 6)
    )
    ttk.Checkbutton(frm, text="Manual LLM mode (no API)", variable=manual_var).grid(
        row=3, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )

    sep = ttk.Separator(frm)
    sep.grid(row=4, column=0, columnspan=2, sticky="ew", pady=10)

    ttk.Label(frm, text="Max iterations").grid(row=5, column=0, sticky="w", pady=(0, 6))
    ttk.Spinbox(frm, from_=1, to=200, textvariable=max_iter_var, width=8).grid(
        row=5, column=1, sticky="w", pady=(0, 6)
    )

    ttk.Label(frm, text="Soft convergence K (streak)").grid(row=6, column=0, sticky="w", pady=(0, 6))
    ttk.Spinbox(frm, from_=1, to=10, textvariable=k_var, width=8).grid(
        row=6, column=1, sticky="w", pady=(0, 6)
    )

    ttk.Checkbutton(frm, text="Stop on soft convergence", variable=stop_soft_var).grid(
        row=7, column=0, columnspan=2, sticky="w", pady=(4, 6)
    )
    ttk.Checkbutton(
        frm,
        text="Stop on hard convergence (penalty=0) — requires human satisfied",
        variable=stop_hard_var,
    ).grid(
        row=8, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )

    status = tk.StringVar(value="")
    ttk.Label(frm, textvariable=status).grid(row=9, column=0, columnspan=2, sticky="w")

    def on_start() -> None:
        try:
            status.set("Launching…")
            root.update_idletasks()

            from pathlib import Path

            run_script = Path(__file__).resolve().with_name("run_experiment.py")
            args = [
                sys.executable,
                str(run_script),
                "--method",
                method_var.get(),
                "--use-ui" if bool(use_ui_var.get()) else "--no-ui",
                "--manual" if bool(manual_var.get()) else "--api",
                "--max-iters",
                str(int(max_iter_var.get())),
                "--agent-alg",
                alg_var.get(),
                "--k",
                str(int(k_var.get())),
            ]
            if bool(stop_soft_var.get()):
                args.append("--stop-soft")
            if bool(stop_hard_var.get()):
                args.append("--stop-hard")

            subprocess.Popen(args, cwd=str(run_script.parent))
            status.set("Launched. Experiment running in a new window.")
        except Exception as e:
            status.set(f"Error: {e}")

    ttk.Button(frm, text="Start", command=on_start).grid(row=10, column=0, sticky="w", pady=12)
    ttk.Button(frm, text="Quit", command=root.destroy).grid(row=10, column=1, sticky="w", pady=12)

    frm.columnconfigure(1, weight=1)
    root.mainloop()


if __name__ == "__main__":
    main()
