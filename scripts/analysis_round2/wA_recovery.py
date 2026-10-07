#!/usr/bin/env python3
"""
Round 2 · workstream A -- Recovery: what makes operators ATTEMPT a fix?

Variant menu: docs/analysis/HYPOTHESES_ROUND2.md §4.A (+ 2026-10-07 amendment). Builds on round-1 H3
(scripts/analysis_round1/h3_recovery.py: episode reconstruction with corrected fixability, attempt
classification, Suggest-press reconstruction). Read-only on Results/. Writes only
docs/analysis/round2/wA_specs.csv; prints every number the report quotes.

    C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wA_recovery.py
"""
import math, sys, warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wA_common as c   # noqa: E402

warnings.filterwarnings('ignore')
OUT = c.BASE / 'docs' / 'analysis' / 'round2' / 'wA_specs.csv'
SEED = 20261007
ROWS = []

SAMPLES = {
    'S-all': lambda d: d,
    'S-v112': lambda d: d[d.v112person == 1],
    'S-s1': lambda d: d[d.run == 1],
    'S-27': lambda d: d[d.swapped == 0],
    'S-6': lambda d: d[d.swapped == 1],
}


def fmt(x, k=3):
    return '' if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), k)


def prep_within(d, xs):
    for x in xs:
        d = c.add_within(d, x)
    return d


def fit_on(d, formula, term, within, binomial=True):
    d = prep_within(d, within)
    return c.est(formula, d, term, binomial), d


def gates(base, formula, term, within, ref_sign, binomial=True, loo=True):
    """s1 direction, both scenario orders, leave-one-person-out sign flips (vs the S-all sign)."""
    g = {}
    r, _ = fit_on(base[base.run == 1], formula, term, within, binomial)
    g['s1'] = 'na' if r is None else int(c.sign(r['b']) == ref_sign)
    o = []
    for od in ('strategic', 'tactical'):
        r, _ = fit_on(base[base.order == od], formula, term, within, binomial)
        o.append(None if r is None else c.sign(r['b']) == ref_sign)
    g['orders'] = 'na' if None in o else int(all(o))
    g['orderEst'] = o
    if loo:
        bs = []
        for p in sorted(base.pid.unique()):
            r, _ = fit_on(base[base.pid != p], formula, term, within, binomial)
            if r is not None:
                bs.append((p, r['b']))
        flips = [p for p, b in bs if c.sign(b) != ref_sign]
        g['loo'] = int(bool(flips)) if bs else 'na'
        g['looRange'] = (min(b for _, b in bs), max(b for _, b in bs)) if bs else None
        g['looFlips'] = flips
    else:
        g['loo'], g['looRange'], g['looFlips'] = 'na', None, []
    return g


def spec(vid, desc, base, outcome, predictor, formula, term, within=(), expected='none', extra=0,
         samples=('S-all', 'S-v112', 'S-s1', 'S-27', 'S-6'), model='GEE logit (bias-reduced)',
         binomial=True, notes='', loo=True):
    """Fit one specification on each sample; gates computed for the S-all row."""
    out = []
    for sc in samples:
        d = SAMPLES[sc](base)
        r, dd = fit_on(d, formula, term, within, binomial)
        row = dict(workstream='A', variant_id=vid, extra=extra, description=desc, sample=sc,
                   outcome=outcome, predictor=predictor, model=model,
                   estimate='', ci_lo='', ci_hi='', estimate_scale='OR' if binomial else 'b', p='',
                   n_obs=len(dd), n_people=int(dd.pid.nunique()), expected_direction=expected,
                   s1_same_direction='na', both_orders_same_direction='na', loo_sign_flip='na',
                   notes=notes + ('; descriptive only (6 clusters)' if sc == 'S-6' else ''))
        if r is None:
            row['notes'] += '; model did not fit (too few events / no variation)'
        else:
            f = math.exp if binomial else (lambda v: v)
            row.update(estimate=fmt(f(r['b'])), ci_lo=fmt(f(r['lo'])), ci_hi=fmt(f(r['hi'])), p=fmt(r['p'], 4))
            if sc == 'S-all':
                g = gates(base, formula, term, within, c.sign(r['b']), binomial, loo)
                row.update(s1_same_direction=g['s1'], both_orders_same_direction=g['orders'],
                           loo_sign_flip=g['loo'])
                if g['looRange']:
                    lo, hi = g['looRange']
                    row['notes'] += f"; LOO range {fmt(f(lo))}..{fmt(f(hi))}" + \
                                    (f" (flips: {','.join(g['looFlips'])})" if g['looFlips'] else '')
        out.append(row)
        ROWS.append(row)
        print(f"  {vid:10s} {sc:7s} {predictor:22s} est={row['estimate']!s:>7} [{row['ci_lo']!s}, {row['ci_hi']!s}] "
              f"p={row['p']!s:7} n={row['n_obs']}/{row['n_people']} gates s1={row['s1_same_direction']} "
              f"ord={row['both_orders_same_direction']} looFlip={row['loo_sign_flip']} {row['notes'][:90]}")
    return out


