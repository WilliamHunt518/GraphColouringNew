#!/usr/bin/env python3
"""
Round 2 · workstream A (recovery) -- shared loader and model helpers.

Builds one row per recovery episode by reusing round-1 H3's episode reconstruction
(`scripts/analysis_round1/h3_recovery.py: parse_session`, which carries the CORRECTED time-local
fixability check -- not study_analysis.read_session's buggy feasibleWithBusy) and adds the
situational predictors workstream A needs. Read-only on Results/; writes nothing.

Per-person reliance axis (PC1) is recomputed from h1_archetypes.py's feature code without its
bootstrap (`pc1_scores`).
"""
import json, math, sys, warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
sys.path.insert(0, str(BASE / 'scripts' / 'analysis_round1'))
warnings.filterwarnings('ignore')

import study_analysis as sa                         # noqa: E402
import h3_recovery as h3                            # noqa: E402
from agent_scenario_stats import events, vrank      # noqa: E402

LOG_DIR = BASE / 'Results' / 'Participants'
EXCLUDE = {'P09'}
SWAPPED = {'P31', 'P32', 'P33', 'P34', 'P35', 'P36'}
V112 = vrank('study-v1.12')
V15 = vrank('study-v1.5')
TRAVEL_ALLOW = 15.0   # s: worst-case in-zone hop for the slowest drone (zone diameter 160 / speed 9 ~ 18 s;
                      # most hops are shorter). Used only for the "could the fix finish?" flag.


def _colours(comp):
    p = (comp or {}).get('primary') or {}
    return {k for k, v in p.items() if v}


def augment(evs, eps, pid, run):
    """Add situational fields to H3's episodes for one session."""
    start = next(e for e in evs if e['type'] == 'session_start')
    tw = {int(k): v for k, v in (start.get('taskWeight') or {}).items()}
    scale = 100.0 / max(tw.values()) if tw else 1.0          # P01/P02 ran on half weights -> x2
    dur = start.get('sessionDuration') or sa.SESSION_S
    comps, mtasks, mcat = {}, defaultdict(list), {}
    for e in evs:
        if e['type'] == 'mission_arrived':
            comps.update(e.get('taskCompositions') or {})
            mtasks[e['missionId']] = [(t['id'], int(t['type'])) for t in e.get('tasks') or []]
            mcat[e['missionId']] = e.get('category')
    done_at = {}
    for e in evs:
        if e['type'] == 'task_completed':
            done_at[e['taskId']] = e.get('completionTime') or e['elapsed']
    fails = sorted(e['elapsed'] for e in evs if e['type'] == 'drone_failure')
    game_idx = start.get('planSeedIndex') or run
    scen = start.get('complexity')
    windows = [(x['opened'], x['closed'], x['missionId']) for x in eps]
    out = []
    for i, ep in enumerate(sorted(eps, key=lambda x: x['opened'])):
        t, m = ep['opened'], ep['missionId']
        tasks = mtasks.get(m, [])
        left = [(tid, ty) for tid, ty in tasks if not (tid in done_at and done_at[tid] <= t)]
        reward = scale * sum(tw.get(ty, 0) for _, ty in left)
        rewardAff = scale * sum(tw.get(ty, 0) for tid, ty in tasks if tid in ep['affected'])
        cols = set().union(*[_colours(comps.get(tid)) for tid, _ in tasks]) if tasks else set()
        need = max([(comps.get(x) or {}).get('baseTime') or 0 for x in ep['affected']] or [0]) + TRAVEL_ALLOW
        tl = ep['timeRemaining'] if ep['timeRemaining'] is not None else dur - t
        clean = ep['fixIdleRecon'] if ep['vrank'] >= V15 else ep['fixIdleLogged']
        r = dict(ep)
        r.pop('events', None); r.pop('presses', None)
        r.update(
            game=f'{scen}|{game_idx}', gameIndex=game_idx, scale=scale,
            attempted=int(ep['suggest'] > 0 or ep['drags'] > 0),
            abandoned=int(ep['outcome'] == 'abandoned'),
            unresolved=int(ep['outcome'] == 'unresolved'),
            timeLeft=tl / 60.0, needSec=need, finishable=int(tl > need), last90=int(tl <= 90),
            reward=reward / 100.0, rewardAff=rewardAff / 100.0, nTasksLeft=len(left),
            nTasksTotal=len(tasks), dronesLeft=ep['nIdle'] + ep['nBusy'],
            ncolMission=len(cols), threeType=int(len(cols) == 3),
            suggestClean=int(bool(clean)),
            affectedDone=int(all(x in done_at for x in ep['affected'])),
            recentFail60=sum(1 for f in fails if t - 60 <= f < t - 0.01),
            concurrentRec=sum(1 for (o, c, mm) in windows if mm != m and o < t < c),
            priorSameMission=sum(1 for (o, c, mm) in windows if mm == m and o < t),
            epIndex=i + 1,
            presses_detail=[dict(at=p['at'], result=p['result'], blind=p['blind'], next=p['next'])
                            for p in ep['presses']],
            closedAt=ep['closed'])
        out.append(r)
    return out


