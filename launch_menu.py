"""Small launcher UI for running the constraint visualisation study.

Run from the repository root with:

    python launch_menu.py

Choose the condition (C1–C4), graph preset, and fixed constraints.
Clicking **Start** runs the experiment and writes results under
./results/<condition>_<timestamp>/
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
    root.title("Graph Colouring Constraint Viz Launcher")
    root.geometry("520x530")

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

    # ── Main experimental presets ─────────────────────────────────────────
    _MAIN_LABELS = [
        "Easy 8-A  –  8-node CX (2 agents)",
        "Easy 8-B  –  8-node CX (2 agents)",
        "Easy 8-C  –  8-node CX (2 agents)",
        "Hard 8-A  –  8-node CX (2 agents)",
        "Hard 8-B  –  8-node CX (2 agents)",
        "Hard 8-C  –  8-node CX (2 agents)",
    ]
    # ── Dev/testing presets (shown only when "Testing modes" is ticked) ───
    _TESTING_LABELS = [
        "── Simple Constraints ──────────────",
        "Easy    –  Simple Constraints",
        "Tight   –  Simple Constraints",
        "Hard    –  Simple Constraints",
        "── Complex Constraints ─────────────",
        "Easy    –  Complex Constraints",
        "Medium  –  Complex Constraints",
        "Hard    –  Complex Constraints",
        "── Harder ───────────────────────────",
        "Easy+   –  Complex Constraints",
        "Hard (no fixed)  –  Complex Constraints",
        "Expert  –  All nodes cross-constrained",
        "Gauntlet  –  Dual-agent bottlenecks",
        "Super   –  8 nodes + complex domains",
        "Tight II  –  Simple Constraints",
        "Tight III  –  Simple Constraints",
        "Tight IV  –  Simple Constraints",
        "Trio    –  Three Agents",
        "Trio II –  Three Agents",
        "Trio CX    –  Three Agents",
        "Trio CX II –  Three Agents",
        "── Other test sizes ─────────────────",
        "Test XL  –  10-node CX (2 agents)",
        "Test Trio –  8-node CX (3 agents)",
    ]
    # All selectable labels (headers excluded automatically by _on_preset_change)
    _PRESET_LABELS = _MAIN_LABELS + _TESTING_LABELS

    _PRESET_CLI = {
        "Easy 8-A  –  8-node CX (2 agents)":         "cx_easy_8",
        "Easy 8-B  –  8-node CX (2 agents)":         "cx_easy_8_b",
        "Easy 8-C  –  8-node CX (2 agents)":         "cx_easy_8_c",
        "Hard 8-A  –  8-node CX (2 agents)":         "cx_hard_8",
        "Hard 8-B  –  8-node CX (2 agents)":         "cx_hard_8_b",
        "Hard 8-C  –  8-node CX (2 agents)":         "cx_hard_8_c",
        "Easy    –  Simple Constraints":              "easy",
        "Tight   –  Simple Constraints":              "tight",
        "Hard    –  Simple Constraints":              "hard",
        "Easy    –  Complex Constraints":             "cx_easy",
        "Medium  –  Complex Constraints":             "cx_medium",
        "Hard    –  Complex Constraints":             "cx_hard",
        "Easy+   –  Complex Constraints":             "cx_easy_plus",
        "Hard (no fixed)  –  Complex Constraints":   "cx_hard_free",
        "Expert  –  All nodes cross-constrained":    "cx_expert",
        "Gauntlet  –  Dual-agent bottlenecks":       "cx_gauntlet",
        "Super   –  8 nodes + complex domains":      "cx_super",
        "Tight II  –  Simple Constraints":           "tight2",
        "Tight III  –  Simple Constraints":          "tight3",
        "Tight IV  –  Simple Constraints":           "tight4",
        "Trio    –  Three Agents":                   "trio",
        "Trio II –  Three Agents":                   "trio_tight",
        "Trio CX    –  Three Agents":                "trio_cx",
        "Trio CX II –  Three Agents":                "trio_tight_cx",
        "Test XL  –  10-node CX (2 agents)":         "cx_test_10",
        "Test Trio –  8-node CX (3 agents)":         "cx_test_trio_8",
    }
    # Complex presets have pre-designed domains — fixed-node controls irrelevant
    _PRESET_EXPLICIT = {
        "Easy 8-A  –  8-node CX (2 agents)",
        "Easy 8-B  –  8-node CX (2 agents)",
        "Easy 8-C  –  8-node CX (2 agents)",
        "Hard 8-A  –  8-node CX (2 agents)",
        "Hard 8-B  –  8-node CX (2 agents)",
        "Hard 8-C  –  8-node CX (2 agents)",
        "Tight   –  Simple Constraints",
        "Easy    –  Complex Constraints",
        "Medium  –  Complex Constraints",
        "Hard    –  Complex Constraints",
        "Easy+   –  Complex Constraints",
        "Hard (no fixed)  –  Complex Constraints",
        "Expert  –  All nodes cross-constrained",
        "Gauntlet  –  Dual-agent bottlenecks",
        "Super   –  8 nodes + complex domains",
        "Tight II  –  Simple Constraints",
        "Tight III  –  Simple Constraints",
        "Tight IV  –  Simple Constraints",
        "Trio    –  Three Agents",
        "Trio II –  Three Agents",
        "Trio CX    –  Three Agents",
        "Trio CX II –  Three Agents",
        "Test XL  –  10-node CX (2 agents)",
        "Test Trio –  8-node CX (3 agents)",
    }

    # --- variables with saved defaults ---
    participant_name_var = tk.StringVar(value=saved_config.get("participant_name", ""))
    test_run_var = tk.BooleanVar(value=saved_config.get("test_run", False))
    condition_var = tk.StringVar(value=saved_config.get("condition", "C1"))
    testing_modes_var = tk.BooleanVar(value=saved_config.get("testing_modes", False))
    _saved_preset = saved_config.get("graph_preset", _MAIN_LABELS[0])
    # Migrate old/unknown saved values to the first main preset
    if _saved_preset not in _PRESET_CLI or _saved_preset.startswith("──"):
        _saved_preset = _MAIN_LABELS[0]
    graph_preset_var = tk.StringVar(value=_saved_preset)
    use_ui_var = tk.BooleanVar(value=saved_config.get("use_ui", True))
    use_llm_var = tk.BooleanVar(value=saved_config.get("use_llm", False))
    fixed_constraints_var = tk.BooleanVar(value=saved_config.get("fixed_constraints", True))
    # Default fixed nodes: 2 for Hard, 1 for Easy; irrelevant for explicit presets
    _cur = graph_preset_var.get()
    _preset_default_fixed = 2 if "Hard" in _cur else 1
    num_fixed_nodes_var = tk.IntVar(value=saved_config.get("num_fixed_nodes", _preset_default_fixed))

    # --- widgets ---
    row = 0
    ttk.Label(frm, text="Participant name").grid(row=row, column=0, sticky="w", pady=(0, 4))
    ttk.Entry(frm, textvariable=participant_name_var, width=24).grid(
        row=row, column=1, sticky="w", pady=(0, 4)
    )

    row += 1
    test_run_check = ttk.Checkbutton(
        frm,
        text="Test run  (saves to results/tempTest, overwritten each time)",
        variable=test_run_var,
    )
    test_run_check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 10))

    ttk.Separator(frm).grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    row += 2

    ttk.Label(frm, text="Condition").grid(row=row, column=0, sticky="w", pady=(0, 6))
    ttk.Combobox(
        frm,
        textvariable=condition_var,
        values=["C1", "C2", "C3", "C4", "C5", "C6"],
        state="readonly",
        width=22,
    ).grid(row=row, column=1, sticky="w", pady=(0, 6))

    row += 1
    ttk.Label(
        frm,
        text="C1=User-Centric Formulaic\nC2=Agent-Centric Formulaic\nC3=Human Domain Formulaic\nC4=UC Natural Language\nC5=AC Natural Language\nC6=Human Domain Natural Language",
        font=("Arial", 9),
        foreground="#555",
        justify="left",
    ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))

    row += 1
    ttk.Label(frm, text="Graph preset").grid(row=row, column=0, sticky="w", pady=(0, 4))
    preset_combo = ttk.Combobox(
        frm,
        textvariable=graph_preset_var,
        values=_MAIN_LABELS,
        state="readonly",
        width=22,
    )
    preset_combo.grid(row=row, column=1, sticky="w", pady=(0, 4))

    row += 1
    ttk.Label(
        frm,
        text="Simple: fixed nodes constrain one node to one colour.\nComplex: each node limited to 1–3 allowed colours.",
        font=("Arial", 9),
        foreground="#555",
        justify="left",
    ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))

    fixed_check_widget = ttk.Checkbutton(frm, text="Use fixed node constraints",
                                          variable=fixed_constraints_var)
    fixed_spin_label = ttk.Label(frm, text="Fixed nodes per cluster (0-3)")
    fixed_spin_widget = ttk.Spinbox(frm, from_=0, to=3, textvariable=num_fixed_nodes_var, width=8)

    def _on_preset_change(*_):
        sel = graph_preset_var.get()
        # If user somehow selected a header, revert to first main preset
        if sel not in _PRESET_CLI:
            graph_preset_var.set(_MAIN_LABELS[0])
            return
        is_explicit = sel in _PRESET_EXPLICIT
        if "Hard" in sel:
            num_fixed_nodes_var.set(2)
        else:
            num_fixed_nodes_var.set(1)
        state = "disabled" if is_explicit else "normal"
        fixed_check_widget.config(state=state)
        fixed_spin_label.config(foreground="#aaa" if is_explicit else "#000")
        fixed_spin_widget.config(state="disabled" if is_explicit else "normal")

    graph_preset_var.trace_add("write", _on_preset_change)

    def _on_testing_toggle(*_):
        if testing_modes_var.get():
            preset_combo["values"] = _MAIN_LABELS + _TESTING_LABELS
        else:
            preset_combo["values"] = _MAIN_LABELS
            # If a testing preset is active, revert to first main preset
            if graph_preset_var.get() not in set(_MAIN_LABELS):
                graph_preset_var.set(_MAIN_LABELS[0])

    testing_modes_var.trace_add("write", _on_testing_toggle)

    row += 1
    ttk.Checkbutton(
        frm,
        text="Show testing / dev presets",
        variable=testing_modes_var,
    ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))

    row += 1
    fixed_check_widget.grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 6))

    row += 1
    fixed_spin_label.grid(row=row, column=0, sticky="w", pady=(0, 10))
    fixed_spin_widget.grid(row=row, column=1, sticky="w", pady=(0, 10))

    # Apply initial state
    _on_testing_toggle()
    _on_preset_change()

    row += 1
    use_llm_check = ttk.Checkbutton(
        frm,
        text="Use LLM for NL summaries (C4/C5/C6 only)",
        variable=use_llm_var,
    )
    use_llm_check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 10))

    def _on_condition_change(*_):
        cond = condition_var.get()
        if cond in ("C4", "C5", "C6"):
            use_llm_var.set(True)          # Auto-enable LLM for NL conditions
            use_llm_check.config(state="normal")
        else:
            use_llm_var.set(False)         # Not applicable for formulaic conditions
            use_llm_check.config(state="disabled")

    condition_var.trace_add("write", _on_condition_change)
    _on_condition_change()  # Apply initial state

    sep = ttk.Separator(frm)
    sep.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=10)

    status = tk.StringVar(value="")
    ttk.Label(frm, textvariable=status).grid(row=row + 2, column=0, columnspan=2, sticky="w")

    def on_start() -> None:
        try:
            status.set("Launching…")
            root.update_idletasks()

            # Save current configuration
            current_config = {
                "participant_name": participant_name_var.get().strip(),
                "test_run": bool(test_run_var.get()),
                "condition": condition_var.get(),
                "graph_preset": graph_preset_var.get(),
                "use_ui": bool(use_ui_var.get()),
                "use_llm": bool(use_llm_var.get()),
                "fixed_constraints": bool(fixed_constraints_var.get()),
                "num_fixed_nodes": int(num_fixed_nodes_var.get()),
                "testing_modes": bool(testing_modes_var.get()),
            }
            try:
                with open(config_path, "w") as f:
                    json.dump(current_config, f, indent=2)
            except Exception:
                pass

            run_script = Path(__file__).resolve().with_name("run_experiment.py")
            args = [
                sys.executable,
                str(run_script),
                "--condition",
                condition_var.get(),
                "--use-ui" if bool(use_ui_var.get()) else "--no-ui",
            ]
            if bool(fixed_constraints_var.get()):
                args.append("--fixed-constraints")
                args.extend(["--num-fixed-nodes", str(int(num_fixed_nodes_var.get()))])
            if bool(use_llm_var.get()):
                args.append("--use-llm")
            _preset_cli = _PRESET_CLI.get(graph_preset_var.get(), "easy")
            args.extend(["--graph-preset", _preset_cli])
            _pname = participant_name_var.get().strip()
            if _pname:
                args.extend(["--participant-name", _pname])
            if bool(test_run_var.get()):
                args.append("--test-run")

            subprocess.Popen(args, cwd=str(run_script.parent))
            status.set("Launched. Experiment running in a new window.")
        except Exception as e:
            status.set(f"Error: {e}")

    ttk.Button(frm, text="Start", command=on_start).grid(row=row + 3, column=0, sticky="w", pady=12)
    ttk.Button(frm, text="Quit", command=root.destroy).grid(row=row + 3, column=1, sticky="w", pady=12)

    frm.columnconfigure(1, weight=1)
    root.mainloop()


if __name__ == "__main__":
    main()
