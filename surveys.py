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
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Tuple

WINDOW_W = 1380

_F_BODY   = ("Segoe UI", 18)
_F_LABEL  = ("Segoe UI", 17, "bold")
_F_ASIDE  = ("Segoe UI", 16)
_F_SMALL  = ("Segoe UI", 16)


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
    tk.Label(parent, text=text, font=("Segoe UI", 21, "bold"),
             anchor="w").grid(row=row, column=0, columnspan=12,
                              sticky="ew", padx=12, pady=(20, 0))
    ttk.Separator(parent, orient="horizontal").grid(
        row=row + 1, column=0, columnspan=12, sticky="ew", padx=12, pady=(4, 8))
    return row + 2


def _qlabel(parent: tk.Frame, text: str, row: int) -> int:
    tk.Label(parent, text=text, wraplength=WINDOW_W - 60, font=_F_BODY,
             justify="left", anchor="w").grid(
        row=row, column=0, columnspan=12,
        sticky="w", padx=22, pady=(12, 2))
    return row + 1


def _likert(parent: tk.Frame, text: str, row: int, var: tk.IntVar,
            lo: str = "Not at all", hi: str = "Extremely", n: int = 7) -> int:
    row = _qlabel(parent, text, row)
    f = tk.Frame(parent)
    f.grid(row=row, column=0, columnspan=12, sticky="w", padx=30, pady=(0, 8))
    tk.Label(f, text=lo, foreground="#555",
             font=_F_SMALL).grid(row=0, column=0, padx=(0, 10))
    for i in range(1, n + 1):
        tk.Radiobutton(f, text=str(i), variable=var, value=i,
                       font=_F_SMALL, indicatoron=True).grid(row=0, column=i, padx=5)
    tk.Label(f, text=hi, foreground="#555",
             font=_F_SMALL).grid(row=0, column=n + 1, padx=(10, 0))
    return row + 1


def _tlx_item(parent: tk.Frame, text: str, row: int,
              var: tk.IntVar, lo: str = "Very Low", hi: str = "Very High") -> int:
    row = _qlabel(parent, text, row)
    f = tk.Frame(parent)
    f.grid(row=row, column=0, columnspan=12, sticky="w", padx=30, pady=(0, 8))
    tk.Label(f, text=lo, foreground="#555",
             font=_F_SMALL).grid(row=0, column=0, padx=(0, 10))
    tk.Scale(f, variable=var, from_=1, to=20, orient="horizontal",
             length=560, resolution=1, showvalue=True,
             font=_F_SMALL).grid(row=0, column=1)
    tk.Label(f, text=hi, foreground="#555",
             font=_F_SMALL).grid(row=0, column=2, padx=(10, 0))
    return row + 1


def _radio(parent: tk.Frame, text: str, row: int, var: tk.StringVar,
           choices: List[str]) -> int:
    row = _qlabel(parent, text, row)
    f = tk.Frame(parent)
    f.grid(row=row, column=0, columnspan=12, sticky="w", padx=30, pady=(0, 8))
    for i, c in enumerate(choices):
        tk.Radiobutton(f, text=c, variable=var, value=c,
                       font=_F_BODY).grid(row=i, column=0, sticky="w", pady=3)
    return row + 1


def _entry(parent: tk.Frame, text: str, row: int, var: tk.StringVar) -> int:
    row = _qlabel(parent, text, row)
    ttk.Entry(parent, textvariable=var, width=16, font=_F_BODY).grid(
        row=row, column=0, columnspan=12, sticky="w", padx=30, pady=(0, 8))
    return row + 1


def _textbox(parent: tk.Frame, text: str, row: int,
             var: tk.StringVar, height: int = 4) -> int:
    row = _qlabel(parent, text, row)
    box = tk.Text(parent, height=height, wrap="word",
                  relief="solid", borderwidth=1, font=("Segoe UI", 18))
    box.grid(row=row, column=0, columnspan=12,
             sticky="ew", padx=30, pady=(0, 10))
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
    f.grid(row=row, column=0, columnspan=12, pady=28)
    ttk.Button(f, text=text, command=cmd, width=24).pack()


def _all_answered(int_vars: List[tk.IntVar], str_vars: List[tk.StringVar]) -> bool:
    """Return True if all vars have a response (int != 0, string non-empty)."""
    for v in int_vars:
        if v.get() == 0:
            return False
    for v in str_vars:
        if not v.get().strip():
            return False
    return True


