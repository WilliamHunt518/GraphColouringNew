"""
Repeated-measures ANOVA for the drone study.

Within-subjects factor: complexity (easy / medium / hard)
Subjects:               participant_id
DVs:                    see _COMPLEXITY_DVS below

Also runs a per-mode ANOVA on summary-survey ratings if summary_survey.csv is present.

Usage (from project root):
    python -m analysis.stats
    python -m analysis.stats --csv results/analysis/.../trial_metrics.csv
    python -m analysis.stats --csv trial_metrics.csv --summary summary_survey.csv

Outputs (written to --out-dir, default = directory of --csv):
    anova_complexity.csv   — rm ANOVA results, one row per DV
    posthoc_complexity.csv — Bonferroni pairwise comparisons for sig. DVs
    anova_mode.csv         — rm ANOVA: DV ~ mode (from summary_survey.csv)
    posthoc_mode.csv       — Bonferroni pairwise for sig. mode DVs
    anova_report.txt       — human-readable summary

Requires pingouin (preferred) or statsmodels.  Install with:
    pip install pingouin
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── optional heavy dependencies ───────────────────────────────────────────────

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

try:
    import pingouin as pg
    _HAS_PINGOUIN = True
except ImportError:
    _HAS_PINGOUIN = False

try:
    from statsmodels.stats.anova import AnovaRM as _AnovaRM
    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False


# ── DVs ───────────────────────────────────────────────────────────────────────

_COMPLEXITY_DVS = [
    "clash_pct",
    "mean_reaction_time",
    "n_clashes",
    "tlx_mean",
    "trust_composite",
    "tam_mean",
    "n_m1",
    "n_m2",
    "n_flex_auto",
    "n_suggestions_shown",
    "suggestion_accept_rate",
    "bad_suggestion_rate",
    "mode_manual_mean",
    "mode_suggest_mean",
    "mode_auto_mean",
]

_MODE_DVS = ["overall", "drone_count_helpfulness", "overload_preference"]

_COMPLEXITY_ORDER = ["easy", "medium", "hard"]


# ── Main entry ────────────────────────────────────────────────────────────────

def run_anova(
    trial_csv: Path,
    out_dir: Path,
    summary_csv: Optional[Path] = None,
) -> None:
    """Run all ANOVA analyses and write results to out_dir."""
    if not _HAS_PANDAS:
        raise ImportError("pandas is required: pip install pandas")
    if not (_HAS_PINGOUIN or _HAS_STATSMODELS):
        raise ImportError("pingouin or statsmodels is required: pip install pingouin")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    buf = io.StringIO()
    log = lambda s="": print(s, file=buf)

    log("DRONE STUDY — REPEATED-MEASURES ANOVA")
    log(f"Trial CSV : {trial_csv}")
    log(f"Engine    : {'pingouin' if _HAS_PINGOUIN else 'statsmodels'}")
    log()

    df = pd.read_csv(trial_csv)
    df = df[df["is_tutorial"].astype(str).str.lower() != "true"]
    df = df[df["complexity"].isin(_COMPLEXITY_ORDER)]

    for col in _COMPLEXITY_DVS:
        if col not in df.columns:
            df[col] = float("nan")
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Aggregate within participant × complexity (mean across repeated runs)
    agg = df.groupby(["participant_id", "complexity"])[_COMPLEXITY_DVS].mean().reset_index()

    n_participants = agg["participant_id"].nunique()
    n_cells = agg.groupby(["participant_id", "complexity"]).size()
    log(f"Participants: {n_participants}")
    log(f"Complexity levels: {sorted(agg['complexity'].unique())}")
    log()

    # ── Complexity ANOVA ─────────────────────────────────────────────────────
    log("=" * 65)
    log("  ANOVA: DV ~ complexity (within-subjects)")
    log("=" * 65)

    anova_rows: List[Dict] = []
    posthoc_rows: List[Dict] = []

    for dv in _COMPLEXITY_DVS:
        sub = agg[["participant_id", "complexity", dv]].dropna()
        n_complete = _n_complete_subjects(sub, dv, "complexity")
        if n_complete < 3:
            log(f"  {dv:<35s}  skipped (n_complete={n_complete} < 3)")
            continue

        result = _rm_anova(sub, dv, "complexity", "participant_id")
        result["n_subjects"] = n_complete
        anova_rows.append(result)

        sig = result.get("p_unc") is not None and result["p_unc"] < 0.05
        star = " *" if sig else ""
        df1 = result.get("ddof1", "?")
        df2 = result.get("ddof2", "?")
        log(f"  {dv:<35s}  F({df1},{df2})={_ff(result.get('F'))}  "
            f"p={_fp(result.get('p_unc'))}  eta2_p={_ff(result.get('eta2_p'))}{star}")

        if sig:
            ph = _posthoc(sub, dv, "complexity", "participant_id")
            for row in ph:
                row["dv"] = dv
            posthoc_rows.extend(ph)

    log()
    _write_csv(out_dir / "anova_complexity.csv", anova_rows,
               ["dv","n_subjects","F","ddof1","ddof2","p_unc","p_gc","eta2_p","error"])
    _write_csv(out_dir / "posthoc_complexity.csv", posthoc_rows,
               ["dv","A","B","t","dof","p_unc","p_bonf","hedges_g","error"])

    # ── Per-mode ANOVA (summary survey) ──────────────────────────────────────
    if summary_csv and Path(summary_csv).exists():
        ss = pd.read_csv(summary_csv)
        if "mode" in ss.columns:
            log("=" * 65)
            log("  ANOVA: DV ~ mode  (summary survey, within-subjects)")
            log("=" * 65)

            for col in _MODE_DVS:
                if col not in ss.columns:
                    ss[col] = float("nan")
                else:
                    ss[col] = pd.to_numeric(ss[col], errors="coerce")

            mode_anova_rows: List[Dict] = []
            mode_posthoc_rows: List[Dict] = []
            for dv in _MODE_DVS:
                sub = ss[["participant_id", "mode", dv]].dropna()
                n_complete = _n_complete_subjects(sub, dv, "mode")
                if n_complete < 3:
                    log(f"  {dv:<35s}  skipped (n_complete={n_complete} < 3)")
                    continue
                result = _rm_anova(sub, dv, "mode", "participant_id")
                result["n_subjects"] = n_complete
                mode_anova_rows.append(result)
                sig = result.get("p_unc") is not None and result["p_unc"] < 0.05
                star = " *" if sig else ""
                log(f"  {dv:<35s}  F=({_ff(result.get('F'))})  "
                    f"p={_fp(result.get('p_unc'))}{star}")
                if sig:
                    ph = _posthoc(sub, dv, "mode", "participant_id")
                    for row in ph:
                        row["dv"] = dv
                    mode_posthoc_rows.extend(ph)

            log()
            _write_csv(out_dir / "anova_mode.csv", mode_anova_rows,
                       ["dv","n_subjects","F","ddof1","ddof2","p_unc","p_gc","eta2_p","error"])
            _write_csv(out_dir / "posthoc_mode.csv", mode_posthoc_rows,
                       ["dv","A","B","t","dof","p_unc","p_bonf","hedges_g","error"])

    report = buf.getvalue()
    (out_dir / "anova_report.txt").write_text(report, encoding="utf-8")

    try:
        sys.stdout.write(report)
    except UnicodeEncodeError:
        sys.stdout.write(report.encode("ascii", errors="replace").decode("ascii"))


# ── ANOVA backends ────────────────────────────────────────────────────────────

def _n_complete_subjects(sub: "pd.DataFrame", dv: str, within: str) -> int:
    """Count subjects with valid data at every level of within."""
    n_levels = sub[within].nunique()
    counts = sub.groupby("participant_id")[within].count()
    return int((counts == n_levels).sum())


def _rm_anova(sub: "pd.DataFrame", dv: str, within: str, subject: str) -> Dict[str, Any]:
    if _HAS_PINGOUIN:
        return _rm_anova_pingouin(sub, dv, within, subject)
    return _rm_anova_statsmodels(sub, dv, within, subject)


def _rm_anova_pingouin(sub, dv, within, subject) -> Dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res = pg.rm_anova(data=sub, dv=dv, within=within, subject=subject,
                              correction="auto", detailed=False)
            r = res.iloc[0]
            return {
                "dv":      dv,
                "F":       _round(r.get("F")),
                "ddof1":   _round(r.get("ddof1"), 0),
                "ddof2":   _round(r.get("ddof2"), 2),
                "p_unc":   _round(r.get("p-unc"), 4),
                "p_gc":    _round(r.get("p-GG-corr", r.get("p-unc")), 4),
                "eta2_p":  _round(r.get("np2", r.get("eta2-ges")), 4),
                "error":   "",
            }
        except Exception as exc:
            return {"dv": dv, "error": str(exc)}


def _rm_anova_statsmodels(sub, dv, within, subject) -> Dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res = _AnovaRM(data=sub, depvar=dv, subject=subject, within=[within]).fit()
            table = res.anova_table
            r = table.iloc[0]
            return {
                "dv":      dv,
                "F":       _round(float(r["F Value"])),
                "ddof1":   _round(float(r["Num DF"]), 0),
                "ddof2":   _round(float(r["Den DF"]), 2),
                "p_unc":   _round(float(r["Pr > F"]), 4),
                "p_gc":    _round(float(r["Pr > F"]), 4),
                "eta2_p":  None,
                "error":   "",
            }
        except Exception as exc:
            return {"dv": dv, "error": str(exc)}


def _posthoc(sub: "pd.DataFrame", dv: str, within: str, subject: str) -> List[Dict]:
    if _HAS_PINGOUIN:
        return _posthoc_pingouin(sub, dv, within, subject)
    return _posthoc_statsmodels(sub, dv, within, subject)


def _posthoc_pingouin(sub, dv, within, subject) -> List[Dict]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            ph = pg.pairwise_tests(data=sub, dv=dv, within=within, subject=subject,
                                   padjust="bonf")
            rows = []
            for _, r in ph.iterrows():
                rows.append({
                    "A":        r.get("A"),
                    "B":        r.get("B"),
                    "t":        _round(r.get("T")),
                    "dof":      _round(r.get("dof"), 2),
                    "p_unc":    _round(r.get("p-unc"), 4),
                    "p_bonf":   _round(r.get("p-corr"), 4),
                    "hedges_g": _round(r.get("hedges")),
                    "error":    "",
                })
            return rows
        except Exception as exc:
            return [{"error": str(exc)}]


def _posthoc_statsmodels(sub, dv, within, subject) -> List[Dict]:
    # statsmodels AnovaRM doesn't ship post-hoc; use paired t-tests with Bonferroni
    from itertools import combinations
    import math

    levels = sorted(sub[within].unique())
    pairs = list(combinations(levels, 2))
    rows = []
    for a, b in pairs:
        va = sub[sub[within] == a].set_index(subject)[dv]
        vb = sub[sub[within] == b].set_index(subject)[dv]
        both = va.index.intersection(vb.index)
        if len(both) < 2:
            continue
        d = va.loc[both] - vb.loc[both]
        n = len(d)
        mean_d = d.mean()
        std_d = d.std(ddof=1)
        if std_d == 0:
            continue
        t_stat = mean_d / (std_d / math.sqrt(n))
        import scipy.stats as st
        p_unc = float(2 * st.t.sf(abs(t_stat), df=n - 1))
        p_bonf = min(p_unc * len(pairs), 1.0)
        rows.append({
            "A": a, "B": b,
            "t": _round(t_stat),
            "dof": n - 1,
            "p_unc": _round(p_unc, 4),
            "p_bonf": _round(p_bonf, 4),
            "hedges_g": "",
            "error": "",
        })
    return rows


# ── Helpers ───────────────────────────────────────────────────────────────────

def _round(v, ndigits: int = 4):
    if v is None:
        return None
    try:
        return round(float(v), ndigits)
    except (TypeError, ValueError):
        return v


def _ff(v) -> str:
    return f"{v:.3f}" if v is not None else "n/a"


def _fp(v) -> str:
    if v is None:
        return "n/a"
    if v < 0.001:
        return "<.001"
    return f"{v:.3f}"


def _write_csv(path: Path, rows: List[Dict], fieldnames: List[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


# ── CLI ───────────────────────────────────────────────────────────────────────

def _latest_csv(results_root: Path, name: str) -> Optional[Path]:
    """Find the most recent analysis output containing a given CSV."""
    analysis_dir = results_root / "analysis"
    if not analysis_dir.exists():
        return None
    candidates = sorted(
        (p for p in analysis_dir.rglob(name) if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repeated-measures ANOVA for the drone study")
    parser.add_argument("--csv",     default=None, help="Path to trial_metrics.csv")
    parser.add_argument("--summary", default=None, help="Path to summary_survey.csv")
    parser.add_argument("--out-dir", default=None, help="Output directory (default: next to CSV)")
    args = parser.parse_args()

    root = Path(__file__).parent.parent / "results"

    if args.csv:
        trial_csv = Path(args.csv)
    else:
        trial_csv = _latest_csv(root, "trial_metrics.csv")
        if not trial_csv:
            sys.exit("No trial_metrics.csv found. Run run_analysis.py first or pass --csv.")
        print(f"Using: {trial_csv}")

    if args.summary:
        summary_csv = Path(args.summary)
    else:
        summary_csv = trial_csv.parent / "summary_survey.csv"

    out_dir = Path(args.out_dir) if args.out_dir else trial_csv.parent / "anova"

    run_anova(trial_csv, out_dir, summary_csv)
    print(f"\nANOVA outputs written to: {out_dir}")
