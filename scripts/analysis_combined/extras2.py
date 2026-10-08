#!/usr/bin/env python3
"""Second set of follow-ups for the combined findings page (Results/findings_combined.html).

Read-only over Results/. Writes docs/analysis/combined/extras2.json, which build_findings_synthesis.py
folds into the page payload next to extras.json, and prints every number the page quotes. Run from the
repo root:

    python scripts/analysis_combined/extras2.py

extras.json is deliberately NOT rewritten here: part of it (the in-play narration coding and quotes)
needs Results/Narration/, which is gitignored and only complete on the machine that ran the narration
pipeline. Everything below needs only Results/Participants/.

Five questions, asked 2026-10-08 after reading the combined page:

1 · MORE GROUP MEASURES ("X of 33" bars). Beyond score / workload / trust: how much work a person got
    through (tasks and missions completed, allocations per minute), how fast they decided, how much they
    used each assistant, and penalty accrued. Per person = mean over their two sessions. Tested on
    GAME-CENTRED values (each session minus that game's mean) because the four games differ ~1.9x in
    load and a person's pair of games depends on when they took part.
2 · ARCHETYPES -- SIGNAL OR NOISE? Archetypal analysis always returns k corners, whatever the data.
    So the observed numbers are compared with the same pipeline run on simulated operators who have the
    SAME habits, the same habit-habit correlations and the same session-1/session-2 stability, but are
    drawn from one continuous cloud (Gaussian copula, empirical marginals) -- i.e. no types at all.
3 · DEEP QUEUES, AGAIN (theme 4). Finer bins (to 6+), what can be seen (3-4 queue cards at rest, 0-1
    while a decision is open -- read off the recordings), time in session, the complexity of the card
    being decided and of the cards waiting, which card gets picked, and a within-person view.
4 · WHAT IS BEHIND EACH DOT (theme 8). For every point of the event-study lines: the complexity of the
    missions that make it up and the rate a model of mission, time, game and person would expect.
5 · OTHER ANCHORS. The same event study lined up on: first illogical card, first Suggest refusal, first
    WRONG refusal (blind spot), first drone failure, first abandoned mission -- each with both assistants
    as outcomes and a placebo (random anchor) null. Plus the full list of wrong refusals that ended in
    abandonment (the case to track down).
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

BASE = Path(__file__).resolve().parents[2]
for p in ('scripts', 'scripts/analysis_round1', 'scripts/analysis_round2', 'scripts/analysis_combined'):
    sys.path.insert(0, str(BASE / p))
warnings.filterwarnings('ignore')

OUT = BASE / 'docs' / 'analysis' / 'combined' / 'extras2.json'
PARTS = BASE / 'Results' / 'Participants'
EXCLUDE = {'P09'}
SEED = 20261008
N_NULL = int(os.environ.get('EXTRAS2_NULL', 200))       # archetype null simulations
N_PLACEBO = int(os.environ.get('EXTRAS2_PLACEBO', 1000))  # random-anchor draws per event study
VISIBLE = 3      # queue cards fully visible at rest in the recordings (3 + a header on a short window, 4 on a tall one)


def hdr(s):
    print('\n' + '=' * 96 + '\n' + s + '\n' + '=' * 96)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def r(x, d=3):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, d) if np.isfinite(x) else None


def gee(formula, d, binomial=True):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    m = smf.gee(formula, 'pid', data=d, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    try:
        return m.fit(cov_type='bias_reduced')
    except Exception:
        return m.fit()


def orow(m, name, binomial=True):
    ci = m.conf_int().loc[name]
    t = np.exp if binomial else (lambda v: v)
    return dict(est=r(t(m.params[name]), 4), lo=r(t(ci[0]), 4), hi=r(t(ci[1]), 4), p=r(m.pvalues[name], 5))


def holm(ps):
    order = np.argsort(ps)
    out, run = [None] * len(ps), 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, ps[i] * (len(ps) - k)))
        out[i] = run
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# data
# ════════════════════════════════════════════════════════════════════════════════════════════

def raw_logs():
    """Per (pid, run): arrivals, strategic choices, abandons, task-affecting drone failures, session end."""
    out = {}
    for path in sorted(glob.glob(str(PARTS / 'P*.json'))):
        pid = Path(path).stem
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        starts = [e for s in log['sessions'] for e in s if e['type'] == 'session_start']
        if not starts:
            continue
        primary = starts[0]['taskPrimary']
        for run, evs in enumerate(log['sessions'], start=1):
            arr, chosen, ab, fail, end = {}, {}, [], [], None
            for e in evs:
                t = e['type']
                if t == 'mission_arrived':
                    nd = sum(sum(primary[str(k['type'])].values()) for k in e.get('tasks', []))
                    arr[e['missionId']] = dict(t=e['elapsed'], ntasks=len(e.get('tasks', [])), ndrones=nd)
                elif t == 'strategic_choice':
                    chosen.setdefault(e['missionId'], e['elapsed'])
                elif t == 'mission_abandoned':
                    ab.append(e['elapsed'])
                elif t == 'drone_failure' and e.get('taskId'):
                    fail.append(e['elapsed'])
                elif t == 'session_ended':
                    end = e
            out[(pid, run)] = dict(arr=arr, chosen=chosen, ab=ab, fail=fail, end=end)
    return out


def load():
    import build_findings_synthesis as b
    import h3_recovery as h3
    import wB_common as w
    S, T, R, tl = quiet(w.build)
    eps = quiet(h3.load_all)[0]
    dec = quiet(b.load_decisions)
    logs = raw_logs()
    S, T = S[~S.pid.isin(EXCLUDE)].copy(), T[~T.pid.isin(EXCLUDE)].copy()
    S['t'] = S.elapsed_open.astype(float)
    T['t'] = T.open_ts / 1000.0
    # the illogical-card flag lives on load_decisions; both tables are one row per strategic choice
    # in the same order, so line them up and check they agree on mission size
    S = S.sort_values(['pid', 'run', 'choice_ts']).reset_index(drop=True)
    dec = dec.sort_values(['pid', 'run', 'idx']).reset_index(drop=True)
    key = lambda d: d.groupby(['pid', 'run']).cumcount()
    S['k'], dec['k'] = key(S), key(dec)
    S = S.merge(dec[['pid', 'run', 'k', 'odd', 'ndrones']].rename(columns={'ndrones': 'nd_chk'}),
                on=['pid', 'run', 'k'], how='left')
    mism = int((S.nd_chk != S.ndrones).sum())
    print('strategic rows %d, tactical rows %d; odd-card merge mismatches: %d' % (len(S), len(T), mism))
    assert mism == 0, 'decision tables out of step'
    # what was waiting when each strategic decision opened, from the raw log
    qt, qd, pos, qn = [], [], [], []
    for rr in S.itertuples():
        L = logs[(rr.pid, rr.run)]
        wait = [(a['t'], m, a) for m, a in L['arr'].items()
                if a['t'] <= rr.t + 1e-6 and L['chosen'].get(m, 1e9) > rr.t - 1e-6]
        others = [x for x in wait if x[1] != rr.missionId]
        qn.append(len(others))
        qt.append(sum(x[2]['ntasks'] for x in others))
        qd.append(sum(x[2]['ndrones'] for x in others))
        order = [m for _, m, _ in sorted(wait)]
        pos.append(order.index(rr.missionId) + 1 if rr.missionId in order else np.nan)
    S['q_rebuilt'], S['q_tasks'], S['q_drones'], S['pickPos'] = qn, qt, qd, pos
    agree = float((S.q_rebuilt == S.st_queued).mean())
    print('rebuilt queue count agrees with st_queued for %.0f%% of decisions' % (100 * agree))
    return S, T, eps, logs, agree


def add_expected(D, y, extra=()):
    """Expected probability of y from what the decision was (mission size, types, tasks), when (minute),
    which game, and who (the person's own rate on their OTHER decisions, shrunk). The queue is left out
    on purpose so the expected value can be compared across queue depths."""
    D = D.copy()
    g = D.groupby('pid')[y]
    s, n = g.transform('sum'), g.transform('size')
    base = (s - D[y] + 1) / (n - 1 + 2)
    D['base'] = np.log(base / (1 - base))
    rhs = 'ndrones + ntasks + ncolours + emin + C(game) + base' + ''.join(' + ' + e for e in extra)
    d = D.dropna(subset=['ndrones', 'ntasks', 'ncolours', 'emin', y])
    m = smf.glm(f'{y} ~ {rhs}', d, family=sm.families.Binomial()).fit()
    D['exp'] = m.predict(D)
    D['res'] = D[y] - D['exp']
    return D


# ════════════════════════════════════════════════════════════════════════════════════════════
# 1 · per-person measures for the "X of 33" bars
# ════════════════════════════════════════════════════════════════════════════════════════════

PERSON_MEASURES = [
    # key, label, unit
    ('tasks', 'Tasks completed per session', ''),
    ('missions', 'Missions completed per session', ''),
    ('alloc', 'Missions allocated per minute', '/min'),
    ('decide', 'Median seconds per strategic decision', 's'),
    ('took', 'Strategy cards taken', '%'),
    ('suggest', 'Tactical plans with Suggest pressed', '%'),
    ('penalty', 'Waiting penalty per session', ''),
]


def person_measures(S, T, logs):
    hdr('1 · Extra per-person measures for the group bars')
    rows = []
    for (pid, run), L in logs.items():
        e = L['end']
        if not e:
            continue
        s = S[(S.pid == pid) & (S.run == run)]
        t = T[(T.pid == pid) & (T.run == run)]
        if not len(s):
            continue
        ctx = e.get('context') or {}
        rows.append(dict(pid=pid, run=run, game=s.game.iloc[0],
                         tasks=(e.get('taskOutcomes') or {}).get('completed'),
                         missions=ctx.get('missionsCompleted'),
                         alloc=len(s) / 8.0, decide=s.secs.median(), took=s.took.mean(),
                         suggest=t.consulted.mean() if len(t) else np.nan,
                         penalty=e.get('penaltyAccrued')))
    P = pd.DataFrame(rows)
    keys = [k for k, _, _ in PERSON_MEASURES]
    C = P.copy()
    for k in keys:
        C[k] = P[k] - P.groupby('game')[k].transform('mean')
    raw, cen = P.groupby('pid')[keys].mean(), C.groupby('pid')[keys].mean()
    out = {pid: {k: r(raw.loc[pid, k], 4) for k in keys} | {k + '_c': r(cen.loc[pid, k], 4) for k in keys}
           for pid in raw.index}
    print('per-session ranges:', {k: (r(P[k].min(), 2), r(P[k].max(), 2)) for k in keys})
    print('game means:', P.groupby('game')[keys].mean().round(2).to_dict('index'))
    return dict(people=out, measures=[dict(k=k, label=l, unit=u) for k, l, u in PERSON_MEASURES],
                gameMeans={g: {k: r(v, 3) for k, v in row.items()} for g, row in P.groupby('game')[keys].mean().iterrows()})


# ════════════════════════════════════════════════════════════════════════════════════════════
# 2 · archetypes: signal or noise?
# ════════════════════════════════════════════════════════════════════════════════════════════

def _nearest_corr(Rm):
    w, V = np.linalg.eigh((Rm + Rm.T) / 2)
    Rm = V @ np.diag(np.clip(w, 1e-4, None)) @ V.T
    d = np.sqrt(np.diag(Rm))
    return Rm / np.outer(d, d)


def _copula(Xobs, n, rng):
    """n draws with the empirical marginals and rank correlations of Xobs, from a single Gaussian cloud."""
    rho = stats.spearmanr(Xobs).correlation
    Rm = _nearest_corr(2 * np.sin(np.pi * rho / 6))
    Zs = rng.multivariate_normal(np.zeros(len(Rm)), Rm, size=n)
    U = stats.norm.cdf(Zs)
    return np.column_stack([np.quantile(Xobs[:, j], U[:, j]) for j in range(Xobs.shape[1])])


def _best(X, k, starts, iters):
    import extras as x1
    best = None
    for s_ in range(starts):
        A, Zk, rss = x1._archetypes(X, k, x1.SEED + 31 * s_, iters=iters)
        if best is None or rss < best[2]:
            best = (A, Zk, rss)
    return best


def _arch_summary(X, S1, S2, starts, iters=400):
    from itertools import permutations
    tot = float(((X - X.mean(0)) ** 2).sum())
    expl = {}
    A = None
    for k in (2, 3, 4):
        Ak, Zk, rss = _best(X, k, starts, iters)
        expl[k] = 1 - rss / tot
        if k == 3:
            A = Ak
    A1, Z1, _ = _best(S1, 3, starts, iters)
    A2, Z2, _ = _best(S2, 3, starts, iters)
    best = max(permutations(range(3)), key=lambda pm: sum(np.corrcoef(Z1[i], Z2[pm[i]])[0, 1] for i in range(3)))
    prof = sorted([np.corrcoef(Z1[i], Z2[best[i]])[0, 1] for i in range(3)], reverse=True)
    dom1 = A1.argmax(1)
    dom2 = np.array([best.index(j) for j in A2.argmax(1)])
    return dict(expl2=expl[2], expl3=expl[3], expl4=expl[4], gain3=expl[3] - expl[2],
                pure=int((A.max(1) >= .8).sum()), mixed=int((A.max(1) < .6).sum()), medMax=float(np.median(A.max(1))),
                prof1=prof[0], prof2=prof[1], prof3=prof[2], same=float((dom1 == dom2).mean()))


def archetype_null():
    hdr('2 · Archetypes: do they beat a continuous cloud with the same habits and stability?')
    import extras as x1
    import h1_archetypes as h1
    import build_findings_synthesis as b
    S_, T_, R_, SESS = quiet(h1.parse)
    F = h1.features(S_, T_, R_, ['pid', 'run'])
    F[['pid', 'run']] = pd.DataFrame(F.key.tolist(), index=F.index)
    dec = quiet(b.load_decisions)
    gidx = dec.groupby(['pid', 'run']).agg(scenario=('scenario', 'first'), plan=('planIndex', 'first'))
    F = F.join(gidx, on=['pid', 'run'])
    F['game'] = F.scenario.astype(str) + '|' + F.plan.astype(str)
    cols = h1.FEATURES
    Z, _ = quiet(h1.impute_z, F, cols, by='game')
    Z[cols] = Z[cols].fillna(0.0)
    both = Z.groupby('pid').run.nunique()
    Z = Z[Z.pid.isin(both[both == 2].index)].sort_values(['pid', 'run'])
    S1 = Z[Z.run == 1].set_index('pid')[cols]
    S2 = Z[Z.run == 2].set_index('pid')[cols].loc[S1.index]
    S1, S2 = S1.to_numpy(), S2.to_numpy()
    X = (S1 + S2) / 2
    # compared with the nulls under the SAME fitting settings (fewer starts and iterations, for speed),
    # so a truncated fit cannot favour either side; the full fit is kept alongside for reference
    obs = _arch_summary(X, S1, S2, starts=4, iters=150)
    obs_full = _arch_summary(X, S1, S2, starts=20)
    print('observed (null settings):', {k: r(v, 3) for k, v in obs.items()})
    print('observed (full fit):     ', {k: r(v, 3) for k, v in obs_full.items()})
    rng = np.random.default_rng(SEED)
    J = np.hstack([S1, S2])                         # 20 columns: keeps each habit's own retest correlation
    nulls = {'stable': [], 'nocorr': []}
    for i in range(N_NULL):
        Jn = _copula(J, len(J), rng)
        a, bb = Jn[:, :10], Jn[:, 10:]
        nulls['stable'].append(_arch_summary((a + bb) / 2, a, bb, starts=4, iters=150))
        # same marginals and retest, but the ten habits shuffled independently between people (no style)
        perm = [rng.permutation(len(J)) for _ in range(10)]
        a2 = np.column_stack([S1[perm[j], j] for j in range(10)])
        b2 = np.column_stack([S2[perm[j], j] for j in range(10)])
        nulls['nocorr'].append(_arch_summary((a2 + b2) / 2, a2, b2, starts=4, iters=150))
        if (i + 1) % 10 == 0:
            print('  null draws', i + 1, flush=True)
    out = dict(observed={k: r(v, 4) for k, v in obs.items()}, observedFull={k: r(v, 4) for k, v in obs_full.items()},
               n=N_NULL, nulls={})
    for name, L in nulls.items():
        D = pd.DataFrame(L)
        row = {}
        for k in obs:
            v = D[k].to_numpy()
            row[k] = dict(mean=r(v.mean(), 4), lo=r(np.percentile(v, 2.5), 4), hi=r(np.percentile(v, 97.5), 4),
                          pAbove=r((1 + (v >= obs[k]).sum()) / (1 + len(v)), 4),
                          hist=np.histogram(v, bins=24)[0].tolist(),
                          edges=[r(e, 4) for e in np.histogram(v, bins=24)[1]])
        out['nulls'][name] = row
        print('null %-7s' % name, {k: (row[k]['mean'], row[k]['pAbove']) for k in obs})
    # how much of each person's archetype mix is just their position on the first two principal axes?
    pca = __import__('sklearn.decomposition', fromlist=['PCA']).PCA().fit(X)
    pc = pca.transform(X)[:, :2]
    A, _, _ = x1._best_archetypes(X, 3)
    r2 = []
    for j in range(3):
        m = sm.OLS(A[:, j], sm.add_constant(pc)).fit()
        r2.append(r(m.rsquared, 3))
    out['weightsFromPC12'] = r2
    print('archetype weights explained by PC1+PC2 (R2):', r2)
    # is there a gap anywhere along the reliance axis? (dip test needs a package -- use the bimodality
    # coefficient, > .555 suggests more than one mode)
    p1 = pc[:, 0]
    g, k = stats.skew(p1), stats.kurtosis(p1)
    n = len(p1)
    bc = (g ** 2 + 1) / (k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    out['bimodalityPC1'] = r(bc, 3)
    print('bimodality coefficient of PC1 = %.3f (> .555 hints at two modes)' % bc)
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 3 · deep queues, again
# ════════════════════════════════════════════════════════════════════════════════════════════

QBINS = [(0, 0, '0'), (1, 1, '1'), (2, 2, '2'), (3, 3, '3'), (4, 4, '4'), (5, 5, '5'), (6, 99, '6+')]
THIRDS = [(0, 160, 'first third (0–2:40)'), (160, 320, 'middle third'), (320, 481, 'last third (5:20–8:00)')]


def _qbin(q):
    for a, b_, lab in QBINS:
        if a <= q <= b_:
            return lab
    return None


def queue_view(D, y, name):
    D = D.copy()
    D['q'] = D.st_queued
    D['qb'] = D.q.map(_qbin)
    D = add_expected(D, y)
    D['pm'] = D.groupby('pid')[y].transform('mean')
    D['dev'] = D[y] - D.pm
    D['third'] = pd.cut(D.t, [a for a, _, _ in THIRDS] + [481], labels=[l for _, _, l in THIRDS], right=False)
    allrate = D[y].mean()
    bins = []
    for _, _, lab in QBINS:
        g = D[D.qb == lab]
        if not len(g):
            continue
        se = np.sqrt(max(g[y].mean() * (1 - g[y].mean()), 1e-9) / len(g))
        bins.append(dict(label=lab, n=int(len(g)), people=int(g.pid.nunique()), rate=r(g[y].mean()),
                         lo=r(max(0, g[y].mean() - 1.96 * se)), hi=r(min(1, g[y].mean() + 1.96 * se)),
                         dev=r(g.dev.mean()), expected=r(g.exp.mean()), adjusted=r(allrate + g.res.mean()),
                         ndrones=r(g.ndrones.mean(), 2), ntasks=r(g.ntasks.mean(), 2),
                         three=r((g.ncolours == 3).mean()), minute=r(g.t.mean() / 60, 2),
                         early=r(g.early.mean()) if 'early' in g else None,
                         secs=r(g.secs.median(), 1),
                         qtasks=r(g.q_tasks.mean(), 1) if 'q_tasks' in g else None,
                         pickPos=r(g.pickPos.mean(), 2) if 'pickPos' in g else None,
                         pickOldest=r((g.pickPos == 1).mean()) if 'pickPos' in g else None,
                         pickVisible=r((g.pickPos <= VISIBLE).mean()) if 'pickPos' in g else None))
    # by third of the session
    thirds = []
    for _, _, lab in THIRDS:
        g3 = D[D.third == lab]
        thirds.append(dict(label=lab, n=int(len(g3)), meanQ=r(g3.q.mean(), 2),
                           bins=[dict(label=bl, rate=r(g3[g3.qb == bl][y].mean()), n=int((g3.qb == bl).sum()))
                                 for _, _, bl in QBINS]))
    # models: within-person (person-mean centred) linear, hinge at what is visible, and controls
    D['q_pm'] = D.groupby('pid').q.transform('mean')
    D['q_w'] = D.q - D.q_pm
    D['qlo'] = D.q.clip(upper=VISIBLE)
    D['qhi'] = (D.q - VISIBLE).clip(lower=0)
    D['qlo_w'] = D.qlo - D.groupby('pid').qlo.transform('mean')
    D['qhi_w'] = D.qhi - D.groupby('pid').qhi.transform('mean')
    ctrl = 'ndrones + ntasks + ncolours + emin + C(game)'
    models = {}
    specs = [('linear, no controls', f'{y} ~ q_w + q_pm'),
             ('linear + time', f'{y} ~ q_w + q_pm + emin + C(game)'),
             ('linear + time + this card', f'{y} ~ q_w + q_pm + {ctrl}'),
             ('hinge at what is visible', f'{y} ~ qlo_w + qhi_w + q_pm + {ctrl}')]
    if 'q_tasks' in D:
        D['qt_w'] = D.q_tasks - D.groupby('pid').q_tasks.transform('mean')
        D['qt_pm'] = D.groupby('pid').q_tasks.transform('mean')
        specs.append(('tasks waiting, not missions', f'{y} ~ qt_w + qt_pm + {ctrl}'))
    for lab, f in specs:
        m = gee(f, D)
        terms = [t for t in ('q_w', 'qlo_w', 'qhi_w', 'qt_w') if t in m.params.index]
        models[lab] = {t: orow(m, t) for t in terms}
    # direct standardisation over time: each queue bin's rate if it had the whole sample's spread of thirds
    wts = D.third.value_counts(normalize=True)
    std = []
    for _, _, bl in QBINS:
        v, wsum = 0.0, 0.0
        for th, wt in wts.items():
            g = D[(D.qb == bl) & (D.third == th)]
            if len(g) >= 3:
                v += wt * g[y].mean()
                wsum += wt
        std.append(dict(label=bl, rate=r(v / wsum) if wsum else None, cover=r(wsum)))
    # people who met both a short (<= visible) and a long (> visible) queue: their own two rates
    D['long'] = (D.q > VISIBLE).astype(int)
    pp = D.groupby(['pid', 'long'])[y].mean().unstack().dropna()
    diff = pp[1] - pp[0]
    wil = stats.wilcoxon(diff) if (diff != 0).sum() > 5 else None
    persons = dict(n=int(len(diff)), higher=int((diff > 0).sum()), lower=int((diff < 0).sum()),
                   same=int((diff == 0).sum()), meanDiff=r(diff.mean()), p=r(wil.pvalue, 4) if wil else None,
                   points=[dict(pid=p_, short=r(a), long=r(b_)) for p_, (a, b_) in pp[[0, 1]].iterrows()])
    # residual (mission/time/person adjusted) rate, short vs long queue
    mres = gee('res ~ long', D, binomial=False)
    out = dict(name=name, n=int(len(D)), people=int(D.pid.nunique()), overall=r(allrate), bins=bins, thirds=thirds,
               standardised=std, models=models, persons=persons, residualLong=orow(mres, 'long', binomial=False),
               qByThird=[dict(label=l, meanQ=r(D[D.third == l].q.mean(), 2)) for _, _, l in THIRDS],
               corrQminute=r(stats.spearmanr(D.q, D.t)[0]))
    print('%s: n %d; rate by queue:' % (name, len(D)), [(b_['label'], b_['rate'], b_['n'], b_['adjusted']) for b_ in bins])
    for lab, mm in models.items():
        print('   %-32s' % lab, {k: (v['est'], v['p']) for k, v in mm.items()})
    print('   standardised over thirds:', [(x['label'], x['rate']) for x in std])
    print('   person short vs long: higher %d lower %d same %d, mean diff %s, p %s'
          % (persons['higher'], persons['lower'], persons['same'], persons['meanDiff'], persons['p']))
    print('   residual long-vs-short %s; queue~minute rho %s' % (out['residualLong'], out['corrQminute']))
    return out


def deep_queue(S, T, agree):
    hdr('3 · Deep queues: finer bins, visibility, time, complexity')
    s = queue_view(S[S.residual == 0] if 'residual' in S else S, 'took', 'strategic')
    s['rebuildAgree'] = r(agree)
    t = queue_view(T, 'consulted', 'tactical')
    # what gets picked when the queue is long: smaller missions? the oldest? one in view?
    D = S.copy()
    D['long'] = (D.st_queued > VISIBLE).astype(int)
    pick = []
    for lab, g in D.groupby('long'):
        pick.append(dict(k='more than %d waiting' % VISIBLE if lab else '%d or fewer waiting' % VISIBLE,
                         n=int(len(g)), ndrones=r(g.ndrones.mean(), 2), ntasks=r(g.ntasks.mean(), 2),
                         oldest=r((g.pickPos == 1).mean()), visible=r((g.pickPos <= VISIBLE).mean()),
                         early=r(g.early.mean()), secs=r(g.secs.median(), 1), took=r(g.took.mean())))
    # is the chosen mission smaller than what else was waiting? (mean size of the others)
    D['qavg'] = np.where(D.st_queued > 0, D.q_drones / D.st_queued.clip(lower=1), np.nan)
    sm_ = D[D.st_queued > 0]
    smaller = dict(n=int(len(sm_)), pickedSmaller=r((sm_.ndrones < sm_.qavg).mean()),
                   pickedLarger=r((sm_.ndrones > sm_.qavg).mean()),
                   byLong=[dict(long=int(k), smaller=r((g.ndrones < g.qavg).mean()), n=int(len(g)))
                           for k, g in sm_.groupby('long')])
    print('   picks:', pick)
    print('   picked a smaller-than-average waiting mission:', smaller)
    # does manual-before-the-cards rise with depth?
    m_early = gee('early ~ q_w + q_pm + ndrones + ncolours + emin + C(game)',
                  D.assign(q=D.st_queued, q_pm=D.groupby('pid').st_queued.transform('mean'),
                           q_w=D.st_queued - D.groupby('pid').st_queued.transform('mean')))
    m_secs = gee('lsecs ~ q_w + q_pm + ndrones + ncolours + emin + C(game)',
                 D.assign(q_pm=D.groupby('pid').st_queued.transform('mean'),
                          q_w=D.st_queued - D.groupby('pid').st_queued.transform('mean')), binomial=False)
    s['pick'], s['smaller'] = pick, smaller
    s['earlyModel'] = orow(m_early, 'q_w')
    s['secsModel'] = orow(m_secs, 'q_w', binomial=False)
    s['secsModel']['pctPerMission'] = r(100 * (np.exp(m_secs.params['q_w']) - 1), 2)
    print('   early-manual per extra mission waiting (within person): OR %s p %s' % (s['earlyModel']['est'], s['earlyModel']['p']))
    print('   decision time per extra mission waiting: %+.1f%% p %s' % (s['secsModel']['pctPerMission'], s['secsModel']['p']))
    return dict(strategic=s, tactical=t, visible=VISIBLE)


# ════════════════════════════════════════════════════════════════════════════════════════════
# 4 + 5 · event studies on several anchors, with what is behind every dot
# ════════════════════════════════════════════════════════════════════════════════════════════

def _after(D, anchors):
    a = D.pid.map(lambda p: anchors.get(p))
    return np.array([np.nan if x is None else int(ru > x[0] or (ru == x[0] and t > x[1]))
                     for x, ru, t in zip(a, D.run, D.t)])


def event_study(D, y, anchors, lo=-8, hi=12, minn=5, placebo=True, rng=None, subset=None):
    """Decisions in study order (both sessions) lined up on each person's anchor. The position `rel`
    counts EVERY decision (1 = first after the anchor, 0 = last before); `subset` (a 0/1 column, e.g.
    three-type missions) then keeps only some of them for the rates -- the same construction as the
    theme-8 chart, so its dots can be explained one by one."""
    D = D[D.pid.isin(anchors)].sort_values(['pid', 'run', 't']).copy()
    D['seq'] = D.groupby('pid').cumcount()
    D['after'] = _after(D, anchors)
    fa = D[D.after == 1].groupby('pid').seq.min()
    D = D[D.pid.isin(fa.index)].copy()
    D['rel'] = D.seq - D.pid.map(fa) + 1             # 1 = first after the anchor, 0 = last before
    if subset:
        D = D[D[subset] == 1].copy()
    if not len(D):
        return None
    series = []
    for k, g in D[(D.rel >= lo) & (D.rel <= hi)].groupby('rel'):
        if len(g) < minn:
            continue
        series.append(dict(rel=int(k), n=int(len(g)), people=int(g.pid.nunique()), rate=r(g[y].mean()),
                           expected=r(g.exp.mean()), adjusted=r(D[y].mean() + g.res.mean()),
                           ndrones=r(g.ndrones.mean(), 2), ntasks=r(g.ntasks.mean(), 2),
                           three=r((g.ncolours == 3).mean()), queue=r(g.st_queued.mean(), 2),
                           minute=r(g.t.mean() / 60, 2), session2=r((g.run == 2).mean())))
    pp = D.groupby(['pid', 'after'])[y].mean().unstack()
    both = pp.dropna()
    diff = both[1] - both[0]
    stat = float(diff.mean()) if len(diff) else np.nan
    out = dict(people=int(D.pid.nunique()), peopleBoth=int(len(both)), nBefore=int((D.after == 0).sum()),
               nAfter=int((D.after == 1).sum()), before=r(D[D.after == 0][y].mean()), after=r(D[D.after == 1][y].mean()),
               expBefore=r(D[D.after == 0].exp.mean()), expAfter=r(D[D.after == 1].exp.mean()),
               higher=int((diff > 0).sum()), lower=int((diff < 0).sum()), same=int((diff == 0).sum()),
               personDiff=r(stat), series=series)
    try:
        m = gee(f'{y} ~ after + seq + C(game)', D)
        out['model'] = orow(m, 'after')
    except Exception:
        try:
            out['model'] = orow(gee(f'{y} ~ after + seq', D), 'after')
        except Exception:
            out['model'] = None
    # the residual (observed minus expected) is a bounded difference, so a plain least-squares fit with
    # person-clustered errors is used: an exchangeable Gaussian GEE on it failed to converge on the
    # smaller subsets and returned impossible estimates
    try:
        ma = smf.ols('res ~ after + seq', D).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(D.pid)[0]})
        out['modelAdj'] = orow(ma, 'after', binomial=False)
    except Exception:
        out['modelAdj'] = None
    if placebo and rng is not None and len(diff) >= 4:
        # random anchors: each person's anchor moved to a random point in their own decision sequence,
        # keeping at least one decision either side -- what "after minus before" looks like by chance,
        # practice trend included
        G = {p: g[y].to_numpy() for p, g in D.groupby('pid')}
        null = np.empty(N_PLACEBO)
        for i in range(N_PLACEBO):
            ds = []
            for p, v in G.items():
                if len(v) < 2:
                    continue
                c = rng.integers(1, len(v))
                ds.append(v[c:].mean() - v[:c].mean())
            null[i] = np.mean(ds)
        out['placebo'] = dict(mean=r(null.mean()), lo=r(np.percentile(null, 2.5)), hi=r(np.percentile(null, 97.5)),
                              p=r((1 + (np.abs(null - null.mean()) >= abs(stat - null.mean())).sum()) / (1 + N_PLACEBO), 4))
    return out


def anchors_from(eps, logs, S):
    P = pd.DataFrame([dict(pid=e['pid'], run=e['run'], at=pr['at'], result=pr['result'], blind=pr['blind'])
                      for e in eps for pr in e['presses']])
    P = P.sort_values(['pid', 'run', 'at'])
    ref = P[P.result.isin(['failed', 'partial'])].groupby('pid').head(1)
    bl = P[P.blind].groupby('pid').head(1)
    A = {}
    A['refusal'] = {p: (ru, t) for p, ru, t in zip(ref.pid, ref.run, ref['at'])}
    A['blind'] = {p: (ru, t) for p, ru, t in zip(bl.pid, bl.run, bl['at'])}
    for key, fld in (('failure', 'fail'), ('abandon', 'ab')):
        d = {}
        for (pid, run), L in sorted(logs.items()):
            if pid not in d and L[fld]:
                d[pid] = (run, min(L[fld]))
        A[key] = d
    od = S[S.odd == 1].sort_values(['pid', 'run', 't']).groupby('pid').head(1)
    A['odd'] = {p: (ru, t + 1e-3) for p, ru, t in zip(od.pid, od.run, od.t)}
    return A


ANCHOR_LABEL = {
    'odd': 'first illogical strategy card',
    'refusal': 'first “No workable plan” from Suggest',
    'blind': 'first WRONG “No workable plan” (a fix existed)',
    'failure': 'first drone failure on a task',
    'abandon': 'first mission abandoned',
}


def flaw_events(S, T, eps, logs):
    hdr('4+5 · Event studies on five anchors, with what is behind each dot')
    rng = np.random.default_rng(SEED + 5)
    A = anchors_from(eps, logs, S)
    # every strategic decision counts towards the position (residual missions included, as in the
    # theme-8 chart); the expected rate knows a decision was a residual
    Sx = add_expected(S.copy(), 'took', extra=('st_queued', 'residual'))
    Sx['three'] = (Sx.ncolours == 3).astype(int)
    Tx = add_expected(T.copy(), 'consulted', extra=('st_queued',))
    out = {}
    for k, anc in A.items():
        res = dict(label=ANCHOR_LABEL[k], nPeople=len(anc),
                   strategic=event_study(Sx, 'took', anc, rng=rng),
                   strategic3=event_study(Sx, 'took', anc, rng=rng, subset='three'),
                   tactical=event_study(Tx, 'consulted', anc, rng=rng))
        out[k] = res
        for o in ('strategic', 'strategic3', 'tactical'):
            e = res[o]
            if not e:
                continue
            print('%-8s %-10s people %2d  before %.2f -> after %.2f (expected %.2f -> %.2f)  OR %s p %s | adj %s p %s | person diff %s vs placebo %s, p %s | +%d -%d'
                  % (k, o, e['people'], e['before'], e['after'], e['expBefore'], e['expAfter'],
                     e['model'] and e['model']['est'], e['model'] and e['model']['p'],
                     e['modelAdj'] and e['modelAdj']['est'], e['modelAdj'] and e['modelAdj']['p'],
                     e['personDiff'], e.get('placebo', {}).get('mean'), e.get('placebo', {}).get('p'), e['higher'], e['lower']))
    # the existing theme-8 split: illogical card, three-type missions, by whether the person ever said so
    import extras as x1
    M = x1._qual_codes()
    said = set(M.index[M.C12 == 1]) if M is not None else set()
    said |= {p for p, v in x1.SPOKEN_STRAT.items() if v[2]}
    out['oddSplit'] = dict(
        said=event_study(Sx[Sx.pid.isin(said)], 'took', A['odd'], lo=-6, minn=4, rng=rng, subset='three'),
        notSaid=event_study(Sx[~Sx.pid.isin(said)], 'took', A['odd'], lo=-6, minn=4, rng=rng, subset='three'))
    out['oddSplit']['saidPeople'] = sorted(said)
    # first abandonment split by what preceded it: a Suggest refusal in the 20 s before (the assistant
    # said it could not) or not (the operator gave up on their own)
    pr = [(e['pid'], e['run'], p_['at']) for e in eps for p_ in e['presses'] if p_['result'] in ('failed', 'partial')]
    afterRef = {p for p, (ru, t) in A['abandon'].items()
                if any(pp == p and rr == ru and 0 <= t - at <= 20 for pp, rr, at in pr)}
    out['abandonSplit'] = dict(afterRefusalPeople=sorted(afterRef))
    for g, keep in (('afterRefusal', afterRef), ('own', set(A['abandon']) - afterRef)):
        anc = {p: v for p, v in A['abandon'].items() if p in keep}
        out['abandonSplit'][g] = dict(strategic=event_study(Sx, 'took', anc, rng=rng),
                                      strategic3=event_study(Sx, 'took', anc, rng=rng, subset='three'),
                                      tactical=event_study(Tx, 'consulted', anc, rng=rng))
        for o in ('strategic', 'strategic3', 'tactical'):
            e = out['abandonSplit'][g][o]
            if e:
                print('abandon/%-12s %-10s people %2d  %.2f -> %.2f (exp %.2f -> %.2f) adj %s p %s'
                      % (g, o, e['people'], e['before'], e['after'], e['expBefore'], e['expAfter'],
                         e['modelAdj'] and e['modelAdj']['est'], e['modelAdj'] and e['modelAdj']['p']))
    for g in ('said', 'notSaid'):
        e = out['oddSplit'][g]
        print('odd/%-7s dots:' % g, [(x['rel'], x['rate'], x['expected'], x['ndrones'], x['n']) for x in e['series']])
    print('refusal/tactical dots:', [(x['rel'], x['rate'], x['expected'], x['ndrones'], x['n']) for x in out['refusal']['tactical']['series']])
    # anchor timing overlap: are these different moments or the same one?
    ov = {}
    for a_, b_ in (('refusal', 'failure'), ('abandon', 'failure'), ('abandon', 'refusal'), ('blind', 'abandon')):
        common = set(A[a_]) & set(A[b_])
        gap = [(A[a_][p][0] - A[b_][p][0]) * 480 + A[a_][p][1] - A[b_][p][1] for p in common]
        ov[f'{a_}-{b_}'] = dict(n=len(common), medianGap=r(np.median(gap), 1) if gap else None)
    out['overlap'] = ov
    out['anchorPeople'] = {k: len(v) for k, v in A.items()}
    print('anchor overlap (seconds of play from second to first):', ov)
    return out


def blind_abandons(eps):
    """Every wrong refusal (Suggest said no plan; one existed using a drone busy on another task),
    with what happened next -- the cases that ended in abandoning a saveable mission listed in full."""
    hdr('5b · Wrong refusals that ended in abandonment')
    rows = []
    for e in eps:
        for pr in e['presses']:
            if not pr['blind']:
                continue
            rows.append(dict(pid=e['pid'], run=e['run'], mission=e['missionId'], category=e['category'],
                             opened=r(e['opened'], 1), press=r(pr['at'], 1), pressNo=pr['idx'],
                             next=pr['next'], outcome=e['outcome'], closed=r(e['closed'], 1),
                             secsToClose=r(e['closed'] - pr['at'], 1), timeLeft=r(480 - pr['at'], 0),
                             idleFix=bool(e['fixIdleLogged']), busyOnMission=pr['busyOnMission']))
    B = pd.DataFrame(rows)
    ab = B[B.outcome == 'abandoned']
    last = ab.sort_values('press').groupby(['pid', 'run', 'mission']).tail(1)
    print('wrong refusals %d (%d people); episodes containing one %d; of those abandoned %d (%d people)'
          % (len(B), B.pid.nunique(), B.groupby(['pid', 'run', 'mission']).ngroups,
             last.shape[0], last.pid.nunique()))
    print(last[['pid', 'run', 'mission', 'category', 'press', 'next', 'secsToClose', 'timeLeft']].to_string(index=False))
    rec = B[B.outcome == 'recovered'].groupby(['pid', 'run', 'mission']).tail(1)
    return dict(all=B.to_dict('records'), abandonedEpisodes=last.to_dict('records'),
                nPresses=int(len(B)), nPeople=int(B.pid.nunique()),
                nEpisodes=int(B.groupby(['pid', 'run', 'mission']).ngroups),
                nAbandoned=int(len(last)), nAbandonedPeople=int(last.pid.nunique()),
                nRecovered=int(len(rec)), medianSecsToAbandon=r(last.secsToClose.median(), 1),
                verified=dict(pid='P19', run=1, mission='M003', videoFile='Results/Narration/_clips/P19_s1_M003_blindspot_refusal.mp4',
                              note='Camera-2 failed; the Supply Drop needs 2 Lifters + 1 Camera or 1 Lifter + 1 Camera. '
                                   'Lifter-2 and Lifter-3 sat unassigned; the only Camera left, Camera-1, was executing '
                                   'Search & Service (done in ~45 s). Suggest answered "No workable plan with the drones '
                                   'left on this mission"; the operator abandoned about 3 s later. Chaining Camera-1 onto '
                                   'the Supply Drop after Search & Service would have saved it.'))


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # EXTRAS2_REUSE_ARCH=1 keeps the (slow, seeded) archetype nulls from the last run
    reuse = os.environ.get('EXTRAS2_REUSE_ARCH') == '1' and OUT.exists()
    prev = json.loads(OUT.read_text(encoding='utf-8')) if reuse else {}
    S, T, eps, logs, agree = load()
    res = dict(generated=pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
               personExtra=person_measures(S, T, logs),
               deepQueue2=deep_queue(S, T, agree),
               events=flaw_events(S, T, eps, logs),
               blindAbandons=blind_abandons(eps),
               archNull=prev['archNull'] if reuse and 'archNull' in prev else archetype_null())
    OUT.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)),
                   encoding='utf-8')
    print('\nwrote', OUT.relative_to(BASE))


if __name__ == '__main__':
    main()
