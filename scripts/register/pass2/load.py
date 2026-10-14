#!/usr/bin/env python3
"""Pass 2 · area `load` ("Workload and the queue").

Read-only over Results/. Writes docs/analysis/register/pass2/load.json and prints every number the
findings quote. Run from the repo root:

    python scripts/register/pass2/load.py

Cards carried: load-null, load-visible, load-backlog-practice, load-deep-queue, load-pick-small, q-C11.

What is computed (each block is a section of f-workload or f-triage):

A · QUEUE BINS, RAW vs ADJUSTED, with person-level bootstrap CIs (strategic: card taken; tactical:
    Suggest pressed). "Adjusted" = the overall rate + the mean of (observed − expected) in that bin,
    where "expected" comes from a model that knows the mission (drones, tasks, drone types), the minute
    of the session, the game, and the person's own rate on their OTHER decisions -- but not the queue
    (extras2.add_expected). The bootstrap resamples PEOPLE and re-fits that model every time.
B · ROBUSTNESS STRIP: the within-person odds ratio per extra waiting mission under every specification
    tried (no controls, + time, + mission, hinge at the visible limit, tasks waiting, exogenous
    arrivals, each game separately, heavy vs light games).
C · SAID vs DID. (1) the 9 people coded C11 ("hands over when overloaded") vs the rest: each person's
    own queue slope on the adjusted scale; (2) the session-level version of the claim (more reliance in
    the busier game); (3) in-play spoken overload moments, from the narration transcripts (30 people,
    60 sessions), vs a null of random utterances in the same sessions.
D · BACKLOG vs PRACTICE (tactical Suggest vs strategic backlog at the first planner action, with and
    without minute of session).
E · DEEP QUEUES (4+ waiting): within-person vs between-person.
F · TRIAGE: which mission gets picked (oldest? top 3 of the list? small vs what is waiting?), pace
    (decision time, decisions per minute, deciding before the cards load), all against chance or
    within person.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

BASE = Path(__file__).resolve().parents[3]
for p in ('scripts', 'scripts/analysis_round1', 'scripts/analysis_round2', 'scripts/analysis_combined'):
    sys.path.insert(0, str(BASE / p))
warnings.filterwarnings('ignore')

import extras2 as x2  # noqa: E402

OUT = BASE / 'docs' / 'analysis' / 'register' / 'pass2' / 'load.json'
NARR = BASE / 'Results' / 'Narration'
QUAL = BASE / 'docs' / 'analysis' / 'qual'
SEED = 20261012
B_BOOT = int(__import__('os').environ.get('LOAD_BOOT', 400))
N_NULL = 5000
VISIBLE = x2.VISIBLE          # 3 full queue cards at rest
QB = [(0, 0, '0'), (1, 1, '1'), (2, 2, '2'), (3, 3, '3'), (4, 4, '4'), (5, 5, '5'), (6, 99, '6+')]
r = x2.r
gee, orow = x2.gee, x2.orow


def hdr(s):
    print('\n' + '=' * 96 + '\n' + s + '\n' + '=' * 96)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def qbin(q, bins=QB):
    for a, b, lab in bins:
        if a <= q <= b:
            return lab
    return None


def centre(D, col):
    D[col + '_pm'] = D.groupby('pid')[col].transform('mean')
    D[col + '_w'] = D[col] - D[col + '_pm']
    return D


def boot_people(D, rng, B):
    """Yield B person-resampled copies of D (duplicated people get distinct ids)."""
    groups = {p: g for p, g in D.groupby('pid')}
    pids = np.array(list(groups))
    for _ in range(B):
        pick = rng.choice(pids, len(pids), replace=True)
        yield pd.concat([groups[p].assign(pid=f'{p}#{i}') for i, p in enumerate(pick)], ignore_index=True)


def pci(v):
    v = np.asarray([x for x in v if x is not None and np.isfinite(x)])
    return (r(np.percentile(v, 2.5)), r(np.percentile(v, 97.5))) if len(v) > 10 else (None, None)


# ════════════════════════════════════════════════════════════════════════════════════════════
# data
# ════════════════════════════════════════════════════════════════════════════════════════════

def load():
    S, T, eps, logs, agree = quiet(x2.load)
    S = S.copy()
    T = T.copy()
    # waiting set at each strategic decision (including the picked mission), from the raw log
    W = []
    for rr in S.itertuples():
        L = logs[(rr.pid, rr.run)]
        wait = sorted((a['t'], m, a['ndrones'], a['ntasks']) for m, a in L['arr'].items()
                      if a['t'] <= rr.t + 1e-6 and L['chosen'].get(m, 1e9) > rr.t - 1e-6)
        W.append(wait)
    S['waiting'] = W
    M = pd.read_csv(QUAL / 'codes_matrix.csv').set_index('pid')
    said = set(M.index[M.C11 == 1]) - x2.EXCLUDE
    return S, T, logs, said, M


def game_load(S, logs):
    """How heavy each game is: arrivals and drones demanded per session, and the mean queue met."""
    rows = []
    for (pid, run), L in logs.items():
        s = S[(S.pid == pid) & (S.run == run)]
        if not len(s):
            continue
        real = [a for m, a in L['arr'].items() if not m.endswith('-R')]
        rows.append(dict(pid=pid, run=run, game=s.game.iloc[0], arrivals=len(real),
                         drones=sum(a['ndrones'] for a in real), tasks=sum(a['ntasks'] for a in real),
                         meanQ=s.st_queued.mean()))
    G = pd.DataFrame(rows)
    out = []
    for g, d in G.groupby('game'):
        out.append(dict(game=g, sessions=int(len(d)), arrivals=r(d.arrivals.mean(), 1),
                        drones=r(d.drones.mean(), 1), tasks=r(d.tasks.mean(), 1), meanQ=r(d.meanQ.mean(), 2)))
    print('games:', out)
    return out, {o['game']: o['drones'] for o in out}


# ════════════════════════════════════════════════════════════════════════════════════════════
# A + B · the null, raw vs adjusted, robustness strip
# ════════════════════════════════════════════════════════════════════════════════════════════

def bin_table(D, y, qcol):
    D = D.copy()
    D['qb'] = D[qcol].map(qbin)
    E = x2.add_expected(D, y)
    allrate = E[y].mean()
    out = {}
    for _, _, lab in QB:
        g = E[E.qb == lab]
        if len(g):
            out[lab] = dict(n=int(len(g)), people=int(g.pid.nunique()), raw=g[y].mean(),
                            exp=g.exp.mean(), adj=allrate + g.res.mean(), ndrones=g.ndrones.mean(),
                            minute=g.t.mean() / 60, person=(1 / (1 + np.exp(-g.base))).mean(),
                            stratGame=g.game.str.startswith('strategic').mean(),
                            three=(g.ncolours == 3).mean())
    return out, E


def null_bins(D, y, qcol, name, rng):
    base, E = bin_table(D, y, qcol)
    boots = {lab: dict(raw=[], adj=[], exp=[]) for lab in base}
    for Db in boot_people(D, rng, B_BOOT):
        try:
            bt, _ = bin_table(Db, y, qcol)
        except Exception:
            continue
        for lab in base:
            if lab in bt:
                for k in ('raw', 'adj', 'exp'):
                    boots[lab][k].append(bt[lab][k])
    rows = []
    for _, _, lab in QB:
        if lab not in base:
            continue
        b = base[lab]
        rl, rh = pci(boots[lab]['raw'])
        al, ah = pci(boots[lab]['adj'])
        rows.append(dict(label=lab, n=b['n'], people=b['people'], raw=r(b['raw']), rawLo=rl, rawHi=rh,
                         exp=r(b['exp']), adj=r(b['adj']), adjLo=al, adjHi=ah, ndrones=r(b['ndrones'], 2),
                         minute=r(b['minute'], 2), person=r(b['person']), stratGame=r(b['stratGame']),
                         three=r(b['three'])))
    print('%s bins (label, n, raw [ci], expected, adjusted [ci]):' % name)
    for x in rows:
        print('   %-3s n %3d  raw %.2f [%s, %s]  exp %.2f  adj %.2f [%s, %s]  drones %.1f  min %.1f  person %.2f  stratGame %.2f  3type %.2f'
              % (x['label'], x['n'], x['raw'], x['rawLo'], x['rawHi'], x['exp'], x['adj'], x['adjLo'], x['adjHi'],
                 x['ndrones'], x['minute'], x['person'], x['stratGame'], x['three']))
    return rows, E


def robustness(D, y, qcol, name, heavy, extra_ctrl=''):
    D = D.copy()
    D['q'] = D[qcol]
    D = centre(D, 'q')
    D['qlo'] = D.q.clip(upper=VISIBLE)
    D['qhi'] = (D.q - VISIBLE).clip(lower=0)
    D = centre(D, 'qlo')
    D = centre(D, 'qhi')
    D = centre(D, 'q_tasks') if 'q_tasks' in D else D
    D = centre(D, 'arrivals60') if 'arrivals60' in D else D
    ctrl = 'ndrones + ntasks + ncolours + emin + C(game)' + extra_ctrl
    specs = [
        ('No controls', f'{y} ~ q_w + q_pm', 'q_w', D),
        ('+ minute and game', f'{y} ~ q_w + q_pm + emin + C(game)', 'q_w', D),
        ('+ mission size and types (main)', f'{y} ~ q_w + q_pm + {ctrl}', 'q_w', D),
        ('Hinge: 0–3 waiting (visible)', f'{y} ~ qlo_w + qhi_w + q_pm + {ctrl}', 'qlo_w', D),
        ('Hinge: beyond 3 (off the list)', f'{y} ~ qlo_w + qhi_w + q_pm + {ctrl}', 'qhi_w', D),
    ]
    if 'q_tasks_w' in D:
        specs.append(('Tasks waiting (per 3 tasks)', f'{y} ~ I(q_tasks_w/3) + q_tasks_pm + {ctrl}', 'I(q_tasks_w / 3)', D))
    if 'arrivals60_w' in D:
        specs.append(('Arrivals in last 60 s (fixed by game)', f'{y} ~ arrivals60_w + arrivals60_pm + {ctrl}',
                      'arrivals60_w', D))
    ctrl_ng = 'ndrones + ntasks + ncolours + emin' + extra_ctrl
    for g in sorted(D.game.unique()):
        Dg = centre(D[D.game == g].copy(), 'q')
        specs.append((f'Game {g} only', f'{y} ~ q_w + q_pm + {ctrl_ng}', 'q_w', Dg))
    for lab, keep in (('Two heavier games only', D.game.isin(heavy)), ('Two lighter games only', ~D.game.isin(heavy))):
        Dg = centre(D[keep].copy(), 'q')
        specs.append((lab, f'{y} ~ q_w + q_pm + {ctrl}', 'q_w', Dg))
    rows = []
    for lab, f, term, d in specs:
        try:
            m = gee(f, d)
            o = orow(m, term)
        except Exception as e:  # noqa: BLE001
            print('   spec failed', lab, e)
            continue
        rows.append(dict(label=lab, n=int(len(d)), people=int(d.pid.nunique()), **o))
    print('%s robustness (OR per extra waiting mission, within person):' % name)
    for x in rows:
        print('   %-40s n %3d  OR %.2f [%.2f, %.2f] p %.3f' % (x['label'], x['n'], x['est'], x['lo'], x['hi'], x['p']))
    return rows


def detectable(D, y, row):
    """What the upper CI would mean in percentage points: 0 vs 5 waiting at the overall rate."""
    p0 = D[y].mean()
    lo0 = np.log(p0 / (1 - p0))
    out = {}
    for k in ('lo', 'hi', 'est'):
        v = lo0 + 5 * np.log(row[k])
        out[k] = r(1 / (1 + np.exp(-v)))
    out['base'] = r(p0)
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# C · said vs did
# ════════════════════════════════════════════════════════════════════════════════════════════

def person_slopes(E, y, qcol, said):
    """Each person's own slope of (observed − expected) on queue depth, in percentage points per extra
    waiting mission. Least squares, one line per person; people need >= 6 decisions and some spread."""
    rows = []
    for p, g in E.groupby('pid'):
        if len(g) < 6 or g[qcol].nunique() < 3:
            continue
        b = np.polyfit(g[qcol].astype(float), g.res.astype(float), 1)[0]
        braw = np.polyfit(g[qcol].astype(float), g[y].astype(float), 1)[0]
        rows.append(dict(pid=p, said=int(p in said), n=int(len(g)), slope=r(b, 4), slopeRaw=r(braw, 4),
                         meanQ=r(g[qcol].mean(), 2), maxQ=int(g[qcol].max())))
    P = pd.DataFrame(rows)
    out = dict(points=rows)
    for k, lab in ((1, 'said'), (0, 'notSaid')):
        v = P[P.said == k].slope
        out[lab] = dict(n=int(len(v)), mean=r(v.mean(), 4), median=r(v.median(), 4),
                        lo=r(v.mean() - 1.96 * v.std(ddof=1) / np.sqrt(len(v)), 4) if len(v) > 1 else None,
                        hi=r(v.mean() + 1.96 * v.std(ddof=1) / np.sqrt(len(v)), 4) if len(v) > 1 else None,
                        positive=int((v > 0).sum()))
    mw = stats.mannwhitneyu(P[P.said == 1].slope, P[P.said == 0].slope)
    w1 = stats.wilcoxon(P[P.said == 1].slope) if (P.said == 1).sum() > 4 else None
    out['pDiff'] = r(mw.pvalue, 4)
    out['pSaidVsZero'] = r(w1.pvalue, 4) if w1 else None
    return out


def said_interaction(D, y, qcol, said):
    D = D.copy()
    D['q'] = D[qcol]
    D = centre(D, 'q')
    D['said'] = D.pid.isin(said).astype(int)
    m = gee(f'{y} ~ q_w * said + q_pm + ndrones + ntasks + ncolours + emin + C(game)', D)
    # the queue OR within each group
    D1 = D[D.said == 1]
    D0 = D[D.said == 0]
    o1 = orow(gee(f'{y} ~ q_w + q_pm + ndrones + ntasks + ncolours + emin + C(game)', D1), 'q_w')
    o0 = orow(gee(f'{y} ~ q_w + q_pm + ndrones + ntasks + ncolours + emin + C(game)', D0), 'q_w')
    return dict(interaction=orow(m, 'q_w:said'), saidOR=o1, notSaidOR=o0,
                nSaid=int(len(D1)), nNot=int(len(D0)), peopleSaid=int(D1.pid.nunique()))


def busier_session(E, y, said, gdrones):
    """Session-level version of the claim: reliance in the person's heavier game minus the lighter."""
    rows = []
    for p, g in E.groupby('pid'):
        runs = g.groupby('game').agg(raw=(y, 'mean'), res=('res', 'mean'), n=(y, 'size'))
        if len(runs) != 2:
            continue
        runs['load'] = [gdrones[k] for k in runs.index]
        hv, lt = runs.load.idxmax(), runs.load.idxmin()
        if hv == lt:
            continue
        rows.append(dict(pid=p, said=int(p in said), heavy=hv, light=lt,
                         rawHeavy=r(runs.loc[hv, 'raw']), rawLight=r(runs.loc[lt, 'raw']),
                         adjDiff=r(runs.loc[hv, 'res'] - runs.loc[lt, 'res']),
                         rawDiff=r(runs.loc[hv, 'raw'] - runs.loc[lt, 'raw'])))
    P = pd.DataFrame(rows)
    out = dict(points=rows)
    for k, lab in ((1, 'said'), (0, 'notSaid'), (None, 'all')):
        d = P if k is None else P[P.said == k]
        o = {}
        for col in ('rawDiff', 'adjDiff'):
            v = d[col].astype(float)
            se = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan
            o[col] = dict(mean=r(v.mean()), lo=r(v.mean() - 1.96 * se), hi=r(v.mean() + 1.96 * se),
                          higher=int((v > 0).sum()), n=int(len(v)),
                          p=r(stats.wilcoxon(v).pvalue, 4) if len(v) > 5 and (v != 0).sum() > 5 else None)
        out[lab] = o
    return out