def add_row(**kw):
    row = dict(workstream='A', extra=0, s1_same_direction='na', both_orders_same_direction='na',
               loo_sign_flip='na', notes='', ci_lo='', ci_hi='')
    row.update(kw)
    ROWS.append(row)
    print(f"  {row['variant_id']:10s} {row['sample']:7s} {row['predictor']:22s} est={row['estimate']} "
          f"[{row['ci_lo']}, {row['ci_hi']}] p={row['p']} n={row['n_obs']}/{row['n_people']} {row['notes'][:100]}")


def cond_logit(d, y, x):
    from statsmodels.discrete.conditional_models import ConditionalLogit
    k = d.groupby('pid').filter(lambda g: g[y].nunique() > 1 and g[x].nunique() > 1)
    if k.pid.nunique() < 3:
        return None, k
    try:
        m = ConditionalLogit(k[y].values, k[[x]].values, groups=k.pid.values).fit(disp=0)
        b, se = float(m.params[0]), float(m.bse[0])
        return dict(b=b, lo=b - 1.96 * se, hi=b + 1.96 * se, p=float(m.pvalues[0])), k
    except Exception:
        return None, k


def spearman_gates(FX, col):
    """Gates for a person-level Spearman of attempt rate on a person score."""
    def rho(d):
        g = d.groupby('pid').agg(rate=('attempted', 'mean'), x=(col, 'first'))
        return stats.spearmanr(g.x, g.rate)[0] if len(g) > 3 and g.rate.nunique() > 1 else None
    full = rho(FX)
    s1 = rho(FX[FX.run == 1])
    o = [rho(FX[FX.order == od]) for od in ('strategic', 'tactical')]
    loo = [rho(FX[FX.pid != p]) for p in sorted(FX.pid.unique())]
    loo = [x for x in loo if x is not None]
    return dict(s1_same_direction=int(c.sign(s1) == c.sign(full)) if s1 is not None else 'na',
                both_orders_same_direction=int(all(c.sign(x) == c.sign(full) for x in o)) if None not in o else 'na',
                loo_sign_flip=int(any(c.sign(x) != c.sign(full) for x in loo)),
                notes=f'ties: most people attempt every fixable failure; s1 rho {fmt(s1, 2)}, orders rho '
                      f'{fmt(o[0], 2)} (Strategic first) / {fmt(o[1], 2)} (Tactical first); LOO rho range '
                      f'{fmt(min(loo), 2)}..{fmt(max(loo), 2)}')


