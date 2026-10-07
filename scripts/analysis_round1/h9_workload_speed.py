#!/usr/bin/env python3
"""H9 -- Does momentary workload push operators onto the assistant?  (+ speed vs accuracy)

Pre-registered in docs/analysis/HYPOTHESES_ROUND1.md (H9, amended 2026-10-07).

PRIMARY (confirmatory, exactly as specified):
    GEE logit (binomial, exchangeable, clustered on participant) of card-taking at a strategic
    decision on the number of OTHER missions queued when the strategic panel opened, centred
    within person, with the person mean as a covariate, controlling for composition (ncolours,
    ndrones), scenario and run.  Support = OR > 1 per extra queued mission, 95% CI excluding 1.
    Primary on all 33 (P09 excluded); sensitivity on study-v1.12+ (n = 24).

Everything else printed here is exploratory and labelled as such.

Read-only on Results/.  Run from the repo root:
    C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h9_workload_speed.py
"""
from __future__ import annotations

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
from scipy import stats

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))

# Reuse the canonical helpers (HYPOTHESES_ROUND1 §1): gee/term and the strategic decision table
# from the synthesis builder, spearman from study_analysis, version ranks from agent_scenario_stats.
from build_findings_synthesis import (load_decisions, load_people, gee, term,  # noqa: E402
                                      load_quotes, EXCLUDE)
from study_analysis import spearman  # noqa: E402
from agent_scenario_stats import vrank, events  # noqa: E402

PARTICIPANTS = BASE / 'Results' / 'Participants'
V112 = vrank('study-v1.12')
SUGGEST_REVEAL_S = 1.0   # MapDisplay.tsx progressive reveal: one (task, drone) entry per 1000 ms,
                         # unchanged since before study-v1.0 (git log -L on that effect).

warnings.filterwarnings('ignore')   # GEE/statsmodels convergence chatter; fits are checked below


def quiet(fn):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn()


def hdr(s):
    print('\n' + '=' * 100 + '\n' + s + '\n' + '=' * 100)


def fmt_or(t, scale=1.0):
    """term() dict -> 'OR [lo, hi] p' on the odds-ratio scale (per `scale` units)."""
    return 'OR %.3f [%.3f, %.3f]  p=%.4f' % (np.exp(t['b'] * scale), np.exp(t['lo'] * scale),
                                             np.exp(t['hi'] * scale), t['p'])


def fmt_b(t, unit=''):
    return 'b=%+.3f%s [%+.3f, %+.3f]  p=%.4f' % (t['b'], unit, t['lo'], t['hi'], t['p'])


def within(df, var, by='pid'):
    df[var + '_pm'] = df.groupby(by)[var].transform('mean')
    df[var + '_w'] = df[var] - df[var + '_pm']
    return df


# ════════════════════════════════════════════════════════════════════════════════════════════
# 1 · Loading: one row per strategic decision / tactical confirm / recovery episode / mission
# ════════════════════════════════════════════════════════════════════════════════════════════

def ctx_fields(e, prefix):
    c = e.get('context') or {}
    return {prefix + 'queued': c.get('missionsQueued'),
            prefix + 'active': c.get('missionsActive'),
            prefix + 'tacPending': len(c.get('tacticalPendingMissionIds') or []),
            prefix + 'recPending': len(c.get('recoveryPendingMissionIds') or []),
            prefix + 'tasksPending': c.get('tasksPending'),
            prefix + 'tasksExecuting': c.get('tasksExecuting'),
            prefix + 'dronesAvail': c.get('dronesAvailable'),
            prefix + 'tacPendingIds': list(c.get('tacticalPendingMissionIds') or [])}