STRICT = None


def narration_moments(S_E, T_E, logs, said, rng):
    """In-play spoken overload (STRICT phrase list from round 2, fixed before behaviour was looked at),
    over every narrated session now available (segments.json gives each session's video window).
    For each moment: the strategic queue at that second, and the adjusted card/Suggest residuals of
    decisions within ±60 s. Null: the same number of utterances drawn at random from the same session."""
    import wB_narration as wn
    rx = re.compile('|'.join(wn.STRICT))
    sessions = []
    for d in sorted(NARR.glob('P*_s1')):
        pid = d.name[:-3]
        if pid in x2.EXCLUDE or not (d / 'segments.json').exists():
            continue
        sj = json.loads((d / 'segments.json').read_text(encoding='utf-8'))
        tr = json.loads((d / 'transcript.raw.json').read_text(encoding='utf-8'))['segments']
        segs = [x for x in sj['segments'] if x['kind'] == 'session']
        for run, sg in enumerate(segs, start=1):
            if (pid, run) not in logs:
                continue
            us = []
            for u in tr:
                e = u['start'] - sg['videoStart']
                if 0 <= e < 480:
                    us.append(dict(e=e, text=(u.get('text') or '').lower()))
            sessions.append(dict(pid=pid, run=run, utts=us))

    def q_at(L, t):
        return sum(1 for m, a in L['arr'].items() if a['t'] <= t and L['chosen'].get(m, 1e9) > t)

    def near(D, tcol, pid, run, t, scale=1.0):
        g = D[(D.pid == pid) & (D.run == run)]
        g = g[(g[tcol] / scale >= t - 60) & (g[tcol] / scale <= t + 60)]
        return g.res.mean() if len(g) else np.nan

    rows, nullpool = [], []
    for s in sessions:
        L = logs[(s['pid'], s['run'])]
        hits = [u for u in s['utts'] if rx.search(u['text'])]
        kept = []
        for h in hits:
            if not kept or h['e'] - kept[-1]['e'] >= 20:
                kept.append(h)
        # every utterance's measures (the null pool for this session)
        pool = [(u['e'], q_at(L, u['e'])) for u in s['utts']]
        sess_q = np.mean([q for _, q in pool]) if pool else np.nan
        nullpool.append(dict(pid=s['pid'], run=s['run'], k=len(kept), qs=np.array([q for _, q in pool]),
                             es=np.array([e for e, _ in pool])))
        for h in kept:
            rows.append(dict(pid=s['pid'], run=s['run'], e=r(h['e'], 1), q=q_at(L, h['e']), sessQ=r(sess_q, 2),
                             took=near(S_E, 't', s['pid'], s['run'], h['e']),
                             consulted=near(T_E, 'first_ts', s['pid'], s['run'], h['e'], scale=1000.0)))
    Mo = pd.DataFrame(rows)
    obsQ = Mo.q.mean() if len(Mo) else np.nan
    # null: same count per session, random utterances
    act = [x for x in nullpool if x['k'] > 0 and len(x['qs'])]
    nullQ = np.empty(N_NULL)
    for i in range(N_NULL):
        v = []
        for x in act:
            v += list(rng.choice(x['qs'], x['k'], replace=True))
        nullQ[i] = np.mean(v)
    # the mean residual of decisions within ±60 s of a random utterance, same per-session counts
    pools = {}
    for x in act:
        es = x['es']
        tk = [near(S_E, 't', x['pid'], x['run'], e) for e in es]
        cs = [near(T_E, 'first_ts', x['pid'], x['run'], e, scale=1000.0) for e in es]
        pools[(x['pid'], x['run'])] = (np.array(tk), np.array(cs), x['k'])
    nullT, nullC = np.empty(N_NULL), np.empty(N_NULL)
    for i in range(N_NULL):
        tv, cv = [], []
        for (tk, cs, k) in pools.values():
            idx = rng.integers(0, len(tk), k)
            tv += list(tk[idx])
            cv += list(cs[idx])
        nullT[i] = np.nanmean(tv)
        nullC[i] = np.nanmean(cv)

    def summ(obs, null):
        return dict(obs=r(obs), mean=r(null.mean()), lo=r(np.percentile(null, 2.5)), hi=r(np.percentile(null, 97.5)),
                    p=r((1 + (np.abs(null - null.mean()) >= abs(obs - null.mean())).sum()) / (1 + len(null)), 4),
                    hist=np.histogram(null, bins=30)[0].tolist(),
                    edges=[r(e) for e in np.histogram(null, bins=30)[1]])
    out = dict(sessions=len(sessions), people=len({s['pid'] for s in sessions}),
               utterances=int(sum(len(s['utts']) for s in sessions)),
               moments=int(len(Mo)), momentPeople=int(Mo.pid.nunique()) if len(Mo) else 0,
               momentsBySaid={'said': int(Mo.pid.isin(said).sum()), 'notSaid': int((~Mo.pid.isin(said)).sum())} if len(Mo) else {},
               saidNarrated=int(len({s['pid'] for s in sessions} & said)),
               saidWithMoment=int(len(set(Mo.pid) & said)) if len(Mo) else 0,
               queue=summ(obsQ, nullQ),
               took=summ(Mo.took.mean(), nullT), consulted=summ(Mo.consulted.mean(), nullC),
               points=[dict(pid=x.pid, said=int(x.pid in said), run=int(x.run), e=x.e, q=int(x.q), sessQ=x.sessQ)
                       for x in Mo.itertuples()])
    print('narration: %d sessions, %d people, %d utterances; overload moments %d from %d people'
          % (out['sessions'], out['people'], out['utterances'], out['moments'], out['momentPeople']))
    print('   queue at overload moments %.2f vs random utterances %.2f [%.2f, %.2f] p %.3f'
          % (obsQ, nullQ.mean(), out['queue']['lo'], out['queue']['hi'], out['queue']['p']))
    print('   card residual ±60 s %s vs null %s p %s; Suggest residual %s vs null %s p %s'
          % (out['took']['obs'], out['took']['mean'], out['took']['p'], out['consulted']['obs'],
             out['consulted']['mean'], out['consulted']['p']))
    print('   said-coded people narrated %d, with a moment %d' % (out['saidNarrated'], out['saidWithMoment']))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# D · backlog vs practice (tactical)
