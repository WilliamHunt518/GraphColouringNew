"""Workstream E shared helpers: codings, behaviour tables, samples, GEE with gates.

Read-only on Results/ and docs/analysis/round1/. Run from the repo root.
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
sys.path.insert(0, str(BASE / 'scripts' / 'analysis_round1'))
from build_findings_synthesis import load_decisions  # noqa: E402
from h2_verification_cost import load as load_tactical  # noqa: E402
import h6_stated_preference as h6  # noqa: E402  (existing() / reduce() for the original codes)

warnings.filterwarnings('ignore')
MINE = BASE / 'docs' / 'analysis' / 'round2' / 'wE_codes.csv'
R1 = BASE / 'docs' / 'analysis' / 'round1' / 'h6_codes.csv'
SWAPPED = {'P31', 'P32', 'P33', 'P34', 'P35', 'P36'}


def codes(path):
    c = pd.read_csv(path, dtype=str).fillna('').set_index('pid')
    c = c[c.index != 'P09']
    c['stance'] = np.where(c.cond != 'none', 'conditional', c.pref)   # ruling-applied label
    return c


def original():
    """Original quote-level single-coder stances, reduced as in round 1 (both precedences)."""
    ex = h6.existing()
    rows = {}
    for p, d in ex.items():
        if p == 'P09':
            continue
        rows[p] = dict(rank_first=h6.reduce(d['ac']), cond_first=h6.reduce(d['ac'], True),
                       rank_first_all=h6.reduce(d['all']))
    return pd.DataFrame(rows).T


_CACHE = {}


def behaviour():
    """Decision-level strategic table and plan-level tactical table, P09 and residuals excluded."""
    if 'b' in _CACHE:
        return _CACHE['b']
    dec = load_decisions()
    dec = dec[(dec.pid != 'P09') & (dec.residual == 0)].copy()
    dec['game'] = dec.scenario + dec.planIndex.astype(int).astype(str)
    first = dec[dec.run == 1].groupby('pid').scenario.first()
    dec['order'] = dec.pid.map(first)
    dec['three'] = (dec.ncolours == 3).astype(int)
    dec['single'] = (dec.ncolours == 1).astype(int)
    dec['zdrones'] = (dec.ndrones - dec.ndrones.mean()) / dec.ndrones.std()
    tac, _, v112 = load_tactical()
    tac = tac[(tac.pid != 'P09') & (tac.residual == 0)].copy()
    tac['order'] = tac.pid.map(first)
    med = tac['size'].median()
    tac['big'] = (tac['size'] > med).astype(int)
    tac['zlogsize'] = np.log(tac['size'])
    tac['zlogsize'] = (tac.zlogsize - tac.zlogsize.mean()) / tac.zlogsize.std()
    _CACHE['b'] = (dec, tac, set(v112), first)
    return _CACHE['b']


def sample(df, code, v112):
    if code == 'S-all':
        return df
    if code == 'S-v112':
        return df[df.pid.isin(v112)]
    if code == 'S-s1':
        return df[df.run == 1]
    if code == 'S-27':
        return df[~df.pid.isin(SWAPPED)]
    if code == 'S-6':
        return df[df.pid.isin(SWAPPED)]
    raise ValueError(code)


def gee(formula, df, term):
    """Logistic GEE, clusters = person, independence working structure, bias-reduced errors.
    Returns (OR, lo, hi, p) for `term`, or None if it cannot be fitted."""
    try:
        m = smf.gee(formula, groups='pid', data=df, family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Independence()).fit(cov_type='bias_reduced')
        b, se, p = m.params[term], m.bse[term], m.pvalues[term]
        if not np.isfinite(se) or se > 50 or abs(b) > 8:
            return None
        return float(np.exp(b)), float(np.exp(b - 1.96 * se)), float(np.exp(b + 1.96 * se)), float(p)
    except Exception:
        return None


def coef_only(formula, df, term):
    try:
        m = smf.gee(formula, groups='pid', data=df, family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Independence()).fit()
        return float(m.params[term])
    except Exception:
        return np.nan


def gates(formula, df, term, sign, between=True):
    """S-s1 direction, both-order direction, leave-one-person-out range + sign flip."""
    def same(x):
        return 'na' if not np.isfinite(x) or sign == 0 else int(np.sign(x) == sign)
    s1 = coef_only(formula, df[df.run == 1], term)
    o = [coef_only(formula, df[df.order == k], term) for k in ('strategic', 'tactical')]
    both = 'na' if any(not np.isfinite(x) for x in o) or sign == 0 else int(all(np.sign(x) == sign for x in o))
    loo = []
    for p in sorted(df.pid.unique()):
        loo.append(coef_only(formula, df[df.pid != p], term))
    loo = np.array([x for x in loo if np.isfinite(x)])
    full = coef_only(formula, df, term)
    flip = int(np.any(np.sign(loo) != np.sign(full))) if len(loo) else 'na'
    return dict(s1=same(s1), orders=both, loo_flip=flip,
                loo_range='LOO OR %.2f-%.2f' % (np.exp(loo.min()), np.exp(loo.max())) if len(loo) else '',
                order_or='order ORs strat-first %.2f / tac-first %.2f' % tuple(np.exp(o)))
