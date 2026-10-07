#!/usr/bin/env python3
"""Workstream B (round 2) -- load and pace. Runs every variant and writes docs/analysis/round2/wB_specs.csv.

    cd G:/Files/Code/GraphColouringNew
    C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wB_main.py

Read-only on Results/. Deterministic (narration null simulation seeded). ~3-4 minutes.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wB_common as c  # noqa: E402
import wB_load  # noqa: E402
import wB_narration  # noqa: E402


def main():
    t0 = time.time()
    S, T, R, tl = c.build()
    print('Strategic decisions %d, tactical confirms %d, people %d (v1.12+: %d)'
          % (len(S), len(T), S.pid.nunique(), S[S.vrank >= c.V112].pid.nunique()))
    sp = c.Specs('B')
    wB_load.run_all(sp, S, T)
    wB_narration.run(sp, S, T, tl)
    out = c.BASE / 'docs' / 'analysis' / 'round2' / 'wB_specs.csv'
    F = sp.frame()
    F.to_csv(out, index=False, float_format='%.6g')
    print('\nWrote %s (%d rows) in %.0f s' % (out, len(F), time.time() - t0))


if __name__ == '__main__':
    main()
