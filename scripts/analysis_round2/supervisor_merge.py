#!/usr/bin/env python3
"""Round 2 · merge every workstream's spec table and apply one Benjamini–Hochberg correction.

The pooling rule is in docs/analysis/round2/SUPERVISOR_LOG.md and was written before any q-value
was computed. Writes docs/analysis/round2/round2_pooled.csv (every row, with q and the gate verdict)
and prints the rows that reach q < .10.

    python scripts/analysis_round2/supervisor_merge.py
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests

BASE = Path(__file__).resolve().parents[2]
R2 = BASE / 'docs' / 'analysis' / 'round2'

EXCLUDE_IDS = {'D2d', 'D2e', 'D2h', 'F4.1'}
# Agent-identified artefacts: kept in the pool, vetoed at review if they pass.
ARTEFACTS = {'A1a', 'A1b', 'A1c', 'A8a', 'B2d', 'B2d-r1'}


def gate_ok(v):
    """A gate passes if it is 1 or not applicable; it fails on 0 (or, for the flip gate, on 1)."""
    return str(v).strip().lower() in ('1', '1.0', 'na', 'nan', '')


def main():
    frames = [pd.read_csv(f) for f in sorted(glob.glob(str(R2 / 'w*_specs.csv')))]
    d = pd.concat(frames, ignore_index=True)
    d['p'] = pd.to_numeric(d['p'], errors='coerce')
    d['estimate'] = pd.to_numeric(d['estimate'], errors='coerce')
    vid = d['variant_id'].astype(str)
    # Ids carry suffixes (e.g. 'D2e.first', 'A1a-pool'), so the rule's ids are matched as prefixes. F4.1 is
    # matched exactly: its valid siblings F4.1p / F4.3 must stay in.
    def prefixed(ids):
        return vid.apply(lambda v: any(v == i or v.startswith(i + '.') or v.startswith(i + '-') for i in ids))
    excluded = ((d['sample'].astype(str) == 'S-6') | prefixed(EXCLUDE_IDS - {'F4.1'}) | (vid == 'F4.1')
                | d['p'].isna() | d['estimate'].isna())
    # B's X3 is an artefact too, but variant ids repeat across workstreams, so key it with the workstream.
    artefact = prefixed(ARTEFACTS) | ((d['workstream'].astype(str).str.upper().str[0] == 'B') & (vid == 'X3'))
    d['pooled'] = ~excluded
    d['q'] = np.nan
    pooled = d[d['pooled']]
    d.loc[pooled.index, 'q'] = multipletests(pooled['p'].clip(lower=1e-300), method='fdr_bh')[1]
    flip_ok = d['loo_sign_flip'].astype(str).str.strip().str.lower().isin(('0', '0.0', 'na', 'nan', ''))
    d['gates_pass'] = d['s1_same_direction'].map(gate_ok) & d['both_orders_same_direction'].map(gate_ok) & flip_ok
    d['artefact'] = artefact
    d['candidate'] = (d['q'] < 0.10) & d['gates_pass'] & ~d['artefact']
    d.to_csv(R2 / 'round2_pooled.csv', index=False)

    print(f"{len(d)} tests; pooled {int(d['pooled'].sum())}; q < .10: {int((d['q'] < .10).sum())}; "
          f"of those gates pass: {int(((d['q'] < .10) & d['gates_pass']).sum())}; "
          f"candidates (also not an artefact): {int(d['candidate'].sum())}")
    cols = ['workstream', 'variant_id', 'sample', 'description', 'estimate', 'estimate_scale', 'p', 'q',
            'gates_pass', 'artefact']
    pd.set_option('display.width', 250, 'display.max_colwidth', 70)
    print(d[d['q'] < .10].sort_values('q')[cols].to_string(index=False))


if __name__ == '__main__':
    main()
