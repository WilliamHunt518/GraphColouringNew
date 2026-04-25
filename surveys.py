"""
surveys.py — Tkinter questionnaire windows for the drone channel assignment study.

Three entry points:
    run_demographic_survey(mon)              -> dict | None
    run_trial_survey(num, label, mon)        -> dict | None
    run_summary_survey(scenario_infos, mon)  -> dict | None

Each function creates a fresh tk.Tk root, runs its mainloop, and returns the
collected responses as a plain dict (or None if the window was closed without
submitting).  They are designed to be called from inside run_study() while
pygame is initialised but before/between/after trials.
"""
from __future__ import annotations

import datetime
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Tuple

WINDOW_W = 720


# ── Shared layout helpers ─────────────────────────────────────────────────────

def _scrollable_form(root: tk.Tk) -> tk.Frame:
    """Attach a vertically-scrollable canvas to root; return the inner frame."""
    canvas = tk.Canvas(root, highlightthickness=0)
    vsb = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = tk.Frame(canvas)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner(_e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas(e):
        canvas.itemconfig(win_id, width=e.width)

    inner.bind("<Configure>", _on_inner)
    canvas.bind("<Configure>", _on_canvas)
    canvas.bind_all("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
    return inner


def _heading(parent: tk.Frame, text: str, row: int) -> int:
    tk.Label(parent, text=text, font=("Segoe UI", 12, "bold"),
             anchor="w").grid(row=row, column=0, columnspan=12,
                              sticky="ew", padx=12, pady=(14, 0))
    ttk.Separator(parent, orient="horizontal").grid(
        row=row + 1, column=0, columnspan=12, sticky="ew", padx=12, pady=(2, 4))
    return row + 2


def _qlabel(parent: tk.Frame, text: str, row: int) -> int:
    tk.Label(parent, text=text, wraplength=WINDOW_W - 50,
             justify="left", anchor="w").grid(
        row=row, column=0, columnspan=12,
        sticky="w", padx=22, pady=(8, 1))
    return row + 1


def _likert(parent: tk.Frame, text: str, row: int, var: tk.IntVar,
            lo: str = "Not at all", hi: str = "Extremely", n: int = 7) -> int:
    row = _qlabel(parent, text, row)
    f = tk.Frame(parent)
    f.grid(row=row, column=0, columnspan=12, sticky="w", padx=30, pady=(0, 4))
    tk.Label(f, text=lo, foreground="#666",
             font=("Segoe UI", 9)).grid(row=0, column=0, padx=(0, 6))
    for i in range(1, n + 1):
        tk.Radiobutton(f, text=str(i), variable=var, value=i,
                       indicatoron=True).grid(row=0, column=i, padx=2)
    tk.Label(f, text=hi, foreground="#666",
             font=("Segoe UI", 9)).grid(row=0, column=n + 1, padx=(6, 0))
    return row + 1


def _tlx_item(parent: tk.Frame, text: str, row: int,
              var: tk.IntVar, lo: str = "Very Low", hi: str = "Very High") -> int:
    row = _qlabel(parent, text, row)
    f = tk.Frame(parent)
    f.grid(row=row, column=0, columnspan=12, sticky="w", padx=30, pady=(0, 4))
    tk.Label(f, text=lo, foreground="#666",
             font=("Segoe UI", 9)).grid(row=0, column=0, padx=(0, 6))
    tk.Scale(f, variable=var, from_=1, to=20, orient="horizontal",
             length=320, resolution=1, showvalue=True,
             font=("Segoe UI", 9)).grid(row=0, column=1)
    tk.Label(f, text=hi, foreground="#666",
             font=("Segoe UI", 9)).grid(row=0, column=2, padx=(6, 0))
    return row + 1


def _radio(parent: tk.Frame, text: str, row: int, var: tk.StringVar,
           choices: List[str]) -> int:
    row = _qlabel(parent, text, row)
    f = tk.Frame(parent)
    f.grid(row=row, column=0, columnspan=12, sticky="w", padx=30, pady=(0, 4))
    for i, c in enumerate(choices):
        tk.Radiobutton(f, text=c, variable=var, value=c).grid(
            row=i, column=0, sticky="w", pady=1)
    return row + 1


def _entry(parent: tk.Frame, text: str, row: int, var: tk.StringVar) -> int:
    row = _qlabel(parent, text, row)
    ttk.Entry(parent, textvariable=var, width=14).grid(
        row=row, column=0, columnspan=12, sticky="w", padx=30, pady=(0, 4))
    return row + 1


def _textbox(parent: tk.Frame, text: str, row: int,
             var: tk.StringVar, height: int = 4) -> int:
    row = _qlabel(parent, text, row)
    box = tk.Text(parent, height=height, wrap="word",
                  relief="solid", borderwidth=1, font=("Segoe UI", 10))
    box.grid(row=row, column=0, columnspan=12,
             sticky="ew", padx=30, pady=(0, 6))
    box.bind("<KeyRelease>", lambda _: var.set(box.get("1.0", "end-1c")))
    return row + 1


def _center(win: tk.Tk, mon: Optional[Tuple[int, int, int, int]]) -> None:
    win.update_idletasks()
    ww, wh = win.winfo_width(), win.winfo_height()
    if mon:
        x = mon[0] + (mon[2] - ww) // 2
        y = mon[1] + (mon[3] - wh) // 2
    else:
        x = (win.winfo_screenwidth() - ww) // 2
        y = (win.winfo_screenheight() - wh) // 2
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


def _submit_btn(parent: tk.Frame, row: int, text: str, cmd) -> None:
    f = tk.Frame(parent)
    f.grid(row=row, column=0, columnspan=12, pady=20)
    ttk.Button(f, text=text, command=cmd, width=18).pack()


# ── Pre-study demographics ────────────────────────────────────────────────────

def run_demographic_survey(
    mon: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[dict]:
    """Show pre-study demographics form. Returns responses dict or None."""
    result: Optional[dict] = None

    root = tk.Tk()
    root.title("Pre-Study Survey")
    root.geometry(f"{WINDOW_W}x620")
    root.resizable(False, True)

    inner = _scrollable_form(root)
    r = 0

    tk.Label(inner, text="Pre-Study Questionnaire",
             font=("Segoe UI", 15, "bold")).grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(16, 2))
    r += 1
    tk.Label(inner, text="Please answer the following before we begin.",
             foreground="#555").grid(row=r, column=0, columnspan=12,
                                     sticky="w", padx=12, pady=(0, 8))
    r += 1

    r = _heading(inner, "About you", r)

    age_var = tk.StringVar()
    r = _entry(inner, "Age:", r, age_var)

    gender_var = tk.StringVar()
    r = _radio(inner, "Gender:", r, gender_var,
               ["Man", "Woman", "Non-binary", "Prefer not to say"])

    edu_var = tk.StringVar()
    r = _radio(inner, "Highest level of education completed:", r, edu_var,
               ["High school / A-levels", "Bachelor's degree",
                "Master's degree", "Doctoral degree", "Other"])

    r = _heading(inner, "Experience with technology", r)

    tech_var = tk.IntVar(value=4)
    r = _likert(inner,
                "How comfortable are you with technology in general?",
                r, tech_var, lo="Not comfortable", hi="Very comfortable")

    ai_var = tk.IntVar(value=4)
    r = _likert(inner,
                "How often do you use AI-based tools "
                "(e.g. virtual assistants, recommendation systems)?",
                r, ai_var, lo="Never", hi="Daily")

    drone_var = tk.IntVar(value=1)
    r = _likert(inner,
                "How much experience do you have with drone operations "
                "or air-traffic management?",
                r, drone_var, lo="None", hi="Expert")

    def _submit():
        nonlocal result
        result = {
            "age":              age_var.get().strip(),
            "gender":           gender_var.get(),
            "education":        edu_var.get(),
            "tech_comfort":     tech_var.get(),
            "ai_experience":    ai_var.get(),
            "drone_experience": drone_var.get(),
            "timestamp":        datetime.datetime.now().isoformat(),
        }
        root.destroy()

    _submit_btn(inner, r, "Continue →", _submit)

    _center(root, mon)
    root.mainloop()
    return result


# ── Per-trial survey (TLX + Trust + Acceptance) ───────────────────────────────

_TLX_ITEMS = [
    ("tlx_mental",
     "Mental Demand — How much mental effort was required?"),
    ("tlx_physical",
     "Physical Demand — How much physical activity was required?"),
    ("tlx_temporal",
     "Temporal Demand — How much time pressure did you feel?"),
    ("tlx_performance",
     "Performance — How successful were you at achieving the goal? "
     "(Low = perfect, High = failure)"),
    ("tlx_effort",
     "Effort — How hard did you have to work?"),
    ("tlx_frustration",
     "Frustration — How insecure, irritated, or stressed did you feel?"),
]

# Abridged Jian, Bisantz & Drury (2000) — items 1-2 are distrust (reversed scoring)
_TRUST_ITEMS = [
    ("trust_suspicious",
     "I was suspicious of the assistant's recommendations."),
    ("trust_wary",
     "I was wary of following the assistant's suggestions."),
    ("trust_confident",
     "I was confident the assistant was giving good recommendations."),
    ("trust_reliable",
     "The assistant's suggestions were reliable."),
    ("trust_overall",
     "I felt I could trust the assistant."),
    ("trust_accepted",
     "I generally accepted the assistant's recommendations without modifying them."),
]

_TAM_ITEMS = [
    ("tam_improved",
     "Using the tools improved my performance on the task."),
    ("tam_easy",
     "The tools were easy to use."),
    ("tam_useful",
     "I found the tools genuinely useful."),
    ("tam_would_use",
     "I would want to use these tools in a real scenario."),
]


def run_trial_survey(
    scenario_num: int,
    scenario_label: str,
    mon: Optional[Tuple[int, int, int, int]] = None,
    show_tlx: bool = True,
    show_trust: bool = True,
    show_tam: bool = True,
) -> Optional[dict]:
    """Post-trial questionnaire (TLX + Trust + TAM). Returns dict or None."""
    result: Optional[dict] = None

    root = tk.Tk()
    root.title(f"Scenario {scenario_num} — Feedback")
    root.geometry(f"{WINDOW_W}x680")
    root.resizable(False, True)

    inner = _scrollable_form(root)
    r = 0

    tk.Label(inner, text=f"Scenario {scenario_num} — Feedback",
             font=("Segoe UI", 15, "bold")).grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(16, 2))
    r += 1
    tk.Label(inner,
             text="Please rate the scenario you just completed. "
                  "There are no right or wrong answers.",
             foreground="#555").grid(row=r, column=0, columnspan=12,
                                     sticky="w", padx=12, pady=(0, 8))
    r += 1

    tlx_vars: Dict[str, tk.IntVar] = {}
    if show_tlx:
        r = _heading(inner, "Workload  (NASA Task Load Index)", r)
        for key, text in _TLX_ITEMS:
            v = tk.IntVar(value=10)
            tlx_vars[key] = v
            r = _tlx_item(inner, text, r, v)

    trust_vars: Dict[str, tk.IntVar] = {}
    if show_trust:
        r = _heading(inner, "Trust in the Assistant", r)
        for key, text in _TRUST_ITEMS:
            v = tk.IntVar(value=4)
            trust_vars[key] = v
            r = _likert(inner, text, r, v, lo="Not at all", hi="Extremely")

    tam_vars: Dict[str, tk.IntVar] = {}
    if show_tam:
        r = _heading(inner, "Tool Usefulness", r)
        for key, text in _TAM_ITEMS:
            v = tk.IntVar(value=4)
            tam_vars[key] = v
            r = _likert(inner, text, r, v,
                        lo="Strongly disagree", hi="Strongly agree")

    r = _heading(inner, "Open-ended", r)
    comments_var = tk.StringVar()
    r = _textbox(inner,
                 "Any other comments about this scenario? (optional)",
                 r, comments_var, height=4)

    def _submit():
        nonlocal result
        result = {
            "scenario_num":   scenario_num,
            "scenario_label": scenario_label,
            **{k: v.get() for k, v in tlx_vars.items()},
            **{k: v.get() for k, v in trust_vars.items()},
            **{k: v.get() for k, v in tam_vars.items()},
            "comments":       comments_var.get().strip(),
            "timestamp":      datetime.datetime.now().isoformat(),
        }
        root.destroy()

    _submit_btn(inner, r, "Continue →", _submit)

    _center(root, mon)
    root.mainloop()
    return result


# ── Post-study summary survey ─────────────────────────────────────────────────

def run_summary_survey(
    scenario_infos: List[Dict],   # [{"num": 1, "label": "Easy-perfect"}, ...]
    mon: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[dict]:
    """
    Final summary questionnaire shown once after all trials.

    Refers to scenarios by ordinal number only ("Scenario 1", "Scenario 2", …).
    The mapping from ordinal → actual trial label is saved in the result under
    "scenario_map", so the researcher can decode responses offline.
    """
    result: Optional[dict] = None

    root = tk.Tk()
    root.title("Summary Questionnaire")
    root.geometry(f"{WINDOW_W}x740")
    root.resizable(False, True)

    inner = _scrollable_form(root)
    r = 0

    tk.Label(inner, text="Summary Questionnaire",
             font=("Segoe UI", 15, "bold")).grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(16, 2))
    r += 1
    tk.Label(inner,
             text="Now that you've completed all scenarios, please reflect on "
                  "your experience overall.",
             foreground="#555", wraplength=WINDOW_W - 40, justify="left").grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(0, 8))
    r += 1

    # ── Per-scenario ratings ──────────────────────────────────────────────────
    r = _heading(inner, "Rating each scenario", r)

    tk.Label(inner,
             text='"Scenario 1" is the first scenario you completed, '
                  '"Scenario 2" the second, and so on.',
             foreground="#555", wraplength=WINDOW_W - 40, justify="left").grid(
        row=r, column=0, columnspan=12, sticky="w", padx=22, pady=(0, 8))
    r += 1

    per_vars: Dict[int, Dict[str, tk.IntVar]] = {}
    for info in scenario_infos:
        num = info["num"]
        per_vars[num] = {}

        tk.Label(inner, text=f"Scenario {num}",
                 font=("Segoe UI", 11, "bold"), anchor="w").grid(
            row=r, column=0, columnspan=12,
            sticky="w", padx=22, pady=(10, 2))
        r += 1

        v = tk.IntVar(value=4)
        per_vars[num]["difficulty"] = v
        r = _likert(inner, "How difficult was this scenario?",
                    r, v, lo="Very easy", hi="Very difficult")

        v = tk.IntVar(value=4)
        per_vars[num]["tool_usefulness"] = v
        r = _likert(inner,
                    "How useful were the tools (Suggest / Auto-assign)?",
                    r, v, lo="Not useful", hi="Very useful")

        v = tk.IntVar(value=4)
        per_vars[num]["manual_frequency"] = v
        r = _likert(inner,
                    "How often did you manually adjust channel assignments "
                    "rather than using the tools?",
                    r, v, lo="Rarely", hi="Very often")

        v = tk.IntVar(value=4)
        per_vars[num]["confidence"] = v
        r = _likert(inner,
                    "How confident did you feel in your decisions?",
                    r, v, lo="Not confident", hi="Very confident")

    # ── Open-ended reflections ────────────────────────────────────────────────
    r = _heading(inner, "Reflections", r)

    factors_var = tk.StringVar()
    r = _textbox(inner,
                 "What factors influenced how often you manually adjusted drone "
                 "channels? (Think about what made you intervene vs. use the tools.)",
                 r, factors_var, height=5)

    diff_var = tk.StringVar()
    r = _textbox(inner,
                 "Did you notice any differences between the scenarios? "
                 "If so, describe them.",
                 r, diff_var, height=5)

    pref_var = tk.StringVar()
    r = _textbox(inner,
                 "Which scenario felt most natural or manageable, and why?",
                 r, pref_var, height=4)

    other_var = tk.StringVar()
    r = _textbox(inner, "Any other feedback? (optional)",
                 r, other_var, height=3)

    def _submit():
        nonlocal result
        d: dict = {
            "scenario_map": {str(info["num"]): info["label"]
                              for info in scenario_infos},
            "timestamp": datetime.datetime.now().isoformat(),
        }
        for num, vars_ in per_vars.items():
            for key, var in vars_.items():
                d[f"scenario_{num}_{key}"] = var.get()
        d["factors_influencing_manual"] = factors_var.get().strip()
        d["differences_noticed"]        = diff_var.get().strip()
        d["preferred_scenario_reason"]  = pref_var.get().strip()
        d["other_comments"]             = other_var.get().strip()
        result = d
        root.destroy()

    _submit_btn(inner, r, "Finish →", _submit)

    _center(root, mon)
    root.mainloop()
    return result