def main():
    df = c.load_episodes()
    pc1, ev, load = c.pc1_scores()
    pc1x, evx, loadx = c.pc1_scores(drop=('recSug',))
    df['pc1'] = df.pid.map(pc1)
    df['pc1_noRec'] = df.pid.map(pc1x)
    df['solvedPress'] = df.presses_detail.map(lambda ps: int(any(p['result'] == 'solved' for p in ps)))
    df['failedPress'] = df.presses_detail.map(lambda ps: int(any(p['result'] in ('failed', 'partial') for p in ps)))
    df['notClean'] = 1 - df.suggestClean
    df['suggestUsed'] = (df.suggest > 0).astype(int)
    df['needsChain'] = (~df.fixIdleLogged).astype(int)
    df['pc1XnotClean'] = df.pc1 * df.notClean
    df['pc1XpressFail'] = df.pc1 * df.failedPress

    print(f'episodes {len(df)} from {df.pid.nunique()} people; outcomes {dict(Counter(df.outcome))}')
    print(f'PC1 (all 10 features): {ev:.3f} of variance; loadings {load}')
    print(f'PC1 without recSug: {evx:.3f}; loadings {loadx}; corr with full PC1 = {np.corrcoef(pc1, pc1x)[0, 1]:.3f}')

    FX = df[df.fixAll].copy()                                   # fixable with drones already on the mission
    RES = FX[FX.outcome != 'unresolved'].copy()                 # H3's sample (resolved fixable)
    print(f'\nfixable episodes {len(FX)} ({FX.pid.nunique()} people); resolved {len(RES)}')
    print('attempt x outcome (fixable):\n', pd.crosstab(FX.attempted, FX.outcome))
    pr = FX.groupby('pid').attempted.mean()
    print('people with within-person variation in attempting:', sorted(pr[(pr > 0) & (pr < 1)].index),
          '| never attempt:', sorted(pr[pr == 0].index), '| always:', int((pr == 1).sum()))
    na = FX[FX.attempted == 0]
    print('non-attempts by person:', dict(Counter(na.pid)))

    # ------------------------------------------------------------------ descriptives for A1
    print('\n## Descriptives: time left at the failure')
    FX['tbin'] = pd.cut(FX.timeLeft * 60, [0, 90, 180, 300, 480], right=True)
    print(FX.groupby('tbin').agg(n=('attempted', 'size'), attempted=('attempted', 'mean'),
                                 abandoned=('abandoned', 'mean'), leftOpen=('unresolved', 'mean'),
                                 finishable=('finishable', 'mean')).round(2))
    print('failure times recur across people on the same game (seeded hazard): top repeated (game, elapsed):',
          Counter(zip(FX.game, FX.opened.round(0))).most_common(6))

    # =========================================================================== A1 · time left
    print('\n## A1 · time left in the session at the failure')
    W = ('timeLeft',)
    spec('A1a', 'Attempted (drag or Suggest) vs not, by minutes left at the failure; within-person part', FX,
         'attempted', 'timeLeft_w (per min)', 'attempted ~ timeLeft_w + timeLeft_b', 'timeLeft_w', W, '+')
    spec('A1a-game', 'A1a + game fixed effect + run', FX, 'attempted', 'timeLeft_w (per min)',
         'attempted ~ timeLeft_w + timeLeft_b + C(game) + run2', 'timeLeft_w', W, '+', samples=('S-all', 'S-v112', 'S-27'))
    spec('A1a-pool', 'Attempted by minutes left, pooled (total association, not split within/between)', FX,
         'attempted', 'timeLeft (per min)', 'attempted ~ timeLeft', 'timeLeft', (), '+', samples=('S-all', 'S-v112', 'S-s1', 'S-27'))
    r, k = cond_logit(FX, 'attempted', 'timeLeft')
    add_row(variant_id='A1a-cl', description='Attempted by minutes left, conditional (fixed-effect) logit: purely within person',
            sample='S-all', outcome='attempted', predictor='timeLeft (per min)', model='conditional logit',
            estimate=fmt(math.exp(r['b'])) if r else '', ci_lo=fmt(math.exp(r['lo'])) if r else '',
            ci_hi=fmt(math.exp(r['hi'])) if r else '', estimate_scale='OR', p=fmt(r['p'], 4) if r else '',
            n_obs=len(k), n_people=int(k.pid.nunique()), expected_direction='+',
            notes='only people with both attempted and not-attempted episodes are informative')
    spec('A1b', 'Attempted by whether the repaired task could still finish before the buzzer '
                '(time left > affected task base time + 15 s travel); within-person', FX,
         'attempted', 'finishable_w', 'attempted ~ finishable_w + finishable_b', 'finishable_w', ('finishable',), '+',
         notes='scoring: unfinished tasks earn 0 at the buzzer; penalty is the same whether abandoned (residual accrues) or not')
    spec('A1c', 'Attempted by failure in the final 90 s; within-person', FX,
         'attempted', 'last90_w', 'attempted ~ last90_w + last90_b', 'last90_w', ('last90',), '-')
    spec('A1d', 'Abandoned vs recovered (H3 sample: resolved fixable) by minutes left; within-person', RES,
         'abandoned', 'timeLeft_w (per min)', 'abandoned ~ timeLeft_w + timeLeft_b', 'timeLeft_w', W, '-',
         notes='"rational triage" predicts more abandonment late, i.e. negative')
    spec('A1d-game', 'A1d + game fixed effect + run', RES, 'abandoned', 'timeLeft_w (per min)',
         'abandoned ~ timeLeft_w + timeLeft_b + C(game) + run2', 'timeLeft_w', W, '-', samples=('S-all', 'S-v112', 'S-27'))

    # =========================================================================== A2 · stakes
    print('\n## A2 · reward at stake, mission size, drones left on the mission')
    spec('A2a', 'Attempted by reward still at stake on the mission (incomplete tasks, per 100 pts; P01/P02 rescaled x2)', FX,
         'attempted', 'reward_w (per 100)', 'attempted ~ reward_w + reward_b', 'reward_w', ('reward',), '+')
    spec('A2b', 'Attempted by number of tasks left on the mission', FX,
         'attempted', 'nTasksLeft_w', 'attempted ~ nTasksLeft_w + nTasksLeft_b', 'nTasksLeft_w', ('nTasksLeft',), '+')
    spec('A2c', 'Attempted by drones still on the mission (idle + executing) at the failure', FX,
         'attempted', 'dronesLeft_w', 'attempted ~ dronesLeft_w + dronesLeft_b', 'dronesLeft_w', ('dronesLeft',), '+')
    spec('A2d', 'Abandoned vs recovered (resolved fixable) by reward at stake', RES,
         'abandoned', 'reward_w (per 100)', 'abandoned ~ reward_w + reward_b', 'reward_w', ('reward',), '-')
    jW = ('timeLeft', 'reward', 'dronesLeft')
    jf = 'attempted ~ timeLeft_w + reward_w + dronesLeft_w + timeLeft_b + reward_b + dronesLeft_b + C(game) + run2'
    for t, lab, e in (('reward_w', 'reward_w (per 100)', '+'), ('dronesLeft_w', 'dronesLeft_w', '+'),
                      ('timeLeft_w', 'timeLeft_w (per min)', '+')):
        spec('A2e', 'Joint model: time left + reward + drones left (within parts), + game FE + run', FX,
             'attempted', lab, jf, t, jW, e, samples=('S-all', 'S-v112', 'S-27'))

    # =========================================================================== A3 · recent failures
    print('\n## A3 · recent failures')
    spec('A3a', 'Attempted by number of other drone failures in the previous 60 s (any mission)', FX,
         'attempted', 'recentFail60_w', 'attempted ~ recentFail60_w + recentFail60_b', 'recentFail60_w', ('recentFail60',), '-')
    spec('A3b', 'Attempted by another recovery already open on a different mission at the failure', FX,
         'attempted', 'concurrentRec_w', 'attempted ~ concurrentRec_w + concurrentRec_b', 'concurrentRec_w', ('concurrentRec',), '-',
         notes='only 15 episodes with a concurrent recovery')
    spec('A3c', 'Attempted by a second failure on the same mission (earlier recovery on it this session)', FX,
         'attempted', 'priorSameMission_w', 'attempted ~ priorSameMission_w + priorSameMission_b', 'priorSameMission_w',
         ('priorSameMission',), '-', notes='only 11 second-failure episodes; post-failure grace (v1.5+) blocks a repeat for 30 s')
    spec('A3d', 'Abandoned vs recovered (resolved fixable) by failures in the previous 60 s', RES,
         'abandoned', 'recentFail60_w', 'abandoned ~ recentFail60_w + recentFail60_b', 'recentFail60_w', ('recentFail60',), '+')
    # A3 null: permute recentFail60 within person (keeps who-has-many-failures); calibrated p for A3a
    d0 = c.add_within(FX, 'recentFail60')
    obs = c.est('attempted ~ recentFail60_w + recentFail60_b', d0, 'recentFail60_w')
    rng = np.random.default_rng(SEED)
    null = []
    for _ in range(300):
        dd = FX.copy()
        dd['recentFail60'] = dd.groupby('pid').recentFail60.transform(lambda v: rng.permutation(v.values))
        dd = c.add_within(dd, 'recentFail60')
        r = c.est('attempted ~ recentFail60_w + recentFail60_b', dd, 'recentFail60_w')
        if r:
            null.append(r['b'])
    null = np.array(null)
    cp = float(np.mean(np.abs(null) >= abs(obs['b']))) if obs and len(null) else None
    print(f'  A3a null (within-person permutation, {len(null)} sims): null b mean {null.mean():+.3f}, '
          f'sd {null.std():.3f}; observed {obs["b"] if obs else None}; calibrated two-sided p = {cp}')
    for r_ in ROWS:
        if r_['variant_id'] == 'A3a' and r_['sample'] == 'S-all':
            r_['notes'] += f'; within-person permutation null calibrated p = {fmt(cp)}'

    # =========================================================================== A4 · reliance axis
    print('\n## A4 · the person\'s position on the reliance axis (PC1, recomputed, no bootstrap)')
    spec('A4a', 'Attempted by the person\'s reliance-axis score (PC1, between-person)', FX,
         'attempted', 'pc1 (per unit)', 'attempted ~ pc1', 'pc1', (), '+',
         notes='PC1 includes recSug (share of recovery episodes with Suggest), which overlaps the outcome; see X1')
    spec('A4a-game', 'A4a + game FE + run', FX, 'attempted', 'pc1 (per unit)', 'attempted ~ pc1 + C(game) + run2',
         'pc1', (), '+', samples=('S-all', 'S-v112', 'S-27'))
    spec('A4b', 'Abandoned vs recovered (resolved fixable) by PC1', RES,
         'abandoned', 'pc1 (per unit)', 'abandoned ~ pc1', 'pc1', (), '-')
    # person-level Spearman
    P = FX.groupby('pid').agg(rate=('attempted', 'mean'), n=('attempted', 'size'), pc1=('pc1', 'first'),
                              pc1x=('pc1_noRec', 'first'), swapped=('swapped', 'first'), v112=('v112person', 'first'))
    for sc, sub in (('S-all', P), ('S-v112', P[P.v112 == 1]), ('S-27', P[P.swapped == 0])):
        rho, p = stats.spearmanr(sub.pc1, sub.rate)
        add_row(variant_id='A4c', description='Person-level: share of own fixable failures attempted vs PC1 (Spearman)',
                sample=sc, outcome='attempt rate (person)', predictor='pc1', model='Spearman',
                estimate=fmt(rho), estimate_scale='rho', p=fmt(p, 4), n_obs=len(sub), n_people=len(sub),
                expected_direction='+', **(spearman_gates(FX, 'pc1') if sc == 'S-all' else
                                           dict(notes='ties: most people attempt every fixable failure')))
    print('  never-attempters PC1:', P[P.rate == 0].pc1.round(2).to_dict(), '| median PC1 of others',
          round(P[P.rate > 0].pc1.median(), 2))

    # =========================================================================== A5 · opposite
    print('\n## A5 · opposite: do high-reliance operators abandon MORE when Suggest has no clean fix?')
    print('  fixable episodes where Suggest (pressed at the failure) would NOT have covered the task:',
          int(FX.notClean.sum()), '| outcomes', dict(Counter(FX[FX.notClean == 1].outcome)))
    spec('A5a', 'Abandoned (resolved fixable) ~ PC1 x [Suggest could not cover it at the failure]', RES,
         'abandoned', 'pc1 x notClean', 'abandoned ~ pc1 + notClean + pc1XnotClean', 'pc1XnotClean', (), '+',
         samples=('S-all', 'S-v112', 'S-27'), notes='only 8 fixable not-clean episodes (7 resolved)')
    spec('A5b', 'Abandoned (resolved fixable) ~ PC1 x [a Suggest press in the episode failed or was partial]', RES,
         'abandoned', 'pc1 x pressFailed', 'abandoned ~ pc1 + failedPress + pc1XpressFail', 'pc1XpressFail', (), '+',
         samples=('S-all', 'S-v112', 'S-27'), notes='11 fixable episodes with a failed/partial press')
    nc = FX[FX.notClean == 1]
    print('  not-clean fixable episodes:', nc[['pid', 'outcome', 'attempted', 'pc1']].round(2).to_dict('records'))

    # =========================================================================== A6 · abandoning a working plan
    print('\n## A6 · abandoning a working (solved) Suggest plan')
    S6 = RES[RES.solvedPress == 1].copy()
    print(f'  resolved fixable episodes with a solved press: {len(S6)}; abandoned {int(S6.abandoned.sum())} '
          f'from {S6[S6.abandoned == 1].pid.nunique()} people: {dict(Counter(S6[S6.abandoned == 1].pid))}')
    spec('A6a', 'Among episodes where Suggest returned a complete plan: abandoned ~ PC1 (who)', S6,
         'abandoned', 'pc1 (per unit)', 'abandoned ~ pc1', 'pc1', (), 'none', samples=('S-all', 'S-v112', 'S-27'))
    spec('A6b', 'Among solved-press episodes: abandoned ~ minutes left (when), pooled', S6,
         'abandoned', 'timeLeft (per min)', 'abandoned ~ timeLeft', 'timeLeft', (), '-', samples=('S-all', 'S-v112', 'S-27'))
    spec('A6c', 'Among solved-press episodes: abandoned ~ reward at stake, pooled', S6,
         'abandoned', 'reward (per 100)', 'abandoned ~ reward', 'reward', (), '-', samples=('S-all', 'S-v112', 'S-27'))
    spec('A6d', 'Among solved-press episodes: abandoned ~ the fix needed a drone already heading to another task '
                '(not coverable by truly idle drones, so Suggest\'s plan chains it)', S6,
         'abandoned', 'needsChain', 'abandoned ~ needsChain', 'needsChain', (), '+', samples=('S-all', 'S-v112', 'S-27'))
    print('  solved-press episodes, abandoned vs recovered means:')
    print(S6.groupby('outcome')[['timeLeft', 'reward', 'dronesLeft', 'nTasksLeft', 'needsChain', 'pc1', 'run2']].mean().round(2))
    S6['pressToEnd'] = S6.closedAt - S6.presses_detail.map(lambda ps: ps[-1]['at'])
    print('  press->close (s), abandoned:', S6[S6.abandoned == 1].pressToEnd.round(1).tolist())
    # those people's other solved-press episodes
    ab_people = sorted(S6[S6.abandoned == 1].pid.unique())
    print('  same people, other solved-press episodes recovered:',
          {p: int(((S6.pid == p) & (S6.abandoned == 0)).sum()) for p in ab_people})

    # =========================================================================== A7 · after a Suggest failure
    print('\n## A7 · after a Suggest failure: within-person change in later attempt rates')
    allE = df.sort_values(['pid', 'run', 'opened']).copy()
    allE['tkey'] = allE.run * 1000 + allE.opened

    def press_keys(row, cond):
        return [row.run * 1000 + p['at'] for p in row.presses_detail if cond(p)]

    def a7_frame(cond, pseudo=None):
        """Per fixable episode of exposed people: post = opened after the person's first qualifying press."""
        first = {}
        for _, r_ in allE.iterrows():
            for k in press_keys(r_, cond):
                first[r_.pid] = min(first.get(r_.pid, 1e12), k)
        if pseudo is not None:
            first = pseudo
        f = FX.copy()
        f['tkey'] = f.run * 1000 + f.opened
        f = f[f.pid.isin(first)]
        f['ev'] = f.pid.map(first)
        # drop the exposure episode itself (it contains the qualifying press)
        f = f[~((f.tkey <= f.ev) & (f.closedAt + f.run * 1000 >= f.ev))]
        f['post'] = (f.tkey > f.ev).astype(int)
        return f, first

    for vid, lab, cond in (('A7a', 'any failed/partial press', lambda p: p['result'] in ('failed', 'partial')),
                           ('A7b', 'blind-spot press (fix needed a busy drone)', lambda p: p['blind'])):
        f, first = a7_frame(cond)
        both = f.groupby('pid').post.agg(lambda v: 0 < v.mean() < 1)
        print(f'  {vid} [{lab}]: exposed people {len(first)}; with episodes both before and after: {int(both.sum())}')
        print('    cells (post: attempted rate, n):', f.groupby('post').attempted.agg(['mean', 'size']).round(2).to_dict())
        fm = 'attempted ~ post + run2'
        spec(vid, f'Exposed people only: attempted on later fixable failures after their first {lab} vs before (+ run)',
             f, 'attempted', 'post', fm, 'post', (), '-', samples=('S-all', 'S-v112'), loo=True,
             notes='event-defined: see null simulation')
        spec(vid + '-sug', f'Exposed people only: Suggest pressed on later fixable failures after their first {lab} (+ run)',
             f, 'suggestUsed', 'post', 'suggestUsed ~ post + run2', 'post', (), '-', samples=('S-all', 'S-v112'),
             notes='event-defined: see null simulation')
        # null simulation: pseudo-exposure at a random press (any result) of the same person
        obs = c.est(fm, f, 'post')
        presses_by = {}
        for _, r_ in allE.iterrows():
            ks = press_keys(r_, lambda p: True)
            if r_.pid in first and ks:
                presses_by.setdefault(r_.pid, []).extend(ks)
        nulls = []
        rng = np.random.default_rng(SEED + (1 if vid == 'A7b' else 0))
        for _ in range(400):
            ps = {p: rng.choice(v) for p, v in presses_by.items()}
            g, _ = a7_frame(cond, ps)
            r_ = c.est(fm, g, 'post')
            if r_:
                nulls.append(r_['b'])
        nulls = np.array(nulls)
        if obs and len(nulls):
            cp = float(np.mean(nulls <= obs['b']))   # one-sided in the expected (negative) direction
            print(f'    null sim ({len(nulls)}): null mean OR {math.exp(nulls.mean()):.2f}, 5th pct OR '
                  f'{math.exp(np.percentile(nulls, 5)):.2f}; observed OR {math.exp(obs["b"]):.2f}; '
                  f'calibrated one-sided p (null <= observed) = {cp:.3f}')
            for r_ in ROWS:
                if r_['variant_id'] == vid and r_['sample'] == 'S-all':
                    r_['notes'] += (f'; null sim (pseudo-exposure at a random own press, {len(nulls)} sims): '
                                    f'null mean OR {math.exp(nulls.mean()):.2f}, calibrated one-sided p {cp:.3f}')

    # =========================================================================== A8 · three-type only
    print('\n## A8 · constrained: fixable failures on three-type missions only')
    T3 = FX[FX.threeType == 1].copy()
    spec('A8a', 'Three-type missions: attempted ~ minutes left (within-person)', T3,
         'attempted', 'timeLeft_w (per min)', 'attempted ~ timeLeft_w + timeLeft_b', 'timeLeft_w', W, '+')
    spec('A8b', 'Three-type missions: attempted ~ reward at stake (within-person)', T3,
         'attempted', 'reward_w (per 100)', 'attempted ~ reward_w + reward_b', 'reward_w', ('reward',), '+')
    spec('A8c', 'Three-type missions: attempted ~ recent failures (within-person)', T3,
         'attempted', 'recentFail60_w', 'attempted ~ recentFail60_w + recentFail60_b', 'recentFail60_w', ('recentFail60',), '-')
    spec('A8d', 'Three-type missions: attempted ~ PC1', T3, 'attempted', 'pc1 (per unit)', 'attempted ~ pc1', 'pc1', (), '+')
    spec('A8e', 'Three-type missions: abandoned vs recovered ~ minutes left (within-person)', T3[T3.outcome != 'unresolved'],
         'abandoned', 'timeLeft_w (per min)', 'abandoned ~ timeLeft_w + timeLeft_b', 'timeLeft_w', W, '-')

    # =========================================================================== extras
    print('\n## Extras (pre-stated in the report\'s analysis log)')
    spec('X1', 'Attempted ~ PC1 recomputed WITHOUT the recovery-Suggest feature (removes overlap with the outcome)', FX,
         'attempted', 'pc1_noRec (per unit)', 'attempted ~ pc1_noRec', 'pc1_noRec', (), '+', extra=1)
    spec('X1b', 'Abandoned vs recovered ~ PC1 without recSug', RES, 'abandoned', 'pc1_noRec (per unit)',
         'abandoned ~ pc1_noRec', 'pc1_noRec', (), '-', extra=1)
    FXo = FX.copy()
    spec('X2', 'Abandoned (vs recovered OR left open at the buzzer) ~ failure in the final 90 s; within-person. '
               'Scoring makes a late abandonment dominated (it flies executing drones home; the residual cannot finish)',
         FXo, 'abandoned (unresolved = 0)', 'last90_w', 'abandoned ~ last90_w + last90_b', 'last90_w', ('last90',), '-', extra=1)
    for sc, sub in (('S-all', P), ('S-v112', P[P.v112 == 1]), ('S-27', P[P.swapped == 0])):
        rho, p = stats.spearmanr(sub.pc1x, sub.rate)
        add_row(variant_id='X1c', extra=1, description='Person-level: attempt rate vs PC1 without recSug (Spearman)',
                sample=sc, outcome='attempt rate (person)', predictor='pc1_noRec', model='Spearman',
                estimate=fmt(rho), estimate_scale='rho', p=fmt(p, 4), n_obs=len(sub), n_people=len(sub),
                expected_direction='+', **(spearman_gates(FX, 'pc1_noRec') if sc == 'S-all' else
                                           dict(notes='ties: most people attempt every fixable failure')))
    # X3: censoring -- an episode that opens with seconds left cannot show an attempt
    for thr in (31, 60):
        sub = FX[FX.timeLeft * 60 >= thr].copy()
        print(f'  X3 threshold {thr} s: {len(sub)} episodes, not attempted {int((sub.attempted == 0).sum())} '
              f'(left open {int(sub.unresolved.sum())})')
        spec(f'X3-{thr}s', f'A1a excluding failures with < {thr} s left (censoring: no time to act)', sub,
             'attempted', 'timeLeft_w (per min)', 'attempted ~ timeLeft_w + timeLeft_b', 'timeLeft_w', W, '+', extra=1)
        spec(f'X3-{thr}s-pool', f'A1a-pool excluding failures with < {thr} s left', sub,
             'attempted', 'timeLeft (per min)', 'attempted ~ timeLeft', 'timeLeft', (), '+', extra=1,
             samples=('S-all', 'S-v112', 'S-s1', 'S-27'))
        spec(f'X3-{thr}s-fin', f'A1b (fix could finish) excluding failures with < {thr} s left', sub,
             'attempted', 'finishable_w', 'attempted ~ finishable_w + finishable_b', 'finishable_w', ('finishable',), '+',
             extra=1, samples=('S-all', 'S-s1', 'S-27'))
        spec(f'X3-{thr}s-l90', f'A1c (final 90 s) excluding failures with < {thr} s left', sub,
             'attempted', 'last90_w', 'attempted ~ last90_w + last90_b', 'last90_w', ('last90',), '-',
             extra=1, samples=('S-all', 'S-s1', 'S-27'))
    sub = FX[FX.timeLeft * 60 >= 31]
    sub = sub.assign(tbin=pd.cut(sub.timeLeft * 60, [0, 90, 180, 300, 480]))
    print('  attempt rate by time bin, >= 31 s left:\n', sub.groupby('tbin').attempted.agg(['mean', 'size']).round(2))
    # order-specific estimates for gate cells shown as na
    for nm, d_, fml, t, w in (('A1b', FX, 'attempted ~ finishable_w + finishable_b', 'finishable_w', ('finishable',)),
                              ('A1c', FX, 'attempted ~ last90_w + last90_b', 'last90_w', ('last90',))):
        for od in ('strategic', 'tactical'):
            r, dd = fit_on(d_[d_.order == od], fml, t, w)
            raw = dd.groupby(t.split('_')[0]).attempted.agg(['mean', 'size']).round(2).to_dict()
            print(f'  {nm} order={od}: {None if r is None else round(math.exp(r["b"]), 2)}; raw {raw}')
    # A6d / A5 exact descriptives (models did not converge: quasi-separation)
    t6 = pd.crosstab(S6.needsChain, S6.abandoned)
    print('  A6d needsChain x abandoned (solved-press episodes):', t6.to_dict(),
          'Fisher p =', round(stats.fisher_exact(t6.values)[1], 3) if t6.shape == (2, 2) else None)
    t5 = pd.crosstab(RES.notClean, RES.abandoned)
    print('  A5 notClean x abandoned (resolved fixable):', t5.to_dict(), 'Fisher p =', round(stats.fisher_exact(t5.values)[1], 4))
    for vid, d_, x, desc, exp in (
            ('A6d-exact', S6, 'needsChain', 'Solved-press episodes: abandonment rate when the fix needed a drone already '
             'heading to another task minus when it did not (episode-level Fisher exact; ignores clustering)', '+'),
            ('A5-exact', RES, 'notClean', 'Resolved fixable episodes: abandonment rate when Suggest could not cover the '
             'task at the failure minus when it could (episode-level Fisher exact; context for A5, no PC1 term)', '+')):
        a1 = d_[d_[x] == 1].abandoned; a0 = d_[d_[x] == 0].abandoned
        tab = pd.crosstab(d_[x], d_.abandoned).reindex(index=[0, 1], columns=[0, 1], fill_value=0)
        add_row(variant_id=vid, description=desc, sample='S-all', outcome='abandoned', predictor=x,
                model='Fisher exact', estimate=fmt(a1.mean() - a0.mean()), estimate_scale='diff',
                p=fmt(stats.fisher_exact(tab.values)[1], 4), n_obs=len(d_), n_people=int(d_.pid.nunique()),
                expected_direction=exp,
                notes=f'{int(a1.sum())}/{len(a1)} vs {int(a0.sum())}/{len(a0)} abandoned; people with x=1: '
                      f'{sorted(d_[d_[x] == 1].pid.unique())}')
    # descriptive context for X2 / A1: what late outcomes look like
    rec = FX[FX.outcome == 'recovered']
    print('  recovered episodes: affected task(s) completed before the buzzer, by finishable flag:',
          rec.groupby('finishable').affectedDone.agg(['mean', 'size']).round(2).to_dict())
    print('  censored (< 31 s left) episodes that are three-type:', int(((FX.timeLeft * 60 < 31) & (FX.threeType == 1)).sum()),
          'of', int((FX.timeLeft * 60 < 31).sum()))
    late = FX[FX.last90 == 1]
    print('  last-90-s fixable failures: outcome x attempted', pd.crosstab(late.attempted, late.outcome).to_dict())
    print('  not finishable (time left < task time + 15 s):', pd.crosstab(FX[FX.finishable == 0].attempted,
                                                                         FX[FX.finishable == 0].outcome).to_dict())

    # ------------------------------------------------------------------ write
    cols = ['workstream', 'variant_id', 'extra', 'description', 'sample', 'outcome', 'predictor', 'model', 'estimate',
            'ci_lo', 'ci_hi', 'estimate_scale', 'p', 'n_obs', 'n_people', 'expected_direction', 's1_same_direction',
            'both_orders_same_direction', 'loo_sign_flip', 'notes']
    out = pd.DataFrame([r for r in ROWS if r is not None])[cols]
    out['notes'] = out.notes.str.lstrip('; ')
    out.to_csv(OUT, index=False)
    print(f'\nwrote {len(out)} spec rows -> {OUT}')
    ok = out[(out['sample'] == 'S-all') & (out.p != '')].copy()
    ok['p'] = ok.p.astype(float)
    print('S-all rows with p < .05:')
    print(ok[ok.p < .05][['variant_id', 'predictor', 'estimate', 'ci_lo', 'ci_hi', 'p', 's1_same_direction',
                          'both_orders_same_direction', 'loo_sign_flip']].to_string(index=False))


if __name__ == '__main__':
    main()
