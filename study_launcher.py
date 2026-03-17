"""Study launcher for the graph colouring constraint visualisation experiment.

Run with:
    python study_launcher.py

Study flow:
    1. Setup        — participant name, condition order, graph preset
    2. Pre-study questionnaire
    3. Tutorial
    4. For each condition (in chosen order):
         a. Transition screen   ("Condition X of N — about to start")
         b. Experiment window   (spawned as subprocess, waited on)
         c. Inter-condition survey
    5. Final survey
    6. Done screen

Results are written to:
    results/participants/<name>_<timestamp>/
        setup.json
        pre_questionnaire.json
        condition_1_<C>/          ← experiment logs from run_experiment.py
        condition_1_<C>_survey.json
        condition_2_<C>/
        condition_2_<C>_survey.json
        ...
        final_survey.json
        study_log.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk

# ── Visual constants ──────────────────────────────────────────────────────────
BG      = "#f5f6fa"
BG_W    = "#ffffff"
ACCENT  = "#2563eb"
FG      = "#111827"
FG_M    = "#6b7280"
FG_E    = "#dc2626"

F_TIT   = ("Arial", 20, "bold")
F_H2    = ("Arial", 14, "bold")
F_BD    = ("Arial", 12)
F_LB    = ("Arial", 11)
F_SM    = ("Arial", 10)

# ── Study content ─────────────────────────────────────────────────────────────
CONDITION_INFO: dict[str, str] = {
    "C1": "User-Centric Formulaic",
    "C2": "Agent-Centric Formulaic",
    "C3": "Human Domain Formulaic",
    "C4": "User-Centric Natural Language",
    "C5": "Agent-Centric Natural Language",
    "C6": "Human Domain Natural Language",
}

GRAPH_PRESETS = [
    "easy", "medium", "tight", "hard",
    "expert", "dense", "dense_tight", "super",
]
EXPLICIT_PRESETS = {"medium", "tight", "dense", "dense_tight", "expert", "super"}

# ── Question definitions ──────────────────────────────────────────────────────
# Each question is a dict with keys:
#   id        str   — unique key for the result dict
#   type      str   — "entry" | "radio" | "likert" | "text" | "dynamic_radio"
#   label     str   — question text shown to participant
#   opts      list  — options for "radio" questions
#   low/high  str   — endpoint labels for "likert" questions

PRE_QUESTIONS: list[dict] = [
    {
        "id": "age", "type": "entry",
        "label": "Age",
    },
    {
        "id": "bio_sex", "type": "radio",
        "label": "Biological Sex",
        "opts": ["Male", "Female"],
    },
    {
        "id": "gender", "type": "entry",
        "label": "Gender (optional)",
    },
    {
        "id": "education", "type": "radio",
        "label": "Highest level of education completed",
        "opts": [
            "Secondary / High school",
            "Undergraduate degree",
            "Postgraduate / Masters",
            "PhD or higher",
            "Prefer not to say",
        ],
    },
    {
        "id": "cs_familiarity", "type": "likert",
        "label": "How familiar are you with graph problems or constraint satisfaction?",
        "low": "Not at all", "high": "Expert",
    },
    {
        "id": "ai_experience", "type": "radio",
        "label": "Prior experience with AI collaboration or decision-support tools such as ChatGPT?",
        "opts": ["None", "A little", "Regularly", "I regularly work with AI tools"],
    },
]

# ── Trust in Automation Survey (Jian, Bisantz & Drury, 2000) ─────────────────
# Scale: 1 = Not at all … 7 = Extremely
_TRUST_ITEMS: list[dict] = [
    {"id": "trust_1",  "type": "likert",
     "label": "The system is deceptive.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_2",  "type": "likert",
     "label": "The system behaves in an underhanded manner.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_3",  "type": "likert",
     "label": "I am suspicious of the system's intent, action, or outputs.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_4",  "type": "likert",
     "label": "I am wary of the system.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_5",  "type": "likert",
     "label": "The system's actions will have a harmful or injurious outcome.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_6",  "type": "likert",
     "label": "I am confident in the system.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_7",  "type": "likert",
     "label": "The system provides security.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_8",  "type": "likert",
     "label": "The system has integrity.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_9",  "type": "likert",
     "label": "The system is dependable.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_10", "type": "likert",
     "label": "The system is reliable.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_11", "type": "likert",
     "label": "I can trust the system.",
     "low": "Not at all", "high": "Extremely"},
    {"id": "trust_12", "type": "likert",
     "label": "I am familiar with the system.",
     "low": "Not at all", "high": "Extremely"},
]

# ── NASA Task Load Index (Hart & Staveland, 1988) ─────────────────────────────
# Scale: 1 (Low/Perfect) … 20 (High/Failure)
_TLX_ITEMS: list[dict] = [
    {"id": "tlx_mental",      "type": "tlx",
     "label": "Mental Demand — How much mental and perceptual activity was required?",
     "low": "Low", "high": "High"},
    {"id": "tlx_physical",    "type": "tlx",
     "label": "Physical Demand — How much physical activity was required?",
     "low": "Low", "high": "High"},
    {"id": "tlx_temporal",    "type": "tlx",
     "label": "Temporal Demand — How much time pressure did you feel?",
     "low": "Low", "high": "High"},
    {"id": "tlx_performance", "type": "tlx",
     "label": "Performance — How successful were you in accomplishing what you were asked to do?",
     "low": "Perfect", "high": "Failure"},
    {"id": "tlx_effort",      "type": "tlx",
     "label": "Effort — How hard did you have to work to accomplish your level of performance?",
     "low": "Low", "high": "High"},
    {"id": "tlx_frustration", "type": "tlx",
     "label": "Frustration — How insecure, discouraged, irritated, stressed, and annoyed were you?",
     "low": "Low", "high": "High"},
]

INTER_QUESTIONS: list[dict] = [
    # ── Condition ratings ─────────────────────────────────────────────────────
    {
        "id": "info_clarity", "type": "likert",
        "label": "How easy was it to understand the constraint information shown?",
        "low": "Very hard", "high": "Very easy",
    },
    {
        "id": "info_useful", "type": "likert",
        "label": "How useful was the information for solving the puzzle?",
        "low": "Not useful", "high": "Extremely useful",
    },
    {
        "id": "confidence", "type": "likert",
        "label": "How confident are you in the solution you found?",
        "low": "Not confident", "high": "Very confident",
    },
    {
        "id": "satisfaction", "type": "likert",
        "label": "How satisfied are you with this condition overall?",
        "low": "Very dissatisfied", "high": "Very satisfied",
    },
    # ── Trust in Automation Survey ────────────────────────────────────────────
    {
        "id": "_trust_header", "type": "section",
        "label": "Rate each statement from 1 (Not at all) to 7 (Extremely).",
    },
    *_TRUST_ITEMS,
    # ── NASA Task Load Index ──────────────────────────────────────────────────
    {
        "id": "_tlx_header", "type": "section",
        "label": "Rate each dimension from 1 to 20.",
    },
    *_TLX_ITEMS,
    # ── Open comment ─────────────────────────────────────────────────────────
    {
        "id": "inter_comments", "type": "text",
        "label": "Any comments about this condition? (optional)",
    },
]

FINAL_QUESTIONS: list[dict] = [
    {
        "id": "ranking", "type": "ranking",
        "label": "Rank the conditions from most to least helpful overall.\n"
                 "Drag items or use ↑ ↓ to reorder — top = most helpful.",
    },
    {
        "id": "comparison", "type": "text",
        "label": "How would you compare the different conditions you experienced?",
    },
    {
        "id": "final_comments", "type": "text",
        "label": "Any other feedback or suggestions? (optional)",
    },
]

TUTORIAL_TEXT = """\
TASK OVERVIEW
━━━━━━━━━━━━━
Your task is to colour every node in a graph using three colours
(red, green, blue) so that no two connected nodes share the same colour.

