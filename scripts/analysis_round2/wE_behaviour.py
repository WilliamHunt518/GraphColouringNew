"""Workstream E2/E3 -- do stated reasons and stated scale rules show up in each person's own behaviour?

E2a  cites SPEED            -> reliance rises more on large missions (cards: 3-type vs 1-type / drones;
                               Suggest: big vs small plan)
E2b  cites VISIBLE ERRORS   -> more manual allocation on single-type missions
E2c  says CAN'T CHECK       -> keeps tactical plans unmodified more
E3   states a scale rule    -> own composition effect larger (interaction), plus person-level rho
X2   (extra) E2/E3 headline tests re-run on the round-1 coder's codes (does the link depend on the coder?)

All GEEs: logistic, clusters = person, independence, bias-reduced (Mancl-DeRouen) errors.
Run: C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wE_behaviour.py
"""
import sys

import numpy as np
import pandas as pd
from scipy import stats

from wE_common import MINE, R1, codes, behaviour, sample, gee, gates

SAMPLES = ['S-all', 'S-v112', 'S-s1', 'S-27', 'S-6']


def person_flags(c):
    f = pd.DataFrame(index=c.index)
    f['spdS'] = c.r_speed.str.contains('S').astype(int)
    f['spdT'] = c.r_speed.str.contains('T').astype(int)
    f['spdAny'] = (c.r_speed != '').astype(int)
    f['visS'] = c.r_visible_err.str.contains('S').astype(int)
    f['ccT'] = c.r_cantcheck.str.contains('T').astype(int)
    f['ccAny'] = (c.r_cantcheck != '').astype(int)
    f['ruleC'] = (c.cond == 'more_assist_when_complex').astype(int)
    f['ruleCsize'] = ((c.cond == 'more_assist_when_complex') & (c.cond_load != '1')).astype(int)
    f['ruleOrd'] = c.cond.map({'more_assist_when_complex': 1, 'more_assist_when_simple': -1}).fillna(0)
    f['ruleCstrat'] = ((c.cond == 'more_assist_when_complex') & c.cond_tier.isin(['strategic', 'both', 'unspecified'])).astype(int)
    f['ruleCtac'] = ((c.cond == 'more_assist_when_complex') & c.cond_tier.isin(['tactical', 'both', 'unspecified'])).astype(int)
    f['ruleNone'] = (c.cond == 'none').astype(int)
    return f


def spec(rows, vid, desc, df, formula, term, outcome, predictor, samples=SAMPLES, extra=0, expected='+', notes='',
         game_fe=True, v112=None, coder='wE'):
    sign = {'+': 1, '-': -1}.get(expected, 0)
    todo = [(s, formula) for s in samples]
    if game_fe:
        todo.append(('S-all', formula + ' + C(game)'))
    for s, f in todo:
        d = sample(df, s, v112)
        r = gee(f, d, term)
        g = gates(f, d, term, sign) if (s == 'S-all') else dict(s1='na', orders='na', loo_flip='na', loo_range='', order_or='')
        label = s + (' +game FE' if 'C(game)' in f else '')
        row = dict(variant_id=vid + ('-gameFE' if 'C(game)' in f else ('' if s == 'S-all' else '-' + s)),
                   extra=extra, description=desc + (' [game fixed effect]' if 'C(game)' in f else ''), sample=s,
                   outcome=outcome, predictor=predictor + ' (%s codes)' % coder,
                   model='logistic GEE, person clusters, bias-reduced SE: ' + f,
                   estimate=np.nan, ci_lo=np.nan, ci_hi=np.nan, estimate_scale='OR', p=np.nan,
                   n_obs=len(d), n_people=d.pid.nunique(), expected_direction=expected,
                   s1_same_direction=g['s1'], both_orders_same_direction=g['orders'], loo_sign_flip=g['loo_flip'],
                   notes='; '.join(x for x in (notes, g['loo_range'], g['order_or'],
                                                'descriptive only' if s == 'S-6' else '') if x))
        if r is None:
            row['notes'] = (row['notes'] + '; model did not converge / not estimable').strip('; ')
            print('%-14s %-9s n=%4d  NOT ESTIMABLE' % (row['variant_id'], label, len(d)))
        else:
            row.update(estimate=r[0], ci_lo=r[1], ci_hi=r[2], p=r[3])
            print('%-14s %-16s OR=%.2f [%.2f, %.2f] p=%.3f n=%d/%d  s1=%s orders=%s looflip=%s %s'
                  % (row['variant_id'], label, r[0], r[1], r[2], r[3], len(d), d.pid.nunique(),
                     g['s1'], g['orders'], g['loo_flip'], g['loo_range']))
        rows.append(row)


