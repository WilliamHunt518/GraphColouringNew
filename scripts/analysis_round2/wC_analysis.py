#!/usr/bin/env python3
"""Workstream C (round 2) -- the reliance trait, its payoff, and game difficulty / order.

Run from the repo root:
    C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wC_analysis.py

Read-only over Results/ and docs/reports/. Prints every number in docs/analysis/round2/wC_trait_payoff.md
and writes the spec table docs/analysis/round2/wC_specs.csv. No randomness except the seeded cluster
bootstrap in C2e (SEED below). Data layer: wC_common.py (round-1 loaders + PC1 without bootstrap).

Variants (menu = HYPOTHESES_ROUND2.md §4 C + the 2026-10-07 amendment; extras X1, X2 pre-logged in the report):
  C1  what predicts the reliance axis (person level, Spearman; plus a joint OLS)
  C2  throughput: reliance -> missions never allocated / queue time / unallocated points, within and
      between person, game + run fixed; payoff on all four performance metrics and how much of the
      between-person payoff unallocated work carries
  C3  three-type vs single-type: card vs manual on completion and decision time, within person
  C4  single-type: is manual better?
  C5  penalty per mission, card vs manual, within person
  D   difficulty and order: per-game descriptives; game + run models; scenario x run; S-27; S-s1; S-6
  X1  session-2 PC1 ~ session-1 failures | session-1 PC1           (extra)
  X2  first-two-minutes performance as the early allocation share  (extra)
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
warnings.simplefilter('ignore')
import wC_common as W  # noqa: E402

pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 40)
OUT = W.BASE / 'docs' / 'analysis' / 'round2' / 'wC_specs.csv'
SEED = 20261007
COLS = ['workstream', 'variant_id', 'extra', 'description', 'sample', 'outcome', 'predictor', 'model',
        'estimate', 'ci_lo', 'ci_hi', 'estimate_scale', 'p', 'n_obs', 'n_people', 'expected_direction',
        's1_same_direction', 'both_orders_same_direction', 'loo_sign_flip', 'notes']
ROWS = []


def hdr(t):
    print('\n' + '=' * 110 + '\n' + t + '\n' + '=' * 110)


def sgn(x):
    return 0 if (x is None or not np.isfinite(x)) else int(np.sign(x))


def same(a, b):
    if sgn(a) == 0 or sgn(b) == 0:
        return 'na'
    return '1' if sgn(a) == sgn(b) else '0'


def safe(fn, df):
    try:
        v = fn(df)
        return float(v) if v is not None and np.isfinite(v) else np.nan
    except Exception:
        return np.nan


def gates(fn, df, est, s1_fn=None, split='order', loo=True):
    """fn(df) -> estimate. Returns (s1, both, loo_flip, note)."""
    s1 = same(est, safe(s1_fn, df)) if s1_fn is not None else 'na'
    if split is None:
        both, bnote = 'na', ''
    else:
        parts = {g: safe(fn, d) for g, d in df.groupby(split)}
        both = '1' if all(same(est, v) == '1' for v in parts.values()) else (
            'na' if any(not np.isfinite(v) for v in parts.values()) else '0')
        bnote = ' %s: ' % split + ', '.join('%s %.3g' % (k, v) for k, v in parts.items())
    if loo:
        ests = [safe(fn, df[df.pid != p]) for p in sorted(df.pid.unique())]
        ests = np.array([e for e in ests if np.isfinite(e)])
        flip = '1' if (ests.size and np.any(np.sign(ests) != np.sign(est))) else '0'
        lnote = ' LOO range [%.3g, %.3g]' % (ests.min(), ests.max()) if ests.size else ''
    else:
        flip, lnote = 'na', ''
    return s1, both, flip, (bnote + ';' + lnote).strip(' ;')


def add(variant, desc, sample, outcome, predictor, model, est, lo, hi, scale, p, n_obs, n_people,
        expected, s1='na', both='na', loo='na', notes='', extra=0):
    ROWS.append(dict(workstream='C', variant_id=variant, extra=extra, description=desc, sample=sample,
                     outcome=outcome, predictor=predictor, model=model, estimate=est, ci_lo=lo, ci_hi=hi,
                     estimate_scale=scale, p=p, n_obs=n_obs, n_people=n_people,
                     expected_direction=expected, s1_same_direction=s1,
                     both_orders_same_direction=both, loo_sign_flip=loo, notes=notes))
    star = '*' if (p is not None and np.isfinite(p) and p < .05) else ' '
    print('%s %-5s %-7s %-22s ~ %-22s %8.3f [%8.3f, %8.3f] %-4s p=%6.3f n=%4s/%2s exp %s | s1 %s orders %s looflip %s | %s'
          % (star, variant, sample, outcome[:22], predictor[:22], est, lo if lo is not None else np.nan,
             hi if hi is not None else np.nan, scale, p if p is not None else np.nan, n_obs, n_people,
             expected, s1, both, loo, notes[:150]))


# ── helpers ─────────────────────────────────────────────────────────────────────────────────

def spearman(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    r, p = stats.spearmanr(x[m], y[m])
    n = int(m.sum())
    z, se = np.arctanh(r), 1 / np.sqrt(max(n - 3, 1))
    return float(r), float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se)), float(p), n


def gee_term(df, formula, name, fam='gaussian'):
    """Fit; terms (other than `name`) that are constant in this subsample are dropped first, so the
    same formula can be refitted within a scenario or order group."""
    lhs, rhs = formula.split('~')
    keep = []
    for t in rhs.split('+'):
        t = t.strip()
        if t != name and t in df.columns and df[t].nunique() < 2:
            continue
        keep.append(t)
    # within one order group, scenario and run are the same split (and C(game) spans scenario): drop
    # the redundant nuisance term so the subgroup estimate is identified rather than arbitrary
    import patsy
    for drop in ('run2', 'tact_c', 'run2_c'):
        X = patsy.dmatrix(' + '.join(keep), df, return_type='dataframe')
        if np.linalg.matrix_rank(X.values) == X.shape[1]:
            break
        if drop != name and drop in keep:
            keep = [k for k in keep if k != drop]
    X = patsy.dmatrix(' + '.join(keep), df, return_type='dataframe')
    if np.linalg.matrix_rank(X.values) < X.shape[1]:
        raise ValueError('rank deficient: ' + ' + '.join(keep))
    m = W.gee('%s ~ %s' % (lhs.strip(), ' + '.join(keep)), df, fam)
    return W.term(m, name)


def wb(df, col):
    df = df.copy()
    df[col + '_b'] = df.groupby('pid')[col].transform('mean')
    df[col + '_w'] = df[col] - df[col + '_b']
    return df


def pm(df, col):
    df = df.copy()
    df[col + '_pm'] = df.groupby('pid')[col].transform('mean')
    return df


# ── C1 · predictors of the reliance axis ────────────────────────────────────────────────────

def c1(P):
    hdr('C1 -- what predicts position on the reliance axis (PC1, SD units)')
    preds = [('gaming', 'gaming frequency (0 never - 4 daily)', 'none', 0),
             ('experience', 'prior experience (mean of 5 items, 0-3)', 'none', 0),
             ('early_pts_z', 'session-1 score at 120 s (game z)', '+', 0),
             ('s1_fail_z', 'session-1 drone failures (game z)', '-', 0),
             ('s1_aband', 'session-1 missions abandoned', '-', 0),
             ('early_alloc', 'session-1 share of first-120-s missions allocated by 120 s (game-centred)', '+', 1)]
    print(P[['PC1', 'gaming', 'experience', 'early_pts_z', 's1_fail_z', 's1_aband', 'early_alloc']].describe().round(2))
    print('score at 120 s is exactly 0 in %d of 33 session-1s' % int((W.load()[0].query('run==1').pts_early == 0).sum()))
    for x, lab, exp, extra in preds:
        vid = 'X2' if extra else 'C1'
        fn = lambda d, x=x: spearman(d[x].values, d['PC1'].values)[0]
        s1fn = lambda d, x=x: spearman(d[x].values, d['s1_PC1'].values)[0]
        r, lo, hi, p, n = spearman(P[x].values, P['PC1'].values)
        s1, both, loo, note = gates(fn, P, r, s1fn)
        add(vid, 'PC1 ~ ' + lab, 'S-all', 'PC1 (pooled)', x, 'Spearman', r, lo, hi, 'rho', p, n, n, exp,
            s1, both, loo, note, extra)
        V = W.sample(P, 'S-v112')
        r, lo, hi, p, n = spearman(V[x].values, V['PC1'].values)
        add(vid, 'PC1 ~ ' + lab, 'S-v112', 'PC1 (pooled)', x, 'Spearman', r, lo, hi, 'rho', p, n, n, exp,
            notes='sensitivity', extra=extra)
        r, lo, hi, p, n = spearman(P[x].values, P['s1_PC1'].values)
        add(vid, 'session-1 PC1 ~ ' + lab, 'S-s1', 'PC1 (session 1)', x, 'Spearman', r, lo, hi, 'rho', p, n, n,
            exp, notes='session-1 projection on the pooled axis', extra=extra)
    # joint model
    d = P.dropna(subset=['gaming', 'experience', 'early_pts_z', 's1_fail_z'])
    f = 'PC1 ~ gaming + experience + early_pts_z + s1_fail_z'
    m = smf.ols(f, d).fit(cov_type='HC3')
    print('\njoint OLS (HC3):', f, ' R2 = %.3f, adj R2 = %.3f, F p = %.3f' % (m.rsquared, m.rsquared_adj, m.f_pvalue))
    for t, exp in (('gaming', 'none'), ('experience', 'none'), ('early_pts_z', '+'), ('s1_fail_z', '-')):
        fn = lambda dd, t=t: smf.ols(f, dd).fit().params[t]
        s1fn = lambda dd, t=t: smf.ols(f.replace('PC1', 's1_PC1'), dd).fit().params[t]
        lo, hi = m.conf_int().loc[t]
        s1, both, loo, note = gates(fn, d, m.params[t], s1fn)
        add('C1', 'joint OLS ' + f, 'S-all', 'PC1 (pooled)', t, 'OLS HC3', m.params[t], lo, hi, 'b',
            m.pvalues[t], len(d), len(d), exp, s1, both, loo, note + '; model R2 %.2f' % m.rsquared)
    # X1: does session-1 experience move session-2 reliance?
    hdr('X1 -- session-2 PC1 ~ session-1 failures, holding session-1 PC1 (extra)')
    for x, exp in (('s1_fail_z', '-'), ('s1_aband', '-')):
        f = 's2_PC1 ~ %s + s1_PC1' % x
        m = smf.ols(f, P).fit(cov_type='HC3')
        fn = lambda dd, f=f, x=x: smf.ols(f, dd).fit().params[x]
        s1_, both, loo, note = gates(fn, P, m.params[x])
        lo, hi = m.conf_int().loc[x]
        add('X1', 'change in reliance: ' + f, 'S-all', 'PC1 (session 2)', x, 'OLS HC3', m.params[x], lo, hi,
            'b', m.pvalues[x], len(P), len(P), exp, 'na', both, loo, note, extra=1)


# ── C2 · throughput ─────────────────────────────────────────────────────────────────────────

THRU = [('unallocMissions', 'genuine missions never allocated (count)', '-'),
        ('queue_mean', 'mean arrival->allocation time, buzzer-censored (s)', '-'),
        ('unallocPts_eff', 'points left on never-allocated missions / points on offer', '-')]
PERF = [('eff', 'score efficiency (score / points on offer)'),
        ('z', 'per-game z-score'),
        ('bshare', 'share of near-perfect benchmark (T2 unreliable)'),
        ('best', 'share of best human score on the game')]


def c2(S):
    hdr('C2 -- throughput: does reliance pay through getting more missions allocated?')
    print('session means by scenario:')
    print(S.groupby('scenario')[['n_arrived', 'n_alloc', 'unallocMissions', 'queue_mean', 'unallocPts_eff',
                                 'n_abandoned', 'n_requeued']].mean().round(2))
    print('missions abandoned (re-queued as <id>-R, counted as transferred, not lost): total %d, tasks re-queued %d'
          % (S.n_abandoned.sum(), S.n_requeued.sum()))
    for rel, rlab, vid, xtra in (('uptake', 'card uptake', 'C2', 0), ('sPC1', 'session PC1', 'C2', 0),
                                 ('sPC1_nos', 'session PC1 without decision speed', 'X3', 1)):
        for y, ylab, exp in THRU:
            f = '%s ~ %s_w + %s_b + C(game) + run2' % (y, rel, rel)
            d = wb(S.dropna(subset=[y, rel]), rel)
            for comp in ('w', 'b'):
                name = '%s_%s' % (rel, comp)
                r = gee_term(d, f, name)
                fn = lambda dd, f=f, name=name, rel=rel: gee_term(wb(dd, rel), f, name)['est']
                s1fn = (lambda dd, y=y, rel=rel: gee_term(dd[dd.run == 1], '%s ~ %s + C(game)' % (y, rel), rel)['est']) \
                    if comp == 'b' else None
                s1, both, loo, note = gates(fn, d, r['est'], s1fn)
                add(vid, '%s ~ %s (%s person), game FE + run' % (ylab, rlab, 'within' if comp == 'w' else 'between'),
                    'S-all', y, name, 'GEE gaussian exch, bias-reduced', r['est'], r['lo'], r['hi'], 'b', r['p'],
                    r['n_obs'], d.pid.nunique(), exp, s1, both, loo, note, extra=xtra)
            # v112 and S-27 sensitivity for uptake only
            if rel == 'uptake':
                for smp in ('S-v112', 'S-27'):
                    dd = wb(W.sample(S, smp).dropna(subset=[y]), rel)
                    for comp in ('w', 'b'):
                        name = '%s_%s' % (rel, comp)
                        try:
                            r = gee_term(dd, f, name)
                        except Exception:
                            continue
                        add('C2', '%s ~ %s (%s), game FE + run' % (ylab, rlab, comp), smp, y, name,
                            'GEE gaussian exch, bias-reduced', r['est'], r['lo'], r['hi'], 'b', r['p'], r['n_obs'],
                            dd.pid.nunique(), exp, notes='sensitivity' + ('; in S-27 run = game index' if smp == 'S-27' else ''))

    hdr('C2e -- the payoff on all four performance metrics, and how much of it unallocated work carries')
    rng = np.random.default_rng(SEED)
    d0 = wb(S, 'uptake')
    pids = np.array(sorted(d0.pid.unique()))
    for y, ylab in PERF:
        base = '%s ~ uptake_w + uptake_b + C(game) + run2' % y
        med = base + ' + unallocPts_eff'
        for comp, exp in (('w', '+'), ('b', '+')):
            name = 'uptake_' + comp
            r = gee_term(d0, base, name)
            fn = lambda dd, name=name, base=base: gee_term(wb(dd, 'uptake'), base, name)['est']
            s1fn = (lambda dd, y=y: gee_term(dd[dd.run == 1], '%s ~ uptake + C(game)' % y, 'uptake')['est']) if comp == 'b' else None
            s1, both, loo, note = gates(fn, d0, r['est'], s1fn)
            add('C2', '%s ~ card uptake (%s person), game FE + run' % (ylab, 'within' if comp == 'w' else 'between'),
                'S-all', y, name, 'GEE gaussian exch, bias-reduced', r['est'], r['lo'], r['hi'], 'b', r['p'],
                r['n_obs'], 33, exp, s1, both, loo, note + ('; bshare unreliable on tactical|2' if y == 'bshare' else ''))
        # mediation share of the between-person term (OLS point estimates; person-cluster bootstrap)
        def share(dd):
            dd = wb(dd, 'uptake')
            b0 = smf.ols(base, dd).fit().params['uptake_b']
            b1 = smf.ols(med, dd).fit().params['uptake_b']
            return (b0 - b1) / b0 if b0 != 0 else np.nan, b0, b1
        est, b0, b1 = share(d0)
        boots = []
        for _ in range(1000):
            pick = rng.choice(pids, len(pids), replace=True)
            bd = pd.concat([d0[d0.pid == p].assign(pid='%s_%d' % (p, i)) for i, p in enumerate(pick)])
            try:
                boots.append(share(bd)[0])
            except Exception:
                pass
        boots = np.array([b for b in boots if np.isfinite(b)])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        pb = float(min(1, 2 * min((boots <= 0).mean(), (boots >= 0).mean())))
        rm = gee_term(d0, med, 'unallocPts_eff')
        print('   %s: between b %.3f -> %.3f with unallocated-points share; mediated share %.2f [%.2f, %.2f]; '
              'unallocPts_eff b %.3f [%.3f, %.3f] p %.3f'
              % (y, b0, b1, est, lo, hi, rm['est'], rm['lo'], rm['hi'], rm['p']))
        fn = lambda dd: share(dd)[0]
        s1, both, loo, note = gates(fn, d0, est, None, split='order')
        add('C2', 'share of the between-person uptake->%s link removed by adding unallocated-points share'
            % ylab, 'S-all', y, 'uptake_b (attenuation)', 'OLS point est., person-cluster bootstrap 1000',
            est, lo, hi, 'diff', pb, len(d0), 33, '+', 'na', both, loo,
            note + '; b_between %.3f -> %.3f' % (b0, b1))


# ── C3-C5 · decision level ──────────────────────────────────────────────────────────────────

def dec_fit(df, y, x, fam, extra_terms='+ ndrones + C(game) + time_left'):
    d = pm(df.dropna(subset=[y]), x)
    return gee_term(d, '%s ~ %s + %s_pm %s' % (y, x, x, extra_terms), x, fam), d


def dec_row(variant, desc, D, sample, y, x, fam, exp, extra_terms='+ ndrones + C(game) + time_left'):
    try:
        r, d = dec_fit(D, y, x, fam, extra_terms)
    except Exception as e:
        print('   fit failed', variant, desc, e)
        return
    fn = lambda dd: dec_fit(dd, y, x, fam, extra_terms)[0]['est']
    s1fn = lambda dd: dec_fit(dd[dd.run == 1], y, x, fam, extra_terms)[0]['est']
    s1, both, loo, note = gates(fn, d, r['est'], s1fn) if sample == 'S-all' else ('na', 'na', 'na', 'sensitivity')
    if fam == 'binomial':
        est, lo, hi, scale = np.exp(r['est']), np.exp(r['lo']), np.exp(r['hi']), 'OR'
    else:
        est, lo, hi, scale = r['est'], r['lo'], r['hi'], 'b'
    raw = d.groupby(x)[y].mean()
    add(variant, desc, sample, y, x + ' (within person)', 'GEE %s exch, bias-reduced; %s_pm Mundlak %s' % (fam, x, extra_terms),
        est, lo, hi, scale, r['p'], r['n_obs'], d.pid.nunique(), exp, s1, both, loo,
        note + '; raw mean %s=0: %.3g, =1: %.3g' % (x, raw.get(0, np.nan), raw.get(1, np.nan)))


def c3_c5(D):
    hdr('C3 -- three-type vs single-type missions: card vs manual, within person')
    D = D.copy()
    D['log_net'] = np.log1p(D.net_secs)
    D['val_share'] = D.net / D.max_points.replace(0, np.nan)
    D['pen_share'] = D.penalty / D.max_points.replace(0, np.nan)
    three, single = D[D.ncolours == 3], D[D.ncolours == 1]
    print('decisions: three-type %d (card %.2f), single-type %d (card %.2f), two-type %d'
          % (len(three), three.took.mean(), len(single), single.took.mean(), (D.ncolours == 2).sum()))
    print('median net decision time (s) by type x route:')
    print(D.groupby(['ncolours', 'took']).net_secs.median().round(1))
    for sub, lab in ((three, 'three-type'), (single, 'single-type')):
        exp_full = '+' if lab == 'three-type' else 'none'
        dec_row('C3', '%s missions: full completion, card vs manual' % lab, sub, 'S-all', 'full', 'took', 'binomial', exp_full)
        dec_row('C3', '%s missions: full completion, card vs manual' % lab, W.sample(sub, 'S-v112'), 'S-v112', 'full', 'took', 'binomial', exp_full)
        dec_row('C3', '%s missions: log(1 + decision time beyond the forced reveal), card vs manual' % lab, sub,
                'S-all', 'log_net', 'took', 'gaussian', '-' if lab == 'three-type' else 'none',
                extra_terms='+ ndrones + C(game) + elapsed')
        dec_row('C3', '%s missions: full completion following abandoned work into its residual' % lab, sub,
                'S-all', 'chain_full', 'took', 'binomial', exp_full)
    # interaction: does the card's effect differ by type?
    for y, fam, exp in (('full', 'binomial', '+'), ('log_net', 'gaussian', '-')):
        d = pm(D[D.ncolours.isin([1, 3])].dropna(subset=[y]), 'took')
        d['three'] = (d.ncolours == 3).astype(int)
        f = '%s ~ took * three + took_pm + ndrones + C(game) + %s' % (y, 'time_left' if y == 'full' else 'elapsed')
        r = gee_term(d, f, 'took:three', fam)
        fn = lambda dd, f=f, fam=fam: gee_term(pm(dd, 'took'), f, 'took:three', fam)['est']
        s1fn = lambda dd, f=f, fam=fam: gee_term(pm(dd[dd.run == 1], 'took'), f, 'took:three', fam)['est']
        s1, both, loo, note = gates(fn, d, r['est'], s1fn)
        est, lo, hi, sc = (np.exp(r['est']), np.exp(r['lo']), np.exp(r['hi']), 'OR') if fam == 'binomial' else (r['est'], r['lo'], r['hi'], 'b')
        add('C3', 'card x three-type interaction on %s (does the card pay more on three-type missions)' % y, 'S-all', y,
            'took:three', 'GEE %s exch, bias-reduced' % fam, est, lo, hi, sc, r['p'], r['n_obs'], d.pid.nunique(),
            exp, s1, both, loo, note)

    hdr('C4 -- opposite: on single-type missions, does manual do better?')
    for y, fam, lab in (('full', 'binomial', 'full completion'), ('chain_full', 'binomial', 'completion following residuals'),
                        ('val_share', 'gaussian', 'net value / points on offer')):
        dec_row('C4', 'single-type missions: %s, manual vs card' % lab, single, 'S-all', y, 'manual', fam, '+')
    dec_row('C4', 'single-type missions: full completion, manual vs card', W.sample(single, 'S-v112'), 'S-v112',
            'full', 'manual', 'binomial', '+')

    hdr('C5 -- penalty accrued per mission, card vs manual, within person')
    for y, lab in (('penalty', 'penalty points accrued by the mission'), ('pen_share', 'penalty / points on offer')):
        dec_row('C5', '%s, card vs manual' % lab, D, 'S-all', y, 'took', 'gaussian', '-',
                extra_terms='+ ncolours + ndrones + C(game) + time_left')
        dec_row('C5', '%s, card vs manual' % lab, W.sample(D, 'S-v112'), 'S-v112', y, 'took', 'gaussian', '-',
                extra_terms='+ ncolours + ndrones + C(game) + time_left')
    dec_row('C5', 'penalty, card vs manual, genuine missions only', D[D.residual == 0], 'S-all', 'penalty', 'took',
            'gaussian', '-', extra_terms='+ ncolours + ndrones + C(game) + time_left')


# ── D · difficulty and order ────────────────────────────────────────────────────────────────

DOUT = [('eff', 'score efficiency', 'perf'), ('z', 'per-game z-score', 'perf'),
        ('bshare', 'benchmark share (T2 unreliable)', 'perf'), ('best', 'share of best human', 'perf'),
        ('unallocMissions', 'missions never allocated', 'thru'), ('queue_mean', 'censored queue time (s)', 'thru'),
        ('uptake', 'card uptake', 'rel'), ('tac_consult', 'tactical Suggest consulted', 'rel'),
        ('sPC1_raw', 'session reliance score (uncentred PC1)', 'rel')]


def coded(S):
    S = S.copy()
    c = np.where(S.planIndex == 2, .5, -.5)
    S['idx_s'] = (1 - S.tact) * c   # S2 - S1
    S['idx_t'] = S.tact * c         # T2 - T1
    S['tact_c'] = S.tact - .5
    S['run2_c'] = S.run2 - .5
    return S


def difficulty(S):
    hdr('D -- how hard was each game, and game vs order vs scenario')
    S = coded(S)
    bench = pd.read_json(W.BASE / 'docs' / 'reports' / 'smart_benchmark.json')['games']
    bf = {(g['complexity'], g['planIndex']): g['failures'] for g in bench}
    tab = S.groupby('game').agg(n=('pid', 'size'), n_run1=('run', lambda r: int((r == 1).sum())),
                                on_offer=('avail_r', 'mean'), arrived=('n_arrived', 'mean'),
                                score=('score_r', 'mean'), score_sd=('score_r', 'std'), eff=('eff', 'mean'),
                                bshare=('bshare', 'mean'), best_human=('score_r', 'max'), best_share=('best', 'mean'),
                                unalloc=('unallocMissions', 'mean'), queue=('queue_mean', 'mean'),
                                failures=('failures', 'mean'), uptake=('uptake', 'mean'),
                                consult=('tac_consult', 'mean'))
    tab['bench_failures'] = [bf[(g.split('|')[0], int(g.split('|')[1]))] for g in tab.index]
    print(tab.round(3).to_string())
    print('\nby game x run (mean eff / unalloc / uptake, n):')
    print(S.groupby(['game', 'run']).agg(n=('pid', 'size'), eff=('eff', 'mean'), z=('z', 'mean'),
                                         unalloc=('unallocMissions', 'mean'), uptake=('uptake', 'mean'),
                                         consult=('tac_consult', 'mean')).round(3).to_string())
    print('\nS-6 (swapped) per person:')
    print(W.sample(S, 'S-6')[['pid', 'run', 'game', 'order', 'eff', 'z', 'best', 'unallocMissions', 'uptake',
                              'tac_consult']].round(3).to_string(index=False))

    terms_m2 = [('tact_c', 'scenario: Tactical - Strategic (avg over games)'), ('idx_s', 'game: S2 - S1'),
                ('idx_t', 'game: T2 - T1'), ('run2', 'run 2 - run 1 (order / practice)')]
    for y, ylab, kind in DOUT:
        d = S.dropna(subset=[y])
        f2 = '%s ~ tact_c + idx_s + idx_t + run2' % y
        exp = {'perf': {'tact_c': 'none', 'idx_s': 'none', 'idx_t': 'none', 'run2': '+'},
               'thru': {'tact_c': '-', 'idx_s': 'none', 'idx_t': 'none', 'run2': '-'},
               'rel': {'tact_c': 'none', 'idx_s': 'none', 'idx_t': 'none', 'run2': 'none'}}[kind]
        if y == 'unallocMissions':
            exp['tact_c'] = '-'  # Strategic Heavy has more missions -> more never allocated (round 1)
        for t, tl in terms_m2:
            if y == 'z' and t != 'run2':
                continue  # z is standardised within game: scenario and game terms are 0 by construction
            r = gee_term(d, f2, t)
            fn = lambda dd, t=t, f2=f2: gee_term(dd, f2, t)['est']
            s1fn = None
            if t != 'run2':
                s1fn = lambda dd, t=t, y=y: gee_term(dd[dd.run == 1], '%s ~ tact_c + idx_s + idx_t' % y, t)['est']
            split = 'order' if t != 'run2' else 'scenario'
            s1, both, loo, note = gates(fn, d, r['est'], s1fn, split=split)
            add('D2', '%s ~ scenario + game index within scenario + run (game + order in one model): %s' % (ylab, tl),
                'S-all', y, t, 'GEE gaussian exch, bias-reduced', r['est'], r['lo'], r['hi'], 'b', r['p'], r['n_obs'],
                d.pid.nunique(), exp[t], s1, both, loo,
                note + ('; both-orders column = same direction within each scenario' if t == 'run2' else '')
                + ('; run vs game index separated only by the 6 swapped' if t in ('run2', 'idx_s', 'idx_t') else ''))
            if t in ('tact_c', 'run2'):
                dv = W.sample(d, 'S-v112')
                try:
                    rv = gee_term(dv, f2, t)
                    add('D2', '%s: %s' % (ylab, tl), 'S-v112', y, t, 'GEE gaussian exch, bias-reduced', rv['est'], rv['lo'],
                        rv['hi'], 'b', rv['p'], rv['n_obs'], dv.pid.nunique(), exp[t], notes='sensitivity')
                except Exception:
                    pass
        # scenario x run interaction (does the order/practice effect differ by scenario = game x order)
        f3 = '%s ~ tact_c * run2_c + idx_s + idx_t' % y
        r = gee_term(d, f3, 'tact_c:run2_c')
        fn = lambda dd, f3=f3: gee_term(dd, f3, 'tact_c:run2_c')['est']
        s1, both, loo, note = gates(fn, d, r['est'], None, split=None)
        add('D3', '%s: scenario x run interaction (combination of scenario and order)' % ylab, 'S-all', y,
            'tact_c:run2_c', 'GEE gaussian exch, bias-reduced', r['est'], r['lo'], r['hi'], 'b', r['p'], r['n_obs'],
            d.pid.nunique(), 'none', 'na', 'na', loo, note + '; + = practice gain larger in Tactical Heavy')
        # S-27: order and game pairing coincide (run 2 = game index 2)
        d27 = W.sample(d, 'S-27')
        f27 = '%s ~ tact_c + run2' % y
        for t, tl in (('tact_c', 'scenario T - S'), ('run2', 'run 2 - run 1 (= order + pairing; = game index 2)')):
            if y == 'z' and t != 'run2':
                continue
            r = gee_term(d27, f27, t)
            fn = lambda dd, t=t: gee_term(dd, f27, t)['est']
            s1, both, loo, note = gates(fn, d27, r['est'], None, split='order' if t == 'tact_c' else 'scenario')
            add('D4', '%s on S-27: %s' % (ylab, tl), 'S-27', y, t, 'GEE gaussian exch, bias-reduced', r['est'], r['lo'],
                r['hi'], 'b', r['p'], r['n_obs'], d27.pid.nunique(), exp[t], 'na', both, loo, note)
        # S-s1: between-person, no order
        if y != 'z':
            d1 = d[d.run == 1]
            r = gee_term(d1, '%s ~ tact_c + idx_s + idx_t' % y, 'tact_c')
            add('D5', '%s, session 1 only: scenario T - S (between person, game index adjusted; S2/T2 n = 3 each)' % ylab,
                'S-s1', y, 'tact_c', 'GEE (1 obs/cluster = robust OLS), bias-reduced', r['est'], r['lo'], r['hi'], 'b',
                r['p'], r['n_obs'], d1.pid.nunique(), exp['tact_c'])
        # S-6 descriptive: the one place run and game separate
        d6 = W.sample(d, 'S-6')
        run_diff = d6[d6.run == 2][y].mean() - d6[d6.run == 1][y].mean()
        tac_diff = d6[d6.tact == 1][y].mean() - d6[d6.tact == 0][y].mean()
        add('D6', '%s, swapped six: run 2 - run 1 mean (descriptive)' % ylab, 'S-6', y, 'run2', 'mean difference',
            run_diff, None, None, 'diff', None, len(d6), 6, exp['run2'],
            notes='descriptive only; compare D2 run2 and D4 run2. T - S in S-6 = %.3g' % tac_diff)


def main():
    S, D, P = W.load()
    hdr('DATA')
    _, _, load, var = W.reliance_axis()
    print('participants %d, sessions %d, strategic decisions %d; PC1 explains %.1f%%, loadings %s'
          % (P.pid.nunique(), len(S), len(D), 100 * var, load))
    print('P01/P02 rescaled to current task weights (2 x points - penalty), not excluded')
    c1(P)
    c2(S)
    c3_c5(D)
    difficulty(S)
    out = pd.DataFrame(ROWS)[COLS]
    for c in ('estimate', 'ci_lo', 'ci_hi', 'p'):
        out[c] = pd.to_numeric(out[c], errors='coerce').round(5)
    out.to_csv(OUT, index=False)
    print('\nwrote %s (%d rows)' % (OUT.relative_to(W.BASE), len(out)))
    print('rows with p < .05: %d; p < .01: %d' % ((out.p < .05).sum(), (out.p < .01).sum()))


if __name__ == '__main__':
    main()
