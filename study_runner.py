"""
study_runner.py — researcher setup window + sequential trial orchestrator.

    python study_runner.py
"""
from __future__ import annotations

import json
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

import pygame

from robot_world import COMPLEXITY_PRESETS, SPEED_MIN, SPEED_MAX, SWITCH_DURATION


# ── Trial configuration ───────────────────────────────────────────────────────

@dataclass
class TrialConfig:
    label: str
    complexity: str = "medium"
    seed: int = 42
    duration: float = 90.0
    epsilon: float = 0.20
    switch_duration: float = SWITCH_DURATION
    n_robots: Optional[int] = None    # None → use complexity preset
    v_min: Optional[float] = None
    v_max: Optional[float] = None
    is_tutorial: bool = False


@dataclass
class StudyConfig:
    participant_id: str
    trials: List[TrialConfig] = field(default_factory=list)
    output_root: str = "results/participants"


# ── Presets ───────────────────────────────────────────────────────────────────

STUDY_PRESETS: Dict[str, TrialConfig] = {
    "Tutorial":         TrialConfig("Tutorial",  is_tutorial=True, epsilon=0.0, duration=0),
    "Easy — perfect":   TrialConfig("Easy-perfect",   complexity="easy",   epsilon=0.0,  duration=90),
    "Easy — noisy":     TrialConfig("Easy-noisy",     complexity="easy",   epsilon=0.4,  duration=90),
    "Medium — perfect": TrialConfig("Medium-perfect", complexity="medium", epsilon=0.0,  duration=120),
    "Medium — noisy":   TrialConfig("Medium-noisy",   complexity="medium", epsilon=0.4,  duration=120),
    "Hard — perfect":   TrialConfig("Hard-perfect",   complexity="hard",   epsilon=0.0,  duration=150),
    "Hard — noisy":     TrialConfig("Hard-noisy",     complexity="hard",   epsilon=0.4,  duration=150),
    "Custom…":          TrialConfig("Custom"),
}

_PRESET_NAMES = list(STUDY_PRESETS)
_CONFIG_PATH  = Path.home() / ".drone_study_config.json"

_DEFAULT_TRIALS = ["Tutorial", "Easy — perfect", "Medium — noisy"]


# ── Setup window ──────────────────────────────────────────────────────────────

class StudySetupWindow:
    """Researcher-facing Tkinter window for configuring a study session."""

    def __init__(self) -> None:
        self.config: Optional[StudyConfig] = None

        self._root = tk.Tk()
        self._root.title("Drone Study — Researcher Setup")
        self._root.resizable(False, False)

        self._saved = self._load_saved_config()
        self._build_ui()
        self._root.mainloop()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_saved_config(self) -> dict:
        try:
            return json.loads(_CONFIG_PATH.read_text())
        except Exception:
            return {}

    def _save_config(self, data: dict) -> None:
        try:
            _CONFIG_PATH.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = self._root
        pad = {"padx": 10, "pady": 4}
        row = 0

        # ── Participant ID ─────────────────────────────────────────────────────
        ttk.Label(root, text="Participant ID:").grid(row=row, column=0, sticky="e", **pad)
        self._pid_var = tk.StringVar()
        ttk.Entry(root, textvariable=self._pid_var, width=20).grid(
            row=row, column=1, columnspan=2, sticky="w", **pad)
        row += 1

        ttk.Separator(root, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        # ── Trial list header ─────────────────────────────────────────────────
        ttk.Label(root, text="Trials", font=("TkDefaultFont", 10, "bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(4, 0))
        row += 1

        # Container for trial rows
        self._trials_frame = ttk.Frame(root)
        self._trials_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=4)
        row += 1

        self._trial_rows: List[_TrialRow] = []
        defaults = self._saved.get("trials", _DEFAULT_TRIALS)
        for preset_name in defaults:
            self._add_trial_row(preset_name)

        # ── Add / Remove buttons ──────────────────────────────────────────────
        btn_frame = ttk.Frame(root)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=10, pady=2)
        ttk.Button(btn_frame, text="+ Add Trial", command=self._add_trial_row, width=12).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="− Remove Last", command=self._remove_last_row, width=14).pack(side="left")
        row += 1

        ttk.Separator(root, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=6)
        row += 1

        # ── Start button ──────────────────────────────────────────────────────
        ttk.Button(root, text="▶  Start Study", command=self._start, width=18).grid(
            row=row, column=0, columnspan=3, pady=8)

    def _add_trial_row(self, preset_name: str = "Medium — perfect") -> None:
        if len(self._trial_rows) >= 6:
            return
        idx = len(self._trial_rows)
        row = _TrialRow(self._trials_frame, idx, preset_name)
        self._trial_rows.append(row)

    def _remove_last_row(self) -> None:
        if len(self._trial_rows) <= 1:
            return
        row = self._trial_rows.pop()
        row.destroy()

    # ── Start handler ─────────────────────────────────────────────────────────

    def _start(self) -> None:
        pid = self._pid_var.get().strip()
        if not pid:
            pid = time.strftime("P%Y%m%d_%H%M%S")
        if not self._trial_rows:
            messagebox.showwarning("No Trials", "Add at least one trial.")
            return

        trials: List[TrialConfig] = []
        for tr in self._trial_rows:
            cfg = tr.build_config()
            if cfg is None:
                return   # validation error already shown
            trials.append(cfg)

        self._save_config({"trials": [tr.preset_name for tr in self._trial_rows]})

        self.config = StudyConfig(participant_id=pid, trials=trials)
        self._root.destroy()