# ════════════════════════════════════════════════════════════════════════════════════════════

def backlog_practice(T, rng):
    D = T.dropna(subset=['fa_queued', 'consulted', 'lplan', 'emin']).copy()
    D['b'] = D.fa_queued.clip(upper=99)
    D = centre(D, 'b')
    D = centre(D, 'emin')
    base = 'consulted ~ b_w + b_pm + lplan + ncolours + C(game)'
    m0 = gee(base, D)
    m1 = gee(base + ' + emin', D)
    m2 = gee('consulted ~ emin_w + emin_pm + lplan + ncolours + C(game)', D)
    mb = gee('b ~ emin_w + emin_pm + C(game)', D, binomial=False)
    res = dict(n=int(len(D)), people=int(D.pid.nunique()),
               without=orow(m0, 'b_w'), withMinute=orow(m1, 'b_w'),
               minuteOnSuggest=orow(m2, 'emin_w'), minuteOnBacklog=orow(mb, 'emin_w', binomial=False),
               rhoBacklogMinute=r(stats.spearmanr(D.b, D.emin)[0]))
    # bins: raw and minute-adjusted (expected from minute + plan + game + person, no backlog)
    BB = [(0, 0, '0'), (1, 1, '1'), (2, 2, '2'), (3, 3, '3'), (4, 99, '4+')]
    D['bb'] = D.b.map(lambda v: qbin(v, BB))

    def tab(Dx):
        Dx = Dx.copy()
        g = Dx.groupby('pid').consulted
        s, n = g.transform('sum'), g.transform('size')
        bs = (s - Dx.consulted + 1) / (n - 1 + 2)
        Dx['base'] = np.log(bs / (1 - bs))
        mm = smf.glm('consulted ~ emin + lplan + ncolours + C(game) + base', Dx, family=sm.families.Binomial()).fit()
        Dx['res'] = Dx.consulted - mm.predict(Dx)
        Dx['res2'] = Dx.consulted - smf.glm('consulted ~ lplan + ncolours + C(game) + base', Dx,
                                            family=sm.families.Binomial()).fit().predict(Dx)
        allr = Dx.consulted.mean()
        return {lab: dict(raw=g_.consulted.mean(), adj=allr + g_.res.mean(), adjNoMin=allr + g_.res2.mean(),
                          n=len(g_), people=g_.pid.nunique(), minute=g_.emin.mean())
                for lab, g_ in Dx.groupby('bb')}
    base_t = tab(D)
    boots = {lab: dict(raw=[], adj=[], adjNoMin=[]) for lab in base_t}
    for Db in boot_people(D, rng, B_BOOT):
        try:
            bt = tab(Db)
        except Exception:
            continue
        for lab in base_t:
            if lab in bt:
                for k in boots[lab]:
                    boots[lab][k].append(bt[lab][k])
    bins = []
    for _, _, lab in BB:
        if lab not in base_t:
            continue
        b = base_t[lab]
        row = dict(label=lab, n=int(b['n']), people=int(b['people']), minute=r(b['minute'], 2))
        for k in ('raw', 'adj', 'adjNoMin'):
            lo, hi = pci(boots[lab][k])
            row[k], row[k + 'Lo'], row[k + 'Hi'] = r(b[k]), lo, hi
        bins.append(row)
    res['bins'] = bins
    # both over the session, by minute
    D['min'] = (D.emin).clip(upper=7.99).astype(int)
    res['byMinute'] = [dict(minute=int(k), n=int(len(g)), backlog=r(g.b.mean(), 2), suggest=r(g.consulted.mean()))
                       for k, g in D.groupby('min')]
    print('backlog-practice: n %d; OR without minute %s p %s -> with minute %s p %s' %
          (res['n'], res['without']['est'], res['without']['p'], res['withMinute']['est'], res['withMinute']['p']))
    print('   minute -> Suggest OR/min %s p %s; minute -> backlog %+.2f/min p %s; rho %s'
          % (res['minuteOnSuggest']['est'], res['minuteOnSuggest']['p'], res['minuteOnBacklog']['est'],
             res['minuteOnBacklog']['p'], res['rhoBacklogMinute']))
    for x in bins:
        print('   backlog %-3s n %3d  raw %.2f [%s,%s]  adj(no minute) %.2f  adj(+minute) %.2f [%s,%s]  minute %.1f'
              % (x['label'], x['n'], x['raw'], x['rawLo'], x['rawHi'], x['adjNoMin'], x['adj'], x['adjLo'], x['adjHi'], x['minute']))
    print('   by minute:', [(x['minute'], x['backlog'], x['suggest']) for x in res['byMinute']])
    return res


