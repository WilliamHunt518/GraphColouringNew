#!/usr/bin/env python3
"""
scenario_preview.py — headless scenario analyser.

Simulates a scenario without any display and prints topology dynamics and
clash statistics, helping researchers choose seeds for study trials.

Usage:
    python scenario_preview.py --complexity medium --seed 42
    python scenario_preview.py --complexity hard --seed 137 --duration 150
    python scenario_preview.py -c easy -s 7 -w 15   # 15-second windows
    python scenario_preview.py -c medium --seeds 1 2 3 42 99  # compare seeds
"""
from __future__ import annotations
import argparse
import math
import random
from typing import Dict, List, Optional, Set

from robot_world import RobotWorld, COMPLEXITY_PRESETS, SWITCH_DURATION, CHANNELS

_SIM_DT   = 1.0 / 60.0          # fixed timestep — matches robot_game.py
_CHANNELS = list(CHANNELS)       # ("red", "green", "blue")


# ── Graph helpers ─────────────────────────────────────────────────────────────

def _components(edges: list, n: int) -> List[Set[int]]:
    adj: Dict[int, Set[int]] = {i: set() for i in range(n)}
    for i, j in edges:
        adj[i].add(j); adj[j].add(i)
    visited: Set[int] = set()
    out: List[Set[int]] = []
    for start in range(n):
        if start in visited:
            continue
        comp: Set[int] = set()
        stack = [start]
        while stack:
            v = stack.pop()
            if v in visited:
                continue
            visited.add(v); comp.add(v)
            stack.extend(adj[v] - visited)
        out.append(comp)
    return out


# ── Core simulation ───────────────────────────────────────────────────────────

def run_preview(
    complexity: str,
    seed: int,
    duration: Optional[float] = None,
    window: float = 10.0,
) -> dict:
    """Simulate one scenario headlessly and return a stats dict."""
    n_robots, v_min, v_max = COMPLEXITY_PRESETS[complexity]
    if duration is None:
        duration = {"easy": 90.0, "medium": 120.0, "hard": 150.0}.get(complexity, 120.0)

    world = RobotWorld(
        n_robots=n_robots, seed=seed, duration=duration,
        v_min=v_min, v_max=v_max, switch_duration=SWITCH_DURATION,
    )

    # Assign channels randomly (seeded) — gives a "no-agent" clash baseline.
    ch_rng = random.Random(seed + 9999)
    for r in world.robots:
        r.channel = ch_rng.choice(_CHANNELS)
    world._detect_edges()

    # ── Per-window accumulators ───────────────────────────────────────────────
    windows: List[dict] = []
    prev_edges: frozenset = frozenset(world.edges)

    # "pair_clash_s" counts pair-seconds of clash (can exceed duration if multiple pairs clash).
    # "any_clash_s"  counts seconds where at least one clash was active (capped at window length).
    w_pair_clash_s = 0.0
    w_any_clash_s  = 0.0
    w_edges_sum    = 0
    w_comps_sum    = 0.0
    w_csizes: List[float] = []
    w_new_e        = 0
    w_lost_e       = 0
    w_max_clash    = 0
    w_steps        = 0
    next_w         = window

    total_pair_clash_s = 0.0
    total_any_clash_s  = 0.0
    peak_clash         = 0

    while not world.is_over():
        world.update(_SIM_DT)

        n_clash  = len(world.clashing_pairs)
        n_edges  = len(world.edges)
        comps    = _components(world.edges, n_robots)
        cur_e    = frozenset(world.edges)
        new_e    = len(cur_e - prev_edges)
        lost_e   = len(prev_edges - cur_e)
        prev_edges = cur_e

        w_pair_clash_s += n_clash * _SIM_DT
        w_any_clash_s  += _SIM_DT if n_clash > 0 else 0.0
        w_edges_sum    += n_edges
        w_comps_sum    += len(comps)
        w_csizes.extend(len(c) for c in comps)
        w_new_e        += new_e
        w_lost_e       += lost_e
        w_max_clash     = max(w_max_clash, n_clash)
        w_steps        += 1

        total_pair_clash_s += n_clash * _SIM_DT
        total_any_clash_s  += _SIM_DT if n_clash > 0 else 0.0
        peak_clash          = max(peak_clash, n_clash)

        if world.elapsed >= next_w or world.is_over():
            t0 = next_w - window
            t1 = min(world.elapsed, duration)
            real_w = t1 - t0
            windows.append({
                "t0": t0, "t1": t1,
                "pair_clash_s": w_pair_clash_s,
                "any_clash_s":  w_any_clash_s,
                "any_clash_pct": (w_any_clash_s / real_w * 100) if real_w > 0 else 0.0,
                "avg_edges": w_edges_sum / max(1, w_steps),
                "avg_comps": w_comps_sum / max(1, w_steps),
                "avg_comp_size": (sum(w_csizes) / len(w_csizes)) if w_csizes else 0.0,
                "new_edges":  w_new_e,
                "lost_edges": w_lost_e,
                "max_clash":  w_max_clash,
            })
            w_pair_clash_s = 0.0; w_any_clash_s = 0.0
            w_edges_sum = 0; w_comps_sum = 0.0
            w_csizes.clear(); w_new_e = 0; w_lost_e = 0
            w_max_clash = 0; w_steps = 0
            next_w += window

    return {
        "complexity": complexity, "seed": seed,
        "n_robots": n_robots, "duration": duration,
        "v_min": v_min, "v_max": v_max,
        "total_pair_clash_s": total_pair_clash_s,
        "total_any_clash_s":  total_any_clash_s,
        "any_clash_pct":  total_any_clash_s  / duration * 100,
        "pair_clash_pct": total_pair_clash_s / duration * 100,
        "peak_clash": peak_clash,
        "windows": windows,
    }


