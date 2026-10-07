"""H2 follow-up (found after the primary was run, exploratory): how fragile is component C?

Only a handful of consulted plans were modified, so the binomial GEE in component C rests on very
few events in very few clusters. This prints who the modified plans belong to, a leave-one-person-
out re-fit of the interaction, and a person-level check of the A/A' split (consulting vs keeping).

Run from the repo root:  C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h2_fragility.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from h2_verification_cost import load, z  # noqa: E402
from build_findings_synthesis import gee, term  # noqa: E402

warnings.filterwarnings('ignore')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    tac, _, new = load()
    con = tac[tac.consulted == 1].copy()
    con['ipd'] = con.net / con.drones
    mod = con[con.keep == 0]
    print('modified-after-consulting plans by person:', mod.pid.value_counts().to_dict())
    print(mod[['pid', 'run', 'size', 'drones', 'net', 'pre', 'nedits']].to_string())
    print('size of modified vs kept consulted plans: median %.0f vs %.0f'
          % (mod['size'].median(), con[con.keep == 1]['size'].median()))
    res = []
    for pid in sorted(mod.pid.unique()):
        d = con[con.pid != pid].copy()
        d['size_z'], d['ipd_z'] = z(d['size']), z(d['ipd'])
        try:
            t = term(gee('keep ~ size_z * ipd_z + C(scenario) + C(run)', d, binomial=True), 'size_z:ipd_z')
            res.append((pid, np.exp(t['b']), t['p']))
        except Exception as e:  # noqa: BLE001
            res.append((pid, None, str(e)))
    print('leave-one-person-out, interaction OR and p (dropping each person with a modified plan):')
    for r in res:
        print('  drop %s: %s' % (r[0], r[1:]))
    # person-level: does consulting rise with size within person while keep|consulted does not?
    tac['big'] = (tac['size'] > tac['size'].median()).astype(int)
    pp = tac.groupby(['pid', 'big']).agg(consult=('consulted', 'mean'), keep=('keep', 'mean')).unstack()
    dc = (pp[('consult', 1)] - pp[('consult', 0)]).dropna()
    print('within person, consult rate big - small plans: median %+.3f, higher for %d of %d'
          % (dc.median(), (dc > 0).sum(), len(dc)))
    kc = con.assign(big=(con['size'] > tac['size'].median()).astype(int)).groupby(['pid', 'big']).keep.mean().unstack()
    d = (kc[1] - kc[0]).dropna()
    print('within person, keep|consulted big - small: median %+.3f, lower for %d, higher for %d, same %d of %d'
          % (d.median(), (d < 0).sum(), (d > 0).sum(), (d == 0).sum(), len(d)))


if __name__ == '__main__':
    main()
