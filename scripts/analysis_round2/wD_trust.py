"""Workstream D (round 2) -- trust: separating scenario, game and order.

    C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wD_trust.py

Variant menu: docs/analysis/HYPOTHESES_ROUND2.md §4 D (D1-D5) as amended 2026-10-07 (S-bal replaced
by S-27 / S-6 / game fixed effects). Extras X1, X2 are logged in docs/analysis/round2/wD_trust.md
before they were run. Every test becomes one row of docs/analysis/round2/wD_specs.csv (the only file
written). All GEEs use the bias-reduced (Mancl-DeRouen) small-sample covariance.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wD_common as WC  # noqa: E402

warnings.filterwarnings('ignore')
pd.set_option('display.width', 200)
pd.set_option('display.max_columns', 40)
OUT = WC.ROOT / 'docs' / 'analysis' / 'round2' / 'wD_specs.csv'
ROWS = []
COLS = ['workstream', 'variant_id', 'extra', 'description', 'sample', 'outcome', 'predictor', 'model',
        'estimate', 'ci_lo', 'ci_hi', 'estimate_scale', 'p', 'n_obs', 'n_people',
        'expected_direction', 's1_same_direction', 'both_orders_same_direction', 'loo_sign_flip',
        'notes']


def add(**kw):
    row = {c: kw.get(c, 'na') for c in COLS}
    row['workstream'] = 'D'
    row['extra'] = kw.get('extra', 0)
    for k in ('estimate', 'ci_lo', 'ci_hi', 'p'):
        if isinstance(row[k], (float, np.floating)):
            row[k] = round(float(row[k]), 5)
    ROWS.append(row)
    print('  %-8s %-7s %-34s est=%+.3f [%+.3f, %+.3f] p=%.4f n=%s/%s  s1=%s ord=%s loo=%s %s'
          % (row['variant_id'], row['sample'], row['predictor'][:34], row['estimate'], row['ci_lo'],
             row['ci_hi'], row['p'], row['n_obs'], row['n_people'], row['s1_same_direction'],
             row['both_orders_same_direction'], row['loo_sign_flip'], row['notes'][:70]))


# ── model helpers ────────────────────────────────────────────────────────────────────────────

def gee(formula, data):
    return smf.gee(formula, 'pid', data=data, family=sm.families.Gaussian(),
                   cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type='bias_reduced')


def ols(formula, data):
    return smf.ols(formula, data).fit(cov_type='HC3')


def coef(m, name):
    lo, hi = m.conf_int().loc[name]
    return float(m.params[name]), float(lo), float(hi), float(m.pvalues[name])


def welch(a, b):
    """mean(a) - mean(b), Welch CI and p."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a.mean() - b.mean()
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = np.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    t = stats.t.ppf(.975, df)
    p = 2 * stats.t.sf(abs(d / se), df)
    return float(d), float(d - t * se), float(d + t * se), float(p)


def loo(fit_fn, data, est):
    """Leave-one-person-out: (min, max, any sign flip) of the estimate."""
    vals = []
    for p in data.pid.unique():
        try:
            vals.append(fit_fn(data[data.pid != p]))
        except Exception:
            pass
    vals = np.array(vals)
    flip = int(np.any(np.sign(vals) != np.sign(est)))
    return float(vals.min()), float(vals.max()), flip


def sgn(x):
    return int(np.sign(x))


def wb(S, x):
    """Within-person deviation and person mean of x."""
    D = S.copy()
    D[x + '_b'] = D.groupby('pid')[x].transform('mean')
    D[x + '_w'] = D[x] - D[x + '_b']
    return D


# ── D3 / D4 / X1: what in a session predicts that session's trust (within person) ───────────

