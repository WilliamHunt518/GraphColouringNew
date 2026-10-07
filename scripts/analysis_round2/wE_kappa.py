"""Workstream E1 -- reliability of the third coding (wE_codes.csv) against round 1's second coding
(h6_codes.csv) and the original single-coder quote stances (quotes.json, reduced as in round 1).

Run: C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wE_kappa.py
"""
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

from wE_common import MINE, R1, codes, original, behaviour

B = 4000


def kappa_ci(a, b, seed=42):
    a, b = list(a), list(b)
    k = cohen_kappa_score(a, b)
    rng = np.random.default_rng(seed)
    ks = []
    n = len(a)
    for _ in range(B):
        i = rng.integers(0, n, n)
        aa, bb = [a[j] for j in i], [b[j] for j in i]
        if len(set(aa) | set(bb)) > 1:
            kk = cohen_kappa_score(aa, bb)
            if np.isfinite(kk):
                ks.append(kk)
    lo, hi = np.percentile(ks, [2.5, 97.5])
    return k, lo, hi, float(np.mean([x == y for x, y in zip(a, b)])), n


def fleiss(table):
    """Fleiss' kappa; table = subjects x categories counts."""
    t = np.asarray(table, float)
    n = t.sum(1)[0]
    p = t.sum(0) / t.sum()
    P = ((t * t).sum(1) - n) / (n * (n - 1))
    pe = (p * p).sum()
    return (P.mean() - pe) / (1 - pe)


def fleiss_ci(labels, seed=42):
    cats = sorted(set(np.ravel(labels)))
    tab = np.array([[sum(r == c for r in row) for c in cats] for row in labels])
    k = fleiss(tab)
    rng = np.random.default_rng(seed)
    ks = []
    for _ in range(B):
        i = rng.integers(0, len(tab), len(tab))
        kk = fleiss(tab[i])
        if np.isfinite(kk):
            ks.append(kk)
    lo, hi = np.percentile(ks, [2.5, 97.5])
    return k, lo, hi


def per_category(a, b, cats):
    out = {}
    for c in cats:
        x, y = [v == c for v in a], [v == c for v in b]
        if len(set(x)) > 1 or len(set(y)) > 1:
            out[c] = (cohen_kappa_score(x, y), sum(x), sum(y))
    return out


def has(col, tier):
    return col.str.contains(tier).astype(int)


