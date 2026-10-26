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
G · PASS 3 (written under `p3`; earlier keys unchanged). The researcher's pass-2 notes: why 5-drone missions
    dip; mission-shared intervals (person + mission clusters); the tactical tier under five size measures x the
    strategic route; person-level bars; spread of the quick pre-emptive decisions; a tactical plan split into
    phases (before first action / building / ready -> confirm / carrying out); C06 group means with intervals;
    whether the within-session speed-up carries over; C22's change in assistant use.
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

MISSION = {}   # (pid, run, missionId) -> task composition, arrival, completion (filled by raw_pass)


def raw_pass():
    """Per strategic choice: the cards shown at the last open (true asset counts per colour, whether a
    card was an ε-corrupted one), the operator's chosen counts, the mission's per-colour need.
    Per tactical planner: Suggest press times and strategic-panel opens for OTHER missions while open."""
    strat, tac = {}, {}
    MISSION.clear()
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
            need, last_open, open_tac, sacts = {}, {}, {}, {}
            for e in evs:
                t, m, ts = e['type'], e.get('missionId'), e.get('timestamp')
                if t == 'mission_arrived':
                    tot = {'Blue': 0, 'Red': 0, 'Green': 0}
                    for task in e.get('tasks', []):
                        for c, n in primary[str(task['type'])].items():
                            tot[c] += n
                    need[m] = tot
                    MISSION[(pid, run, m)] = dict(
                        comp='+'.join(sorted('T%s' % task['type'] for task in e.get('tasks', []))),
                        arrived=ts, done=None, outcome=None, failures=None, nd=sum(tot.values()),
                        nc=sum(1 for v in tot.values() if v > 0), residual=bool(e.get('isResidual') or str(m).endswith('-R')))
                elif t == 'mission_completed' and (pid, run, m) in MISSION:
                    MISSION[(pid, run, m)].update(done=ts, outcome=e.get('outcome'),
                                                  failures=e.get('droneFailureCount'))
                elif t == 'strategic_modal_opened':
                    for om, rec in open_tac.items():
                        if om != m:
                            rec['opens'].append(ts)
                    cards = {c['name']: c for c in e.get('strategiesPresented', [])}
                    sacts[m] = []
                    if len(cards) >= 2:
                        last_open[m] = cards
                elif t in ('strategic_card_previewed', 'manual_allocation_edited') and m in sacts:
                    sacts[m].append(ts)
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
                        need=need.get(m, {}), acts=list(sacts.get(m, [])))
                elif t == 'tactical_opened':
                    open_tac[m] = dict(open=ts, sugg=[], opens=[], choices=[], drags=[])
                elif t == 'tactical_suggest_used' and not e.get('recoveryMode') and m in open_tac:
                    open_tac[m]['sugg'].append(ts)
                elif t == 'tactical_assignment_changed' and not e.get('recoveryMode') and m in open_tac:
                    open_tac[m]['drags'].append(ts)
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
# G · pass 3 — the researcher's pass-2 notes (docs/analysis/register/passes/pass2.json)
# ════════════════════════════════════════════════════════════════════════════════════════════

def wilson(k, n, z=1.96):
    if not n:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    hw = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return r(c - hw), r(c + hw)


def gee_terms(d, formula, names, binomial=True):
    """Fit a person-clustered GEE and return the named terms (odds ratios if binomial)."""
    try:
        m = gee_fit(formula, d, binomial)
    except Exception as ex:
        print('   fit failed: %s (%s)' % (formula, ex))
        return {k: None for k in names}
    return {k: dict(term(m, k, binomial), n=int(len(d)), k=int(d.pid.nunique())) for k in names}


def boot_mean_people(vals, B=B_BOOT):
    """Mean of per-person values (each person counts once), 95% interval from resampling people."""
    v = np.array([x for x in vals if x is not None and np.isfinite(x)], dtype=float)
    if len(v) < 2:
        return dict(mean=r(v.mean()) if len(v) else None, lo=None, hi=None, k=int(len(v)))
    draw = RNG.integers(0, len(v), (B, len(v)))
    bs = v[draw].mean(1)
    return dict(mean=r(v.mean()), lo=r(np.percentile(bs, 2.5)), hi=r(np.percentile(bs, 97.5)), k=int(len(v)))


def boot_seg_means(d, cols, B=B_BOOT, rng=None):
    """Mean of each column over rows, 95% interval from resampling PEOPLE (rows travel with their person)."""
    people = sorted(d.pid.unique())
    groups = [d[d.pid == p_] for p_ in people]
    sums = np.array([[g[c].sum() for c in cols] for g in groups])
    ns = np.array([len(g) for g in groups])
    draw = (rng or RNG).integers(0, len(people), (B, len(people)))
    bs = sums[draw].sum(1) / ns[draw].sum(1)[:, None]
    return {c: dict(mean=r(d[c].mean(), 2), lo=r(np.percentile(bs[:, j], 2.5), 2), hi=r(np.percentile(bs[:, j], 97.5), 2))
            for j, c in enumerate(cols)}


STORE = {}   # pass-3 frames handed on to pass 4
TEAMBIN = [(1, 3, '1–3'), (4, 5, '4–5'), (6, 7, '6–7'), (8, 9, '8–9'), (10, 99, '10+')]
PEOPLEBAND = [(0, 5, '≤5'), (6, 6, '6'), (7, 9, '7–9'), (10, 18, '10–18')]


