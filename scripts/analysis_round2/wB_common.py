#!/usr/bin/env python3
"""Workstream B (round 2) -- shared loaders, load measures, bias-reduced GEE and robustness gates.

Builds on round-1 H9 (`scripts/analysis_round1/h9_workload_speed.py`): its `load_all()` gives the
strategic-decision / tactical-confirm / recovery tables (cross-checked there against the builder's
`load_decisions()`), and its forced-wait conventions are kept:
  * strategic cards cannot be applied until `deployEnabledAtMs` (the slower card's reveal);
  * tactical Suggest reveals 1 (task, drone) entry per second and Deploy waits for it
    (`MapDisplay.tsx` ~l.965, SUGGEST_REVEAL_S = 1.0).

Added here: the game state at ANY moment (the context of the last logged event at or before t --
`state_snapshot` every 10 s bounds staleness), drone failures in a trailing window, the age of the
oldest mission still waiting for a strategic decision, and per-colour reserve slack.

Read-only on Results/.  P09 excluded (inherited from build_findings_synthesis.EXCLUDE).
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
sys.path.insert(0, str(BASE / 'scripts' / 'analysis_round1'))

import h9_workload_speed as h9  # noqa: E402
from build_findings_synthesis import EXCLUDE  # noqa: E402
from agent_scenario_stats import vrank  # noqa: E402

warnings.filterwarnings('ignore')
PARTICIPANTS = BASE / 'Results' / 'Participants'
V112 = vrank('study-v1.12')
SWAPPED = {'P31', 'P32', 'P33', 'P34', 'P35', 'P36'}
SUGGEST_REVEAL_S = h9.SUGGEST_REVEAL_S
FINAL_WINDOW_S = 90.0
SESSION_S = 480.0
COLOURS = ('Blue', 'Red', 'Green')


# ════════════════════════════════════════════════════════════════════════════════════════════
# Session timelines: state at any moment
# ════════════════════════════════════════════════════════════════════════════════════════════

class Timeline:
    """Everything needed to ask 'what was the game state at session time t (ms)?'."""

    def __init__(self, pid, run, evs):
        self.pid, self.run = pid, run
        evs = [e for e in evs if e.get('timestamp') is not None]
        self.ts = [e['timestamp'] for e in evs]
        self.ctx = [e.get('context') or {} for e in evs]
        self.res = [e.get('reserveStateAvailable') or e.get('reserveState') or {} for e in evs]
        self.failures = sorted(e['timestamp'] for e in evs if e['type'] == 'drone_failure')
        self.arrivals = {}          # missionId -> arrival ts
        self.residual = set()
        self.chosen = {}            # missionId -> first strategic_choice ts
        self.ended = {}             # missionId -> mission_completed / abandoned ts
        for e in evs:
            t, m = e['type'], e.get('missionId')
            if t == 'mission_arrived':
                self.arrivals[m] = e['timestamp']
                if e.get('isResidual') or (m or '').endswith('-R'):
                    self.residual.add(m)
            elif t == 'strategic_choice':
                self.chosen.setdefault(m, e['timestamp'])
            elif t in ('mission_completed', 'mission_abandoned'):
                self.ended.setdefault(m, e['timestamp'])
        self.genuine_arrivals = sorted(a for m, a in self.arrivals.items() if m not in self.residual)

    def _i(self, t):
        return bisect.bisect_right(self.ts, t) - 1

    def context_at(self, t):
        i = self._i(t)
        return self.ctx[i] if i >= 0 else {}

    def reserve_at(self, t):
        i = self._i(t)
        return self.res[i] if i >= 0 else {}

    def failures_in(self, t, window_s):
        lo = bisect.bisect_left(self.failures, t - window_s * 1000)
        hi = bisect.bisect_left(self.failures, t)
        return hi - lo

    def arrivals_in(self, t, window_s):
        lo = bisect.bisect_left(self.genuine_arrivals, t - window_s * 1000)
        hi = bisect.bisect_left(self.genuine_arrivals, t)
        return hi - lo

    def waiting(self, t, exclude=None):
        """Missions arrived by t still waiting for a strategic decision (not chosen, not ended)."""
        out = []
        for m, a in self.arrivals.items():
            if m == exclude or a > t:
                continue
            if self.chosen.get(m, np.inf) <= t or self.ended.get(m, np.inf) <= t:
                continue
            out.append((m, a))
        return out

    def oldest_wait_s(self, t, exclude=None):
        w = self.waiting(t, exclude)
        return max((t - a) / 1000.0 for _, a in w) if w else 0.0

    def state(self, t, exclude=None):
        c = self.context_at(t)
        return dict(st_queued=len(self.waiting(t, exclude)),
                    st_tacPending=len([x for x in (c.get('tacticalPendingMissionIds') or []) if x != exclude]),
                    st_active=c.get('missionsActive'),
                    st_dronesAvail=c.get('dronesAvailable'),
                    st_oldest=self.oldest_wait_s(t, exclude),
                    st_fail60=self.failures_in(t, 60),
                    st_arr60=self.arrivals_in(t, 60))


def load_timelines():
    tl = {}
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, raw in enumerate(log['sessions'], start=1):
            tl[(pid, run)] = Timeline(pid, run, list(raw))
    return tl


def _raw_extras():
    """Per strategic decision: card previews before the choice. Per tactical confirm: nothing extra."""
    prev = {}
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, raw in enumerate(log['sessions'], start=1):
            cur = {}
            for e in raw:
                m = e.get('missionId')
                if e['type'] == 'strategic_modal_opened':
                    cur[m] = set()
                elif e['type'] == 'strategic_card_previewed' and m in cur:
                    cur[m].add(e.get('strategyName'))
                elif e['type'] == 'strategic_choice' and m in cur:
                    prev[(pid, run, m, e['timestamp'])] = len(cur.pop(m))
    return prev


# ════════════════════════════════════════════════════════════════════════════════════════════
# The decision tables with every load measure attached
# ════════════════════════════════════════════════════════════════════════════════════════════

def within(df, var, by='pid'):
    df[var + '_pm'] = df.groupby(by)[var].transform('mean')
    df[var + '_w'] = df[var] - df[var + '_pm']
    return df


def add_order(df):
    first = df[df.run == 1].groupby('pid').scenario.first()
    df['order'] = df.pid.map(first).map({'strategic': 'SH-first', 'tactical': 'TH-first'})
    return df


def build():
    S, T, R, M, SESS = h9.quiet(h9.load_all)
    h9.crosscheck(S)
    S = h9.prep_strat(S)
    T = h9.prep_tac(T)
    tl = load_timelines()
    prev = _raw_extras()

    # ---- strategic decisions: load at the (last) panel open ------------------------------------
    rows = []
    for r in S.itertuples():
        t = tl[(r.pid, r.run)]
        st = t.state(r.open_ts, exclude=r.missionId)
        rows.append(dict(st, colslack=np.nan, previews=prev.get((r.pid, r.run, r.missionId, r.choice_ts), 0),
                         recPend=r.recPending))
    X = pd.DataFrame(rows, index=S.index)
    S = pd.concat([S, X], axis=1)
    # per-colour slack: available minus primary need, minimum over the colours the mission needs
    need = _needs()
    sl = []
    for r in S.itertuples():
        res = tl[(r.pid, r.run)].reserve_at(r.open_ts)
        req = need.get((r.pid, r.run, r.missionId), {})
        vals = [res.get(c, 0) - req[c] for c in COLOURS if req.get(c, 0) > 0]
        sl.append(min(vals) if vals else np.nan)
    S['colslack'] = sl
    S['early'] = S.early.fillna(False).astype(bool).astype(int)   # pre-emptive manual (before cards readable)
    S['final90'] = (S.elapsed_open >= SESSION_S - FINAL_WINDOW_S).astype(int)
    S['threetype'] = (S.ncolours == 3).astype(int)
    S['net'] = np.where(S.took == 1, S.secs - S.deployEnabled, S.secs)
    S['lsecs'] = np.log(S.secs.clip(lower=0.5))
    S['lnet'] = np.log(S.net.clip(lower=0.5))
    S['bothprev'] = (S.previews >= 2).astype(int)
    S['anyprev'] = (S.previews >= 1).astype(int)
    S['emin'] = S.elapsed_open / 60.0
    S = add_order(S)

    # ---- tactical confirms: load at tactical_opened and at the first planner action -----------
    T = T.copy()
    T['first_ts'] = T.open_ts + (T.idleBefore.fillna(T.secs) * 1000.0)
    rows = []
    for r in T.itertuples():
        t = tl[(r.pid, r.run)]
        a = t.state(r.open_ts, exclude=r.missionId)
        b = {k.replace('st_', 'fa_'): v for k, v in t.state(r.first_ts, exclude=r.missionId).items()}
        rows.append(dict(a, **b))
    T = pd.concat([T, pd.DataFrame(rows, index=T.index)], axis=1)
    # the mission's own wait from arrival to its first strategic open (from the strategic table)
    fw = S.drop_duplicates(['pid', 'run', 'missionId']).set_index(['pid', 'run', 'missionId']).firstWait
    T['firstWait'] = [fw.get((p, r_, m), np.nan) for p, r_, m in zip(T.pid, T.run, T.missionId)]
    T['final90'] = (T.elapsed_open >= SESSION_S - FINAL_WINDOW_S).astype(int)
    T['threetype'] = (T.ncolours == 3).astype(int)
    T['emin'] = T.elapsed_open / 60.0
    # checking time after the Suggest reveal finished (kept plans): confirm - (last Suggest + entries*1s)
    T['postReveal'] = T.afterLastSuggest - T.entries * SUGGEST_REVEAL_S
    T['lpostReveal'] = np.log(T.postReveal.clip(lower=0.5))
    T['lastSuggest_ts'] = T.confirm_ts - T.afterLastSuggest * 1000.0
    rows = []
    for r in T.itertuples():
        if np.isfinite(r.lastSuggest_ts):
            st = tl[(r.pid, r.run)].state(r.lastSuggest_ts, exclude=r.missionId)
        else:
            st = {k: np.nan for k in tl[(r.pid, r.run)].state(0).keys()}
        rows.append({k.replace('st_', 'ls_'): v for k, v in st.items()})
    T = pd.concat([T, pd.DataFrame(rows, index=T.index)], axis=1)
    T = add_order(T)
    return S, T, R, tl


def _needs():
    out = {}
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        starts = [e for s in log['sessions'] for e in s if e['type'] == 'session_start']
        primary = starts[0]['taskPrimary']
        for run, raw in enumerate(log['sessions'], start=1):
            for e in raw:
                if e['type'] == 'mission_arrived':
                    tot = {c: 0 for c in COLOURS}
                    for task in e.get('tasks', []):
                        for c, n in primary[str(task['type'])].items():
                            tot[c] += n
                    out[(pid, run, e['missionId'])] = tot
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# Models, the spec table and the gates
# ════════════════════════════════════════════════════════════════════════════════════════════

SPEC_COLS = ['workstream', 'variant_id', 'extra', 'description', 'sample', 'outcome', 'predictor', 'model',
             'estimate', 'ci_lo', 'ci_hi', 'estimate_scale', 'p', 'n_obs', 'n_people', 'expected_direction',
             's1_same_direction', 'both_orders_same_direction', 'loo_sign_flip', 'notes']


def gee_br(formula, data, binomial):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    mod = smf.gee(formula, 'pid', data=data, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return mod.fit(cov_type='bias_reduced')


def _prep(df, centre, need):
    d = df.dropna(subset=need).copy()
    for v in centre:
        d = within(d, v)
    return d


def fit_term(df, y, rhs, coef, centre, binomial):
    """Fit y ~ rhs on df, re-centring `centre` vars within person on THIS sample. Returns (b, lo, hi, p, n, k)."""
    need = [y] + [c for c in df.columns if c in rhs.replace('*', ' ').replace(':', ' ').replace('+', ' ').split()]
    need += [v for v in centre]
    d = _prep(df, centre, list(dict.fromkeys(need)))
    if d[y].nunique() < 2 or d.pid.nunique() < 4:
        return None
    # Where game determines run (S-27, or one scenario order: unswapped players' game index IS the run),
    # C(game) + C(run) is collinear and the bias-reduced covariance cannot be formed. Run is then
    # redundant given game, so drop it.
    if 'C(run)' in rhs and 'C(game)' in rhs and             d.groupby('game').run.nunique().max() == 1:
        rhs = _drop_run(rhs)
    try:
        m = gee_br('%s ~ %s' % (y, rhs), d, binomial)
        b = float(m.params[coef])
        se = float(m.bse[coef])
        p = float(m.pvalues[coef])
    except Exception as ex:  # reported as NA, never hidden
        print('   fit failed (%s): %s' % (coef, ex))
        return None
    if not np.isfinite(se):
        return None
    return dict(b=b, lo=b - 1.959964 * se, hi=b + 1.959964 * se, p=p, n=len(d), k=d.pid.nunique(), data=d)


def _drop_run(rhs):
    return rhs.replace(' + C(run)', '').replace('C(run) + ', '')


class Specs:
    def __init__(self, workstream='B'):
        self.rows = []
        self.ws = workstream

    def run(self, vid, desc, sample, df, y, rhs, coef, centre=(), binomial=True, expected='+',
            extra=0, scale=1.0, model=None, gates=True, loo=None, notes='', predictor=None):
        """One spec-table row. Gates: s1 / both orders always (if gates), LOO when p < .10 (or loo=True)."""
        if sample == 'S-s1':
            rhs = _drop_run(rhs)
        r = fit_term(df, y, rhs, coef, list(centre), binomial)
        row = dict(workstream=self.ws, variant_id=vid, extra=extra, description=desc, sample=sample,
                   outcome=y, predictor=predictor or coef,
                   model=model or ('GEE logit, exch., bias-reduced: %s ~ %s' % (y, rhs) if binomial
                                   else 'GEE gaussian, exch., bias-reduced: %s ~ %s' % (y, rhs)),
                   expected_direction=expected, notes=notes)
        if r is None:
            row.update(estimate=np.nan, ci_lo=np.nan, ci_hi=np.nan, estimate_scale='OR' if binomial else 'b',
                       p=np.nan, n_obs=0, n_people=0, s1_same_direction='na', both_orders_same_direction='na',
                       loo_sign_flip='na', notes=(notes + ' | model not estimable').strip(' |'))
            self.rows.append(row)
            print('%-10s %-55s NA' % (vid, desc[:55]))
            return row
        f = np.exp if binomial else (lambda x: x)
        row.update(estimate=f(r['b'] * scale), ci_lo=f(r['lo'] * scale), ci_hi=f(r['hi'] * scale),
                   estimate_scale='OR' if binomial else 'b', p=r['p'], n_obs=r['n'], n_people=r['k'])
        sign = np.sign(r['b'])
        s1 = orders = lo_flip = 'na'
        if gates and sample not in ('S-s1', 'S-6'):
            d = df
            r1 = fit_term(d[d.run == 1], y, _drop_run(rhs), coef, list(centre), binomial)
            s1 = 'na' if r1 is None else int(np.sign(r1['b']) == sign)
            if 'order' in d.columns:
                o = []
                for g in ('SH-first', 'TH-first'):
                    ro = fit_term(d[d.order == g], y, rhs, coef, list(centre), binomial)
                    o.append(None if ro is None else np.sign(ro['b']) == sign)
                orders = 'na' if None in o else int(all(o))
            do_loo = loo if loo is not None else (r['p'] < 0.10)
            if do_loo:
                ests = []
                for pid in sorted(d.pid.unique()):
                    rl = fit_term(d[d.pid != pid], y, rhs, coef, list(centre), binomial)
                    if rl is not None:
                        ests.append(rl['b'])
                ests = np.array(ests)
                lo_flip = int((np.sign(ests) != sign).any())
                row['notes'] = (row['notes'] + ' | LOO range %s %.3f-%.3f' % (
                    'OR' if binomial else 'b', f(ests.min() * scale), f(ests.max() * scale))).strip(' |')
        row.update(s1_same_direction=s1, both_orders_same_direction=orders, loo_sign_flip=lo_flip)
        self.rows.append(row)
        print('%-10s %-55s %s %.3f [%.3f, %.3f] p=%.4f n=%d/%d  s1=%s ord=%s loo=%s'
              % (vid, desc[:55], row['estimate_scale'], row['estimate'], row['ci_lo'], row['ci_hi'], r['p'],
                 r['n'], r['k'], s1, orders, lo_flip))
        return row

    def add(self, **kw):
        row = {c: kw.get(c, 'na' if c in ('s1_same_direction', 'both_orders_same_direction', 'loo_sign_flip')
                         else '') for c in SPEC_COLS}
        row['workstream'] = self.ws
        self.rows.append(row)
        return row

    def frame(self):
        return pd.DataFrame(self.rows)[SPEC_COLS]


def samples(df):
    """The briefing's sample codes -> subsets (re-centring happens inside fit_term)."""
    return {'S-all': df,
            'S-v112': df[df.vrank >= V112],
            'S-s1': df[df.run == 1],
            'S-27': df[~df.pid.isin(SWAPPED)]}


