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
    import json
    from pathlib import Path

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

    # --- Load saved config ---
    config_path = Path.home() / ".graph_coloring_launcher_config.json"
    saved_config = {}
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                saved_config = json.load(f)
        except Exception:
            pass

    # --- variables with saved defaults ---
    method_var = tk.StringVar(value=saved_config.get("method", "RB"))
    use_ui_var = tk.BooleanVar(value=saved_config.get("use_ui", True))
    manual_var = tk.BooleanVar(value=saved_config.get("manual", False))
    alg_var = tk.StringVar(value=saved_config.get("algorithm", "greedy"))
    max_iter_var = tk.IntVar(value=saved_config.get("max_iters", 10))
    k_var = tk.IntVar(value=saved_config.get("k", 2))
    stop_soft_var = tk.BooleanVar(value=saved_config.get("stop_soft", True))
    stop_hard_var = tk.BooleanVar(value=saved_config.get("stop_hard", False))
    cf_utils_var = tk.BooleanVar(value=saved_config.get("cf_utils", True))
    fixed_constraints_var = tk.BooleanVar(value=saved_config.get("fixed_constraints", True))
    # ALWAYS default to 1 fixed node per agent (creates good renegotiation dynamics)
    num_fixed_nodes_var = tk.IntVar(value=1)

    # --- widgets ---
    ttk.Label(frm, text="Condition").grid(row=0, column=0, sticky="w", pady=(0, 6))
    ttk.Combobox(
        frm,
        textvariable=method_var,
        values=["RB", "LLM_API", "LLM_F", "LLM_RB"],
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
        row=3, column=0, columnspan=2, sticky="w", pady=(0, 6)
    )
    ttk.Checkbutton(frm, text="Use fixed node constraints", variable=fixed_constraints_var).grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(0, 6)
    )

    ttk.Label(frm, text="Fixed nodes per cluster (0-3)").grid(row=5, column=0, sticky="w", pady=(0, 10))
    ttk.Spinbox(frm, from_=0, to=3, textvariable=num_fixed_nodes_var, width=8).grid(
        row=5, column=1, sticky="w", pady=(0, 10)
    )

    ttk.Checkbutton(
        frm,
        text="LLM-U/LLM-C: Counterfactual utilities (best-response)",
        variable=cf_utils_var,
    ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 6))

    sep = ttk.Separator(frm)
    sep.grid(row=7, column=0, columnspan=2, sticky="ew", pady=10)

    ttk.Label(frm, text="Max iterations").grid(row=8, column=0, sticky="w", pady=(0, 6))
    ttk.Spinbox(frm, from_=1, to=200, textvariable=max_iter_var, width=8).grid(
        row=8, column=1, sticky="w", pady=(0, 6)
    )

    ttk.Label(frm, text="Soft convergence K (streak)").grid(row=9, column=0, sticky="w", pady=(0, 6))
    ttk.Spinbox(frm, from_=1, to=10, textvariable=k_var, width=8).grid(
        row=9, column=1, sticky="w", pady=(0, 6)
    )

    ttk.Checkbutton(frm, text="Stop on soft convergence", variable=stop_soft_var).grid(
        row=10, column=0, columnspan=2, sticky="w", pady=(4, 6)
    )
    ttk.Checkbutton(
        frm,
        text="Stop on hard convergence (penalty=0) — requires human satisfied",
        variable=stop_hard_var,
    ).grid(
        row=11, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )

    status = tk.StringVar(value="")
    ttk.Label(frm, textvariable=status).grid(row=12, column=0, columnspan=2, sticky="w")

    def on_start() -> None:
        try:
            status.set("Launching…")
            root.update_idletasks()

            # Save current configuration
            current_config = {
                "method": method_var.get(),
                "use_ui": bool(use_ui_var.get()),
                "manual": bool(manual_var.get()),
                "algorithm": alg_var.get(),
                "max_iters": int(max_iter_var.get()),
                "k": int(k_var.get()),
                "stop_soft": bool(stop_soft_var.get()),
                "stop_hard": bool(stop_hard_var.get()),
                "cf_utils": bool(cf_utils_var.get()),
                "fixed_constraints": bool(fixed_constraints_var.get()),
                "num_fixed_nodes": int(num_fixed_nodes_var.get()),
            }
            try:
                with open(config_path, "w") as f:
                    json.dump(current_config, f, indent=2)
            except Exception:
                pass

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
            args.append("--counterfactual-utils" if bool(cf_utils_var.get()) else "--naive-utils")
            if bool(stop_soft_var.get()):
                args.append("--stop-soft")
            if bool(stop_hard_var.get()):
                args.append("--stop-hard")
            if bool(fixed_constraints_var.get()):
                args.append("--fixed-constraints")
                args.extend(["--num-fixed-nodes", str(int(num_fixed_nodes_var.get()))])

            subprocess.Popen(args, cwd=str(run_script.parent))
            status.set("Launched. Experiment running in a new window.")
        except Exception as e:
            status.set(f"Error: {e}")

    ttk.Button(frm, text="Start", command=on_start).grid(row=13, column=0, sticky="w", pady=12)
    ttk.Button(frm, text="Quit", command=root.destroy).grid(row=13, column=1, sticky="w", pady=12)

    frm.columnconfigure(1, weight=1)
    root.mainloop()


if __name__ == "__main__":
    main()