def section_pass3(S, T, P, PT, who):
    from scipy import stats
    hdr('G · PASS 3: the pass-2 notes')
    out = {}
    S = S.copy()
    T = T.copy()
    S['comp'] = [MISSION.get((a, b_, c), {}).get('comp') for a, b_, c in zip(S.pid, S.run, S.missionId)]
    S['mkey'] = S.game + '|' + S.missionId
    T['mkey'] = T.game + '|' + T.missionId
    T['card'] = (T.strategy != 'Manual').astype(int)
    T['cbin'] = T.ndrones.map(lambda v: binof(v, CBIN))
    T['pbin'] = T.plan.map(lambda v: binof(v, PBIN))
    T['tbin'] = T.pool.map(lambda v: binof(v, TEAMBIN))
    T['l2pool'] = np.log2(T.pool.clip(lower=1))

    # ── G1 · why the 5-drone missions dip (f-size-decides#strategic-steps) ──────────────────────
    print('\nG1 one-type missions of 3, 5 and 6 drones: what differs')
    o = S[(S.ncolours == 1) & S.ndrones.isin([3, 5, 6])].copy()
    o['minute'] = o.emin
    per = []
    for (nd, comp, game, mid), g in o.groupby(['ndrones', 'comp', 'game', 'missionId']):
        kt, ke, n = int(g.took.sum()), int(g.early.sum()), len(g)
        lo, hi = wilson(kt, n)
        elo, ehi = wilson(ke, n)
        per.append(dict(nd=int(nd), comp=comp, game=game, mission=mid, n=n, k=int(g.pid.nunique()),
                        took=r(kt / n), lo=lo, hi=hi, early=r(ke / n), elo=elo, ehi=ehi,
                        minute=r(g.minute.mean(), 2), queue=r(g.q.mean(), 2), secs=r(g.secs.median(), 1),
                        resid=int(g.residual.max())))
    per.sort(key=lambda x: (x['nd'], x['minute']))
    for x in per:
        print('   %2d %-12s %-12s %-7s n=%2d card %.2f [%.2f,%.2f] early %.2f  minute %.1f  waiting %.1f  %.1f s'
              % (x['nd'], x['comp'], x['game'], x['mission'], x['n'], x['took'], x['lo'], x['hi'], x['early'],
                 x['minute'], x['queue'], x['secs']))
    grp = []
    for nd, g in o.groupby('ndrones'):
        cons_b = np.mean([gg['cons'].get('Blue', 0) for gg in g._g])
        aggr_b = np.mean([gg['aggr'].get('Blue', 0) for gg in g._g])
        grp.append(dict(nd=int(nd), n=int(len(g)), missions=int(g.mkey.nunique()), comps=sorted(g.comp.dropna().unique().tolist()),
                        games=g.game.value_counts().to_dict(), took=r(g.took.mean()), early=r(g.early.mean()),
                        minute=r(g.minute.mean(), 2), queue=r(g.q.mean(), 2), busy=r((g.q >= 3).mean()),
                        secs=r(g.secs.median(), 1), consBlue=r(cons_b, 2), aggrBlue=r(aggr_b, 2), odd=r(g.odd.mean())))
        print('   %d drones: %s' % (nd, grp[-1]))
    o['five'] = (o.ndrones == 5).astype(float)
    o['six'] = (o.ndrones == 6).astype(float)
    for v in ('five', 'six'):
        o = centre(o, v)
    o['busy'] = (o.q >= 3).astype(int)
    fm = {}
    fm['took'] = gee_terms(o, 'took ~ five_w + six_w + five_pm + six_pm + C(game) + C(run)', ['five_w', 'six_w'])
    fm['tookQ'] = gee_terms(o, 'took ~ five_w + six_w + five_pm + six_pm + q + emin + C(game) + C(run)', ['five_w', 'six_w', 'q'])
    fm['early'] = gee_terms(o, 'early ~ five_w + six_w + five_pm + six_pm + C(game) + C(run)', ['five_w', 'six_w'])
    fm['earlyQ'] = gee_terms(o, 'early ~ five_w + six_w + five_pm + six_pm + q + emin + C(game) + C(run)', ['five_w', 'six_w', 'q'])
    for k, v in fm.items():
        for kk, t in v.items():
            say('   %s: %s (vs 3-drone, within person, game + session fixed)' % (k, kk), t)
    # 5-drone missions split by how busy the operator was
    f5 = o[o.ndrones == 5]
    busy = {}
    for b_, lab in ((0, 'calm'), (1, 'busy')):
        g = f5[f5.busy == b_]
        busy[lab] = dict(n=int(len(g)), took=r(g.took.mean()), early=r(g.early.mean()), k=int(g.pid.nunique()))
    allb = {}
    for b_, lab in ((0, 'calm'), (1, 'busy')):
        g = S[(S.q >= 3) == bool(b_)]
        allb[lab] = dict(n=int(len(g)), took=r(g.took.mean()), early=r(g.early.mean()))
    print('   5-drone missions, <3 vs >=3 waiting:', busy, ' all decisions:', allb)
    out['five'] = dict(per=per, groups=grp, models=fm, busy5=busy, busyAll=allb,
                       nMissionsByBin={str(k): int(v) for k, v in S.groupby('ndrones').mkey.nunique().items()})

    # ── G2 · mission-level checks for the models chart (f-size-decides#models + #artefacts) ──────
    print('\nG2 shared missions: the within-person model with intervals clustered on person AND mission')
    # Everyone played the same fixed missions, so decisions on one mission are not independent across people.
    # Same within/between split as the main model; logistic fit, standard errors clustered two ways
    # (person and mission), so neither a heavy user nor an odd mission can make the interval look tight.

    def twoway(d, y, x):
        d = centre(d.dropna(subset=[y, x]).copy(), x)
        f = '%s ~ %s_w + %s_pm + C(game) + C(run)' % (y, x, x)
        try:
            m = smf.glm(f, d, family=sm.families.Binomial()).fit(
                cov_type='cluster', cov_kwds={'groups': np.column_stack([pd.factorize(d.pid)[0], pd.factorize(d.mkey)[0]])})
            return dict(term(m, x + '_w'), n=int(len(d)), k=int(d.pid.nunique()), missions=int(d.mkey.nunique()))
        except Exception as ex:
            print('   two-way fit failed', f, ex)
            return None
    mc = {}
    mc['s'] = twoway(S, 'took', 'l2d'); say('strategic, per doubling of drones, person + mission clusters', mc['s'])
    mc['t'] = twoway(T[T.ndrones > 0], 'consulted', 'l2d'); say('tactical, per doubling of drones needed, person + mission clusters', mc['t'])
    mc['tPlan'] = twoway(T, 'consulted', 'l2plan'); say('tactical, per doubling of plan, person + mission clusters', mc['tPlan'])
    # mission-level: one row per mission (game x mission), the share handed over
    ml = {}
    for lab, d, y in (('s', S, 'took'), ('t', T[T.ndrones > 0], 'consulted')):
        g = d.groupby('mkey').agg(rate=(y, 'mean'), n=(y, 'size'), l2d=('l2d', 'first'), game=('game', 'first')).reset_index()
        g = g[g.n >= 5]
        rho, pv = stats.spearmanr(g.l2d, g.rate)
        ml[lab] = dict(missions=int(len(g)), rho=r(rho), p=r(pv, 5), decisions=int(g.n.sum()))
        print('   %s: %d missions with >=5 decisions, Spearman rho(size, hand-over share) = %.2f, p = %.4f' % (lab, len(g), rho, pv))
    out['missionChecks'] = dict(fe=mc, missionLevel=ml)

    # ── G3 · tactical tier under five size measures, split by strategic route (f-size-decides#tactical) ──
    print('\nG3 tactical: Suggest by size measure x strategic route')
    meas = [('needed', T[T.ndrones > 0], 'cbin', [b[2] for b in CBIN], 'l2d', 'per doubling of drones the mission needs'),
            ('team', T, 'tbin', [b[2] for b in TEAMBIN], 'l2pool', 'per doubling of drones committed (team)'),
            ('tasks', T[T.residual == 0], 'ntasks', [2, 3, 4, 5, 6], 'ntasks', 'per extra task'),
            ('types', T[T.ncolours > 0], 'ncolours', [1, 2, 3], 'ntypes', 'per extra drone type'),
            ('plan', T, 'pbin', [b[2] for b in PBIN], 'l2plan', 'per doubling of plan size (team x tasks)')]
    tm = {}
    for key, d, binc, order, x, unit in meas:
        rec = dict(unit=unit, bins=[str(b_) for b_ in order])
        for lab, g in (('all', d), ('card', d[d.card == 1]), ('manual', d[d.card == 0])):
            rows = boot_rate(g, 'consulted', binc, order)
            for z in rows:
                z['bin'] = str(z['bin'])
            rec[lab] = rows
        dd = centre(centre(d, 'card'), x)
        rec['size'] = within_or(d, 'consulted', x)
        tt = gee_terms(dd, 'consulted ~ card_w + card_pm + %s_w + %s_pm + C(game) + C(run)' % (x, x), ['card_w', '%s_w' % x])
        rec['route'] = tt['card_w']
        rec['sizeHeldRoute'] = tt['%s_w' % x]
        ti = gee_terms(dd, 'consulted ~ card_w * %s_w + card_pm + %s_pm + C(game) + C(run)' % (x, x), ['card_w:%s_w' % x])
        rec['inter'] = ti['card_w:%s_w' % x]
        # how far the measure itself depends on the strategic route (same mission, card vs manual)
        mm = d.groupby('card')[x].mean()
        rec['meanByRoute'] = dict(card=r(mm.get(1)), manual=r(mm.get(0)))
        try:
            om = smf.ols('%s ~ card + C(mkey)' % x, d).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(d.pid)[0]})
            rec['sameMissionDiff'] = dict(b=r(om.params['card']), lo=r(om.conf_int().loc['card', 0]),
                                          hi=r(om.conf_int().loc['card', 1]), p=r(om.pvalues['card'], 5))
        except Exception:
            rec['sameMissionDiff'] = None
        tm[key] = rec
        say('   %s: size %s' % (key, unit), rec['size'])
        say('   %s: card-allocated vs hand-allocated (size held)' % key, rec['route'])
        say('   %s: route x size (ratio of ORs; <1 = gap narrows with size)' % key, rec['inter'])
        print('      measure by route: card %s, manual %s; same mission, card minus manual: %s'
              % (rec['meanByRoute']['card'], rec['meanByRoute']['manual'], rec['sameMissionDiff']))
        for lab in ('card', 'manual'):
            print('      %-6s' % lab, [(z['bin'], z['n'], z['rate']) for z in rec[lab]])
    pr = pd.DataFrame(dict(took=S.groupby('pid').took.mean(), sug=T.groupby('pid').consulted.mean())).dropna()
    rho, pv = stats.spearmanr(pr.took, pr.sug)
    tm['personLink'] = dict(rho=r(rho), p=r(pv, 5), k=int(len(pr)))
    print('   person level: card-taking rate vs Suggest rate, Spearman rho = %.2f (p = %.4f, %d people)' % (rho, pv, len(pr)))
    out['tacMeasures'] = tm

    # ── G4 · person by person, as bars (f-size-decides#people) ─────────────────────────────────────
    print('\nG4 per person, by drones-needed band (each person counts once per band)')
    pb = {}
    for lab, d, y in (('strat', S, 'took'), ('tac', T[T.ndrones > 0], 'consulted')):
        d = d.copy()
        d['band'] = d.ndrones.map(lambda v: binof(v, PEOPLEBAND))
        own = d.groupby('pid')[y].mean()
        grand = d[y].mean()
        rows = []
        per_person = {}
        for b_ in [x[2] for x in PEOPLEBAND]:
            g = d[d.band == b_]
            cnt = g.groupby('pid')[y].agg(['mean', 'size'])
            cnt = cnt[cnt['size'] >= 2]
            raw = boot_mean_people(cnt['mean'].values)
            rel = boot_mean_people((cnt['mean'] - own.reindex(cnt.index)).values + grand)
            rows.append(dict(bin=b_, raw=raw, rel=rel, k=int(len(cnt)), n=int(cnt['size'].sum())))
            for pid_, v in cnt['mean'].items():
                per_person.setdefault(pid_, {})[b_] = v
            print('   %s %-6s people %2d (decisions %3d): plain mean %.2f [%.2f, %.2f]; own average removed %.2f [%.2f, %.2f]'
                  % (lab, b_, len(cnt), cnt['size'].sum(), raw['mean'], raw['lo'], raw['hi'], rel['mean'], rel['lo'], rel['hi']))
        # people whose rate on their biggest band beats their smallest band (both with >= 2 decisions)
        up = down = same = 0
        for pid_, bb in per_person.items():
            ks = [x[2] for x in PEOPLEBAND if x[2] in bb]
            if len(ks) < 2:
                continue
            a_, z_ = bb[ks[0]], bb[ks[-1]]
            up += z_ > a_ + 1e-9
            down += z_ < a_ - 1e-9
            same += abs(z_ - a_) <= 1e-9
        sp = stats.binomtest(int(up), int(up + down)).pvalue if up + down else None
        pb[lab] = dict(rows=rows, up=int(up), down=int(down), same=int(same), p=r(sp, 5), grand=r(grand))
        print('   %s: biggest band above smallest for %d people, below %d, equal %d (sign test p = %.4f)' % (lab, up, down, same, sp))
    out['peopleBars'] = pb

    # ── G5 · the "one type, manual" error bars (f-size-decides#speed) ─────────────────────────────
    print('\nG5 spread of strategic decision time, one-type missions, by route')
    S['route3'] = np.where(S.took == 1, 'card', np.where(S.early == 1, 'pre-emptive manual', 'manual after cards'))
    sp_ = {}
    for rt in ('card', 'manual after cards', 'pre-emptive manual'):
        g = S[(S.route3 == rt) & (S.ncolours == 1)]
        pm = g.groupby('pid').secs.median()
        sp_[rt] = dict(n=int(len(g)), k=int(g.pid.nunique()), med=r(g.secs.median(), 2), q1=r(g.secs.quantile(.25), 2),
                       q3=r(g.secs.quantile(.75), 2), p10=r(g.secs.quantile(.10), 2), p90=r(g.secs.quantile(.90), 2),
                       personMedQ1=r(pm.quantile(.25), 2), personMedQ3=r(pm.quantile(.75), 2))
        print('   %-20s n=%d (%d people): median %.1f s, middle half %.1f-%.1f s, 10th-90th %.1f-%.1f s; person medians, middle half %.1f-%.1f s'
              % (rt, len(g), g.pid.nunique(), g.secs.median(), g.secs.quantile(.25), g.secs.quantile(.75),
                 g.secs.quantile(.10), g.secs.quantile(.90), pm.quantile(.25), pm.quantile(.75)))
    out['speedSpread'] = sp_

    # ── G6 · where the tactical time goes (f-size-decides#parallel) ─────────────────────────────
    print('\nG6 tactical plan, phase by phase: before first action / building / plan ready -> confirm / carrying out')
    ph = []
    for x, raw in zip(T.itertuples(), T['_raw']):
        if raw is None:
            continue
        o_, c_ = raw['open'], x.confirm_ts
        acts = sorted(raw['sugg'] + raw['drags'])
        first = min(acts[0], c_) if acts else c_
        if raw['sugg']:
            ready = max([raw['sugg'][-1] + x.entries * 1000.0] + raw['drags'])
        else:
            ready = max(raw['drags']) if raw['drags'] else first
        ready = min(max(ready, first), c_)
        M_ = MISSION.get((x.pid, x.run, x.missionId), {})
        done = M_.get('done')
        clean_ = done is not None and M_.get('outcome') == 'all_completed' and not M_.get('failures')
        anydone = done is not None and M_.get('outcome') == 'all_completed'
        nopen = sum(1 for t_ in raw['opens'] if ready <= t_ <= c_)
        ph.append(dict(pid=x.pid, run=x.run, game=x.game, route=x.route, consulted=x.consulted, l2d=x.l2d, ndrones=x.ndrones,
                       pre=(first - o_) / 1000.0, build=(ready - first) / 1000.0, hold=(c_ - ready) / 1000.0,
                       carry=(done - c_) / 1000.0 if clean_ else np.nan, clean=int(clean_), holdOther=int(nopen > 0),
                       preOther=int(any(o_ <= t_ <= first for t_ in raw['opens'] + raw['choices'])),
                       carryAny=(done - c_) / 1000.0 if anydone else np.nan, failures=M_.get('failures'),
                       agentProj=x.agentProj, finalProj=x.finalProj))
    PH = pd.DataFrame(ph)
    PH['band'] = np.where(PH.ndrones <= 6, 'small', np.where(PH.ndrones <= 9, 'mid', 'large'))
    PH['total'] = PH[['pre', 'build', 'hold', 'carry']].sum(1, min_count=4)
    print('   plans %d; mission completed in full with no drone failure (carry-out measurable): %d' % (len(PH), PH.clean.sum()))
    seg = ['pre', 'build', 'hold', 'carry']
    phases = {}
    for band in ('all', 'small', 'mid', 'large'):
        g0 = PH[PH.clean == 1] if band == 'all' else PH[(PH.clean == 1) & (PH.band == band)]
        rec = {}
        for rt in ('hand', 'suggest-kept', 'suggest-edited'):
            g = g0[g0.route == rt]
            if len(g) < 3:
                continue
            rec[rt] = dict(boot_seg_means(g, seg + ['total']), n=int(len(g)), k=int(g.pid.nunique()),
                           holdOther=r(g.holdOther.mean()))
        phases[band] = rec
        for rt, v in rec.items():
            print('   %-5s %-15s n=%3d  before %5.1f  building %5.1f  ready->confirm %5.1f  carrying out %5.1f  total %5.1f'
                  % (band, rt, v['n'], v['pre']['mean'], v['build']['mean'], v['hold']['mean'], v['carry']['mean'], v['total']['mean']))
    # within person, drones needed held: seconds added on each phase by a Suggest plan (kept or edited) vs hand
    d = PH[(PH.clean == 1) & (PH.ndrones > 0)].copy()
    d = centre(d, 'consulted')
    pm_ = {}
    for sgm in seg + ['total']:
        t_ = gee_terms(d, '%s ~ consulted_w + consulted_pm + l2d + C(game) + C(run)' % sgm, ['consulted_w'], binomial=False)['consulted_w']
        pm_[sgm] = t_
        if t_:
            print('   %-6s Suggest vs hand, same person, size held: %+.1f s [%+.1f, %+.1f] p=%.4f' % (sgm, t_['est'], t_['lo'], t_['hi'], t_['p']))
    # robustness: the first three phases on ALL plans (no completion needed); carrying out on every mission
    # completed in full, drone failures included
    dA = centre(PH[PH.ndrones > 0].copy(), 'consulted')
    rob = {}
    for sgm in ('pre', 'build', 'hold'):
        rob[sgm] = gee_terms(dA, '%s ~ consulted_w + consulted_pm + l2d + C(game) + C(run)' % sgm, ['consulted_w'], binomial=False)['consulted_w']
        say('   ALL plans, %s: Suggest vs hand, s' % sgm, rob[sgm], unit='s')
    dC = centre(PH[(PH.ndrones > 0) & PH.carryAny.notna()].copy(), 'consulted')
    rob['carryAny'] = gee_terms(dC, 'carryAny ~ consulted_w + consulted_pm + l2d + C(game) + C(run)', ['consulted_w'], binomial=False)['consulted_w']
    say('   carrying out, completed missions incl. drone failures', rob['carryAny'], unit='s')
    excl = PH[PH.clean == 0]
    why = dict(notCompleted=int(excl.carryAny.isna().sum()), droneFailure=int((excl.carryAny.notna()).sum()),
               byRoute={rt: dict(n=int((PH.route == rt).sum()), clean=int(PH[PH.route == rt].clean.sum())) for rt in ('hand', 'suggest-kept', 'suggest-edited')})
    print('   excluded from the stacked view:', why)
    # projected completion: the plan as confirmed vs the agent's plan at open (same scheduler, seconds)
    PH['projGap'] = PH.finalProj - PH.agentProj
    pj = {}
    for rt in ('hand', 'suggest-kept', 'suggest-edited'):
        g = PH[(PH.route == rt) & PH.projGap.notna()]
        bm = boot_median(g.assign(one=1), 'projGap', 'one', [1], B=1000)
        pj[rt] = dict(n=int(len(g)), mean=r(g.projGap.mean(), 2), med=r(g.projGap.median(), 2),
                      lo=bm[0]['lo'] if bm else None, hi=bm[0]['hi'] if bm else None,
                      later=r((g.projGap > 1).mean()))
        print('   projected completion, confirmed plan minus the agent plan at open, %-15s n=%d mean %+.1f s median %+.1f s; >1 s later in %.0f%%'
              % (rt, len(g), g.projGap.mean(), g.projGap.median(), 100 * (g.projGap > 1).mean()))
    out['phases'] = dict(phases=phases, models=pm_, robust=rob, excluded=why, proj=pj, nPlans=int(len(PH)), nClean=int(PH.clean.sum()),
                         bandDef='small ≤ 6 drones needed, mid 7–9, large 10+')
    STORE.update(PH=PH, S=S, T=T)

    # ── G7 · C06 profile as means with intervals (f-size-decides#slow) ────────────────────────────
    print('\nG7 C06 vs others, group means with 95% intervals (people resampled within group)')
    grp6 = who['C06']
    c6 = []
    for k_, lab, unit in PROFILE:
        v = PT[k_].dropna()
        a_ = boot_mean_people(v[v.index.isin(grp6)].values)
        b2 = boot_mean_people(v[~v.index.isin(grp6)].values)
        c6.append(dict(key=k_, inMean=a_['mean'], inLo=a_['lo'], inHi=a_['hi'], nIn=a_['k'],
                       restMean=b2['mean'], restLo=b2['lo'], restHi=b2['hi'], nRest=b2['k']))
        print('   %-45s C06 %s [%s, %s]  others %s [%s, %s]' % (lab, a_['mean'], a_['lo'], a_['hi'], b2['mean'], b2['lo'], b2['hi']))
    out['c06ci'] = c6

    # ── G8 · within-session speed-up: does it carry over? (f-practice#speed) ────────────────────────
    print('\nG8 speed-up within a session vs carry-over to the next')
    S['minute'] = np.minimum(np.floor(S.elapsed_open / 60).astype(int) + 1, 8)
    T['minute'] = np.minimum(np.floor(T.elapsed_open / 60).astype(int) + 1, 8)
    carry = {}
    for lab, d, ctrl in (('strat', S, 'took + threetype + l2d'), ('tac', T, 'consulted + np.log(plan)')):
        d = d.copy()
        d['part'] = np.where(d.minute <= 2, 'start', np.where(d.minute >= 7, 'end', 'middle'))
        bars = []
        for run in (1, 2):
            for part in ('start', 'end'):
                g = d[(d.run == run) & (d.part == part)]
                bm = boot_median(g.assign(one=1), 'net', 'one', [1], B=1000)
                if bm:
                    bars.append(dict(run=run, part=part, med=bm[0]['med'], lo=bm[0]['lo'], hi=bm[0]['hi'], n=bm[0]['n'], k=bm[0]['k']))
        m = gee_fit('lnet ~ emin * run2 + %s + C(game)' % ctrl, d, binomial=False)
        b_ = m.params
        cov = m.cov_params()

        def pct_of(vec):
            est = float(np.dot(vec.values, b_[list(vec.index)].values))
            se = float(np.sqrt(vec.values @ cov.loc[vec.index, vec.index].values @ vec.values))
            return dict(pct=r(np.exp(est) - 1), lo=r(np.exp(est - 1.96 * se) - 1), hi=r(np.exp(est + 1.96 * se) - 1),
                        p=r(2 * stats.norm.sf(abs(est / se)), 5))
        # predicted time relative to session 1 at its start (minute 0.5)
        e0, e1 = 0.5, 7.5
        v = lambda names, vals: pd.Series(vals, index=names, dtype=float)
        pr_ = dict(
            s1end=pct_of(v(['emin'], [e1 - e0])),
            s2start=pct_of(v(['run2', 'emin:run2'], [1.0, e0])),
            s2end=pct_of(v(['emin', 'run2', 'emin:run2'], [e1 - e0, 1.0, e1])),
            s2start_vs_s1end=pct_of(v(['emin', 'run2', 'emin:run2'], [-(e1 - e0), 1.0, e0])),
            slopeS1=pct_of(v(['emin'], [1.0])),
            slopeS2=pct_of(v(['emin', 'emin:run2'], [1.0, 1.0])),
            slopeDiff=pct_of(v(['emin:run2'], [1.0])))
        # does the within-session slope survive holding the queue fixed?
        mq = gee_fit('lnet ~ emin + run2 + q + %s + C(game)' % ctrl, d, binomial=False)
        tq = term(mq, 'emin', binomial=False)
        pr_['slopeQueueHeld'] = dict(pct=r(np.exp(tq['b']) - 1), lo=r(np.exp(tq['b'] - 1.96 * tq['se']) - 1),
                                     hi=r(np.exp(tq['b'] + 1.96 * tq['se']) - 1), p=tq['p'])
        carry[lab] = dict(bars=bars, model=pr_, n=int(len(d)), k=int(d.pid.nunique()))
        print('   %s: medians %s' % (lab, [(z['run'], z['part'], z['med'], z['n']) for z in bars]))
        for k_, t_ in pr_.items():
            print('      %-18s %+.0f%% [%+.0f, %+.0f] p=%.4f' % (k_, 100 * t_['pct'], 100 * t_['lo'], 100 * t_['hi'], t_['p']))
    out['carry'] = carry

    # ── G9 · C22: did "got better" mean "used the assistants more"? (f-practice#c22) ──────────────
    print("\nG9 C22: change in assistant use, session 1 -> 2 (each session's rate minus that game's average)")
    cols = []
    for lab, d, y in (('took', S, 'took'), ('sug', T, 'consulted')):
        g = d.groupby(['pid', 'run', 'game'])[y].mean().reset_index()
        g['adj'] = g[y] - g.groupby('game')[y].transform('mean')
        w_ = g.pivot_table(index='pid', columns='run', values='adj')
        raw_ = d.groupby(['pid', 'run'])[y].mean().unstack()
        cols += [(w_[2] - w_[1]).rename(lab), (raw_[2] - raw_[1]).rename(lab + 'Raw')]
    U = pd.concat(cols, axis=1)
    c22 = {}
    for k_ in ('took', 'sug', 'tookRaw', 'sugRaw'):
        t_ = perm_diff(U[k_], who['C22'])
        c22[k_] = t_
        print('   %-8s C22 %s  others %s  p=%s' % (k_, t_['inMean'], t_['restMean'], t_['p']))
    # across everyone: does a bigger score gain go with a bigger change in use?
    dz = pd.Series(score_change(S, P))
    for k_ in ('took', 'sug'):
        j = pd.concat([dz.rename('dZ'), U[k_]], axis=1).dropna()
        rho, pv = stats.spearmanr(j.dZ, j[k_])
        c22['rho_' + k_] = dict(rho=r(rho), p=r(pv, 5), k=int(len(j)))
        print('   everyone: score change vs change in %s, Spearman rho = %.2f (p = %.4f, %d people)' % (k_, rho, pv, len(j)))
    c22['people'] = {pid_: dict(dTook=r(U.loc[pid_, 'took']), dSug=r(U.loc[pid_, 'sug'])) for pid_ in U.index}
    inC = U.index.isin(who['C22'])
    c22['upTook'] = dict(c22=int((U.loc[inC, 'took'] > 0).sum()), others=int((U.loc[~inC, 'took'] > 0).sum()),
                         nC22=int(U.loc[inC, 'took'].notna().sum()), nOthers=int(U.loc[~inC, 'took'].notna().sum()))
    c22['upSug'] = dict(c22=int((U.loc[inC, 'sug'] > 0).sum()), others=int((U.loc[~inC, 'sug'] > 0).sum()),
                        nC22=int(U.loc[inC, 'sug'].notna().sum()), nOthers=int(U.loc[~inC, 'sug'].notna().sum()))
    print('   used more in session 2 (game-adjusted): cards C22 %d, others %d; Suggest C22 %d, others %d'
          % (c22['upTook']['c22'], c22['upTook']['others'], c22['upSug']['c22'], c22['upSug']['others']))
    out['c22use'] = c22
    return out