def load_all():
    strat, tac, rec, missions, sessions = [], [], [], [], []
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        starts = [e for s in log['sessions'] for e in s if e['type'] == 'session_start']
        if not starts:
            continue
        primary = starts[0]['taskPrimary']
        for run, raw in enumerate(log['sessions'], start=1):
            evs = list(raw)
            # load_decisions() iterates in file order; the analysis relies on seq order. Assert equal.
            assert [e.get('seq') for e in evs] == [e.get('seq') for e in events(raw)], (pid, run)
            st = next((e for e in evs if e['type'] == 'session_start'), {})
            scenario, version = st.get('complexity'), st.get('appVersion')
            plan_index = st.get('planSeedIndex') or run
            sessions.append(dict(pid=pid, run=run, scenario=scenario, version=version,
                                 planIndex=plan_index))
            arrivals = []            # (ts, missionId, isResidual)
            arr_ts, need, ntasks, residual = {}, {}, {}, set()
            pending, first_open, n_open = {}, {}, {}
            tac_open, sugg, drags, interleave = {}, {}, {}, {}
            strat_choice_ts, completed = {}, {}
            open_rec = {}
            idx, last_took = 0, None
            for e in evs:
                t, m, ts = e['type'], e.get('missionId'), e.get('timestamp')
                if t == 'mission_arrived':
                    arrivals.append((ts, m, bool(e.get('isResidual'))))
                    arr_ts[m] = ts
                    ntasks[m] = len(e.get('tasks', []))
                    if e.get('isResidual') or (m or '').endswith('-R'):
                        residual.add(m)
                    tot = {'Blue': 0, 'Red': 0, 'Green': 0}
                    for task in e.get('tasks', []):
                        for col, n in primary[str(task['type'])].items():
                            tot[col] += n
                    need[m] = tot
                elif t == 'strategic_modal_opened':
                    # every other open tactical planner counts as "interleaved" work
                    for om in tac_open:
                        if om != m:
                            interleave[om] = interleave.get(om, 0) + 1
                    req = need.get(m)
                    cards = {c['name']: c for c in e.get('strategiesPresented', [])}
                    first_open.setdefault(m, e)
                    n_open[m] = n_open.get(m, 0) + 1
                    if not req or len(cards) < 2:
                        continue
                    # the LAST open before the choice, as load_decisions() keeps it
                    pending[m] = dict(open_ts=ts, ev=e, req=req,
                                      reveal=max(c['revealDelayMs'] for c in cards.values()))
                elif t == 'strategic_choice' and m in pending:
                    p = pending.pop(m)
                    o = p['ev']
                    req = p['req']
                    choice = e.get('choiceType')
                    fo = first_open[m]
                    recent = lambda w: sum(1 for (a, mm, r) in arrivals
                                           if not r and p['open_ts'] - w * 1000 <= a < p['open_ts'])
                    row = dict(
                        pid=pid, run=run, scenario=scenario, version=version, planIndex=plan_index,
                        game='%s|%s' % (scenario, plan_index), idx=idx, missionId=m,
                        choice=choice, took=int(choice in ('aggressive', 'conservative')),
                        manual=int(choice == 'manual'), early=e.get('manualBeforeCardsLoaded'),
                        edited=int(e.get('editedFromStrategy') is not None),
                        ncolours=sum(1 for c in req if req[c] > 0), ndrones=sum(req.values()),
                        ntasks=ntasks.get(m), residual=int(m in residual),
                        reveal=p['reveal'] / 1000.0,
                        deployEnabled=(e.get('deployEnabledAtMs') or 0) / 1000.0,
                        latency=(e.get('latencyMs') or 0) / 1000.0,
                        secs=(ts - p['open_ts']) / 1000.0,
                        open_ts=p['open_ts'], choice_ts=ts, elapsed_open=p['open_ts'] / 1000.0,
                        wait=(p['open_ts'] - arr_ts[m]) / 1000.0 if m in arr_ts else np.nan,
                        firstWait=(fo['timestamp'] - arr_ts[m]) / 1000.0 if m in arr_ts else np.nan,
                        nOpens=n_open[m],
                        arrivals60=recent(60), arrivals120=recent(120), arrivals30=recent(30),
                        prevTook=last_took,
                        reserveTotal=sum((o.get('reserveStateAvailable') or o.get('reserveState')
                                          or {}).values()),
                        **ctx_fields(o, ''),
                        **{k: v for k, v in ctx_fields(fo, 'first_').items()})
                    strat.append(row)
                    strat_choice_ts[m] = ts
                    last_took = row['took']
                    idx += 1
                elif t == 'tactical_opened':
                    plan = e.get('agentPlan') or []
                    tac_open[m] = dict(ts=ts, ev=e, pool=len(e.get('dronePool') or []),
                                       arr60=sum(1 for (a, mm, r) in arrivals
                                                 if not r and ts - 60000 <= a < ts),
                                       ntasks_plan=len(plan),
                                       entries=sum(len(s.get('assetIds') or []) for s in plan),
                                       strategy=e.get('strategyChosen'))
                    sugg[m], drags[m], interleave[m] = [], [], 0
                elif t == 'tactical_suggest_used' and not e.get('recoveryMode'):
                    if m in tac_open:
                        sugg[m].append(ts)
                    elif m in open_rec:
                        pass
                elif t == 'tactical_assignment_changed' and not e.get('recoveryMode'):
                    if m in tac_open:
                        drags[m].append(ts)
                elif t == 'tactical_confirmed' and m in tac_open:
                    o = tac_open.pop(m)
                    s_ts, d_ts = sugg.pop(m, []), drags.pop(m, [])
                    first_int = min(s_ts[:1] + d_ts[:1]) if (s_ts or d_ts) else None
                    consulted = (e.get('suggestUsedCount') or 0) > 0
                    agent_plan = e.get('agentPlan')
                    unmod = int(consulted and bool(agent_plan) and not e.get('modifiedFromAgentPlan'))
                    tac.append(dict(
                        pid=pid, run=run, scenario=scenario, version=version, planIndex=plan_index,
                        game='%s|%s' % (scenario, plan_index), missionId=m,
                        residual=int(m in residual),
                        consulted=int(consulted), unmod=unmod,
                        modified=int(bool(e.get('modifiedFromAgentPlan'))),
                        route='hand' if not consulted else ('suggest-kept' if unmod else 'suggest-edited'),
                        hasAgentPlan=int(bool(agent_plan)),
                        nSuggest=e.get('suggestUsedCount') or 0,
                        chaining=int(bool(e.get('chainingUsed'))),
                        latency=(e.get('latencyMs') or 0) / 1000.0,
                        secs=(ts - o['ts']) / 1000.0,
                        engaged=(ts - first_int) / 1000.0 if first_int is not None else np.nan,
                        idleBefore=(first_int - o['ts']) / 1000.0 if first_int is not None else np.nan,
                        afterLastSuggest=(ts - s_ts[-1]) / 1000.0 if s_ts else np.nan,
                        nDrags=len(d_ts), interleaved=interleave.pop(m, 0),
                        pool=o['pool'], ntasks=ntasks.get(m) or o['ntasks_plan'],
                        entries=o['entries'], strategy=o['strategy'],
                        agentProj=e.get('agentProjectedCompletion'),
                        finalProj=e.get('finalProjectedCompletion'),
                        unassigned=len(e.get('unassignedTaskIds') or []),
                        open_ts=o['ts'], confirm_ts=ts, elapsed_open=o['ts'] / 1000.0,
                        arrivals60=o['arr60'],
                        ncolours=sum(1 for c in (need.get(m) or {}).values() if c > 0),
                        ndrones=sum((need.get(m) or {}).values()),
                        **ctx_fields(o['ev'], '')))
                elif t == 'recovery_opened':
                    open_rec[m] = dict(pid=pid, run=run, scenario=scenario, version=version,
                                       missionId=m, open_ts=ts, reason=e.get('recoveryReason'),
                                       elapsed_open=ts / 1000.0,
                                       feasible=int(bool(e.get('feasibleWithOnMissionDrones'))),
                                       onMission=len(e.get('onMissionDroneIds') or []),
                                       suggest=0, **ctx_fields(e, ''))
                elif m in open_rec and t == 'tactical_suggest_used' and e.get('recoveryMode'):
                    open_rec[m]['suggest'] += 1
                elif m in open_rec and t in ('failure_recovery', 'mission_abandoned'):
                    ep = open_rec.pop(m)
                    ep.update(outcome='recovered' if t == 'failure_recovery' else 'abandoned',
                              latency=(ts - ep['open_ts']) / 1000.0,
                              agentPlan=int(bool(e.get('wasAgentSuggested'))))
                    rec.append(ep)
                if t == 'mission_completed':
                    completed[m] = e
            for ep in open_rec.values():
                ep.update(outcome='unresolved', latency=np.nan, agentPlan=0)
                rec.append(ep)
            for m, e in completed.items():
                missions.append(dict(pid=pid, run=run, missionId=m, outcome=e.get('outcome'),
                                     full=int(e.get('outcome') == 'all_completed'),
                                     mpenalty=e.get('penaltyAccrued'),
                                     reward=e.get('rewardEarned'), maxReward=e.get('maxReward'),
                                     completionTime=e.get('completionTime'),
                                     durFromAlloc=e.get('durationFromAllocation'),
                                     timeToAllocate=e.get('timeToAllocate'),
                                     failures=e.get('droneFailureCount') or 0))
    S, T, R, M = (pd.DataFrame(x) for x in (strat, tac, rec, missions))
    for d in (S, T, R):
        d['vrank'] = d.version.map(vrank)
    return S, T, R, M, pd.DataFrame(sessions)


def crosscheck(S):
    """Our strategic table must be the builder's load_decisions() row for row."""
    B = load_decisions()
    a = S[['pid', 'run', 'idx', 'choice', 'ncolours', 'ndrones', 'took', 'manual']].reset_index(drop=True)
    b = B[['pid', 'run', 'idx', 'choice', 'ncolours', 'ndrones', 'took', 'manual']].reset_index(drop=True)
    same = a.equals(b) and np.allclose(S.secs.values, B.secs.values) \
        and np.allclose(S.reveal.values, B.reveal.values / 1000.0)
    print('Cross-check vs build_findings_synthesis.load_decisions(): %d vs %d rows, identical=%s'
          % (len(a), len(b), same))
    assert same
    return B


# ════════════════════════════════════════════════════════════════════════════════════════════
# 2 · Analyses
# ════════════════════════════════════════════════════════════════════════════════════════════

PRIMARY = 'took ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run)'


def prep_strat(S):
    S = S.copy()
    # q = OTHER missions in the queue when the panel opened. context.missionsQueued counts every
    # mission with status 'queued' -- which includes the mission being opened, and missions that
    # have had a strategic choice but whose tactical plan is still unconfirmed.
    S['q'] = S.queued - 1
    S['q_strat'] = S.queued - 1 - S.apply(
        lambda r: len([x for x in r.tacPendingIds if x != r.missionId]), axis=1)
    S['q_first'] = S.first_queued - 1
    S['anyq'] = (S.q > 0).astype(int)
    S = within(S, 'q')
    for v in ('q_strat', 'q_first', 'arrivals60', 'arrivals120', 'arrivals30', 'dronesAvail',
              'reserveTotal', 'tasksPending', 'active', 'anyq'):
        S = within(S, v)
    # within person-SESSION centring (removes scenario/run mean queue completely)
    S['q_ws'] = S.q - S.groupby(['pid', 'run']).q.transform('mean')
    S['q_spm'] = S.groupby(['pid', 'run']).q.transform('mean')
    return S