# ── Printing ──────────────────────────────────────────────────────────────────

def _bar(pct: float, width: int = 20) -> str:
    filled = round(pct / 100 * width)
    return "#" * filled + "." * (width - filled)


def print_report(s: dict, window: float) -> None:
    print()
    print(f"+-- {s['complexity'].upper()}  seed={s['seed']}  "
          f"{s['n_robots']} robots  {s['duration']:.0f}s  "
          f"speed {s['v_min']:.0f}-{s['v_max']:.0f} px/s")
    print(f"|   (channels assigned randomly - no agent help)")
    print(f"|")
    # any_clash_pct = fraction of time ANY clash was active (0-100%)
    # pair_clash_pct = pair-seconds / duration (can exceed 100% with simultaneous clashes)
    print(f"|   Clash-time (any):  {s['total_any_clash_s']:>6.1f}s  "
          f"({s['any_clash_pct']:>5.1f}%)  {_bar(s['any_clash_pct'])}")
    print(f"|   Pair-clash burden: {s['total_pair_clash_s']:>6.1f}s  "
          f"({s['pair_clash_pct']:>5.1f}%  -- pair-seconds, can exceed 100%)")
    print(f"|   Peak clashes: {s['peak_clash']} simultaneous pair(s)")
    print(f"|")

    hdr  = f"  {'Window':<11}  {'Edges':>5}  {'Comps':>5}  {'AvgSz':>5}  "
    hdr += f"{'NewE':>5}  {'LostE':>5}  {'AnyClsh':>7}  {'Any%':>5}  {'MaxClsh':>7}"
    sep  = "  " + "-" * (len(hdr) - 2)
    print(f"|{hdr}")
    print(f"|{sep}")
    for w in s["windows"]:
        label = f"{w['t0']:.0f}-{w['t1']:.0f}s"
        row  = f"  {label:<11}  {w['avg_edges']:>5.1f}  {w['avg_comps']:>5.1f}  "
        row += f"{w['avg_comp_size']:>5.1f}  {w['new_edges']:>5}  {w['lost_edges']:>5}  "
        row += f"{w['any_clash_s']:>7.1f}  {w['any_clash_pct']:>4.0f}%  {w['max_clash']:>7}"
        print(f"|{row}")
    print(f"+{'-' * (len(hdr) - 1)}")


def print_comparison(results: List[dict], window: float) -> None:
    """Print a compact side-by-side summary when comparing multiple seeds."""
    print()
    complexity = results[0]["complexity"]
    dur        = results[0]["duration"]
    sep = "-" * 52
    print(sep)
    print(f"  Seed comparison  {complexity.upper()}  {dur:.0f}s  "
          f"(random channel assignment)")
    print(sep)
    print(f"  {'Seed':>6}  {'AnyClsh-s':>9}  {'Any%':>5}  {'PairBurden':>10}  {'Peak':>5}  Bar (any%)")
    print(f"  {'----':>6}  {'---------':>9}  {'----':>5}  {'----------':>10}  {'----':>5}  " + "-" * 20)
    for s in results:
        bar = _bar(s["any_clash_pct"], 20)
        print(f"  {s['seed']:>6}  {s['total_any_clash_s']:>9.1f}  "
              f"{s['any_clash_pct']:>4.0f}%  {s['pair_clash_pct']:>9.0f}%  "
              f"{s['peak_clash']:>5}  {bar}")
    print(sep)
    print()
    print("  Target range for study trials: ~15-35% clash without agent help.")
    print("  Low  (<10%): too easy  -- robots barely interact.")
    print("  High (>50%): chaotic   -- little room for meaningful agent assistance.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Headless scenario analyser — evaluate seeds before running the study.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scenario_preview.py -c medium -s 42
  python scenario_preview.py -c hard -s 137 -d 150 -w 15
  python scenario_preview.py -c easy --seeds 1 5 10 42 100
        """,
    )
    parser.add_argument("--complexity", "-c", default="medium",
                        choices=list(COMPLEXITY_PRESETS),
                        help="Scenario complexity preset  (default: medium)")
    parser.add_argument("--seed", "-s", type=int, default=None,
                        help="Single RNG seed  (default: 42)")
    parser.add_argument("--seeds", type=int, nargs="+", metavar="SEED",
                        help="Compare multiple seeds (overrides --seed)")
    parser.add_argument("--duration", "-d", type=float, default=None,
                        help="Override duration in seconds")
    parser.add_argument("--window", "-w", type=float, default=10.0,
                        help="Stats window size in seconds  (default: 10)")
    args = parser.parse_args()

    seeds = args.seeds if args.seeds else [args.seed if args.seed is not None else 42]

    if len(seeds) == 1:
        result = run_preview(args.complexity, seeds[0], args.duration, args.window)
        print_report(result, args.window)
    else:
        results = []
        for seed in seeds:
            print(f"  simulating seed={seed}...", end="\r", flush=True)
            results.append(run_preview(args.complexity, seed, args.duration, args.window))
        print(" " * 40, end="\r")  # clear the progress line
        print_comparison(results, args.window)
        print()
        # Also print full report for whichever seed had clash% closest to 25%
        best = min(results, key=lambda r: abs(r["any_clash_pct"] - 25.0))
        print(f"  Best candidate (closest to 25% clash): seed={best['seed']}")
        print_report(best, args.window)


if __name__ == "__main__":
    main()
