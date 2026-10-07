#!/usr/bin/env python3
"""Workstream C (round 2) -- shared data layer: the reliance trait, its payoff, game difficulty/order.

Read-only over Results/ and docs/reports/. Writes nothing. Reuses the round-1 loaders:
  * scripts/analysis_round1/h4_h10_data.py   -- decisions() and sessions() (scores, benchmark share,
                                                missions never allocated, manual/uptake rates)
  * scripts/analysis_round1/h1_archetypes.py -- parse()/features()/impute_z()/kaiser_pcs(): the PC1
                                                reliance axis, recomputed WITHOUT the bootstrap

Adds:
  * game / order / swapped / sample flags (S-all, S-v112, S-s1, S-27, S-6)
  * the four performance metrics the amendment requires, on the rescaled score
    (P01/P02 ran on half task weights: rescaled to current weights as 2 x points - penalty, the
    h4 convention; available points likewise x2)
  * throughput measures per session: genuine missions arrived / allocated / never allocated, and
    a buzzer-censored mean queue time (arrival -> strategic choice; a mission never allocated waits
    until the end of the session). Abandoned missions' leftover work re-queues as <id>-R: residuals
    are NOT counted as new arrivals, and a parent abandoned after allocation counts as allocated
  * person predictors: gaming frequency, prior experience, first-two-minutes performance, session-1
    drone failures / abandonments
  * gee(): GEE with the small-sample (bias-reduced, Mancl-DeRouen) covariance, as the briefing requires
"""
from __future__ import annotations

import glob
import json
import os
import sys
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
sys.path.insert(0, str(BASE / 'scripts' / 'analysis_round1'))
warnings.simplefilter('ignore')

import h4_h10_data as H  # noqa: E402
import h1_archetypes as A  # noqa: E402
from agent_scenario_stats import events  # noqa: E402

PART = BASE / 'Results' / 'Participants'
SWAPPED = {'P31', 'P32', 'P33', 'P34', 'P35', 'P36'}
SESSION_S = 480.0
EARLY_S = 120.0  # "first two minutes"

ORD = {'gaming_frequency': {'Never': 0, 'Rarely': 1, 'Occasionally': 2, 'Weekly': 3, 'Daily': 4},
       'exp': {'None': 0, 'A little': 1, 'Moderate': 2, 'Extensive': 3}}
EXP_ITEMS = ['sim_experience', 'strategy_experience', 'drone_experience', 'autonomy_experience',
             'command_experience']


# ── statistics helpers ──────────────────────────────────────────────────────────────────────

def gee(formula, data, family='gaussian', group='pid'):
    fam = {'gaussian': sm.families.Gaussian(), 'binomial': sm.families.Binomial(),
           'poisson': sm.families.Poisson()}[family]
    return smf.gee(formula, group, data=data, family=fam,
                   cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type='bias_reduced')


def term(m, name):
    b = float(m.params[name])
    lo, hi = (float(x) for x in m.conf_int().loc[name])
    return dict(est=b, lo=lo, hi=hi, p=float(m.pvalues[name]), n_obs=int(m.nobs))


# ── per-session event extras (throughput and early performance) ─────────────────────────────

def _session_extras(pid, run, evs):
    start = next((e for e in evs if e['type'] == 'session_start'), None)
    end = next((e for e in evs if e['type'] == 'session_ended'), None)
    if not start or not end:
        return None
    weight = start['taskWeight']
    scale = weight['5'] / 100.0
    end_el = end.get('elapsed') or SESSION_S
    arrivals, chosen = {}, {}
    fails_early = 0
    for e in evs:
        t = e['type']
        if t == 'mission_arrived' and not e.get('isResidual'):
            arrivals[e['missionId']] = e.get('arrivalTime', e.get('elapsed'))
        elif t == 'strategic_choice':
            chosen.setdefault(e['missionId'], e.get('elapsed'))
        elif t == 'drone_failure' and (e.get('elapsed') or 1e9) <= EARLY_S:
            fails_early += 1
    ctx = [e for e in evs if (e.get('elapsed') or 1e9) <= EARLY_S and e.get('context')]
    # session score (points - penalty, floored at 0) at 120 s; /scale puts P01/P02 on current weights
    # for the points part (penalty does not scale) -- approximate, and only ranks within game are used
    pts_early = (ctx[-1]['context']['score'] / scale) if ctx else 0.0
    q = [min(chosen.get(m, end_el), end_el) - a for m, a in arrivals.items()]
    alloc_early = sum(1 for m, a in arrivals.items() if a <= EARLY_S and chosen.get(m, 1e9) <= EARLY_S)
    arr_early = sum(1 for a in arrivals.values() if a <= EARLY_S)
    return dict(pid=pid, run=run, n_arrived=len(arrivals),
                n_alloc=sum(1 for m in arrivals if m in chosen),
                queue_mean=float(np.mean(q)) if q else np.nan,
                n_abandoned=sum(1 for e in evs if e['type'] == 'mission_abandoned'),
                n_requeued=sum(1 for e in evs if e['type'] == 'task_requeued'),
                pts_early=pts_early, alloc_early=alloc_early, arr_early=arr_early,
                fails_early=fails_early)


