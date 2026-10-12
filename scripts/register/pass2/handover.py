#!/usr/bin/env python3
"""Pass 2 · AREA `handover` — "When operators hand over".

Read-only over Results/. Writes docs/analysis/register/pass2/handover.json (embedded in the review page as
DATA.pass2.handover) and prints every number the findings quote. Run from the repo root:

    python scripts/register/pass2/handover.py

Cards carried here: size-decides, speed-big-jobs, speed-parallel, learn-speed, learn-calibration-null,
manual-anchored (+ qualitative codes C03-C10, C22). What each block does:

A · SIZE DECIDES. Hand-over rate against mission size, separately for the strategic tier (strategy card
    taken as offered) and the tactical tier (Suggest pressed at least once in the planner), and both tiers
    in one model. Size = drones the mission needs (sum of primary requirements over its tasks, what the task
    badges say), drone types needed, tasks, and for the planner the plan size (drones in the team x tasks).
    Person adjustment: GEE logit clustered on person with the size measure split into a within-person part
    (this decision's size minus the person's own mean) and a between-person part (that mean); the within
    coefficient compares each person only with themselves. A conditional (fixed-effects) logit is the
    second check. Robustness strip: every specification tried is reported, including the artefact checks
    the researcher asked for (illogical Conservative card excluded; corrupted cards; queue held fixed).
B · SPEED BY SIZE. Decision time by route x size, both tiers.
C · PARALLEL WORK. What "4.8x more likely to start the next mission during the fill" is, re-derived and
    sharpened (fill window itself; time-matched; only when something was waiting).
D · C06 "the assistant is slow": who said it, and their numbers against everyone else's.
E · LEARNING. Speed by minute and session; whether the size rule sharpens (it does not); C22 vs logs.
F · MANUAL AROUND THE CARDS. Manual drones minus Conservative card drones per decision, by size; the
    pre-emptive manuals (made before the cards existed) are the natural control for "anchoring".
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.discrete.conditional_models import ConditionalLogit

BASE = Path(__file__).resolve().parents[3]
for p in ('scripts', 'scripts/analysis_round1', 'scripts/analysis_round2', 'scripts/analysis_combined'):
    sys.path.insert(0, str(BASE / p))
warnings.filterwarnings('ignore')

OUT = BASE / 'docs' / 'analysis' / 'register' / 'pass2' / 'handover.json'
PARTS = BASE / 'Results' / 'Participants'
QUAL = BASE / 'docs' / 'analysis' / 'qual' / 'codes_matrix.csv'
SEED = 20261012
B_BOOT = 2000
N_PERM = 20000
EXCLUDE = {'P09'}
HALF_WEIGHT = {'P01', 'P02'}
SUGGEST_REVEAL_S = 1.0


def hdr(s):
    print('\n' + '=' * 96 + '\n' + s + '\n' + '=' * 96)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def r(x, d=4):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, d) if np.isfinite(x) else None


# ════════════════════════════════════════════════════════════════════════════════════════════
# data
# ════════════════════════════════════════════════════════════════════════════════════════════

def raw_pass():
    """Per strategic choice: the cards shown at the last open (true asset counts per colour, whether a
    card was an ε-corrupted one), the operator's chosen counts, the mission's per-colour need.
    Per tactical planner: Suggest press times and strategic-panel opens for OTHER missions while open."""
    strat, tac = {}, {}
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
            need, last_open, open_tac = {}, {}, {}
            for e in evs:
                t, m, ts = e['type'], e.get('missionId'), e.get('timestamp')
                if t == 'mission_arrived':
                    tot = {'Blue': 0, 'Red': 0, 'Green': 0}
                    for task in e.get('tasks', []):
                        for c, n in primary[str(task['type'])].items():
                            tot[c] += n
                    need[m] = tot
                elif t == 'strategic_modal_opened':
                    for om, rec in open_tac.items():
                        if om != m:
                            rec['opens'].append(ts)
                    cards = {c['name']: c for c in e.get('strategiesPresented', [])}
                    if len(cards) >= 2:
                        last_open[m] = cards
                if t == 'strategic_choice':
                    for om, rec in open_tac.items():
                        if om != m:
                            rec['choices'].append(ts)
                if t == 'strategic_choice' and m in last_open:
                    cards = last_open.pop(m)
                    strat[(pid, run, m, ts)] = dict(
                        cons={k: int(v) for k, v in cards['Conservative']['trueAssets'].items()},
                        aggr={k: int(v) for k, v in cards['Aggressive']['trueAssets'].items()},
                        bad=int(any(c.get('isBadSuggestion') for c in cards.values())),
                        chosen={k: int(v) for k, v in (e.get('assetsChosen') or {}).items()},
                        need=need.get(m, {}))
                elif t == 'tactical_opened':
                    open_tac[m] = dict(open=ts, sugg=[], opens=[], choices=[])
                elif t == 'tactical_suggest_used' and not e.get('recoveryMode') and m in open_tac:
                    open_tac[m]['sugg'].append(ts)
                elif t == 'tactical_confirmed' and m in open_tac:
                    rec = open_tac.pop(m)
                    tac[(pid, run, m, ts)] = rec
    return strat, tac


def load():
    import build_findings_synthesis as b
    import extras2 as X2
    import h4_h10_data as H4
    S, T, _eps, logs, _agree = quiet(X2.load)
    dec = quiet(b.load_decisions)
    dec = dec.sort_values(['pid', 'run', 'idx']).reset_index(drop=True)
    dec['k'] = dec.groupby(['pid', 'run']).cumcount()
    S = S.merge(dec[['pid', 'run', 'k', 'cons_total', 'aggr_total', 'committed']], on=['pid', 'run', 'k'],
                how='left')
    strat, tac = raw_pass()
    rows = []
    for x in S.itertuples():
        g = strat.get((x.pid, x.run, x.missionId, x.choice_ts))
        rows.append(dict(bad=g['bad'] if g else np.nan, _g=g))
    G = pd.DataFrame(rows, index=S.index)
    S['bad'] = G.bad
    S['_g'] = G._g
    miss = int(S._g.isna().sum())
    print('strategic rows %d (raw-card merge misses %d); tactical rows %d' % (len(S), miss, len(T)))
    assert miss == 0
    chk = (S.cons_total != S._g.map(lambda g: sum(g['cons'].values()))).sum()
    assert chk == 0, 'card totals disagree'
    # size measures
    S['l2d'] = np.log2(S.ndrones.clip(lower=1))
    S['ntypes'] = S.ncolours
    S['multi'] = (S.ncolours >= 2).astype(int)
    T = T.copy()
    T['l2plan'] = np.log2(T.plan.clip(lower=1))
    T['l2d'] = np.log2(T.ndrones.clip(lower=1))
    T['ntypes'] = T.ncolours
    T['run2'] = (T.run == 2).astype(int)
    S['run2'] = (S.run == 2).astype(int)
    # tactical: Suggest timing and interleaving from the raw pass
    tr = [tac.get((x.pid, x.run, x.missionId, x.confirm_ts)) for x in T.itertuples()]
    print('tactical raw merge misses: %d' % sum(v is None for v in tr))
    T['_raw'] = tr
    # net decision time (forced waits removed) -- as round 2 defined it
    T['net'] = np.where(T.consulted == 1, T.secs - T.entries * SUGGEST_REVEAL_S, T.secs)
    T['lnet'] = np.log(T.net.clip(lower=0.5))
    T['lsecs'] = np.log(T.secs.clip(lower=0.5))
    # session scores, rescaled for P01/P02's half task weights, standardised within game
    P = quiet(H4.sessions).copy()
    P = P[P.pid.isin(set(S.pid))]
    P['zgame'] = P.groupby('game').score_rescaled.transform(lambda s: (s - s.mean()) / s.std())
    qual = pd.read_csv(QUAL)
    who = {c: sorted(qual.pid[qual[c] == 1]) for c in qual.columns if c.startswith('C')}
    return S, T, P, who


# ════════════════════════════════════════════════════════════════════════════════════════════
# statistics helpers
# ════════════════════════════════════════════════════════════════════════════════════════════

RNG = np.random.default_rng(SEED)


def boot_rate(d, y, by, order=None, B=B_BOOT):
    """Pooled rate of y per bin, with a 95% interval from resampling PEOPLE (a person's decisions travel
    together, so one heavy user cannot make an interval look tight)."""
    d = d.dropna(subset=[by, y])
    people = sorted(d.pid.unique())
    pi = {p: i for i, p in enumerate(people)}
    bins = order or sorted(d[by].unique())
    num = np.zeros((len(bins), len(people)))
    den = np.zeros((len(bins), len(people)))
    for j, b_ in enumerate(bins):
        g = d[d[by] == b_]
        for p, gg in g.groupby('pid'):
            num[j, pi[p]] = gg[y].sum()
            den[j, pi[p]] = len(gg)
    draw = RNG.integers(0, len(people), (B, len(people)))
    out = []
    for j, b_ in enumerate(bins):
        if den[j].sum() == 0:
            continue
        nn = num[j][draw].sum(1)
        dd = den[j][draw].sum(1)
        bs = nn[dd > 0] / dd[dd > 0]
        out.append(dict(bin=b_ if not isinstance(b_, (np.integer, np.floating)) else b_.item(),
                        rate=r(num[j].sum() / den[j].sum()), lo=r(np.percentile(bs, 2.5)),
                        hi=r(np.percentile(bs, 97.5)), n=int(den[j].sum()), k=int((den[j] > 0).sum())))
    return out


def boot_median(d, y, by, order=None, B=1000):
    """Median of y per bin; 95% interval from resampling people."""
    d = d.dropna(subset=[by, y])
    people = np.array(sorted(d.pid.unique()))
    bins = order or sorted(d[by].unique())
    out = []
    for b_ in bins:
        g = d[d[by] == b_]
        if not len(g):
            continue
        per = {p: gg[y].values for p, gg in g.groupby('pid')}
        arrs = [per.get(p, np.array([])) for p in people]
        meds = []
        for _ in range(B):
            pick = RNG.integers(0, len(people), len(people))
            v = np.concatenate([arrs[i] for i in pick])
            if len(v):
                meds.append(np.median(v))
        out.append(dict(bin=b_ if not isinstance(b_, (np.integer, np.floating)) else b_.item(),
                        med=r(g[y].median(), 2), lo=r(np.percentile(meds, 2.5), 2),
                        hi=r(np.percentile(meds, 97.5), 2), n=int(len(g)), k=int(g.pid.nunique())))
    return out


def centre(d, var):
    d = d.copy()
    d[var + '_pm'] = d.groupby('pid')[var].transform('mean')
    d[var + '_w'] = d[var] - d[var + '_pm']
    return d


def gee_fit(formula, d, binomial=True):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    m = smf.gee(formula, 'pid', data=d, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    try:
        return m.fit(cov_type='bias_reduced')
    except Exception:
        return m.fit()


def term(m, name, binomial=True, scale=1.0):
    b = float(m.params[name]) * scale
    se = float(m.bse[name]) * scale
    f = np.exp if binomial else (lambda v: v)
    return dict(est=r(f(b)), lo=r(f(b - 1.96 * se)), hi=r(f(b + 1.96 * se)), p=r(m.pvalues[name], 5),
                b=r(b), se=r(se))


def within_or(d, y, x, extra='C(game) + C(run)', binomial=True, scale=1.0):
    """y ~ x_w + x_pm + extra, GEE clustered on person. Returns the within-person term."""
    need = [y, x] + [c for c in ('game', 'run', 'pid') if c in d.columns]
    d = d.dropna(subset=need)
    if d[x].nunique() < 2 or (binomial and d[y].nunique() < 2) or d.pid.nunique() < 4:
        return None
    d = centre(d, x)
    if 'C(game)' in extra and 'C(run)' in extra and d.groupby('game').run.nunique().max() == 1:
        extra = extra.replace(' + C(run)', '').replace('C(run) + ', '').replace('C(run)', '')
    f = '%s ~ %s_w + %s_pm%s' % (y, x, x, (' + ' + extra) if extra.strip() else '')
    try:
        m = gee_fit(f, d, binomial)
        out = term(m, x + '_w', binomial, scale)
    except Exception as ex:
        print('   fit failed: %s (%s)' % (f, ex))
        return None
    out.update(n=int(len(d)), k=int(d.pid.nunique()))
    return out


def clogit(d, y, x):
    """Conditional (fixed-effects) logit: each person compared only with themselves, with a session-2
    dummy. Within one person the game is fixed by the session (everyone plays two different games), so
    the session dummy is the game adjustment; game dummies on top are collinear with it."""
    d = d.dropna(subset=[y, x]).copy()
    # people who never vary on y carry no information in a conditional logit
    v = d.groupby('pid')[y].transform('nunique') > 1
    d = d[v]
    X = np.column_stack([d[x].values.astype(float), (d.run == 2).values.astype(float)])
    m = ConditionalLogit(d[y].values.astype(float), X, groups=pd.factorize(d.pid)[0]).fit(disp=0)
    b, se, p = m.params[0], m.bse[0], m.pvalues[0]
    return dict(est=r(np.exp(b)), lo=r(np.exp(b - 1.96 * se)), hi=r(np.exp(b + 1.96 * se)), p=r(p, 5),
                n=int(len(d)), k=int(d.pid.nunique()))


def perm_diff(vals, inset, n=N_PERM):
    """Group mean minus the rest; two-sided permutation p (labels reshuffled n times)."""
    v = pd.Series(vals).dropna()
    lab = v.index.isin(inset)
    if lab.sum() < 2 or (~lab).sum() < 2:
        return dict(inMean=r(v[lab].mean()), restMean=r(v[~lab].mean()), diff=None, p=None,
                    nIn=int(lab.sum()), nRest=int((~lab).sum()))
    obs = v[lab].mean() - v[~lab].mean()
    rng = np.random.default_rng(SEED)
    arr, k = v.values, lab.sum()
    cnt = 0
    for _ in range(n):
        idx = rng.permutation(len(arr))
        dd = arr[idx[:k]].mean() - arr[idx[k:]].mean()
        cnt += abs(dd) >= abs(obs) - 1e-12
    return dict(inMean=r(v[lab].mean()), restMean=r(v[~lab].mean()), diff=r(obs), p=r((cnt + 1) / (n + 1)),
                nIn=int(k), nRest=int((~lab).sum()))


def say(label, t, unit='OR'):
    if t is None:
        print('  %-70s  not estimable' % label)
        return
    print('  %-70s  %s %.2f [%.2f, %.2f] p=%.4f  n=%s/%s' % (label, unit, t['est'], t['lo'], t['hi'], t['p'],
                                                               t.get('n'), t.get('k')))


# ════════════════════════════════════════════════════════════════════════════════════════════
# A · size decides
# ════════════════════════════════════════════════════════════════════════════════════════════

DBIN = [(1, 3, '1–3'), (5, 5, '5'), (6, 6, '6'), (7, 8, '7–8'), (9, 9, '9'), (10, 11, '10–11'),
        (12, 13, '12–13'), (15, 15, '15'), (18, 18, '18')]
DBIN_X = {'1–3': 3, '5': 5, '6': 6, '7–8': 7, '9': 9, '10–11': 10.5, '12–13': 12.5, '15': 15, '18': 18}
CBIN = [(0, 3, '≤3'), (5, 5, '5'), (6, 6, '6'), (7, 9, '7–9'), (10, 13, '10–13'), (15, 18, '15–18')]
CBIN_X = {'≤3': 3, '5': 5, '6': 6, '7–9': 8, '10–13': 11.5, '15–18': 16.5}
PBIN = [(0, 8, '≤8'), (9, 15, '9–15'), (16, 24, '16–24'), (25, 35, '25–35'), (36, 50, '36–50'),
        (51, 1000, '51+')]


def binof(v, bins):
    for lo, hi, lab in bins:
        if lo <= v <= hi:
            return lab
    return None


def section_size(S, T, who):
    hdr('A · SIZE DECIDES')
    out = {}
    S = S.copy()
    T = T.copy()
    S['dbin'] = S.ndrones.map(lambda v: binof(v, DBIN))
    S['cbin'] = S.ndrones.map(lambda v: binof(v, CBIN))
    T['cbin'] = T.ndrones.map(lambda v: binof(v, CBIN))
    T['pbin'] = T.plan.map(lambda v: binof(v, PBIN))
    S['typelab'] = S.ncolours.map({1: 'one type', 2: 'two types', 3: 'three types'})
    T['typelab'] = T.ncolours.map({0: None, 1: 'one type', 2: 'two types', 3: 'three types'})

    # A1 · the raw dose-response, strategic, split by drone types
    print('\nA1 strategic: card taken by drones needed, single- vs three-type')
    dose = {}
    for nc, lab in ((1, 'one'), (3, 'three')):
        g = S[S.ncolours == nc]
        rows = boot_rate(g, 'took', 'dbin', [b[2] for b in DBIN])
        for x in rows:
            x['x'] = DBIN_X[x['bin']]
        dose[lab] = rows
        for x in rows:
            print('   %-5s %-6s n=%3d k=%2d  %.2f [%.2f, %.2f]' % (lab, x['bin'], x['n'], x['k'], x['rate'], x['lo'], x['hi']))
    dose['byTypes'] = boot_rate(S, 'took', 'ncolours', [1, 2, 3])
    dose['byTasks'] = boot_rate(S[S.residual == 0], 'took', 'ntasks', [2, 3, 4, 5, 6])
    print('   by types:', [(x['bin'], x['n'], x['rate']) for x in dose['byTypes']])
    print('   by tasks (non-residual):', [(x['bin'], x['n'], x['rate']) for x in dose['byTasks']])
    # the strategic hand-over has two steps: deciding before the cards exist (pre-emptive manual), and,
    # once the cards are on screen, taking one
    dose['preempt'] = boot_rate(S, 'early', 'cbin', [b[2] for b in CBIN])
    dose['tookSeen'] = boot_rate(S[S.early == 0], 'took', 'cbin', [b[2] for b in CBIN])
    for k in ('preempt', 'tookSeen'):
        for x in dose[k]:
            x['x'] = CBIN_X[x['bin']]
        print('   %s:' % k, [(x['bin'], x['n'], x['rate']) for x in dose[k]])
    out['strat'] = dose

    # A2 · tactical: Suggest pressed by plan size and by tasks
    print('\nA2 tactical: Suggest pressed by plan size (drones in team x tasks)')
    tac = dict(byPlan=boot_rate(T, 'consulted', 'pbin', [b[2] for b in PBIN]),
               byTasks=boot_rate(T[T.residual == 0], 'consulted', 'ntasks', [2, 3, 4, 5, 6]),
               byTypes=boot_rate(T[T.ncolours > 0], 'consulted', 'ncolours', [1, 2, 3]))
    for x in tac['byPlan']:
        print('   plan %-6s n=%3d k=%2d  %.2f [%.2f, %.2f]' % (x['bin'], x['n'], x['k'], x['rate'], x['lo'], x['hi']))
    print('   by tasks:', [(x['bin'], x['n'], x['rate']) for x in tac['byTasks']])
    print('   by types:', [(x['bin'], x['n'], x['rate']) for x in tac['byTypes']])
    # tactical by plan size, split by the strategic route chosen for that mission
    tac['byPlanRoute'] = {}
    for st, lab in (('Manual', 'manual'), ('card', 'card')):
        g = T[T.strategy == 'Manual'] if st == 'Manual' else T[T.strategy != 'Manual']
        tac['byPlanRoute'][lab] = boot_rate(g, 'consulted', 'pbin', [b[2] for b in PBIN])
    out['tac'] = tac

    # A3 · both tiers on one axis: drones the mission needs
    print('\nA3 both tiers by drones needed')
    both = dict(strat=boot_rate(S, 'took', 'cbin', [b[2] for b in CBIN]),
                tac=boot_rate(T[T.ndrones > 0], 'consulted', 'cbin', [b[2] for b in CBIN]))
    for k in both:
        for x in both[k]:
            x['x'] = CBIN_X[x['bin']]
        print('  ', k, [(x['bin'], x['n'], x['rate']) for x in both[k]])
    out['both'] = both

    # A4 · person-adjusted models
    print('\nA4 within-person models (GEE logit, clustered on person, size split within/between; game + run)')
    M = {}
    M['s_doubling'] = within_or(S, 'took', 'l2d'); say('strategic: card ~ doubling of drones needed', M['s_doubling'])
    M['s_type'] = within_or(S, 'took', 'ntypes'); say('strategic: card ~ each extra drone type', M['s_type'])
    M['s_task'] = within_or(S[S.residual == 0], 'took', 'ntasks'); say('strategic: card ~ each extra task', M['s_task'])
    M['s_three'] = within_or(S, 'took', 'threetype'); say('strategic: card ~ three-type vs not', M['s_three'])
    M['s_pre'] = within_or(S, 'early', 'l2d'); say('strategic: pre-emptive manual ~ doubling of drones', M['s_pre'])
    M['s_seen'] = within_or(S[S.early == 0], 'took', 'l2d'); say('strategic, cards seen: card ~ doubling of drones', M['s_seen'])
    M['s_seen_three'] = within_or(S[S.early == 0], 'took', 'threetype'); say('strategic, cards seen: card ~ three-type', M['s_seen_three'])
    M['s_pre_three'] = within_or(S, 'early', 'threetype'); say('strategic: pre-emptive ~ three-type', M['s_pre_three'])
    M['s_d_in3'] = within_or(S[S.ncolours == 3], 'took', 'l2d'); say('strategic, three-type only: doubling of drones', M['s_d_in3'])
    M['s_d_in1'] = within_or(S[S.ncolours == 1], 'took', 'l2d'); say('strategic, single-type only: doubling of drones', M['s_d_in1'])
    M['t_doubling_plan'] = within_or(T, 'consulted', 'l2plan'); say('tactical: Suggest ~ doubling of plan size', M['t_doubling_plan'])
    M['t_doubling'] = within_or(T[T.ndrones > 0], 'consulted', 'l2d'); say('tactical: Suggest ~ doubling of drones needed', M['t_doubling'])
    M['t_type'] = within_or(T[T.ncolours > 0], 'consulted', 'ntypes'); say('tactical: Suggest ~ each extra drone type', M['t_type'])
    M['t_task'] = within_or(T[T.residual == 0], 'consulted', 'ntasks'); say('tactical: Suggest ~ each extra task', M['t_task'])
    M['t_plan_in3'] = within_or(T[T.ncolours == 3], 'consulted', 'l2plan'); say('tactical, three-type only: doubling of plan', M['t_plan_in3'])
    M['t_plan_in1'] = within_or(T[T.ncolours == 1], 'consulted', 'l2plan'); say('tactical, single-type only: doubling of plan', M['t_plan_in1'])
    # combined: both tiers stacked, same size measure, slope per tier and the difference
    A = pd.concat([S.assign(y=S.took, tier='strat')[['pid', 'run', 'game', 'y', 'tier', 'l2d']],
                   T[T.ndrones > 0].assign(y=T.consulted, tier='tac')[['pid', 'run', 'game', 'y', 'tier', 'l2d']]],
                  ignore_index=True)
    A = centre(A, 'l2d')
    A['tac'] = (A.tier == 'tac').astype(int)
    mA = gee_fit('y ~ l2d_w + l2d_w:tac + tac + l2d_pm + l2d_pm:tac + C(game) + C(run)', A)
    M['both_strat_slope'] = term(mA, 'l2d_w')
    M['both_diff'] = term(mA, 'l2d_w:tac')
    mA2 = gee_fit('y ~ l2d_w + tac + l2d_pm + C(game) + C(run)', A)
    M['both_common'] = dict(term(mA2, 'l2d_w'), n=int(len(A)), k=int(A.pid.nunique()))
    say('both tiers, common slope per doubling of drones needed', M['both_common'])
    say('  strategic slope in the stacked model', M['both_strat_slope'])
    say('  tactical minus strategic slope (ratio of ORs)', M['both_diff'])
    # predicted curves (within-person slope, at the average person, game-averaged) for the chart
    grid = np.log2(np.array([3, 5, 6, 9, 12, 15, 18]))
    curves = {}
    for lab, d, y in (('strat', S, 'took'), ('tac', T[T.ndrones > 0], 'consulted')):
        dd = centre(d.dropna(subset=['l2d']), 'l2d')
        m = gee_fit('%s ~ l2d_w + l2d_pm + C(game) + C(run)' % y, dd)
        base = dd.copy()
        pts = []
        for gv in grid:
            base['l2d_w'] = gv - dd.l2d.mean()
            base['l2d_pm'] = dd.l2d.mean()
            # mean over the observed rows (their games and runs) of the predicted probability
            p = m.predict(base)
            pts.append(dict(x=r(2 ** gv, 2), p=r(p.mean())))
        curves[lab] = pts
    out['curves'] = curves

    # A5 · robustness strip, strategic (per doubling of drones needed) and tactical (per doubling of plan)
    print('\nA5 robustness, strategic: OR per doubling of drones needed, within person')
    v112 = S.vrank >= quiet(lambda: __import__('wB_common').V112)
    rs = []

    def add(lst, label, t, note=''):
        if t is not None:
            lst.append(dict(label=label, note=note, **t))
        say(label, t)

    add(rs, 'All decisions (main)', M['s_doubling'])
    add(rs, 'Illogical Conservative card excluded', within_or(S[S.odd == 0], 'took', 'l2d'),
        'drops the 129 single-type + 3 two-type decisions where the Conservative card carried a type the mission did not need')
    add(rs, 'Pre-emptive manuals excluded', within_or(S[S.early == 0], 'took', 'l2d'),
        'only decisions where the cards were on screen before the choice')
    add(rs, 'Residual missions excluded', within_or(S[S.residual == 0], 'took', 'l2d'))
    add(rs, 'P01/P02 (half task weights) excluded', within_or(S[~S.pid.isin(HALF_WEIGHT)], 'took', 'l2d'))
    add(rs, 'Session 1 only', within_or(S[S.run == 1], 'took', 'l2d', extra='C(game)'))
    add(rs, 'Session 2 only', within_or(S[S.run == 2], 'took', 'l2d', extra='C(game)'))
    add(rs, 'study-v1.12+ only', within_or(S[v112], 'took', 'l2d'))
    add(rs, 'Strategic Heavy sessions only', within_or(S[S.scenario == 'strategic'], 'took', 'l2d'))
    add(rs, 'Tactical Heavy sessions only', within_or(S[S.scenario == 'tactical'], 'took', 'l2d'))
    add(rs, 'Queue length held fixed', within_or(S, 'took', 'l2d', extra='C(game) + C(run) + q_w + q_pm'),
        'missions waiting at the decision, within + between person (f-workload owns the queue story)')
    add(rs, 'Minute of session held fixed', within_or(S, 'took', 'l2d', extra='C(game) + C(run) + emin'))
    try:
        add(rs, 'Conditional logit (person fixed effects)', clogit(S, 'took', 'l2d'))
        add(rs, 'Conditional logit, illogical card excluded', clogit(S[S.odd == 0], 'took', 'l2d'))
    except Exception as ex:
        print('  clogit failed', ex)
    out['robustS'] = rs

    print('\nA5 robustness, tactical: OR per doubling of plan size, within person')
    rt = []
    v112t = T.vrank >= quiet(lambda: __import__('wB_common').V112)
    add(rt, 'All plans (main)', M['t_doubling_plan'])
    add(rt, 'Mission had an illogical Conservative card excluded',
        within_or(T.merge(S[['pid', 'run', 'missionId', 'odd']].drop_duplicates(['pid', 'run', 'missionId'], keep='last'),
                          on=['pid', 'run', 'missionId'], how='left').query('odd == 0'), 'consulted', 'l2plan'))
    add(rt, 'Strategic card taken for that mission', within_or(T[T.strategy != 'Manual'], 'consulted', 'l2plan'))
    add(rt, 'Strategic allocation was manual', within_or(T[T.strategy == 'Manual'], 'consulted', 'l2plan'))
    add(rt, 'Strategic route held fixed', within_or(T, 'consulted', 'l2plan', extra='C(game) + C(run) + C(strategy)'))
    add(rt, 'Residual missions excluded', within_or(T[T.residual == 0], 'consulted', 'l2plan'))
    add(rt, 'P01/P02 excluded', within_or(T[~T.pid.isin(HALF_WEIGHT)], 'consulted', 'l2plan'))
    add(rt, 'Session 1 only', within_or(T[T.run == 1], 'consulted', 'l2plan', extra='C(game)'))
    add(rt, 'Session 2 only', within_or(T[T.run == 2], 'consulted', 'l2plan', extra='C(game)'))
    add(rt, 'study-v1.12+ only', within_or(T[v112t], 'consulted', 'l2plan'))
    add(rt, 'Strategic Heavy sessions only', within_or(T[T.scenario == 'strategic'], 'consulted', 'l2plan'))
    add(rt, 'Tactical Heavy sessions only', within_or(T[T.scenario == 'tactical'], 'consulted', 'l2plan'))
    add(rt, 'Queue length held fixed', within_or(T, 'consulted', 'l2plan', extra='C(game) + C(run) + q_w + q_pm'))
    add(rt, 'Minute of session held fixed', within_or(T, 'consulted', 'l2plan', extra='C(game) + C(run) + emin'))
    try:
        add(rt, 'Conditional logit (person fixed effects)', clogit(T, 'consulted', 'l2plan'))
    except Exception as ex:
        print('  clogit failed', ex)
    out['robustT'] = rt
    out['models'] = M

    # A6 · artefact checks in plain numbers
    print('\nA6 artefact checks')
    one = S[S.ncolours == 1]
    art = dict(
        oddShareOne=r(one.odd.mean()), oddShareThree=r(S[S.ncolours == 3].odd.mean()),
        tookOneOdd=r(one[one.odd == 1].took.mean()), nOneOdd=int((one.odd == 1).sum()),
        tookOneClean=r(one[one.odd == 0].took.mean()), nOneClean=int((one.odd == 0).sum()),
        tookThree=r(S[S.ncolours == 3].took.mean()), nThree=int((S.ncolours == 3).sum()),
        badShareOne=r(one.bad.mean()), badShareThree=r(S[S.ncolours == 3].bad.mean()),
        nBad=int(S.bad.sum()),
        oneScenario=one.scenario.value_counts().to_dict())
    art['oneOddVsClean'] = within_or(one, 'took', 'odd', extra='C(game) + C(run)')
    art['oneVsThreeClean'] = within_or(S[S.odd == 0], 'took', 'threetype')
    for k, v in art.items():
        print('  ', k, v)
    out['artefact'] = art

    # A7 · per person: small vs big (both tiers)
    print('\nA7 per person: hand-over on small vs big jobs')
    pp = []
    for pid, g in S.groupby('pid'):
        a, b_ = g[g.ncolours == 1], g[g.ncolours == 3]
        t = T[T.pid == pid]
        med = T.plan.median()
        ta, tb = t[t.plan <= med], t[t.plan > med]
        pp.append(dict(pid=pid,
                       sA=r(a.took.mean()) if len(a) >= 3 else None, sB=r(b_.took.mean()) if len(b_) >= 3 else None,
                       sNa=int(len(a)), sNb=int(len(b_)),
                       tA=r(ta.consulted.mean()) if len(ta) >= 3 else None,
                       tB=r(tb.consulted.mean()) if len(tb) >= 3 else None,
                       tNa=int(len(ta)), tNb=int(len(tb)), c03=int(pid in who['C03'])))
    PP = pd.DataFrame(pp)
    for a_, b_, lab in (('sA', 'sB', 'strategic'), ('tA', 'tB', 'tactical')):
        d = PP.dropna(subset=[a_, b_])
        up, down, same = int((d[b_] > d[a_]).sum()), int((d[b_] < d[a_]).sum()), int((d[b_] == d[a_]).sum())
        from scipy import stats
        sp = stats.binomtest(up, up + down).pvalue if up + down else None
        print('   %s: %d people with >=3 of each; higher on big jobs %d, lower %d, equal %d; sign test p=%.4f'
              % (lab, len(d), up, down, same, sp))
        out.setdefault('peopleCounts', {})[lab] = dict(n=len(d), up=up, down=down, same=same, p=r(sp, 5),
                                                       medSmall=r(d[a_].median()), medBig=r(d[b_].median()))
    out['tacPlanMedian'] = r(T.plan.median(), 1)
    out['people'] = [{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in rec.items()}
                     for rec in PP.to_dict('records')]

    # A8 · do the people who STATE the rule (C03) apply it more steeply?
    print('\nA8 C03 (state the rule) vs others: size slope')
    for lab, d, y, x in (('strat', S, 'took', 'l2d'), ('tac', T, 'consulted', 'l2plan')):
        d = centre(d.assign(c03=d.pid.isin(who['C03']).astype(int)), x)
        m = gee_fit('%s ~ %s_w * c03 + %s_pm + C(game) + C(run)' % (y, x, x), d)
        t_ = term(m, '%s_w:c03' % x)
        lvl = term(m, 'c03')
        say('   %s: size slope, C03 / others (ratio of ORs)' % lab, t_)
        out.setdefault('c03', {})[lab] = dict(slopeRatio=t_, rateIn=r(d[d.c03 == 1][y].mean()),
                                              rateOut=r(d[d.c03 == 0][y].mean()))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# B · speed by size
# ════════════════════════════════════════════════════════════════════════════════════════════

def section_speed(S, T):
    hdr('B · SPEED BY ROUTE x SIZE')
    out = {}
    S = S.copy()
    S['route'] = np.where(S.took == 1, 'card', np.where(S.early == 1, 'pre-emptive manual', 'manual after cards'))
    S['size'] = np.where(S.ncolours == 1, 'one type', np.where(S.ncolours == 3,
                         np.where(S.ndrones <= 9, 'three types, 6–9 drones', 'three types, 10–18 drones'), None))
    order = ['one type', 'three types, 6–9 drones', 'three types, 10–18 drones']
    st = {}
    for rt in ('card', 'manual after cards', 'pre-emptive manual'):
        st[rt] = boot_median(S[S.route == rt], 'secs', 'size', order)
        for x in st[rt]:
            print('   strategic %-20s %-28s n=%3d  median %.1f s [%.1f, %.1f]' % (rt, x['bin'], x['n'], x['med'], x['lo'], x['hi']))
    out['strat'] = st
    out['revealMean'] = r(S.reveal.mean(), 2)
    # model: log seconds ~ card x three-type, all manual pooled (the decision the operator faces)
    d = S[S.ncolours.isin([1, 3])].copy()
    d['three'] = (d.ncolours == 3).astype(int)
    d = centre(d, 'took')
    mods = {}
    for y, lab in (('lsecs', 'raw'), ('lnet', 'net')):
        m = gee_fit('%s ~ took * three + took_pm + l2d + C(game) + C(run) + emin' % y, d, binomial=False)
        cov = m.cov_params()
        b1, b3 = m.params['took'], m.params['took:three']
        se1 = np.sqrt(cov.loc['took', 'took'])
        se13 = np.sqrt(cov.loc['took', 'took'] + cov.loc['took:three', 'took:three'] + 2 * cov.loc['took', 'took:three'])
        pct = lambda b, s: dict(est=r(np.exp(b) - 1), lo=r(np.exp(b - 1.96 * s) - 1), hi=r(np.exp(b + 1.96 * s) - 1))
        from scipy import stats
        mods[lab] = dict(one=dict(pct(b1, se1), p=r(2 * stats.norm.sf(abs(b1 / se1)), 5)),
                         three=dict(pct(b1 + b3, se13), p=r(2 * stats.norm.sf(abs((b1 + b3) / se13)), 5)),
                         inter=term(m, 'took:three', binomial=False), n=int(len(d)), k=int(d.pid.nunique()))
        print('   %s time, card vs manual: one-type %+.0f%% [%+.0f, %+.0f] p=%.4f; three-type %+.0f%% [%+.0f, %+.0f] p=%.4g; interaction b=%.3f p=%.4g'
              % (lab, 100 * mods[lab]['one']['est'], 100 * mods[lab]['one']['lo'], 100 * mods[lab]['one']['hi'], mods[lab]['one']['p'],
                 100 * mods[lab]['three']['est'], 100 * mods[lab]['three']['lo'], 100 * mods[lab]['three']['hi'], mods[lab]['three']['p'],
                 mods[lab]['inter']['b'], mods[lab]['inter']['p']))
    out['stratModel'] = mods

    # tactical
    T = T.copy()
    T['band'] = pd.qcut(T.plan, 3, labels=['small', 'mid', 'large']).astype(str)
    edges = T.plan.quantile([1 / 3, 2 / 3]).values
    out['tacBandEdges'] = [r(x, 1) for x in edges]
    tt = {}
    for rt in ('hand', 'suggest-kept', 'suggest-edited'):
        tt[rt] = boot_median(T[T.route == rt], 'secs', 'band', ['small', 'mid', 'large'])
        for x in tt[rt]:
            print('   tactical %-15s %-6s n=%3d  median %.1f s [%.1f, %.1f]' % (rt, x['bin'], x['n'], x['med'], x['lo'], x['hi']))
    out['tac'] = tt
    d = T[T.route != 'suggest-edited'].copy()
    d['kept'] = (d.route == 'suggest-kept').astype(int)
    d = centre(d, 'kept')
    d['lplan_c'] = np.log(d.plan) - np.log(d.plan).mean()
    m = gee_fit('lsecs ~ kept_w + kept_pm + np.log(plan) + C(game) + C(run)', d, binomial=False)
    k = term(m, 'kept_w', binomial=False)
    out['tacKept'] = dict(pct=r(np.exp(k['b']) - 1), lo=r(np.exp(k['b'] - 1.96 * k['se']) - 1),
                          hi=r(np.exp(k['b'] + 1.96 * k['se']) - 1), p=k['p'], n=int(len(d)), k=int(d.pid.nunique()))
    print('   tactical kept Suggest vs hand, within person, plan size held: %+.0f%% [%+.0f, %+.0f] p=%.4f'
          % (100 * out['tacKept']['pct'], 100 * out['tacKept']['lo'], 100 * out['tacKept']['hi'], k['p']))
    m = gee_fit('lsecs ~ kept_w * lplan_c + kept_pm + C(game) + C(run)', d, binomial=False)
    out['tacInter'] = term(m, 'kept_w:lplan_c', binomial=False)
    print('   kept x log plan size interaction b=%.3f [%.3f, %.3f] p=%.4f'
          % (out['tacInter']['b'], out['tacInter']['lo'], out['tacInter']['hi'], out['tacInter']['p']))
    out['entriesMedian'] = r(T[T.consulted == 1].entries.median(), 1)
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# C · parallel work during the Suggest fill
# ════════════════════════════════════════════════════════════════════════════════════════════

def section_parallel(S, T):
    hdr('C · PARALLEL WORK WHILE A PLAN FILLS')
    T = T.copy()
    T['inter'] = (T.interleaved > 0).astype(int)
    fill_open, any_fill = [], []
    for x, raw in zip(T.itertuples(), T['_raw']):
        if raw is None or not x.consulted:
            fill_open.append(np.nan)
            continue
        win = [(s, s + x.entries * 1000.0) for s in raw['sugg']]
        n = sum(any(a <= o <= b for a, b in win) for o in raw['opens'])
        fill_open.append(int(n > 0))
    T['duringFill'] = fill_open
    T['allocOther'] = [int(len(raw['choices']) > 0) if raw else np.nan for raw in T['_raw']]
    out = dict(n=int(len(T)), nSuggest=int(T.consulted.sum()), nHand=int((T.consulted == 0).sum()))
    out['rateSuggest'] = r(T[T.consulted == 1].inter.mean())
    out['rateHand'] = r(T[T.consulted == 0].inter.mean())
    out['rateDuringFill'] = r(T[T.consulted == 1].duringFill.mean())
    out['allocSuggest'] = r(T[T.consulted == 1].allocOther.mean())
    out['allocHand'] = r(T[T.consulted == 0].allocOther.mean())
    print('  another mission actually ALLOCATED (strategic choice made) before confirming: Suggest %.0f%%, hand %.0f%%'
          % (100 * out['allocSuggest'], 100 * out['allocHand']))
    out['fillSecsMedian'] = r(T[T.consulted == 1].entries.median(), 1)
    out['openSecsMedian'] = dict(suggest=r(T[T.consulted == 1].secs.median(), 1), hand=r(T[T.consulted == 0].secs.median(), 1))
    print('  plans %d (Suggest %d, hand %d). Another strategic panel opened before confirming: Suggest %.0f%%, hand %.0f%%'
          % (out['n'], out['nSuggest'], out['nHand'], 100 * out['rateSuggest'], 100 * out['rateHand']))
    print('  ...of which during the fill window itself (Suggest plans): %.0f%%; median fill %.0f s'
          % (100 * out['rateDuringFill'], out['fillSecsMedian']))
    # the round-1 model, re-run
    T['llat'] = np.log(T.secs.clip(lower=0.5))
    T['lplan'] = np.log(T.plan.clip(lower=1))
    d = centre(T, 'consulted')
    m = gee_fit('inter ~ consulted_w + consulted_pm + lplan + llat + C(scenario) + C(run)', d)
    out['orRound1'] = dict(term(m, 'consulted_w'), n=int(len(d)), k=int(d.pid.nunique()))
    say('round-1 spec: interleave ~ Suggest (within), log plan, log open time, scenario, run', out['orRound1'])
    specs = []

    def add(label, t, note=''):
        if t is not None:
            specs.append(dict(label=label, note=note, **t))
        say(label, t)

    add('Round-1 specification (as reported)', out['orRound1'])
    d2 = centre(T, 'consulted')
    m = gee_fit('inter ~ consulted_w + consulted_pm + lplan + C(scenario) + C(run)', d2)
    add('Without holding open time fixed', dict(term(m, 'consulted_w'), n=int(len(d2)), k=int(d2.pid.nunique())))
    m = gee_fit('inter ~ consulted_w + consulted_pm + lplan + llat + st_queued + C(game) + C(run)', d2)
    add('Missions waiting at open held fixed; game not scenario', dict(term(m, 'consulted_w'), n=int(len(d2)), k=int(d2.pid.nunique())))
    w = T[T.st_queued >= 1]
    d3 = centre(w, 'consulted')
    m = gee_fit('inter ~ consulted_w + consulted_pm + lplan + llat + C(game) + C(run)', d3)
    add('Only plans opened with ≥1 mission waiting', dict(term(m, 'consulted_w'), n=int(len(d3)), k=int(d3.pid.nunique())),
        'nothing to start otherwise')
    d4 = centre(T[T.route != 'suggest-edited'], 'consulted')
    m = gee_fit('inter ~ consulted_w + consulted_pm + lplan + llat + C(game) + C(run)', d4)
    add('Edited Suggest plans dropped', dict(term(m, 'consulted_w'), n=int(len(d4)), k=int(d4.pid.nunique())))
    d5 = centre(T, 'consulted')
    m = gee_fit('allocOther ~ consulted_w + consulted_pm + lplan + llat + C(scenario) + C(run)', d5)
    add('Outcome = another mission actually allocated', dict(term(m, 'consulted_w'), n=int(len(d5)), k=int(d5.pid.nunique())),
        'a strategic choice made, not just the panel opened')
    out['specs'] = specs
    # time-matched view: % interleaved by how long the planner was open
    T['openband'] = pd.cut(T.secs, [0, 15, 25, 40, 1e9], labels=['<15 s', '15–25 s', '25–40 s', '>40 s']).astype(str)
    tm = {}
    for c, lab in ((1, 'suggest'), (0, 'hand')):
        tm[lab] = boot_rate(T[T.consulted == c], 'inter', 'openband', ['<15 s', '15–25 s', '25–40 s', '>40 s'])
        print('  ', lab, [(x['bin'], x['n'], x['rate']) for x in tm[lab]])
    out['timeMatched'] = tm
    out['waiting'] = dict(suggest=r(w[w.consulted == 1].inter.mean()), hand=r(w[w.consulted == 0].inter.mean()),
                          nS=int((w.consulted == 1).sum()), nH=int((w.consulted == 0).sum()))
    print('  only with >=1 waiting: Suggest %.0f%% (n=%d) vs hand %.0f%% (n=%d)'
          % (100 * out['waiting']['suggest'], out['waiting']['nS'], 100 * out['waiting']['hand'], out['waiting']['nH']))
    # overall bars with CIs
    T['routeLab'] = np.where(T.consulted == 1, 'suggest', 'hand')
    out['overall'] = boot_rate(T, 'inter', 'routeLab', ['hand', 'suggest'])
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# per-person table (used by D and E)
# ════════════════════════════════════════════════════════════════════════════════════════════

def person_table(S, T, P):
    rows = []
    med = T.plan.median()
    for pid in sorted(S.pid.unique()):
        s, t, p = S[S.pid == pid], T[T.pid == pid], P[P.pid == pid]
        a, b_ = s[s.ncolours == 1], s[s.ncolours == 3]
        ta, tb = t[t.plan <= med], t[t.plan > med]
        rows.append(dict(
            pid=pid, took=s.took.mean(), suggest=t.consulted.mean() if len(t) else np.nan,
            kept=t[t.consulted == 1].unmod.mean() if (t.consulted == 1).any() else np.nan,
            zgame=p.zgame.mean(), stratSecs=s.secs.median(), tacSecs=t.secs.median() if len(t) else np.nan,
            stratNet=s.net.median(), tacNet=t.net.median() if len(t) else np.nan,
            preempt=s.early.mean(), decisions=len(s) / max(1, s.run.nunique()),
            sGap=(b_.took.mean() - a.took.mean()) if len(a) >= 3 and len(b_) >= 3 else np.nan,
            tGap=(tb.consulted.mean() - ta.consulted.mean()) if len(ta) >= 3 and len(tb) >= 3 else np.nan,
            cardSecs3=b_[b_.took == 1].secs.median() if (b_.took == 1).any() else np.nan,
            cardSecs1=a[a.took == 1].secs.median() if (a.took == 1).any() else np.nan))
    return pd.DataFrame(rows).set_index('pid')


PROFILE = [('took', 'Strategy cards taken', 'pct'), ('suggest', 'Plans with Suggest pressed', 'pct'),
           ('kept', 'Suggest plans kept unedited', 'pct'),
           ('preempt', 'Decided before the cards loaded', 'pct'),
           ('sGap', 'Card uptake: three-type minus one-type', 'pp'),
           ('tGap', 'Suggest: big minus small plans', 'pp'),
           ('stratSecs', 'Seconds per strategic decision (median)', 's'),
           ('tacSecs', 'Seconds per tactical plan (median)', 's'),
           ('decisions', 'Strategic decisions per session', 'n'),
           ('zgame', 'Score within game (SD units)', 'z')]


def section_c06(PT, who):
    hdr('D · C06 "the assistant is slow": who, and their numbers')
    grp = who['C06']
    print('  C06:', grp)
    rows = []
    for k, lab, unit in PROFILE:
        t = perm_diff(PT[k], grp)
        rows.append(dict(key=k, label=lab, unit=unit, **t))
        print('   %-45s C06 %s  others %s  diff %s  p=%s' % (lab, t['inMean'], t['restMean'], t['diff'], t['p']))
    people = {pid: {k: r(PT.loc[pid, k]) for k, _, _ in PROFILE} for pid in PT.index}
    return dict(who=grp, rows=rows, people=people)


# ════════════════════════════════════════════════════════════════════════════════════════════
# E · learning
# ════════════════════════════════════════════════════════════════════════════════════════════

def section_learning(S, T, PT, P, who):
    hdr('E · LEARNING')
    out = {}
    S = S.copy()
    T = T.copy()
    S['minute'] = np.minimum(np.floor(S.elapsed_open / 60).astype(int) + 1, 8)
    T['minute'] = np.minimum(np.floor(T.elapsed_open / 60).astype(int) + 1, 8)
    curves = {}
    for lab, d in (('strat', S), ('tac', T)):
        for run in (1, 2):
            curves['%s%d' % (lab, run)] = boot_median(d[d.run == run], 'net', 'minute', list(range(1, 9)), B=600)
    out['curves'] = curves
    # models
    m = gee_fit('lnet ~ emin + run2 + took + threetype + l2d + C(scenario)', S, binomial=False)
    sm_ = term(m, 'emin', binomial=False)
    sr_ = term(m, 'run2', binomial=False)
    m = gee_fit('lnet ~ emin + run2 + consulted + np.log(plan) + C(scenario)', T, binomial=False)
    tm_ = term(m, 'emin', binomial=False)
    tr_ = term(m, 'run2', binomial=False)
    pc = lambda t, k=1: dict(pct=r(np.exp(t['b'] * k) - 1), lo=r(np.exp((t['b'] - 1.96 * t['se']) * k) - 1),
                             hi=r(np.exp((t['b'] + 1.96 * t['se']) * k) - 1), p=t['p'], b=t['b'])
    out['models'] = dict(stratMinute=pc(sm_), stratOver8=pc(sm_, 8), stratRun2=pc(sr_),
                         tacMinute=pc(tm_), tacOver8=pc(tm_, 8), tacRun2=pc(tr_),
                         nS=int(len(S)), nT=int(len(T)), k=int(S.pid.nunique()))
    for k, v in out['models'].items():
        if isinstance(v, dict):
            print('   %-12s %+.1f%% [%+.1f, %+.1f] p=%.5f' % (k, 100 * v['pct'], 100 * v['lo'], 100 * v['hi'], v['p']))
    # calibration: does the size gap widen in session 2?
    print('\n  calibration: size gap by session')
    gap = {}
    for lab, d, y, flag in (('strat', S[S.ncolours.isin([1, 3])], 'took', 'threetype'),
                            ('tac', T.assign(big=(T.plan > T.plan.median()).astype(int)), 'consulted', 'big')):
        for run in (1, 2):
            g = d[d.run == run]
            # per-person sums, people resampled
            agg = g.groupby(['pid', flag])[y].agg(['sum', 'size']).unstack(fill_value=0)
            sA, nA = agg[('sum', 1)].values, agg[('size', 1)].values
            s0, n0 = agg[('sum', 0)].values, agg[('size', 0)].values
            draw = RNG.integers(0, len(agg), (B_BOOT, len(agg)))
            bs = sA[draw].sum(1) / nA[draw].sum(1) - s0[draw].sum(1) / n0[draw].sum(1)
            est = sA.sum() / nA.sum() - s0.sum() / n0.sum()
            gap['%s%d' % (lab, run)] = dict(gap=r(est), lo=r(np.nanpercentile(bs, 2.5)), hi=r(np.nanpercentile(bs, 97.5)),
                                            big=r(sA.sum() / nA.sum()), small=r(s0.sum() / n0.sum()),
                                            nBig=int(nA.sum()), nSmall=int(n0.sum()), k=int(len(agg)))
            print('   %s run %d: big %.2f (n=%d) small %.2f (n=%d) gap %+.2f [%+.2f, %+.2f]'
                  % (lab, run, gap['%s%d' % (lab, run)]['big'], nA.sum(), gap['%s%d' % (lab, run)]['small'], n0.sum(),
                     est, gap['%s%d' % (lab, run)]['lo'], gap['%s%d' % (lab, run)]['hi']))
    out['gap'] = gap
    inter = {}
    m = gee_fit('took ~ threetype * run2 + l2d + C(scenario)', S[S.ncolours.isin([1, 3])])
    inter['strat'] = term(m, 'threetype:run2')
    m = gee_fit('took ~ threetype * run2 + l2d + C(game)', S[S.ncolours.isin([1, 3]) & (S.scenario == 'strategic')])
    inter['stratSH'] = term(m, 'threetype:run2')
    m = gee_fit('consulted ~ l2plan * run2 + C(scenario)', T)
    inter['tac'] = term(m, 'l2plan:run2')
    # within-session sharpening: size x minute
    m = gee_fit('took ~ l2d * emin + C(game) + C(run)', S)
    inter['stratMinute'] = term(m, 'l2d:emin')
    m = gee_fit('consulted ~ l2plan * emin + C(game) + C(run)', T)
    inter['tacMinute'] = term(m, 'l2plan:emin')
    for k, v in inter.items():
        say('   size x %s (ratio of ORs; >1 = rule sharpens)' % k, v)
    out['inter'] = inter
    # C22: did the people who say they got better speed up / score up more?
    print('\n  C22 vs logs')
    rows = []
    for pid in sorted(S.pid.unique()):
        s, t = S[S.pid == pid], T[T.pid == pid]
        p = P[P.pid == pid].set_index('run')
        if not ({1, 2} <= set(s.run)):
            continue
        rows.append(dict(pid=pid,
                         dS=np.log(s[s.run == 2].net.median()) - np.log(s[s.run == 1].net.median()),
                         dT=(np.log(t[t.run == 2].net.median()) - np.log(t[t.run == 1].net.median()))
                         if ({1, 2} <= set(t.run)) else np.nan,
                         dZ=(p.zgame.get(2, np.nan) - p.zgame.get(1, np.nan)),
                         c22=int(pid in who['C22'])))
    C = pd.DataFrame(rows).set_index('pid')
    c22 = {}
    for k, lab in (('dS', 'strategic decision time, session 2 vs 1 (log)'), ('dT', 'tactical plan time (log)'),
                   ('dZ', 'score within game, change (SD)')):
        t = perm_diff(C[k], who['C22'])
        c22[k] = dict(label=lab, **t)
        print('   %-48s C22 %s others %s p=%s' % (lab, t['inMean'], t['restMean'], t['p']))
    c22['fasterS'] = dict(c22=int((C[C.c22 == 1].dS < 0).sum()), others=int((C[C.c22 == 0].dS < 0).sum()),
                          nC22=int((C.c22 == 1).sum()), nOthers=int((C.c22 == 0).sum()))
    c22['fasterT'] = dict(c22=int((C[C.c22 == 1].dT < 0).sum()), others=int((C[C.c22 == 0].dT < 0).sum()))
    c22['scoreUp'] = dict(c22=int((C[C.c22 == 1].dZ > 0).sum()), others=int((C[C.c22 == 0].dZ > 0).sum()))
    print('   faster strategic: C22 %d/%d, others %d/%d; faster tactical C22 %d, others %d; score up C22 %d, others %d'
          % (c22['fasterS']['c22'], c22['fasterS']['nC22'], c22['fasterS']['others'], c22['fasterS']['nOthers'],
             c22['fasterT']['c22'], c22['fasterT']['others'], c22['scoreUp']['c22'], c22['scoreUp']['others']))
    c22['people'] = {pid: dict(dS=r(row.dS), dT=r(row.dT), dZ=r(row.dZ), c22=int(row.c22)) for pid, row in C.iterrows()}
    c22['who'] = who['C22']
    out['c22'] = c22
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# F · manual allocations around the cards
# ════════════════════════════════════════════════════════════════════════════════════════════

def section_manual(S, who):
    hdr('F · MANUAL ALLOCATIONS AROUND THE CARDS')
    M = S[S.manual == 1].copy()
    M['kind'] = np.where(M.early == 1, 'pre-emptive', np.where(M.edited == 1, 'edited a card', 'built after seeing cards'))
    M['dCons'] = M.committed - M.cons_total
    M['dAggr'] = M.committed - M.aggr_total
    M['dNeed'] = M.committed - M.ndrones
    # the Conservative card's spare drones of types the mission does not need, split off
    nn, un = [], []
    for g in M._g:
        need, cons, ch = g['need'], g['cons'], g['chosen']
        nn.append(sum(ch.get(c, 0) - cons.get(c, 0) for c in cons if need.get(c, 0) > 0))
        un.append(sum(ch.get(c, 0) - cons.get(c, 0) for c in cons if need.get(c, 0) == 0))
    M['dConsNeeded'], M['dConsUnneeded'] = nn, un
    M['consNeeded'] = [sum(v for c, v in g['cons'].items() if g['need'].get(c, 0) > 0) for g in M._g]
    M['gotNeeded'] = [sum(v for c, v in g['chosen'].items() if g['need'].get(c, 0) > 0) for g in M._g]
    lo, hi = np.minimum(M.cons_total, M.aggr_total), np.maximum(M.cons_total, M.aggr_total)
    M['pos'] = np.select([M.committed < lo, M.committed > hi, (M.committed == M.cons_total) | (M.committed == M.aggr_total)],
                         ['below both', 'above both', 'equals a card'], 'strictly between')
    M['sizeband'] = np.where(M.ncolours == 1, 'one type', np.where(M.ndrones <= 9, 'three types, ≤9', 'three types, 10+'))
    M.loc[M.ncolours == 2, 'sizeband'] = 'two types'
    print('  manual decisions:', len(M), M.kind.value_counts().to_dict())
    pos = (M.groupby(['kind', 'pos']).size().unstack(fill_value=0))
    print(pos)
    print(M.groupby(['sizeband', 'kind']).dCons.agg(['size', 'mean', 'median']).round(2))
    print('  needed-type vs unneeded-type part of the gap to Conservative, by size band:')
    print(M.groupby('sizeband')[['dCons', 'dConsNeeded', 'dConsUnneeded', 'dNeed']].mean().round(2))
    dots = [dict(pid=x.pid, nd=int(x.ndrones), nc=int(x.ncolours), d=int(x.dCons), dn=int(x.dConsNeeded),
                 du=int(x.dConsUnneeded), dA=int(x.dAggr), kind=x.kind, cons=int(x.cons_total), aggr=int(x.aggr_total),
                 got=int(x.committed), odd=int(x.odd), pos=x.pos) for x in M.itertuples()]
    bands = []
    for (sb, kind), g in M.groupby(['sizeband', 'kind']):
        bands.append(dict(band=sb, kind=kind, n=int(len(g)), k=int(g.pid.nunique()),
                          mean=r(g.dCons.mean(), 2), med=r(g.dCons.median(), 2),
                          meanNeeded=r(g.dConsNeeded.mean(), 2), meanUnneeded=r(g.dConsUnneeded.mean(), 2)))
    posTab = []
    for kind, g in M.groupby('kind'):
        vc = g.pos.value_counts()
        posTab.append(dict(kind=kind, n=int(len(g)), **{k: int(vc.get(k, 0)) for k in
                                                        ('below both', 'equals a card', 'strictly between', 'above both')}))
    posAll = M.pos.value_counts().to_dict()
    # does the card's number predict the manual number beyond the mission's need? (seen vs not seen)
    tests = {}
    for lab, g in (('seen', M[M.early == 0]), ('seenOwn', M[M.kind == 'built after seeing cards']),
                   ('edited', M[M.kind == 'edited a card']), ('preempt', M[M.early == 1])):
        for f, key in (('committed ~ cons_total + ndrones + C(ncolours)', 'cons_total'),
                       ('gotNeeded ~ consNeeded + ndrones + C(ncolours)', 'consNeeded')):
            try:
                m = gee_fit(f, g, binomial=False)
                k_ = lab + ('' if key == 'cons_total' else 'Needed')
                tests[k_] = dict(term(m, key, binomial=False), n=int(len(g)), k=int(g.pid.nunique()))
                say('   %s (| need, types), %s' % (f.split('+')[0], lab), tests[k_], unit='b')
            except Exception as ex:
                print('   fit failed', lab, key, ex)
    # variation in the card total beyond what need predicts (if ~0 the test above has nothing to work with)
    res = smf.ols('cons_total ~ ndrones + C(ncolours)', S).fit()
    tests['consResidSD'] = r(np.sqrt(res.mse_resid), 3)
    tests['consR2'] = r(res.rsquared, 3)
    print('   Conservative total explained by need + types: R2=%.3f, residual SD %.2f drones' % (res.rsquared, np.sqrt(res.mse_resid)))
    # by-size slope, after cards seen: dCons ~ l2d, within person
    t = within_or(M[M.early == 0], 'dCons', 'l2d', binomial=False)
    tests['sizeSlopeSeen'] = t
    say('   manual minus Conservative ~ doubling of drones (after seeing cards, within person)', t, unit='b')
    t = within_or(M[M.early == 1], 'dCons', 'l2d', binomial=False)
    tests['sizeSlopePre'] = t
    say('   same, pre-emptive', t, unit='b')
    t = within_or(M[M.early == 0], 'dConsNeeded', 'l2d', binomial=False)
    tests['sizeSlopeSeenNeeded'] = t
    say('   needed-types part only, after seeing cards', t, unit='b')
    # who holds the codes: their manual numbers
    codes = {}
    for c in ('C07', 'C08', 'C09', 'C10'):
        g = M[M.pid.isin(who[c])]
        codes[c] = dict(who=who[c], nManual=int(len(g)), k=int(g.pid.nunique()),
                        meanD=r(g.dCons.mean(), 2), meanDNeeded=r(g.dConsNeeded.mean(), 2),
                        between=r((g.pos == 'strictly between').mean()) if len(g) else None,
                        edited=int((g.kind == 'edited a card').sum()))
        print('  ', c, codes[c])
    return dict(n=int(len(M)), kinds=M.kind.value_counts().to_dict(), dots=dots, bands=bands, pos=posTab,
                posAll=posAll, tests=tests, codes=codes,
                overall=dict(mean=r(M.dCons.mean(), 2), meanNeeded=r(M.dConsNeeded.mean(), 2),
                             meanUnneeded=r(M.dConsUnneeded.mean(), 2)))


# ════════════════════════════════════════════════════════════════════════════════════════════

def clean(o):
    """NaN/inf -> null everywhere, numpy scalars -> Python."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if hasattr(o, 'item') and not isinstance(o, (str, bytes)):
        o = o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def main():
    S, T, P, who = load()
    out = dict(meta=dict(seed=SEED, nPeople=int(S.pid.nunique()), nStrat=int(len(S)), nTac=int(len(T)),
                         boot=B_BOOT, script='scripts/register/pass2/handover.py'))
    out['size'] = section_size(S, T, who)
    out['speed'] = section_speed(S, T)
    out['parallel'] = section_parallel(S, T)
    PT = person_table(S, T, P)
    out['c06'] = section_c06(PT, who)
    out['learn'] = section_learning(S, T, PT, P, who)
    out['manual'] = section_manual(S, who)
    out['who'] = {c: who[c] for c in ('C03', 'C04', 'C05', 'C06', 'C07', 'C08', 'C09', 'C10', 'C22')}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(clean(out), ensure_ascii=False, allow_nan=False, separators=(',', ':'), default=lambda o: o.item()
                              if hasattr(o, 'item') else str(o)), encoding='utf-8')
    print('\nwrote', OUT.relative_to(BASE), '(%.0f kB)' % (OUT.stat().st_size / 1024))


if __name__ == '__main__':
    main()