# ════════════════════════════════════════════════════════════════════════════════════════════
# E · deep queues: within vs between
# ════════════════════════════════════════════════════════════════════════════════════════════

def deep(E, y, name):
    E = E.copy()
    E['deep'] = (E.st_queued >= VISIBLE + 1).astype(int)
    E = centre(E, 'deep')
    ctrl = 'ndrones + ntasks + ncolours + emin + C(game)'
    m = gee(f'{y} ~ deep_w + deep_pm + {ctrl}', E)
    P = E.groupby('pid').agg(share=('deep', 'mean'), rate=(y, 'mean'), n=(y, 'size'),
                             adj=('res', 'mean'), ndrones=('ndrones', 'mean'))
    rho = stats.spearmanr(P.share, P.rate)
    pp = E.groupby(['pid', 'deep']).agg(raw=(y, 'mean'), res=('res', 'mean')).unstack().dropna()
    within = [dict(pid=p, shallow=r(row[('raw', 0)]), deep=r(row[('raw', 1)]),
                   adjDiff=r(row[('res', 1)] - row[('res', 0)])) for p, row in pp.iterrows()]
    dd = np.array([w['adjDiff'] for w in within])
    out = dict(name=name, n=int(len(E)), share=r(E.deep.mean()), peopleDeep=int(E[E.deep == 1].pid.nunique()),
               people=int(E.pid.nunique()), within=orow(m, 'deep_w'), between=orow(m, 'deep_pm'),
               rho=r(rho.correlation), rhoP=r(rho.pvalue, 4),
               rhoSize=r(stats.spearmanr(P.share, P.ndrones).correlation),
               persons=[dict(pid=p, share=r(row.share), rate=r(row.rate), n=int(row.n)) for p, row in P.iterrows()],
               paired=within, pairedN=len(within), pairedHigher=int((dd > 0).sum()), pairedLower=int((dd < 0).sum()),
               pairedMean=r(dd.mean()), pairedP=r(stats.wilcoxon(dd).pvalue, 4) if len(dd) > 5 else None)
    print('%s deep (4+): share %.2f of decisions, %d/%d people; within OR %s [%s,%s] p %s; between OR %s p %s; '
          'person rho(share, rate) %s p %s; rho(share, mission size) %s; paired adj diff %s (+%d -%d) p %s'
          % (name, out['share'], out['peopleDeep'], out['people'], out['within']['est'], out['within']['lo'],
             out['within']['hi'], out['within']['p'], out['between']['est'], out['between']['p'], out['rho'],
             out['rhoP'], out['rhoSize'], out['pairedMean'], out['pairedHigher'], out['pairedLower'], out['pairedP']))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# F · triage