class _TrialRow:
    """One row in the trial list."""

    def __init__(self, parent: ttk.Frame, idx: int, preset_name: str) -> None:
        self._parent = parent
        self._idx    = idx
        self.preset_name = preset_name

        self._frame = ttk.Frame(parent)
        self._frame.grid(row=idx, column=0, sticky="ew", pady=2)

        ttk.Label(self._frame, text=f"Trial {idx + 1}:", width=8).grid(
            row=0, column=0, sticky="e", padx=(0, 4))

        self._preset_var = tk.StringVar(value=preset_name)
        self._cb = ttk.Combobox(
            self._frame, textvariable=self._preset_var,
            values=_PRESET_NAMES, state="readonly", width=20,
        )
        self._cb.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self._preset_var.trace_add("write", self._on_preset_change)

        # Custom fields (hidden unless "Custom…" selected)
        self._custom_frame = ttk.Frame(self._frame)
        self._custom_frame.grid(row=1, column=0, columnspan=6, sticky="w", padx=20, pady=(0, 2))

        def _spinbox(label: str, col: int, default, frm, to, inc, fmt=None, width=7) -> tk.Variable:
            ttk.Label(self._custom_frame, text=label).grid(row=0, column=col * 2, sticky="e", padx=4)
            if isinstance(default, float):
                var = tk.DoubleVar(value=default)
            else:
                var = tk.IntVar(value=default)
            kw = dict(from_=frm, to=to, increment=inc, textvariable=var, width=width)
            if fmt:
                kw["format"] = fmt
            ttk.Spinbox(self._custom_frame, **kw).grid(row=0, column=col * 2 + 1, sticky="w")
            return var

        self._seed_var     = _spinbox("Seed:",       0, 42,   0,   99999, 1)
        self._dur_var      = _spinbox("Duration(s):", 1, 90.0, 30,  300,  10, "%.0f")
        self._eps_var      = _spinbox("Noise(ε):",   2, 0.20, 0.0, 1.0,  0.05, "%.2f")
        self._sw_var       = _spinbox("SwitchDly:",  3, 3.0,  0.0, 10.0, 0.5, "%.1f")
        self._cpx_var      = tk.StringVar(value="medium")
        ttk.Label(self._custom_frame, text="Complexity:").grid(row=0, column=8, sticky="e", padx=4)
        ttk.Combobox(
            self._custom_frame, textvariable=self._cpx_var,
            values=list(COMPLEXITY_PRESETS), state="readonly", width=8,
        ).grid(row=0, column=9, sticky="w")

        self._custom_frame.grid_remove()   # hidden by default
        self._on_preset_change()

    @property
    def preset_name(self) -> str:
        return getattr(self, "_preset_var", None) and self._preset_var.get() or self.__dict__.get("_init_preset", "")

    @preset_name.setter
    def preset_name(self, v: str) -> None:
        self._init_preset = v

    def _on_preset_change(self, *_) -> None:
        name = self._preset_var.get()
        self.preset_name = name
        if name == "Custom…":
            self._custom_frame.grid()
        else:
            self._custom_frame.grid_remove()

    def build_config(self) -> Optional[TrialConfig]:
        name = self._preset_var.get()
        if name != "Custom…":
            preset = STUDY_PRESETS[name]
            # Return a copy so mutations don't affect the shared template
            return TrialConfig(
                label=preset.label,
                complexity=preset.complexity,
                seed=preset.seed,
                duration=preset.duration,
                epsilon=preset.epsilon,
                switch_duration=preset.switch_duration,
                n_robots=preset.n_robots,
                v_min=preset.v_min,
                v_max=preset.v_max,
                is_tutorial=preset.is_tutorial,
            )

        # Custom — validate
        try:
            dur = float(self._dur_var.get())
            eps = float(self._eps_var.get())
            sw  = float(self._sw_var.get())
            seed = int(self._seed_var.get())
        except (ValueError, tk.TclError):
            messagebox.showwarning("Bad input", f"Trial {self._idx + 1}: invalid numeric value.")
            return None

        cpx = self._cpx_var.get()
        n_default, vmin_default, vmax_default = COMPLEXITY_PRESETS[cpx]
        return TrialConfig(
            label=f"Custom-{self._idx + 1}",
            complexity=cpx,
            seed=seed,
            duration=dur,
            epsilon=eps,
            switch_duration=sw,
            n_robots=n_default,
            v_min=vmin_default,
            v_max=vmax_default,
        )

    def destroy(self) -> None:
        self._frame.destroy()


