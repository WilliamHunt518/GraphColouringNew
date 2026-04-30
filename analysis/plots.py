"""
All plot-generating functions.

Each function saves one figure to out_dir and returns the Path.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from .data_loader import ParticipantData, TrialData
from .metrics import (
    compute_trial_metrics, extract_summary_survey,
    reconstruct_clash_series, get_strategy_timeline,
    classify_suggestion_quality,
    COMPLEXITY_ORDER,
)

# ── Palette ───────────────────────────────────────────────────────────────────
COMPLEXITY_COLORS = {
    "easy":     "#4caf50",
    "medium":   "#ff9800",
    "hard":     "#f44336",
    "tutorial": "#9e9e9e",
}
MODE_COLORS = {
    "M1":               "#5c85d6",
    "M2":               "#8fbc8f",
    "M3":               "#ffa500",
    "flex_watch_setup": "#cc99ff",
    "flex_auto":        "#cc5500",
    "flex_auto_mixed":  "#cc5500",
}
MODE_LABELS = {
    "M1":               "M1: Manual click",
    "M2":               "M2: Apply suggestion",
    "M3":               "M3: Watch:Auto batch",
    "flex_watch_setup": "Watch setup (mid-game)",
    "flex_auto":        "Agent auto-fix",
    "flex_auto_mixed":  "Agent auto-fix",
}
QUALITY_COLORS = {
    "clean_accepted":       "#2ca02c",
    "clean_modified":       "#98df8a",
    "clean_bad_applied":    "#d62728",
    "unavoidable_accepted": "#ff7f0e",
    "unavoidable_modified": "#ffbb78",
    "cancelled":            "#aec7e8",
}
QUALITY_LABELS = {
    "clean_accepted":       "Clean — accepted as-is",
    "clean_modified":       "Clean — user tweaked",
    "clean_bad_applied":    "Bad — epsilon error, accepted",
    "unavoidable_accepted": "Unavoidable clash — accepted",
    "unavoidable_modified": "Unavoidable clash — tweaked",
    "cancelled":            "Cancelled",
}
PARTICIPANT_COLORS  = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b"]
PARTICIPANT_MARKERS = ["o","s","^","D","v","P"]

_MODE_ORDER = ["M1","M2","M3","flex_watch_setup","flex_auto","flex_auto_mixed"]
_QUALITY_ORDER = [
    "clean_accepted","clean_modified","clean_bad_applied",
    "unavoidable_accepted","unavoidable_modified","cancelled",
]


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

def _save(fig, path: Path) -> Path:
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path

def _pid(p: ParticipantData) -> str:
    return p.pid_label or p.participant_id

def _label_to_complexity(label: str) -> str:
    ll = label.lower()
    for c in COMPLEXITY_ORDER:
        if c in ll: return c
    return ll


# ══════════════════════════════════════════════════════════════════════════════
#  PER-PARTICIPANT PLOTS
# ══════════════════════════════════════════════════════════════════════════════

def plot_performance_bars(p: ParticipantData, out_dir: Path) -> Path:
    game_trials = [t for t in p.trials if not t.config.get("is_tutorial")]
    if not game_trials: return None

    labels   = [t.config.get("complexity","?").capitalize() for t in game_trials]
    clsh_sec = [t.summary.get("clash_seconds",0) for t in game_trials]
    clsh_pct = [t.summary.get("clash_pct",0)     for t in game_trials]
    colors   = [COMPLEXITY_COLORS.get(t.config.get("complexity",""),"#888") for t in game_trials]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    fig.suptitle(f"{_pid(p)} — Performance", fontsize=13, fontweight="bold")
    x = np.arange(len(labels))
    for ax, vals, ylabel, title, hline in [
        (ax1, clsh_sec, "Clash-seconds",     "Total pair-clash time",       None),
        (ax2, clsh_pct, "Clash % of duration","Clash % (>100% = multi-pair)", 100),
    ]:
        ax.bar(x, vals, color=colors, edgecolor="white", linewidth=0.8)
        ax.set_xticks(x); ax.set_xticklabels(labels)
        ax.set_ylabel(ylabel); ax.set_title(title); ax.set_ylim(bottom=0)
        if hline:
            ax.axhline(hline, linestyle="--", color="gray", linewidth=0.8, label=f"{hline}%")
            ax.legend(fontsize=8)

    _ensure(out_dir)
    return _save(fig, out_dir / "performance_bars.png")


def plot_clash_area(p: ParticipantData, out_dir: Path) -> Path:
    """
    Area chart showing number of simultaneously clashing pairs over time.
    One subplot per game trial. A moving-average line overlays the step function.
    """
    game_trials = [t for t in p.trials if not t.config.get("is_tutorial")]
    if not game_trials: return None

    n = len(game_trials)
    fig, axes = plt.subplots(n, 1, figsize=(12, 3 * n), squeeze=False)
    fig.suptitle(f"{_pid(p)} — Clashing Pairs Over Time", fontsize=13, fontweight="bold")

    for row, trial in enumerate(game_trials):
        ax       = axes[row][0]
        duration = trial.config.get("duration", trial.summary.get("elapsed", 120))
        comp     = trial.config.get("complexity", trial.label)
        color    = COMPLEXITY_COLORS.get(comp, "#888")

        times, counts = reconstruct_clash_series(trial.events, duration)

        # Build dense step arrays for fill_between
        t_step = [times[0]]
        c_step = [counts[0]]
        for i in range(1, len(times)):
            t_step.append(times[i])
            c_step.append(counts[i - 1])   # hold previous until new event
            t_step.append(times[i])
            c_step.append(counts[i])

        t_arr = np.array(t_step)
        c_arr = np.array(c_step, dtype=float)

        ax.fill_between(t_arr, c_arr, step="pre", alpha=0.35, color=color, linewidth=0)
        ax.step(t_arr, c_arr, where="pre", color=color, linewidth=1.2, alpha=0.7)

        # Moving-average line (15-second window sampled at 2Hz)
        if duration > 0:
            sample_t = np.arange(0, duration, 0.5)
            sample_c = np.interp(sample_t, times, [counts[max(0,i-1)] for i in range(len(counts))])
            win = max(1, int(15 / 0.5))
            ma  = np.convolve(sample_c, np.ones(win)/win, mode="same")
            ax.plot(sample_t, ma, color="black", linewidth=1.8,
                    linestyle="--", alpha=0.7, label="15s moving avg")

        # Mark switch events — group by mode to build shaded regions
        switch_events = [
            (e["elapsed"], e.get("mode", ""))
            for e in trial.events
            if e["event"] == "switch_requested" and e.get("elapsed", 0) > 0
        ]

        max_c = max(c_arr) if len(c_arr) else 1
        y_top = max(max_c + 0.5, 1.5)

        # Shade inter-switch regions by the mode used in that segment
        if switch_events:
            region_boundaries = [0.0] + [t for t, _ in switch_events] + [duration]
            region_modes      = [""] + [m for _, m in switch_events]
            for k in range(len(switch_events)):
                t0, t1 = region_boundaries[k], region_boundaries[k + 1]
                m = region_modes[k + 1]
                col = MODE_COLORS.get(m, "#888")
                ax.axvspan(t0, t1, alpha=0.06, color=col, linewidth=0)

        # Vertical lines + short mode labels at each switch
        prev_t_label: Dict[str, float] = {}
        for t_sw, mode in switch_events:
            col = MODE_COLORS.get(mode, "#555")
            ax.axvline(t_sw, color=col, alpha=0.7, linewidth=1.4, zorder=3)
            short = mode.split("_")[0] if mode.startswith("flex") else mode
            last  = prev_t_label.get(mode, -999)
            if t_sw - last > duration * 0.04:
                ax.text(t_sw + duration * 0.005, y_top * 0.92, short,
                        color=col, fontsize=6, va="top", rotation=90,
                        clip_on=True, zorder=4)
                prev_t_label[mode] = t_sw

        ax.set_xlim(0, duration)
        ax.set_ylim(-0.1, y_top)
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.set_xlabel("Elapsed (s)")
        ax.set_ylabel("Clashing pairs")
        ax.set_title(
            f"{comp.capitalize()} — {trial.summary.get('clash_seconds',0):.1f}s total "
            f"clash-pair-time  ({trial.summary.get('clash_pct',0):.0f}%)",
            fontsize=9
        )

    # Legend for switch modes (first subplot only)
    patches = [mpatches.Patch(color=c, alpha=0.7, label=MODE_LABELS.get(m, m))
               for m, c in MODE_COLORS.items() if m != "flex_auto_mixed"]
    axes[0][0].legend(handles=patches + [
        plt.Line2D([0],[0], color="black", linewidth=1.8, linestyle="--", label="15s moving avg")
    ], fontsize=6, loc="upper right", ncol=2)

    fig.tight_layout()
    _ensure(out_dir)
    return _save(fig, out_dir / "clash_area.png")


def plot_intervention_breakdown(p: ParticipantData, out_dir: Path) -> Path:
    """
    Multi-panel intervention analysis:
      Row 0: Setup-phase strategy (what watch mode did they pick?)
      Row 1: In-game switch counts by mode, bucketed over time
      Row 2: Running cumulative switches by mode (shows strategy changes)
    One column per game trial.
    """
    game_trials = [t for t in p.trials if not t.config.get("is_tutorial")]
    if not game_trials: return None

    n = len(game_trials)
    fig, axes = plt.subplots(3, n, figsize=(5 * n, 12), squeeze=False)
    fig.suptitle(f"{_pid(p)} — Intervention Analysis", fontsize=13, fontweight="bold")

    for col, trial in enumerate(game_trials):
        comp     = trial.config.get("complexity", trial.label).capitalize()
        duration = trial.config.get("duration", trial.summary.get("elapsed", 120))
        color    = COMPLEXITY_COLORS.get(trial.config.get("complexity",""), "#888")

        # ── Row 0: Setup strategy ─────────────────────────────────────────
        ax0 = axes[0][col]
        setup_switches = [e for e in trial.events
                          if e["event"] == "switch_requested" and e.get("elapsed",0) == 0]
        setup_mc: Dict[str, int] = {}
        for s in setup_switches:
            m = s.get("mode","unknown")
            setup_mc[m] = setup_mc.get(m,0) + 1

        watch_events = [e for e in trial.events
                        if e["event"] == "watch_mode_set" and e.get("elapsed",0) == 0]
        watch_mc: Dict[str, int] = {}
        for w in watch_events:
            m = w.get("mode","unknown")
            watch_mc[m] = watch_mc.get(m,0) + 1

        items   = {k: v for d in [setup_mc, watch_mc] for k, v in d.items()}
        keys    = [k for k in _MODE_ORDER if k in items] + [k for k in items if k not in _MODE_ORDER]
        vals    = [items.get(k,0) for k in keys]
        col_arr = [MODE_COLORS.get(k,"#aaa") for k in keys]
        lbls    = [MODE_LABELS.get(k, k) for k in keys]

        if vals and sum(vals) > 0:
            ax0.barh(lbls, vals, color=col_arr, edgecolor="white")
        else:
            ax0.text(0.5, 0.5, "No setup actions", ha="center", va="center",
                     transform=ax0.transAxes, color="gray")
        ax0.set_title(f"{comp}\nSetup phase actions", fontsize=9)
        ax0.set_xlabel("Count")

        # ── Row 1: In-game bucketed by time ───────────────────────────────
        ax1 = axes[1][col]
        strat = get_strategy_timeline(trial.events, duration, n_buckets=6)
        buckets = strat.get("buckets", [])
        bucket_size = strat.get("bucket_size", duration/6)
        n_b = len(buckets)
        x_b = np.arange(n_b)
        bucket_labels = [f"{int(i*bucket_size)}–{int((i+1)*bucket_size)}s" for i in range(n_b)]
        bottom = np.zeros(n_b)

        for mode in _MODE_ORDER:
            vals_b = np.array([b.get(mode,0) for b in buckets], dtype=float)
            if vals_b.sum() == 0: continue
            ax1.bar(x_b, vals_b, bottom=bottom,
                    color=MODE_COLORS.get(mode,"#aaa"), label=MODE_LABELS.get(mode,mode),
                    edgecolor="white", linewidth=0.5)
            bottom += vals_b

        ax1.set_xticks(x_b)
        ax1.set_xticklabels(bucket_labels, rotation=30, ha="right", fontsize=7)
        ax1.set_ylabel("Switches")
        ax1.set_title("In-game switches over time", fontsize=9)
        if col == 0:
            ax1.legend(fontsize=6, loc="upper left")

        # ── Row 2: Cumulative switches by mode ────────────────────────────
        ax2 = axes[2][col]
        ingame = sorted(
            [e for e in trial.events
             if e["event"] == "switch_requested" and e.get("elapsed",0) > 0],
            key=lambda e: e["elapsed"]
        )
        cum: Dict[str, List] = {m: [] for m in _MODE_ORDER}
        cum_t: Dict[str, List] = {m: [0.0] for m in _MODE_ORDER}
        cum_v: Dict[str, List] = {m: [0]   for m in _MODE_ORDER}

        for sw in ingame:
            m = sw.get("mode","unknown")
            if m not in cum_v: continue
            t = sw["elapsed"]
            cum_t[m].append(t)
            cum_v[m].append(cum_v[m][-1] + 1)

        for m in _MODE_ORDER:
            if max(cum_v[m]) == 0: continue
            ts = cum_t[m] + [duration]
            vs = cum_v[m] + [cum_v[m][-1]]
            ax2.step(ts, vs, where="post",
                     color=MODE_COLORS.get(m,"#aaa"),
                     label=MODE_LABELS.get(m,m), linewidth=1.8)

        ax2.set_xlim(0, duration)
        ax2.set_xlabel("Elapsed (s)")
        ax2.set_ylabel("Cumulative switches")
        ax2.set_title("Cumulative — strategy over time", fontsize=9)
        if col == 0:
            ax2.legend(fontsize=6, loc="upper left")

    fig.tight_layout()
    _ensure(out_dir)
    return _save(fig, out_dir / "intervention_detail.png")


def plot_suggestion_quality(p: ParticipantData, out_dir: Path) -> Path:
    """
    Per-trial suggestion quality breakdown:
      Top: stacked bar of quality categories per trial
      Bottom: acceptance rate with good/bad split
    """
    game_trials = [t for t in p.trials
                   if not t.config.get("is_tutorial") and t.events]
    if not game_trials: return None

    n = len(game_trials)
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(max(7, n*2.5), 9))
    fig.suptitle(f"{_pid(p)} — Suggestion Quality", fontsize=13, fontweight="bold")

    trial_labels = [t.config.get("complexity","?").capitalize() for t in game_trials]
    x = np.arange(n)

    # ── Top: stacked bars ────────────────────────────────────────────────────
    bottom = np.zeros(n)
    for cat in _QUALITY_ORDER:
        vals = np.array([
            sum(1 for s in classify_suggestion_quality(
                t.events, t.config.get("switch_duration",3.0))
                if s["quality"] == cat)
            for t in game_trials
        ], dtype=float)
        if vals.sum() == 0: continue
        ax_top.bar(x, vals, bottom=bottom,
                   color=QUALITY_COLORS[cat], label=QUALITY_LABELS[cat],
                   edgecolor="white", linewidth=0.5)
        bottom += vals

    ax_top.set_xticks(x); ax_top.set_xticklabels(trial_labels)
    ax_top.set_ylabel("Suggestions")
    ax_top.set_title("All suggestions by quality category")
    ax_top.legend(fontsize=7, loc="upper right")

    # ── Bottom: rates ────────────────────────────────────────────────────────
    rate_data = []
    for t in game_trials:
        sq  = classify_suggestion_quality(t.events, t.config.get("switch_duration",3.0))
        n_applied = sum(1 for s in sq if s["applied"])
        n_bad     = sum(1 for s in sq if s["quality"] == "clean_bad_applied")
        n_clean   = sum(1 for s in sq if s["quality"] in ("clean_accepted","clean_modified"))
        n_unavoid = sum(1 for s in sq if s["applied"] and s["infeasible"])
        n_cancel  = sum(1 for s in sq if not s["applied"])
        total     = len(sq)
        rate_data.append({
            "accept":  n_applied/total*100     if total   > 0 else 0,
            "bad":     n_bad/max(n_applied,1)*100,
            "clean":   n_clean/max(n_applied,1)*100,
            "unavoid": n_unavoid/max(n_applied,1)*100,
        })

    width = 0.22
    for i, (key, label, col) in enumerate([
        ("accept",  "Accept rate (%)",                 "#5c85d6"),
        ("clean",   "Clean-accepted / applied (%)",    QUALITY_COLORS["clean_accepted"]),
        ("bad",     "Bad-applied / applied (epsilon %)", QUALITY_COLORS["clean_bad_applied"]),
        ("unavoid", "Unavoidable / applied (%)",        QUALITY_COLORS["unavoidable_accepted"]),
    ]):
        vals = [rd[key] for rd in rate_data]
        offset = (i - 1.5) * width
        bars = ax_bot.bar(x + offset, vals, width=width, color=col, label=label,
                          edgecolor="white", linewidth=0.5, alpha=0.85)
        for bar, v in zip(bars, vals):
            if v > 3:
                ax_bot.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                            f"{v:.0f}", ha="center", va="bottom", fontsize=7)

    ax_bot.set_xticks(x); ax_bot.set_xticklabels(trial_labels)
    ax_bot.set_ylabel("Percentage (%)")
    ax_bot.set_ylim(0, 115)
    ax_bot.set_title("Suggestion rates (accept / clean / bad / unavoidable)")
    ax_bot.axhline(100, linestyle="--", color="gray", linewidth=0.7, alpha=0.5)
    ax_bot.legend(fontsize=7)

    fig.tight_layout()
    _ensure(out_dir)
    return _save(fig, out_dir / "suggestion_quality.png")


def plot_survey_per_participant(p: ParticipantData, out_dir: Path) -> Path:
    game_trials = [t for t in p.trials if not t.config.get("is_tutorial") and t.survey]
    if not game_trials: return None

    TLX_KEYS   = ["tlx_mental","tlx_physical","tlx_temporal",
                  "tlx_performance","tlx_effort","tlx_frustration"]
    TLX_LABELS = ["Mental","Physical","Temporal","Performance","Effort","Frustration"]
    TRUST_KEYS  = ["trust_suspicious","trust_wary","trust_confident",
                   "trust_reliable","trust_overall","trust_accepted"]
    TRUST_LABELS= ["Suspicious*","Wary*","Confident","Reliable","Overall","Accepted"]
    TAM_KEYS    = ["tam_improved","tam_easy","tam_useful","tam_would_use"]
    TAM_LABELS  = ["Improved WF","Easy to use","Useful","Would use"]

    n = len(game_trials)
    fig, axes = plt.subplots(3, n, figsize=(4.5*n, 11), squeeze=False)
    fig.suptitle(f"{_pid(p)} — Survey Responses  (* = negative items, higher = worse trust)",
                 fontsize=11, fontweight="bold")

    for col, trial in enumerate(game_trials):
        sv = trial.survey
        complexity = trial.config.get("complexity", trial.label).capitalize()
        color = COMPLEXITY_COLORS.get(trial.config.get("complexity",""),"#888")

        for ax, keys, labels, title, xlim in [
            (axes[0][col], TLX_KEYS,   TLX_LABELS,   f"{complexity}\nNASA-TLX (0–20)", 20),
            (axes[1][col], TRUST_KEYS, TRUST_LABELS,  "Trust (1–7)",                    7),
            (axes[2][col], TAM_KEYS,   TAM_LABELS,    "TAM (1–7)",                      7),
        ]:
            vals      = [sv.get(k,0) for k in keys]
            bar_cols  = (["#e57373" if k in ("trust_suspicious","trust_wary") else "#81c784"
                          for k in keys]
                         if "trust" in keys[0] else [color]*len(keys))
            ax.barh(labels, vals, color=bar_cols, alpha=0.85)
            ax.set_xlim(0, xlim)
            ax.axvline(xlim/2, color="gray", linestyle="--", linewidth=0.7, alpha=0.5)
            ax.set_title(title, fontsize=9)

    fig.tight_layout()
    _ensure(out_dir)
    return _save(fig, out_dir / "survey_responses.png")


def plot_summary_survey(p: ParticipantData, out_dir: Path) -> Path:
    rows = extract_summary_survey(p)
    if not rows: return None

    keys   = ["difficulty","tool_usefulness","manual_frequency","confidence"]
    labels = ["Difficulty","Tool Usefulness","Manual Frequency","Confidence"]

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.suptitle(f"{_pid(p)} — Post-Session Summary Survey (1–7)",
                 fontsize=12, fontweight="bold")
    x = np.arange(len(keys))
    width = 0.8 / max(len(rows), 1)

    for i, row in enumerate(rows):
        label  = row.get("label","")
        comp   = _label_to_complexity(label)
        color  = COMPLEXITY_COLORS.get(comp, "#888")
        offset = (i - (len(rows)-1)/2) * width
        ax.bar(x + offset, [row.get(k,0) for k in keys],
               width=width*0.9, color=color, alpha=0.85,
               label=label, edgecolor="white")

    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylim(0, 7.5)
    ax.axhline(4, linestyle="--", color="gray", linewidth=0.7, alpha=0.5)
    ax.set_ylabel("Rating"); ax.legend(fontsize=8)

    _ensure(out_dir)
    return _save(fig, out_dir / "summary_survey.png")


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP PLOTS
# ══════════════════════════════════════════════════════════════════════════════

def plot_group_performance(participants: List[ParticipantData], out_dir: Path) -> Path:
    by_comp: Dict[str, list] = {c: [] for c in COMPLEXITY_ORDER}
    for p in participants:
        for t in p.trials:
            if t.config.get("is_tutorial"): continue
            comp = t.config.get("complexity","")
            if comp in by_comp:
                by_comp[comp].append({
                    "pid": _pid(p), "pidx": participants.index(p),
                    "clash_pct": t.summary.get("clash_pct",0),
                    "clash_sec": t.summary.get("clash_seconds",0),
                })

    comps = [c for c in COMPLEXITY_ORDER if by_comp[c]]
    x = np.arange(len(comps))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    fig.suptitle("Group Performance by Complexity", fontsize=13, fontweight="bold")

    for ax, key, ylabel, title, hline in [
        (ax1, "clash_pct", "Clash %",       "Clash % of trial duration",  100),
        (ax2, "clash_sec", "Clash-seconds", "Absolute pair-clash time",    None),
    ]:
        means  = [np.mean([d[key] for d in by_comp[c]]) for c in comps]
        colors = [COMPLEXITY_COLORS.get(c,"#888") for c in comps]
        ax.bar(x, means, color=colors, alpha=0.6, edgecolor="white")
        for ci, comp in enumerate(comps):
            for d in by_comp[comp]:
                i = d["pidx"]
                ax.scatter(ci, d[key],
                           color=PARTICIPANT_COLORS[i % len(PARTICIPANT_COLORS)],
                           marker=PARTICIPANT_MARKERS[i % len(PARTICIPANT_MARKERS)],
                           s=90, zorder=5, edgecolors="white", linewidth=0.5,
                           label=d["pid"] if ci == 0 else "_")
        ax.set_xticks(x); ax.set_xticklabels([c.capitalize() for c in comps])
        ax.set_ylabel(ylabel); ax.set_title(title); ax.set_ylim(bottom=0)
        if hline:
            ax.axhline(hline, linestyle="--", color="gray", linewidth=0.8, label=f"{hline}%")
        ax.legend(fontsize=8)

    _ensure(out_dir)
    return _save(fig, out_dir / "group_performance.png")


def plot_group_clash_area(participants: List[ParticipantData], out_dir: Path) -> Path:
    """
    Combined clash area chart: one column per complexity, one row per participant.
    Lets you directly compare the same scenario across people.
    """
    game_data = {c: [] for c in COMPLEXITY_ORDER}
    for p in participants:
        for t in p.trials:
            if t.config.get("is_tutorial"): continue
            comp = t.config.get("complexity","")
            if comp in game_data:
                game_data[comp].append((p, t))

    comps = [c for c in COMPLEXITY_ORDER if game_data[c]]
    n_p   = len(participants)
    n_c   = len(comps)
    if n_c == 0: return None

    fig, axes = plt.subplots(n_p, n_c, figsize=(5*n_c, 3*n_p), squeeze=False)
    fig.suptitle("Clashing Pairs Over Time — All Participants", fontsize=13, fontweight="bold")

    for ci, comp in enumerate(comps):
        axes[0][ci].set_title(comp.capitalize(), fontsize=11, fontweight="bold")
        for pi, p in enumerate(participants):
            ax    = axes[pi][ci]
            color = COMPLEXITY_COLORS.get(comp,"#888")
            # find this participant's trial for this complexity
            entry = next((td for pp, td in game_data[comp] if pp is p), None)
            if entry is None:
                ax.text(0.5, 0.5, "No data", ha="center", va="center",
                        transform=ax.transAxes, color="gray")
                continue
            trial    = entry
            duration = trial.config.get("duration", trial.summary.get("elapsed",120))
            times, counts = reconstruct_clash_series(trial.events, duration)

            t_step, c_step = [times[0]], [counts[0]]
            for i in range(1, len(times)):
                t_step += [times[i], times[i]]
                c_step += [counts[i-1], counts[i]]
            t_arr = np.array(t_step)
            c_arr = np.array(c_step, dtype=float)

            ax.fill_between(t_arr, c_arr, step="pre", alpha=0.4, color=color)
            ax.step(t_arr, c_arr, where="pre", color=color, linewidth=1.2)

            # Moving average
            if duration > 0:
                st = np.arange(0, duration, 0.5)
                sc = np.interp(st, times, [counts[max(0,i-1)] for i in range(len(counts))])
                win = max(1, int(15/0.5))
                ax.plot(st, np.convolve(sc, np.ones(win)/win, mode="same"),
                        color="black", linewidth=1.5, linestyle="--", alpha=0.6)

            # Mode switch markers
            max_c = max(c_arr) if len(c_arr) else 1
            y_top = max(max_c + 0.5, 1.5)
            switch_events = [
                (e["elapsed"], e.get("mode", ""))
                for e in trial.events
                if e["event"] == "switch_requested" and e.get("elapsed", 0) > 0
            ]
            prev_t_label: Dict[str, float] = {}
            for t_sw, mode in switch_events:
                mcol = MODE_COLORS.get(mode, "#555")
                ax.axvline(t_sw, color=mcol, alpha=0.65, linewidth=1.2, zorder=3)
                short = mode.split("_")[0] if mode.startswith("flex") else mode
                last  = prev_t_label.get(mode, -999)
                if t_sw - last > duration * 0.05:
                    ax.text(t_sw + duration * 0.005, y_top * 0.92, short,
                            color=mcol, fontsize=5, va="top", rotation=90,
                            clip_on=True, zorder=4)
                    prev_t_label[mode] = t_sw

            ax.set_xlim(0, duration)
            ax.set_ylim(-0.1, y_top)
            ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
            if ci == 0:
                ax.set_ylabel(f"{_pid(p)}\n# clashing pairs", fontsize=8)
            if pi == n_p - 1:
                ax.set_xlabel("Elapsed (s)")

    fig.tight_layout()
    _ensure(out_dir)
    return _save(fig, out_dir / "group_clash_area.png")


def plot_group_interventions(participants: List[ParticipantData], out_dir: Path) -> Path:
    """
    One row per participant, one column per complexity.
    Each cell: stacked bar of in-game switch modes.
    """
    game_data: Dict[str, list] = {c: [] for c in COMPLEXITY_ORDER}
    for p in participants:
        for t in p.trials:
            if t.config.get("is_tutorial"): continue
            comp = t.config.get("complexity","")
            if comp in game_data: game_data[comp].append((p, t))

    comps = [c for c in COMPLEXITY_ORDER if game_data[c]]
    n_p   = len(participants)
    n_c   = len(comps)
    if n_c == 0: return None

    fig, axes = plt.subplots(n_p, n_c, figsize=(4*n_c, 4*n_p), squeeze=False)
    fig.suptitle("In-Game Switch Modes — All Participants", fontsize=13, fontweight="bold")

    for ci, comp in enumerate(comps):
        axes[0][ci].set_title(comp.capitalize(), fontsize=11, fontweight="bold")
        for pi, p in enumerate(participants):
            ax    = axes[pi][ci]
            entry = next((td for pp, td in game_data[comp] if pp is p), None)
            if ci == 0:
                ax.set_ylabel(_pid(p), fontsize=9, fontweight="bold")
            if entry is None:
                ax.set_visible(False); continue

            trial    = entry
            duration = trial.config.get("duration", 120)
            strat    = get_strategy_timeline(trial.events, duration, n_buckets=5)
            buckets  = strat.get("buckets",[])
            bsz      = strat.get("bucket_size", duration/5)
            n_b      = len(buckets)
            x_b      = np.arange(n_b)
            bottom   = np.zeros(n_b)

            for mode in _MODE_ORDER:
                vals = np.array([b.get(mode,0) for b in buckets], dtype=float)
                if vals.sum() == 0: continue
                ax.bar(x_b, vals, bottom=bottom,
                       color=MODE_COLORS.get(mode,"#aaa"),
                       label=MODE_LABELS.get(mode,mode),
                       edgecolor="white", linewidth=0.4)
                bottom += vals

            ax.set_xticks(x_b)
            ax.set_xticklabels([f"{int(i*bsz)}" for i in range(n_b)], fontsize=6)
            ax.set_ylim(bottom=0)
            if pi == 0 and ci == 0:
                ax.legend(fontsize=5, loc="upper right")

    # Shared legend
    patches = [mpatches.Patch(color=MODE_COLORS.get(m,"#aaa"), label=MODE_LABELS.get(m,m))
               for m in _MODE_ORDER]
    fig.legend(handles=patches, fontsize=7, loc="lower center",
               ncol=len(_MODE_ORDER)//2, bbox_to_anchor=(0.5, -0.02))

    fig.tight_layout(rect=[0, 0.05, 1, 1])
    _ensure(out_dir)
    return _save(fig, out_dir / "group_interventions.png")


def plot_group_suggestion_quality(participants: List[ParticipantData], out_dir: Path) -> Path:
    """
    Stacked bars: one group per complexity, bars per participant,
    showing suggestion quality breakdown.
    """
    game_data: Dict[str, list] = {c: [] for c in COMPLEXITY_ORDER}
    for p in participants:
        for t in p.trials:
            if t.config.get("is_tutorial"): continue
            comp = t.config.get("complexity","")
            if comp in game_data: game_data[comp].append((p, t))

    comps = [c for c in COMPLEXITY_ORDER if game_data[c]]
    if not comps: return None

    n_p = len(participants)
    fig, axes = plt.subplots(1, len(comps), figsize=(5*len(comps), 6), squeeze=False)
    fig.suptitle("Suggestion Quality — All Participants", fontsize=13, fontweight="bold")

    for ci, comp in enumerate(comps):
        ax    = axes[0][ci]
        ax.set_title(comp.capitalize(), fontsize=11)
        pid_labels = []
        for pi, p in enumerate(participants):
            entry = next((td for pp, td in game_data[comp] if pp is p), None)
            if entry is None:
                pid_labels.append(_pid(p))
                continue
            trial = entry
            sq    = classify_suggestion_quality(trial.events, trial.config.get("switch_duration",3.0))
            bottom = 0.0
            for cat in _QUALITY_ORDER:
                v = sum(1 for s in sq if s["quality"] == cat)
                if v > 0:
                    ax.bar(pi, v, bottom=bottom,
                           color=QUALITY_COLORS[cat],
                           label=QUALITY_LABELS[cat] if ci == 0 and pi == 0 else "_",
                           edgecolor="white", linewidth=0.5)
                    bottom += v
            pid_labels.append(_pid(p))

        ax.set_xticks(range(n_p))
        ax.set_xticklabels(pid_labels)
        ax.set_ylabel("Suggestions")

    # Legend
    patches = [mpatches.Patch(color=QUALITY_COLORS[c], label=QUALITY_LABELS[c])
               for c in _QUALITY_ORDER]
    fig.legend(handles=patches, fontsize=7, loc="lower center",
               ncol=3, bbox_to_anchor=(0.5, -0.05))

    fig.tight_layout(rect=[0, 0.1, 1, 1])
    _ensure(out_dir)
    return _save(fig, out_dir / "group_suggestion_quality.png")


def plot_group_survey(participants: List[ParticipantData], out_dir: Path) -> Path:
    by_comp: Dict[str, list] = {c: [] for c in COMPLEXITY_ORDER}
    for p in participants:
        for t in p.trials:
            if t.config.get("is_tutorial") or not t.survey: continue
            comp = t.config.get("complexity","")
            if comp not in by_comp: continue
            m = compute_trial_metrics(t)
            by_comp[comp].append({"pid": _pid(p), "pidx": participants.index(p), **m})

    comps = [c for c in COMPLEXITY_ORDER if by_comp[c]]
    x     = np.arange(len(comps))
    measures = [
        ("tlx_mean",        "NASA-TLX (0–20)",   "mean TLX"),
        ("trust_composite", "Trust composite (1–7)", "trust"),
        ("tam_mean",        "TAM (1–7)",           "TAM"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle("Group Survey by Complexity", fontsize=13, fontweight="bold")

    for ax, (key, ylabel, title) in zip(axes, measures):
        width = 0.8 / max(len(participants), 1)
        for pidx, p in enumerate(participants):
            p_xs, p_vs = [], []
            for ci, comp in enumerate(comps):
                dp = next((d for d in by_comp[comp] if d["pid"] == _pid(p)), None)
                if dp and dp.get(key) is not None:
                    p_xs.append(ci + (pidx - (len(participants)-1)/2) * width)
                    p_vs.append(dp[key])
            if p_vs:
                ax.bar(p_xs, p_vs, width=width*0.85,
                       color=PARTICIPANT_COLORS[pidx % len(PARTICIPANT_COLORS)],
                       alpha=0.8, label=_pid(p), edgecolor="white")
        ax.set_xticks(x)
        ax.set_xticklabels([c.capitalize() for c in comps])
        ax.set_ylabel(ylabel); ax.set_title(title)
        ax.legend(fontsize=8)

    _ensure(out_dir)
    return _save(fig, out_dir / "group_survey.png")


def plot_group_behaviour(participants: List[ParticipantData], out_dir: Path) -> Path:
    keys = [
        ("n_m1",              "M1 manual\nswitches"),
        ("n_m2",              "M2 suggest\napplied"),
        ("n_flex_auto",       "Agent\nauto-fixes"),
        ("suggestion_accept_rate","Suggest\naccept rate"),
        ("bad_suggestion_rate",   "Bad-suggest\nrate"),
        ("mean_reaction_time",    "Mean reaction\ntime (s)"),
        ("clash_pct",             "Clash %"),
    ]

    rows, row_labels = [], []
    for p in participants:
        for t in p.trials:
            if t.config.get("is_tutorial"): continue
            m    = compute_trial_metrics(t)
            comp = t.config.get("complexity", t.label)
            rows.append([m.get(k) for k, _ in keys])
            row_labels.append(f"{_pid(p)}\n{comp.capitalize()}")

    if not rows: return None

    arr  = np.array([[v if v is not None else np.nan for v in r] for r in rows], dtype=float)
    cmin = np.nanmin(arr, axis=0)
    cmax = np.nanmax(arr, axis=0)
    norm = np.where(cmax != cmin, (arr - cmin)/(cmax - cmin), 0.5)

    fig, ax = plt.subplots(figsize=(len(keys)*1.9, len(rows)*0.75 + 1.5))
    fig.suptitle("Behavioural Metrics Overview", fontsize=13, fontweight="bold")

    im = ax.imshow(norm, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=1)
    for ri in range(len(rows)):
        for ci, (k, _) in enumerate(keys):
            v = arr[ri, ci]
            if k in ("suggestion_accept_rate","bad_suggestion_rate") and not np.isnan(v):
                txt = f"{v:.0%}"
            else:
                txt = f"{v:.1f}" if not np.isnan(v) else "-"
            n_val = norm[ri, ci]
            ax.text(ci, ri, txt, ha="center", va="center", fontsize=8,
                    color="white" if (n_val < 0.25 or n_val > 0.75) else "black")

    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([lbl for _, lbl in keys], fontsize=8)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02).set_label(
        "Normalised (green=low, red=high)", fontsize=7)

    _ensure(out_dir)
    return _save(fig, out_dir / "group_behaviour_heatmap.png")


def plot_version_timeline(participants: List[ParticipantData], out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, max(2, len(participants)*0.9 + 1)))
    fig.suptitle("Participant Sessions vs. Git Commits", fontsize=12, fontweight="bold")

    for i, p in enumerate(participants):
        ax.scatter(0, i,
                   color=PARTICIPANT_COLORS[i % len(PARTICIPANT_COLORS)],
                   marker=PARTICIPANT_MARKERS[i % len(PARTICIPANT_MARKERS)],
                   s=120, zorder=5)
        commit = (f"git {p.git_short}  {p.git_date[:10] if p.git_date else ''}\n"
                  f"{(p.git_message or 'unknown')[:65]}")
        ax.text(0.05, i, commit, va="center", fontsize=7,
                color=PARTICIPANT_COLORS[i % len(PARTICIPANT_COLORS)])
        ax.text(-0.05, i, f"{_pid(p)} = {p.participant_id}\n{p.start_time[:8]}",
                va="center", ha="right", fontsize=8, fontweight="bold")

    ax.set_xlim(-0.5, 1.5)
    ax.set_ylim(-0.5, len(participants) - 0.5)
    ax.axis("off")

    _ensure(out_dir)
    return _save(fig, out_dir / "version_timeline.png")
