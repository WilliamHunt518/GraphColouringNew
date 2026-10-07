#!/usr/bin/env python3
"""Round 2 · workstream G · learning and calibration across the sessions.

Runs the whole G menu (HYPOTHESES_ROUND2.md §4 G1–G4) plus three pre-stated extras (X1–X3),
prints every result, and writes `docs/analysis/round2/wG_specs.csv`. Read-only over Results/.

    C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wG_learning.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.discrete.conditional_models import ConditionalLogit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wG_common as C  # noqa: E402

OUT = C.ROOT / 'docs' / 'analysis' / 'round2' / 'wG_specs.csv'
COLS = ['workstream', 'variant_id', 'extra', 'description', 'sample', 'outcome', 'predictor', 'model',
        'estimate', 'ci_lo', 'ci_hi', 'estimate_scale', 'p', 'n_obs', 'n_people', 'expected_direction',
        's1_same_direction', 'both_orders_same_direction', 'loo_sign_flip', 'notes']
ROWS = []


def sgn(x):
    return 0 if (x is None or not np.isfinite(x)) else int(np.sign(x))


def same(a, b):
    """gate: 1 if a has the same (non-zero) sign as b."""
    if a is None or not np.isfinite(a):
        return 'na'
    return int(sgn(a) == sgn(b) and sgn(b) != 0)


def record(vid, extra, desc, sample, outcome, predictor, model, b, lo, hi, scale, p, n_obs, n_people,
           expected, s1='na', orders='na', flip='na', notes=''):
    tr = np.exp if scale == 'OR' else (lambda v: v)
    row = dict(workstream='G', variant_id=vid, extra=int(extra), description=desc, sample=sample,
               outcome=outcome, predictor=predictor, model=model,
               estimate=round(float(tr(b)), 4), ci_lo=None if lo is None else round(float(tr(lo)), 4),
               ci_hi=None if hi is None else round(float(tr(hi)), 4), estimate_scale=scale,
               p=None if p is None else round(float(p), 5), n_obs=n_obs, n_people=n_people,
               expected_direction=expected, s1_same_direction=s1,
               both_orders_same_direction=orders, loo_sign_flip=flip, notes=notes)
    ROWS.append(row)
    ci = '' if lo is None else '[%.3f, %.3f]' % (tr(lo), tr(hi))
    print('%-7s %-58s %-7s %s=%.3f %s p=%s n=%s/%s exp=%s s1=%s ord=%s flip=%s %s'
          % (vid, desc[:58], sample, scale, tr(b), ci, 'na' if p is None else '%.4f' % p, n_obs, n_people,
             expected, s1, orders, flip, notes))


def gee_variant(vid, desc, sample, data, formula, term, expected, binomial=True, extra=False,
                s1=None, orders=True, do_loo=True, outcome=None, predictor=None, notes=''):
    """Fit one GEE variant and its gates.
    s1: None -> 'na'; or (formula, data) -- the session-1-only analogue (sign compared).
    orders: refit inside each scenario order (factors collinear there are reduced)."""
    f = C.reduce_formula(formula, data)
    r = C.est(f, data, term, binomial)
    b = r['b']
    s1g = 'na'
    if s1 is not None:
        s1g = same(C.point(s1[0], s1[1], term, binomial), b)
    og, onote = 'na', ''
    if orders:
        ests = {o: C.point(formula, data[data.order == o], term, binomial)
                for o in ('strategic', 'tactical')}
        if all(np.isfinite(v) for v in ests.values()):
            og = int(all(sgn(v) == sgn(b) for v in ests.values()))
        tr = np.exp if binomial else (lambda v: v)
        onote = 'by order (S-first, T-first): %s; ' % ', '.join(
            'nan' if not np.isfinite(v) else '%.3f' % tr(v) for v in ests.values())
    flip, lnote = 'na', ''
    if do_loo:
        L = C.loo(formula, data, term, binomial)
        L = L[np.isfinite(L)]
        flip = int(any(sgn(v) != sgn(b) for v in L))
        tr = np.exp if binomial else (lambda v: v)
        lnote = 'LOO range %.3f-%.3f; ' % (tr(L.min()), tr(L.max()))
    if f != formula:
        onote += 'formula reduced to: %s; ' % f
    record(vid, extra, desc, sample, outcome or formula.split('~')[0].strip(), predictor or term,
           'GEE %s exch, bias_reduced: %s' % ('logit' if binomial else 'gaussian', f),
           b, r['lo'], r['hi'], 'OR' if binomial else 'b', r['p'], r['n_obs'], r['n_people'],
           expected, s1g, og, flip, (onote + lnote + notes).strip('; '))
    return r


# ── G1 · calibration ──────────────────────────────────────────────────────────────────────────
def g1(S):
    print('\n=== G1 · calibration: composition x run on card-taking ===')
    print('raw uptake by scenario x run x composition:')
    print(S.groupby(['scenario', 'run', 'multi']).took.agg(['mean', 'size']).round(3).to_string())
    S27, S6, Sv = S[S.swapped == 0], S[S.swapped == 1], S[S.v112 == 1]
    base = 'took ~ multi*run2 + ndrones + C(scenario)'
    gee_variant('G1.1', 'composition x run2, scenario adjusted', 'S-all', S, base, 'multi:run2', '+')
    gee_variant('G1.2', 'composition x run2, game fixed effect', 'S-all', S,
                'took ~ multi*run2 + ndrones + C(game)', 'multi:run2', '+')
    # Single-type missions are almost absent from Tactical Heavy games, so game-specific composition
    # slopes are only estimable inside Strategic Heavy: there, run2 vs game index is separated only
    # by the six swapped people (S1 first + S2 second for everyone else).
    gee_variant('G1.3', 'composition x run2 in Strategic Heavy, game-specific slopes (S-6 identifies)',
                'S-all', S[S.scenario == 'strategic'],
                'took ~ multi*run2 + multi:C(planIndex) + ndrones + C(planIndex)', 'multi:run2', '+',
                orders=False, notes='sample = Strategic Heavy sessions')
    g1_condlogit(S)
    gee_variant('G1.5', 'composition x run2, scenario adjusted', 'S-v112', Sv, base, 'multi:run2', '+')
    gee_variant('G1.6', 'composition x run2 (order + pairing)', 'S-27', S27, base, 'multi:run2', '+')
    # S-6 descriptive diff-in-diff
    t = S6.groupby(['run', 'multi']).took.mean()
    did = (t[(2, 1)] - t[(2, 0)]) - (t[(1, 1)] - t[(1, 0)])
    record('G1.7', 0, 'composition gap (multi - single uptake) run2 minus run1, raw', 'S-6', 'took',
           'multi x run2', 'raw difference in differences (descriptive)', did, None, None, 'diff', None,
           len(S6), S6.pid.nunique(), '+',
           notes='gaps run1 %.3f, run2 %.3f; n single-type run1/run2 = %d/%d'
           % (t[(1, 1)] - t[(1, 0)], t[(2, 1)] - t[(2, 0)],
              ((S6.run == 1) & (S6.multi == 0)).sum(), ((S6.run == 2) & (S6.multi == 0)).sum()))
    for sc, vid in (('strategic', 'G1.8'), ('tactical', 'G1.9')):
        d = S[S.scenario == sc]
        gee_variant(vid, 'composition x run2 within %s scenario (between people, game confounded)' % sc,
                    'S-all', d, 'took ~ multi*run2 + ndrones', 'multi:run2', '+', orders=False,
                    notes='n single-type = %d' % (d.multi == 0).sum())
    gee_variant('G1.10', 'drone count (log) x run2', 'S-all', S,
                'took ~ lsize*run2 + multi + C(scenario)', 'lsize:run2', '+')
    gee_variant('G1.11', 'drone count (log) x run2, three-type missions only', 'S-all',
                S[S.ncolours == 3], 'took ~ lsize*run2 + C(scenario)', 'lsize:run2', '+')
    gee_variant('G1.12', 'composition effect in session 1 only', 'S-s1', S[S.run == 1],
                'took ~ multi + ndrones + C(scenario)', 'multi', '+',
                s1=('took ~ multi + ndrones + C(scenario)', S[S.run == 1]))
    gee_variant('G1.13', 'composition effect in session 2 only', 'S-all', S[S.run == 2],
                'took ~ multi + ndrones + C(scenario)', 'multi', '+',
                s1=('took ~ multi + ndrones + C(scenario)', S[S.run == 1]), notes='sample = session 2 only')
    g1_person(S)


def g1_condlogit(S):
    def fit(d):
        # Game pairing is fixed per person (S1+T2 or S2+T1), so within person the game effect is
        # the scenario contrast inside each pairing: one dummy per tactical game. People who always
        # or never took a card carry no within-person information and are dropped.
        d = d[d.groupby('pid').took.transform('std') > 0]
        X = pd.DataFrame({'gT1': (d.game == 'tactical|1').astype(float),
                          'gT2': (d.game == 'tactical|2').astype(float),
                          'multi': d.multi.astype(float),
                          'multi_run2': (d.multi * d.run2).astype(float),
                          'ndrones': d.ndrones.astype(float)})
        X = X.loc[:, X.std() > 0]
        m = ConditionalLogit(d.took.values.astype(float), X, groups=pd.factorize(d.pid)[0]).fit(disp=0)
        j = list(X.columns).index('multi_run2')
        return float(m.params[j]), float(m.bse[j]), float(m.pvalues[j])
    b, se, p = fit(S)
    ests = []
    for o in ('strategic', 'tactical'):
        try:
            ests.append(fit(S[S.order == o])[0])
        except Exception:
            ests.append(np.nan)
    L = []
    for pid in S.pid.unique():
        try:
            L.append(fit(S[S.pid != pid])[0])
        except Exception:
            pass
    L = np.array(L)
    record('G1.4', 0, 'composition x run2, within person (conditional logit), game dummies', 'S-all',
           'took', 'multi:run2', 'conditional logit on person, + game dummies + ndrones (no GEE)',
           b, b - 1.96 * se, b + 1.96 * se, 'OR', p, len(S), S.pid.nunique(), '+', 'na',
           int(all(sgn(v) == sgn(b) for v in ests)) if all(np.isfinite(ests)) else 'na',
           int(any(sgn(v) != sgn(b) for v in L)),
           'by order: %s; LOO range %.3f-%.3f; only people with both kinds of mission in a session '
           'inform it' % (', '.join('%.3f' % np.exp(v) for v in ests), np.exp(L.min()), np.exp(L.max())))


def g1_person(S):
    g = S.groupby(['pid', 'run', 'multi']).took.mean().unstack('multi')
    gap = (g[1] - g[0]).unstack('run').dropna()
    delta = gap[2] - gap[1]
    order = S.groupby('pid').order.first().loc[delta.index]
    w = stats.wilcoxon(delta) if len(delta) >= 5 else None
    m, se = delta.mean(), delta.std(ddof=1) / np.sqrt(len(delta))
    tcrit = stats.t.ppf(.975, len(delta) - 1)
    o = {k: delta[order == k].mean() for k in ('strategic', 'tactical')}
    L = np.array([delta.drop(p).mean() for p in delta.index])
    record('G1.14', 0, 'per-person change in composition gap (multi - single uptake), run2 - run1',
           'S-all', 'took', 'run2 change in gap', 'person-level mean, Wilcoxon signed-rank p',
           m, m - tcrit * se, m + tcrit * se, 'diff', None if w is None else w.pvalue,
           int(S[S.pid.isin(delta.index)].shape[0]), len(delta), '+', 'na',
           int(all(sgn(v) == sgn(m) for v in o.values() if np.isfinite(v)) and all(np.isfinite(list(o.values())))),
           int(any(sgn(v) != sgn(m) for v in L)),
           'only people with single- and multi-type decisions in BOTH sessions; by order S-first %s, '
           'T-first %s (n %d/%d); LOO range %.3f-%.3f'
           % (o['strategic'], o['tactical'], (order == 'strategic').sum(), (order == 'tactical').sum(),
              L.min(), L.max()))


def x1(S):
    print('\n=== X1 (extra) · composition x elapsed minutes within session ===')
    s1 = S[S.run == 1]
    f1 = 'took ~ multi*emin + ndrones + C(scenario)'
    gee_variant('X1a', 'composition x elapsed minutes within session 1', 'S-s1', s1, f1, 'multi:emin',
                '+', extra=True, s1=(f1, s1))
    f2 = 'took ~ multi*emin + run2 + ndrones + C(scenario)'
    gee_variant('X1b', 'composition x elapsed minutes within session, both sessions', 'S-all', S, f2,
                'multi:emin', '+', extra=True, s1=(f1, s1))
    gee_variant('X1c', 'drone count (log) x elapsed minutes, three-type missions, session 1', 'S-s1',
                s1[s1.ncolours == 3], 'took ~ lsize*emin + C(scenario)', 'lsize:emin', '+', extra=True,
                s1=('took ~ lsize*emin + C(scenario)', s1[s1.ncolours == 3]))


def x2(S):
    print('\n=== X2 (extra) · pre-emptive manual on single-type missions ===')
    one = S[S.ncolours == 1]
    print('pre-emption rate on single-type, by scenario x run:')
    print(one.groupby(['scenario', 'run']).pre.agg(['mean', 'size']).round(3).to_string())
    gee_variant('X2a', 'pre-emptive manual on single-type missions ~ run2', 'S-all', one,
                'pre ~ run2 + ndrones + C(scenario)', 'run2', '+', extra=True)
    gee_variant('X2b', 'pre-emptive manual on single-type missions ~ run2, game FE', 'S-all', one,
                'pre ~ run2 + ndrones + C(game)', 'run2', '+', extra=True)
    f = 'pre ~ emin + ndrones + C(scenario)'
    gee_variant('X2c', 'pre-emptive manual on single-type ~ elapsed minutes, session 1', 'S-s1',
                one[one.run == 1], f, 'emin', '+', extra=True, s1=(f, one[one.run == 1]))
    gee_variant('X2d', 'pre-emption: single-type vs multi x run2 (does it target single-type?)', 'S-all',
                S, 'pre ~ multi*run2 + ndrones + C(scenario)', 'multi:run2', '-', extra=True)


# ── G2 · within-session curves ────────────────────────────────────────────────────────────────
def g2(S):
    print('\n=== G2 · within-session learning curves ===')
    print('uptake and share of multi-type missions by run x third:')
    print(S.groupby(['run', 'third']).agg(took=('took', 'mean'), multi=('multi', 'mean'),
                                          ndrones=('ndrones', 'mean'), n=('took', 'size')).round(3).to_string())
    print('by scenario x run x third:')
    print(S.groupby(['scenario', 'run', 'third']).agg(took=('took', 'mean'), multi=('multi', 'mean'),
                                                      n=('took', 'size')).round(3).to_string())
    s1, s2 = S[S.run == 1], S[S.run == 2]
    f = 'took ~ first3 + multi + ndrones + C(scenario)'
    gee_variant('G2.1', 'first third of session 2 vs rest, composition held', 'S-all', s2, f, 'first3', '-',
                s1=(f, s1), notes='sample = session 2; s1 gate = same model on session 1 (a dip there too?)')
    gee_variant('G2.2', 'first third of session 2 vs rest, game FE', 'S-all', s2,
                'took ~ first3 + multi + ndrones + C(game)', 'first3', '-', notes='sample = session 2')
    gee_variant('G2.3', 'first third x run2 (is the dip specific to session 2?)', 'S-all', S,
                'took ~ first3*run2 + multi + ndrones + C(scenario)', 'first3:run2', '-')
    gee_variant('G2.4', 'first third of session 2, three-type missions only', 'S-all',
                s2[s2.ncolours == 3], 'took ~ first3 + ndrones + C(scenario)', 'first3', '-',
                notes='sample = session 2, three-type')
    f = 'took ~ emin + multi + ndrones + C(scenario)'
    gee_variant('G2.5', 'elapsed minutes in session 2, composition held (climb)', 'S-all', s2, f, 'emin', '+',
                s1=(f, s1), notes='sample = session 2')
    gee_variant('G2.6', 'first third x run2 within Strategic Heavy only', 'S-all',
                S[S.scenario == 'strategic'], 'took ~ first3*run2 + multi + ndrones', 'first3:run2', '-',
                orders=False, notes='between people: Strategic first vs second')
    gee_variant('G2.7', 'elapsed minutes in session 1, composition held', 'S-s1', s1, f, 'emin', 'none',
                s1=(f, s1))
    # Not an event-defined window (thirds are fixed shares of each session's decisions), but checked
    # against a null anyway: shuffle the third labels within each person-session, keeping each
    # decision's outcome and composition together, and refit.
    f1 = 'took ~ first3 + multi + ndrones + C(scenario)'
    obs = C.point(f1, s2, 'first3')
    print('G2.1 session-1 analogue: OR %.3f' % np.exp(C.point(f1, s1, 'first3')))
    rng = np.random.default_rng(20261007)
    null = []
    for _ in range(300):
        d = s2.copy()
        d['first3'] = d.groupby(['pid', 'run']).first3.transform(lambda x: rng.permutation(x.values))
        null.append(C.point(f1, d, 'first3'))
    null = np.array(null)
    print('G2.1 null simulation (300 within-session shuffles): null OR median %.3f, 2.5-97.5%% %.3f-%.3f; '
          'calibrated two-sided p = %.3f'
          % (np.exp(np.median(null)), np.exp(np.quantile(null, .025)), np.exp(np.quantile(null, .975)),
             np.mean(np.abs(null - np.median(null)) >= abs(obs - np.median(null)))))


# ── G3 · dominated cards ──────────────────────────────────────────────────────────────────────
def g3(S):
    print('\n=== G3 · dominated / illogical Conservative cards ===')
    dom = S[S.dominated == 1]
    print('choice on dominated decisions by game x run:')
    print(pd.crosstab([dom.game, dom.run], dom.choice, normalize='index').round(3).to_string())
    print(pd.crosstab([dom.game, dom.run], dom.choice).to_string())
    f = 'cons ~ run2 + multi + ndrones + C(scenario)'
    gee_variant('G3.1', 'Conservative chosen when dominated ~ run2', 'S-all', dom, f, 'run2', '-')
    gee_variant('G3.2', 'Conservative chosen when dominated ~ run2, game FE', 'S-all', dom,
                'cons ~ run2 + multi + ndrones + C(game)', 'run2', '-')
    gee_variant('G3.3', 'dominated x run2 on choosing Conservative (discrimination)', 'S-all', S,
                'cons ~ dominated*run2 + multi + ndrones + C(scenario)', 'dominated:run2', '-')
    one = S[S.ncolours == 1]
    gee_variant('G3.4', 'illogical x run2 on choosing Conservative, single-type only', 'S-all', one,
                'cons ~ odd*run2 + ndrones + C(scenario)', 'odd:run2', '-')
    gee_variant('G3.5', 'Conservative vs Aggressive when dominated ~ run2, card-takers only', 'S-all',
                dom[dom.took == 1], f, 'run2', '-')
    d1 = dom[dom.run == 1]
    f6 = 'cons ~ emin + multi + ndrones + C(scenario)'
    gee_variant('G3.6', 'Conservative chosen when dominated ~ elapsed minutes, session 1', 'S-s1', d1, f6,
                'emin', '-', s1=(f6, d1))
    gee_variant('G3.7', 'Conservative chosen when dominated ~ run2 (order + pairing)', 'S-27',
                dom[dom.swapped == 0], f, 'run2', '-')
    gee_variant('G3.8', 'Conservative chosen when dominated ~ run2', 'S-v112', dom[dom.v112 == 1], f,
                'run2', '-')


# ── G4 · decision speed ───────────────────────────────────────────────────────────────────────
def g4(S, T):
    print('\n=== G4 · decision speed, net of forced waits ===')
    assert (S[S.took == 1].net >= 0).all()
    print('median net / raw seconds by run x route:')
    S = S.assign(route=np.where(S.took == 1, 'card', np.where(S.pre == 1, 'pre-empt', 'manual-after')))
    print(S.groupby(['run', 'route']).agg(net=('net', 'median'), raw=('secs', 'median'),
                                          n=('net', 'size')).round(2).to_string())
    print(S.groupby(['scenario', 'run']).agg(net=('net', 'median'), n=('net', 'size')).round(2).to_string())
    f = 'lnet ~ run2 + took + multi + ndrones + C(scenario)'
    gee_variant('G4.1', 'log decision seconds net of card reveal ~ run2', 'S-all', S, f, 'run2', '-',
                binomial=False)
    gee_variant('G4.2', 'log net decision seconds ~ run2, game FE', 'S-all', S,
                'lnet ~ run2 + took + multi + ndrones + C(game)', 'run2', '-', binomial=False)
    gee_variant('G4.3', 'log net seconds ~ run2, card choices only', 'S-all', S[S.took == 1],
                'lnet ~ run2 + multi + ndrones + C(scenario)', 'run2', '-', binomial=False)
    gee_variant('G4.4', 'log seconds ~ run2, manual choices only', 'S-all', S[S.manual == 1],
                'lnet ~ run2 + multi + ndrones + C(scenario)', 'run2', '-', binomial=False)
    f5 = 'lnet ~ emin + took + multi + ndrones + C(scenario)'
    gee_variant('G4.5', 'log net seconds ~ elapsed minutes within session', 'S-all', S,
                'lnet ~ emin + run2 + took + multi + ndrones + C(scenario)', 'emin', '-', binomial=False,
                s1=(f5, S[S.run == 1]))
    # post hoc robustness of G4.5 (added after seeing it): is the within-session speed-up deadline
    # haste (final 90 s), and does it recur inside session 2?
    gee_variant('G4.5r', 'G4.5 robustness: final 90 s of each session excluded (post hoc)', 'S-all',
                S[S.elapsed <= 390], 'lnet ~ emin + run2 + took + multi + ndrones + C(scenario)', 'emin', '-',
                binomial=False, s1=(f5, S[(S.run == 1) & (S.elapsed <= 390)]))
    gee_variant('G4.5s', 'G4.5 robustness: session 2 only (post hoc)', 'S-all', S[S.run == 2], f5, 'emin',
                '-', binomial=False, s1=(f5, S[S.run == 1]), notes='sample = session 2')
    S['third'] = S.third.astype(int)
    print('median net seconds by run x third:')
    print(S.groupby(['run', 'third']).net.median().round(2).unstack().to_string())
    ft = 'lnet ~ run2 + consulted + lplan + C(scenario)'
    gee_variant('G4.6', 'tactical planner log seconds net of Suggest reveal ~ run2', 'S-all', T, ft, 'run2',
                '-', binomial=False)
    gee_variant('G4.7', 'log net decision seconds ~ run2 (order + pairing)', 'S-27', S[S.swapped == 0], f,
                'run2', '-', binomial=False)
    gee_variant('G4.8', 'log net decision seconds ~ run2', 'S-v112', S[S.v112 == 1], f, 'run2', '-',
                binomial=False)
    gee_variant('G4.9', 'log RAW decision seconds (incl. reveal) ~ run2, for contrast', 'S-all', S,
                'lraw ~ run2 + took + multi + ndrones + C(scenario)', 'run2', '-', binomial=False)
    gee_variant('G4.10', 'tactical log net seconds ~ run2, game FE', 'S-all', T,
                'lnet ~ run2 + consulted + lplan + C(game)', 'run2', '-', binomial=False)


# ── X3 · performance by run ───────────────────────────────────────────────────────────────────
def x3(P):
    print('\n=== X3 (extra) · performance by run ===')
    print(P.groupby(['game', 'run']).agg(eff=('scoreEff', 'mean'), share=('share_rescaled', 'mean'),
                                         n=('pid', 'size')).round(3).to_string())
    metrics = [('scoreEff', 'score efficiency'), ('zgame', 'per-game z-score (rescaled score)'),
               ('share_rescaled', 'share of near-perfect operator score (P01/P02 rescaled x2)'),
               ('bestshare', 'share of best human score on that game')]
    for i, (y, lab) in enumerate(metrics):
        gee_variant('X3.%d' % (i + 1), '%s ~ run2, game FE (run identified by S-6 only)' % lab, 'S-all', P,
                    '%s ~ run2 + C(game)' % y, 'run2', '+', binomial=False, extra=True)
    gee_variant('X3.5', 'share of near-perfect score ~ run2, game FE, Tactical game 2 excluded', 'S-all',
                P[P.game != 'tactical|2'], 'share_rescaled ~ run2 + C(game)', 'run2', '+', binomial=False,
                extra=True)
    gee_variant('X3.6', 'share of near-perfect score ~ run2, scenario only (the synthesis-page reading)',
                'S-all', P, 'share_rescaled ~ run2 + C(scenario)', 'run2', '+', binomial=False, extra=True,
                notes='run identified mainly by game pairing; benchmark unreliable on tactical|2')
    s6 = P[P.swapped == 1]
    g = s6.pivot_table(index='pid', columns='run', values=['scoreEff', 'zgame', 'share_rescaled'])
    print('S-6 per person (run1 -> run2):')
    print(g.round(3).to_string())


def main():
    S, T, P = C.load()
    print('decisions %d / %d people; tactical plans %d; sessions %d'
          % (len(S), S.pid.nunique(), len(T), len(P)))
    g1(S)
    x1(S)
    x2(S)
    g2(S)
    g3(S)
    g4(S, T)
    x3(P)
    pd.DataFrame(ROWS, columns=COLS).to_csv(OUT, index=False)
    print('\nwrote %s (%d rows)' % (OUT, len(ROWS)))


if __name__ == '__main__':
    main()
