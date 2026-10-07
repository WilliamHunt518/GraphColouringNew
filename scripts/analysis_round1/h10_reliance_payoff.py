#!/usr/bin/env python3
"""H10 -- Does relying on the assistants pay off?  (docs/analysis/HYPOTHESES_ROUND1.md section 3, H10)

PRIMARY (confirmatory, as pre-registered):
    decision level, every strategic decision (n = 606, 33 people)
    GEE logit (build_findings_synthesis.gee: exchangeable, clustered on participant)
        full ~ took + ncolours + ndrones + C(game) + took_pm
    full    = the decision's mission completed in full (mission_completed.outcome == all_completed);
              abandoned, partial, none and still-in-flight-at-the-buzzer all count 0
    took    = took a card (Aggressive or Conservative) as-is; 0 = manual (incl. edited cards)
    took_pm = the person's mean card uptake (Mundlak term), so `took` is the within-person route effect
    composition = ncolours + ndrones, the house composition terms (build_findings_synthesis)
    Support = route odds ratio with a 95% CI excluding 1, either direction.

Then a v1.12+ re-run and exploratory secondaries.

Run from the repo root:
    C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h10_reliance_payoff.py
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
warnings.simplefilter('ignore')
pd.set_option('display.width', 220); pd.set_option('display.max_columns', 30)
import h4_h10_data as H  # noqa: E402
from build_findings_synthesis import gee  # noqa: E402
from study_analysis import spearman  # noqa: E402


def hdr(t):
    print('\n' + '=' * 100 + '\n' + t + '\n' + '=' * 100)


def orfmt(m, name):
    b, (lo, hi), p = m.params[name], m.conf_int().loc[name], m.pvalues[name]
    return dict(OR=float(np.exp(b)), lo=float(np.exp(lo)), hi=float(np.exp(hi)), p=float(p), n=int(m.nobs))


def bfmt(m, name):
    b, (lo, hi), p = m.params[name], m.conf_int().loc[name], m.pvalues[name]
    return f'b {b:+.3f} [{lo:+.3f}, {hi:+.3f}] p = {p:.3f} (n = {int(m.nobs)})'


def show_or(label, r):
    print(f"   {label}: OR = {r['OR']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]  p = {r['p']:.4f}  n = {r['n']}")


def add_pm(df, col='took'):
    df = df.copy()
    df[col + '_pm'] = df.groupby('pid')[col].transform('mean')
    return df


def primary(D, label, y='full', extra='', x='took'):
    d = add_pm(D.dropna(subset=[y]), x)
    f = f'{y} ~ {x} + ncolours + ndrones + C(game) + {x}_pm' + (f' + {extra}' if extra else '')
    m = gee(f, d, binomial=True)
    r = orfmt(m, x)
    r['people'] = d.pid.nunique()
    # the confirmatory verdict applies to the primary spec only; robustness lines just say whether the CI excludes 1
    r['verdict'] = 'CI excludes 1' if (r['lo'] > 1 or r['hi'] < 1) else 'CI includes 1'
    print(f"[{label}]  {f}")
    show_or(f'{x} (card vs manual, within person)', r)
    print(f"   people = {r['people']};  {x}_pm: {orfmt(m, x + '_pm')['OR']:.3f} p = {orfmt(m, x + '_pm')['p']:.3f};"
          f"  raw full-completion card {d[d[x]==1][y].mean():.3f} vs manual {d[d[x]==0][y].mean():.3f};  verdict: {r['verdict']}")
    return r, m


def detectable_or(D):
    """Smallest OR detectable at 80% power, two-sided alpha .05, from the primary model's SE (Wald)."""
    d = add_pm(D)
    m = gee('full ~ took + ncolours + ndrones + C(game) + took_pm', d, binomial=True)
    se = m.bse['took']
    return float(np.exp(2.8 * se)), float(np.exp(-2.8 * se))