def prep_strat_light(S):
    """Re-centre q within person on a subset (centring must use the subset's own person means)."""
    return within(S.copy(), 'q')


def fit(formula, data, name, binomial=True, show=('q_w',), scale=1.0):
    try:
        m = quiet(lambda: gee(formula, data, binomial=binomial))
    except Exception as ex:                                     # reported, not hidden
        print('  %-58s FAILED: %s' % (name, ex))
        return None
    out = {}
    for s in show:
        if s in m.params:
            t = term(m, s)
            out[s] = t
            print('  %-58s %-10s %s   n=%d/%d' % (name, s, fmt_or(t, scale) if binomial else fmt_b(t),
                                                   len(data), data.pid.nunique()))
    return out


def detectable_or(t, scale=1.0):
    se = (t['hi'] - t['lo']) / (2 * 1.959964)
    return float(np.exp(2.8 * se * scale))


def section_queue_descriptives(S):
    hdr('A. The load measure: missions queued when the strategic panel opened')
    print('q = context.missionsQueued at the (last) strategic_modal_opened before the choice, minus 1 '
          '(the mission itself).')
    print('Self-check: missionsQueued >= 1 at every open:', bool((S.queued >= 1).all()))
    print('Distribution of q:', S.q.value_counts().sort_index().to_dict())
    for sc, g in S.groupby('scenario'):
        print('  %-9s mean q = %.2f (sd %.2f), any other queued = %.0f%%, mean tactical-pending others = %.2f'
              % (sc, g.q.mean(), g.q.std(), 100 * (g.q > 0).mean(), (g.q - g.q_strat).mean()))
    print('Variance of q: total %.2f, within-person %.2f (%.0f%%), within person-session %.2f (%.0f%%)'
          % (S.q.var(), S.q_w.var(), 100 * S.q_w.var() / S.q.var(), S.q_ws.var(),
             100 * S.q_ws.var() / S.q.var()))
    print('q at the FIRST open vs the last open: equal on %.0f%% of decisions (%d decisions reopened)'
          % (100 * (S.q == S.q_first).mean(), int((S.nOpens > 1).sum())))
    # mechanical links -------------------------------------------------------------------------
    print('\nMechanical links:')
    r = stats.spearmanr(S.q, S.arrivals60)
    print('  q vs arrivals in the previous 60 s (exogenous, fixed by the game): rho=%.3f p=%.2g'
          % (r.correlation, r.pvalue))
    r = stats.spearmanr(S.q, S.elapsed_open)
    print('  q vs time into session: rho=%.3f p=%.2g' % (r.correlation, r.pvalue))
    per = S.groupby('pid').agg(q=('q', 'mean'), took=('took', 'mean'),
                               secs=('secs', 'median'), wait=('wait', 'median'))
    print('  person-level: mean q vs median decision time  %s' % spearman(per.q, per.secs))
    print('  person-level: mean q vs median arrival->open wait %s' % spearman(per.q, per.wait))
    print('  person-level: mean q vs card uptake  %s' % spearman(per.q, per.took))
    # own slowness: time spent on the previous decision (within session) vs queue at this one
    S2 = S.sort_values(['pid', 'run', 'idx']).copy()
    S2['prevSecs'] = S2.groupby(['pid', 'run']).secs.shift()
    d = S2.dropna(subset=['prevSecs'])
    m = quiet(lambda: gee('q ~ prevSecs + C(scenario) + C(run) + idx', d))
    print('  within session: q rises with the previous decision\'s duration: %s per s' % fmt_b(term(m, 'prevSecs')))
    m = quiet(lambda: gee('q ~ prevTook + C(scenario) + C(run) + idx', d.dropna(subset=['prevTook'])))
    print('  within session: q after a taken card vs after manual: %s' % fmt_b(term(m, 'prevTook')))
    print('\nCard uptake by q (raw, all decisions):')
    for k, g in S.groupby(S.q.clip(upper=4)):
        print('  q=%s%s  took=%.2f  n=%d  (single-type share %.2f)' % (k, '+' if k == 4 else ' ', g.took.mean(),
                                                                     len(g), (g.ncolours == 1).mean()))


def section_primary(S, label):
    hdr('B. PRIMARY TEST  [%s]' % label)
    print('Formula: ' + PRIMARY + '   (GEE binomial, exchangeable, cluster = participant)')
    m = quiet(lambda: gee(PRIMARY, S, binomial=True))
    print(m.summary())
    t = term(m, 'q_w')
    print('\n>>> Within-person effect of one extra queued mission: %s' % fmt_or(t))
    print('>>> n decisions = %d, participants = %d' % (len(S), S.pid.nunique()))
    print('>>> 80%%-power detectable OR (two-sided .05) given this SE: %.3f (or %.3f below 1)'
          % (detectable_or(t), 1 / detectable_or(t)))
    print('>>> Verdict: %s' % ('SUPPORTED' if t['lo'] > 0 else 'NOT SUPPORTED'))
    tp = term(m, 'q_pm')
    print('    (person-mean term, between-person: %s)' % fmt_or(tp))
    return t