# ── Pre-study demographics ────────────────────────────────────────────────────

def run_demographic_survey(
    mon: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[dict]:
    """Show pre-study demographics form. Returns responses dict or None."""
    result: Optional[dict] = None

    root = tk.Tk()
    root.title("Pre-Study Survey")
    root.geometry(f"{WINDOW_W}x900")
    root.resizable(False, True)

    inner = _scrollable_form(root)
    r = 0

    tk.Label(inner, text="Pre-Study Questionnaire",
             font=("Segoe UI", 27, "bold")).grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(22, 2))
    r += 1
    tk.Label(inner, text="Please answer the following before we begin.",
             font=_F_ASIDE, foreground="#555").grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(0, 12))
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

    r = _heading(inner, "Experience and background", r)

    computer_var = tk.IntVar(value=0)
    r = _likert(inner,
                "How comfortable are you with computer-based programs and tasks?",
                r, computer_var, lo="Not comfortable", hi="Very comfortable")

    ai_usage_var = tk.IntVar(value=0)
    r = _likert(inner,
                "How often do you use AI tools such as recommendation systems or chatbots?",
                r, ai_usage_var, lo="Never", hi="Very often")

    ai_trust_var = tk.IntVar(value=0)
    r = _likert(inner,
                "How much do you generally trust AI systems?",
                r, ai_trust_var, lo="Not at all", hi="Completely")

    game_var = tk.IntVar(value=0)
    r = _likert(inner,
                "How much experience do you have with video games or control software "
                "that involve tracking multiple moving objects on a screen?",
                r, game_var, lo="None", hi="Very experienced")

    def _submit():
        nonlocal result
        if not age_var.get().strip():
            messagebox.showwarning("Required", "Please enter your age.", parent=root)
            return
        if not gender_var.get():
            messagebox.showwarning("Required", "Please select your gender.", parent=root)
            return
        if not edu_var.get():
            messagebox.showwarning("Required",
                                   "Please select your education level.", parent=root)
            return
        if not _all_answered([computer_var, ai_usage_var, ai_trust_var, game_var], []):
            messagebox.showwarning("Required",
                                   "Please answer all rating questions before continuing.",
                                   parent=root)
            return
        result = {
            "age":              age_var.get().strip(),
            "gender":           gender_var.get(),
            "education":        edu_var.get(),
            "computer_comfort": computer_var.get(),
            "ai_usage":         ai_usage_var.get(),
            "ai_trust":         ai_trust_var.get(),
            "game_experience":  game_var.get(),
            "timestamp":        datetime.datetime.now().isoformat(),
        }
        root.destroy()

    _submit_btn(inner, r, "Continue →", _submit)

    _center(root, mon)
    root.mainloop()
    return result


# ── Per-trial survey (Workload + Trust + Acceptance + Per-mode) ───────────────

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

# Per-mode ratings
_MODES = [
    ("manual",    "Manual",
     "Clicking a drone directly to change its channel yourself."),
    ("suggest",   "Suggest & Review",
     "Selecting drones, requesting a suggestion, reviewing it, then applying."),
    ("auto",      "Auto-assign",
     "Selecting drones and having channels applied instantly without review."),
]

_MODE_ITEMS = [
    ("helpful",     "This mode was helpful to me."),
    ("trusted",     "I trusted this mode."),
    ("focus",       "This mode helped me better use my attention and focus on the task."),
    ("alongside",   "I worked well alongside / with this mode."),
]