def within_battery(S, W, vid, y, x, label, expected, extra=0, note=''):
    """M1 run only; M2 + game FE (primary); M3 v1.12+; M4 S-s1 between; M5/M6 first differences
    within each scenario order. Gates are attached to M1-M3."""
    D = wb(S.dropna(subset=[x, y]), x)
    D = D[D.groupby('pid').pid.transform('size') == 2]
    f1 = '%s ~ %s_w + %s_b + C(run)' % (y, x, x)
    f2 = '%s ~ %s_w + %s_b + C(game) + C(run)' % (y, x, x)

    # gate ingredients
    s1 = S[(S.run == 1)].dropna(subset=[x, y])
    m4 = ols('%s ~ %s + C(game)' % (y, x), s1)
    e4 = coef(m4, x)
    Wd = W.dropna(subset=['d_' + x, 'd_' + y])
    eo = {}
    for o in ('SF', 'TF'):
        sub = Wd[Wd.order == o]
        if sub['d_' + x].std() > 0 and len(sub) > 4:
            eo[o] = coef(ols('d_%s ~ d_%s' % (y, x), sub), 'd_' + x)
        else:
            eo[o] = (np.nan,) * 4

    for mid, sample, formula, data in (('M1', 'S-all', f1, D), ('M2', 'S-all', f2, D),
                                       ('M3', 'S-v112', f2, D[D.v112 == 1])):
        m = gee(formula, data)
        est = coef(m, x + '_w')
        lmin, lmax, flip = loo(lambda d: gee(formula, d).params[x + '_w'], data, est[0])
        both = int(all(sgn(eo[o][0]) == sgn(est[0]) for o in eo)) if all(
            not np.isnan(eo[o][0]) for o in eo) else 'na'
        add(variant_id='%s.%s' % (vid, mid), extra=extra,
            description='%s: within-person effect on %s (%s)' % (label, y, {
                'M1': 'GEE, within + between + run',
                'M2': 'GEE, within + between + game FE + run',
                'M3': 'GEE, within + between + game FE + run, v1.12+'}[mid]),
            sample=sample, outcome=y, predictor=x + ' (within person)',
            model='GEE gaussian exch bias_reduced: ' + formula,
            estimate=est[0], ci_lo=est[1], ci_hi=est[2], estimate_scale='b', p=est[3],
            n_obs=len(data), n_people=data.pid.nunique(), expected_direction=expected,
            s1_same_direction=int(sgn(e4[0]) == sgn(est[0])), both_orders_same_direction=both,
            loo_sign_flip=flip, notes='LOO range [%+.3f, %+.3f]. %s' % (lmin, lmax, note))
    f4 = '%s ~ %s + C(game)' % (y, x)
    l4 = loo(lambda d_: ols(f4, d_).params[x], s1, e4[0])
    o4 = {o: coef(ols(f4, s1[s1.order == o]), x)[0] for o in ('SF', 'TF')}
    add(variant_id='%s.M4' % vid, extra=extra,
        s1_same_direction=1, loo_sign_flip=l4[2],
        both_orders_same_direction=int(all(sgn(v_) == sgn(e4[0]) for v_ in o4.values())),
        description='%s: between-person on session 1 only, game FE' % label,
        sample='S-s1', outcome=y + ' (session 1)', predictor=x + ' (session 1)',
        model='OLS HC3: %s ~ %s + C(game)' % (y, x), estimate=e4[0], ci_lo=e4[1], ci_hi=e4[2],
        estimate_scale='b', p=e4[3], n_obs=len(s1), n_people=len(s1), expected_direction=expected,
        notes='gate source for M1-M3 s1_same_direction. Between person: cannot separate cause from '
              'character. LOO [%+.3f, %+.3f]; within session-1 scenario SF b=%+.3f, TF b=%+.3f'
              % (l4[0], l4[1], o4['SF'], o4['TF']))
    for o in ('SF', 'TF'):
        n = int((Wd.order == o).sum())
        add(variant_id='%s.M5%s' % (vid, o), extra=extra,
            description='%s: first difference (run 2 - run 1) within order %s' % (label, o),
            sample='S-all', outcome='d_' + y, predictor='d_' + x,
            model='OLS HC3: d_%s ~ d_%s, order=%s only' % (y, x, o),
            estimate=eo[o][0], ci_lo=eo[o][1], ci_hi=eo[o][2], estimate_scale='b', p=eo[o][3],
            n_obs=n, n_people=n, expected_direction=expected,
            notes='order %s only (includes its 3 swapped); gate source' % o)