# ════════════════════════════════════════════════════════════════════════════════════════════

TB = [(1, 1, '1'), (2, 2, '2'), (3, 3, '3'), (4, 4, '4'), (5, 5, '5'), (6, 99, '6+')]


def triage(S, logs, rng):
    D = S.copy()
    rows = []
    for rr in D.itertuples():
        w = rr.waiting
        k = len(w)
        ids = [m for _, m, _, _ in w]
        if rr.missionId not in ids or k < 2:
            rows.append(dict(sizeRank=np.nan, oldest=np.nan, top3=np.nan, chOld=np.nan, chTop3=np.nan,
                             smallest=np.nan, chSmall=np.nan, waitMean=np.nan, nwait=k))
            continue
        me = ids.index(rr.missionId)
        nd = np.array([x[2] for x in w], float)
        others = np.delete(nd, me)
        rank = ((others < nd[me]).sum() + 0.5 * (others == nd[me]).sum()) / len(others)
        nsmall = (nd == nd.min()).sum()
        rows.append(dict(sizeRank=rank, oldest=int(me == 0), top3=int(me < VISIBLE), chOld=1 / k,
                         chTop3=min(VISIBLE, k) / k, smallest=int(nd[me] == nd.min()), chSmall=nsmall / k,
                         waitMean=others.mean(), nwait=k))
    D = pd.concat([D.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    D['q'] = D.st_queued
    P = D[D.nwait >= 2].copy()
    P['qb'] = P.q.map(lambda v: qbin(v, TB))

    def tab(Px):
        o = {}
        for lab, g in Px.groupby('qb'):
            o[lab] = dict(n=len(g), people=g.pid.nunique(), oldest=g.oldest.mean(), chOld=g.chOld.mean(),
                          top3=g.top3.mean(), chTop3=g.chTop3.mean(), rank=g.sizeRank.mean(),
                          smallest=g.smallest.mean(), chSmall=g.chSmall.mean(),
                          picked=g.ndrones.mean(), waiting=g.waitMean.mean())
        return o
    base = tab(P)
    keys = ('oldest', 'top3', 'rank', 'smallest', 'picked', 'waiting')
    boots = {lab: {k: [] for k in keys} for lab in base}
    for Pb in boot_people(P, rng, B_BOOT):
        bt = tab(Pb)
        for lab in base:
            if lab in bt:
                for k in keys:
                    boots[lab][k].append(bt[lab][k])
    bins = []
    for _, _, lab in TB:
        if lab not in base:
            continue
        b = base[lab]
        row = dict(label=lab, n=int(b['n']), people=int(b['people']), chOld=r(b['chOld']), chTop3=r(b['chTop3']),
                   chSmall=r(b['chSmall']))
        for k in keys:
            lo, hi = pci(boots[lab][k])
            row[k], row[k + 'Lo'], row[k + 'Hi'] = r(b[k], 3), lo, hi
        bins.append(row)
    print('triage bins (others waiting; picked oldest vs chance; top-3 vs chance; size rank (0 smallest); drones picked vs waiting):')
    for x in bins:
        print('   %-3s n %3d  oldest %.2f [%s,%s] (chance %.2f)  top3 %.2f (chance %.2f)  rank %.2f [%s,%s]  '
              'smallest %.2f (chance %.2f)  picked %.1f vs waiting %.1f'
              % (x['label'], x['n'], x['oldest'], x['oldestLo'], x['oldestHi'], x['chOld'], x['top3'], x['chTop3'],
                 x['rank'], x['rankLo'], x['rankHi'], x['smallest'], x['chSmall'], x['picked'], x['waiting']))
    # within-person models on the decisions with a choice to make (>= 1 other waiting)
    P = centre(P, 'q')
    P['exOld'] = P.oldest - P.chOld
    P['exTop3'] = P.top3 - P.chTop3
    P['exSmall'] = P.smallest - P.chSmall
    ctrl = 'emin + C(game)'
    models = {}
    for key, f, binom in (
            ('sizeRank', f'sizeRank ~ q_w + q_pm + {ctrl}', False),
            ('exOld', f'exOld ~ q_w + q_pm + {ctrl}', False),
            ('exTop3', f'exTop3 ~ q_w + q_pm + {ctrl}', False),
            ('exSmall', f'exSmall ~ q_w + q_pm + {ctrl}', False)):
        m = gee(f, P, binomial=binom)
        models[key] = orow(m, 'q_w', binomial=False)
    # sanity: same, excluding decisions on residual missions and excluding P01/P02
    P2 = centre(P[(P.residual == 0)].copy(), 'q')
    models['sizeRank_noResidual'] = orow(gee(f'sizeRank ~ q_w + q_pm + {ctrl}', P2, binomial=False), 'q_w', binomial=False)
    models['exOld_noResidual'] = orow(gee(f'exOld ~ q_w + q_pm + {ctrl}', P2, binomial=False), 'q_w', binomial=False)
    # overall vs chance
    overall = dict(n=int(len(P)), people=int(P.pid.nunique()),
                   rank=r(P.sizeRank.mean()), oldest=r(P.oldest.mean()), chOld=r(P.chOld.mean()),
                   top3=r(P.top3.mean()), chTop3=r(P.chTop3.mean()))
    # per person: mean size rank at short vs long queues (people with both)
    P['long'] = (P.q > VISIBLE).astype(int)
    pp = P.groupby(['pid', 'long']).agg(rank=('sizeRank', 'mean'), old=('exOld', 'mean')).unstack().dropna()
    d_rank = (pp[('rank', 1)] - pp[('rank', 0)]).to_numpy()
    d_old = (pp[('old', 1)] - pp[('old', 0)]).to_numpy()
    persons = dict(n=len(pp), rankLower=int((d_rank < 0).sum()), rankHigher=int((d_rank > 0).sum()),
                   rankMean=r(d_rank.mean()), rankP=r(stats.wilcoxon(d_rank).pvalue, 4),
                   oldLower=int((d_old < 0).sum()), oldHigher=int((d_old > 0).sum()),
                   oldMean=r(d_old.mean()), oldP=r(stats.wilcoxon(d_old).pvalue, 4),
                   points=[dict(pid=p, short=r(row[('rank', 0)]), long=r(row[('rank', 1)])) for p, row in pp.iterrows()])
    print('   overall (>=1 other waiting):', overall)
    print('   within-person per extra waiting mission:', {k: (v['est'], v['lo'], v['hi'], v['p']) for k, v in models.items()})
    print('   persons long vs short: size rank lower in %d, higher in %d (mean %s, p %s); excess-oldest lower %d higher %d (p %s)'
          % (persons['rankLower'], persons['rankHigher'], persons['rankMean'], persons['rankP'],
             persons['oldLower'], persons['oldHigher'], persons['oldP']))
    return dict(bins=bins, models=models, overall=overall, persons=persons), D


def triage_choice(S, rng):
    """Which of the waiting missions gets opened? A conditional logit over each decision's waiting set
    (the picked mission vs the others waiting at that moment). Candidate features: it is the OLDEST
    waiting, it is the NEWEST arrival, its size (drones, in units of 3 drones, relative to the set),
    it is a residual (left-over) mission. Fitted separately for short queues (1-3 others waiting) and
    long ones (4+), on all games and on the two Strategic Heavy games only (where 94% of long queues
    happen). CIs from a person bootstrap."""
    from statsmodels.discrete.conditional_models import ConditionalLogit
    rows = []
    for di, rr in enumerate(S.itertuples()):
        w = rr.waiting
        ids = [m for _, m, _, _ in w]
        if rr.missionId not in ids or len(w) < 2:
            continue
        nd = np.array([x[2] for x in w], float)
        for j, (_, m, d_, nt) in enumerate(w):
            rows.append(dict(dec=di, pid=rr.pid, game=rr.game, long=int(rr.st_queued > VISIBLE),
                             y=int(m == rr.missionId), oldest=int(j == 0), newest=int(j == len(w) - 1),
                             size=(d_ - nd.mean()) / 3.0, resid=int(m.endswith('-R'))))
    C = pd.DataFrame(rows)
    feats = ['oldest', 'newest', 'size', 'resid']

    def fit(Cx):
        m = ConditionalLogit(Cx.y.to_numpy(), Cx[feats].to_numpy(float), groups=Cx.dec.to_numpy()).fit(disp=0)
        return dict(zip(feats, np.asarray(m.params)))
    out = {}
    for scope, keep in (('all', C.game.notna()), ('strategicGames', C.game.str.startswith('strategic'))):
        for lab, lv in (('short', 0), ('long', 1)):
            Cx = C[keep & (C.long == lv)]
            est = fit(Cx)
            boots = {f: [] for f in feats}
            decs = {p: g for p, g in Cx.groupby('pid')}
            pids = np.array(list(decs))
            for b in range(200):
                pick = rng.choice(pids, len(pids), replace=True)
                Cb = pd.concat([decs[p].assign(dec=decs[p].dec.astype(str) + f'#{i}') for i, p in enumerate(pick)])
                Cb['dec'] = pd.factorize(Cb.dec)[0]
                try:
                    e = fit(Cb)
                except Exception:
                    continue
                for f in feats:
                    boots[f].append(e[f])
            out[f'{scope}.{lab}'] = dict(
                decisions=int(Cx.dec.nunique()), people=int(Cx.pid.nunique()),
                terms={f: dict(est=r(np.exp(est[f]), 3), lo=r(np.exp(np.nanpercentile(boots[f], 2.5)), 3),
                               hi=r(np.exp(np.nanpercentile(boots[f], 97.5)), 3)) for f in feats})
            print('   choice model %-15s %-5s (%d decisions): ' % (scope, lab, out[f'{scope}.{lab}']['decisions'])
                  + '  '.join('%s x%.2f [%.2f, %.2f]' % (f, v['est'], v['lo'], v['hi'])
                              for f, v in out[f'{scope}.{lab}']['terms'].items()))
    deepGames = S[S.st_queued > VISIBLE].game.value_counts().to_dict()
    out['longByGame'] = {k: int(v) for k, v in deepGames.items()}
    print('   long-queue decisions by game:', out['longByGame'])
    return out


def triage_choice_sig(S):
    """Pass 3: significance for the choice model. Same conditional logit as triage_choice, but the people
    are resampled JOINTLY for the short- and long-queue fits (1000 draws, own seeded RNG), so each term
    gets a bootstrap p-value (how often the resampled odds ratio lands on the other side of 1, doubled)
    and the short-vs-long DIFFERENCE gets its own interval and p-value. A model-based Wald p (which
    ignores that decisions are clustered within people) is given alongside as a cross-check."""
    from statsmodels.discrete.conditional_models import ConditionalLogit
    rng = np.random.default_rng(SEED + 303)
    NB = 1000
    rows = []
    for di, rr in enumerate(S.itertuples()):
        w = rr.waiting
        ids = [m for _, m, _, _ in w]
        if rr.missionId not in ids or len(w) < 2:
            continue
        nd = np.array([x[2] for x in w], float)
        for j, (_, m, d_, nt) in enumerate(w):
            rows.append(dict(dec=di, pid=rr.pid, game=rr.game, long=int(rr.st_queued > VISIBLE),
                             y=int(m == rr.missionId), oldest=int(j == 0), newest=int(j == len(w) - 1),
                             size=(d_ - nd.mean()) / 3.0, resid=int(m.endswith('-R'))))
    C = pd.DataFrame(rows)
    feats = ['oldest', 'newest', 'size', 'resid']

    def fit(Cx, wald=False):
        m = ConditionalLogit(Cx.y.to_numpy(), Cx[feats].to_numpy(float), groups=Cx.dec.to_numpy()).fit(disp=0)
        est = dict(zip(feats, np.asarray(m.params)))
        return (est, dict(zip(feats, np.asarray(m.pvalues)))) if wald else est

    def bp(v):
        v = np.asarray([x for x in v if np.isfinite(x)])
        return min(1.0, 2 * min((v <= 0).mean(), (v >= 0).mean())) if len(v) else None
    out = {}
    for scope, keep in (('all', C.game.notna()), ('strategicGames', C.game.str.startswith('strategic'))):
        Cs = C[keep]
        parts = {lab: Cs[Cs.long == lv] for lab, lv in (('short', 0), ('long', 1))}
        est = {lab: fit(Cx, wald=True) for lab, Cx in parts.items()}
        boots = {lab: {f: [] for f in feats} for lab in parts}
        diff = {f: [] for f in feats}
        decs = {lab: {p: g for p, g in Cx.groupby('pid')} for lab, Cx in parts.items()}
        pids = np.array(sorted(Cs.pid.unique()))
        for b in range(NB):
            pick = rng.choice(pids, len(pids), replace=True)
            e = {}
            for lab in parts:
                Cb = pd.concat([decs[lab][p].assign(dec=decs[lab][p].dec.astype(str) + f'#{i}')
                                for i, p in enumerate(pick) if p in decs[lab]])
                Cb['dec'] = pd.factorize(Cb.dec)[0]
                try:
                    e[lab] = fit(Cb)
                except Exception:
                    e[lab] = None
            for lab in parts:
                for f in feats:
                    boots[lab][f].append(e[lab][f] if e[lab] else np.nan)
            for f in feats:
                diff[f].append(e['long'][f] - e['short'][f] if e['short'] and e['long'] else np.nan)
        res = {}
        for lab, Cx in parts.items():
            res[lab] = dict(decisions=int(Cx.dec.nunique()), people=int(Cx.pid.nunique()), terms={
                f: dict(est=r(np.exp(est[lab][0][f]), 3), lo=r(np.exp(np.nanpercentile(boots[lab][f], 2.5)), 3),
                        hi=r(np.exp(np.nanpercentile(boots[lab][f], 97.5)), 3), p=r(bp(boots[lab][f]), 4),
                        pWald=r(est[lab][1][f], 4)) for f in feats})
        res['ratio'] = {f: dict(est=r(np.exp(est['long'][0][f] - est['short'][0][f]), 3),
                                lo=r(np.exp(np.nanpercentile(diff[f], 2.5)), 3),
                                hi=r(np.exp(np.nanpercentile(diff[f], 97.5)), 3), p=r(bp(diff[f]), 4)) for f in feats}
        out[scope] = res
        for lab in ('short', 'long'):
            print('   choice sig %-15s %-5s (%d decisions): ' % (scope, lab, res[lab]['decisions'])
                  + '  '.join('%s x%.2f [%.2f, %.2f] p=%.3f (Wald %.3f)' % (f, v['est'], v['lo'], v['hi'], v['p'], v['pWald'])
                              for f, v in res[lab]['terms'].items()))
        print('   choice sig %-15s long/short ratio: ' % scope
              + '  '.join('%s x%.2f [%.2f, %.2f] p=%.3f' % (f, v['est'], v['lo'], v['hi'], v['p']) for f, v in res['ratio'].items()))
    out['nBoot'] = NB
    return out


def pace(S, T, logs):
    """How fast: strategic decision time (total and beyond the forced card reveal), deciding before the
    cards load, tactical plan time, and strategic decisions per minute -- each against the queue,
    within person."""
    D = S[S.residual == 0].copy()
    D['q'] = D.st_queued
    D = centre(D, 'q')
    ctrl = 'ndrones + ncolours + emin + C(game)'
    out = {}
    m = gee(f'lsecs ~ q_w + q_pm + {ctrl}', D, binomial=False)
    out['secs'] = orow(m, 'q_w', binomial=False)
    out['secs']['pct'] = r(100 * (np.exp(m.params['q_w']) - 1), 2)
    out['secs']['pctLo'] = r(100 * (np.exp(m.conf_int().loc['q_w', 0]) - 1), 2)
    out['secs']['pctHi'] = r(100 * (np.exp(m.conf_int().loc['q_w', 1]) - 1), 2)
    D['lnet1'] = np.log(D.net.clip(lower=0) + 1)
    m = gee(f'lnet1 ~ q_w + q_pm + {ctrl}', D, binomial=False)
    out['net'] = orow(m, 'q_w', binomial=False)
    out['net']['pct'] = r(100 * (np.exp(m.params['q_w']) - 1), 2)
    out['early'] = orow(gee(f'early ~ q_w + q_pm + {ctrl}', D), 'q_w')
    # by bin, raw medians and early rate
    D['qb'] = D.q.map(qbin)
    out['bins'] = [dict(label=lab, n=int(len(g)), secs=r(g.secs.median(), 1),
                        secsQ1=r(g.secs.quantile(.25), 1), secsQ3=r(g.secs.quantile(.75), 1),
                        net=r(g.net.median(), 1), early=r(g.early.mean()), manual=r(1 - g.took.mean()))
                   for _, _, lab in QB for g in [D[D.qb == lab]] if len(g)]
    # tactical plan time vs strategic queue at planner open
    Tt = T.dropna(subset=['secs']).copy()
    Tt = Tt[Tt.secs > 0]
    Tt['ls'] = np.log(Tt.secs)
    Tt['q'] = Tt.st_queued
    Tt = centre(Tt, 'q')
    m = gee('ls ~ q_w + q_pm + lplan + ncolours + emin + C(game)', Tt, binomial=False)
    out['tacSecs'] = orow(m, 'q_w', binomial=False)
    out['tacSecs']['pct'] = r(100 * (np.exp(m.params['q_w']) - 1), 2)
    # strategic decisions per minute vs queue at the start of that minute (minutes with >= 1 waiting)
    rows = []
    for (pid, run), L in logs.items():
        s = S[(S.pid == pid) & (S.run == run)]
        if not len(s):
            continue
        ch = sorted(L['chosen'].values())
        for mi in range(8):
            t0 = 60 * mi
            q0 = sum(1 for m_, a in L['arr'].items() if a['t'] <= t0 and L['chosen'].get(m_, 1e9) > t0)
            n = sum(1 for c in ch if t0 <= c < t0 + 60)
            rows.append(dict(pid=pid, run=run, game=s.game.iloc[0], minute=mi, q0=q0, n=n))
    R = pd.DataFrame(rows)
    R1 = R[R.q0 >= 1].copy()
    R1 = centre(R1, 'q0')
    m = smf.gee('n ~ q0_w + q0_pm + C(minute) + C(game)', 'pid', data=R1, family=sm.families.Poisson(),
                cov_struct=sm.cov_struct.Exchangeable()).fit()
    out['rate'] = orow(m, 'q0_w')
    out['rate']['n'] = int(len(R1))
    out['rateBins'] = [dict(label=lab, n=int(len(g)), perMin=r(g.n.mean(), 2),
                            lo=r(g.n.mean() - 1.96 * g.n.std(ddof=1) / np.sqrt(len(g)), 2) if len(g) > 1 else None,
                            hi=r(g.n.mean() + 1.96 * g.n.std(ddof=1) / np.sqrt(len(g)), 2) if len(g) > 1 else None)
                       for _, _, lab in QB for g in [R[R.q0.map(qbin) == lab]] if len(g)]
    print('pace: decision time %+.1f%% per extra waiting [%s, %s] p %s; beyond-reveal %+.1f%% p %s; early-manual OR %s p %s'
          % (out['secs']['pct'], out['secs']['pctLo'], out['secs']['pctHi'], out['secs']['p'], out['net']['pct'],
             out['net']['p'], out['early']['est'], out['early']['p']))
    print('   tactical plan time %+.1f%% p %s; decisions/minute rate ratio %s [%s,%s] p %s (n %d minutes with >=1 waiting)'
          % (out['tacSecs']['pct'], out['tacSecs']['p'], out['rate']['est'], out['rate']['lo'], out['rate']['hi'],
             out['rate']['p'], out['rate']['n']))
    print('   bins:', [(x['label'], x['n'], x['secs'], x['net'], x['early'], x['manual']) for x in out['bins']])
    print('   decisions per minute by queue at minute start:', [(x['label'], x['n'], x['perMin']) for x in out['rateBins']])
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════

def main():
    rng = np.random.default_rng(SEED)
    S, T, logs, said, M = load()
    hdr('Games')
    games, gdrones = game_load(S, logs)
    heavy = sorted(gdrones, key=gdrones.get)[-2:]
    print('heavier games:', heavy, '; C11 people:', sorted(said))

    hdr('A · The null, raw vs adjusted (person bootstrap, model re-fitted each time)')
    Ss = S[S.residual == 0].copy()
    sBins, SE = null_bins(Ss, 'took', 'st_queued', 'strategic', rng)
    tBins, TE = null_bins(T, 'consulted', 'st_queued', 'tactical', rng)
    # how the adjustment works, in numbers, for the deepest bins: observed, expected, the gap
    hdr('B · Robustness strip')
    sRob = robustness(Ss, 'took', 'st_queued', 'strategic', heavy)
    tRob = robustness(T, 'consulted', 'st_queued', 'tactical', heavy)
    sDet = detectable(Ss, 'took', sRob[2])
    tDet = detectable(T, 'consulted', tRob[2])
    print('strategic: at the CI limits, uptake at 5 waiting would be %s–%s (vs %s at 0)' % (sDet['lo'], sDet['hi'], sDet['base']))
    print('tactical: at the CI limits, Suggest at 5 waiting would be %s–%s (vs %s at 0)' % (tDet['lo'], tDet['hi'], tDet['base']))
    # the adjustment model itself: how much each ingredient matters
    E = x2.add_expected(Ss, 'took')
    fit = smf.glm('took ~ ndrones + ntasks + ncolours + emin + C(game) + base', E,
                  family=sm.families.Binomial()).fit()
    adjModel = {k: dict(b=r(fit.params[k], 4), p=r(fit.pvalues[k], 4)) for k in ('ndrones', 'ntasks', 'ncolours', 'emin', 'base')}
    print('adjustment model (strategic):', adjModel)
    qcorr = dict(ndrones=r(stats.spearmanr(Ss.st_queued, Ss.ndrones)[0]), minute=r(stats.spearmanr(Ss.st_queued, Ss.t)[0]))
    print('queue vs mission drones rho %s; queue vs minute rho %s' % (qcorr['ndrones'], qcorr['minute']))

    hdr('C · Said vs did')
    sSlopes = person_slopes(SE, 'took', 'st_queued', said)
    tSlopes = person_slopes(TE, 'consulted', 'st_queued', said)
    for nm, o in (('strategic', sSlopes), ('tactical', tSlopes)):
        print('%s person slopes (pp per extra waiting, adjusted): said %s (n %d, %d positive) vs not %s (n %d, %d positive); '
              'Mann-Whitney p %s; said vs 0 p %s' % (nm, o['said']['mean'], o['said']['n'], o['said']['positive'],
                                                   o['notSaid']['mean'], o['notSaid']['n'], o['notSaid']['positive'],
                                                   o['pDiff'], o['pSaidVsZero']))
    sInt = said_interaction(Ss, 'took', 'st_queued', said)
    tInt = said_interaction(T, 'consulted', 'st_queued', said)
    print('strategic interaction:', sInt)
    print('tactical interaction:', tInt)
    sBusy = busier_session(SE, 'took', said, gdrones)
    tBusy = busier_session(TE, 'consulted', said, gdrones)
    for nm, o in (('strategic', sBusy), ('tactical', tBusy)):
        for g in ('said', 'notSaid', 'all'):
            print('%s heavier-minus-lighter game, %s: raw %s [%s,%s] (%d/%d higher, p %s); adjusted %s [%s,%s] (%d/%d higher, p %s)'
                  % (nm, g, o[g]['rawDiff']['mean'], o[g]['rawDiff']['lo'], o[g]['rawDiff']['hi'], o[g]['rawDiff']['higher'],
                     o[g]['rawDiff']['n'], o[g]['rawDiff']['p'], o[g]['adjDiff']['mean'], o[g]['adjDiff']['lo'],
                     o[g]['adjDiff']['hi'], o[g]['adjDiff']['higher'], o[g]['adjDiff']['n'], o[g]['adjDiff']['p']))
    TE2 = TE.copy()
    narr = narration_moments(SE, TE2, logs, said, rng)

    hdr('D · Backlog vs practice (tactical Suggest)')
    bp = backlog_practice(T, rng)

    hdr('E · Deep queues: within vs between')
    sDeep = deep(SE, 'took', 'strategic')
    tDeep = deep(TE, 'consulted', 'tactical')

    hdr('F · Triage: what gets picked, and how fast')
    tri, _ = triage(S, logs, rng)
    tri['choice'] = triage_choice(S, rng)
    pc = pace(S, T, logs)
    tri['choiceSig'] = triage_choice_sig(S)

    res = dict(generated=pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'), visible=VISIBLE, games=games, heavy=heavy,
               said=sorted(said), nPeople=int(S.pid.nunique()),
               null=dict(strategic=dict(bins=sBins, robust=sRob, detect=sDet, n=int(len(Ss)), overall=r(Ss.took.mean())),
                         tactical=dict(bins=tBins, robust=tRob, detect=tDet, n=int(len(T)), overall=r(T.consulted.mean())),
                         adjModel=adjModel, qcorr=qcorr),
               saidDid=dict(slopes=dict(strategic=sSlopes, tactical=tSlopes),
                            interaction=dict(strategic=sInt, tactical=tInt),
                            busier=dict(strategic=sBusy, tactical=tBusy), narration=narr),
               backlog=bp, deep=dict(strategic=sDeep, tactical=tDeep), triage=tri, pace=pc)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, separators=(',', ':'), default=lambda o: o.item() if hasattr(o, 'item') else str(o)),
                   encoding='utf-8')
    print('\nwrote', OUT.relative_to(BASE))


if __name__ == '__main__':
    main()