def run_trial_survey(
    scenario_num: int,
    scenario_label: str,
    mon: Optional[Tuple[int, int, int, int]] = None,
    show_tlx: bool = True,
    show_trust: bool = True,
    show_tam: bool = True,
) -> Optional[dict]:
    """Post-trial questionnaire (Workload + Trust + TAM + Per-mode). Returns dict or None."""
    result: Optional[dict] = None

    root = tk.Tk()
    root.title(f"Scenario {scenario_num} — Feedback")
    root.geometry(f"{WINDOW_W}x950")
    root.resizable(False, True)

    inner = _scrollable_form(root)
    r = 0

    tk.Label(inner, text=f"Scenario {scenario_num} — Feedback",
             font=("Segoe UI", 27, "bold")).grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(22, 2))
    r += 1
    tk.Label(inner,
             text="Please rate the scenario you just completed. "
                  "There are no right or wrong answers.",
             font=_F_ASIDE, foreground="#555").grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(0, 12))
    r += 1

    tlx_vars: Dict[str, tk.IntVar] = {}
    if show_tlx:
        r = _heading(inner, "Workload", r)
        for key, text in _TLX_ITEMS:
            v = tk.IntVar(value=10)
            tlx_vars[key] = v
            r = _tlx_item(inner, text, r, v)

    trust_vars: Dict[str, tk.IntVar] = {}
    if show_trust:
        r = _heading(inner, "Trust in the Assistant", r)
        for key, text in _TRUST_ITEMS:
            v = tk.IntVar(value=0)
            trust_vars[key] = v
            r = _likert(inner, text, r, v, lo="Not at all", hi="Extremely")

    tam_vars: Dict[str, tk.IntVar] = {}
    if show_tam:
        r = _heading(inner, "Tool Usefulness", r)
        for key, text in _TAM_ITEMS:
            v = tk.IntVar(value=0)
            tam_vars[key] = v
            r = _likert(inner, text, r, v,
                        lo="Strongly disagree", hi="Strongly agree")

    # ── Per-mode ratings ──────────────────────────────────────────────────────
    r = _heading(inner, "Interaction Modes", r)
    tk.Label(inner,
             text='Rate how well each interaction mode worked for you in this scenario.',
             font=_F_ASIDE, foreground="#555",
             wraplength=WINDOW_W - 40, justify="left").grid(
        row=r, column=0, columnspan=12, sticky="w", padx=22, pady=(0, 12))
    r += 1

    mode_vars: Dict[str, Dict[str, tk.IntVar]] = {}
    for mode_key, mode_name, mode_desc in _MODES:
        mode_vars[mode_key] = {}

        tk.Label(inner, text=mode_name,
                 font=("Segoe UI", 19, "bold"), anchor="w").grid(
            row=r, column=0, columnspan=12,
            sticky="w", padx=22, pady=(12, 0))
        r += 1
        tk.Label(inner, text=mode_desc,
                 font=_F_ASIDE, foreground="#555", anchor="w").grid(
            row=r, column=0, columnspan=12,
            sticky="w", padx=30, pady=(0, 4))
        r += 1

        for item_key, item_text in _MODE_ITEMS:
            v = tk.IntVar(value=0)
            mode_vars[mode_key][item_key] = v
            r = _likert(inner, item_text, r, v,
                        lo="Strongly disagree", hi="Strongly agree")

    # ── Open-ended ────────────────────────────────────────────────────────────
    r = _heading(inner, "Open-ended", r)
    comments_var = tk.StringVar()
    r = _textbox(inner,
                 "Any other comments about this scenario? (optional)",
                 r, comments_var, height=4)

    def _submit():
        nonlocal result
        required_ints: List[tk.IntVar] = (
            list(trust_vars.values()) +
            list(tam_vars.values()) +
            [v for mv in mode_vars.values() for v in mv.values()]
        )
        if not _all_answered(required_ints, []):
            messagebox.showwarning(
                "Required",
                "Please answer all rating questions before continuing.",
                parent=root)
            return
        result = {
            "scenario_num":   scenario_num,
            "scenario_label": scenario_label,
            **{k: v.get() for k, v in tlx_vars.items()},
            **{k: v.get() for k, v in trust_vars.items()},
            **{k: v.get() for k, v in tam_vars.items()},
        }
        for mode_key, mv in mode_vars.items():
            for item_key, v in mv.items():
                result[f"mode_{mode_key}_{item_key}"] = v.get()
        result["comments"]   = comments_var.get().strip()
        result["timestamp"]  = datetime.datetime.now().isoformat()
        root.destroy()

    _submit_btn(inner, r, "Continue →", _submit)

    _center(root, mon)
    root.mainloop()
    return result


# ── Post-study summary survey ─────────────────────────────────────────────────

_SUMMARY_MODES = [
    ("manual",  "Manual",
     "Clicking a drone directly to change its channel."),
    ("suggest", "Suggest & Review",
     "Requesting a suggestion from the assistant, reviewing it, then applying."),
    ("auto",    "Auto-assign",
     "Having the assistant apply channel assignments instantly without review."),
]

_SUMMARY_MODE_QLABEL_FOLLOW = (
    "What influenced your ratings above for {mode}? "
    "Think particularly about how it performed when there were many drones "
    "and when you were under pressure."
)


