"""
Compute behavioural metrics from a TrialData's event log.

Key concepts
────────────
elapsed == 0.0 : pre-game (PAUSED / SETUP state before the timer starts)
elapsed  > 0.0 : in-game actions (timer running)

Modes logged in switch_requested.mode:
  M1               — manual popup click
  M2               — suggestion panel "Apply"
  M3               — Watch:Auto initial batch assignment (button press)
  flex_watch_setup — auto-assign fired when Watch:Auto is set mid-game (elapsed=0 usually)
  flex_auto        — automatic watch-agent fix during live flight
  flex_auto_mixed  — watch fix across multiple components

Suggestion quality categories
──────────────────────────────
  clean_accepted    infeasible=False, n_overrides=0, no clash follows quickly
  clean_modified    infeasible=False, user changed at least one channel before applying
  clean_bad_applied infeasible=False, but clash involving same drones starts within
                    switch_duration+2s of application (epsilon noise made it bad)
  unavoidable_accepted  infeasible=True, applied as-is
  unavoidable_modified  infeasible=True, user changed channels before applying
  cancelled         suggestion dismissed
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from .data_loader import TrialData

HUMAN_MODES  = {"M1", "M2"}
AGENT_MODES  = {"flex_auto", "flex_auto_mixed"}
SETUP_MODES  = {"M3", "flex_watch_setup"}
COMPLEXITY_ORDER = ["easy", "medium", "hard"]

_MODES      = ["manual", "suggest", "auto"]
_MODE_ITEMS = ["helpful", "trusted", "focus", "alongside"]
_SUMM_QUANT = ["overall", "drone_count_helpfulness", "overload_preference"]

# Window after suggestion_applied in which a clash_start involving the same
# drones is treated as evidence the proposal was bad (epsilon noise hit)
BAD_SUGGESTION_WINDOW = 5.0   # seconds (covers 3s switch + buffer)


# ── Main per-trial metrics ────────────────────────────────────────────────────

def compute_trial_metrics(trial: TrialData) -> Dict[str, Any]:
    events  = trial.events
    summary = trial.summary

    m: Dict[str, Any] = {
        "label":      trial.label,
        "complexity": trial.config.get("complexity", "tutorial"),
        "duration":   trial.config.get("duration", 0),
        "epsilon":    trial.config.get("epsilon", 0.0),
        "is_tutorial": trial.config.get("is_tutorial", False),
        "clash_seconds": summary.get("clash_seconds", 0.0),
        "clash_pct":     summary.get("clash_pct", 0.0),
        "elapsed":       summary.get("elapsed", 0.0),
        "completed":     summary.get("completed", False),
    }

    if trial.config.get("is_tutorial"):
        return m

    # ── Clash episodes ────────────────────────────────────────────────────────
    clash_starts    = [e for e in events if e["event"] == "clash_start"]
    clash_ends      = [e for e in events if e["event"] == "clash_end"]
    n_clashes       = len(clash_starts)
    clash_durations = _compute_clash_durations(clash_starts, clash_ends)

    m["n_clashes"]          = n_clashes
    m["avg_clash_duration"] = _safe_mean(clash_durations)
    m["max_clash_duration"] = max(clash_durations, default=0.0)

    # ── Reaction times ────────────────────────────────────────────────────────
    reaction_times = _compute_reaction_times(events)
    m["n_reactions"]        = len(reaction_times)
    m["mean_reaction_time"] = _safe_mean(reaction_times)
    m["med_reaction_time"]  = _safe_median(reaction_times)

    # ── Switch counts split by phase ─────────────────────────────────────────
    switches_setup   = [e for e in events if e["event"] == "switch_requested" and e.get("elapsed", 0) == 0.0]
    switches_ingame  = [e for e in events if e["event"] == "switch_requested" and e.get("elapsed", 0) > 0.0]

    def _mode_counts(switch_list):
        mc: Dict[str, int] = {}
        for s in switch_list:
            md = s.get("mode", "unknown")
            mc[md] = mc.get(md, 0) + 1
        return mc

    mc_setup  = _mode_counts(switches_setup)
    mc_ingame = _mode_counts(switches_ingame)

    m["n_switches_setup"]   = len(switches_setup)
    m["n_switches_ingame"]  = len(switches_ingame)

    for pfx, mc in [("setup_", mc_setup), ("ig_", mc_ingame)]:
        m[pfx+"m1"]               = mc.get("M1", 0)
        m[pfx+"m2"]               = mc.get("M2", 0)
        m[pfx+"m3"]               = mc.get("M3", 0)
        m[pfx+"flex_auto"]        = mc.get("flex_auto", 0) + mc.get("flex_auto_mixed", 0)
        m[pfx+"flex_watch_setup"] = mc.get("flex_watch_setup", 0)

    # Convenience aliases (in-game)
    m["n_m1"]         = m["ig_m1"]
    m["n_m2"]         = m["ig_m2"]
    m["n_m3"]         = m["ig_m3"]
    m["n_flex_auto"]  = m["ig_flex_auto"]
    m["n_human_actions"] = m["n_m1"] + m["n_m2"]
    m["n_agent_actions"] = m["n_flex_auto"]
    m["n_setup_actions"] = m["setup_m3"] + m["setup_flex_watch_setup"] + m["ig_flex_watch_setup"]

    # ── Setup strategy label ──────────────────────────────────────────────────
    # What did the participant do in the pre-game phase?
    watch_setup = [e for e in events if e["event"] == "watch_mode_set" and e.get("elapsed", 0) == 0]
    watch_ingame = [e for e in events if e["event"] == "watch_mode_set" and e.get("elapsed", 0) > 0]
    m["setup_used_auto"]    = any(e.get("mode") == "auto"    for e in watch_setup)
    m["setup_used_suggest"] = any(e.get("mode") == "suggest" for e in watch_setup)
    m["ingame_switched_watch"] = len(watch_ingame) > 0
    m["n_watch_auto_set"]    = sum(1 for e in watch_setup + watch_ingame if e.get("mode") == "auto")
    m["n_watch_suggest_set"] = sum(1 for e in watch_setup + watch_ingame if e.get("mode") == "suggest")

    # ── Suggestion quality ────────────────────────────────────────────────────
    sq = classify_suggestion_quality(events, trial.config.get("switch_duration", 3.0))
    m["suggestions"] = sq
    m["n_suggestions_total"]    = len(sq)
    m["n_suggestions_shown"]    = len(sq)

    cats = [s["quality"] for s in sq]
    m["n_clean_accepted"]      = cats.count("clean_accepted")
    m["n_clean_modified"]      = cats.count("clean_modified")
    m["n_clean_bad_applied"]   = cats.count("clean_bad_applied")
    m["n_unavoidable_accepted"]= cats.count("unavoidable_accepted")
    m["n_unavoidable_modified"]= cats.count("unavoidable_modified")
    m["n_cancelled"]           = cats.count("cancelled")

    n_applied = sum(1 for s in sq if s["applied"])
    n_no_override = sum(1 for s in sq if s["applied"] and s.get("n_overrides", 0) == 0)
    m["n_suggestions_applied"]   = n_applied
    m["n_suggestions_cancelled"] = m["n_cancelled"]
    m["suggestion_accept_rate"]  = n_no_override / n_applied if n_applied > 0 else None
    m["total_channel_overrides"] = sum(s.get("n_overrides", 0) for s in sq if s["applied"])

    # Bad-suggestion accept rate (the critical metric)
    n_bad_shown = cats.count("clean_bad_applied") + cats.count("clean_accepted")
    # Among suggestions where infeasible=False (agent claimed success),
    # what fraction turned out bad?
    n_feasible_shown = sum(1 for s in sq if not s["infeasible"])
    n_feasible_bad   = cats.count("clean_bad_applied")
    m["bad_suggestion_rate"] = n_feasible_bad / n_feasible_shown if n_feasible_shown > 0 else None

    # ── Survey ────────────────────────────────────────────────────────────────
    if trial.survey:
        m.update(_extract_survey(trial.survey))

    return m


# ── Suggestion quality ────────────────────────────────────────────────────────

def classify_suggestion_quality(
    events: List[Dict], switch_duration: float = 3.0
) -> List[Dict[str, Any]]:
    """
    Match suggestion_shown → (suggestion_applied | suggestion_cancelled) pairs
    and classify each suggestion's quality.

    Returns a list of dicts, one per suggestion_shown event, with fields:
      elapsed, infeasible, applied, n_overrides, quality, drone_ids
    """
    results = []
    shown_queue: List[Dict] = []

    for e in events:
        ev = e["event"]

        if ev == "suggestion_shown":
            shown_queue.append(e)

        elif ev == "suggestion_applied" and shown_queue:
            shown = shown_queue.pop(0)
            n_ov   = e.get("n_overrides", 0)
            infeas = shown.get("infeasible", False)
            drone_ids = set(int(d) for d in shown.get("drone_ids", []))

            # Tentative quality (will refine for clean below)
            if infeas:
                quality = "unavoidable_modified" if n_ov > 0 else "unavoidable_accepted"
            else:
                quality = "clean_modified" if n_ov > 0 else "clean_accepted"

            results.append({
                "elapsed":    shown["elapsed"],
                "infeasible": infeas,
                "applied":    True,
                "n_overrides":n_ov,
                "quality":    quality,
                "drone_ids":  drone_ids,
                "apply_elapsed": e["elapsed"],
            })

        elif ev == "suggestion_cancelled" and shown_queue:
            shown = shown_queue.pop(0)
            results.append({
                "elapsed":    shown["elapsed"],
                "infeasible": shown.get("infeasible", False),
                "applied":    False,
                "n_overrides":0,
                "quality":    "cancelled",
                "drone_ids":  set(int(d) for d in shown.get("drone_ids", [])),
                "apply_elapsed": e["elapsed"],
            })

    # Second pass: mark "clean_accepted" as "clean_bad_applied" if a clash
    # involving those drones starts shortly after the suggestion was applied
    window = switch_duration + 2.0
    clash_events = [(e["elapsed"], set(d for pair in e.get("pairs", []) for d in pair))
                    for e in events if e["event"] == "clash_start"]

    for rec in results:
        if rec["quality"] not in ("clean_accepted", "clean_modified"):
            continue
        t_apply = rec["apply_elapsed"]
        drones  = rec["drone_ids"]
        for t_clash, clash_drones in clash_events:
            if t_apply <= t_clash <= t_apply + window:
                if clash_drones & drones:   # overlap
                    rec["quality"] = rec["quality"].replace("clean_", "clean_bad_")
                    # clean_accepted → clean_bad_applied, clean_modified → clean_bad_applied
                    rec["quality"] = "clean_bad_applied"
                    break

    return results


# ── Clash time-series reconstruction ─────────────────────────────────────────

def reconstruct_clash_series(
    events: List[Dict], duration: float
) -> Tuple[List[float], List[int]]:
    """
    Returns (times, pair_counts) as a step function.
    pair_counts[i] is the number of simultaneously clashing pairs between
    times[i] and times[i+1].

    clash_start / clash_update carry n_pairs (or len(pairs) as fallback).
    clash_end signals zero active pairs.
    """
    times:  List[float] = [0.0]
    counts: List[int]   = [0]

    for e in events:
        ev = e.get("event")
        t  = e.get("elapsed", 0.0)
        if t < 0:
            continue
        if ev in ("clash_start", "clash_update"):
            times.append(t)
            counts.append(e.get("n_pairs", len(e.get("pairs", []))))
        elif ev == "clash_end":
            times.append(t)
            counts.append(0)

    times.append(duration)
    counts.append(0)
    return times, counts


# ── Strategy timeline ─────────────────────────────────────────────────────────

def get_strategy_timeline(
    events: List[Dict], duration: float, n_buckets: int = 6
) -> Dict[str, Any]:
    """
    Divide the trial into n_buckets equal time windows.
    For each bucket, count switch events by mode.
    Also return the ordered sequence of watch_mode_set events.
    """
    if duration <= 0:
        return {}
    bucket_size = duration / n_buckets
    buckets: List[Dict[str, int]] = [{} for _ in range(n_buckets)]

    for e in events:
        if e["event"] != "switch_requested":
            continue
        t = e.get("elapsed", 0.0)
        if t <= 0:
            continue
        mode = e.get("mode", "unknown")
        bi   = min(int(t / bucket_size), n_buckets - 1)
        buckets[bi][mode] = buckets[bi].get(mode, 0) + 1

    watch_seq = [
        {"elapsed": e["elapsed"], "drones": e.get("drones", []), "mode": e.get("mode")}
        for e in events
        if e["event"] == "watch_mode_set"
    ]

    return {
        "bucket_size": bucket_size,
        "n_buckets":   n_buckets,
        "buckets":     buckets,
        "watch_sequence": watch_seq,
    }


# ── Survey extraction ─────────────────────────────────────────────────────────

def _extract_survey(sv: Dict) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    tlx_keys = ["tlx_mental","tlx_physical","tlx_temporal",
                 "tlx_performance","tlx_effort","tlx_frustration"]
    for k in tlx_keys:
        if k in sv: out[k] = sv[k]
    tlx_vals = [sv[k] for k in tlx_keys if k in sv]
    out["tlx_mean"] = _safe_mean(tlx_vals)

    trust_keys = ["trust_suspicious","trust_wary","trust_confident",
                  "trust_reliable","trust_overall","trust_accepted"]
    for k in trust_keys:
        if k in sv: out[k] = sv[k]
    pos_vals = [sv[k] for k in ["trust_confident","trust_reliable",
                                  "trust_overall","trust_accepted"] if k in sv]
    neg_vals = [sv[k] for k in ["trust_suspicious","trust_wary"] if k in sv]
    if pos_vals or neg_vals:
        out["trust_composite"] = (_safe_mean(pos_vals) - _safe_mean(neg_vals) + 6) / 12 * 7

    tam_keys = ["tam_improved","tam_easy","tam_useful","tam_would_use"]
    for k in tam_keys:
        if k in sv: out[k] = sv[k]
    out["tam_mean"] = _safe_mean([sv[k] for k in tam_keys if k in sv])

    # Per-mode ratings (helpful/trusted/focus/alongside for manual/suggest/auto)
    for mode in _MODES:
        vals = []
        for item in _MODE_ITEMS:
            k = f"mode_{mode}_{item}"
            v = sv.get(k)
            if v is not None and v != 0:
                out[k] = v
                vals.append(v)
        if vals:
            out[f"mode_{mode}_mean"] = _safe_mean(vals)

    return out


def extract_summary_survey(participant) -> List[Dict[str, Any]]:
    ss = participant.summary_survey
    if not ss:
        return []

    # New format: per-mode ratings with overall/drone_count_helpfulness/overload_preference
    if any(k.startswith("mode_") for k in ss):
        rows = []
        for mode in _MODES:
            row: Dict[str, Any] = {
                "participant_id": participant.participant_id,
                "pid_label":      participant.pid_label,
                "mode":           mode,
            }
            for q in _SUMM_QUANT:
                k = f"mode_{mode}_{q}"
                if k in ss:
                    row[q] = ss[k]
            qual_k = f"mode_{mode}_qualitative"
            if qual_k in ss:
                row["qualitative"] = ss[qual_k]
            rows.append(row)
        return rows

    # Legacy format: scenario-based ratings
    scenario_map = ss.get("scenario_map", {})
    rows = []
    for num_str, label in scenario_map.items():
        row = {"participant_id": participant.participant_id,
               "pid_label": participant.pid_label,
               "label": label}
        for key in ["difficulty","tool_usefulness","manual_frequency","confidence"]:
            fk = f"scenario_{num_str}_{key}"
            if fk in ss: row[key] = ss[fk]
        rows.append(row)
    return rows


# ── Internal helpers ──────────────────────────────────────────────────────────

def _compute_clash_durations(clash_starts, clash_ends):
    durations = []
    end_idx = 0
    for cs in clash_starts:
        t0 = cs["elapsed"]
        for i in range(end_idx, len(clash_ends)):
            if clash_ends[i]["elapsed"] >= t0:
                durations.append(clash_ends[i]["elapsed"] - t0)
                end_idx = i + 1
                break
    return durations


def _compute_reaction_times(events):
    rts = []
    for i, e in enumerate(events):
        if e["event"] != "clash_start": continue
        t_clash = e["elapsed"]
        for e2 in events[i + 1:]:
            ev2 = e2["event"]
            if ev2 == "switch_requested" and e2.get("elapsed", 0) >= t_clash:
                rts.append(max(e2["elapsed"] - t_clash, 0.0))
                break
            if ev2 in ("clash_end","clash_start","game_end"):
                break
    return rts


def _safe_mean(vals):
    return sum(vals) / len(vals) if vals else None

def _safe_median(vals):
    if not vals: return None
    s = sorted(vals); n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