def main():
    D = H.decisions()
    S = H.sessions()

    hdr('DATA')
    print(H.check_against_synthesis())
    print('decisions', len(D), 'people', D.pid.nunique(), 'card', int(D.took.sum()), 'manual', int(D.manual.sum()),
          'residual decisions', int(D.residual.sum()))
    print('mission status:', D.status.value_counts().to_dict())
    print('status by route:'); print(pd.crosstab(D.took, D.status, normalize='index').round(3))
    print('C.outcome on the synthesis page is restricted to <3-colour missions with a mission_completed event '
          '(drops abandoned and in-flight); recomputed here:')
    few = D[(D.ncolours < 3) & D.status.isin(['all_completed', 'partial', 'none_completed'])]
    print('  ', few.groupby('manual').full.agg(['mean', 'count']).round(4).to_dict('index'))
    print('reverse selection check -- manual share and completion by colours needed:')
    print(D.groupby('ncolours').agg(n=('full', 'size'), manual=('manual', 'mean'), full=('full', 'mean')).round(3))

    hdr('PRIMARY (confirmatory) -- all 33')
    P, mP = primary(D, 'all 33')
    print('   CONFIRMATORY VERDICT:', 'SUPPORTED' if P['verdict'] == 'CI excludes 1' else 'NOT SUPPORTED')
    hi, lo = detectable_or(D)
    print(f"   detectable at 80% power: OR <= {lo:.2f} or >= {hi:.2f}")
    print(mP.summary().tables[1])

    hdr('v1.12+ SENSITIVITY (n = 24)')
    primary(D[D.v112], 'v1.12+')

    hdr('ROBUSTNESS (exploratory)')
    primary(D, '+ time left at decision (censoring by the buzzer)', extra='time_left')
    primary(D[D.time_left >= 150], 'decisions with >= 150 s left')
    primary(D[D.status != 'inflight'], 'resolved missions only (drop in-flight at the buzzer)')
    primary(D, 'outcome follows abandoned work into its residual (chain_full)', y='chain_full')
    primary(D[D.residual == 0], 'genuine (non-residual) decisions only')
    primary(D, 'composition as task count too', extra='ntasks')
    primary(D, '+ C(run)', extra='C(run)')
    # finer composition: exact task multiset within person (conditional logit, the strictest match)
    from statsmodels.discrete.conditional_models import ConditionalLogit
    for lab, dd in (('all', D), ('genuine', D[D.residual == 0])):
        dd = dd.copy(); dd['stratum'] = dd.pid + '|' + dd.compkey
        dd = dd[dd.groupby('stratum').took.transform(lambda s: s.nunique() > 1)]
        for y in ('full', 'chain_full'):
            cm = ConditionalLogit(dd[y].values, dd[['took', 'time_left']].values, groups=dd.stratum.values).fit(disp=0)
            b, se = cm.params[0], cm.bse[0]
            print(f"[person x exact composition strata, {lab}, {y}, +time left] card OR = {np.exp(b):.2f} "
                  f"[{np.exp(b-1.96*se):.2f}, {np.exp(b+1.96*se):.2f}] p = {cm.pvalues[0]:.3f}  "
                  f"(n = {len(dd)} in {dd.stratum.nunique()} strata, {dd.pid.nunique()} people)")
    # route split: which card / which kind of manual
    d = add_pm(D)
    d['route'] = np.select([D.choice == 'conservative', D.choice == 'aggressive', D.early == 1, D.edited == 1],
                           ['cons', 'aggr', 'manual_pre', 'manual_edited'], 'manual_post')
    m = gee("full ~ C(route, Treatment('manual_post')) + ncolours + ndrones + C(game) + took_pm + time_left", d, binomial=True)
    print('[route split vs post-reveal unedited manual, + time left]')
    for t in m.params.index:
        if 'route' in t:
            r = orfmt(m, t); print(f"   {t.split('[T.')[1][:-1]:14s} OR {r['OR']:.2f} [{r['lo']:.2f}, {r['hi']:.2f}] p = {r['p']:.3f}")
    print('   route counts:', d.route.value_counts().to_dict())
    # interaction with mission size (does reliance pay off only on big missions?)
    m = gee('full ~ took * C(ncolours == 3) + ndrones + C(game) + took_pm + time_left', d, binomial=True)
    print('[took x three-colour mission]', {t: (round(float(np.exp(m.params[t])), 2), round(float(m.pvalues[t]), 3))
                                           for t in m.params.index if 'took' in t and t != 'took_pm'})

    hdr('SECONDARY 1 (exploratory) -- penalty, net value and time to complete, per decision')
    d = add_pm(D)
    d['net_share'] = d.net / d.max_points
    for y in ('penalty', 'net_share', 'points'):
        m = gee(f'{y} ~ took + ncolours + ndrones + C(game) + took_pm + time_left', d.dropna(subset=[y]))
        print(f'   {y:10s} card - manual (within person): {bfmt(m, "took")}   raw card {d[d.took==1][y].mean():.2f} manual {d[d.took==0][y].mean():.2f}')
    dc = d[d.full == 1]
    for y in ('t_complete', 'dur_alloc'):
        m = gee(f'{y} ~ took + ncolours + ndrones + C(game) + took_pm', dc.dropna(subset=[y]))
        print(f'   {y:10s} (fully completed missions) card - manual: {bfmt(m, "took")}')
    m = gee('drone_failures ~ took + ncolours + ndrones + C(game) + took_pm + time_left', d, binomial=False)
    print(f'   drone failures on the mission, card - manual: {bfmt(m, "took")}   (cards commit more drones: '
          f'{d[d.took==1].committed.mean():.1f} vs {d[d.took==0].committed.mean():.1f})')
    m = gee('full ~ took + committed + ncolours + ndrones + C(game) + took_pm + time_left', d, binomial=True)
    show_or('full ~ took, holding drones committed fixed', orfmt(m, 'took'))
    show_or('   ... per extra drone committed', orfmt(m, 'committed'))

    hdr('SECONDARY 2 (exploratory) -- session level, between vs within person, game controlled')
    S2 = S.copy()
    for u in ('uptake', 'tac_unmod', 'tac_consult'):
        S2[u + '_pm'] = S2.groupby('pid')[u].transform('mean')
        S2[u + '_w'] = S2[u] - S2[u + '_pm']
    for y in ('share', 'scoreEff'):
        for u in ('uptake', 'tac_unmod'):
            for lab, dat in (('all 33', S2), ('v1.12+', S2[S2.v112])):
                mm = smf.mixedlm(f'{y} ~ C(game) + {u}_w + {u}_pm', dat, groups=dat.pid).fit()
                w, b = mm.conf_int().loc[u + '_w'], mm.conf_int().loc[u + '_pm']
                print(f"   [{lab}] {y} ~ game + {u}: within {mm.params[u+'_w']:+.3f} [{w[0]:+.3f},{w[1]:+.3f}] p={mm.pvalues[u+'_w']:.3f}; "
                      f"between {mm.params[u+'_pm']:+.3f} [{b[0]:+.3f},{b[1]:+.3f}] p={mm.pvalues[u+'_pm']:.3f}")
    # the existing person-level Spearman (useVsPerf), recomputed on all 33 and with benchmark share
    pp = S.groupby('pid').agg(uptake=('uptake', 'mean'), tac=('tac_unmod', 'mean'), share=('share', 'mean'),
                              eff=('scoreEff', 'mean'), v112=('v112', 'first'))
    for lab, q in (('all 33', pp), ('v1.12+', pp[pp.v112]), ('v1.4+ (= useVsPerf cohort)', pp.drop(['P01', 'P02'], errors='ignore'))):
        print(f"   person-level Spearman [{lab}]: uptake~scoreEff {spearman(list(q.uptake), list(q.eff))}; "
              f"uptake~share {spearman(list(q.uptake), list(q.share))}; tactical keep~share {spearman(list(q.tac), list(q.share))}")

    hdr('SECONDARY 3 (exploratory) -- tactical: kept-unmodified vs edited vs built from scratch')
    T = D[D.tac_confirmed == 1].copy()
    T['delay'] = T.tac_conf_el - T.tac_open_el
    T['delta'] = T.finalProj - T.agentProj
    T['route'] = np.where(T.tac_unmod == 1, 'unmod', np.where(T.tac_consulted == 1, 'edited', 'scratch'))
    print('counts:', T.route.value_counts().to_dict(), ' people with any edited plan:', T[T.route == 'edited'].pid.nunique())
    print('finalProjectedCompletion - agentProjectedCompletion (s), by route:')
    print(T.groupby('route').delta.describe().round(2))
    u = T[T.route == 'unmod']
    print(f"   NB the agent projection is made when the planner opens and the final one at confirm; for UNMODIFIED "
          f"plans (identical plan) delta still correlates r = {np.corrcoef(u.delay, u.delta)[0,1]:.2f} with the confirm delay,"
          f" so the raw delta is partly waiting time, not plan quality. Controlled for below.")
    T['unassigned_any'] = (T.tac_unassigned > 0).astype(int)
    print('plans confirmed with a task left unassigned:', T.groupby('route').unassigned_any.sum().to_dict())
    for lab, sub in (('scratch vs unmodified', T[T.route != 'edited']), ('edited vs unmodified', T[T.route != 'scratch'])):
        sub = sub.copy(); sub['x'] = (sub.route != 'unmod').astype(int)
        sub['x_pm'] = sub.groupby('pid').x.transform('mean')
        m = gee('delta ~ x + delay + ncolours + ndrones + C(game) + x_pm', sub)
        print(f'   [{lab}] delta (s), delay-adjusted, within person: {bfmt(m, "x")}')
        sub['ldelta'] = np.log1p(sub.delta.clip(lower=0))
        m = gee('ldelta ~ x + delay + ncolours + ndrones + C(game) + x_pm', sub)
        print(f'   [{lab}] log1p(delta), delay-adjusted: {bfmt(m, "x")}')
        m = gee('full ~ x + ncolours + ndrones + C(game) + x_pm + time_left', sub, binomial=True)
        show_or(f'[{lab}] full completion, built/edited vs kept', orfmt(m, 'x'))
    # does the tactical route confound the strategic one? (manual strategic choices are followed by
    # hand-built plans more often)
    print('   tactical route by strategic route:'); print(pd.crosstab(T.took, T.route, normalize='index').round(3))
    m = gee("full ~ took + C(route, Treatment('unmod')) + ncolours + ndrones + C(game) + took_pm + time_left",
            add_pm(T), binomial=True)
    show_or('strategic card OR, holding the tactical route fixed', orfmt(m, 'took'))


if __name__ == '__main__':
    main()