def main():
    S, dec_b, dec_h5 = WC.build()
    W = WC.wide(S)

    print('=' * 100)
    print('DATA')
    print('=' * 100)
    print('sessions %d, people %d, v1.12+ people %d, swapped %s'
          % (len(S), S.pid.nunique(), S[S.v112 == 1].pid.nunique(), sorted(WC.SWAPPED)))
    print('\nStrategic trust by game x run (mean, n):')
    print(S.pivot_table(index='game', columns='run', values='trust_s', aggfunc=['mean', 'size']).round(2))
    print('\nTactical trust by game x run (mean, n):')
    print(S.pivot_table(index='game', columns='run', values='trust_t', aggfunc=['mean', 'size']).round(2))
    print('\nPer-game session features (means):')
    print(S.groupby('game')[['single_share', 'odd_seen', 'dom_seen', 'card_bad', 'took', 'consult',
                             'scoreEff', 'bench_share', 'best_share']].mean().round(2))
    print('\nThe six swapped participants:')
    print(W[W.swapped == 1][['pid', 'order', 'game_1', 'game_2', 'trust_s_1', 'trust_s_2', 'd_trust_s',
                             'trust_t_1', 'trust_t_2', 'd_trust_t', 'took_1', 'took_2']].round(2)
          .to_string(index=False))

    # ── D1 · session 1 only ────────────────────────────────────────────────────────────────
    print('\n' + '=' * 100)
    print('D1 · Session 1 only: strategic trust after a Strategic Heavy vs a Tactical Heavy first session')
    print('=' * 100)
    s1 = S[S.run == 1].copy()
    a, b = s1[s1.tac == 1].trust_s, s1[s1.tac == 0].trust_s
    d = welch(a, b)
    lmin, lmax, flip = loo(lambda x: welch(x[x.tac == 1].trust_s, x[x.tac == 0].trust_s)[0], s1, d[0])
    mw = stats.mannwhitneyu(a, b)
    add(variant_id='D1a', description='Strategic trust after session 1: Tactical-first minus Strategic-first',
        sample='S-s1', outcome='trust_s (session 1)', predictor='scenario played (Tactical - Strategic)',
        model='Welch t', estimate=d[0], ci_lo=d[1], ci_hi=d[2], estimate_scale='diff', p=d[3],
        n_obs=len(s1), n_people=len(s1), expected_direction='+', s1_same_direction=1,
        loo_sign_flip=flip,
        notes='means T %.2f (n=%d) S %.2f (n=%d); Mann-Whitney p=%.3f; LOO [%+.3f, %+.3f]. Order cannot '
              'enter (session 1); game is nested in scenario'
              % (a.mean(), len(a), b.mean(), len(b), mw.pvalue, lmin, lmax))
    m = ols('trust_s ~ tac + idx2', s1)
    e = coef(m, 'tac')
    lmin, lmax, flip = loo(lambda x: ols('trust_s ~ tac + idx2', x).params['tac'], s1, e[0])
    add(variant_id='D1b', description='Session-1 strategic trust: scenario, adjusting for which game index '
        '(game 2 only for the 6 swapped)', sample='S-s1', outcome='trust_s (session 1)',
        predictor='scenario (Tactical)', model='OLS HC3: trust_s ~ tac + idx2', estimate=e[0],
        ci_lo=e[1], ci_hi=e[2], estimate_scale='b', p=e[3], n_obs=len(s1), n_people=len(s1),
        expected_direction='+', s1_same_direction=1, loo_sign_flip=flip,
        notes='LOO [%+.3f, %+.3f]' % (lmin, lmax))
    e = coef(m, 'idx2')
    add(variant_id='D1b.idx', description='Session-1 strategic trust: game 2 vs game 1 within scenario '
        '(identified by the 6 swapped only)', sample='S-s1', outcome='trust_s (session 1)',
        predictor='game index 2', model='OLS HC3: trust_s ~ tac + idx2', estimate=e[0], ci_lo=e[1],
        ci_hi=e[2], estimate_scale='b', p=e[3], n_obs=len(s1), n_people=len(s1),
        expected_direction='none', notes='6 people on game 2 in session 1 (P31-P36)')
    v = s1[s1.v112 == 1]
    d = welch(v[v.tac == 1].trust_s, v[v.tac == 0].trust_s)
    add(variant_id='D1c', description='As D1a on the identical-version cohort', sample='S-v112',
        outcome='trust_s (session 1)', predictor='scenario played (Tactical - Strategic)',
        model='Welch t (session 1, v1.12+)', estimate=d[0], ci_lo=d[1], ci_hi=d[2],
        estimate_scale='diff', p=d[3], n_obs=len(v), n_people=len(v), expected_direction='+',
        s1_same_direction=1, notes='session 1 only')
    a2, b2 = s1[s1.tac == 1].trust_t, s1[s1.tac == 0].trust_t
    d = welch(a2, b2)
    add(variant_id='D1d', description='Discriminant: TACTICAL trust after session 1, Tactical-first minus '
        'Strategic-first', sample='S-s1', outcome='trust_t (session 1)',
        predictor='scenario played (Tactical - Strategic)', model='Welch t', estimate=d[0], ci_lo=d[1],
        ci_hi=d[2], estimate_scale='diff', p=d[3], n_obs=len(s1), n_people=len(s1),
        expected_direction='none', s1_same_direction='na',
        notes='means T %.2f S %.2f' % (a2.mean(), b2.mean()))
    s27 = s1[s1.swapped == 0]
    d = welch(s27[s27.tac == 1].trust_s, s27[s27.tac == 0].trust_s)
    add(variant_id='D1e', description='As D1a without the swapped six (session 1 = game T1 vs game S1)',
        sample='S-27', outcome='trust_s (session 1)', predictor='game T1 - game S1',
        model='Welch t (session 1)', estimate=d[0], ci_lo=d[1], ci_hi=d[2], estimate_scale='diff',
        p=d[3], n_obs=len(s27), n_people=len(s27), expected_direction='+', s1_same_direction=1,
        notes='scenario and game coincide here')

    # ── D2 · scenario vs game vs order ─────────────────────────────────────────────────────
    print('\n' + '=' * 100)
    print('D2 · Scenario, game and order (strategic trust; D4a/D4b repeat on tactical trust)')
    print('=' * 100)
    S['tac_c'], S['idx_c'] = S.tac - .5, S.idx2 - .5
    S['tf'] = (S.order == 'TF').astype(int)
    for prefix, y, exp_s, exp_r in (('D2', 'trust_s', '+', '-'), ('D4', 'trust_t', 'none', 'none')):
        vid = lambda k: ('%s%s' % (prefix, k)) if prefix == 'D2' else ('D4%s' % {'a': 'a', 'b': 'b',
                                                                                'g': 'g', 'f': 'f'}[k])
        # Gates for the crossover terms. Scenario: the session-1-only between-person difference (D1a/D1d)
        # is the order-free version. Run: cannot exist in session 1 (na); in each order the run effect
        # is confounded with +/- the scenario effect, so the check is that the mean change has the
        # run effect's sign in BOTH orders. Scenario has no within-order version (na).
        s1_ = S[S.run == 1]
        s1_diff = s1_[s1_.tac == 1][y].mean() - s1_[s1_.tac == 0][y].mean()
        dmean = {o: W[W.order == o]['d_' + y].mean() for o in ('SF', 'TF')}

        def gates(term, est):
            if term in ('tac', 'tac_c'):
                return int(sgn(s1_diff) == sgn(est)), 'na'
            if term == 'run2':
                return 'na', int(all(sgn(v) == sgn(est) for v in dmean.values()))
            return 'na', 'na'

        # (a) crossover: scenario + run
        fa = '%s ~ tac + run2' % y
        m = gee(fa, S)
        for term, lab, ex in (('tac', 'scenario (Tactical - Strategic)', exp_s),
                              ('run2', 'run 2 vs run 1', exp_r)):
            e = coef(m, term)
            lmin, lmax, flip = loo(lambda d_: gee(fa, d_).params[term], S, e[0])
            g1, g2 = gates(term, e[0])
            add(variant_id=vid('a') + '.' + term, description='%s: %s, crossover model' % (y, lab),
                sample='S-all', outcome=y, predictor=lab, model='GEE bias_reduced: ' + fa,
                estimate=e[0], ci_lo=e[1], ci_hi=e[2], estimate_scale='b', p=e[3], n_obs=len(S),
                n_people=S.pid.nunique(), expected_direction=ex, loo_sign_flip=flip,
                s1_same_direction=g1, both_orders_same_direction=g2,
                notes='LOO [%+.3f, %+.3f]. Scenario and run are both within person; tac and run are '
                      'separately identified because order is crossed' % (lmin, lmax))
        # (b) game FE (effect-coded scenario x game index) + run, and + order
        fb = '%s ~ tac_c * idx_c + run2' % y
        m = gee(fb, S)
        for term, lab, ex in (('tac_c', 'scenario (Tactical - Strategic), averaged over game index', exp_s),
                              ('idx_c', 'game 2 - game 1, averaged over scenario', 'none'),
                              ('tac_c:idx_c', 'scenario x game index (T2-T1) - (S2-S1)', 'none'),
                              ('run2', 'run 2 vs run 1, net of game', exp_r)):
            e = coef(m, term)
            lmin, lmax, flip = loo(lambda d_: gee(fb, d_).params[term], S, e[0])
            add(variant_id=vid('b') + '.' + term.replace(':', 'x'),
                description='%s: %s; game fixed effects + run' % (y, lab), sample='S-all', outcome=y,
                predictor=lab, model='GEE bias_reduced: ' + fb, estimate=e[0], ci_lo=e[1], ci_hi=e[2],
                estimate_scale='b', p=e[3], n_obs=len(S), n_people=S.pid.nunique(),
                expected_direction=ex, loo_sign_flip=flip,
                s1_same_direction=gates(term, e[0])[0], both_orders_same_direction=gates(term, e[0])[1],
                notes='LOO [%+.3f, %+.3f]. Game index vs run separated ONLY by the 6 swapped'
                      % (lmin, lmax))
        fg = '%s ~ tac_c * idx_c + run2 + tf' % y
        m = gee(fg, S)
        e = coef(m, 'tf')
        add(variant_id=vid('g') + '.order', description='%s: order (Tactical first) as a person-level fixed '
            'effect alongside game FE + run' % y, sample='S-all', outcome=y,
            predictor='order TF (person-level)', model='GEE bias_reduced: ' + fg, estimate=e[0],
            ci_lo=e[1], ci_hi=e[2], estimate_scale='b', p=e[3], n_obs=len(S), n_people=S.pid.nunique(),
            expected_direction='none', notes='between-person level difference (carry-over)')
        e = coef(m, 'tac_c')
        add(variant_id=vid('g') + '.tac', description='%s: scenario with game FE + run + order' % y,
            sample='S-all', outcome=y, predictor='scenario (Tactical - Strategic)',
            model='GEE bias_reduced: ' + fg, estimate=e[0], ci_lo=e[1], ci_hi=e[2], estimate_scale='b',
            p=e[3], n_obs=len(S), n_people=S.pid.nunique(), expected_direction=exp_s)
        v = S[S.v112 == 1]
        m = gee(fb, v)
        e = coef(m, 'tac_c')
        add(variant_id=vid('f') + '.tac', description='%s: scenario, game FE + run, identical-version cohort'
            % y, sample='S-v112', outcome=y, predictor='scenario (Tactical - Strategic)',
            model='GEE bias_reduced: ' + fb, estimate=e[0], ci_lo=e[1], ci_hi=e[2], estimate_scale='b',
            p=e[3], n_obs=len(v), n_people=v.pid.nunique(), expected_direction=exp_s)

    # order + pairing (S-27) and the swapped six (S-6), person level
    for y, prefix, ex in (('trust_s', 'D2', '-'), ('trust_t', 'D4', 'none')):
        w27 = W[W.swapped == 0]
        d = welch(w27[w27.order == 'TF']['d_' + y], w27[w27.order == 'SF']['d_' + y])
        lmin, lmax, flip = loo(lambda x: welch(x[x.order == 'TF']['d_' + y], x[x.order == 'SF']['d_' + y])[0],
                               w27, d[0])
        add(variant_id='%sc' % prefix, description='Change in %s (run 2 - run 1): Tactical-first minus '
            'Strategic-first, unswapped only = "order + pairing"' % y, sample='S-27', outcome='d_' + y,
            predictor='order TF (= pairing S2+T1)', model='Welch t', estimate=d[0], ci_lo=d[1], ci_hi=d[2],
            estimate_scale='diff', p=d[3], n_obs=len(w27), n_people=len(w27), expected_direction=ex,
            loo_sign_flip=flip, notes='means TF %.2f SF %.2f; LOO [%+.3f, %+.3f]'
            % (w27[w27.order == 'TF']['d_' + y].mean(), w27[w27.order == 'SF']['d_' + y].mean(), lmin, lmax))
        w6 = W[W.swapped == 1]
        d = welch(w6[w6.order == 'TF']['d_' + y], w6[w6.order == 'SF']['d_' + y])
        add(variant_id='%sd' % prefix, description='Change in %s: Tactical-first minus Strategic-first among '
            'the 6 swapped (order separated from pairing: here TF = S1+T2)' % y, sample='S-6',
            outcome='d_' + y, predictor='order TF (= pairing S1+T2)', model='Welch t (descriptive)',
            estimate=d[0], ci_lo=d[1], ci_hi=d[2], estimate_scale='diff', p=d[3], n_obs=6, n_people=6,
            expected_direction=ex, notes='DESCRIPTIVE ONLY, n=3 v 3; TF %s; SF %s'
            % (w6[w6.order == 'TF']['d_' + y].round(2).tolist(), w6[w6.order == 'SF']['d_' + y].round(2).tolist()))

    # game at fixed order: S2 vs S1 played in the same position
    for pos, lab in ((1, 'first'), (2, 'second')):
        x = S[(S.scenario == 'strategic') & (S.run == pos)]
        d = welch(x[x.gameIndex == 2].trust_s, x[x.gameIndex == 1].trust_s)
        add(variant_id='D2e.%s' % lab, description='Strategic trust after game S2 minus after game S1, '
            'both played %s (S-6 cell n=3 vs S-27 cell)' % lab, sample='S-all',
            outcome='trust_s (after the Strategic Heavy session)', predictor='game S2 vs S1 at fixed order',
            model='Welch t (descriptive)', estimate=d[0], ci_lo=d[1], ci_hi=d[2], estimate_scale='diff',
            p=d[3], n_obs=len(x), n_people=len(x), expected_direction='none',
            notes='DESCRIPTIVE: S2 n=%d mean %.2f; S1 n=%d mean %.2f' % (
                (x.gameIndex == 2).sum(), x[x.gameIndex == 2].trust_s.mean(), (x.gameIndex == 1).sum(),
                x[x.gameIndex == 1].trust_s.mean()))
    # position at fixed game: Strategic Heavy second minus first, same game
    for g in (1, 2):
        x = S[(S.scenario == 'strategic') & (S.gameIndex == g)]
        d = welch(x[x.run == 2].trust_s, x[x.run == 1].trust_s)
        add(variant_id='D2h.S%d' % g, description='Strategic trust after game S%d played second minus played '
            'first (between person)' % g, sample='S-all', outcome='trust_s (after the Strategic Heavy session)',
            predictor='Strategic Heavy second vs first, game S%d' % g, model='Welch t (descriptive)',
            estimate=d[0], ci_lo=d[1], ci_hi=d[2], estimate_scale='diff', p=d[3], n_obs=len(x),
            n_people=len(x), expected_direction='-',
            notes='DESCRIPTIVE: second n=%d mean %.2f; first n=%d mean %.2f' % (
                (x.run == 2).sum(), x[x.run == 2].trust_s.mean(), (x.run == 1).sum(), x[x.run == 1].trust_s.mean()))

    # ── D3 · within person: what in a session predicts its strategic trust ─────────────────
    print('\n' + '=' * 100)
    print('D3 · Within person: session features -> that session\'s strategic trust')
    print('=' * 100)
    for vid, x, lab, ex in (('D3a', 'single_share', 'share of single-type missions (0-1)', '-'),
                            ('D3b', 'dom_seen', 'dominated Conservative cards seen (count)', '-'),
                            ('D3c', 'odd_seen', 'illogical Conservative cards seen (count)', '-'),
                            ('D3d', 'card_bad', 'card missions failed/abandoned (count)', '-'),
                            ('D3e1', 'scoreEff', 'score efficiency (score / points available)', '+'),
                            ('D3e2', 'z_game', 'per-game z-score (P01/P02 rescaled x2)', '+'),
                            ('D3e3', 'bench_share', 'share of near-perfect operator score (x2 rescale)', '+'),
                            ('D3e4', 'best_share', 'share of best human score on that game (x2 rescale)', '+')):
        note = 'bench_share unreliable on tactical|2' if x == 'bench_share' else ''
        within_battery(S, W, vid, 'trust_s', x, lab, ex, note=note)

    print('\n  X1 (extra) · strategic uptake -> strategic trust, same battery as D4')
    within_battery(S, W, 'X1', 'trust_s', 'took', 'strategic card uptake (0-1)', '+', extra=1)

    # ── D4 · tactical tier ─────────────────────────────────────────────────────────────────
    print('\n' + '=' * 100)
    print('D4 · Tactical trust and tactical behaviour, within person')
    print('=' * 100)
    for vid, x, lab in (('D4c', 'consult', 'tactical consult rate (Suggest pressed, 0-1)'),
                        ('D4d', 'accept', 'tactical keep-unmodified rate (0-1)'),
                        ('D4e', 'recoveryUse', 'recovery Suggest rate (0-1)')):
        within_battery(S, W, vid, 'trust_t', x, lab, '+')

    # ── D5 · does trust lead behaviour? ────────────────────────────────────────────────────
    print('\n' + '=' * 100)
    print('D5 · Session-1 trust -> change in session-2 uptake')
    print('=' * 100)
    W['game_1c'] = W.game_1
    for vid, t, beh, lab, extra in (('D5', 'trust_s', 'took', 'strategic card uptake', 0),
                                    ('D5t', 'trust_t', 'consult', 'tactical consult rate', 0),
                                    ('D5u', 'trust_t', 'accept', 'tactical keep-unmodified rate', 0),
                                    ('X2', 'trust_s', 'took3', 'card uptake on three-type missions', 1)):
        Wd = W.dropna(subset=[t + '_1', 'd_' + beh, beh + '_1'])
        r = stats.spearmanr(Wd[t + '_1'], Wd['d_' + beh])
        if vid == 'D5':
            from h5_h8_common import spearman_ci
            sc = spearman_ci(Wd[t + '_1'], Wd['d_' + beh])
            lmin, lmax, flip = loo(lambda x: stats.spearmanr(x[t + '_1'], x['d_' + beh])[0], Wd, sc['rho'])
            add(variant_id='D5a', description='Spearman: session-1 strategic trust vs change in card uptake',
                sample='S-all', outcome='d_took', predictor='trust_s session 1', model='Spearman',
                estimate=sc['rho'], ci_lo=sc['lo'], ci_hi=sc['hi'], estimate_scale='rho', p=sc['p'],
                n_obs=sc['n'], n_people=sc['n'], expected_direction='+', loo_sign_flip=flip,
                notes='Fisher-z CI; LOO [%+.3f, %+.3f]. Raw change is regression-to-mean prone; see D5b'
                      % (lmin, lmax))
        f = 'd_%s ~ %s_1 + %s_1 + C(game_1)' % (beh, t, beh)
        m = ols(f, Wd)
        e = coef(m, t + '_1')
        lmin, lmax, flip = loo(lambda x: ols(f, x).params[t + '_1'], Wd, e[0])
        eo = {o: coef(ols('d_%s ~ %s_1 + %s_1' % (beh, t, beh), Wd[Wd.order == o]), t + '_1')
              for o in ('SF', 'TF')}
        both = int(all(sgn(eo[o][0]) == sgn(e[0]) for o in eo))
        add(variant_id=vid + 'b', extra=extra, description='Session-1 %s predicts change in %s, adjusting for '
            'session-1 %s and session-1 game' % (t, lab, beh), sample='S-all', outcome='d_' + beh,
            predictor=t + ' session 1 (per scale point)', model='OLS HC3: ' + f, estimate=e[0], ci_lo=e[1],
            ci_hi=e[2], estimate_scale='b', p=e[3], n_obs=len(Wd), n_people=len(Wd),
            expected_direction='+', s1_same_direction='na', both_orders_same_direction=both,
            loo_sign_flip=flip, notes='LOO [%+.3f, %+.3f]; within SF b=%+.3f p=%.3f, TF b=%+.3f p=%.3f; '
            'S-s1 gate not applicable (needs two sessions); raw Spearman rho=%+.3f p=%.3f'
            % (lmin, lmax, eo['SF'][0], eo['SF'][3], eo['TF'][0], eo['TF'][3], r.correlation, r.pvalue))
        for o in ('SF', 'TF'):
            n = int((Wd.order == o).sum())
            add(variant_id='%sb.%s' % (vid, o), extra=extra, description='As %sb within order %s' % (vid, o),
                sample='S-all', outcome='d_' + beh, predictor=t + ' session 1',
                model='OLS HC3: d_%s ~ %s_1 + %s_1, order=%s' % (beh, t, beh, o), estimate=eo[o][0],
                ci_lo=eo[o][1], ci_hi=eo[o][2], estimate_scale='b', p=eo[o][3], n_obs=n, n_people=n,
                expected_direction='+', notes='gate source')
        v = Wd[Wd.v112 == 1]
        m = ols(f, v)
        e = coef(m, t + '_1')
        add(variant_id=vid + 'c', extra=extra, description='As %sb on the identical-version cohort' % vid,
            sample='S-v112', outcome='d_' + beh, predictor=t + ' session 1', model='OLS HC3: ' + f,
            estimate=e[0], ci_lo=e[1], ci_hi=e[2], estimate_scale='b', p=e[3], n_obs=len(v), n_people=len(v),
            expected_direction='+')
        w27 = Wd[Wd.swapped == 0]
        f27 = 'd_%s ~ %s_1 + %s_1 + C(order)' % (beh, t, beh)
        e = coef(ols(f27, w27), t + '_1')
        add(variant_id=vid + 'd', extra=extra, description='As %sb without the swapped six (order = pairing)'
            % vid, sample='S-27', outcome='d_' + beh, predictor=t + ' session 1', model='OLS HC3: ' + f27,
            estimate=e[0], ci_lo=e[1], ci_hi=e[2], estimate_scale='b', p=e[3], n_obs=len(w27),
            n_people=len(w27), expected_direction='+')

    # ── mechanism material: debrief quotes ─────────────────────────────────────────────────
    print('\n' + '=' * 100)
    print('Debrief quotes (trust_trajectory / scenario_comparison) with each speaker\'s trust path')
    print('=' * 100)
    q = WC.H.B.load_quotes()
    Wi = W.set_index('pid')
    for x in q['quotes']:
        if x['theme'] in ('trust_trajectory', 'scenario_comparison') and x['pid'] in Wi.index:
            r_ = Wi.loc[x['pid']]
            print('  %-34s %s swapped=%d trust_s %.2f->%.2f | %s'
                  % (x['id'], r_.order, r_.swapped, r_.trust_s_1, r_.trust_s_2, x['text'][:150].replace('\n', ' ')))
    print('  coded debriefs among swapped: %s' % sorted(set(q['participants']) & WC.SWAPPED))

    print('\nPer-person table:')
    print(W[['pid', 'order', 'swapped', 'game_1', 'game_2', 'trust_s_1', 'trust_s_2', 'd_trust_s',
             'trust_t_1', 'trust_t_2', 'took_1', 'took_2', 'consult_1', 'consult_2']]
          .sort_values(['order', 'swapped', 'd_trust_s']).round(2).to_string(index=False))

    pd.DataFrame(ROWS, columns=COLS).to_csv(OUT, index=False)
    print('\nwrote %s (%d rows)' % (OUT.relative_to(WC.ROOT), len(ROWS)))


if __name__ == '__main__':
    main()