def tactical_all():
    """Every NON-recovery tactical planner opened, confirmed or not (15 opened in the final 90 s were cut
    off by the session end). consultedAny = Suggest pressed in it at least once. Built to check that a
    final-90-s result is not produced by dropping unconfirmed plans."""
    need = _needs()
    rows = []
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, raw in enumerate(log['sessions'], start=1):
            st = next((e for e in raw if e['type'] == 'session_start'), {})
            scen, ver = st.get('complexity'), st.get('appVersion')
            game = '%s|%s' % (scen, st.get('planSeedIndex') or run)
            op = {}
            for e in raw:
                m, t = e.get('missionId'), e['type']
                if t == 'tactical_opened':
                    op[m] = dict(pid=pid, run=run, missionId=m, scenario=scen, version=ver, game=game,
                                 open_ts=e['timestamp'], pool=len(e.get('dronePool') or []),
                                 ntasks=len(e.get('agentPlan') or []), sug=0)
                elif t == 'tactical_suggest_used' and not e.get('recoveryMode') and m in op:
                    op[m]['sug'] += 1
                elif t in ('tactical_confirmed', 'mission_abandoned') and m in op:
                    o = op.pop(m)
                    o['confirmed'] = int(t == 'tactical_confirmed')
                    rows.append(o)
            for o in op.values():
                o['confirmed'] = 0
                rows.append(o)
    D = pd.DataFrame(rows)
    D['consultedAny'] = (D.sug > 0).astype(int)
    D['ncolours'] = [sum(1 for v in need.get((p, r, m), {}).values() if v > 0)
                     for p, r, m in zip(D.pid, D.run, D.missionId)]
    D['lplan'] = np.log((D.pool * D.ntasks).clip(lower=1))
    D['elapsed_open'] = D.open_ts / 1000.0
    D['emin'] = D.elapsed_open / 60.0
    D['final90'] = (D.elapsed_open >= SESSION_S - FINAL_WINDOW_S).astype(int)
    D['vrank'] = D.version.map(vrank)
    return add_order(D)
