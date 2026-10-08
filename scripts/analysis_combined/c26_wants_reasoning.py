#!/usr/bin/env python3
"""C26 'wants the assistant's reasoning / transparency / auditability' -- who are they, and why did
they score higher?  Report: docs/analysis/combined/c26_wants_reasoning.md

Read-only over Results/ and docs/. Run from the repo root:

    C:/Users/Work/anaconda3/python.exe scripts/analysis_combined/c26_wants_reasoning.py

Group = participants coded C26 in docs/analysis/qual/codes_matrix.csv. P02 is coded C26 but played
on half task weights, so (exactly as person_summary() in build_findings_synthesis does) P02 is out of
every SCORE comparison and kept in the behaviour description. P09 is excluded everywhere.

All tests are permutation tests on the group label (person-level means; 20 000 shuffles, two-sided,
|mean_in - mean_rest|). Every test run is counted and printed at the end.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
sys.path.insert(0, str(BASE / 'scripts' / 'analysis_round1'))
warnings.filterwarnings('ignore')

import build_findings_synthesis as b  # noqa: E402
import h1_archetypes as h1  # noqa: E402

RNG = np.random.default_rng(20261008)
N_PERM = 20000
TESTS = []  # (label, p)
HALF = {'P01', 'P02'}


def perm(x: pd.Series, members: set, label: str, record=True):
    x = x.dropna()
    lab = x.index.isin(members)
    if lab.sum() < 2 or (~lab).sum() < 2:
        return None
    v = x.values
    obs = v[lab].mean() - v[~lab].mean()
    k = lab.sum()
    null = np.empty(N_PERM)
    for i in range(N_PERM):
        idx = RNG.permutation(len(v))[:k]
        m = np.zeros(len(v), bool)
        m[idx] = True
        null[i] = v[m].mean() - v[~m].mean()
    p = (np.sum(np.abs(null) >= abs(obs) - 1e-12) + 1) / (N_PERM + 1)
    if record:
        TESTS.append((label, p))
    return dict(inMean=v[lab].mean(), restMean=v[~lab].mean(), nIn=int(k), nRest=int((~lab).sum()),
                diff=obs, p=p)


def hdr(s):
    print('\n' + '=' * 90 + '\n' + s + '\n' + '=' * 90)


def main():
    M = pd.read_csv(BASE / 'docs/analysis/qual/codes_matrix.csv').set_index('pid')
    C26 = set(M.index[M.C26 == 1])
    C26_score = C26 - HALF
    hdr('Membership')
    print('C26 coded:', sorted(C26), ' | in score comparisons:', sorted(C26_score))
    print('sources:', M.loc[sorted(C26), 'sources'].to_dict())

    S, T, R, Se = h1.parse()
    Se = Se.set_index(['pid', 'run'])
    sess, people = b.load_people()
    sess = pd.DataFrame(sess).set_index(['pid', 'run'])

    # ── benchmark share and within-game z ─────────────────────────────────────────────────
    ref = json.loads((BASE / 'docs/reports/smart_benchmark.json').read_text(encoding='utf-8'))
    bench = {(g['complexity'], g['planIndex']): g['score'] for g in ref['games']}
    Se['bench'] = [bench.get((sc, gi)) for sc, gi in zip(Se.scenario, Se.gameIndex)]
    Se['share'] = Se.score / Se.bench
    ok = ~Se.index.get_level_values('pid').isin(HALF)
    Se['z'] = np.nan
    Se.loc[ok, 'z'] = Se[ok].groupby('game').score.transform(lambda s: (s - s.mean()) / s.std())
    Se['grp'] = Se.index.get_level_values('pid').isin(C26)

    hdr('Session table for C26 members (and game means)')
    cols = ['scenario', 'game', 'swapped', 'version', 'epsS', 'epsT', 'score', 'bench', 'share', 'z',
            'missionsArrived', 'nStrategic', 'completion', 'failures', 'episodes', 'abandons',
            'reliance']
    print(Se.loc[Se.grp, cols].round(2).to_string())
    print('\nGame means (score-eligible sessions):')
    print(Se[ok].groupby('game').agg(n=('score', 'size'), score=('score', 'mean'),
                                     sd=('score', 'std'), share=('share', 'mean')).round(2))

    # ── confounds: design cells ───────────────────────────────────────────────────────────
    hdr('Design confounds')
    first = Se.xs(1, level='run')
    order = first.scenario.rename('firstScenario')
    swapped = Se.groupby(level='pid').swapped.first()
    vers = Se.groupby(level='pid').version.first()
    epsS = Se.groupby(level='pid').epsS.max()
    epsT = Se.groupby(level='pid').epsT.max()
    D = pd.concat([order, swapped, vers, epsS, epsT], axis=1)
    D['C26'] = D.index.isin(C26)
    print(D[D.C26].to_string())
    for c in ['firstScenario', 'swapped', 'version']:
        print(f'\n{c}: C26 vs rest (counts)')
        print(pd.crosstab(D[c], D.C26))
    print('\nfailures live (epsS>0 or epsT>0):',
          pd.crosstab((D.epsS > 0) | (D.epsT > 0), D.C26).to_dict())

    # ── score: raw, within-game z, benchmark share ────────────────────────────────────────
    hdr('Score (person means; P01/P02 out)')
    P = Se[ok].groupby(level='pid').agg(score=('score', 'mean'), z=('z', 'mean'),
                                         share=('share', 'mean'))
    for k in ['score', 'z', 'share']:
        r = perm(P[k], C26_score, f'score:{k}')
        print(f'{k:6s} in={r["inMean"]:.3f} rest={r["restMean"]:.3f} n={r["nIn"]}/{r["nRest"]} '
              f'perm p={r["p"]:.4f}')
    rk = P.score.rank(ascending=False)
    rz = P.z.rank(ascending=False)
    print('\nRank of members out of', len(P), '(1 = best)  raw:', rk[list(C26_score)].to_dict(),
          ' z-within-game:', rz[list(C26_score)].to_dict())
    print('Member per-person means:\n', P.loc[sorted(C26_score)].round(3))
    # leave-one-out: does any single member carry it?
    print('\nLeave-one-out mean z (in vs rest):')
    for p in sorted(C26_score):
        g = C26_score - {p}
        print(f'  drop {p}: in={P.z[list(g)].mean():.3f}  rest={P.z.drop(list(g)).mean():.3f}')

    # ── behaviour: ten h1 features + session outcomes ────────────────────────────────────
    hdr('Behaviour (person level; P02 included, descriptive permutation p)')
    F = h1.features(S, T, R, ['pid']).set_index('key')
    F['netSecsRaw'] = np.expm1(F.netSecs)
    sesP = Se.groupby(level='pid').agg(
        missions=('missionsArrived', 'mean'), allocated=('nStrategic', 'mean'),
        completion=('completion', 'mean'), failures=('failures', 'mean'),
        episodes=('episodes', 'mean'), abandons=('abandons', 'mean'), drags=('drags', 'mean'),
        reliance=('reliance', 'mean'), scoreEff=('scoreEff', 'mean'))
    sesP['allocShare'] = Se.groupby(level='pid').apply(lambda g: g.nStrategic.sum() / g.missionsArrived.sum())
    sesP['abandonPerEp'] = Se.groupby(level='pid').apply(
        lambda g: g.abandons.sum() / g.episodes.sum() if g.episodes.sum() else np.nan)
    # tactical: median confirm latency
    T2 = T.copy()
    sesP['tacSecs'] = T2.groupby('pid').latency.median() / 1000
    sv = sess.groupby(level='pid')[['rtlx', 'trust_s', 'trust_t']].mean()
    X = F.join(sesP).join(sv)
    behaviours = ['took', 'preempt', 'edit', 'consult', 'keep', 'recSug', 'netSecsRaw', 'previews',
                  'toggles', 'dSmall', 'dLarge', 'tacSecs', 'allocShare', 'completion', 'episodes',
                  'abandonPerEp', 'drags', 'scoreEff', 'rtlx', 'trust_s', 'trust_t']
    rows = []
    for k in behaviours:
        r = perm(X[k], C26, f'beh:{k}')
        if r is None:
            continue
        pct = X[k].dropna().rank(pct=True)
        rows.append(dict(measure=k, C26=round(r['inMean'], 3), rest=round(r['restMean'], 3),
                         n=f"{r['nIn']}/{r['nRest']}", p=round(r['p'], 3),
                         **{p: round(X.loc[p, k], 2) if p in X.index else None for p in sorted(C26)},
                         pctiles=' '.join(f'{pct.get(p, np.nan):.2f}' for p in sorted(C26))))
    BT = pd.DataFrame(rows)
    print(BT.to_string(index=False))

    # reliance PC from fingerprint
    fp = json.loads((BASE / 'docs/analysis/combined/extras.json').read_text(encoding='utf-8'))['fingerprint']
    FP = pd.DataFrame(fp['points'])
    relP = FP.groupby('pid').rel.mean()
    r = perm(relP, C26, 'beh:rel(fingerprint PC1)')
    print(f'\nreliance axis (fingerprint rel): in={r["inMean"]:.2f} rest={r["restMean"]:.2f} '
          f'p={r["p"]:.3f}; members: {relP[list(C26)].round(2).to_dict()}; '
          f'pct: {relP.rank(pct=True)[list(C26)].round(2).to_dict()}')

    # does reliance explain the score gap?  OLS z ~ C26 + rel (person level), descriptive
    import statsmodels.formula.api as smf
    Q = P.join(relP).join(X[['took', 'consult', 'allocShare']]).dropna(subset=['z', 'rel'])
    Q['C26'] = Q.index.isin(C26_score).astype(int)
    for f in ['z ~ C26', 'z ~ C26 + rel', 'z ~ rel', 'z ~ C26 + allocShare']:
        m = smf.ols(f, Q).fit()
        print(f'{f:28s} b(C26)={m.params.get("C26", np.nan):+.3f} '
              f'(p={m.pvalues.get("C26", np.nan):.3f})  R2={m.rsquared:.3f}  n={int(m.nobs)}')
    print('rho(rel, z) =', round(Q[['rel', 'z']].corr('spearman').iloc[0, 1], 3))

    # ── demographics / dispositions ───────────────────────────────────────────────────────
    hdr('Demographics & dispositions (descriptive)')
    dem = pd.DataFrame({p: dict(age=v['dem'].get('age'), gender=v['dem'].get('gender'),
                                field=v['dem'].get('field'), gaming=v['dem'].get('gaming_frequency'),
                                sim=v['dem'].get('sim_experience'),
                                strat=v['dem'].get('strategy_experience'),
                                drone=v['dem'].get('drone_experience'),
                                command=v['dem'].get('command_experience'),
                                expMean=v.get('experienceMean'), aias=v.get('aias'),
                                verification=v.get('verification'), delegation=v.get('delegation'),
                                want_reasoning=(v.get('raw') or {}).get('verif_want_reasoning'))
                        for p, v in people.items()}).T
    print(dem.loc[sorted(C26)].to_string())
    for k in ['expMean', 'aias', 'verification', 'delegation', 'want_reasoning']:
        x = pd.to_numeric(dem[k], errors='coerce')
        r = perm(x, C26, f'disp:{k}')
        if r:
            print(f'{k:15s} in={r["inMean"]:.2f} rest={r["restMean"]:.2f} p={r["p"]:.3f}')
    print('\nfield counts, C26:', dem.loc[sorted(C26), 'field'].tolist())
    print('want_reasoning item distribution (all):',
          pd.to_numeric(dem.want_reasoning, errors='coerce').value_counts().sort_index().to_dict())
    print('Does the pre-study item predict score z? rho =',
          round(pd.concat([pd.to_numeric(dem.want_reasoning, errors='coerce'), P.z], axis=1)
                .dropna().corr('spearman').iloc[0, 1], 3))
    # experience vs z
    print('rho(expMean, z) =', round(pd.concat([pd.to_numeric(dem.expMean, errors='coerce'), P.z], axis=1)
                                     .dropna().corr('spearman').iloc[0, 1], 3))

    # ── base rate of 'a random group of 4 this extreme' among the codes ────────────────────
    hdr('Context: how unusual is this among all 28 codes?')
    out = []
    for c in [c for c in M.columns if c.startswith('C')]:
        g = set(M.index[M[c] == 1]) - HALF
        a = P.z[P.index.isin(g)]
        if len(a) >= 2:
            out.append((c, len(a), round(a.mean(), 2)))
    print(sorted(out, key=lambda t: -t[2])[:6])

    # ── rank-based view, coverage, and the 'said something similar' near-miss group ───────────
    hdr('Rank test, mission coverage, near-miss participants')
    from math import comb
    from scipy.stats import mannwhitneyu, spearmanr
    a, rest = P.z[P.index.isin(C26_score)], P.z[~P.index.isin(C26_score)]
    print('Mann-Whitney raw score p =', round(mannwhitneyu(P.score[P.index.isin(C26_score)],
                                                         P.score[~P.index.isin(C26_score)]).pvalue, 4),
          '| within-game z p =', round(mannwhitneyu(a, rest).pvalue, 4))
    print('P(4 random people of 31 all land in the top 6 by z) =', round(comb(6, 4) / comb(31, 4), 5))
    rows = []
    for path in sorted((BASE / 'Results/Participants').glob('P*.json')):
        pid = path.stem
        if pid == 'P09':
            continue
        log = json.loads(path.read_text(encoding='utf-8'))
        for run, ev in enumerate(log['sessions'], 1):
            arr = {e['missionId'] for e in ev if e['type'] == 'mission_arrived' and not e.get('isResidual')}
            alloc = {e['missionId'] for e in ev if e['type'] == 'strategic_choice'}
            rows.append(dict(pid=pid, run=run, cover=len(arr & alloc) / len(arr) if arr else np.nan,
                             unalloc=len(arr - alloc)))
    Cv = pd.DataFrame(rows).set_index(['pid', 'run']).join(Se[['game', 'completionPoints', 'penalty', 'z']])
    Cv = Cv[~Cv.index.get_level_values('pid').isin(HALF)]
    for k in ['completionPoints', 'penalty']:
        Cv[k + '_z'] = Cv.groupby('game')[k].transform(lambda s: (s - s.mean()) / s.std())
    Qc = Cv.groupby(level='pid').mean(numeric_only=True)
    Qc['C26'] = Qc.index.isin(C26_score)
    print(Qc.groupby('C26')[['cover', 'unalloc', 'completionPoints_z', 'penalty_z', 'z']].mean().round(3))
    print('members:\n', Qc.loc[sorted(C26_score), ['cover', 'unalloc', 'completionPoints_z', 'penalty_z']].round(2))
    print('rho(coverage, z) =', round(spearmanr(Qc.cover, Qc.z).correlation, 3),
          '| allocated every original mission: C26', (Qc[Qc.C26].unalloc == 0).mean(),
          'rest', round((Qc[~Qc.C26].unalloc == 0).mean(), 3))
    print('Top 12 by z:\n', Qc.sort_values('z', ascending=False)[['z', 'cover', 'unalloc']].head(12).round(2))
    near = {'P03', 'P04', 'P05', 'P06', 'P13', 'P20'}  # see coding_notes.md + interview notes
    print('near-miss z:', P.z.reindex(sorted(near)).round(2).to_dict(), 'mean',
          round(P.z.reindex(sorted(near)).mean(), 2))
    both = C26_score | near
    print('C26 + near-miss vs rest: Mann-Whitney p =',
          round(mannwhitneyu(P.z[P.index.isin(both)], P.z[~P.index.isin(both)]).pvalue, 3),
          '(not counted in TESTS; descriptive)')
    V = Se[ok].groupby(level='pid').agg(version=('version', 'first'), z=('z', 'mean'), swapped=('swapped', 'first'))
    print('mean z by version:', V.groupby('version').z.agg(['mean', 'size']).round(2).to_dict('index'))
    print('mean z by swapped:', V.groupby('swapped').z.mean().round(2).to_dict())

    hdr(f'Tests run: {len(TESTS)} permutation tests (uncorrected). p < .05:')
    for lab, p in TESTS:
        if p < .05:
            print(f'  {lab}: p={p:.4f}')


if __name__ == '__main__':
    main()
