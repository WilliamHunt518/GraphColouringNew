"""
Main analysis entry point.

Usage:
    python -m analysis.run_analysis               # analyses everything
    python -m analysis.run_analysis --pid Andrei  # single participant

Outputs go to:
    results/analysis/<YYYYMMDD_HHMMSS>/
        individual/<participant_id>/  — per-participant plots + CSV
        group/                        — cross-participant plots + CSV
        summary_report.txt            — human-readable text summary
"""

from __future__ import annotations
import argparse
import csv
import io
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── add project root to path so 'analysis' package resolves ──────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.data_loader import load_all_participants, save_participant_map, ParticipantData, TrialData
from analysis.metrics     import (compute_trial_metrics, extract_summary_survey,
                                   COMPLEXITY_ORDER, _MODES, _MODE_ITEMS, _SUMM_QUANT)
from analysis.plots       import (
    plot_performance_bars,
    plot_clash_area,
    plot_intervention_breakdown,
    plot_suggestion_quality,
    plot_survey_per_participant,
    plot_summary_survey,
    plot_group_performance,
    plot_group_clash_area,
    plot_group_interventions,
    plot_group_suggestion_quality,
    plot_group_survey,
    plot_group_behaviour,
    plot_version_timeline,
)

RESULTS_ROOT = Path(__file__).parent.parent / "results"


# ══════════════════════════════════════════════════════════════════════════════
#  Text report helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fmt(v, fmt=".1f", fallback="n/a"):
    if v is None:
        return fallback
    return format(v, fmt)


def _participant_text_block(p: ParticipantData) -> str:
    buf = io.StringIO()
    w   = lambda s="": print(s, file=buf)

    w(f"{'='*70}")
    w(f"  {p.pid_label} = {p.participant_id}   session {p.start_time}")
    w(f"  git: {p.git_short or 'unknown'}  {p.git_date or ''}  \"{p.git_message or ''}\"")
    w(f"{'-'*70}")

    d = p.demographics
    w(f"  Demographics: age={d.get('age')}  gender={d.get('gender')}  "
      f"edu={d.get('education')}")
    w(f"                tech_comfort={d.get('tech_comfort')}/7  "
      f"ai_exp={d.get('ai_experience')}/7  drone_exp={d.get('drone_experience')}/7")
    w()

    game_trials = [t for t in p.trials if not t.config.get("is_tutorial")]
    for t in game_trials:
        m = compute_trial_metrics(t)
        w(f"  [{t.index}] {t.label}  ({m['complexity']}, ε={m['epsilon']}, "
          f"{m['duration']}s)")
        w(f"      Performance : clash={_fmt(m['clash_seconds'])}s  "
          f"({_fmt(m['clash_pct'])}%)  n_clashes={m.get('n_clashes',0)}")
        w(f"      Reaction    : mean={_fmt(m.get('mean_reaction_time'))}s  "
          f"median={_fmt(m.get('med_reaction_time'))}s")
        w(f"      Interventions (in-game): M1={m['n_m1']}  M2={m['n_m2']}  "
          f"M3={m['n_m3']}  agent_auto={m['n_flex_auto']}")
        if m.get("n_suggestions_shown", 0) > 0:
            w(f"      Suggestions : shown={m.get('n_suggestions_shown',0)}  "
              f"applied={m.get('n_suggestions_applied',0)}  "
              f"cancelled={m.get('n_suggestions_cancelled',0)}  "
              f"accept_rate={_fmt(m.get('suggestion_accept_rate'), '.0%')}")
            w(f"                    clean_ok={m.get('n_clean_accepted',0)}  "
              f"clean_bad={m.get('n_clean_bad_applied',0)}  "
              f"unavoidable={m.get('n_unavoidable_accepted',0)}  "
              f"bad_rate={_fmt(m.get('bad_suggestion_rate'), '.0%')}")
        if t.survey:
            w(f"      TLX (mean)  : {_fmt(m.get('tlx_mean'))}/20   "
              f"Trust composite: {_fmt(m.get('trust_composite'))}/7   "
              f"TAM mean: {_fmt(m.get('tam_mean'))}/7")
            mode_parts = [f"{md}={_fmt(m.get(f'mode_{md}_mean'), '.1f')}"
                          for md in _MODES if m.get(f"mode_{md}_mean") is not None]
            if mode_parts:
                w(f"      Mode ratings: " + "  ".join(mode_parts) + " /7")
        w()

    # Post-session summary survey
    ss_rows = extract_summary_survey(p)
    if ss_rows:
        w("  Post-session summary survey:")
        if ss_rows and "mode" in ss_rows[0]:
            for row in ss_rows:
                quals = [f"{q}={row.get(q,'?')}" for q in _SUMM_QUANT]
                w(f"    {row.get('mode','?'):8s}  " + "  ".join(quals))
                qual = row.get("qualitative", "").strip()
                if qual:
                    w(f"             \"{qual[:100]}\"")
        else:
            for row in ss_rows:
                w(f"    {row.get('label','?'):25s}  "
                  f"difficulty={row.get('difficulty','?')}  "
                  f"tool_usefulness={row.get('tool_usefulness','?')}  "
                  f"manual_freq={row.get('manual_frequency','?')}  "
                  f"confidence={row.get('confidence','?')}")
    w()
    return buf.getvalue()