def load_episodes():
    rows = []
    for f in sorted(LOG_DIR.glob('P*.json')):
        pid = f.stem
        if pid in EXCLUDE:
            continue
        d = json.loads(f.read_text(encoding='utf-8'))
        for i, s in enumerate(d.get('sessions') or []):
            evs = events(s)
            r = h3.parse_session(evs, pid, i + 1)
            if not r:
                continue
            for ep in r['episodes']:
                ep.pop('plan', None)
            rows += augment(evs, r['episodes'], pid, i + 1)
    df = pd.DataFrame(rows)
    # person-level attributes
    first_scen = df[df.run == 1].groupby('pid').scenario.first()
    # sessions with no episode in run 1 still have an order: read it from the logs
    order = {}
    for f in sorted(LOG_DIR.glob('P*.json')):
        if f.stem in EXCLUDE:
            continue
        d = json.loads(f.read_text(encoding='utf-8'))
        st = [e for e in events(d['sessions'][0]) if e['type'] == 'session_start']
        order[f.stem] = st[0]['complexity'] if st else first_scen.get(f.stem)
        vr = [vrank(next((e.get('appVersion') or 'pre-tag') for e in events(s) if e['type'] == 'session_start'))
              for s in d['sessions']]
        order[f.stem + '_v'] = min(vr)
    df['order'] = df.pid.map(lambda p: order[p])          # scenario played FIRST
    df['v112person'] = df.pid.map(lambda p: int(order[p + '_v'] >= V112))
    df['swapped'] = df.pid.isin(SWAPPED).astype(int)
    df['run2'] = (df.run == 2).astype(int)
    df['tacScen'] = (df.scenario == 'tactical').astype(int)
    # chronological index across both runs within person
    df = df.sort_values(['pid', 'run', 'opened']).reset_index(drop=True)
    df['seqAll'] = df.groupby('pid').cumcount() + 1
    return df


# ------------------------------------------------------------------------------------------------
# Reliance axis (PC1), recomputed from h1_archetypes' features, no bootstrap
# ------------------------------------------------------------------------------------------------

def pc1_scores(drop=()):
    import h1_archetypes as h1
    from sklearn.decomposition import PCA
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        S, T, R, SESS = h1.parse()
        F = h1.features(S, T, R, 'pid')
        F['pid'] = F.key
        pids = sorted(S.pid.unique())
        F = F.set_index('pid').loc[pids].reset_index()
        cols = [c for c in h1.FEATURES if c not in drop]
        Zdf, _ = h1.impute_z(F, cols=cols)
    Z = Zdf[cols].values
    pca = PCA().fit(Z)
    comp = pca.components_[0]
    if comp[cols.index('took')] < 0:
        comp = -comp
    sc = Z @ comp
    ev = pca.explained_variance_ratio_[0]
    load = dict(zip(cols, np.round(comp * np.sqrt(pca.explained_variance_[0] * (len(Z) - 1) / len(Z)), 2)))
    return pd.Series(sc, index=pids), ev, load


# ------------------------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------------------------

def gee_fit(formula, df, binomial=True):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    return smf.gee(formula, 'pid', data=df, family=fam,
                   cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type='bias_reduced')


def est(formula, df, term, binomial=True):
    """Return dict(b, lo, hi, p) on the link scale; None on failure."""
    try:
        if df.pid.nunique() < 3 or len(df) < 8:
            return None
        y = formula.split('~')[0].strip()
        if df[y].nunique() < 2:
            return None
        m = gee_fit(formula, df, binomial)
        b = float(m.params[term]); ci = m.conf_int().loc[term]
        if not np.isfinite(b) or abs(b) > 20 or not np.isfinite(ci[0]) or max(abs(ci[0]), abs(ci[1])) > 30:
            return None        # separation / degenerate fit
        if not np.isfinite(float(m.pvalues[term])) or float(ci[1] - ci[0]) < 1e-9:
            return None        # no variation in the predictor within this sample
        return dict(b=b, lo=float(ci[0]), hi=float(ci[1]), p=float(m.pvalues[term]))
    except Exception:
        return None


def add_within(df, x):
    """Within-person (centred) and between-person (person mean) parts of x, within this sample."""
    df = df.copy()
    df[x + '_b'] = df.groupby('pid')[x].transform('mean')
    df[x + '_w'] = df[x] - df[x + '_b']
    return df


def sign(v):
    return 0 if v is None else (1 if v > 0 else -1 if v < 0 else 0)
