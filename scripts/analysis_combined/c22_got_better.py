#!/usr/bin/env python3
"""C22 'got better with practice' -- did their use of the assistants change, and is that why their
workload is lower?  Read-only over Results/. Run from the repo root:

    C:/Users/Work/anaconda3/python.exe scripts/analysis_combined/c22_got_better.py

Report: docs/analysis/combined/c22_got_better.md.  P09 excluded (via the shared loaders).

PRE-STATED COMPARISONS (fixed before any number was computed). Group = C22 coded (n = 6) vs not
(n = 27). Every test is a two-sided permutation test of the difference in group means (C22 - rest),
20,000 random relabellings of the group label, seed fixed; categorical splits use the difference in
proportions (equivalent to a Fisher-type test).
  A  reliance, CHANGE session 2 - session 1 (7): took, consult, keep, recSug, preempt,
     stratNet (log median net strategic decision time), tacNet (log median net tactical time)
  A' reliance, LEVEL = mean of the two sessions (same 7)
  B  workload (4): RTLX session 1, session 2, change (s2 - s1), mean of both; plus the same four
     with RTLX expressed relative to the game mean (game = scenario x plan index) as a robustness
     row (4 more)
  C  performance / design (5): mean zgame (score z-scored within game; P01/P02 rescaled), mean
     mission completion rate, scenario order (strategic first), swapped game pairing, version
     >= study-v1.12
  D  self-report accuracy, CHANGE s2 - s1 (3): zgame, completion, mean mission time
     (strategic/tactical decision-time change are already in A)
  E  mediation (descriptive): OLS of mean RTLX on C22 alone, then + each A / A' measure (and three
     performance/order covariates); report how much the C22 coefficient moves, and a permutation p
     for the adjusted C22 coefficient.
Tests: 7 + 7 + 8 + 5 + 3 = 30 group comparisons, + 17 adjusted-coefficient permutations in E.
None are corrected; none were powered.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for p in ('scripts', 'scripts/analysis_round1', 'scripts/analysis_round2'):
    sys.path.insert(0, str(ROOT / p))
warnings.filterwarnings('ignore')

import build_findings_synthesis as B  # noqa: E402
import h1_archetypes as H1  # noqa: E402
import wG_common as G  # noqa: E402

NPERM = 20000
RNG = np.random.default_rng(20261008)
REL = ['took', 'consult', 'keep', 'recSug', 'preempt', 'stratNet', 'tacNet']


def perm(y, g, n=NPERM):
    """Two-sided permutation p for mean(y[g]) - mean(y[~g]); drops NaN."""
    y, g = np.asarray(y, float), np.asarray(g, bool)
    ok = ~np.isnan(y)
    y, g = y[ok], g[ok]
    obs = y[g].mean() - y[~g].mean()
    k = g.sum()
    null = np.empty(n)
    for i in range(n):
        m = np.zeros(len(y), bool)
        m[RNG.permutation(len(y))[:k]] = True
        null[i] = y[m].mean() - y[~m].mean()
    p = (np.sum(np.abs(null) >= abs(obs) - 1e-12) + 1) / (n + 1)
    return obs, p, int(k), int(len(y) - k)


def ols_coef(y, X):
    X = np.column_stack([np.ones(len(y))] + list(X))
    return np.linalg.lstsq(X, y, rcond=None)[0][1]


def perm_adj(y, g, z, n=5000):
    """Permutation p for the C22 coefficient adjusted for covariate z (labels permuted, z fixed)."""
    y, g, z = (np.asarray(a, float) for a in (y, g, z))
    ok = ~(np.isnan(y) | np.isnan(z))
    y, g, z = y[ok], g[ok], z[ok]
    obs = ols_coef(y, [g, z])
    null = np.array([ols_coef(y, [RNG.permutation(g), z]) for _ in range(n)])
    return obs, (np.sum(np.abs(null) >= abs(obs) - 1e-12) + 1) / (n + 1)


def build():
    S, T, R, SS = B._quietly(H1.parse)
    F = H1.features(S, T, R, ['pid', 'run'])
    F[['pid', 'run']] = pd.DataFrame(F.key.tolist(), index=F.index)
    Sg, Tg, P = G.load()
    F = F.drop(columns=['netSecs'])
    F = F.merge(Sg.groupby(['pid', 'run']).lnet.median().rename('stratNet').reset_index(),
                on=['pid', 'run'], how='left')
    F = F.merge(Tg.groupby(['pid', 'run']).lnet.median().rename('tacNet').reset_index(),
                on=['pid', 'run'], how='left')
    sess, _ = B._quietly(B.load_people)
    W = pd.DataFrame(sess)[['pid', 'run', 'rtlx']]
    F = F.merge(W, on=['pid', 'run'], how='left')
    F = F.merge(P[['pid', 'run', 'game', 'zgame', 'scenario', 'order', 'swapped', 'v112']],
                on=['pid', 'run'], how='left')
    F = F.merge(SS[['pid', 'run', 'completion', 'meanMissionTime']], on=['pid', 'run'], how='left')
    F['rtlx_g'] = F.rtlx - F.groupby('game').rtlx.transform('mean')
    codes = pd.read_csv(ROOT / 'docs/analysis/qual/codes_matrix.csv')
    c22 = set(codes.loc[codes.C22 == 1, 'pid'])
    F['c22'] = F.pid.isin(c22).astype(int)
    return F, c22


def wide(F, cols):
    w = F.pivot(index='pid', columns='run', values=cols)
    out = pd.DataFrame(index=w.index)
    for c in cols:
        out[c + '_1'] = w[(c, 1)]
        out[c + '_2'] = w[(c, 2)]
        out[c + '_d'] = w[(c, 2)] - w[(c, 1)]
        out[c + '_m'] = w[[(c, 1), (c, 2)]].mean(axis=1)
    return out


def row(label, y, g, rows, fam):
    obs, p, k, m = perm(y, g)
    y = np.asarray(y, float)
    gg = np.asarray(g, bool)
    rows.append(dict(family=fam, measure=label, c22=np.nanmean(y[gg]), rest=np.nanmean(y[~gg]),
                     c22_med=np.nanmedian(y[gg]), rest_med=np.nanmedian(y[~gg]),
                     diff=obs, p=p, n_c22=k, n_rest=m))


def main():
    F, c22 = build()
    cols = REL + ['rtlx', 'rtlx_g', 'zgame', 'completion', 'meanMissionTime']
    W = wide(F, cols)
    first = F[F.run == 1].set_index('pid')
    W['strat_first'] = (first.scenario == 'strategic').astype(int)
    W['swapped'] = first.swapped
    W['v112'] = first.v112
    W['c22'] = W.index.isin(c22)
    g = W.c22.values
    print('C22 members:', sorted(c22), ' n =', g.sum(), 'vs', (~g).sum())

    rows = []
    for c in REL:
        row(c + ' change', W[c + '_d'], g, rows, 'A change')
    for c in REL:
        row(c + ' level', W[c + '_m'], g, rows, "A' level")
    for c in ('rtlx', 'rtlx_g'):
        for s, lab in (('_1', 's1'), ('_2', 's2'), ('_d', 'change'), ('_m', 'mean')):
            row(f'{c} {lab}', W[c + s], g, rows, 'B workload')
    row('zgame mean', W.zgame_m, g, rows, 'C perf/design')
    row('completion mean', W.completion_m, g, rows, 'C perf/design')
    for c in ('strat_first', 'swapped', 'v112'):
        row(c, W[c], g, rows, 'C perf/design')
    for c in ('zgame', 'completion', 'meanMissionTime'):
        row(c + ' change', W[c + '_d'], g, rows, 'D accuracy')
    out = pd.DataFrame(rows)
    pd.set_option('display.width', 220)
    print(out.round(3).to_string(index=False))

    print('\nPer-person table, C22 members (s1 -> s2):')
    show = ['rtlx_1', 'rtlx_2', 'took_1', 'took_2', 'consult_1', 'consult_2', 'keep_1', 'keep_2',
            'recSug_1', 'recSug_2', 'preempt_1', 'preempt_2', 'stratNet_1', 'stratNet_2',
            'zgame_1', 'zgame_2', 'strat_first', 'swapped']
    print(W.loc[W.c22, show].round(2).to_string())

    print('\nRTLX by group x order (strat_first=1: Strategic Heavy first):')
    print(W.groupby(['c22', 'strat_first'])[['rtlx_1', 'rtlx_2', 'rtlx_m']]
          .agg(['mean', 'count']).round(2).to_string())
    print('\nrank of each C22 member among all 33 (1 = lowest workload):')
    print('  s1:', W.rtlx_1.rank()[W.c22].to_dict())
    print('  s2:', W.rtlx_2.rank()[W.c22].to_dict())
    print('  rtlx s1-s2 correlation, all:', round(W[['rtlx_1', 'rtlx_2']].corr().iloc[0, 1], 3))

    print('\nE  mediation of mean RTLX ~ C22 (n = 33 unless noted)')
    y = W.rtlx_m.values
    print(f'  C22 alone: b = {ols_coef(y, [g.astype(float)]):.2f}')
    med = []
    covs = [c + s for c in REL for s in ('_d', '_m')] + ['zgame_m', 'completion_m', 'strat_first']
    for c in covs:
        z = W[c].values.astype(float)
        ok = ~np.isnan(z)
        b0 = ols_coef(y[ok], [g[ok].astype(float)])
        b1, p = perm_adj(y, g, z)
        med.append(dict(covariate=c, n=int(ok.sum()), b_c22=b0, b_c22_adj=b1, change=b1 - b0,
                        r_cov_rtlx=np.corrcoef(z[ok], y[ok])[0, 1], p_adj=p))
    print(pd.DataFrame(med).round(3).to_string(index=False))
    print('\nTests run:', len(out), 'group comparisons +', len(med), 'adjusted permutations')

    # Robustness (descriptive, not counted as new hypotheses): reconcile with the screening
    # Mann-Whitney, and check the two p < .05 group differences for single-person dependence.
    from scipy.stats import mannwhitneyu
    for c in ('rtlx_m', 'rtlx_1', 'rtlx_2'):
        print(f'  Mann-Whitney {c}: p = {mannwhitneyu(W.loc[W.c22, c], W.loc[~W.c22, c]).pvalue:.3f}')
    print('  rest: share with zgame improving s1->s2 =',
          round((W.loc[~W.c22, 'zgame_d'] > 0).mean(), 2), '; C22:',
          round((W.loc[W.c22, 'zgame_d'] > 0).mean(), 2))
    for c in ('took_m', 'zgame_d', 'rtlx_m', 'rtlx_2'):
        diffs = {}
        for pid in sorted(c22):
            ww = W.drop(index=pid)
            diffs[pid] = round(ww.loc[ww.c22, c].mean() - ww.loc[~ww.c22, c].mean(), 2)
        print(f'  leave-one-C22-out diff {c}:', diffs)
    print('  others, zgame_d by order:', W[~W.c22].groupby('strat_first').zgame_d.mean().round(2).to_dict(),
          ' C22:', W[W.c22].groupby('strat_first').zgame_d.mean().round(2).to_dict())


if __name__ == '__main__':
    main()
