#!/usr/bin/env python3
"""H4 -- Is the larger shortfall against the near-perfect operator in Strategic Heavy explained by
manual work?  (docs/analysis/HYPOTHESES_ROUND1.md section 3, H4)

PRIMARY (confirmatory, as pre-registered):
    share = session score / SMART benchmark score for that game
    MixedLM  share ~ 0 + C(game) + manual_rate,   random intercept per participant
    'gap'    = Strategic-minus-Tactical contrast of the four game means,
               0.5*(S|1 + S|2) - 0.5*(T|1 + T|2), with and without manual_rate in the model
    Support  = manual_rate coefficient < 0 (95% CI excluding 0) AND the gap shrinks by >= 50%.
    Shrinkage CI by participant-cluster bootstrap (both models refitted in every replicate).

Then a v1.12+ re-run, and exploratory secondaries (labelled as such in the printout).

Run from the repo root:
    C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h4_benchmark_shortfall.py
Reads only; writes nothing.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4_h10_data as H  # noqa: E402
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from build_findings_synthesis import gee as _syn_gee  # noqa: E402

warnings.simplefilter('ignore')
pd.set_option('display.width', 220); pd.set_option('display.max_columns', 30)
GAMES = ['strategic|1', 'strategic|2', 'tactical|1', 'tactical|2']
L = np.array([.5, .5, -.5, -.5])   # Strategic minus Tactical
N_BOOT = int(__import__('os').environ.get('H4_NBOOT', 1000))  # set H4_NBOOT=20 for a quick run


def hdr(t):
    print('\n' + '=' * 100 + '\n' + t + '\n' + '=' * 100)


def fit_mixed(df, y, extra=''):
    f = f'{y} ~ 0 + C(game, levels={GAMES})' + (f' + {extra}' if extra else '')
    return smf.mixedlm(f, df, groups=df['pid']).fit(reml=True)


def gap(m):
    names = [f"C(game, levels={GAMES})[{g}]" for g in GAMES]
    b = m.fe_params[names].values
    V = m.cov_params().loc[names, names].values
    est = float(L @ b)
    se = float(np.sqrt(L @ V @ L))
    return est, se


def coef(m, name):
    ci = m.conf_int().loc[name]
    return dict(b=float(m.params[name]), lo=float(ci[0]), hi=float(ci[1]), p=float(m.pvalues[name]))


def primary(S, label, y='share', x='manual_rate', boot=True, seed=11):
    df = S.dropna(subset=[y, x]).copy()
    m0 = fit_mixed(df, y)
    m1 = fit_mixed(df, y, x)
    g0, se0 = gap(m0)
    g1, se1 = gap(m1)
    c = coef(m1, x)
    shrink = 1 - g1 / g0
    out = dict(label=label, n_people=df.pid.nunique(), n_sessions=len(df), y=y, x=x,
               coef=c, gap0=g0, gap0_se=se0, gap1=g1, gap1_se=se1, shrink=shrink)
    if boot:
        rng = np.random.default_rng(seed)
        pids = df.pid.unique()
        by = {p: g for p, g in df.groupby('pid')}
        sh, bs = [], []
        for _ in range(N_BOOT):
            pick = rng.choice(pids, len(pids), replace=True)
            bd = pd.concat([by[p].assign(pid=f'{p}_{i}') for i, p in enumerate(pick)])
            try:
                b0, b1 = fit_mixed(bd, y), fit_mixed(bd, y, x)
                sh.append(1 - gap(b1)[0] / gap(b0)[0])
                bs.append(b1.params[x])
            except Exception:
                continue
        out['shrink_ci'] = (float(np.percentile(sh, 2.5)), float(np.percentile(sh, 97.5)))
        out['coef_boot_ci'] = (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))
        out['n_boot_ok'] = len(sh)
    supported = c['b'] < 0 and c['hi'] < 0 and shrink >= .5
    out['verdict'] = 'SUPPORTED' if supported else 'NOT SUPPORTED'
    return out


def show(r):
    c = r['coef']
    print(f"[{r['label']}]  y={r['y']}  x={r['x']}  people={r['n_people']} sessions={r['n_sessions']}")
    print(f"   {r['x']} coefficient b = {c['b']:+.3f}  95% CI [{c['lo']:+.3f}, {c['hi']:+.3f}]  p = {c['p']:.4f}"
          + (f"   (cluster-bootstrap CI [{r['coef_boot_ci'][0]:+.3f}, {r['coef_boot_ci'][1]:+.3f}])" if 'coef_boot_ci' in r else ''))
    print(f"   S-T gap without {r['x']}: {r['gap0']:+.3f} (SE {r['gap0_se']:.3f});  with: {r['gap1']:+.3f} (SE {r['gap1_se']:.3f})")
    print(f"   gap shrinkage = {r['shrink']*100:.1f}%"
          + (f"   bootstrap 95% CI [{r['shrink_ci'][0]*100:.1f}%, {r['shrink_ci'][1]*100:.1f}%]  ({r['n_boot_ok']} reps)" if 'shrink_ci' in r else ''))
    print(f"   verdict: {r['verdict']}")


def differencing(S, y='share', x='manual_rate'):
    """Within-person first differences (tactical session minus strategic session). Each person
    played one of two game pairs, (S|1,T|2) or (S|2,T|1); pair enters effect-coded so the intercept
    is the average T-S gap."""
    rows = []
    for pid, g in S.groupby('pid'):
        if set(g.scenario) != {'strategic', 'tactical'}:
            continue
        s, t = g[g.scenario == 'strategic'].iloc[0], g[g.scenario == 'tactical'].iloc[0]
        rows.append(dict(pid=pid, dy=t[y] - s[y], dx=t[x] - s[x],
                         pair=.5 if s.planIndex == 1 else -.5,
                         sfirst=.5 if s.run == 1 else -.5))
    d = pd.DataFrame(rows).dropna()
    m0 = smf.ols('dy ~ pair', d).fit()
    m1 = smf.ols('dy ~ pair + dx', d).fit()
    return d, m0, m1


def main():
    S = H.sessions()
    D = H.decisions()

    hdr('DATA CHECKS')
    print(H.check_against_synthesis())
    print('participants', S.pid.nunique(), 'sessions', len(S), ' v1.12+ participants', S[S.v112].pid.nunique())
    print('share by scenario (all 33):', S.groupby('scenario').share.mean().round(4).to_dict(),
          ' -- the brief quotes 61% / 75%')
    print('share by game:', S.groupby('game').share.agg(['mean', 'count']).round(3).to_dict('index'))
    print('manual rate by scenario (session means):', S.groupby('scenario').manual_rate.mean().round(3).to_dict())
    print('   pre-emptive rate by scenario:', S.groupby('scenario').early_rate.mean().round(3).to_dict(),
          ' post-reveal:', S.groupby('scenario').post_rate.mean().round(3).to_dict())
    print('sessions with score floored at 0:', S[S.score == 0][['pid', 'run', 'version', 'net']].values.tolist())
    print('sessions on half task weights (v1.0-v1.2: benchmark not on the same scale):',
          S[S.taskWeightScale != 1][['pid', 'run', 'version', 'score', 'score_rescaled']].values.tolist())
    pm = S.groupby('pid').manual_rate.agg(['mean', 'std'])
    print('manual rate: between-person SD of person means', round(pm['mean'].std(), 3),
          ' mean within-person SD', round(pm['std'].mean(), 3))
    r = stats.spearmanr(S[S.scenario == 'strategic'].set_index('pid').manual_rate,
                        S[S.scenario == 'tactical'].set_index('pid').manual_rate.reindex(S[S.scenario == 'strategic'].pid))
    print(f'manual rate, strategic vs tactical session, Spearman rho = {r.correlation:.2f} p = {r.pvalue:.4f}')
    dm = S.pivot(index='pid', columns='scenario', values='manual_rate')
    w = stats.wilcoxon(dm.strategic, dm.tactical)
    print(f'paired manual rate S - T = {(dm.strategic - dm.tactical).mean():+.3f}  Wilcoxon p = {w.pvalue:.4f}')

    hdr('PRIMARY (confirmatory) -- all 33')
    P = primary(S, 'all 33')
    show(P)

    hdr('v1.12+ SENSITIVITY (n = 24)')
    show(primary(S[S.v112], 'v1.12+', seed=12))

    hdr('ROBUSTNESS of the primary (exploratory)')
    show(primary(S[S.taskWeightScale == 1], 'exclude P01/P02 (half task weights)', boot=False))
    show(primary(S, 'all 33, unfloored net score', y='share_net', boot=False))
    show(primary(S, 'all 33, P01/P02 rescaled to current weights', y='share_rescaled', boot=False))
    show(primary(S, 'manual rate on genuine (non-residual) decisions', x='manual_rate_gen', boot=False))
    show(primary(S, 'outcome = scoreEff (score / points on offer) instead of benchmark share', y='scoreEff', boot=False))
    print('per game: raw score, sessions beating the benchmark, benchmark penalty/task completion')
    import json
    bref = {f"{g['complexity']}|{g['planIndex']}": g for g in json.loads(H.BENCH.read_text())['games']}
    for gname, g in S.groupby('game'):
        b = bref[gname]
        print(f"   {gname}: mean score {g.score.mean():7.1f}  benchmark {b['score']}  sessions > benchmark {int((g.share > 1).sum())}/{len(g)}"
              f"  benchmark penalty {b['penalty']}  benchmark taskCompletion {b['taskCompletion']:.2f}  benchmark failures {b['failures']}  participants' mean failures {g.failures.mean():.1f}  mean penalty {g.penalty.mean():.0f}")
    # run (learning) as an extra fixed effect: game is only partly confounded with run after v1.13
    print('where the shortfall sits (session means, current-weight sessions only): points on offer, earned, '
          'unearned on never-allocated missions, unearned on allocated missions (requeued work excluded), penalty')
    cw = S[S.taskWeightScale == 1]
    print(cw.groupby('scenario')[['availablePoints', 'completionPoints', 'unallocPoints', 'allocLostPoints', 'penalty',
                                  'unallocMissions', 'manual_rate']].mean().round(1))
    print(cw.groupby('game')[['availablePoints', 'completionPoints', 'unallocPoints', 'allocLostPoints', 'penalty']].mean().round(1))
    for v in ('unallocPoints', 'allocLostPoints', 'penalty'):
        mm = smf.mixedlm(f'{v} ~ C(game) + manual_rate', cw, groups=cw.pid).fit()
        ci = mm.conf_int().loc['manual_rate']
        print(f"   {v} ~ game + manual_rate (person RE): b = {mm.params['manual_rate']:+.1f} [{ci[0]:+.1f}, {ci[1]:+.1f}] p = {mm.pvalues['manual_rate']:.3f}")
    cw = cw.copy(); cw['m_pm'] = cw.groupby('pid').manual_rate.transform('mean'); cw['m_w'] = cw.manual_rate - cw.m_pm
    for v in ('unallocPoints', 'penalty'):
        mm = smf.mixedlm(f'{v} ~ C(game) + m_w + m_pm', cw, groups=cw.pid).fit()
        print(f"   {v} ~ game + manual (within / between): within {mm.params['m_w']:+.1f} p = {mm.pvalues['m_w']:.3f}; "
              f"between {mm.params['m_pm']:+.1f} p = {mm.pvalues['m_pm']:.3f}")
    dfr = S.copy(); dfr['run2'] = (dfr.run == 2).astype(int)
    m0 = fit_mixed(dfr, 'share', 'run2'); m1 = fit_mixed(dfr, 'share', 'run2 + manual_rate')
    g0, g1 = gap(m0)[0], gap(m1)[0]
    print(f"[+ run fixed effect] manual b = {coef(m1, 'manual_rate')['b']:+.3f} "
          f"[{coef(m1, 'manual_rate')['lo']:+.3f}, {coef(m1, 'manual_rate')['hi']:+.3f}] p = {coef(m1, 'manual_rate')['p']:.4f}; "
          f"gap {g0:+.3f} -> {g1:+.3f}, shrink {100*(1-g1/g0):.1f}%;  run2 b = {coef(m1, 'run2')['b']:+.3f}")
    # within-person differencing
    d, m0, m1 = differencing(S)
    g0 = -(m0.params['Intercept']); g1 = -(m1.params['Intercept'])
    ci = m1.conf_int().loc['dx']
    print(f"[first differences, n = {len(d)}] d(manual) b = {m1.params['dx']:+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}] "
          f"p = {m1.pvalues['dx']:.4f};  S-T gap {g0:+.3f} -> {g1:+.3f} (shrink {100*(1-g1/g0):.1f}%);  "
          f"mean d(manual) T-S = {d.dx.mean():+.3f}")
    d2, m0b, m1b = differencing(S[S.v112])
    print(f"[first differences v1.12+, n = {len(d2)}] d(manual) b = {m1b.params['dx']:+.3f} p = {m1b.pvalues['dx']:.4f}; "
          f"gap {-m0b.params['Intercept']:+.3f} -> {-m1b.params['Intercept']:+.3f}")

    hdr('SECONDARY 1 (exploratory) -- within vs between person; pre-emptive vs post-reveal manual')
    S2 = S.copy()
    for v in ('manual_rate', 'early_rate', 'post_rate', 'edited_rate', 'post_unedited_rate'):
        S2[v + '_pm'] = S2.groupby('pid')[v].transform('mean')
        S2[v + '_w'] = S2[v] - S2[v + '_pm']
    for spec in ['manual_rate_w + manual_rate_pm',
                 'early_rate + post_rate',
                 'early_rate_w + early_rate_pm + post_rate_w + post_rate_pm',
                 'early_rate + edited_rate + post_unedited_rate']:
        m = fit_mixed(S2, 'share', spec)
        g = gap(m)[0]
        terms = '; '.join(f"{t} {m.params[t]:+.3f} [{m.conf_int().loc[t, 0]:+.3f},{m.conf_int().loc[t, 1]:+.3f}] p={m.pvalues[t]:.3f}"
                          for t in spec.replace(' ', '').split('+'))
        print(f"share ~ game + {spec}:  {terms};  gap {g:+.3f} (vs {P['gap0']:+.3f}, shrink {100*(1-g/P['gap0']):.1f}%)")
    m = fit_mixed(S2[S2.v112], 'share', 'manual_rate_w + manual_rate_pm')
    print('v1.12+ within/between:', {t: (round(m.params[t], 3), round(m.pvalues[t], 3)) for t in ('manual_rate_w', 'manual_rate_pm')})
    # the gap is not uniform over the four games
    print('\nshare by game pair (each person plays one pair):')
    S['pair'] = np.where(((S.scenario == 'strategic') & (S.planIndex == 1)) | ((S.scenario == 'tactical') & (S.planIndex == 2)),
                         'S1+T2', 'S2+T1')
    print(S.groupby(['pair', 'scenario']).share.agg(['mean', 'count']).round(3))
    for pair, g in S.groupby('pair'):
        w = g.pivot(index='pid', columns='scenario', values='share')
        t = stats.ttest_rel(w.tactical, w.strategic)
        print(f"   pair {pair}: T - S share = {(w.tactical - w.strategic).mean():+.3f}  paired t p = {t.pvalue:.4f}  n = {len(w)}")

    hdr('SECONDARY 2 (exploratory) -- per mission, manual vs card, matched on composition and person')
    G = D[D.residual == 0].copy()
    G['net_share'] = G.net / G.max_points
    G['stratum'] = G.pid + '|' + G.compkey
    mixed = G.groupby('stratum').manual.transform(lambda s: s.nunique() > 1)
    M = G[mixed].copy()
    print(f'genuine decisions {len(G)}; in person x composition strata that contain BOTH routes: {len(M)} '
          f'({M.stratum.nunique()} strata, {M.pid.nunique()} people, {int(M.manual.sum())} manual)')
    print('   compositions in matched strata:', M.compkey.value_counts().head(8).to_dict())
    from statsmodels.discrete.conditional_models import ConditionalLogit
    for y in ('full', 'chain_full'):
        try:
            cm = ConditionalLogit(M[y].values, M[['manual']].values, groups=M.stratum.values).fit(disp=0)
            b, se = cm.params[0], cm.bse[0]
            print(f"   conditional logit {y}: manual OR = {np.exp(b):.2f} [{np.exp(b-1.96*se):.2f}, {np.exp(b+1.96*se):.2f}] p = {cm.pvalues[0]:.3f}"
                  f"   (raw rates card {M[M.manual==0][y].mean():.3f}, manual {M[M.manual==1][y].mean():.3f})")
        except Exception as ex:
            print('   conditional logit failed', y, ex)
    for y in ('net_share', 'penalty', 't_complete'):
        mm = M.dropna(subset=[y]).copy()
        mm = mm[mm.groupby('stratum').manual.transform(lambda s: s.nunique() > 1)]
        mm['yd'] = mm[y] - mm.groupby('stratum')[y].transform('mean')
        mm['xd'] = mm.manual - mm.groupby('stratum').manual.transform('mean')
        mm['tl'] = mm.time_left - mm.groupby('stratum').time_left.transform('mean')
        o = smf.ols('yd ~ 0 + xd + tl', mm).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(mm.pid)[0]})
        ci = o.conf_int().loc['xd']
        print(f"   within-stratum {y}: manual - card = {o.params['xd']:+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}] p = {o.pvalues['xd']:.3f}  (n = {len(mm)}, time-left adjusted)")
    # the same, split by whether the manual choice was pre-emptive
    for lab, sel in (('pre-emptive manual vs card', (M.manual == 0) | (M.early == 1)),
                     ('post-reveal manual vs card', (M.manual == 0) | (M.early == 0))):
        mm = M[sel]; mm = mm[mm.groupby('stratum').manual.transform(lambda s: s.nunique() > 1)]
        try:
            cm = ConditionalLogit(mm.full.values, mm[['manual']].values, groups=mm.stratum.values).fit(disp=0)
            print(f"   {lab}: full-completion OR = {np.exp(cm.params[0]):.2f} p = {cm.pvalues[0]:.3f} (n = {len(mm)}, manual = {int(mm.manual.sum())})")
        except Exception as ex:
            print('   ', lab, 'failed', ex)

    hdr('SECONDARY 3 (exploratory) -- does trimming small missions leave a reserve that later missions use?')
    D2 = D.sort_values(['pid', 'run', 'elapsed']).copy()
    D2['trim'] = np.where((D2.manual == 1) & (D2.d_cons < 0), -D2.d_cons, 0)
    small = D2[(D2.ncolours == 1) & (D2.residual == 0)]
    print(f"single-type (small) genuine decisions: {len(small)}; manual {int(small.manual.sum())}; "
          f"trimmed below Conservative {int((small.trim > 0).sum())}; mean drones saved per trim {small[small.trim>0].trim.mean():.2f}")
    print(f"reserve pressure: a needed colour's reserve below the mission's total need ('tight') on {D2.tight.mean():.1%} of decisions "
          f"(Strategic Heavy {D2[D2.scenario=='strategic'].tight.mean():.1%}, Tactical Heavy {D2[D2.scenario=='tactical'].tight.mean():.1%}); "
          f"a task unstaffable from reserve ('starved'): {int(D2.starved.sum())} of {len(D2)}")
    # drones trimmed in the preceding window, for every later decision in the same session
    for win in (60, 120):
        sv = []
        for (pid, run), g in D2.groupby(['pid', 'run']):
            el, tr = g.elapsed.values, g.trim.values
            sv += [float(tr[(el < e) & (el >= e - win)].sum()) for e in el]
        D2[f'saved{win}'] = sv
    # 'saved_active': drones trimmed on earlier missions that are STILL running at this decision --
    # the only drones trimming can actually have kept in reserve (a card's extra drones would have
    # come home when that mission ended). The 60/120 s windows were the first attempt.
    act = []
    for (pid, run), g in D2.groupby(['pid', 'run']):
        el, tr, en = g.elapsed.values, g.trim.values, g.end_el.values
        act += [float(tr[(el < e) & (en > e)].sum()) for e in el]
    D2['saved_active'] = act
    big = D2[(D2.ncolours == 3) & (D2.residual == 0)].copy()
    big['net_share'] = big.net / big.max_points
    for sv in ('saved120', 'saved60', 'saved_active'):
        big['saved_pm'] = big.groupby('pid')[sv].transform('mean')
        big['saved_w'] = big[sv] - big.saved_pm
        print(f"[{sv}] three-type genuine decisions: {len(big)}; with >0 drones saved: {int((big[sv]>0).sum())}, mean when >0 {big[big[sv]>0][sv].mean():.2f}")
        m = H_gee('reserve_total ~ saved_w + saved_pm + elapsed + C(game) + ndrones', big)
        print('   reserve at decision ~ saved (within-person):', fmt(m, 'saved_w'))
        m = H_gee('tight ~ saved_w + saved_pm + elapsed + C(game) + ndrones', big, binomial=True)
        print('   P(tight) ~ saved (within-person, logit):', fmt(m, 'saved_w', exp=True))
        for y, binom in (('full', True), ('net_share', False)):
            m = H_gee(f'{y} ~ saved_w + saved_pm + time_left + C(game) + ndrones', big.dropna(subset=[y]), binomial=binom)
            print(f'   {y} ~ saved (within-person):', fmt(m, 'saved_w', exp=binom))
    # busy-ness check: are trims clustered when many missions are queued/active (which would explain
    # a positive saved -> outcome link without any reserve mechanism)?
    print('   corr(saved_active, elapsed) on three-type decisions:', round(big[['saved_active', 'elapsed']].corr().iloc[0, 1], 3))
    # reserve itself as the mediator: does a bigger reserve at the moment of decision go with better outcomes?
    G2 = D2[D2.residual == 0].copy(); G2['net_share'] = G2.net / G2.max_points
    G2['res_pm'] = G2.groupby('pid').reserve_total.transform('mean'); G2['res_w'] = G2.reserve_total - G2.res_pm
    for y, binom in (('full', True), ('net_share', False)):
        m = H_gee(f'{y} ~ res_w + res_pm + time_left + C(game) + ncolours + ndrones', G2.dropna(subset=[y]), binomial=binom)
        print(f'   all genuine decisions, {y} ~ reserve at decision (within-person, per drone):', fmt(m, 'res_w', exp=binom))
    # session level: does a person's trimming on small missions go with their large-mission results?
    per = []
    for (pid, run), g in D2[D2.residual == 0].groupby(['pid', 'run']):
        sm_ = g[g.ncolours == 1]; bg = g[g.ncolours == 3]
        if len(sm_) and len(bg):
            per.append(dict(pid=pid, run=run, game=g.game.iloc[0], trim_small=sm_.trim.sum(),
                            big_full=bg.full.mean(), big_net=(bg.net / bg.max_points).mean()))
    per = pd.DataFrame(per).merge(S[['pid', 'run', 'share']], on=['pid', 'run'])
    for y in ('big_full', 'big_net', 'share'):
        mm = smf.mixedlm(f'{y} ~ C(game) + trim_small', per, groups=per.pid).fit()
        ci = mm.conf_int().loc['trim_small']
        print(f"   session level, {y} ~ drones trimmed on small missions (+game, person RE): b = {mm.params['trim_small']:+.4f} "
              f"[{ci[0]:+.4f}, {ci[1]:+.4f}] p = {mm.pvalues['trim_small']:.3f}  (n = {len(per)} sessions)")


def H_gee(formula, data, binomial=False):
    """= build_findings_synthesis.gee (person-clustered exchangeable GEE)."""
    return _syn_gee(formula, data, binomial)


def _unused(formula, data, binomial=False):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    return smf.gee(formula, 'pid', data=data, family=fam, cov_struct=sm.cov_struct.Exchangeable()).fit()


def fmt(m, name, exp=False):
    b, (lo, hi), p = m.params[name], m.conf_int().loc[name], m.pvalues[name]
    if exp:
        return f'OR {np.exp(b):.3f} [{np.exp(lo):.3f}, {np.exp(hi):.3f}] p = {p:.3f} (n = {int(m.nobs)})'
    return f'b {b:+.4f} [{lo:+.4f}, {hi:+.4f}] p = {p:.3f} (n = {int(m.nobs)})'


if __name__ == '__main__':
    main()