def run_summary_survey(
    scenario_infos: List[Dict],   # [{"num": 1, "label": "Easy-perfect"}, ...]
    mon: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[dict]:
    """
    Final summary questionnaire shown once after all trials.

    Asks per-mode quantitative ratings plus qualitative follow-ups.
    scenario_infos is preserved in the output as scenario_map.
    """
    result: Optional[dict] = None

    root = tk.Tk()
    root.title("Summary Questionnaire")
    root.geometry(f"{WINDOW_W}x950")
    root.resizable(False, True)

    inner = _scrollable_form(root)
    r = 0

    tk.Label(inner, text="Summary Questionnaire",
             font=("Segoe UI", 27, "bold")).grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(22, 2))
    r += 1
    tk.Label(inner,
             text="Now that you've completed all scenarios, please reflect on "
                  "each interaction mode overall.",
             font=_F_ASIDE, foreground="#555",
             wraplength=WINDOW_W - 40, justify="left").grid(
        row=r, column=0, columnspan=12, sticky="w", padx=12, pady=(0, 12))
    r += 1

    # ── Per-mode quantitative + qualitative ───────────────────────────────────
    r = _heading(inner, "Rating each interaction mode", r)

    summary_mode_vars: Dict[str, Dict[str, tk.IntVar]] = {}
    summary_mode_text: Dict[str, tk.StringVar] = {}

    for mode_key, mode_name, mode_desc in _SUMMARY_MODES:
        summary_mode_vars[mode_key] = {}

        tk.Label(inner, text=mode_name,
                 font=("Segoe UI", 20, "bold"), anchor="w").grid(
            row=r, column=0, columnspan=12,
            sticky="w", padx=22, pady=(14, 0))
        r += 1
        tk.Label(inner, text=mode_desc,
                 font=_F_ASIDE, foreground="#555", anchor="w").grid(
            row=r, column=0, columnspan=12,
            sticky="w", padx=30, pady=(0, 6))
        r += 1

        v_overall = tk.IntVar(value=0)
        summary_mode_vars[mode_key]["overall"] = v_overall
        r = _likert(inner,
                    f"Overall, how would you rate {mode_name}?",
                    r, v_overall, lo="Very poor", hi="Excellent")

        v_drones = tk.IntVar(value=0)
        summary_mode_vars[mode_key]["drone_count_helpfulness"] = v_drones
        r = _likert(inner,
                    f"In scenarios with more drones, {mode_name} was more helpful.",
                    r, v_drones, lo="Strongly disagree", hi="Strongly agree")

        v_overload = tk.IntVar(value=0)
        summary_mode_vars[mode_key]["overload_preference"] = v_overload
        r = _likert(inner,
                    f"When I felt overloaded, I preferred {mode_name}.",
                    r, v_overload, lo="Strongly disagree", hi="Strongly agree")

        qual_var = tk.StringVar()
        summary_mode_text[mode_key] = qual_var
        r = _textbox(inner,
                     _SUMMARY_MODE_QLABEL_FOLLOW.format(mode=mode_name),
                     r, qual_var, height=4)

    # ── General reflection ────────────────────────────────────────────────────
    r = _heading(inner, "General reflections", r)

    other_var = tk.StringVar()
    r = _textbox(inner,
                 "Any other thoughts about the three modes or the study overall? (optional)",
                 r, other_var, height=4)

    def _submit():
        nonlocal result
        required_ints: List[tk.IntVar] = [
            v
            for mv in summary_mode_vars.values()
            for v in mv.values()
        ]
        if not _all_answered(required_ints, []):
            messagebox.showwarning(
                "Required",
                "Please answer all rating questions before finishing.",
                parent=root)
            return
        d: dict = {
            "scenario_map": {str(info["num"]): info["label"]
                             for info in scenario_infos},
            "timestamp": datetime.datetime.now().isoformat(),
        }
        for mode_key, mv in summary_mode_vars.items():
            for q_key, v in mv.items():
                d[f"mode_{mode_key}_{q_key}"] = v.get()
            d[f"mode_{mode_key}_qualitative"] = summary_mode_text[mode_key].get().strip()
        d["other_comments"] = other_var.get().strip()
        result = d
        root.destroy()

    _submit_btn(inner, r, "Finish →", _submit)

    _center(root, mon)
    root.mainloop()
    return result