# ── Inter-trial / completion screens ─────────────────────────────────────────

def _show_inter_trial_screen(
    screen: pygame.Surface,
    trial_idx: int,
    total: int,
    prev_result: Optional[dict],
) -> None:
    """Blocking mini event-loop: full-screen between-trial card. Advances on SPACE."""
    font_big   = pygame.font.SysFont("Arial", 44, bold=True)
    font_med   = pygame.font.SysFont("Arial", 28)
    font_small = pygame.font.SysFont("Arial", 22)

    w, h = screen.get_size()
    clock = pygame.time.Clock()

    # Build lines
    heading = f"Trial {trial_idx} of {total} complete" if trial_idx > 0 else f"Starting trial {trial_idx + 1} of {total}"
    lines = []
    if prev_result:
        clash_pct = prev_result.get("clash_pct", 0.0)
        elapsed   = prev_result.get("elapsed", 0.0)
        lines.append(f"Clash time: {clash_pct:.1f}%  ({elapsed:.0f}s)")

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    return
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    raise SystemExit

        screen.fill((12, 14, 22))

        # Card
        card_w, card_h = 680, 300
        card_x = (w - card_w) // 2
        card_y = (h - card_h) // 2
        card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        card_surf.fill((25, 30, 55, 230))
        pygame.draw.rect(card_surf, (80, 130, 240), (0, 0, card_w, card_h), 2, border_radius=12)
        screen.blit(card_surf, (card_x, card_y))

        cx = w // 2

        s = font_big.render(heading, True, (220, 235, 255))
        screen.blit(s, s.get_rect(centerx=cx, centery=card_y + 70))

        y_off = card_y + 140
        for line in lines:
            s = font_med.render(line, True, (180, 210, 255))
            screen.blit(s, s.get_rect(centerx=cx, centery=y_off))
            y_off += 38

        next_label = f"Trial {trial_idx + 1} of {total}"
        s = font_small.render(f"Next: {next_label}", True, (140, 180, 220))
        screen.blit(s, s.get_rect(centerx=cx, centery=card_y + card_h - 70))

        hint = font_small.render("Press SPACE to begin", True, (100, 220, 140))
        screen.blit(hint, hint.get_rect(centerx=cx, centery=card_y + card_h - 38))

        pygame.display.flip()
        clock.tick(30)