# ════════════════════════════════════════════════════════════════════════════════════════════
# H · PASS 4 (written under `p4`; earlier keys unchanged). The researcher's pass-3 notes
# (docs/analysis/register/passes/pass3.json).
# ════════════════════════════════════════════════════════════════════════════════════════════

SPEED_BANDS = ['one type', 'three types, 6–9 drones', 'three types, 10–18 drones']
TAC_BANDS = ['small', 'mid', 'large']


def boot_std_means(d, cols, band_col, bands, weights, B=B_BOOT, rng=None):
    """Size-standardised mean of each column: sum over bands of weight x the band's mean, with the SAME
    band weights for every route. 95% interval from resampling people (draws where a band is empty skipped)."""
    people = sorted(d.pid.unique())
    pi = {p_: i for i, p_ in enumerate(people)}
    S_ = np.zeros((len(bands), len(people), len(cols)))
    N_ = np.zeros((len(bands), len(people)))
    for j, b_ in enumerate(bands):
        g = d[d[band_col] == b_]
        for p_, gg in g.groupby('pid'):
            S_[j, pi[p_]] = gg[cols].sum().values
            N_[j, pi[p_]] = len(gg)
    w = np.array([weights[b_] for b_ in bands])

    def stat(idx):
        s_ = S_[:, idx].sum(1)
        n_ = N_[:, idx].sum(1)
        if (n_ == 0).any():
            return None
        return (w[:, None] * s_ / n_[:, None]).sum(0)
    est = stat(np.arange(len(people)))
    bs, skipped = [], 0
    for _ in range(B):
        v = stat((rng or RNG).integers(0, len(people), len(people)))
        if v is None:
            skipped += 1
        else:
            bs.append(v)
    bs = np.array(bs)
    out = {c: dict(mean=r(est[k], 2), lo=r(np.percentile(bs[:, k], 2.5), 2), hi=r(np.percentile(bs[:, k], 97.5), 2))
           for k, c in enumerate(cols)}
    out['skipped'] = skipped
    return out