@lru_cache(maxsize=1)
def _extras_and_people():
    rows, people = [], {}
    for path in sorted(glob.glob(str(PART / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in H.EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        dem = log.get('demographics') or {}
        people[pid] = dem
        for run, sess in enumerate(log['sessions'], start=1):
            evs = events(sess)
            r = _session_extras(pid, run, evs)
            if r is not None:
                rows.append(r)
    return pd.DataFrame(rows), people


# ── the reliance axis (round-1 H1 PC1, no bootstrap) ────────────────────────────────────────

@lru_cache(maxsize=1)
def h1_parse():
    return A.parse()


@lru_cache(maxsize=1)
def reliance_axis():
    """Returns (P, FS, loadings, var share): P = per person PC1 (pooled) + s1/s2 PC1; FS = per-session PC1."""
    Sd, T, R, SESS = h1_parse()
    pids = sorted(Sd.pid.unique())
    F = A.features(Sd, T, R, 'pid')
    F['pid'] = F.key
    F = F.set_index('pid').loc[pids].reset_index()
    Zdf, _ = A.impute_z(F, verbose=False)
    Z = Zdf[A.FEATURES].values
    pca, ev, keep = A.kaiser_pcs(Z)
    if pca.components_[0][A.FEATURES.index('took')] < 0:
        pca.components_[0] *= -1
    P = pd.DataFrame({'pid': pids, 'PC1': pca.transform(Z)[:, 0]})
    P['PC1'] = P.PC1 / P.PC1.std(ddof=0)  # in SD units
    FS = A.features(Sd, T, R, ['pid', 'run'])
    FS['pid'] = [k[0] for k in FS.key]
    FS['run'] = [k[1] for k in FS.key]
    scen = SESS.set_index(['pid', 'run']).scenario
    FS['scenario'] = [scen.get((p, r)) for p, r in zip(FS.pid, FS.run)]
    FS['cell'] = FS.run.astype(str) + FS.scenario
    FSz, _ = A.impute_z(FS, by='cell', verbose=False)
    FS['sPC1'] = FSz[A.FEATURES].values @ pca.components_[0]
    FS['sPC1'] = FS.sPC1 / FS.sPC1.std(ddof=0)
    # X3: the same axis with decision speed (netSecs) taken out
    w = pca.components_[0].copy()
    w[A.FEATURES.index('netSecs')] = 0.0
    FS['sPC1_nos'] = FSz[A.FEATURES].values @ w
    FS['sPC1_nos'] = FS.sPC1_nos / FS.sPC1_nos.std(ddof=0)
    # uncentred version (z-scored on all sessions jointly, so scenario/run differences in reliance stay in)
    FSa, _ = A.impute_z(FS, verbose=False)
    FS['sPC1_raw'] = FSa[A.FEATURES].values @ pca.components_[0]
    FS['sPC1_raw'] = FS.sPC1_raw / FS.sPC1_raw.std(ddof=0)
    for run in (1, 2):
        P['s%d_PC1' % run] = P.pid.map(FS[FS.run == run].set_index('pid').sPC1)
    load = dict(zip(A.FEATURES, np.round(pca.components_[0] * np.sqrt(ev[0]), 2)))
    return P, FS[['pid', 'run', 'sPC1', 'sPC1_raw', 'sPC1_nos']], load, float(pca.explained_variance_ratio_[0])


# ── assembled tables ─────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load():
    S, D = H.sessions(), H.decisions()
    X, people = _extras_and_people()
    S = S.merge(X, on=['pid', 'run'], how='left')
    P, FS, _, _ = reliance_axis()
    S = S.merge(FS, on=['pid', 'run'], how='left')
    first = S[S.run == 1].set_index('pid').scenario
    S['order'] = S.pid.map(lambda p: 'SF' if first[p] == 'strategic' else 'TF')  # scenario played first
    S['swapped'] = S.pid.isin(SWAPPED).astype(int)
    S['tact'] = (S.scenario == 'tactical').astype(int)
    S['run2'] = (S.run == 2).astype(int)
    S['gidx2'] = (S.planIndex == 2).astype(int)
    # pairing: S1+T2 (default for SF up to P30) vs S2+T1
    pair = S.groupby('pid').apply(lambda g: 'S1T2' if set(g.game) == {'strategic|1', 'tactical|2'} else 'S2T1')
    S['pairing'] = S.pid.map(pair)
    # performance, P01/P02 rescaled to current weights (2 x points - penalty, floored at 0 like the app)
    S['avail_r'] = S.availablePoints / S.taskWeightScale
    S['score_r'] = S.score_rescaled
    S['eff'] = S.score_r / S.avail_r
    g = S.groupby('game').score_r
    S['z'] = (S.score_r - g.transform('mean')) / g.transform('std')
    S['bshare'] = S.score_r / S.benchmark
    S['best'] = S.score_r / g.transform('max')
    S['unalloc_share'] = 1 - S.n_alloc / S.n_arrived
    S['unallocPts_r'] = S.unallocPoints / S.taskWeightScale
    S['unallocPts_eff'] = S.unallocPts_r / S.avail_r
    D = D.merge(S[['pid', 'run', 'order', 'swapped', 'pairing']], on=['pid', 'run'], how='left')
    D['wait_open'] = D.wait - D.secs  # arrival -> modal open
    Sd = h1_parse()[0][['pid', 'run', 'missionId', 'net']].rename(columns={'net': 'net_secs'})
    # a few missions carry two strategic decisions (re-allocated): align by occurrence order
    Sd['k'] = Sd.groupby(['pid', 'run', 'missionId']).cumcount()
    D['k'] = D.groupby(['pid', 'run', 'missionId']).cumcount()
    D = D.merge(Sd, on=['pid', 'run', 'missionId', 'k'], how='left')  # decision time beyond the forced reveal
    # person table
    P = P.merge(S[S.run == 1][['pid', 'order', 'swapped', 'pairing', 'v112']], on='pid')
    pr = []
    for pid, dem in people.items():
        exp = [ORD['exp'].get(dem.get(k)) for k in EXP_ITEMS]
        exp = [x for x in exp if x is not None]
        pr.append(dict(pid=pid, gaming=ORD['gaming_frequency'].get(dem.get('gaming_frequency'), np.nan),
                       experience=float(np.mean(exp)) if exp else np.nan,
                       sim_exp=ORD['exp'].get(dem.get('sim_experience'), np.nan),
                       strat_exp=ORD['exp'].get(dem.get('strategy_experience'), np.nan)))
    P = P.merge(pd.DataFrame(pr), on='pid', how='left')
    # game-standardised (over all sessions of that game, both runs: run-1 cells of S2/T2 hold only 3 people)
    gg = S.groupby('game')
    for c in ('pts_early', 'failures'):
        S[c + '_z'] = (S[c] - gg[c].transform('mean')) / gg[c].transform('std')
    S['early_alloc'] = S.alloc_early / S.arr_early.replace(0, np.nan)
    s1 = S[S.run == 1].set_index('pid')
    # first-two-minutes performance in session 1: session score at 120 s, z-scored within game
    P['early_pts_z'] = P.pid.map(s1.pts_early_z)
    P['early_alloc'] = P.pid.map(s1.early_alloc - S.groupby('game').early_alloc.mean().reindex(s1.game).values)
    P['s1_fail_z'] = P.pid.map(s1.failures_z)
    P['s1_fail'] = P.pid.map(s1.failures)
    P['s1_aband'] = P.pid.map(s1.n_abandoned)
    P['s1_eff_z'] = P.pid.map(s1.z)
    return S, D, P


def sample(df, code):
    if code == 'S-all':
        return df
    if code == 'S-v112':
        return df[df.v112.astype(bool)]
    if code == 'S-s1':
        return df[df.run == 1] if 'run' in df else df
    if code == 'S-27':
        return df[~df.pid.isin(SWAPPED)]
    if code == 'S-6':
        return df[df.pid.isin(SWAPPED)]
    raise ValueError(code)


if __name__ == '__main__':
    S, D, P = load()
    pd.set_option('display.width', 250)
    pd.set_option('display.max_columns', 40)
    print(S[['pid', 'run', 'game', 'order', 'pairing', 'score_r', 'eff', 'z', 'bshare', 'best', 'n_arrived',
             'n_alloc', 'queue_mean', 'pts_early', 'sPC1']].to_string())
    print(P.to_string())
    print(reliance_axis()[2:])
