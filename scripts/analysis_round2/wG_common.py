"""Round 2 · workstream G · shared data and model helpers (read-only over Results/).

Data are the round-1 tables, reused rather than re-parsed:
  * strategic decisions: `h9_workload_speed.load_all()` (row-for-row equal to the builder's
    `load_decisions()`, asserted here), plus the builder's `dominated` / `odd` / `elapsed`;
  * tactical plans: `h9_workload_speed.load_all()` (route, Suggest reveal entries, plan size);
  * sessions: `h4_h10_data.sessions()` (score, rescaled score for P01/P02, benchmark share).
"""
from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts' / 'analysis_round1'))
warnings.filterwarnings('ignore')

import build_findings_synthesis as B  # noqa: E402
import h9_workload_speed as H9  # noqa: E402
import h4_h10_data as H4  # noqa: E402
from agent_scenario_stats import vrank  # noqa: E402

SWAPPED = {'P31', 'P32', 'P33', 'P34', 'P35', 'P36'}
V112 = vrank('study-v1.12')
SUGGEST_REVEAL_S = 1.0


def _thirds(s):
    return pd.cut(s.rank(pct=True), [0, 1 / 3, 2 / 3, 1], labels=[0, 1, 2],
                  include_lowest=True).astype(int)


def load():
    S, T, _, _, _ = B._quietly(H9.load_all)
    ref = B._quietly(B.load_decisions)
    assert (S[['pid', 'run', 'idx', 'choice']].values == ref[['pid', 'run', 'idx', 'choice']].values).all()
    S = S.copy()
    for k in ('dominated', 'odd', 'elapsed', 'cons_total', 'aggr_total'):
        S[k] = ref[k].values
    order = S[S.run == 1].groupby('pid').scenario.first()
    for d in (S, T):
        d['run2'] = (d.run == 2).astype(int)
        d['order'] = d.pid.map(order)
        d['swapped'] = d.pid.isin(SWAPPED).astype(int)
        d['v112'] = (d.vrank >= V112).astype(int)
    S['multi'] = (S.ncolours >= 2).astype(int)
    S['lsize'] = np.log(S.ndrones.clip(lower=1))
    S['emin'] = S.elapsed / 60.0
    S['third'] = S.groupby(['pid', 'run']).idx.transform(_thirds)
    S['first3'] = (S.third == 0).astype(int)
    S['cons'] = (S.choice == 'conservative').astype(int)
    S['pre'] = ((S.manual == 1) & (S.early == True)).astype(int)  # noqa: E712
    S['net'] = S.secs - S.deployEnabled          # card: time after the forced reveal; manual: raw
    S['lnet'] = np.log(S.net.clip(lower=0.5))
    S['lraw'] = np.log(S.secs.clip(lower=0.5))
    T = T.copy()
    T['net'] = np.where(T.consulted == 1, T.secs - T.entries * SUGGEST_REVEAL_S, T.secs)
    T['lnet'] = np.log(T.net.clip(lower=0.5))
    T['lplan'] = np.log((T.pool * T.ntasks).clip(lower=1))
    T['emin'] = T.elapsed_open / 60.0

    P = H4.sessions().copy()
    P = P[P.pid.isin(set(S.pid))]
    P['run2'] = (P.run == 2).astype(int)
    P['order'] = P.pid.map(order)
    P['swapped'] = P.pid.isin(SWAPPED).astype(int)
    P['v112'] = P.v112.astype(int)
    P['zgame'] = P.groupby('game').score_rescaled.transform(lambda s: (s - s.mean()) / s.std())
    P['bestshare'] = P.score_rescaled / P.groupby('game').score_rescaled.transform('max')
    return S, T, P


# ── models ─────────────────────────────────────────────────────────────────────────────────────
def _full_rank(formula, data):
    rhs = formula.split('~', 1)[1]
    X = patsy.dmatrix(rhs, data, return_type='dataframe')
    return np.linalg.matrix_rank(X.values) == X.shape[1]


def reduce_formula(formula, data):
    """Drop factors that are constant, or that make the design collinear, in a subsample
    (e.g. scenario is fixed by run inside one order group). Tries, in order: drop single-level
    factors; drop C(scenario); C(game) -> C(planIndex); drop C(planIndex)."""
    f = formula
    for x in re.findall(r'C\((\w+)\)', f):
        if data[x].nunique() < 2:
            f = re.sub(r'\s*[+*]\s*\w*:?C\(%s\)' % x, '', f)
    steps = [lambda g: re.sub(r'\s*\+\s*C\(scenario\)', '', g),
             lambda g: g.replace('C(game)', 'C(planIndex)'),
             lambda g: re.sub(r'\s*\+\s*C\(planIndex\)', '', g)]
    for st in steps:
        try:
            if _full_rank(f, data):
                return f
        except Exception:
            pass
        f = st(f)
    return f


def gee(formula, data, binomial=True, reduced=True):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    m = smf.gee(formula, 'pid', data=data, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    return m.fit(cov_type='bias_reduced') if reduced else m.fit()


def est(formula, data, term, binomial=True):
    m = gee(formula, data, binomial)
    b, se = float(m.params[term]), float(m.bse[term])
    lo, hi = b - 1.96 * se, b + 1.96 * se
    return dict(b=b, lo=lo, hi=hi, p=float(m.pvalues[term]), n_obs=int(m.nobs),
                n_people=int(data.pid.nunique()))


def point(formula, data, term, binomial=True):
    try:
        f = reduce_formula(formula, data)
        m = gee(f, data, binomial, reduced=False)
        return float(m.params[term])
    except Exception:
        return np.nan


def loo(formula, data, term, binomial=True):
    vals = []
    for pid in sorted(data.pid.unique()):
        vals.append(point(formula, data[data.pid != pid], term, binomial))
    return np.array(vals)