def _group_text_block(participants: List[ParticipantData]) -> str:
    buf = io.StringIO()
    w   = lambda s="": print(s, file=buf)

    w(f"{'='*70}")
    w(f"  GROUP COMPARISON  (n={len(participants)})")
    w(f"{'-'*70}")

    by_comp: Dict[str, list] = {c: [] for c in COMPLEXITY_ORDER}
    for p in participants:
        for t in p.trials:
            if t.config.get("is_tutorial"): continue
            comp = t.config.get("complexity","")
            if comp in by_comp:
                by_comp[comp].append((p.participant_id, compute_trial_metrics(t)))

    for comp in COMPLEXITY_ORDER:
        entries = by_comp[comp]
        if not entries:
            continue
        w(f"  {comp.upper()}")
        for pid, m in entries:
            w(f"    {pid:20s}  clash={_fmt(m['clash_pct'])}%  "
              f"M1={m['n_m1']}  M2={m['n_m2']}  agent={m['n_flex_auto']}  "
              f"TLX={_fmt(m.get('tlx_mean'))}/20  TAM={_fmt(m.get('tam_mean'))}/7")
        w()
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  CSV export
# ══════════════════════════════════════════════════════════════════════════════

def _write_trial_csv(participants: List[ParticipantData], out_path: Path) -> None:
    """One row per (participant × trial)."""
    metric_keys = [
        "clash_seconds","clash_pct","elapsed","n_clashes",
        "avg_clash_duration","max_clash_duration",
        "mean_reaction_time","med_reaction_time","n_reactions",
        "n_switches_setup","n_switches_ingame",
        "n_m1","n_m2","n_m3","n_flex_auto","n_human_actions","n_agent_actions","n_setup_actions",
        "setup_used_auto","setup_used_suggest","ingame_switched_watch",
        "n_watch_auto_set","n_watch_suggest_set",
        "n_suggestions_shown","n_suggestions_applied","n_suggestions_cancelled",
        "n_clean_accepted","n_clean_modified","n_clean_bad_applied",
        "n_unavoidable_accepted","n_unavoidable_modified","n_cancelled",
        "suggestion_accept_rate","bad_suggestion_rate","total_channel_overrides",
        "tlx_mean","tlx_mental","tlx_physical","tlx_temporal",
        "tlx_performance","tlx_effort","tlx_frustration",
        "trust_composite","trust_suspicious","trust_wary","trust_confident",
        "trust_reliable","trust_overall","trust_accepted",
        "tam_mean","tam_improved","tam_easy","tam_useful","tam_would_use",
        # Per-mode trial ratings (suited rating for manual/suggest/auto)
        *[f"mode_{mode}_suited"  for mode in _MODES],
        *[f"mode_{mode}_comment" for mode in _MODES],
        *[f"mode_{mode}_mean"    for mode in _MODES],
    ]
    demo_keys = ["age","gender","education","tech_comfort","ai_experience","drone_experience"]

    header = (["pid_label","participant_id","session_start","git_short","git_message",
               "trial_index","trial_label","complexity","duration","epsilon","is_tutorial"]
              + demo_keys + metric_keys)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for p in participants:
            demo = {k: p.demographics.get(k, "") for k in demo_keys}
            for t in p.trials:
                m = compute_trial_metrics(t)
                row = {
                    "pid_label":      p.pid_label,
                    "participant_id": p.participant_id,
                    "session_start":  p.start_time,
                    "git_short":      p.git_short or "",
                    "git_message":    p.git_message or "",
                    "trial_index":    t.index,
                    "trial_label":    t.label,
                    "complexity":     t.config.get("complexity",""),
                    "duration":       t.config.get("duration",""),
                    "epsilon":        t.config.get("epsilon",""),
                    "is_tutorial":    t.config.get("is_tutorial", False),
                }
                row.update(demo)
                row.update({k: m.get(k, "") for k in metric_keys})
                writer.writerow(row)