def _show_completion_screen(screen: pygame.Surface, results: List[dict]) -> None:
    """Final screen shown after all trials. ESC or SPACE to quit."""
    font_big   = pygame.font.SysFont("Arial", 48, bold=True)
    font_med   = pygame.font.SysFont("Arial", 26)
    font_small = pygame.font.SysFont("Arial", 20)

    w, h = screen.get_size()
    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_SPACE, pygame.K_ESCAPE, pygame.K_RETURN):
                    return

        screen.fill((12, 14, 22))

        cx = w // 2
        s = font_big.render("Study Complete", True, (140, 255, 140))
        screen.blit(s, s.get_rect(centerx=cx, centery=h // 2 - 120))

        s = font_med.render("Thank you for participating!", True, (200, 220, 255))
        screen.blit(s, s.get_rect(centerx=cx, centery=h // 2 - 60))

        y = h // 2
        for i, res in enumerate(results):
            label     = res.get("complexity", f"Trial {i + 1}")
            clash_pct = res.get("clash_pct", 0.0)
            completed = res.get("completed", False)
            status    = "✓" if completed else "—"
            line = f"  {status}  {label}   clash: {clash_pct:.1f}%"
            col  = (160, 255, 160) if completed else (200, 200, 200)
            s = font_small.render(line, True, col)
            screen.blit(s, s.get_rect(centerx=cx, centery=y))
            y += 30

        hint = font_small.render("Press SPACE or ESC to exit", True, (120, 160, 200))
        screen.blit(hint, hint.get_rect(centerx=cx, centery=h - 50))

        pygame.display.flip()
        clock.tick(30)


# ── Study orchestrator ────────────────────────────────────────────────────────

def run_study(config: StudyConfig) -> None:
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("Drone Channel Assignment — Study")

    ts = time.strftime("%Y%m%d_%H%M%S")
    pid = config.participant_id
    out_root = Path(config.output_root) / f"{pid}_{ts}"
    out_root.mkdir(parents=True, exist_ok=True)

    # Write metadata before first trial
    meta = {
        "participant_id": pid,
        "start_time": ts,
        "n_trials": len(config.trials),
        "trials": [
            {
                "label": t.label,
                "complexity": t.complexity,
                "seed": t.seed,
                "duration": t.duration,
                "epsilon": t.epsilon,
                "switch_duration": t.switch_duration,
                "is_tutorial": t.is_tutorial,
            }
            for t in config.trials
        ],
    }
    (out_root / "study_metadata.json").write_text(json.dumps(meta, indent=2))

    from robot_game import run_game
    from tutorial import run_tutorial

    results: List[dict] = []
    total = len(config.trials)

    try:
        for i, trial in enumerate(config.trials):
            # Inter-trial screen (skip before first trial)
            if i > 0:
                _show_inter_trial_screen(screen, i, total, results[-1] if results else None)

            trial_dir = out_root / f"trial_{i + 1:02d}_{trial.label}"
            trial_dir.mkdir(parents=True, exist_ok=True)

            if trial.is_tutorial:
                result = run_tutorial(
                    seed=trial.seed,
                    screen=screen,
                    output_dir=str(trial_dir),
                )
            else:
                # Resolve n_robots / v_min / v_max from complexity preset if not overridden
                n_default, vmin_default, vmax_default = COMPLEXITY_PRESETS[trial.complexity]
                result = run_game(
                    seed=trial.seed,
                    n_robots=trial.n_robots or n_default,
                    duration=trial.duration,
                    v_min=trial.v_min or vmin_default,
                    v_max=trial.v_max or vmax_default,
                    epsilon=trial.epsilon,
                    complexity=trial.complexity,
                    switch_duration=trial.switch_duration,
                    study_mode=True,
                    output_dir=str(trial_dir),
                    screen=screen,
                )

            result = result or {}
            results.append(result)

        _show_completion_screen(screen, results)

    finally:
        # Write summary regardless of whether study finished cleanly
        summary = {
            "participant_id": pid,
            "end_time": time.strftime("%Y%m%d_%H%M%S"),
            "n_completed": len(results),
            "n_total": total,
            "trials": results,
        }
        (out_root / "study_summary.json").write_text(json.dumps(summary, indent=2))
        pygame.quit()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    window = StudySetupWindow()
    if window.config is not None:
        run_study(window.config)


if __name__ == "__main__":
    main()