def section_pass4(who):
    from scipy import stats
    hdr('H · PASS 4: the pass-3 notes')
    out = {}
    S, T, PH = STORE['S'].copy(), STORE['T'].copy(), STORE['PH'].copy()

    # ── H1 · do the 5-drone missions arrive in a burst? (f-size-decides#both) ──────────────────
    print('\nH1 Strategic Heavy games: mission arrivals (fixed per game; residual missions left out)')
    gmap = S.drop_duplicates(['pid', 'run']).set_index(['pid', 'run']).game.to_dict()
    arr = {}
    for (pid, run, m), rec in MISSION.items():
        g = gmap.get((pid, run))
        if g is None or rec['residual']:
            continue
        arr.setdefault(g, {}).setdefault(m, []).append(rec['arrived'] / 1000.0)
    burst = {}
    for g in sorted(arr):
        if not g.startswith('strategic'):
            continue
        ms = []
        for m, ts in arr[g].items():
            spread = max(ts) - min(ts)
            rec = next(v for (p_, r_, mm), v in MISSION.items() if mm == m and gmap.get((p_, r_)) == g)
            ms.append(dict(mission=m, t=r(np.median(ts), 1), spread=r(spread, 2), nd=rec['nd'], nc=rec['nc'], comp=rec['comp']))
        ms.sort(key=lambda x: x['t'])
        for x in ms:
            x['near60'] = int(sum(1 for y in ms if y is not x and abs(y['t'] - x['t']) <= 60))
            x['before90'] = int(sum(1 for y in ms if y is not x and 0 <= x['t'] - y['t'] <= 90))
        burst[g] = ms
        print('   %s: %d missions' % (g, len(ms)))
        for x in ms:
            print('      %-6s t=%6.1f s (min %.1f)  %2d drones, %d type(s) %-14s  others within 60 s: %d; arrived in the 90 s before: %d%s'
                  % (x['mission'], x['t'], x['t'] / 60, x['nd'], x['nc'], x['comp'], x['near60'], x['before90'],
                     '   (arrival differs across people by %.1f s)' % x['spread'] if x['spread'] > 1 else ''))
    allm = [x for ms in burst.values() for x in ms]
    summ = {}
    for lab, sel in (('five', lambda x: x['nc'] == 1 and x['nd'] == 5), ('threeSix', lambda x: x['nc'] == 1 and x['nd'] in (3, 6)),
                     ('other', lambda x: not (x['nc'] == 1 and x['nd'] in (3, 5, 6)))):
        g = [x for x in allm if sel(x)]
        summ[lab] = dict(n=len(g), near60=r(np.mean([x['near60'] for x in g]), 2) if g else None,
                         before90=r(np.mean([x['before90'] for x in g]), 2) if g else None,
                         minute=r(np.mean([x['t'] / 60 for x in g]), 2) if g else None)
    print('   mean other arrivals within 60 s, Strategic Heavy games:', summ)
    out['burst'] = dict(games=burst, summary=summ)

    # ── H2 · the strategic choice and Suggest (f-size-decides#tactical) ──────────────────────────
    print('\nH2 Suggest by strategic route: Aggressive card vs Conservative card vs by hand')
    T['aggr'] = (T.strategy == 'Aggressive').astype(int)
    rates = {}
    for st in ('Aggressive', 'Conservative', 'Manual'):
        g = T[T.strategy == st]
        rates[st] = dict(n=int(len(g)), rate=r(g.consulted.mean()), k=int(g.pid.nunique()))
    c = T[(T.strategy != 'Manual') & (T.ndrones > 0)].copy()
    c = centre(centre(c, 'aggr'), 'l2d')
    ag = gee_terms(c, 'consulted ~ aggr_w + aggr_pm + l2d_w + l2d_pm + C(game) + C(run)', ['aggr_w'])['aggr_w']
    say('   Aggressive vs Conservative card, same person, drones needed held', ag)
    print('   rates:', rates)
    ppl = {}
    for pid in ('P05', 'P10', 'P30'):
        g = T[T.pid == pid]
        ppl[pid] = {st: dict(n=int((g.strategy == st).sum()), rate=r(g[g.strategy == st].consulted.mean()))
                    for st in ('Aggressive', 'Conservative', 'Manual')}
        print('   %s:' % pid, ppl[pid])
    out['route'] = dict(rates=rates, aggrVsCons=ag, people=ppl)

    # ── H3 · strategic decision time, phase by phase (f-size-decides#speed) ──────────────────────
    print('\nH3 strategic decision split: before the first action (cards loading / cards on screen) and first action -> choice')
    S['size'] = np.where(S.ncolours == 1, 'one type', np.where(S.ncolours == 3, np.where(S.ndrones <= 9, SPEED_BANDS[1], SPEED_BANDS[2]), None))
    S['route'] = np.where(S.took == 1, 'card', np.where(S.early == 1, 'pre-emptive manual', 'manual after cards'))
    first = []
    for g_, o_, c_ in zip(S._g, S.open_ts, S.choice_ts):
        acts = [a for a in (g_ or {}).get('acts', []) if o_ <= a <= c_]
        first.append(min(acts) if acts else c_)
    S['first'] = first
    rv = S.open_ts + S.reveal * 1000.0
    S['load'] = (np.minimum(S['first'], rv) - S.open_ts) / 1000.0
    S['idle'] = np.maximum(0.0, S['first'] - rv) / 1000.0
    S['act'] = (S.choice_ts - S['first']) / 1000.0
    S['tot'] = S[['load', 'idle', 'act']].sum(1)
    S['noidle'] = S.load + S.act
    print('   no first action recorded before the choice: %d of %d' % (int((S['first'] == S.choice_ts).sum()), len(S)))
    print('   check: segments add to the logged seconds: max abs diff %.3f s' % (S.tot - S.secs).abs().max())
    seg = ['load', 'idle', 'act', 'tot', 'noidle']
    sph = {}
    for band in SPEED_BANDS:
        rec = {}
        for rt in ('card', 'manual after cards', 'pre-emptive manual'):
            g = S[(S['size'] == band) & (S.route == rt)]
            if len(g) < 3:
                continue
            rec[rt] = dict(boot_seg_means(g, seg), n=int(len(g)), k=int(g.pid.nunique()))
            v = rec[rt]
            print('   %-27s %-19s n=%3d  loading %4.1f  on screen, no action %4.1f  acting %4.1f  = %4.1f s  (no idle %4.1f)'
                  % (band, rt, v['n'], v['load']['mean'], v['idle']['mean'], v['act']['mean'], v['tot']['mean'], v['noidle']['mean']))
        sph[band] = rec
    # within person: card vs all manual, log seconds, by one-type / three-type (as section B), three definitions
    d = S[S.ncolours.isin([1, 3])].copy()
    d['three'] = (d.ncolours == 3).astype(int)
    d = centre(d, 'took')
    smod = {}
    for y, lab in (('tot', 'all'), ('noidle', 'noIdle'), ('act', 'active')):
        d['ly'] = np.log(d[y].clip(lower=0.5))
        m = gee_fit('ly ~ took * three + took_pm + l2d + C(game) + C(run) + emin', d, binomial=False)
        cov = m.cov_params()
        b1, b3 = m.params['took'], m.params['took:three']
        se1 = np.sqrt(cov.loc['took', 'took'])
        se13 = np.sqrt(cov.loc['took', 'took'] + cov.loc['took:three', 'took:three'] + 2 * cov.loc['took', 'took:three'])
        pc = lambda b, s_: dict(est=r(np.exp(b) - 1), lo=r(np.exp(b - 1.96 * s_) - 1), hi=r(np.exp(b + 1.96 * s_) - 1),
                                p=r(2 * stats.norm.sf(abs(b / s_)), 5))
        smod[lab] = dict(one=pc(b1, se1), three=pc(b1 + b3, se13), inter=term(m, 'took:three', binomial=False), n=int(len(d)), k=int(d.pid.nunique()))
        print('   %-7s card vs manual, same person: one-type %+.0f%% [%+.0f, %+.0f] p=%.4f; three-type %+.0f%% [%+.0f, %+.0f] p=%.4g; difference p=%.4g'
              % (lab, 100 * smod[lab]['one']['est'], 100 * smod[lab]['one']['lo'], 100 * smod[lab]['one']['hi'], smod[lab]['one']['p'],
                 100 * smod[lab]['three']['est'], 100 * smod[lab]['three']['lo'], 100 * smod[lab]['three']['hi'], smod[lab]['three']['p'],
                 smod[lab]['inter']['p']))
    hang = dict(card=r(S[S.route == 'card'].idle.median(), 2), manualAfter=r(S[S.route == 'manual after cards'].idle.median(), 2),
                share10=r((S.idle > 10).mean()))
    print('   idle with cards on screen, median: card %.1f s, manual after cards %.1f s; > 10 s in %.0f%% of decisions'
          % (hang['card'], hang['manualAfter'], 100 * hang['share10']))
    # r5 (2026-10-26): card vs by hand after the cards loaded (pre-emptive left out), pooled over the three bands as
    # decided (raw mix) and size-standardised (each band weighted by its share of those decisions, the same for both
    # routes), as in the tactical chart. Own generator, so adding it leaves every other interval in this file unchanged.
    rng5 = np.random.default_rng(SEED + 2610)
    S2 = S[S['size'].isin(SPEED_BANDS) & S.route.isin(['card', 'manual after cards'])]
    swts = {b_: float((S2['size'] == b_).mean()) for b_ in SPEED_BANDS}
    smix = {}
    for rt in ('card', 'manual after cards'):
        g = S2[S2.route == rt]
        smix[rt] = dict(raw=dict(boot_seg_means(g, seg, rng=rng5), n=int(len(g)), k=int(g.pid.nunique())),
                        std=boot_std_means(g, seg, 'size', SPEED_BANDS, swts, rng=rng5),
                        mix={b_: r((g['size'] == b_).mean()) for b_ in SPEED_BANDS})
        print('   %-19s all bands, raw: load %.1f + act %.1f = %.1f s (no idle) | standardised: %.1f [%.1f, %.1f]; mix %s'
              % (rt, smix[rt]['raw']['load']['mean'], smix[rt]['raw']['act']['mean'], smix[rt]['raw']['noidle']['mean'],
                 smix[rt]['std']['noidle']['mean'], smix[rt]['std']['noidle']['lo'], smix[rt]['std']['noidle']['hi'], smix[rt]['mix']))
    print('   weights (both routes pooled):', {k: round(v, 3) for k, v in swts.items()})
    out['stratPhases'] = dict(phases=sph, models=smod, idle=hang, n=int(len(S)), mix=smix, weights=swts)

    # ── H4 · tactical planner time, phase by phase, all plans (f-size-decides#speed) ─────────────
    print('\nH4 tactical planner split (all plans with a known size): before first action / building / ready -> confirmed')
    A = PH[PH.ndrones > 0].copy()
    A['plan'] = A[['build', 'hold']].sum(1)
    A['tot'] = A[['pre', 'build', 'hold']].sum(1)
    tph = {}
    for band in ['all'] + TAC_BANDS:
        g0 = A if band == 'all' else A[A.band == band]
        rec = {}
        for rt in ('hand', 'suggest-kept', 'suggest-edited'):
            g = g0[g0.route == rt]
            if len(g) < 3:
                continue
            rec[rt] = dict(boot_seg_means(g, ['pre', 'build', 'hold', 'plan', 'tot']), n=int(len(g)), k=int(g.pid.nunique()))
            v = rec[rt]
            print('   %-5s %-15s n=%3d  before %5.1f  building %5.1f  ready->confirm %4.1f  = %5.1f s (without before: %5.1f)'
                  % (band, rt, v['n'], v['pre']['mean'], v['build']['mean'], v['hold']['mean'], v['tot']['mean'], v['plan']['mean']))
        tph[band] = rec
    dA = centre(A.copy(), 'consulted')
    tmod = {}
    for y in ('plan', 'tot'):
        tmod[y] = gee_terms(dA, '%s ~ consulted_w + consulted_pm + l2d + C(game) + C(run)' % y, ['consulted_w'], binomial=False)['consulted_w']
        say('   %s: Suggest vs hand, same person, size held (s)' % y, tmod[y], unit='s')
    tmod['planInter'] = gee_terms(centre(dA, 'l2d'), 'plan ~ consulted_w * l2d_w + consulted_pm + l2d_pm + C(game) + C(run)',
                                  ['consulted_w:l2d_w'], binomial=False)['consulted_w:l2d_w']
    say('   without "before": Suggest x doubling of size (s)', tmod['planInter'], unit='s')
    po = {rt: dict(n=int((A.route == rt).sum()), share=r(A[A.route == rt].preOther.mean()),
                   shareLong=r(A[(A.route == rt) & (A.pre > 10)].preOther.mean()), nLong=int(((A.route == rt) & (A.pre > 10)).sum()))
          for rt in ('hand', 'suggest-kept')}
    po['all'] = dict(n=int(len(A)), share=r(A.preOther.mean()), shareLong=r(A[A.pre > 10].preOther.mean()), nLong=int((A.pre > 10).sum()),
                     medPre=r(A.pre.median(), 2))
    print('   before the first action, operator opened or allocated another mission in the meantime:', po)
    out['tacPhases'] = dict(phases=tph, models=tmod, n=int(len(A)), preOther=po)

    # ── H5 · the whole tactical timeline: size mix and the all-missions reversal (f-size-decides#parallel) ──
    print('\nH5 finished plans: why "all" reverses the per-size ordering (size mix), and size-standardised means')
    C_ = PH[(PH.clean == 1) & PH.route.isin(['hand', 'suggest-kept'])].copy()
    C_['noPre'] = C_[['build', 'hold', 'carry']].sum(1)
    mix = {}
    for rt in ('hand', 'suggest-kept'):
        g = C_[C_.route == rt]
        mix[rt] = {b_: dict(n=int((g.band == b_).sum()), share=r((g.band == b_).mean())) for b_ in TAC_BANDS}
        mix[rt]['nd'] = r(g.ndrones.mean(), 2)
        print('   %-13s size mix: %s; mean drones needed %.1f' % (rt, {b_: (v['n'], v['share']) for b_, v in mix[rt].items() if b_ != 'nd'}, mix[rt]['nd']))
    wts = {b_: float((C_.band == b_).mean()) for b_ in TAC_BANDS}
    print('   weights (both routes pooled):', {k: round(v, 3) for k, v in wts.items()})
    std = {}
    cols = ['pre', 'build', 'hold', 'carry', 'total', 'noPre']
    for rt in ('hand', 'suggest-kept'):
        std[rt] = dict(boot_std_means(C_[C_.route == rt], cols, 'band', TAC_BANDS, wts), n=int((C_.route == rt).sum()),
                       k=int(C_[C_.route == rt].pid.nunique()))
        v = std[rt]
        print('   standardised %-13s before %5.1f  building %5.1f  ready->confirm %4.1f  carrying out %5.1f  total %5.1f [%5.1f, %5.1f] (skipped draws %d)'
              % (rt, v['pre']['mean'], v['build']['mean'], v['hold']['mean'], v['carry']['mean'], v['total']['mean'],
                 v['total']['lo'], v['total']['hi'], v['skipped']))
    raw = {rt: dict(boot_seg_means(C_[C_.route == rt], cols), n=int((C_.route == rt).sum())) for rt in ('hand', 'suggest-kept')}
    # per-size raw means of 'without before'
    bandNoPre = {}
    for b_ in TAC_BANDS:
        bandNoPre[b_] = {}
        for rt in ('hand', 'suggest-kept'):
            g = C_[(C_.route == rt) & (C_.band == b_)]
            if len(g) >= 3:
                bandNoPre[b_][rt] = dict(boot_seg_means(g, ['noPre']), n=int(len(g)), k=int(g.pid.nunique()))['noPre'] | dict(n=int(len(g)), k=int(g.pid.nunique()))
    # within person, size held: the whole thing without the time before the first action
    dC = centre(C_[C_.ndrones > 0].copy(), 'consulted')
    noPreM = gee_terms(dC, 'noPre ~ consulted_w + consulted_pm + l2d + C(game) + C(run)', ['consulted_w'], binomial=False)['consulted_w']
    say('   whole thing without "before the first action": Suggest vs hand, same person, size held (s)', noPreM, unit='s')
    # the same raw comparison with person held but size NOT held, to show which of the two creates the reversal
    noSize = gee_terms(dC, 'total ~ consulted_w + consulted_pm + C(game) + C(run)', ['consulted_w'], binomial=False)['consulted_w']
    say('   whole thing, same person, size NOT held (s)', noSize, unit='s')
    hl = C_[C_.route == 'hand']
    largeHand = dict(n=int((hl.band == 'large').sum()), k=int(hl[hl.band == 'large'].pid.nunique()))
    print('   large hand-built finished plans: %d from %d people' % (largeHand['n'], largeHand['k']))
    out['simpson'] = dict(mix=mix, weights={k: r(v) for k, v in wts.items()}, std=std, raw=raw, noPre=noPreM, noSize=noSize,
                          bandNoPre=bandNoPre, largeHand=largeHand)
    return out