The graph is split into three regions:
  • YOUR cluster (centre) — you control these nodes directly
  • Agent 1's cluster (left side)  — managed automatically
  • Agent 2's cluster (right side) — managed automatically

Fixed nodes (shown with a darker/locked border) have pre-assigned colours
that cannot be changed.  These create the constraint structure for the puzzle.


HOW TO INTERACT
━━━━━━━━━━━━━━━
• Click a node in YOUR cluster to cycle its colour:
      grey → red → green → blue → grey …
• The constraint panel on the right updates in real time as you click
• Agent nodes colour themselves — you do not need to interact with them


READING THE CONSTRAINT PANEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The right-hand panel shows how your current colour choices interact with the
neighbouring clusters.  It tells you whether a valid (conflict-free) colouring
is still possible given your current choices, and may give more detail
depending on the condition.

Use this information to guide which colours you choose for your nodes.


FINISHING A CONDITION
━━━━━━━━━━━━━━━━━━━━━
• When you are satisfied with your colouring, simply close the experiment window
• A short questionnaire will follow before the next condition begins
• You can close at any point — there is no time limit


TIPS
━━━━
• You only colour YOUR nodes — agents handle their own clusters
• Every edge must connect nodes of DIFFERENT colours
• If you are stuck, try changing one node at a time and watch the panel update
• It is fine to close the window before finding a perfect solution
"""


# ── Main application class ────────────────────────────────────────────────────

class StudyApp:
    """Single-window study flow controller."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Graph Colouring Study")
        self.root.geometry("580x560")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        # ── Study-wide state ──────────────────────────────────────────────
        self.participant_name: str = ""
        self.selected_conditions: list[str] = []
        self.graph_preset: str = "medium"
        self.use_llm: bool = False
        self._fixed_constraints: bool = True
        self._num_fixed_nodes: int = 1
        self.results_dir: Path | None = None

        # ── Per-condition runtime state ───────────────────────────────────
        self.condition_idx: int = 0
        self._proc: subprocess.Popen | None = None
        self._proc_done: bool = False

        # ── Accumulated survey data ───────────────────────────────────────
        self.study_meta: dict = {}
        self.pre_data: dict = {}
        self.inter_data: list[dict] = []
        self.final_data: dict = {}

        # ── UI state ──────────────────────────────────────────────────────
        self._cur_frame: tk.Frame | None = None
        self._mw_bound: bool = False

        self.show_setup()
        self.root.mainloop()

    # ── Page management ───────────────────────────────────────────────────────

    def _page(self) -> tk.Frame:
        """Destroy current page frame and return a fresh one."""
        if self._cur_frame is not None:
            self._cur_frame.destroy()
        if self._mw_bound:
            try:
                self.root.unbind_all("<MouseWheel>")
            except Exception:
                pass
            self._mw_bound = False
        f = tk.Frame(self.root, bg=BG)
        f.pack(fill="both", expand=True)
        self._cur_frame = f
        return f

    def _header(self, page: tk.Frame, title: str,
                subtitle: str = "", step: str = "") -> None:
        hf = tk.Frame(page, bg=BG)
        hf.pack(fill="x", padx=20, pady=(16, 0))
        if step:
            tk.Label(hf, text=step, font=F_SM, bg=BG, fg=FG_M,
                     anchor="e").pack(fill="x")
        tk.Label(hf, text=title, font=F_TIT, bg=BG, fg=FG,
                 anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(hf, text=subtitle, font=F_SM, bg=BG, fg=FG_M,
                     anchor="w", wraplength=700).pack(fill="x", pady=(2, 0))
        ttk.Separator(page).pack(fill="x", padx=20, pady=8)

    def _footer(self, page: tk.Frame) -> tk.Frame:
        """Fixed footer frame anchored to the bottom of page."""
        ttk.Separator(page).pack(fill="x", padx=20, side="bottom")
        ff = tk.Frame(page, bg=BG)
        ff.pack(side="bottom", fill="x", padx=20, pady=10)
        return ff

    def _scrollable(self, page: tk.Frame) -> tk.Frame:
        """Scrollable inner frame that fills remaining page space."""
        outer = tk.Frame(page, bg=BG)
        outer.pack(fill="both", expand=True, padx=20, pady=4)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        canvas.configure(yscrollcommand=vsb.set)

        def _on_inner_resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_resize(e):
            canvas.itemconfig(inner_id, width=e.width)

        inner.bind("<Configure>", _on_inner_resize)
        canvas.bind("<Configure>", _on_canvas_resize)

        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _mwheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        self.root.bind_all("<MouseWheel>", _mwheel)
        self._mw_bound = True
        return inner

    # ── Survey widget helpers ─────────────────────────────────────────────────

    def _render_question(self, parent: tk.Frame, q: dict,
                         dyn_opts: list[str] | None = None) -> dict:
        """Render one survey question into parent; return widget-info dict."""
        qtype = q["type"]

        # ── Section header — styled divider, no data collected ────────────────
        if qtype == "section":
            card = tk.Frame(parent, bg="#dbeafe",
                            highlightthickness=1, highlightbackground="#93c5fd")
            card.pack(fill="x", pady=(12, 2))
            tk.Label(card, text=q["label"], font=F_BD, bg="#dbeafe", fg="#1e3a8a",
                     wraplength=640, justify="left").pack(anchor="w", padx=12, pady=10)
            return {"type": "section"}

        card = tk.Frame(parent, bg=BG_W,
                        highlightthickness=1, highlightbackground="#e5e7eb")
        card.pack(fill="x", pady=4)

        tk.Label(card, text=q["label"], font=F_LB, bg=BG_W, fg=FG,
                 wraplength=640, justify="left").pack(anchor="w", padx=12, pady=(10, 4))

        if qtype == "entry":
            var = tk.StringVar()
            ttk.Entry(card, textvariable=var, width=40,
                      font=F_LB).pack(anchor="w", padx=12, pady=(0, 10))
            return {"type": "entry", "var": var}

        elif qtype == "radio":
            opts = q.get("opts", [])
            var = tk.StringVar()
            rf = tk.Frame(card, bg=BG_W)
            rf.pack(anchor="w", padx=12, pady=(0, 10))
            for opt in opts:
                ttk.Radiobutton(rf, text=opt, variable=var,
                                value=opt).pack(anchor="w", pady=1)
            return {"type": "radio", "var": var}

        elif qtype == "dynamic_radio":
            opts = dyn_opts or []
            var = tk.StringVar()
            rf = tk.Frame(card, bg=BG_W)
            rf.pack(anchor="w", padx=12, pady=(0, 10))
            for opt in opts:
                ttk.Radiobutton(rf, text=opt, variable=var,
                                value=opt).pack(anchor="w", pady=1)
            return {"type": "radio", "var": var}

        elif qtype == "likert":
            var = tk.IntVar(value=4)
            lf = tk.Frame(card, bg=BG_W)
            lf.pack(anchor="w", padx=12, pady=(0, 10), fill="x")
            tk.Label(lf, text=q.get("low", "1"), font=F_SM,
                     bg=BG_W, fg=FG_M).pack(side="left")
            sc = tk.Scale(
                lf, variable=var, from_=1, to=7, orient="horizontal",
                length=320, showvalue=True, bg=BG_W, highlightthickness=0,
                font=F_SM, troughcolor="#dbeafe", activebackground=ACCENT,
            )
            sc.pack(side="left", padx=8)
            tk.Label(lf, text=q.get("high", "7"), font=F_SM,
                     bg=BG_W, fg=FG_M).pack(side="left")
            return {"type": "likert", "var": var}

        elif qtype == "tlx":
            # 1–20 slider, default 10
            var = tk.IntVar(value=10)
            lf = tk.Frame(card, bg=BG_W)
            lf.pack(anchor="w", padx=12, pady=(0, 10), fill="x")
            tk.Label(lf, text=q.get("low", "Low"), font=F_SM,
                     bg=BG_W, fg=FG_M).pack(side="left")
            sc = tk.Scale(
                lf, variable=var, from_=1, to=20, orient="horizontal",
                length=360, showvalue=True, bg=BG_W, highlightthickness=0,
                font=F_SM, troughcolor="#dbeafe", activebackground=ACCENT,
            )
            sc.pack(side="left", padx=8)
            tk.Label(lf, text=q.get("high", "High"), font=F_SM,
                     bg=BG_W, fg=FG_M).pack(side="left")
            return {"type": "tlx", "var": var}

        elif qtype == "ranking":
            # Drag-and-drop + ↑↓ reorderable listbox
            items = list(dyn_opts or [])
            rf = tk.Frame(card, bg=BG_W)
            rf.pack(anchor="w", padx=12, pady=(0, 10), fill="x")

            lb_frame = tk.Frame(rf, bg=BG_W)
            lb_frame.pack(anchor="w")

            lb = tk.Listbox(
                lb_frame, selectmode="single", font=F_LB, bg=BG_W,
                relief="solid", borderwidth=1,
                height=max(len(items), 2), width=58,
                activestyle="dotbox",
                selectbackground=ACCENT, selectforeground="white",
            )
            for item in items:
                lb.insert("end", item)
            lb.select_set(0)
            lb.pack(side="left")

            btn_f = tk.Frame(lb_frame, bg=BG_W)
            btn_f.pack(side="left", padx=(6, 0), anchor="n")

            def _move_up(_lb=lb):
                sel = _lb.curselection()
                if not sel or sel[0] == 0:
                    return
                i = sel[0]
                item = _lb.get(i)
                _lb.delete(i)
                _lb.insert(i - 1, item)
                _lb.selection_set(i - 1)

            def _move_down(_lb=lb):
                sel = _lb.curselection()
                if not sel or sel[0] >= _lb.size() - 1:
                    return
                i = sel[0]
                item = _lb.get(i)
                _lb.delete(i)
                _lb.insert(i + 1, item)
                _lb.selection_set(i + 1)

            ttk.Button(btn_f, text="↑", width=3,
                       command=_move_up).pack(pady=2)
            ttk.Button(btn_f, text="↓", width=3,
                       command=_move_down).pack(pady=2)

            _drag_from = [None]

            def _start_drag(e, _lb=lb, _df=_drag_from):
                _df[0] = _lb.nearest(e.y)
                _lb.selection_clear(0, "end")
                _lb.selection_set(_df[0])

            def _do_drag(e, _lb=lb, _df=_drag_from):
                cur = _lb.nearest(e.y)
                if _df[0] is not None and cur != _df[0]:
                    item = _lb.get(_df[0])
                    _lb.delete(_df[0])
                    _lb.insert(cur, item)
                    _lb.selection_clear(0, "end")
                    _lb.selection_set(cur)
                    _df[0] = cur

            lb.bind("<Button-1>", _start_drag)
            lb.bind("<B1-Motion>", _do_drag)

            return {"type": "ranking", "widget": lb}

        elif qtype == "text":
            tw = tk.Text(card, height=3, width=64, font=F_LB,
                         wrap="word", relief="solid", borderwidth=1,
                         highlightthickness=0)
            tw.pack(anchor="w", padx=12, pady=(0, 10))
            return {"type": "text", "widget": tw}

        return {}

    def _render_survey(self, parent: tk.Frame, questions: list[dict],
                       dyn_opts: list[str] | None = None) -> dict:
        """Render a list of questions; return {id: widget_info}."""
        wmap: dict = {}
        for q in questions:
            opts = dyn_opts if q["type"] in ("dynamic_radio", "ranking") else None
            wmap[q["id"]] = self._render_question(parent, q, dyn_opts=opts)
        return wmap

    @staticmethod
    def _collect(wmap: dict) -> dict:
        """Collect current values from a rendered survey widget map."""
        result: dict = {}
        for qid, info in wmap.items():
            t = info.get("type")
            if t in ("entry", "radio", "likert", "tlx"):
                result[qid] = info["var"].get()
            elif t == "text":
                result[qid] = info["widget"].get("1.0", "end-1c").strip()
            elif t == "ranking":
                result[qid] = list(info["widget"].get(0, "end"))
            # "section" entries carry no data — skipped
        return result

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self, filename: str, data: dict) -> None:
        if self.results_dir is not None:
            (self.results_dir / filename).write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )

    # ── Subprocess management ─────────────────────────────────────────────────

    def _launch_condition(self, condition: str, out_dir: Path,
                          on_done: callable) -> None:
        """Spawn run_experiment.py; call on_done() in the Tk thread when it exits."""
        out_dir.mkdir(parents=True, exist_ok=True)
        run_script = Path(__file__).resolve().with_name("run_experiment.py")

        args = [
            sys.executable, str(run_script),
            "--condition", condition,
            "--use-ui",
            "--output-dir", str(out_dir),
            "--graph-preset", self.graph_preset,
        ]
        if self._fixed_constraints and self.graph_preset not in EXPLICIT_PRESETS:
            args += ["--fixed-constraints",
                     "--num-fixed-nodes", str(self._num_fixed_nodes)]
        if self.use_llm and condition in ("C4", "C5", "C6"):
            args.append("--use-llm")

        self._proc_done = False

        def _run() -> None:
            self._proc = subprocess.Popen(args, cwd=str(run_script.parent))
            self._proc.wait()
            self._proc_done = True

        threading.Thread(target=_run, daemon=True).start()

        def _poll() -> None:
            if self._proc_done:
                on_done()
            else:
                self.root.after(500, _poll)

        self.root.after(500, _poll)

    # ── Step numbering helper ─────────────────────────────────────────────────

    def _step_label(self, step: int) -> str:
        n = len(self.selected_conditions)
        total = 2 + 2 * n + 1  # PreQ + Tutorial + N*(transition+survey) + FinalSurvey
        return f"Step {step} of {total}"

    # ── Pages ─────────────────────────────────────────────────────────────────

    def show_setup(self) -> None:
        """Compact launch-menu style configuration screen."""
        self.root.geometry("580x560")
        self.root.resizable(False, False)

        # ── Load saved config ─────────────────────────────────────────────
        config_path = Path.home() / ".graph_coloring_study_config.json"
        saved: dict = {}
        if config_path.exists():
            try:
                saved = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        page = self._page()
        FONT = ("Arial", 12)
        page.option_add("*TLabel.Font", FONT)
        page.option_add("*TButton.Font", FONT)
        page.option_add("*TCheckbutton.Font", FONT)
        page.option_add("*TCombobox.Font", FONT)

        frm = ttk.Frame(page, padding=16)
        frm.pack(fill="both", expand=True)

        row = 0

        # ── Title ─────────────────────────────────────────────────────────
        ttk.Label(frm, text="Graph Colouring Study",
                  font=("Arial", 15, "bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 2))
        row += 1
        ttk.Separator(frm).grid(row=row, column=0, columnspan=3,
                                sticky="ew", pady=(4, 10))
        row += 1

        # ── Participant name ───────────────────────────────────────────────
        ttk.Label(frm, text="Participant name / ID").grid(
            row=row, column=0, sticky="w")
        row += 1
        name_var = tk.StringVar()           # intentionally not persisted
        ttk.Entry(frm, textvariable=name_var, width=30, font=FONT).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row += 1

        # ── Conditions ────────────────────────────────────────────────────
        ttk.Label(frm, text="Conditions to run").grid(
            row=row, column=0, columnspan=2, sticky="w")
        ttk.Label(frm, text="Order", foreground="#555555").grid(
            row=row, column=2, sticky="w")
        row += 1
        ttk.Label(frm,
                  text="Tick each condition and assign a run order (1 = first).",
                  font=("Arial", 9), foreground="#555555").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
        row += 1

        saved_conds: dict = saved.get("conditions", {})
        cond_vars: dict[str, tuple[tk.BooleanVar, tk.StringVar]] = {}
        for code, cname in CONDITION_INFO.items():
            saved_order = saved_conds.get(code, "")
            cv = tk.BooleanVar(value=bool(saved_order))
            ov = tk.StringVar(value=str(saved_order))
            cond_vars[code] = (cv, ov)
            ttk.Checkbutton(frm, text=f"{code}  —  {cname}",
                            variable=cv).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=1)
            ttk.Spinbox(frm, from_=1, to=6, textvariable=ov, width=5).grid(
                row=row, column=2, sticky="w", pady=1)
            row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=3,
                                sticky="ew", pady=(6, 8))
        row += 1

        # ── Graph preset ──────────────────────────────────────────────────
        ttk.Label(frm, text="Graph preset").grid(
            row=row, column=0, sticky="w", pady=(0, 4))
        preset_var = tk.StringVar(value=saved.get("graph_preset", "medium"))
        preset_combo = ttk.Combobox(
            frm, textvariable=preset_var, values=GRAPH_PRESETS,
            state="readonly", width=22)
        preset_combo.grid(row=row, column=1, columnspan=2,
                          sticky="w", pady=(0, 4))
        row += 1

        # ── Fixed-node controls ───────────────────────────────────────────
        fixed_var = tk.BooleanVar(value=saved.get("fixed_constraints", True))
        fixed_check = ttk.Checkbutton(frm, text="Use fixed node constraints",
                                      variable=fixed_var)
        fixed_check.grid(row=row, column=0, columnspan=3,
                         sticky="w", pady=(2, 0))
        row += 1

        fixed_num_var = tk.IntVar(value=saved.get("num_fixed_nodes", 1))
        fixed_lbl = ttk.Label(frm, text="Fixed nodes per cluster (0–3)")
        fixed_lbl.grid(row=row, column=0, sticky="w")
        fixed_spin = ttk.Spinbox(frm, from_=0, to=3,
                                 textvariable=fixed_num_var, width=8)
        fixed_spin.grid(row=row, column=1, sticky="w")
        row += 1

        def _on_preset_change(*_) -> None:
            is_explicit = preset_var.get() in EXPLICIT_PRESETS
            state = "disabled" if is_explicit else "normal"
            fixed_check.config(state=state)
            fixed_spin.config(state=state)
            fixed_lbl.config(foreground="#aaaaaa" if is_explicit else "#000000")

        preset_var.trace_add("write", _on_preset_change)
        _on_preset_change()

        # ── LLM toggle ────────────────────────────────────────────────────
        llm_var = tk.BooleanVar(value=saved.get("use_llm", False))
        ttk.Checkbutton(
            frm,
            text="Use LLM for NL summaries (C4 / C5 / C6 only)",
            variable=llm_var,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 0))
        row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=3,
                                sticky="ew", pady=(8, 4))
        row += 1

        # ── Status + buttons ──────────────────────────────────────────────
        status_var = tk.StringVar()
        ttk.Label(frm, textvariable=status_var,
                  foreground=FG_E).grid(
            row=row, column=0, columnspan=2, sticky="w")

        def _start() -> None:
            name = name_var.get().strip()
            if not name:
                status_var.set("Please enter a participant name.")
                return

            selected: list[tuple[int, str]] = []
            for code, (cv, ov) in cond_vars.items():
                if cv.get():
                    s = ov.get().strip()
                    if not s:
                        status_var.set(f"Please set an order for {code}.")
                        return
                    try:
                        selected.append((int(s), code))
                    except ValueError:
                        status_var.set(f"Order for {code} must be a number.")
                        return

            if not selected:
                status_var.set("Please select at least one condition.")
                return

            selected.sort()

            # Persist config (excluding the participant name)
            cfg = {
                "conditions": {
                    code: ov.get()
                    for code, (cv, ov) in cond_vars.items()
                    if cv.get()
                },
                "graph_preset": preset_var.get(),
                "fixed_constraints": bool(fixed_var.get()),
                "num_fixed_nodes": int(fixed_num_var.get()),
                "use_llm": bool(llm_var.get()),
            }
            try:
                config_path.write_text(json.dumps(cfg, indent=2),
                                       encoding="utf-8")
            except Exception:
                pass

            # Store study state
            self.participant_name = name
            self.selected_conditions = [c for _, c in selected]
            self.graph_preset = preset_var.get()
            self.use_llm = bool(llm_var.get())
            self._fixed_constraints = bool(fixed_var.get())
            self._num_fixed_nodes = int(fixed_num_var.get())

            safe = (
                "".join(c for c in name if c.isalnum() or c in " _-")
                [:40].strip().replace(" ", "_")
            )
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_root = Path(__file__).resolve().parent
            self.results_dir = (
                project_root / "results" / "participants" / f"{safe}_{ts}"
            )
            self.results_dir.mkdir(parents=True, exist_ok=True)

            self.study_meta = {
                "participant_name": self.participant_name,
                "timestamp_start": ts,
                "selected_conditions": self.selected_conditions,
                "graph_preset": self.graph_preset,
                "use_llm": self.use_llm,
                "fixed_constraints": self._fixed_constraints,
                "num_fixed_nodes": self._num_fixed_nodes,
            }
            self._save("setup.json", self.study_meta)
            self.show_pre_questionnaire()

        ttk.Button(frm, text="Start Study →", command=_start).grid(
            row=row, column=2, sticky="e", pady=4)
        row += 1
        ttk.Button(frm, text="Quit", command=self.root.destroy).grid(
            row=row, column=2, sticky="e")

        frm.columnconfigure(1, weight=1)

    # ─────────────────────────────────────────────────────────────────────────

    def _enter_study_flow(self) -> None:
        """Expand window from compact setup size to full study-flow size."""
        self.root.geometry("760x640")
        self.root.resizable(True, True)

    def show_pre_questionnaire(self) -> None:
        self._enter_study_flow()
        page = self._page()
        self._header(
            page, "Pre-Study Questionnaire",
            "Please answer these questions before starting the experiment.",
            step=self._step_label(1),
        )
        footer = self._footer(page)
        inner = self._scrollable(page)

        wmap = self._render_survey(inner, PRE_QUESTIONS)

        err_var = tk.StringVar()
        tk.Label(footer, textvariable=err_var, font=F_SM,
                 bg=BG, fg=FG_E).pack(side="left")

        def _next() -> None:
            self.pre_data = self._collect(wmap)
            self.pre_data["timestamp"] = datetime.now().isoformat()
            self._save("pre_questionnaire.json", self.pre_data)
            self.show_tutorial()

        ttk.Button(footer, text="Next →", command=_next).pack(side="right")
        ttk.Button(footer, text="← Back",
                   command=self.show_setup).pack(side="left")

    # ─────────────────────────────────────────────────────────────────────────

    def show_tutorial(self) -> None:
        page = self._page()
        self._header(
            page, "Instructions",
            "Please read carefully before beginning.",
            step=self._step_label(2),
        )
        footer = self._footer(page)

        tf = tk.Frame(page, bg=BG)
        tf.pack(fill="both", expand=True, padx=24, pady=8)

        tw = tk.Text(
            tf, font=("Courier New", 11), bg=BG_W, fg=FG,
            wrap="word", relief="solid", borderwidth=1,
            state="normal", padx=14, pady=14,
        )
        tw.insert("end", TUTORIAL_TEXT)
        tw.config(state="disabled")

        vsb = ttk.Scrollbar(tf, orient="vertical", command=tw.yview)
        tw.configure(yscrollcommand=vsb.set)
        tw.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _start() -> None:
            self.condition_idx = 0
            self.show_condition_transition()

        ttk.Button(
            footer,
            text="I have read the instructions — Begin Study →",
            command=_start,
        ).pack(side="right")
        ttk.Button(footer, text="← Back",
                   command=self.show_pre_questionnaire).pack(side="left")

    # ─────────────────────────────────────────────────────────────────────────

    def show_condition_transition(self) -> None:
        idx = self.condition_idx
        cond = self.selected_conditions[idx]
        cname = CONDITION_INFO.get(cond, cond)
        n = len(self.selected_conditions)
        step = 3 + 2 * idx   # 3, 5, 7, …

        page = self._page()
        self._header(
            page,
            f"Condition {idx + 1} of {n}",
            f"You are about to start:  {cond} — {cname}",
            step=self._step_label(step),
        )
        footer = self._footer(page)
        inner = tk.Frame(page, bg=BG)
        inner.pack(fill="both", expand=True, padx=28, pady=20)

        # Summary card
        card = tk.Frame(inner, bg=BG_W,
                        highlightthickness=1, highlightbackground="#e5e7eb")
        card.pack(fill="x", pady=8)
        lines = [
            ("Condition",    f"{cond} — {cname}"),
            ("Graph preset", self.graph_preset.capitalize()),
            ("Run",          f"{idx + 1} of {n}"),
        ]
        for label, value in lines:
            row_f = tk.Frame(card, bg=BG_W)
            row_f.pack(fill="x", padx=14, pady=3)
            tk.Label(row_f, text=f"{label}:", font=F_LB, bg=BG_W,
                     fg=FG_M, width=16, anchor="w").pack(side="left")
            tk.Label(row_f, text=value, font=F_LB, bg=BG_W,
                     fg=FG).pack(side="left")

        tk.Label(inner, text="\n"
                 "When you click 'Start Condition', a new experiment window will open.\n"
                 "Complete the colouring task, then close that window to continue.\n",
                 font=F_BD, bg=BG, fg=FG, justify="left",
                 wraplength=680).pack(anchor="w", pady=8)

        if idx > 0:
            tk.Label(
                inner,
                text="Note: this is a new condition — the constraint panel may look different.",
                font=F_SM, bg=BG, fg=FG_M, wraplength=680,
            ).pack(anchor="w")

        ttk.Button(footer, text="Start Condition →",
                   command=self.show_running).pack(side="right")

    # ─────────────────────────────────────────────────────────────────────────

    def show_running(self) -> None:
        idx = self.condition_idx
        cond = self.selected_conditions[idx]
        cname = CONDITION_INFO.get(cond, cond)
        n = len(self.selected_conditions)
        step = 3 + 2 * idx

        page = self._page()
        self._header(
            page,
            "Experiment Running",
            f"Condition {idx + 1} of {n}:  {cond} — {cname}",
            step=self._step_label(step),
        )

        inner = tk.Frame(page, bg=BG)
        inner.pack(fill="both", expand=True, padx=28, pady=30)

        status_var = tk.StringVar(value="Starting experiment window…")
        tk.Label(inner, textvariable=status_var, font=F_H2,
                 bg=BG, fg=FG).pack(pady=16)
        tk.Label(
            inner,
            text="Complete the task in the experiment window, then close it to continue.",
            font=F_LB, bg=BG, fg=FG_M, wraplength=560,
        ).pack()

        # Simple animated dots
        dot_var = tk.StringVar(value="")
        tk.Label(inner, textvariable=dot_var, font=("Arial", 28),
                 bg=BG, fg=ACCENT).pack(pady=24)
        _frames = ["●○○", "○●○", "○○●", "○●○"]
        _fi = [0]

        def _anim() -> None:
            if not self._proc_done:
                dot_var.set(_frames[_fi[0] % len(_frames)])
                _fi[0] += 1
                self.root.after(420, _anim)

        self.root.after(80, _anim)

        out_dir = self.results_dir / f"condition_{idx + 1}_{cond}"

        def _done() -> None:
            status_var.set("Experiment complete.  Loading survey…")
            self.root.after(900, self.show_inter_survey)

        self._launch_condition(cond, out_dir, _done)

    # ─────────────────────────────────────────────────────────────────────────

    def show_inter_survey(self) -> None:
        idx = self.condition_idx
        cond = self.selected_conditions[idx]
        cname = CONDITION_INFO.get(cond, cond)
        step = 4 + 2 * idx   # 4, 6, 8, …

        page = self._page()
        self._header(
            page,
            f"Condition {idx + 1} Survey",
            f"Please rate your experience with:  {cond} — {cname}",
            step=self._step_label(step),
        )
        footer = self._footer(page)
        inner = self._scrollable(page)

        tk.Label(inner, text=f"Condition:  {cond} — {cname}",
                 font=F_H2, bg=BG, fg=ACCENT).pack(anchor="w", pady=(0, 8))

        wmap = self._render_survey(inner, INTER_QUESTIONS)

        err_var = tk.StringVar()
        tk.Label(footer, textvariable=err_var, font=F_SM,
                 bg=BG, fg=FG_E).pack(side="left")

        def _next() -> None:
            data = self._collect(wmap)
            data["condition"] = cond
            data["condition_name"] = cname
            data["timestamp"] = datetime.now().isoformat()
            self.inter_data.append(data)
            self._save(f"condition_{idx + 1}_{cond}_survey.json", data)

            self.condition_idx += 1
            if self.condition_idx < len(self.selected_conditions):
                self.show_condition_transition()
            else:
                self.show_final_survey()

        next_label = (
            "Next Condition →"
            if self.condition_idx + 1 < len(self.selected_conditions)
            else "Final Survey →"
        )
        ttk.Button(footer, text=next_label, command=_next).pack(side="right")

    # ─────────────────────────────────────────────────────────────────────────

    def show_final_survey(self) -> None:
        n = len(self.selected_conditions)
        step = 2 + 2 * n + 1   # last step

        page = self._page()
        self._header(
            page, "Final Survey",
            "Almost done — a few final questions about the overall study.",
            step=self._step_label(step),
        )
        footer = self._footer(page)
        inner = self._scrollable(page)

        _ORDINALS = ["FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH"]
        dyn_opts = [
            f"{_ORDINALS[i]} MODE — {CONDITION_INFO.get(c, c)}"
            for i, c in enumerate(self.selected_conditions)
        ]
        wmap = self._render_survey(inner, FINAL_QUESTIONS, dyn_opts=dyn_opts)

        err_var = tk.StringVar()
        tk.Label(footer, textvariable=err_var, font=F_SM,
                 bg=BG, fg=FG_E).pack(side="left")

        def _submit() -> None:
            self.final_data = self._collect(wmap)
            self.final_data["timestamp"] = datetime.now().isoformat()
            self._save("final_survey.json", self.final_data)

            log = {
                **self.study_meta,
                "timestamp_end": datetime.now().isoformat(),
                "n_conditions": len(self.selected_conditions),
                "conditions_order": self.selected_conditions,
                "inter_surveys": len(self.inter_data),
            }
            self._save("study_log.json", log)
            self.show_done()

        ttk.Button(footer, text="Submit & Finish",
                   command=_submit).pack(side="right")

    # ─────────────────────────────────────────────────────────────────────────

    def show_done(self) -> None:
        page = self._page()
        inner = tk.Frame(page, bg=BG)
        inner.pack(expand=True)

        tk.Label(inner, text="Study Complete",
                 font=F_TIT, bg=BG, fg=FG).pack(pady=(50, 12))
        tk.Label(inner, text="Thank you for participating!",
                 font=F_BD, bg=BG, fg=FG).pack()
        tk.Label(inner, text="Your responses have been saved.",
                 font=F_LB, bg=BG, fg=FG_M).pack(pady=4)

        if self.results_dir is not None:
            tk.Label(
                inner,
                text=f"Results folder:\n{self.results_dir}",
                font=F_SM, bg=BG, fg=FG_M, justify="center",
            ).pack(pady=16)

        ttk.Button(inner, text="Close",
                   command=self.root.destroy).pack(pady=12)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    StudyApp()


if __name__ == "__main__":
    main()