def _write_summary_survey_csv(participants: List[ParticipantData], out_path: Path) -> None:
    """One row per (participant × mode or scenario) for post-session ratings."""
    is_new = any(
        any(k.startswith("mode_") for k in p.summary_survey)
        for p in participants if p.summary_survey
    )
    if is_new:
        header = (["participant_id", "session_start", "mode"]
                  + list(_SUMM_QUANT) + ["qualitative"])
    else:
        header = ["participant_id","session_start","label",
                  "difficulty","tool_usefulness","manual_frequency","confidence"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for p in participants:
            rows = extract_summary_survey(p)
            for row in rows:
                row["participant_id"] = p.participant_id
                row["session_start"]  = p.start_time
                writer.writerow(row)


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def run(pid_filter: Optional[str] = None) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root  = RESULTS_ROOT / "analysis" / timestamp
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Drone study analysis — {timestamp}")
    print(f"  Output: {out_root}")
    print(f"{'='*60}\n")

    print("Loading participants …")
    all_participants = load_all_participants()
    if not all_participants:
        print("No participants found. Check results/participants/")
        return

    if pid_filter:
        filtered = [p for p in all_participants
                    if pid_filter.lower() in p.participant_id.lower()]
        if not filtered:
            print(f"No participants matching '{pid_filter}'. "
                  f"Available: {[p.participant_id for p in all_participants]}")
            return
        analysis_set = filtered
    else:
        analysis_set = all_participants

    print(f"\n  Analysing {len(analysis_set)} participant(s) "
          f"({[p.participant_id for p in analysis_set]})\n")

    report_buf = io.StringIO()
    rw = lambda s="": print(s, file=report_buf)

    rw("DRONE STUDY — PILOT ANALYSIS")
    rw(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    rw(f"Participants: {len(analysis_set)}")
    rw()

    # ── Participant map ───────────────────────────────────────────────────────
    map_path = out_root / "participant_map.json"
    save_participant_map(analysis_set, map_path)
    print(f"  Wrote participant_map.json")

    # ── Per-participant ───────────────────────────────────────────────────────
    for p in analysis_set:
        ind_dir = out_root / "individual" / p.pid_label
        ind_dir.mkdir(parents=True, exist_ok=True)

        print(f"  [{p.pid_label} = {p.participant_id}]  git={p.git_short}  trials={len(p.trials)}")

        _run_plot("performance_bars",     plot_performance_bars,     p, ind_dir)
        _run_plot("clash_area",           plot_clash_area,           p, ind_dir)
        _run_plot("intervention_detail",  plot_intervention_breakdown, p, ind_dir)
        _run_plot("suggestion_quality",   plot_suggestion_quality,   p, ind_dir)
        _run_plot("survey_responses",     plot_survey_per_participant, p, ind_dir)
        _run_plot("summary_survey",       plot_summary_survey,       p, ind_dir)

        rw(_participant_text_block(p))

    # ── Group ─────────────────────────────────────────────────────────────────
    grp_dir = out_root / "group"
    grp_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Group plots ...")
    _run_plot("version_timeline",        plot_version_timeline,        analysis_set, grp_dir)
    if len(analysis_set) >= 2:
        _run_plot("group_performance",        plot_group_performance,       analysis_set, grp_dir)
        _run_plot("group_clash_area",         plot_group_clash_area,        analysis_set, grp_dir)
        _run_plot("group_interventions",      plot_group_interventions,     analysis_set, grp_dir)
        _run_plot("group_suggestion_quality", plot_group_suggestion_quality, analysis_set, grp_dir)
        _run_plot("group_survey",             plot_group_survey,            analysis_set, grp_dir)
        _run_plot("group_behaviour",          plot_group_behaviour,         analysis_set, grp_dir)
        rw(_group_text_block(analysis_set))

    # ── CSVs ──────────────────────────────────────────────────────────────────
    csv_path = out_root / "trial_metrics.csv"
    _write_trial_csv(analysis_set, csv_path)
    print(f"  Wrote {csv_path.name}")

    ss_csv = out_root / "summary_survey.csv"
    _write_summary_survey_csv(analysis_set, ss_csv)
    print(f"  Wrote {ss_csv.name}")

    # ── ANOVA ─────────────────────────────────────────────────────────────────
    try:
        from analysis.stats import run_anova
        anova_dir = out_root / "anova"
        anova_dir.mkdir(exist_ok=True)
        run_anova(csv_path, anova_dir, ss_csv)
        print(f"  Wrote ANOVA results to {anova_dir.name}/")
    except ImportError as exc:
        print(f"  [!] ANOVA skipped (missing library): {exc}")
    except Exception as exc:
        print(f"  [!] ANOVA failed: {exc}")

    # ── Text report ───────────────────────────────────────────────────────────
    report_text = report_buf.getvalue()
    report_path = out_root / "summary_report.txt"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"  Wrote {report_path.name}")
    print(f"\n{'-'*60}")
    # Print safely on Windows terminals that don't support all Unicode
    try:
        print(report_text)
    except UnicodeEncodeError:
        print(report_text.encode("ascii", errors="replace").decode("ascii"))
    print(f"{'-'*60}")
    print(f"\nDone. All output in:\n  {out_root}\n")


def _run_plot(name: str, fn, *args) -> None:
    try:
        path = fn(*args)
        if path:
            print(f"    [ok] {name}: {path.name}")
    except Exception as exc:
        print(f"    [!]  {name}: {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drone study analysis")
    parser.add_argument("--pid", default=None,
                        help="Filter to a single participant ID substring")
    args = parser.parse_args()
    run(pid_filter=args.pid)