def score_change(S, P):
    """Per person: within-game score, session 2 minus session 1 (same definition as section_learning)."""
    res = {}
    for pid in sorted(S.pid.unique()):
        p = P[P.pid == pid].set_index('run')
        if {1, 2} <= set(S[S.pid == pid].run):
            res[pid] = p.zgame.get(2, np.nan) - p.zgame.get(1, np.nan)
    return res


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


# ════════════════════════════════════════════════════════════════════════════════════════════
# Pass 5 (mid-pass notes). Run after everything else so no earlier bootstrap draw moves.
# ════════════════════════════════════════════════════════════════════════════════════════════

def section_pass5(S, T):
    from scipy import stats
    out = {}
    # ── P5a · card-then-Suggest: is the gap carried by a few people? (f-size-decides#tactical) ──────
    print('\nP5a card-allocated vs hand-allocated Suggest rate, person by person')
    d = T[T.ndrones > 0].copy()
    d['card'] = (d.strategy != 'Manual').astype(int)
    # expected Suggest use from size + game + session, NOT the route; a person's gap on this residual is size-held
    dd = centre(d, 'l2d')
    m = gee_fit('consulted ~ l2d_w + l2d_pm + C(game) + C(run)', dd)
    d['res'] = d.consulted - m.predict(dd)
    rows = []
    for pid, g in d.groupby('pid'):
        c, h_ = g[g.card == 1], g[g.card == 0]
        row = dict(pid=pid, nCard=int(len(c)), nHand=int(len(h_)), card=r(c.consulted.mean()) if len(c) else None,
                   hand=r(h_.consulted.mean()) if len(h_) else None, all=r(g.consulted.mean()))
        if len(c) >= 2 and len(h_) >= 2:
            row['gap'] = r(c.consulted.mean() - h_.consulted.mean())
            row['gapAdj'] = r(c.res.mean() - h_.res.mean())
        rows.append(row)
    both = [x for x in rows if 'gap' in x]
    up, down = sum(x['gapAdj'] > 0.005 for x in both), sum(x['gapAdj'] < -0.005 for x in both)
    same = len(both) - up - down
    sign_p = r(stats.binomtest(up, up + down).pvalue, 5) if up + down else None
    # leave-one-person-out and drop-the-biggest: the route odds ratio each time
    base = centre(centre(d, 'card'), 'l2d')
    f = 'consulted ~ card_w + card_pm + l2d_w + l2d_pm + C(game) + C(run)'
    main_ = gee_terms(base, f, ['card_w'])['card_w']
    loo = []
    for pid in sorted(x['pid'] for x in both):
        dl = centre(centre(d[d.pid != pid], 'card'), 'l2d')
        tt = gee_terms(dl, f, ['card_w'])['card_w']
        if tt:
            loo.append(dict(pid=pid, est=tt['est'], p=tt['p']))
    order = sorted(both, key=lambda x: -x['gapAdj'])
    drop = []
    for k in (1, 3, 5, 8):
        gone = {x['pid'] for x in order[:k]}
        dl = centre(centre(d[~d.pid.isin(gone)], 'card'), 'l2d')
        tt = gee_terms(dl, f, ['card_w'])['card_w']
        drop.append(dict(k=k, people=sorted(gone), est=tt['est'], lo=tt['lo'], hi=tt['hi'], p=tt['p']))
    gaps = np.array([x['gapAdj'] for x in both])
    pos = np.sort(gaps[gaps > 0])[::-1]
    share3 = r(pos[:3].sum() / gaps.sum()) if gaps.sum() > 0 else None
    only = dict(cardOnly=sum(1 for x in rows if x['nHand'] < 2), handOnly=sum(1 for x in rows if x['nCard'] < 2))
    out['routePeople'] = dict(rows=rows, nBoth=len(both), up=up, down=down, same=same, signP=sign_p, main=main_,
                              loo=dict(min=min(loo, key=lambda x: x['est']), max=max(loo, key=lambda x: x['est']),
                                       allSig=all(x['p'] < .05 for x in loo), n=len(loo)),
                              drop=drop, shareTop3=share3, meanGapAdj=r(gaps.mean()), only=only)
    print('   people with >=2 plans each way: %d; size-held gap up %d, down %d, same %d (sign p %s); mean gap %+.2f'
          % (len(both), up, down, same, sign_p, gaps.mean()))
    print('   route OR all: %s; leave-one-out range %s (%s) to %s (%s); every LOO p<.05: %s'
          % (main_['est'], out['routePeople']['loo']['min']['est'], out['routePeople']['loo']['min']['pid'],
             out['routePeople']['loo']['max']['est'], out['routePeople']['loo']['max']['pid'], out['routePeople']['loo']['allSig']))
    for x in drop:
        print('   drop top %d %s: OR %s [%s, %s] p %s' % (x['k'], x['people'], x['est'], x['lo'], x['hi'], x['p']))
    print('   top 3 positive gaps = %s of the summed gap; only one route: %s' % (share3, only))

    # ── P5b · speed through the session at finer grain (f-practice#speed) ─────────────────────────
    print('\nP5b net decision time by minute / pair of minutes / third of the session')
    fine = {}
    for lab, d in (('strat', S), ('tac', T)):
        d = d.copy()
        mnt = np.minimum(np.floor(d.elapsed_open / 60).astype(int) + 1, 8)
        groupings = dict(minute=(mnt.astype(str), [str(i) for i in range(1, 9)]),
                         pair=(((mnt + 1) // 2).map({1: '1–2', 2: '3–4', 3: '5–6', 4: '7–8'}), ['1–2', '3–4', '5–6', '7–8']),
                         third=(np.minimum(np.floor(d.elapsed_open / 160).astype(int), 2).map({0: 'first', 1: 'middle', 2: 'last'}),
                                ['first', 'middle', 'last']))
        rec = {}
        for gk, (col, order_) in groupings.items():
            d['g'] = col
            rec[gk] = {}
            for run in (1, 2):
                rows_ = boot_median(d[d.run == run], 'net', 'g', order_, B=1000)
                rec[gk][str(run)] = rows_
                print('   %s %s s%d: %s' % (lab, gk, run, [(z['bin'], z['med'], z['n']) for z in rows_]))
        fine[lab] = rec
    out['fine'] = fine

    # ── P5c · where manual builds sit, balanced for the mission (f-manual-cards#position) ─────────────
    # Pre-emptive builds were on smaller, more often one-type missions than builds made after seeing the cards, and an
    # 'equals a card' total is easier to hit when the cards are close together. Standardise: one logistic model per
    # position (is it 'below both'? 'equals a card'? ...) on the kind of build + drones needed + number of drone types +
    # the gap between the two card totals + game + session + minute; predict every one of the 209 builds as if it were
    # each kind in turn and average, so all three kinds are compared on the same mix of missions. The four shares are
    # rescaled to sum to 100%. 95% intervals: people resampled 1000 times, models refitted.
    print('\nP5c manual totals vs the two cards, balanced for the mission')
    rng = np.random.default_rng(SEED + 51)
    M = S[S.manual == 1].copy()
    M['kind'] = np.where(M.early == 1, 'pre-emptive', np.where(M.edited == 1, 'edited a card', 'built after seeing cards'))
    lo_, hi_ = np.minimum(M.cons_total, M.aggr_total), np.maximum(M.cons_total, M.aggr_total)
    M['pos'] = np.select([M.committed < lo_, M.committed > hi_, (M.committed == M.cons_total) | (M.committed == M.aggr_total)],
                         ['below both', 'above both', 'equals a card'], 'strictly between')
    M['spread'] = M.aggr_total - M.cons_total
    M['minute'] = M.elapsed_open / 60
    POS = ['below both', 'equals a card', 'strictly between', 'above both']
    KINDS = ['built after seeing cards', 'edited a card', 'pre-emptive']
    F = 'y ~ C(kind) + ndrones + C(ncolours) + spread + C(game) + C(run) + minute'

    def std_shares(d):
        tab = {}
        for p in POS:
            dd = d.assign(y=(d.pos == p).astype(int))
            try:
                m = quiet(smf.logit(F, dd).fit, disp=0, method='bfgs', maxiter=3000)
            except Exception:
                return None
            tab[p] = [m.predict(dd.assign(kind=k)).mean() for k in KINDS]
        a = np.array([tab[p] for p in POS]).T          # kinds x positions
        return a / a.sum(1, keepdims=True)
    est = std_shares(M)
    pids = M.pid.unique()
    byp = {p: M[M.pid == p] for p in pids}
    bs = []
    for _ in range(1000):
        a = std_shares(pd.concat([byp[p] for p in rng.choice(pids, len(pids))], ignore_index=True))
        if a is not None and np.isfinite(a).all():
            bs.append(a)
    bs = np.stack(bs)
    raw = pd.crosstab(M.kind, M.pos).reindex(index=KINDS, columns=POS, fill_value=0)
    mix = M.groupby('kind').agg(n=('pid', 'size'), people=('pid', 'nunique'), drones=('ndrones', 'mean'),
                                oneType=('ncolours', lambda v: (v == 1).mean()), spread=('spread', 'mean'),
                                session2=('run', lambda v: (v == 2).mean()), minute=('minute', 'mean'))
    rows = []
    for i, k in enumerate(KINDS):
        n = int(raw.loc[k].sum())
        rows.append(dict(kind=k, n=n, people=int(mix.loc[k, 'people']),
                         mix=dict(drones=r(mix.loc[k, 'drones'], 2), oneType=r(mix.loc[k, 'oneType']), spread=r(mix.loc[k, 'spread'], 2),
                                  session2=r(mix.loc[k, 'session2']), minute=r(mix.loc[k, 'minute'], 2)),
                         raw={p: r(raw.loc[k, p] / n) for p in POS},
                         adj={p: r(est[i, j]) for j, p in enumerate(POS)},
                         lo={p: r(np.quantile(bs[:, i, j], .025)) for j, p in enumerate(POS)},
                         hi={p: r(np.quantile(bs[:, i, j], .975)) for j, p in enumerate(POS)}))
        print('   %-26s n %3d  raw %s  balanced %s' % (k, n, [round(raw.loc[k, p] / n, 3) for p in POS], [round(est[i, j], 3) for j in range(4)]))
    # the comparison the section's text makes: pre-emptive vs after seeing, 'equals a card' and 'below both'
    pe, se_ = KINDS.index('pre-emptive'), KINDS.index('built after seeing cards')
    diffs = {}
    for j, p in enumerate(POS[:2]):
        dv = bs[:, pe, j] - bs[:, se_, j]
        diffs[p] = dict(raw=r(raw.loc['pre-emptive', p] / raw.loc['pre-emptive'].sum() - raw.loc['built after seeing cards', p]
                              / raw.loc['built after seeing cards'].sum()),
                        adj=r(est[pe, j] - est[se_, j]), lo=r(np.quantile(dv, .025)), hi=r(np.quantile(dv, .975)))
        print('   pre-emptive minus after seeing, %s: raw %+.3f, balanced %+.3f [%+.3f, %+.3f]'
              % (p, diffs[p]['raw'], diffs[p]['adj'], diffs[p]['lo'], diffs[p]['hi']))
    out['manualPosAdj'] = dict(rows=rows, diffs=diffs, boot=int(len(bs)), model=F.replace('y ~ ', ''))

    # ── P5d · is the card → Suggest link the mission's complexity? (f-size-decides#route-people) ─────
    # People who pair the tiers describe a whole-mission rule ('one colour I do myself, several I hand over'). The route
    # model holds drones needed; add one-type-or-not and number of tasks (both within and between person).
    print('\nP5d card -> Suggest, also holding drone types and tasks')
    d = T[T.ndrones > 0].copy()
    d['card'] = (d.strategy != 'Manual').astype(int)
    d['one'] = (d.ncolours == 1).astype(int)
    base = centre(centre(centre(centre(d, 'card'), 'l2d'), 'one'), 'ntasks')
    rt = {}
    for key, f in (('size', 'consulted ~ card_w + card_pm + l2d_w + l2d_pm + C(game) + C(run)'),
                   ('types', 'consulted ~ card_w + card_pm + l2d_w + l2d_pm + one_w + one_pm + C(game) + C(run)'),
                   ('typesTasks', 'consulted ~ card_w + card_pm + l2d_w + l2d_pm + one_w + one_pm + ntasks_w + ntasks_pm + C(game) + C(run)')):
        rt[key] = gee_terms(base, f, ['card_w'])['card_w']
        print('   %-10s card vs hand OR %s [%s, %s] p %s' % (key, rt[key]['est'], rt[key]['lo'], rt[key]['hi'], rt[key]['p']))
    out['routeTypes'] = rt
    return out


def main():
    if '--p5' in sys.argv:          # just the pass-5 block, patched into the existing handover.json
        S, T, P, who = load()
        prev = json.loads(OUT.read_text(encoding='utf-8'))
        section_size(S, T, who)     # adds the derived columns the later blocks use
        prev['p5'] = clean(section_pass5(S, T))
        OUT.write_text(json.dumps(prev, ensure_ascii=False, allow_nan=False, separators=(',', ':'), default=lambda o: o.item()
                                  if hasattr(o, 'item') else str(o)), encoding='utf-8')
        print('wrote p5 into', OUT.relative_to(BASE))
        return
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
    out['p3'] = section_pass3(S, T, P, PT, who)
    out['p4'] = section_pass4(who)
    out['p5'] = section_pass5(S, T)
    out['who'] = {c: who[c] for c in ('C03', 'C04', 'C05', 'C06', 'C07', 'C08', 'C09', 'C10', 'C22')}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(clean(out), ensure_ascii=False, allow_nan=False, separators=(',', ':'), default=lambda o: o.item()
                              if hasattr(o, 'item') else str(o)), encoding='utf-8')
    print('\nwrote', OUT.relative_to(BASE), '(%.0f kB)' % (OUT.stat().st_size / 1024))


if __name__ == '__main__':
    main()
