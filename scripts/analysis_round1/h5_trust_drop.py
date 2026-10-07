"""H5 -- does the drop in strategic trust follow the operator's own session-1 experience?

    C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h5_trust_drop.py

Primary (pre-registered, docs/analysis/HYPOTHESES_ROUND1.md §3 H5):
  Spearman rho( trust_s[run 2] - trust_s[run 1],
                number of session-1 missions that failed or were abandoned after a card was taken ).
  Support = rho < 0 with the 95% interval excluding 0.

Operationalisation (decided here, justified in the report):
  * "session 1" = the first session the participant played (run 1).
  * A mission counts as "card" when its FINAL strategic_choice in that session was Aggressive or
    Conservative (3 missions in the dataset were allocated twice; the allocation in force is the
    last one).
  * "failed or abandoned" = mission_abandoned, or mission_completed with outcome partial /
    none_completed. Missions still in flight at the buzzer are not counted (the operator never saw
    them fail; the timer cut them).
  * Residuals are their own missions (see h5_h8_common docstring); a parent's abandonment counts
    once, against the parent's allocation.
  * trust_s / trust_t = mean of the six 1-7 items of the post-session trust scale (builder's
    load_people).
Everything else printed is exploratory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

import h5_h8_common as H

pd.set_option('display.width', 160)


def mission_level(dec: pd.DataFrame) -> pd.DataFrame:
    """One row per (pid, run, mission): the allocation in force (last choice) and its fate."""
    return dec.sort_values('idx').groupby(['pid', 'run', 'missionId'], as_index=False).last()


def build_people(dec: pd.DataFrame, sess: pd.DataFrame) -> pd.DataFrame:
    mis = mission_level(dec)
    mis['bad'] = mis.fate.isin(H.BAD_FATES).astype(int)
    mis['resolved'] = (mis.fate != 'inflight').astype(int)

    per_run = {}
    for (pid, run), g in mis.groupby(['pid', 'run']):
        card, man = g[g.took == 1], g[g.took == 0]
        per_run[(pid, run)] = dict(
            card_bad=int(card.bad.sum()), manual_bad=int(man.bad.sum()),
            card_n=int(len(card)), manual_n=int(len(man)),
            card_resolved=int(card.resolved.sum()),
            card_abandoned=int((card.fate == 'abandoned').sum()),
            card_partial=int(card.fate.isin(['partial', 'none_completed']).sum()),
            cons_bad=int(card[card.choice == 'conservative'].bad.sum()),
            aggr_bad=int(card[card.choice == 'aggressive'].bad.sum()),
            odd_seen=int(dec[(dec.pid == pid) & (dec.run == run)].odd.sum()))

    ev_counts = {}
    for pid, run, events in H.session_events():
        ev_counts[(pid, run)] = dict(
            drone_failures=sum(e['type'] == 'drone_failure' for e in events),
            abandoned=sum(e['type'] == 'mission_abandoned' for e in events))

    bench = B_benchmark(dec)

    rows = []
    for pid, g in sess.groupby('pid'):
        r = {int(x.run): x for x in g.itertuples()}
        if 1 not in r or 2 not in r:
            continue
        a, b = r[1], r[2]
        row = dict(pid=pid, version=a.version, order='SF' if a.scenario == 'strategic' else 'TF',
                   trust_s1=a.trust_s, trust_s2=b.trust_s, trust_t1=a.trust_t, trust_t2=b.trust_t,
                   took1=a.took, took2=b.took)
        for run in (1, 2):
            for k, v in per_run.get((pid, run), {}).items():
                row['%s_%d' % (k, run)] = v
            for k, v in ev_counts.get((pid, run), {}).items():
                row['%s_%d' % (k, run)] = v
            row['bench_%d' % run] = bench.get((pid, run), np.nan)
        rows.append(row)
    p = pd.DataFrame(rows)
    p['d_trust_s'] = p.trust_s2 - p.trust_s1
    p['d_trust_t'] = p.trust_t2 - p.trust_t1
    p['card_bad_rate_1'] = p.card_bad_1 / p.card_n_1.replace(0, np.nan)
    p['card_bad_rate_res_1'] = p.card_bad_1 / p.card_resolved_1.replace(0, np.nan)
    return p


def B_benchmark(dec):
    """Share of the near-perfect-operator benchmark score per session (builder's benchmark())."""
    ref = H.B._quietly(H.B.load_decisions)
    out = H.B.benchmark(ref)
    return {(s['pid'], s['run']): s['share'] for s in out.get('sessions', [])}


def ols(formula, data):
    return smf.ols(formula, data).fit(cov_type='HC3')


def main():
    dec = H.decisions()
    sess = H.sessions()
    P = build_people(dec, sess)
    pv = H.versions()
    v12 = H.v112plus(pv)

    print('=' * 88)
    print('H5 · data')
    print('=' * 88)
    print('participants with trust after both sessions: %d (P09 excluded); v1.12+: %d'
          % (P.d_trust_s.notna().sum(), P[P.pid.isin(v12)].d_trust_s.notna().sum()))
    print('strategic trust: s1 mean %.2f -> s2 mean %.2f; fell for %d, rose for %d, same %d'
          % (P.trust_s1.mean(), P.trust_s2.mean(), (P.d_trust_s < 0).sum(),
             (P.d_trust_s > 0).sum(), (P.d_trust_s == 0).sum()))
    print('tactical trust:  s1 mean %.2f -> s2 mean %.2f' % (P.trust_t1.mean(), P.trust_t2.mean()))
    print('\nSession-1 card missions that failed/were abandoned, per person:')
    print('  distribution:', P.card_bad_1.value_counts().sort_index().to_dict())
    print('  total %d (abandoned %d, partial/none %d) out of %d session-1 card missions '
          '(%d resolved before the buzzer)'
          % (P.card_bad_1.sum(), P.card_abandoned_1.sum(), P.card_partial_1.sum(),
             P.card_n_1.sum(), P.card_resolved_1.sum()))
    print('  of which after Conservative %d, after Aggressive %d'
          % (P.cons_bad_1.sum(), P.aggr_bad_1.sum()))
    print('  session-1 manual missions failed/abandoned: total %d of %d'
          % (P.manual_bad_1.sum(), P.manual_n_1.sum()))

    print('\n' + '=' * 88)
    print('H5 · PRIMARY  rho(change in strategic trust, # s1 card missions failed/abandoned)')
    print('=' * 88)
    prim = H.spearman_ci(P.card_bad_1, P.d_trust_s)
    print('  ALL      ' + H.fmt_rho(prim))
    print('  detectable |rho| at 80%% power, n=%d: %.2f' % (prim['n'], H.detectable_rho(prim['n'])))
    verdict = 'SUPPORTED' if (prim['rho'] < 0 and prim['hi'] < 0) else 'NOT SUPPORTED'
    print('  verdict (rho<0, Fisher-z CI excludes 0): %s' % verdict)
    Q = P[P.pid.isin(v12)]
    s12 = H.spearman_ci(Q.card_bad_1, Q.d_trust_s)
    print('  v1.12+   ' + H.fmt_rho(s12))

    print('\nRobustness (pre-registered variant): normalised by number of session-1 card missions')
    for lab, col in (('per card mission', 'card_bad_rate_1'),
                     ('per RESOLVED card mission', 'card_bad_rate_res_1')):
        print('  %-26s ALL    %s' % (lab, H.fmt_rho(H.spearman_ci(P[col], P.d_trust_s))))
        print('  %-26s v1.12+ %s' % (lab, H.fmt_rho(H.spearman_ci(Q[col], Q.d_trust_s))))

    print('\nRobustness: partial Spearman controlling for scenario order (SF/TF) -- the change score')
    print('carries +/- the scenario effect depending on order, and order sets session-1 workload.')
    sub = P.dropna(subset=['d_trust_s'])
    r, p, n = H.partial_spearman(sub.card_bad_1, sub.d_trust_s,
                                 pd.get_dummies(sub.order, drop_first=True))
    print('  partial rho = %+.3f, p = %.3f, n = %d' % (r, p, n))
    print('  card_bad_1 by order:', sub.groupby('order').card_bad_1.agg(['mean', 'size']).round(2).to_dict())
    print('  d_trust_s by order: ', sub.groupby('order').d_trust_s.agg(['mean', 'size']).round(2).to_dict())

    print('\n' + '=' * 88)
    print('H5 · SECONDARY (exploratory)')
    print('=' * 88)
    print('\n(a) Discriminant: same predictor vs change in TACTICAL trust (should be ~0)')
    disc = H.spearman_ci(P.card_bad_1, P.d_trust_t)
    print('  ALL    ' + H.fmt_rho(disc))
    print('  v1.12+ ' + H.fmt_rho(H.spearman_ci(Q.card_bad_1, Q.d_trust_t)))

    print('\n(b) Other session-1 predictors, one at a time vs change in strategic trust')
    for col, lab in (('manual_bad_1', 'missions failed/abandoned after MANUAL'),
                     ('drone_failures_1', 'drone failures experienced'),
                     ('abandoned_1', 'missions abandoned (any route)'),
                     ('bench_1', 'score share of near-perfect benchmark'),
                     ('cons_bad_1', 'failed/abandoned after CONSERVATIVE'),
                     ('aggr_bad_1', 'failed/abandoned after AGGRESSIVE'),
                     ('odd_seen_1', 'illogical Conservative cards seen'),
                     ('card_n_1', 'card missions (exposure)')):
        print('  %-42s %s' % (lab, H.fmt_rho(H.spearman_ci(P[col], P.d_trust_s))))

    print('\n(c) Regression with all session-1 predictors (OLS, HC3 SEs, n=%d; exploratory, ~5 '
          'cases per predictor)' % len(sub))
    m = ols('d_trust_s ~ card_bad_1 + manual_bad_1 + drone_failures_1 + bench_1 + C(order)',
            sub.dropna(subset=['bench_1']))
    print(m.summary().tables[1])
    print('  R2 = %.3f, n = %d. (abandoned_1 dropped: r with card_bad_1+manual_bad_1 is high by'
          ' construction.)' % (m.rsquared, int(m.nobs)))
    print('  corr(abandoned_1, card_bad_1+manual_bad_1) = %.2f'
          % np.corrcoef(sub.abandoned_1, sub.card_bad_1 + sub.manual_bad_1)[0, 1])

    print('\n(d) Timing problem with the pre-registered design (found after the fact):')
    print('    trust is measured AFTER each session, so session-1 experience should already be in')
    print('    trust_s1. The experience that falls BETWEEN the two measurements is session 2.')
    print('  s1 card failures vs trust_s1 LEVEL     ' + H.fmt_rho(H.spearman_ci(P.card_bad_1, P.trust_s1)))
    print('  s2 card failures vs change in trust_s  ' + H.fmt_rho(H.spearman_ci(P.card_bad_2, P.d_trust_s)))
    print('  s2 card failures vs trust_s2 LEVEL     ' + H.fmt_rho(H.spearman_ci(P.card_bad_2, P.trust_s2)))
    P['d_card_bad'] = P.card_bad_2 - P.card_bad_1
    P['d_manual_bad'] = P.manual_bad_2 - P.manual_bad_1
    print('  first-difference: change in card failures vs change in trust_s   '
          + H.fmt_rho(H.spearman_ci(P.d_card_bad, P.d_trust_s)))
    print('  first-difference: change in card failures vs change in trust_t   '
          + H.fmt_rho(H.spearman_ci(P.d_card_bad, P.d_trust_t)))
    print('  first-difference, v1.12+ (strategic) '
          + H.fmt_rho(H.spearman_ci(P[P.pid.isin(v12)].d_card_bad, P[P.pid.isin(v12)].d_trust_s)))
    fd = ols('d_trust_s ~ d_card_bad + d_manual_bad + C(order)', P.dropna(subset=['d_trust_s']))
    print('  OLS d_trust_s ~ d_card_bad + d_manual_bad + order:  d_card_bad b=%+.3f [%+.3f, %+.3f] '
          'p=%.3f; d_manual_bad b=%+.3f p=%.3f'
          % (fd.params['d_card_bad'], *fd.conf_int().loc['d_card_bad'], fd.pvalues['d_card_bad'],
             fd.params['d_manual_bad'], fd.pvalues['d_manual_bad']))

    # session-level, within person: trust_s ~ card failures that session, person-clustered GEE
    long = []
    for r_ in P.itertuples():
        for run in (1, 2):
            long.append(dict(pid=r_.pid, run=run, trust_s=getattr(r_, 'trust_s%d' % run),
                             trust_t=getattr(r_, 'trust_t%d' % run),
                             card_bad=getattr(r_, 'card_bad_%d' % run),
                             card_n=getattr(r_, 'card_n_%d' % run),
                             manual_bad=getattr(r_, 'manual_bad_%d' % run)))
    L = pd.DataFrame(long).dropna()
    L['card_bad_pm'] = L.groupby('pid').card_bad.transform('mean')
    L['card_bad_w'] = L.card_bad - L.card_bad_pm
    g = H.B.gee('trust_s ~ card_bad_w + card_bad_pm + C(run)', L)
    print('  session-level GEE trust_s ~ within + between card failures + run (n=%d sessions):'
          % len(L))
    for k in ('card_bad_w', 'card_bad_pm'):
        t = H.B.term(g, k)
        print('    %-12s b=%+.3f [%+.3f, %+.3f] p=%.3f' % (k, t['b'], t['lo'], t['hi'], t['p']))

    print('\n(e) Does trust change track behaviour change? (already in the brief: rho ~ .09)')
    print('  d_trust_s vs d_uptake ' + H.fmt_rho(H.spearman_ci(P.took2 - P.took1, P.d_trust_s)))

    print('\n(f) Debrief trust_trajectory quotes (coded by reading; quote IDs only) vs the data')
    q = H.B.load_quotes()
    tt = [x for x in q['quotes'] if x['theme'] == 'trust_trajectory']
    P_ = P.set_index('pid')
    order = P.sort_values('d_trust_s')
    print('  biggest strategic-trust drops: ' + ', '.join(
        '%s %+.2f' % (r_.pid, r_.d_trust_s) for r_ in order.head(8).itertuples()))
    coded = set(q['participants'])
    print('  of the 8 biggest drops, %d have a coded debrief; trust_trajectory quote holders: %s'
          % (sum(p_ in coded for p_ in order.head(8).pid), sorted({x['pid'] for x in tt})))
    for x in tt:
        if x['pid'] in P_.index:
            r_ = P_.loc[x['pid']]
            print('   %-28s d_trust_s=%+.2f  card_bad s1=%d s2=%d  odd seen s1=%d s2=%d'
                  % (x['id'], r_.d_trust_s, r_.card_bad_1, r_.card_bad_2, r_.odd_seen_1,
                     r_.odd_seen_2))
    # The one quote that names exactly the H5 mechanism (card missions failing in round 1):
    if 'P18' in P_.index:
        r_ = P_.loc['P18']
        print('  P18 (names the H5 mechanism, P18/trust_trajectory/1711): s1 card missions %d, of '
              'which failed/abandoned %d (Conservative %d); d_trust_s=%+.2f, rank of drop %d/%d'
              % (r_.card_n_1, r_.card_bad_1, r_.cons_bad_1, r_.d_trust_s,
                 int((P.d_trust_s < r_.d_trust_s).sum()) + 1, len(P)))

    print('\n(g) Mission-level check of the premise: are card missions more likely to fail than'
          ' manual ones? (session 1, resolved missions)')
    mis = mission_level(dec)
    mis = mis[mis.fate != 'inflight'].copy()
    mis['bad'] = mis.fate.isin(H.BAD_FATES).astype(int)
    for run in (1, 2):
        x = mis[mis.run == run]
        print('  run %d: card %.1f%% bad (n=%d), manual %.1f%% bad (n=%d)'
              % (run, 100 * x[x.took == 1].bad.mean(), (x.took == 1).sum(),
                 100 * x[x.took == 0].bad.mean(), (x.took == 0).sum()))
    gm = H.B.gee('bad ~ took + ncolours + ndrones + C(scenario) + C(run)', mis, binomial=True)
    t = H.B.term(gm, 'took')
    print('  GEE bad ~ took + composition + scenario + run: OR=%.2f [%.2f, %.2f] p=%.3f'
          % (np.exp(t['b']), np.exp(t['lo']), np.exp(t['hi']), t['p']))

    print('\n(h) Where the drop sits: 2x2 crossover on trust (study_analysis.crossover)')
    from study_analysis import crossover
    recs = [dict(pid=r_.pid, run=int(r_.run), scenario=r_.scenario, trust_s=r_.trust_s,
                 trust_t=r_.trust_t) for r_ in sess.itertuples()]
    for metric in ('trust_s', 'trust_t'):
        for lab, rr in (('ALL', recs), ('v1.12+', [x for x in recs if x['pid'] in v12])):
            c = crossover(rr, metric)
            print('  %-7s %-6s run effect %+.2f [%+.2f, %+.2f] p=%.3f | scenario (Tac-Strat) %+.2f '
                  '[%+.2f, %+.2f] p=%.3f | carry-over p=%.3f | n=%d'
                  % (metric, lab, c['run']['diff'], *c['run']['ci'], c['run']['p'],
                     c['scenario']['diff'], *c['scenario']['ci'], c['scenario']['p'],
                     c['carryover']['p'], c['n']))
    print('  mean change by order: SF (Strategic Heavy first) %+.2f, TF (Tactical Heavy first) %+.2f'
          % (P[P.order == 'SF'].d_trust_s.mean(), P[P.order == 'TF'].d_trust_s.mean()))
    print('  fell: SF %d/%d, TF %d/%d' % ((P[P.order == 'SF'].d_trust_s < 0).sum(),
                                          (P.order == 'SF').sum(),
                                          (P[P.order == 'TF'].d_trust_s < 0).sum(),
                                          (P.order == 'TF').sum()))
    zs = {}
    for o_ in ('SF', 'TF'):
        sub_ = P[P.order == o_]
        d_ = H.spearman_ci(sub_.card_bad_1, sub_.d_trust_s)
        zs[o_] = (np.arctanh(d_['rho']), d_['n'])
        print('  primary within order %s (POST HOC): ' % o_ + H.fmt_rho(d_))
        sv_ = sub_[sub_.pid.isin(v12)]
        print('      v1.12+ within order %s: ' % o_ + H.fmt_rho(H.spearman_ci(sv_.card_bad_1,
                                                                             sv_.d_trust_s)))
    zd = (zs['SF'][0] - zs['TF'][0]) / np.sqrt(1 / (zs['SF'][1] - 3) + 1 / (zs['TF'][1] - 3))
    print('  difference between orders (Fisher z): z = %.2f, p = %.3f (POST HOC, one of many cuts)'
          % (zd, 2 * stats.norm.sf(abs(zd))))
    rk = P.dropna(subset=['d_trust_s']).copy()
    rk['r_x'], rk['r_y'] = stats.rankdata(rk.card_bad_1), stats.rankdata(rk.d_trust_s)
    mi = ols('r_y ~ r_x * C(order)', rk)
    print('  rank-OLS interaction r_x:TF b=%+.3f [%+.3f, %+.3f] p=%.3f'
          % (mi.params['r_x:C(order)[T.TF]'], *mi.conf_int().loc['r_x:C(order)[T.TF]'],
             mi.pvalues['r_x:C(order)[T.TF]']))
    print('  s1 card failures by order: SF %s | TF %s'
          % (P[P.order == 'SF'].card_bad_1.value_counts().sort_index().to_dict(),
             P[P.order == 'TF'].card_bad_1.value_counts().sort_index().to_dict()))
    # leave-one-out on the TF correlation (P01 has 4, the max)
    tf = P[P.order == 'TF']
    loo = [stats.spearmanr(tf.drop(i).card_bad_1, tf.drop(i).d_trust_s)[0] for i in tf.index]
    print('  TF leave-one-out rho range [%+.3f, %+.3f]' % (min(loo), max(loo)))

    print('\nPer-person table (for audit):')
    cols = ['pid', 'order', 'trust_s1', 'trust_s2', 'd_trust_s', 'd_trust_t', 'card_n_1',
            'card_bad_1', 'manual_bad_1', 'drone_failures_1', 'card_bad_2', 'odd_seen_1']
    print(P[cols].sort_values('d_trust_s').round(2).to_string(index=False))


if __name__ == '__main__':
    main()