def run(verbose=True):
    mine, r1, orig = codes(MINE), codes(R1), original()
    _, _, v112, _ = behaviour()
    pids = sorted(set(mine.index) & set(r1.index))
    po = sorted(set(mine.index) & set(orig.index))
    rows = []
    out = []

    def add(vid, desc, a, b, sample='S-all', extra=0, notes=''):
        k, lo, hi, agree, n = kappa_ci(a, b)
        rows.append(dict(variant_id=vid, extra=extra, description=desc, sample=sample, outcome='coding agreement',
                         predictor='coder', model='Cohen kappa, bootstrap 95% CI over participants (4000)',
                         estimate=k, ci_lo=lo, ci_hi=hi, estimate_scale='kappa', p='na', n_obs=n, n_people=n,
                         expected_direction='none', s1_same_direction='na', both_orders_same_direction='na',
                         loo_sign_flip='na', notes=('raw agreement %.2f; reliability bar .60. ' % agree) + notes))
        out.append('%-6s %-70s k=%.3f [%.3f, %.3f] agree=%.2f n=%d' % (vid, desc[:70], k, lo, hi, agree, n))

    a, b = mine.loc[pids, 'pref'], r1.loc[pids, 'pref']
    add('E1a', 'pref (ranking-first) vs round-1 second coding pref', a, b)
    add('E1b', 'stance (ruling applied: cond!=none -> conditional) vs round-1 same mapping',
        mine.loc[pids, 'stance'], r1.loc[pids, 'stance'])
    add('E1c', 'pref vs original single-coder stances (agent_comparison, ranking-first)',
        mine.loc[po, 'pref'], orig.loc[po, 'rank_first'])
    add('E1d', 'stance (ruling applied) vs original stances (agent_comparison, conditional-first)',
        mine.loc[po, 'stance'], orig.loc[po, 'cond_first'])
    add('E1e', 'binary prefers-tactical vs round-1', a == 'tactical', b == 'tactical')
    add('E1f', 'binary prefers-tactical vs original (ranking-first)',
        mine.loc[po, 'pref'] == 'tactical', orig.loc[po, 'rank_first'] == 'tactical')
    add('E1g', 'states a situational rule (cond != none) vs round-1',
        mine.loc[pids, 'cond'] != 'none', r1.loc[pids, 'cond'] != 'none')
    add('E1h', 'cond category (complex / simple / other / none) vs round-1', mine.loc[pids, 'cond'], r1.loc[pids, 'cond'])
    pv = [p for p in pids if p in v112]
    add('E1i', 'pref vs round-1, v1.12+ cohort', mine.loc[pv, 'pref'], r1.loc[pv, 'pref'], sample='S-v112')
    hi = [p for p in pids if mine.loc[p, 'confidence'] != 'low' and r1.loc[p, 'confidence'] != 'low'
          and mine.loc[p, 'led'] != '1' and r1.loc[p, 'led'] != '1']
    add('E1j', 'pref vs round-1, both coders non-low confidence and not led', mine.loc[hi, 'pref'], r1.loc[hi, 'pref'],
        notes='subset chosen on both codings')
    rec = [p for p in pids if mine.loc[p, 'source'] != 'interview']
    add('E1k', 'pref vs round-1, participants with a recorded debrief', mine.loc[rec, 'pref'], r1.loc[rec, 'pref'])
    # extra X1: reason codes (the behaviour links below depend on them)
    for col, tier, nm in (('r_speed', 'S', 'speed about strategic'), ('r_speed', 'T', 'speed about tactical'),
                          ('r_visible_err', 'S', 'visible error about strategic'),
                          ('r_cantcheck', 'T', 'cannot check, about tactical'), ('r_cantcheck', 'S|T', 'cannot check, any tier')):
        add('X1-%s%s' % (col[2:], tier.replace('|', '')), 'reason code: %s vs round-1' % nm,
            has(mine.loc[pids, col], tier), has(r1.loc[pids, col], tier), extra=1,
            notes='extra X1 (reliability of the reason codes used in E2)')
    # extra X3: Fleiss kappa across the three codings (ranking-first pref)
    common = sorted(set(pids) & set(po))
    lab = [[mine.loc[p, 'pref'], r1.loc[p, 'pref'], orig.loc[p, 'rank_first']] for p in common]
    k, lo, hi_ = fleiss_ci(lab)
    rows.append(dict(variant_id='X3', extra=1, description='Fleiss kappa, three codings (pref ranking-first)',
                     sample='S-all', outcome='coding agreement', predictor='coder', model='Fleiss kappa, bootstrap CI',
                     estimate=k, ci_lo=lo, ci_hi=hi_, estimate_scale='kappa', p='na', n_obs=len(common),
                     n_people=len(common), expected_direction='none', s1_same_direction='na',
                     both_orders_same_direction='na', loo_sign_flip='na', notes='extra X3'))
    out.append('X3     Fleiss three codings k=%.3f [%.3f, %.3f] n=%d' % (k, lo, hi_, len(common)))

    if verbose:
        print('\n'.join(out))
        print('\nmy pref:', mine.pref.value_counts().to_dict(), '| my stance:', mine.stance.value_counts().to_dict())
        print('r1 pref:', r1.pref.value_counts().to_dict(), '| r1 stance:', r1.stance.value_counts().to_dict())
        print('orig rank-first:', orig.rank_first.value_counts().to_dict(), '| cond-first:', orig.cond_first.value_counts().to_dict())
        print('\nE1a confusion (rows = this coding, cols = round-1):')
        print(pd.crosstab(a.rename('wE'), b.rename('r1')).to_string())
        print('disagreements:', [(p, mine.loc[p, 'pref'], r1.loc[p, 'pref']) for p in pids if mine.loc[p, 'pref'] != r1.loc[p, 'pref']])
        cats = ['tactical', 'strategic', 'both', 'neither', 'conditional', 'none']
        print('per-category kappa vs r1 (k, n wE, n r1):', {c: tuple(round(x, 2) for x in v) for c, v in per_category(list(a), list(b), cats).items()})
        print('\nE1c confusion (vs original ranking-first):')
        print(pd.crosstab(mine.loc[po, 'pref'].rename('wE'), orig.loc[po, 'rank_first'].rename('orig')).to_string())
        print('disagreements:', [(p, mine.loc[p, 'pref'], orig.loc[p, 'rank_first']) for p in po if mine.loc[p, 'pref'] != orig.loc[p, 'rank_first']])
        print('per-category kappa vs orig:', {c: tuple(round(x, 2) for x in v) for c, v in per_category(list(mine.loc[po, 'pref']), list(orig.loc[po, 'rank_first']), cats).items()})
        print('\nE1b confusion (stance vs r1 stance):')
        print(pd.crosstab(mine.loc[pids, 'stance'].rename('wE'), r1.loc[pids, 'stance'].rename('r1')).to_string())
        print('\nE1d confusion (stance vs original conditional-first):')
        print(pd.crosstab(mine.loc[po, 'stance'].rename('wE'), orig.loc[po, 'cond_first'].rename('orig')).to_string())
        print('\nE1h cond confusion:')
        print(pd.crosstab(mine.loc[pids, 'cond'].rename('wE'), r1.loc[pids, 'cond'].rename('r1')).to_string())
        print('cond disagreements:', [(p, mine.loc[p, 'cond'], r1.loc[p, 'cond']) for p in pids if mine.loc[p, 'cond'] != r1.loc[p, 'cond']])
        print('round-1 vs original (for reference) pref kappa: %.3f' % cohen_kappa_score(r1.loc[po, 'pref'], orig.loc[po, 'rank_first']))
        t, s = (mine.pref == 'tactical').sum(), (mine.pref == 'strategic').sum()
        from scipy import stats
        print('\nsign test this coding: tactical %d vs strategic %d, p=%.4f' % (t, s, stats.binomtest(int(t), int(t + s)).pvalue))
        nl = mine[(mine.led != '1') & (mine.confidence != 'low')]
        t2, s2 = (nl.pref == 'tactical').sum(), (nl.pref == 'strategic').sum()
        print('  not led and not low confidence: %d vs %d, p=%.4f' % (t2, s2, stats.binomtest(int(t2), int(t2 + s2)).pvalue))
        agree3 = [p for p in common if mine.loc[p, 'pref'] == r1.loc[p, 'pref'] == orig.loc[p, 'rank_first']]
        print('all three agree on pref for %d of %d' % (len(agree3), len(common)))
        cons = pd.Series([mine.loc[p, 'pref'] for p in agree3]).value_counts().to_dict()
        print('  consensus labels:', cons)
    return rows


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run()