def section_robustness(S):
    hdr('C. Robustness / alternative specifications of the primary (EXPLORATORY)')
    fit(PRIMARY + ' + idx', S, '+ position in session (idx)')
    fit(PRIMARY + ' + elapsed_open', S, '+ elapsed seconds at open')
    fit(PRIMARY, prep_strat_light(S[S.residual == 0]), 'genuine missions only (residuals dropped)')
    fit('took ~ q_w + q_pm + ncolours + ndrones + C(game) + C(run)', S, 'game fixed effect instead of scenario')
    fit('took ~ q_ws + q_spm + ncolours + ndrones + C(scenario) + C(run)', S,
        'centred within person-SESSION', show=('q_ws',))
    fit('took ~ q_strat_w + q_strat_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'queue excluding tactical-pending missions', show=('q_strat_w',))
    fit('took ~ q_first_w + q_first_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'queue at FIRST open of this mission', show=('q_first_w',))
    fit('took ~ anyq_w + anyq_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'binary: any other mission queued', show=('anyq_w',))
    d = S.dropna(subset=['prevTook'])
    fit(PRIMARY + ' + prevTook', d, '+ previous decision\'s choice (state dependence)')
    fit('took ~ q_w + q_pm + C(ncolours) + ndrones + C(scenario) + C(run)', S, 'ncolours as categorical')
    # exogenous load: arrivals in the preceding window -- fixed by the game's seeded arrival
    # schedule, so it cannot be built by the operator's own slowness.
    for w in (30, 60, 120):
        v = 'arrivals%d' % w
        fit('took ~ %s_w + %s_pm + ncolours + ndrones + C(scenario) + C(run) + elapsed_open' % (v, v), S,
            'EXOGENOUS: arrivals in previous %ds (+elapsed)' % w, show=(v + '_w',))
    # q split into the exogenous part and the rest
    fit('took ~ q_w + arrivals60_w + q_pm + arrivals60_pm + ncolours + ndrones + C(scenario) + C(run)',
        S, 'q and arrivals60 together', show=('q_w', 'arrivals60_w'))
    # person fixed effects (conditional logit) as a check on the within-person estimate
    try:
        from statsmodels.discrete.conditional_models import ConditionalLogit
        X = pd.get_dummies(S[['q', 'ncolours', 'ndrones', 'scenario', 'run']].astype({'run': str}),
                           drop_first=True).astype(float)
        cl = quiet(lambda: ConditionalLogit(S.took.values, X, groups=S.pid.values).fit(disp=0))
        b, se = cl.params['q'], cl.bse['q']
        print('  %-58s q_w        OR %.3f [%.3f, %.3f]  p=%.4f   n=%d (conditional logit, person FE)'
              % ('person fixed effects (conditional logit)', np.exp(b), np.exp(b - 1.96 * se),
                 np.exp(b + 1.96 * se), cl.pvalues['q'], len(S)))
    except Exception as ex:
        print('  conditional logit failed:', ex)
    # within composition strata (trap 3: drone types is effectively binary)
    for k in (1, 3):
        fit('took ~ q_w + q_pm + ndrones + C(scenario) + C(run)', prep_strat_light(S[S.ncolours == k]),
            'only %d-type missions' % k)
    for sc in ('strategic', 'tactical'):
        fit('took ~ q_w + q_pm + ncolours + ndrones + C(run)', prep_strat_light(S[S.scenario == sc]),
            'only %s scenario' % sc)
    # nonlinearity: q capped
    S = S.copy()
    S['qc'] = S.q.clip(upper=3)
    S = within(S, 'qc')
    fit('took ~ qc_w + qc_pm + ncolours + ndrones + C(scenario) + C(run)', S, 'q capped at 3', show=('qc_w',))
    # unadjusted
    fit('took ~ q_w + q_pm', S, 'no controls', show=('q_w',))
    fit('took ~ q', S, 'raw q, no centring, no controls', show=('q',))


def section_other_strategic_outcomes(S):
    hdr('D. Other strategic outcomes vs queue (EXPLORATORY; D2 added after seeing D1)')
    man = S[S.manual == 1].dropna(subset=['early']).copy()
    man['early'] = man.early.astype(int)
    print('D1. Among manual choices: pre-emptive (before cards readable) vs queue')
    fit('early ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run)', man, 'manual made before cards loaded')
    fit('early ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run) + idx', man, '  ... + idx')
    man = within(man, 'arrivals60')
    fit('early ~ arrivals60_w + arrivals60_pm + ncolours + ndrones + C(scenario) + C(run) + elapsed_open', man,
        '  ... EXOGENOUS arrivals60 (+elapsed)', show=('arrivals60_w',))
    for k in (1, 3):
        fit('early ~ q_w + q_pm + ndrones + C(scenario) + C(run)', within(man[man.ncolours == k].copy(), 'q'),
            '  ... only %d-type missions' % k)
    # D2 (post hoc): every decision is one of four routes; does load move the MIX of manual?
    S = S.copy()
    S['pre'] = ((S.manual == 1) & (S.early == True)).astype(int)            # noqa: E712
    S['post'] = ((S.manual == 1) & (S.early != True) & (S.edited == 0)).astype(int)  # noqa: E712
    print('\nD2. Route shares by q (all decisions):')
    print(S.groupby(S.q.clip(upper=4))[['took', 'pre', 'post', 'edited']].mean().round(3).to_string())
    for y, lab in (('pre', 'pre-emptive manual'), ('post', 'manual after reveal, unedited'),
                   ('edited', 'edited a card')):
        fit(y + ' ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run)', S, lab + ' (all decisions)')
        fit(y + ' ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run) + idx', S, '  ... + idx')
        fit(y + ' ~ arrivals60_w + arrivals60_pm + ncolours + ndrones + C(scenario) + C(run) + elapsed_open', S,
            '  ... EXOGENOUS arrivals60 (+elapsed)', show=('arrivals60_w',))
        fit(y + ' ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run)',
            prep_strat_light(S[S.vrank >= V112]), '  ... v1.12+')
    print('  (edited cards: n=%d decisions, %d people)' % (S.edited.sum(), S[S.edited == 1].pid.nunique()))
    cards = S[S.took == 1].copy()
    cards['aggr'] = (cards.choice == 'aggressive').astype(int)
    fit('aggr ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run)', cards, 'Aggressive (vs Conservative) | card taken')
    fit('edited ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run)', S, 'edited a card')
    print('\nDecision time (s, panel open -> choice) vs queue:')
    fit('secs ~ q_w + q_pm + took + ncolours + ndrones + C(scenario) + C(run)', S, 'secs', binomial=False)


def section_drones(S):
    hdr('E. Drones available as a separate pressure (EXPLORATORY)')
    print('dronesAvail = context.dronesAvailable at panel open (hub inventory); reserveTotal = displayed reserve.')
    print('Distribution by scenario:', S.groupby('scenario').dronesAvail.describe()[['mean', 'std', 'min', 'max']].round(1).to_dict('index'))
    fit('took ~ dronesAvail_w + dronesAvail_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'drones available (per drone)', show=('dronesAvail_w',))
    fit('took ~ dronesAvail_w + dronesAvail_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'drones available (per 5 drones)', show=('dronesAvail_w',), scale=5)
    fit('took ~ q_w + dronesAvail_w + q_pm + dronesAvail_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'q and drones available together', show=('q_w', 'dronesAvail_w'))
    S = S.copy()
    S['slack'] = S.dronesAvail - S.ndrones   # reserve left if the mission took its badge requirement
    S['tight'] = (S.slack < 5).astype(int)
    S = within(S, 'slack'); S = within(S, 'tight')
    fit('took ~ slack_w + slack_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'slack = available - needed (per drone)', show=('slack_w',))
    fit('took ~ tight_w + tight_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'tight reserve (slack < 5)', show=('tight_w',))
    print('  raw uptake when slack<5: %.2f (n=%d) vs >=5: %.2f (n=%d)' % (
        S[S.tight == 1].took.mean(), (S.tight == 1).sum(), S[S.tight == 0].took.mean(), (S.tight == 0).sum()))
    fit('took ~ tasksPending_w + tasksPending_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'tasks pending (all missions)', show=('tasksPending_w',))
    fit('took ~ active_w + active_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'missions active', show=('active_w',))


def prep_tac(T):
    T = T.copy()
    T['q'] = T.queued - 1
    T['plan'] = T.pool * T.ntasks
    T['lplan'] = np.log(T.plan.clip(lower=1))
    T['llat'] = np.log(T.secs.clip(lower=0.5))
    for v in ('q', 'dronesAvail', 'consulted'):
        T = within(T, v)
    return T


def section_tactical(T, R):
    hdr('F. Tactical and recovery reliance vs load (EXPLORATORY)')
    print('Tactical load measured at tactical_opened (= the moment of the strategic choice).')
    print('n confirms = %d, consulted %.2f, kept unmodified (of all) %.2f, of consulted %.2f'
          % (len(T), T.consulted.mean(), T.unmod.mean(), T[T.consulted == 1].unmod.mean()))
    f = '{y} ~ q_w + q_pm + lplan + ncolours + C(scenario) + C(run)'
    fit(f.format(y='consulted'), T, 'consulted Suggest ~ queue')
    fit(f.format(y='unmod'), T, 'kept agent plan unmodified (of all) ~ queue')
    fit(f.format(y='unmod'), T[T.consulted == 1], 'kept unmodified | consulted ~ queue')
    f2 = '{y} ~ dronesAvail_w + dronesAvail_pm + lplan + ncolours + C(scenario) + C(run)'
    fit(f2.format(y='consulted'), T, 'consulted ~ drones available', show=('dronesAvail_w',))
    fit(f2.format(y='unmod'), T[T.consulted == 1], 'kept unmod | consulted ~ drones avail', show=('dronesAvail_w',))
    # queue at CONFIRM is not available (load at decision) -- tactical work is often deferred, so
    # also report the number of other tactical planners open at the time.
    T = within(T.copy(), 'tacPending')
    fit('consulted ~ tacPending_w + tacPending_pm + lplan + ncolours + C(scenario) + C(run)', T,
        'consulted ~ other tactical plans pending', show=('tacPending_w',))
    fit('consulted ~ q_w + q_pm + lplan + ncolours + C(scenario) + C(run)', T[T.vrank >= V112],
        'consulted ~ queue  [v1.12+]')
    print('  -- added after seeing the consult result: is it time-in-session? --')
    fit('consulted ~ q_w + q_pm + lplan + ncolours + C(scenario) + C(run) + elapsed_open', T,
        'consulted ~ queue + elapsed')
    fit('consulted ~ q_w + q_pm + lplan + ncolours + C(game) + C(run)', T, 'consulted ~ queue, game FE')
    fit('consulted ~ q_w + q_pm + lplan + ncolours + C(scenario) + C(run)',
        within(T[T.residual == 0].copy(), 'q'), 'consulted ~ queue, genuine missions')
    T = within(T, 'arrivals60')
    fit('consulted ~ arrivals60_w + arrivals60_pm + lplan + ncolours + C(scenario) + C(run) + elapsed_open', T,
        'consulted ~ EXOGENOUS arrivals60 (+elapsed)', show=('arrivals60_w',))
    fit('consulted ~ elapsed_open + lplan + ncolours + C(scenario) + C(run)', T,
        'consulted ~ elapsed (per minute)', show=('elapsed_open',), scale=60)
    print('  tactical q vs elapsed rho=%.3f' % stats.spearmanr(T.q, T.elapsed_open).correlation)

    R = R.copy()
    print('\nRecovery episodes: n=%d (%d people); Suggest pressed in %.2f; reasons %s'
          % (len(R), R.pid.nunique(), (R.suggest > 0).mean(), R.reason.value_counts().to_dict()))
    R['used'] = (R.suggest > 0).astype(int)
    R['q'] = R.queued
    R = within(R, 'q'); R = within(R, 'dronesAvail'); R = within(R, 'recPending')
    fit('used ~ q_w + q_pm + feasible + C(scenario) + C(run)', R, 'recovery Suggest ~ queue')
    fit('used ~ dronesAvail_w + dronesAvail_pm + feasible + C(scenario) + C(run)', R,
        'recovery Suggest ~ drones available', show=('dronesAvail_w',))
    fit('used ~ q_w + q_pm + feasible + C(scenario) + C(run)', R[R.vrank >= vrank('study-v1.5')],
        'recovery Suggest ~ queue [v1.5+, Suggest exists]')
    fit('used ~ dronesAvail_w + dronesAvail_pm + feasible + C(scenario) + C(run) + elapsed_open', R,
        'recovery Suggest ~ drones available + elapsed', show=('dronesAvail_w',))
    R5 = within(within(R[R.vrank >= vrank('study-v1.5')].copy(), 'dronesAvail'), 'q')
    fit('used ~ dronesAvail_w + dronesAvail_pm + feasible + C(scenario) + C(run)', R5,
        'recovery Suggest ~ drones available [v1.5+]', show=('dronesAvail_w',))
    R12 = within(within(R[R.vrank >= V112].copy(), 'dronesAvail'), 'q')
    fit('used ~ q_w + q_pm + feasible + C(scenario) + C(run)', R12, 'recovery Suggest ~ queue [v1.12+]')
    fit('used ~ dronesAvail_w + dronesAvail_pm + feasible + C(scenario) + C(run)', R12,
        'recovery Suggest ~ drones available [v1.12+]', show=('dronesAvail_w',))
    return T


# ── speed ───────────────────────────────────────────────────────────────────────────────────────

def section_speed_strategic(S, T):
    hdr('G. SPEED 1 -- does taking the card save time at the strategic tier? (EXPLORATORY)')
    S = S.copy()
    # The cards cannot be applied until deployEnabledAtMs (= the slower card's reveal). A manual
    # allocation was never gated (deployEnabledAtMs = 0). net = time the operator controls.
    S['net'] = S.secs - S.deployEnabled
    print('Check: latencyMs == panel-open->choice timestamps: max |diff| = %.3f s'
          % (S.latency - S.secs).abs().max())
    print('Check: deployEnabledAt == max card reveal for card choices: %s'
          % bool(np.allclose(S[S.took == 1].deployEnabled, S[S.took == 1].reveal)))
    print('Check: min card latency - deployEnabled = %.3f s (must be >= 0)' % S[S.took == 1].net.min())
    for lab, g in (('card (as-is)', S[S.took == 1]), ('manual, before cards loaded', S[(S.manual == 1) & (S.early == True)]),  # noqa: E712
                   ('manual, after cards loaded', S[(S.manual == 1) & (S.early != True)])):  # noqa: E712
        print('  %-30s n=%3d  raw median %.1f s  net-of-gate median %.1f s  (mean raw %.1f)'
              % (lab, len(g), g.secs.median(), g.net.median(), g.secs.mean()))
    S = within(S, 'took')
    for y, lab in (('secs', 'raw seconds (incl. forced reveal)'), ('net', 'net of forced reveal')):
        fit(y + ' ~ took_w + took_pm + ncolours + ndrones + C(scenario) + C(run)', S,
            'strategic %s ~ took (within person)' % lab, binomial=False, show=('took_w',))
    S['lsecs'] = np.log(S.secs.clip(lower=0.5))
    fit('lsecs ~ took_w + took_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'log raw seconds ~ took', binomial=False, show=('took_w',))
    # the builder's model for reference (+2.8 s, raw, not within-centred)
    fit('secs ~ manual + ncolours + ndrones + C(scenario)', S, 'builder timing model (manual)', binomial=False,
        show=('manual',))
    # manual after cards loaded only, vs card
    d = S[(S.took == 1) | ((S.manual == 1) & (S.early != True))].copy()  # noqa: E712
    d = within(d, 'took')
    fit('secs ~ took_w + took_pm + ncolours + ndrones + C(scenario) + C(run)', d,
        'raw secs, card vs manual-after-cards-loaded', binomial=False, show=('took_w',))
    for k in (1, 3):
        dd = within(S[S.ncolours == k].copy(), 'took')
        fit('secs ~ took_w + took_pm + ndrones + C(scenario) + C(run)', dd,
            'raw secs ~ took, %d-type missions' % k, binomial=False, show=('took_w',))
        fit('net ~ took_w + took_pm + ndrones + C(scenario) + C(run)', dd,
            'net secs ~ took, %d-type missions' % k, binomial=False, show=('took_w',))

    # panel open -> deployment (tactical confirm), and arrival -> deployment
    hdr('G2. Panel opening -> deployment, and mission arrival -> deployment (EXPLORATORY)')
    J = S.merge(T[['pid', 'run', 'missionId', 'confirm_ts', 'consulted', 'unmod', 'route', 'secs']]
                .rename(columns={'secs': 'tsecs'}), on=['pid', 'run', 'missionId'], how='inner')
    J = J.drop_duplicates(['pid', 'run', 'missionId'], keep='last')
    J['open2deploy'] = (J.confirm_ts - J.open_ts) / 1000.0
    J['arr2deploy'] = J.wait + J.open2deploy
    print('Joined strategic->tactical: %d missions' % len(J))
    for (tk, cs), g in J.groupby(['took', 'consulted']):
        print('  card=%d suggest=%d  n=%3d  open->deploy median %.1f s  arrival->deploy median %.1f s'
              % (tk, cs, len(g), g.open2deploy.median(), g.arr2deploy.median()))
    J = within(J, 'took'); J = within(J, 'consulted')
    J['lplan'] = np.log((J.ndrones * J.ntasks).clip(lower=1))
    for y in ('open2deploy', 'arr2deploy'):
        fit(y + ' ~ took_w + consulted_w + took_pm + consulted_pm + ncolours + ndrones + C(scenario) + C(run)',
            J, y, binomial=False, show=('took_w', 'consulted_w'))
    # does the wait before opening depend on the previous decision's route? (queue spill-over)
    S2 = S.sort_values(['pid', 'run', 'idx']).copy()
    S2['prevTook2'] = S2.groupby(['pid', 'run']).took.shift()
    return J


def section_speed_tactical(T):
    hdr('H. SPEED 2 -- tactical planner: open -> confirm with vs without Suggest (EXPLORATORY)')
    T = T.copy()
    print('Check: latencyMs vs timestamps, max |diff| = %.3f s' % (T.latency - T.secs).abs().max())
    k = T[T.route == 'suggest-kept']
    slack = k.afterLastSuggest - k.entries * SUGGEST_REVEAL_S
    print('Forced Suggest reveal: %d (task,drone) entries on average; confirm - last Suggest - entries*1s:'
          ' min %.1f, 5th pct %.1f, median %.1f s (>= ~0 confirms Deploy waits for the reveal)'
          % (T.entries.mean(), slack.min(), slack.quantile(.05), slack.median()))
    T['net'] = np.where(T.consulted == 1, T.secs - T.entries * SUGGEST_REVEAL_S, T.secs)
    T['lnet'] = np.log(T.net.clip(lower=0.5))
    T['leng'] = np.log(T.engaged.clip(lower=0.5))
    for r, g in T.groupby('route'):
        print('  %-15s n=%3d  open->confirm median %.1f s  idle-before-first-action %.1f s  '
              'engaged (first action->confirm) %.1f s  interleaved %.0f%%  plan size median %d'
              % (r, len(g), g.secs.median(), g.idleBefore.median(), g.engaged.median(),
                 100 * (g.interleaved > 0).mean(), g.plan.median()))
    fit('llat ~ consulted_w + consulted_pm + lplan + C(scenario) + C(run)', T,
        'log(open->confirm) ~ consulted [within, plan size]', binomial=False, show=('consulted_w',))
    fit('lnet ~ consulted_w + consulted_pm + lplan + C(scenario) + C(run)', T,
        'log(net of reveal) ~ consulted', binomial=False, show=('consulted_w',))
    fit('leng ~ consulted_w + consulted_pm + lplan + C(scenario) + C(run)', T.dropna(subset=['leng']),
        'log(engaged time) ~ consulted', binomial=False, show=('consulted_w',))
    fit('secs ~ consulted_w + consulted_pm + lplan + C(scenario) + C(run)', T,
        'open->confirm seconds ~ consulted', binomial=False, show=('consulted_w',))
    # (post hoc, prompted by P15/P27) do Suggest users work on something else while the plan reveals?
    T['inter'] = (T.interleaved > 0).astype(int)
    fit('inter ~ consulted_w + consulted_pm + lplan + llat + C(scenario) + C(run)', T,
        'another strategic panel opened before confirm ~ consulted (| latency)', show=('consulted_w',))
    # route as 3 levels
    T['kept'] = (T.route == 'suggest-kept').astype(int)
    T['edit'] = (T.route == 'suggest-edited').astype(int)
    T = within(T, 'kept'); T = within(T, 'edit')
    fit('llat ~ kept_w + edit_w + kept_pm + edit_pm + lplan + C(scenario) + C(run)', T,
        'log latency: kept / edited vs hand', binomial=False, show=('kept_w', 'edit_w'))
    fit('leng ~ kept_w + edit_w + kept_pm + edit_pm + lplan + C(scenario) + C(run)', T.dropna(subset=['leng']),
        'log engaged: kept / edited vs hand', binomial=False, show=('kept_w', 'edit_w'))
    # interaction with plan size: does Suggest save more on bigger plans?
    T['lplan_c'] = T.lplan - T.lplan.mean()
    fit('llat ~ consulted_w * lplan_c + consulted_pm + C(scenario) + C(run)', T,
        'log latency: consulted x plan size', binomial=False, show=('consulted_w', 'consulted_w:lplan_c'))
    # exact matching: within person x plan-size tercile, compare median latency hand vs suggest
    T['pband'] = pd.qcut(T.plan, 3, labels=['small', 'mid', 'large'])
    rows = []
    for (pid, b), g in T.groupby(['pid', 'pband'], observed=True):
        h, s = g[g.consulted == 0], g[g.consulted == 1]
        if len(h) and len(s):
            rows.append(dict(pid=pid, band=b, d=np.log(s.secs.median()) - np.log(h.secs.median()),
                             de=np.log(s.engaged.median()) - np.log(h.engaged.median())
                             if s.engaged.notna().any() and h.engaged.notna().any() else np.nan))
    M = pd.DataFrame(rows)
    if len(M):
        pp = M.groupby('pid').d.mean()
        w = stats.wilcoxon(pp)
        print('  matched (person x plan-size band) cells: %d cells, %d people; mean log ratio suggest/hand '
              '= %+.3f (x%.2f); per-person Wilcoxon p=%.3g; suggest faster in %d of %d people'
              % (len(M), len(pp), pp.mean(), np.exp(pp.mean()), w.pvalue, int((pp < 0).sum()), len(pp)))
        pe = M.groupby('pid').de.mean().dropna()
        if len(pe) > 5:
            print('  same, engaged time: x%.2f, Wilcoxon p=%.3g, faster in %d of %d'
                  % (np.exp(pe.mean()), stats.wilcoxon(pe).pvalue, int((pe < 0).sum()), len(pe)))
    for b, g in T.groupby('pband', observed=True):
        print('  plan band %-5s  hand median %.1f s (n=%d)  suggest median %.1f s (n=%d)'
              % (b, g[g.consulted == 0].secs.median(), (g.consulted == 0).sum(),
                 g[g.consulted == 1].secs.median(), (g.consulted == 1).sum()))
    return T


def section_pressure_pace(S, T, sess):
    hdr('I. SPEED 3 -- reported time pressure and personal pace vs reliance (EXPLORATORY)')
    P = pd.DataFrame(sess)
    P = P[['pid', 'run', 'scenario', 'version', 'tlx_temporal_demand', 'rtlx', 'took', 'consult', 'accept']]
    print('Session level (66 sessions, not independent):')
    for y in ('took', 'consult', 'accept'):
        print('  temporal demand vs %-8s %s' % (y, spearman(P.tlx_temporal_demand, P[y])))
    per = P.groupby('pid')[['tlx_temporal_demand', 'took', 'consult', 'accept']].mean()
    print('Between person (person means, n=%d):' % len(per))
    for y in ('took', 'consult', 'accept'):
        print('  temporal demand vs %-8s %s' % (y, spearman(per.tlx_temporal_demand, per[y])))
    # within person: change run1 -> run2, with order (scenario sequence) absorbed by an order dummy
    W = P.pivot(index='pid', columns='run', values=['tlx_temporal_demand', 'took', 'consult', 'accept']).dropna()
    first = P[P.run == 1].set_index('pid').scenario
    D = pd.DataFrame({k: W[k][2] - W[k][1] for k in ('tlx_temporal_demand', 'took', 'consult', 'accept')})
    D['SF'] = (first.reindex(D.index) == 'strategic').astype(int)
    print('Within person (run2 - run1, n=%d):' % len(D))
    for y in ('took', 'consult', 'accept'):
        r = spearman(D.tlx_temporal_demand, D[y])
        o = quiet(lambda: smf.ols('%s ~ tlx_temporal_demand + SF' % y, D).fit())
        ci = o.conf_int().loc['tlx_temporal_demand']
        print('  d temporal vs d %-8s %s | OLS +order: b=%+.4f per TLX point [%+.4f, %+.4f] p=%.3f'
              % (y, r, o.params['tlx_temporal_demand'], ci[0], ci[1], o.pvalues['tlx_temporal_demand']))
    # decision level: session temporal demand as predictor of card taking, within person
    S = S.merge(P[['pid', 'run', 'tlx_temporal_demand']], on=['pid', 'run'], how='left')
    S = within(S.dropna(subset=['tlx_temporal_demand']).copy(), 'tlx_temporal_demand')
    fit('took ~ tlx_temporal_demand_w + tlx_temporal_demand_pm + ncolours + ndrones + C(scenario) + C(run)', S,
        'card taking ~ session temporal demand (per 5 TLX points)', show=('tlx_temporal_demand_w', 'tlx_temporal_demand_pm'),
        scale=5)
    # personal pace (between person) -- measured on decisions where the route is held fixed, so it
    # is not mechanically the reliance rate itself
    S['net'] = S.secs - S.deployEnabled
    pace = pd.DataFrame(dict(
        cardNet=S[S.took == 1].groupby('pid').net.median(),
        manNet=S[(S.manual == 1) & (S.early != True)].groupby('pid').secs.median(),   # noqa: E712
        pickUp=S.groupby('pid').firstWait.median(),
        handPerDrone=(T[T.consulted == 0].assign(x=lambda d: d.secs / d.pool)).groupby('pid').x.median(),
        took=S.groupby('pid').took.mean(), consult=T.groupby('pid').consulted.mean(),
        nCard=S[S.took == 1].groupby('pid').size(), nMan=S[(S.manual == 1) & (S.early != True)].groupby('pid').size(),  # noqa: E712
        nHand=T[T.consulted == 0].groupby('pid').size()))
    print('Personal pace (between person):')
    ok = pace[pace.nCard >= 3]
    print('  median net deliberation on CARD choices vs card uptake      %s' % spearman(ok.cardNet, ok.took))
    ok = pace[pace.nMan >= 3]
    print('  median time on post-reveal MANUAL choices vs card uptake    %s' % spearman(ok.manNet, ok.took))
    print('  median arrival->first-open (pick-up speed) vs card uptake   %s' % spearman(pace.pickUp, pace.took))
    print('  median arrival->first-open vs tactical consult rate         %s' % spearman(pace.pickUp, pace.consult))
    ok = pace[pace.nHand >= 3]
    print('  hand-built tactical s/drone vs tactical consult rate        %s' % spearman(ok.handPerDrone, ok.consult))
    return pace


def section_quality(T, M, S):
    hdr('J. SPEED 4 -- speed-quality trade-off: assistant-built vs hand-built plans (EXPLORATORY)')
    T = T.copy()
    T['gap'] = T.finalProj - T.agentProj
    print('agentProjectedCompletion is computed at tactical_opened; finalProjectedCompletion at confirm. '
          'Both are absolute session seconds from the same scheduler, so gap = final - agent includes '
          'both plan quality and any delay in confirming after the drones would have arrived.')
    print('Rows with both projections: %d of %d' % (T.gap.notna().sum(), len(T)))
    for r, g in T.groupby('route'):
        print('  %-15s n=%3d  gap median %+.1f s, mean %+.1f s, share gap>5 s %.2f, share gap<-5 s %.2f, '
              'unassigned tasks>0 %.2f'
              % (r, g.gap.notna().sum(), g.gap.median(), g.gap.mean(), (g.gap > 5).mean(),
                 (g.gap < -5).mean(), (g.unassigned > 0).mean()))
    T['kept'] = (T.route == 'suggest-kept').astype(int)
    T['edit'] = (T.route == 'suggest-edited').astype(int)
    T['hand'] = (T.route == 'hand').astype(int)
    T = within(T, 'kept'); T = within(T, 'edit')
    d = T.dropna(subset=['gap'])
    fit('gap ~ kept_w + edit_w + kept_pm + edit_pm + lplan + C(scenario) + C(run)', d,
        'projected gap (s) ~ route (vs hand)', binomial=False, show=('kept_w', 'edit_w'))
    # (post hoc) the gap grows with confirm delay for KEPT plans too, whose plan is the agent's own,
    # so delay must be held fixed before reading the route term as plan quality.
    k = T[T.route == 'suggest-kept']
    print('  kept plans: gap vs confirm delay rho=%.3f -> gap is mostly delay cost for them'
          % stats.spearmanr(k.secs, k.gap).correlation)
    for lo, hi in ((0, 10), (10, 20), (20, 30), (30, 60), (60, 1e9)):
        g = T[(T.secs >= lo) & (T.secs < hi)]
        a, b = g[g.route == 'suggest-kept'].gap, g[g.route == 'hand'].gap
        print('   confirm delay %3d-%-4s s: kept gap median %+6.1f mean %+6.1f (n=%3d) | hand median %+6.1f '
              'mean %+6.1f (n=%3d), hand share gap>30 s %.2f'
              % (lo, '' if hi > 1e8 else int(hi), a.median(), a.mean(), len(a), b.median(), b.mean(), len(b),
                 (b > 30).mean() if len(b) else np.nan))
    d = within(T[T.route != 'suggest-edited'].dropna(subset=['gap']).copy(), 'hand')
    fit('gap ~ hand_w + hand_pm + bs(secs, df=4) + lplan + C(scenario) + C(run)', d,
        'gap ~ hand-built (vs kept), B-spline in confirm delay', binomial=False, show=('hand_w',))
    for cut in (12, 20):
        dd = within(d[d.secs <= cut].copy(), 'hand')
        fit('gap ~ hand_w + hand_pm + lplan + C(scenario) + C(run)', dd,
            'gap ~ hand-built, only confirms <= %d s' % cut, binomial=False, show=('hand_w',))
    d['big'] = (d.gap > 30).astype(int)
    fit('big ~ hand_w + hand_pm + bs(secs, df=4) + lplan + C(scenario) + C(run)', d,
        'P(gap > 30 s) ~ hand-built, spline in delay', show=('hand_w',))
    # (post hoc) realised analogue of the gap, on missions that ran clean (completed in full, no
    # drone failure), so the realised clock reflects the plan rather than a repair
    Q = T.merge(M, on=['pid', 'run', 'missionId'], how='inner')
    Q = Q[(Q.residual == 0) & (Q.full == 1) & (Q.failures == 0) & (Q.route != 'suggest-edited')].copy()
    Q['rgap'] = Q.completionTime - Q.agentProj      # realised completion minus agent's projection
    Q['rerr'] = Q.completionTime - Q.finalProj      # realised minus the deployed plan's projection
    print('\n  Clean missions (full, no failure): n=%d. Projection error (realised - final projected): '
          'median %+.2f s overall; mean by route %s'
          % (len(Q), Q.rerr.median(), Q.groupby('route').rerr.mean().round(1).to_dict()))
    Q = within(Q, 'hand')
    fit('rgap ~ hand_w + hand_pm + bs(secs, df=4) + lplan + C(scenario) + C(run)', Q,
        'REALISED gap ~ hand-built, spline in delay (clean)', binomial=False, show=('hand_w',))
    fit('gap ~ hand_w + hand_pm + bs(secs, df=4) + lplan + C(scenario) + C(run)', Q,
        'projected gap, same clean missions', binomial=False, show=('hand_w',))
    # actual outcomes
    X = T.merge(M, on=['pid', 'run', 'missionId'], how='left')
    X = X[X.residual == 0]
    print('\nActual outcome (genuine missions; %d with a mission_completed, %d without)'
          % (X.outcome.notna().sum(), X.outcome.isna().sum()))
    for r, g in X.groupby('route'):
        g2 = g.dropna(subset=['outcome'])
        print('  %-15s n=%3d  completed in full %.2f  duration-from-allocation median %.1f s  '
              'mission penalty median %.1f  drone failures/mission %.2f'
              % (r, len(g2), g2.full.mean(), g2.durFromAlloc.median(), g2.mpenalty.median(), g2.failures.mean()))
    Y = X.dropna(subset=['outcome']).copy()
    Y = within(Y, 'kept'); Y = within(Y, 'edit')
    Y['ldur'] = np.log(Y.durFromAlloc.clip(lower=1))
    fit('full ~ kept_w + edit_w + kept_pm + edit_pm + lplan + failures + C(scenario) + C(run)', Y,
        'completed in full ~ route (vs hand)', show=('kept_w', 'edit_w'))
    fit('ldur ~ kept_w + edit_w + kept_pm + edit_pm + lplan + failures + C(scenario) + C(run)', Y,
        'log duration from allocation ~ route', binomial=False, show=('kept_w', 'edit_w'))
    fit('mpenalty ~ kept_w + edit_w + kept_pm + edit_pm + lplan + failures + C(scenario) + C(run)', Y,
        'mission penalty ~ route', binomial=False, show=('kept_w', 'edit_w'))
    # strategic route, the same outcomes (H10 owns the confirmatory version of this)
    Z = S.merge(M, on=['pid', 'run', 'missionId'], how='inner')
    Z = Z[Z.residual == 0].drop_duplicates(['pid', 'run', 'missionId'], keep='last')
    Z = within(Z, 'took')
    Z['ldur'] = np.log(Z.durFromAlloc.clip(lower=1))
    print('\nStrategic route vs outcome (descriptive companion to H10):')
    fit('full ~ took_w + took_pm + ncolours + ndrones + failures + C(scenario) + C(run)', Z,
        'completed in full ~ card', show=('took_w',))
    fit('mpenalty ~ took_w + took_pm + ncolours + ndrones + failures + C(scenario) + C(run)', Z,
        'mission penalty ~ card', binomial=False, show=('took_w',))
    fit('ldur ~ took_w + took_pm + ncolours + ndrones + failures + C(scenario) + C(run)', Z,
        'log duration from allocation ~ card', binomial=False, show=('took_w',))
    return T


SPEED_VALUE = ['P11/verification/1811', 'P20/agent_comparison/1620', 'P22/agent_comparison/1776',
               'P24/verification/1689', 'P26/general_ai_disposition/1828', 'P26/agent_comparison/1717',
               'P28/agent_comparison/1796', 'P28/verification/1833', 'P29/general_ai_disposition/1656',
               'P30/agent_comparison/1540', 'P31/overall_experience/1750', 'P32/scenario_comparison/1497']
SLOW_ASSISTANT = ['P29/manual_override/1469', 'P11/agent_comparison/1781', 'P26/agent_comparison/1717',
                  'P27/design_suggestions/1750', 'P15/agent_comparison/1812', 'P20/agent_comparison/1620']
LOAD_DELEGATION = ['P11/scenario_comparison/1964', 'P18/scenario_comparison/1577',
                   'P32/scenario_comparison/1497', 'P33/verification/1653', 'P35/verification/1729',
                   'P35/agent_comparison/1699', 'P15/agent_comparison/1812', 'P22/agent_comparison/1776',
                   'P24/verification/1660', 'P25/verification/1490']


def section_quotes(S, T):
    hdr('K. Debrief quote IDs on speed / overwhelm (checked to exist; text not printed)')
    q = load_quotes()
    have = {x['id'] for x in q['quotes']}
    print('%d coded quotes from %d debriefs' % (len(q['quotes']), len(q['participants'])))
    per = S.groupby('pid').took.mean()
    con = T.groupby('pid').consulted.mean()
    for name, ids in (('SPEED_VALUE (assistant valued for speed)', SPEED_VALUE),
                      ('SLOW_ASSISTANT (assistant/reveal felt slow)', SLOW_ASSISTANT),
                      ('LOAD_DELEGATION (hand over when overwhelmed)', LOAD_DELEGATION)):
        missing = [i for i in ids if i not in have]
        people = sorted({i.split('/')[0] for i in ids})
        print('  %s: %d quotes, %d people %s; missing ids: %s' % (name, len(ids), len(people), people, missing))
        print('     their card uptake mean %.2f vs others %.2f; tactical consult %.2f vs others %.2f'
              % (per[per.index.isin(people)].mean(), per[~per.index.isin(people)].mean(),
                 con[con.index.isin(people)].mean(), con[~con.index.isin(people)].mean()))


def per_person_load_slopes(S):
    hdr('L. Heterogeneity: per-person within-session association of queue and card taking (EXPLORATORY)')
    rows = []
    for pid, g in S.groupby('pid'):
        if g.q.nunique() > 1 and 0 < g.took.mean() < 1:
            r = stats.spearmanr(g.q_ws, g.took).correlation
            rows.append((pid, r, len(g)))
    R = pd.DataFrame(rows, columns=['pid', 'rho', 'n'])
    print('People with variation in both: %d; median rho %.3f; positive %d, negative %d'
          % (len(R), R.rho.median(), int((R.rho > 0).sum()), int((R.rho < 0).sum())))
    print('Sign test p = %.3f' % stats.binomtest(int((R.rho > 0).sum()), int((R.rho != 0).sum())).pvalue)
    load_ppl = sorted({i.split('/')[0] for i in LOAD_DELEGATION})
    print('People who SAY they hand over under load: %s' %
          R[R.pid.isin(load_ppl)].round(3).to_dict('records'))


def main():
    S, T, R, M, SESS = load_all()
    crosscheck(S)
    S = prep_strat(S)
    T = prep_tac(T)
    sess, _people = load_people()
    print('Participants: %d (v1.12+: %d). Strategic decisions %d, tactical confirms %d, recovery episodes %d'
          % (S.pid.nunique(), S[S.vrank >= V112].pid.nunique(), len(S), len(T), len(R)))

    section_queue_descriptives(S)
    t_all = section_primary(S, 'ALL 33')
    S12 = prep_strat(S[S.vrank >= V112].drop(columns=[c for c in S.columns if c.endswith(('_w', '_pm', '_ws', '_spm'))]))
    t_12 = section_primary(S12, 'study-v1.12+ (n=%d)' % S12.pid.nunique())
    section_robustness(S)
    hdr('C2. Same robustness set, v1.12+ cohort (abbreviated)')
    fit(PRIMARY + ' + idx', S12, '[v1.12+] + idx')
    for w in (60, 120):
        v = 'arrivals%d' % w
        fit('took ~ %s_w + %s_pm + ncolours + ndrones + C(scenario) + C(run) + elapsed_open' % (v, v), S12,
            '[v1.12+] EXOGENOUS arrivals in previous %ds' % w, show=(v + '_w',))
    section_other_strategic_outcomes(S)
    section_drones(S)
    T = section_tactical(T, R)
    section_speed_strategic(S, T)
    T = section_speed_tactical(T)
    section_pressure_pace(S, T, sess)
    section_quality(T, M, S)
    section_quotes(S, T)
    per_person_load_slopes(S)
    hdr('SUMMARY')
    print('PRIMARY all 33 : %s' % fmt_or(t_all))
    print('PRIMARY v1.12+ : %s' % fmt_or(t_12))


if __name__ == '__main__':
    main()