def rho_spec(rows, vid, desc, x, y, outcome, predictor, extra=0, expected='+', notes=''):
    d = pd.concat([x.rename('x'), y.rename('y')], axis=1).dropna()
    r, p = stats.spearmanr(d.x, d.y)
    rng = np.random.default_rng(42)
    bs = []
    for _ in range(4000):
        i = rng.integers(0, len(d), len(d))
        b = d.iloc[i]
        if b.x.nunique() > 1 and b.y.nunique() > 1:
            bs.append(stats.spearmanr(b.x, b.y)[0])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    loo = [stats.spearmanr(d.drop(i).x, d.drop(i).y)[0] for i in d.index]
    flip = int(any(np.sign(v) != np.sign(r) for v in loo))
    rows.append(dict(variant_id=vid, extra=extra, description=desc, sample='S-all', outcome=outcome, predictor=predictor,
                     model='Spearman rho, person level, bootstrap CI', estimate=r, ci_lo=lo, ci_hi=hi,
                     estimate_scale='rho', p=p, n_obs=len(d), n_people=len(d), expected_direction=expected,
                     s1_same_direction='na', both_orders_same_direction='na', loo_sign_flip=flip,
                     notes=(notes + '; LOO rho %.2f-%.2f' % (min(loo), max(loo))).strip('; ')))
    print('%-14s rho=%.2f [%.2f, %.2f] p=%.3f n=%d looflip=%d' % (vid, r, lo, hi, p, len(d), flip))


def person_effects(dec, tac):
    g = dec.groupby(['pid', 'ncolours']).took.mean().unstack()
    comp = g[3] - g[1]
    t = tac.groupby(['pid', 'big']).consulted.mean().unstack()
    size = t[1] - t[0]
    return comp, size


