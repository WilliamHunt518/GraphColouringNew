"""Workstream E -- runs E1 (coding reliability) and E2/E3 (stated reasons vs behaviour) and writes
docs/analysis/round2/wE_specs.csv.

Run from the repo root:  C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wE_main.py
(about 1.5 minutes; the leave-one-person-out gates refit every S-all model 33 times)
"""
import sys

import pandas as pd

import wE_behaviour
import wE_kappa
from wE_common import BASE

COLS = ['workstream', 'variant_id', 'extra', 'description', 'sample', 'outcome', 'predictor', 'model', 'estimate',
        'ci_lo', 'ci_hi', 'estimate_scale', 'p', 'n_obs', 'n_people', 'expected_direction', 's1_same_direction',
        'both_orders_same_direction', 'loo_sign_flip', 'notes']

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    print('=== E1 reliability ===')
    rows = wE_kappa.run()
    print('\n=== E2/E3 behaviour ===')
    rows += wE_behaviour.run()
    df = pd.DataFrame(rows)
    df['workstream'] = 'E'
    for c in ('estimate', 'ci_lo', 'ci_hi'):
        df[c] = pd.to_numeric(df[c], errors='coerce').round(4)
    df['p'] = df.p.apply(lambda v: v if isinstance(v, str) else ('' if pd.isna(v) else round(float(v), 5)))
    out = BASE / 'docs' / 'analysis' / 'round2' / 'wE_specs.csv'
    df[COLS].to_csv(out, index=False)
    print('\nwrote %s (%d rows)' % (out, len(df)))