def run():
    dec, tac, v112, _ = behaviour()
    rows = []
    mine = person_flags(codes(MINE))
    r1 = person_flags(codes(R1))
    D = dec.join(mine, on='pid')
    T = tac.join(mine, on='pid')
    D13 = D[D.ncolours.isin([1, 3])]
    kw = dict(v112=v112)
    print('people citing: speed-S %d, speed-T %d, visible-error-S %d, cant-check-T %d, any %d, rule-complex %d'
          % (mine.spdS.sum(), mine.spdT.sum(), mine.visS.sum(), mine.ccT.sum(), mine.ccAny.sum(), mine.ruleC.sum()))

    print('\n== E2a speed -> reliance rises on large missions ==')
    spec(rows, 'E2a1', 'cites speed (strategic) x three-type mission -> card taken', D13, 'took ~ three * spdS',
         'three:spdS', 'card taken (1/0), decision', 'speed reason about strategic', **kw)
    spec(rows, 'E2a2', 'cites speed (strategic) x drones needed (z) -> card taken', D, 'took ~ zdrones * spdS',
         'zdrones:spdS', 'card taken (1/0), decision', 'speed reason about strategic', **kw)
    spec(rows, 'E2a3', 'cites speed (tactical) x big plan (> median drones x tasks) -> Suggest consulted', T,
         'consulted ~ big * spdT', 'big:spdT', 'Suggest consulted (1/0), plan', 'speed reason about tactical', **kw)
    spec(rows, 'E2a4', 'cites speed (tactical) x log plan size (z) -> Suggest consulted', T,
         'consulted ~ zlogsize * spdT', 'zlogsize:spdT', 'Suggest consulted (1/0), plan', 'speed reason about tactical', **kw)
    spec(rows, 'E2a5', 'cites speed (any tier) x three-type -> card taken', D13, 'took ~ three * spdAny', 'three:spdAny',
         'card taken (1/0), decision', 'speed reason, any tier', samples=['S-all'], **kw)
    spec(rows, 'E2a6', 'cites speed (any tier) x big plan -> Suggest consulted', T, 'consulted ~ big * spdAny', 'big:spdAny',
         'Suggest consulted (1/0), plan', 'speed reason, any tier', samples=['S-all'], **kw)

    print('\n== E2b visible errors -> more manual on single-type missions ==')
    S1 = D[D.ncolours == 1]
    spec(rows, 'E2b1', 'cites a visible strategic error -> manual allocation on single-type missions', S1,
         'manual ~ visS', 'visS', 'manual allocation (1/0), single-type decisions', 'visible-error reason about strategic', **kw)
    spec(rows, 'E2b2', 'cites a visible strategic error x single-type mission -> manual (relative to three-type)', D13,
         'manual ~ single * visS', 'single:visS', 'manual allocation (1/0), decision', 'visible-error reason about strategic', **kw)
    spec(rows, 'E2b3', 'cites a visible strategic error -> manual allocation, all missions', D, 'manual ~ visS', 'visS',
         'manual allocation (1/0), decision', 'visible-error reason about strategic', samples=['S-all'], **kw)

    print("\n== E2c can't check -> keeps tactical plans unmodified ==")
    spec(rows, 'E2c1', "says can't check the tactical plan -> plan kept unmodified (all plans)", T, 'keep ~ ccT', 'ccT',
         'tactical plan kept unmodified (1/0), plan', "can't-check reason about tactical", **kw)
    spec(rows, 'E2c2', "says can't check the tactical plan -> kept unmodified, consulted plans only", T[T.consulted == 1],
         'keep ~ ccT', 'ccT', 'kept unmodified (1/0), consulted plans', "can't-check reason about tactical", **kw)
    spec(rows, 'E2c3', "says can't check (any tier) -> tactical plan kept unmodified", T, 'keep ~ ccAny', 'ccAny',
         'tactical plan kept unmodified (1/0), plan', "can't-check reason, any tier", samples=['S-all'], **kw)
    spec(rows, 'E2c4', "says can't check the tactical plan -> kept unmodified, adjusting for plan size", T,
         'keep ~ ccT + zlogsize', 'ccT', 'tactical plan kept unmodified (1/0), plan', "can't-check reason about tactical",
         samples=['S-all'], **kw)

    print('\n== E3 stated scale rule vs own composition effect ==')
    spec(rows, 'E3a', 'says more assistant use when complex x three-type -> card taken', D13, 'took ~ three * ruleC',
         'three:ruleC', 'card taken (1/0), decision', 'stated scale rule (complex)', **kw)
    spec(rows, 'E3b', 'rule about strategic/both/unspecified tier x three-type -> card taken', D13,
         'took ~ three * ruleCstrat', 'three:ruleCstrat', 'card taken (1/0), decision', 'stated scale rule, strategic-relevant',
         samples=['S-all'], **kw)
    spec(rows, 'E3c', 'says more assistant use when complex x big plan -> Suggest consulted', T, 'consulted ~ big * ruleC',
         'big:ruleC', 'Suggest consulted (1/0), plan', 'stated scale rule (complex)', **kw)
    spec(rows, 'E3d', 'rule about tactical/both/unspecified tier x big plan -> Suggest consulted', T,
         'consulted ~ big * ruleCtac', 'big:ruleCtac', 'Suggest consulted (1/0), plan', 'stated scale rule, tactical-relevant',
         samples=['S-all'], **kw)
    spec(rows, 'E3e', 'size-only rule (load-framed rules excluded) x big plan -> Suggest consulted', T,
         'consulted ~ big * ruleCsize', 'big:ruleCsize', 'Suggest consulted (1/0), plan', 'stated size rule (not load)',
         samples=['S-all'], **kw)
    comp, size = person_effects(dec, tac)
    rho_spec(rows, 'E3f', 'stated rule (+1 complex / 0 none / -1 simple) vs own card composition effect (3-type minus 1-type uptake)',
             mine.ruleOrd, comp, 'person composition effect, strategic', 'stated rule, ordinal')
    rho_spec(rows, 'E3g', 'stated rule (ordinal) vs own Suggest size effect (big minus small consult rate)',
             mine.ruleOrd, size, 'person size effect, tactical', 'stated rule, ordinal')

    print('\n== X2 (extra) headline links on the round-1 codes ==')
    D1 = dec.join(r1, on='pid')
    T1 = tac.join(r1, on='pid')
    D113 = D1[D1.ncolours.isin([1, 3])]
    for vid, desc, df, f, term, out, pred in (
            ('X2-E2a1', 'E2a1 on round-1 codes', D113, 'took ~ three * spdS', 'three:spdS', 'card taken', 'speed reason about strategic'),
            ('X2-E2a3', 'E2a3 on round-1 codes', T1, 'consulted ~ big * spdT', 'big:spdT', 'Suggest consulted', 'speed reason about tactical'),
            ('X2-E2b2', 'E2b2 on round-1 codes', D113, 'manual ~ single * visS', 'single:visS', 'manual allocation', 'visible-error reason'),
            ('X2-E2c1', 'E2c1 on round-1 codes', T1, 'keep ~ ccT', 'ccT', 'plan kept unmodified', "can't-check reason"),
            ('X2-E3a', 'E3a on round-1 codes', D113, 'took ~ three * ruleC', 'three:ruleC', 'card taken', 'stated scale rule'),
            ('X2-E3c', 'E3c on round-1 codes', T1, 'consulted ~ big * ruleC', 'big:ruleC', 'Suggest consulted', 'stated scale rule')):
        spec(rows, vid, desc, df, f, term, out, pred, samples=['S-all'], extra=1, game_fe=False, coder='round-1', **kw)

    # descriptive: raw rates by group for the report
    print('\n== descriptives ==')
    for flag, dd, col, by in (('spdS', D13, 'took', 'three'), ('spdT', T, 'consulted', 'big'), ('visS', D13, 'manual', 'single'),
                              ('ccT', T, 'keep', None), ('ruleC', D13, 'took', 'three'), ('ruleC', T, 'consulted', 'big')):
        pp = dd.groupby(['pid'] + ([by] if by else []))[col].mean()
        if by:
            pe = pp.unstack()
            eff = (pe[1] - pe[0]).rename('eff').to_frame().join(mine[flag])
            print('%s: person-level %s effect (%s=1 minus 0), median by %s: %s'
                  % (flag, col, by, flag, eff.groupby(flag).eff.median().round(3).to_dict()))
        else:
            print('%s: person %s rate median by flag: %s' % (flag, col, pp.to_frame().join(mine[flag]).groupby(flag)[col].median().round(3).to_dict()))
    return rows


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run()
