#!/usr/bin/env python3
"""Shared data layer for H4 (benchmark shortfall) and H10 (does reliance pay off?).

Read-only: reads Results/Participants/*.json and docs/reports/smart_benchmark.json, writes nothing.

Two tables:

* decisions() -- one row per strategic decision (the same rows as
  build_findings_synthesis.load_decisions(); `check_against_synthesis()` asserts it), plus what
  happened to the mission afterwards, reconstructed from the event log:
    status      all_completed / partial / none_completed (mission_completed.outcome),
                abandoned (mission_abandoned), inflight (no terminal event by the buzzer)
    full        1 if status == all_completed
    chain_full  1 if every task of this mission was eventually completed, following abandoned work
                into its residual mission(s) via task_requeued.residualTaskId (abandonment is a
                transfer, not a loss -- docs/EVENT_LOGGING.md "Abandonment")
    points      task weights earned by THIS mission's own tasks
    penalty     the penalty THIS mission accrued, recomputed exactly as computePenaltyAccrued()
                in gameReducer.ts (per-task rate = category rate x weight share; a completed task
                stops at its completionTime; everything else runs to abandonedAt for an abandoned
                mission, else to the end of the session). Validated against session_ended.
    net         points - penalty: the mission's contribution to the session score
  plus the reserve at the moment of choice (reserveStateAvailable in the envelope, pre-commit) and
  the tactical step that followed (consulted / unmodified / projected completions).

* sessions() -- one row per session: score, benchmark share, manual rates (split pre-emptive /
  post-reveal / edited), card uptake, tactical rates.

Excludes P09 everywhere. Nothing here filters residuals; callers decide.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
from agent_scenario_stats import events, vrank  # noqa: E402

PARTICIPANTS = BASE / 'Results' / 'Participants'
BENCH = BASE / 'docs' / 'reports' / 'smart_benchmark.json'
EXCLUDE = {'P09'}
SESSION_S = 480.0
V112 = vrank('study-v1.12')


def _fits(req, have):
    return bool(req) and all(have.get(c, 0) >= n for c, n in req.items())


def _penalty_by_mission(missions, weight, cat_rate, end_elapsed):
    """computePenaltyAccrued, per mission. missions: id -> dict(arrival, category, tasks, done, abandonedAt)."""
    out = {}
    for mid, m in missions.items():
        tw = sum(weight[str(t)] for _, t in m['tasks'])
        if tw == 0:
            out[mid] = 0.0
            continue
        rate = cat_rate[m['category']]
        cutoff = m['abandonedAt'] if m['abandonedAt'] is not None else end_elapsed
        p = 0.0
        for tid, ttype in m['tasks']:
            tr = rate * weight[str(ttype)] / tw
            end = m['done'].get(tid, cutoff)
            p += tr * max(0.0, end - m['arrival'])
        out[mid] = p
    return out


def _read_session(pid, run, evs):
    start = next((e for e in evs if e['type'] == 'session_start'), None)
    end = next((e for e in evs if e['type'] == 'session_ended'), None)
    if not start or not end:
        return None, []
    scenario = start.get('complexity')
    plan = start.get('planSeedIndex') or run
    version = start.get('appVersion') or 'pre-tag'
    primary = start['taskPrimary']
    weight = start['taskWeight']
    cat_rate = start['categoryPenaltyRate']
    end_el = end.get('elapsed') or SESSION_S

    missions, completed_ev, abandoned_ev, requeue = {}, {}, {}, {}
    task_fail = {}
    fail_count = {}
    for e in evs:
        t = e['type']
        if t == 'mission_arrived':
            missions[e['missionId']] = dict(
                arrival=e.get('arrivalTime', e.get('elapsed')), category=e.get('category'),
                tasks=[(x['id'], x['type']) for x in e.get('tasks', [])], done={},
                abandonedAt=None, residual=bool(e.get('isResidual')),
                parent=e.get('parentMissionId'), maxReward=e.get('maxReward'),
                comps=e.get('taskCompositions') or {})
        elif t == 'task_completed':
            m = missions.get(e['missionId'])
            if m is not None:
                m['done'][e['taskId']] = e['completionTime']
        elif t == 'task_failed':
            task_fail[e['taskId']] = e.get('reason')
        elif t == 'task_requeued':
            requeue[e['taskId']] = e.get('residualTaskId')
        elif t == 'mission_completed':
            completed_ev[e['missionId']] = e
        elif t == 'mission_abandoned':
            abandoned_ev[e['missionId']] = e
            if e['missionId'] in missions:
                missions[e['missionId']]['abandonedAt'] = e['elapsed']
        elif t == 'drone_failure' and e.get('missionId'):
            fail_count[e['missionId']] = fail_count.get(e['missionId'], 0) + 1

    pen = _penalty_by_mission(missions, weight, cat_rate, end_el)
    done_all = {tid for m in missions.values() for tid in m['done']}

    def eventually_done(tid, depth=0):
        if tid in done_all:
            return True
        nxt = requeue.get(tid)
        return bool(nxt) and depth < 10 and eventually_done(nxt, depth + 1)

    srow = dict(pid=pid, run=run, scenario=scenario, planIndex=int(plan), game=f'{scenario}|{plan}',
                version=version, vrank=vrank(version), score=end.get('score'),
                completionPoints=end.get('completionPoints'), penalty=end.get('penaltyAccrued'),
                penaltyRecon=sum(pen.values()),
                pointsRecon=sum(weight[str(tt)] for m in missions.values() for tid, tt in m['tasks']
                                if tid in m['done']),
                availablePoints=sum((m['maxReward'] or 0) for m in missions.values() if not m['residual']),
                taskWeightScale=weight['5'] / 100.0, swapped=bool(start.get('swapGames')),
                failures=sum(1 for e in evs if e['type'] == 'drone_failure'))

    rows = []
    pending, need, idx = {}, {}, 0
    tac_open, tac_conf = {}, {}
    for e in evs:
        if e['type'] == 'tactical_opened':
            tac_open.setdefault(e['missionId'], e)
        elif e['type'] == 'tactical_confirmed':
            tac_conf.setdefault(e['missionId'], e)

    for e in evs:
        t = e['type']
        if t == 'mission_arrived':
            tot = {'Blue': 0, 'Red': 0, 'Green': 0}
            for task in e.get('tasks', []):
                for colour, n in primary[str(task['type'])].items():
                    tot[colour] += n
            need[e['missionId']] = tot
        elif t == 'strategic_modal_opened':
            req = need.get(e['missionId'])
            cards = {c['name']: c for c in e.get('strategiesPresented', [])}
            if not req or len(cards) < 2:
                continue
            cons, aggr = cards['Conservative'], cards['Aggressive']
            pending[e['missionId']] = dict(
                opened_at=e['timestamp'], cons=cons['trueAssets'], aggr=aggr['trueAssets'],
                cons_total=sum(cons['trueAssets'].values()), aggr_total=sum(aggr['trueAssets'].values()),
                odd=int(any(cons['trueAssets'].get(c, 0) > 0 and req[c] == 0 for c in req)),
                ncolours=sum(1 for c in req if req[c] > 0), ndrones=sum(req.values()),
                cons_time=cons.get('displayedCompletionTime'), aggr_time=aggr.get('displayedCompletionTime'))
        elif t == 'strategic_choice' and e['missionId'] in pending:
            mid = e['missionId']
            p = pending.pop(mid)
            m = missions.get(mid, {})
            choice = e.get('choiceType')
            dc = e.get('deltaVsConservative') or {}
            res_av = e.get('reserveStateAvailable') or e.get('reserveState') or {}
            ce = completed_ev.get(mid)
            if ce is not None:
                status = ce.get('outcome')
            elif mid in abandoned_ev:
                status = 'abandoned'
            else:
                status = 'inflight'
            tasks = m.get('tasks', [])
            points = sum(weight[str(tt)] for tid, tt in tasks if tid in m.get('done', {}))
            tc = tac_conf.get(mid)
            to = tac_open.get(mid)
            consulted = bool(tc) and (tc.get('suggestUsedCount') or 0) > 0
            rows.append(dict(
                pid=pid, run=run, scenario=scenario, planIndex=int(plan), game=f'{scenario}|{plan}',
                version=version, vrank=vrank(version), missionId=mid, idx=idx,
                residual=int(m.get('residual', False) or mid.endswith('-R')),
                category=e.get('missionCategory'), ntasks=len(tasks),
                compkey=','.join(str(tt) for tt in sorted(tt for _, tt in tasks)),
                ncolours=p['ncolours'], ndrones=p['ndrones'], odd=p['odd'],
                cons_total=p['cons_total'], aggr_total=p['aggr_total'],
                choice=choice, took=int(choice in ('aggressive', 'conservative')),
                manual=int(choice == 'manual'),
                early=int(choice == 'manual' and bool(e.get('manualBeforeCardsLoaded'))),
                edited=int(choice == 'manual' and e.get('editedFromStrategy') is not None),
                committed=sum((e.get('assetsChosen') or {}).values()),
                d_cons=sum(dc.values()) if dc else np.nan,
                elapsed=e.get('elapsed'), time_left=SESSION_S - (e.get('elapsed') or 0),
                arrival=m.get('arrival'), wait=(e.get('elapsed') or 0) - (m.get('arrival') or 0),
                secs=(e['timestamp'] - p['opened_at']) / 1000.0,
                reserve_total=sum(res_av.values()) if res_av else np.nan,
                cons_affordable=int(all(res_av.get(c, 0) >= n for c, n in p['cons'].items())) if res_av else np.nan,
                # reserve pressure: 'tight' = some needed colour has fewer drones in reserve than the
                # mission's total primary need of it (the Aggressive card gets capped); 'starved' =
                # some task cannot be staffed at all from reserve, on primary or substitute.
                tight=int(any(res_av.get(c, 0) < n for c, n in need[mid].items() if n > 0)) if res_av else np.nan,
                starved=int(any(not (_fits(cmp.get('primary'), res_av) or _fits(cmp.get('substitute'), res_av))
                                for cmp in (m.get('comps') or {}).values())) if res_av else np.nan,
                aggr_affordable=int(all(res_av.get(c, 0) >= n for c, n in p['aggr'].items())) if res_av else np.nan,
                status=status, full=int(status == 'all_completed'),
                chain_full=int(bool(tasks) and all(eventually_done(tid) for tid, _ in tasks)),
                max_points=sum(weight[str(tt)] for _, tt in tasks),
                points=points, penalty=pen.get(mid, np.nan),
                net=points - pen.get(mid, np.nan),
                t_complete=(ce['completionTime'] - m['arrival']) if ce is not None and status == 'all_completed' else np.nan,
                dur_alloc=ce.get('durationFromAllocation') if ce is not None and status == 'all_completed' else np.nan,
                drone_failures=fail_count.get(mid, 0),
                end_el=(ce['completionTime'] if ce is not None else abandoned_ev[mid]['elapsed'] if mid in abandoned_ev else end_el),
                tac_confirmed=int(tc is not None), tac_consulted=int(consulted),
                tac_unmod=int(consulted and bool(tc.get('agentPlan')) and not tc.get('modifiedFromAgentPlan')) if tc else 0,
                tac_latency=(tc.get('latencyMs') or 0) / 1000.0 if tc else np.nan,
                agentProj=tc.get('agentProjectedCompletion') if tc else np.nan,
                finalProj=tc.get('finalProjectedCompletion') if tc else np.nan,
                tac_unassigned=len(tc.get('unassignedTaskIds') or []) if tc else np.nan,
                agentOpenProj=to.get('agentProjectedCompletion') if to else np.nan,
                tac_open_el=to.get('elapsed') if to else np.nan,
                tac_conf_el=tc.get('elapsed') if tc else np.nan,
            ))
            idx += 1
    # where the points went: task weight on missions the operator never allocated (queue at the buzzer)
    chosen = {e['missionId'] for e in evs if e['type'] == 'strategic_choice'}
    srow['unallocPoints'] = sum(weight[str(tt)] for mid, m in missions.items() if mid not in chosen
                                for tid, tt in m['tasks'] if tid not in m['done'])
    srow['unallocMissions'] = sum(1 for mid, m in missions.items() if mid not in chosen and not m['residual'])
    srow['allocLostPoints'] = sum(weight[str(tt)] for mid, m in missions.items() if mid in chosen
                                  for tid, tt in m['tasks'] if tid not in m['done'] and tid not in requeue)
    return srow, rows


@lru_cache(maxsize=1)
def _load():
    srows, drows = [], []
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, sess in enumerate(log['sessions'], start=1):
            s, d = _read_session(pid, run, events(sess))
            if s is not None and s['scenario'] in ('strategic', 'tactical'):
                srows.append(s)
                drows += d
    S, D = pd.DataFrame(srows), pd.DataFrame(drows)
    # cohort: a participant's OLDEST session's build (as study_analysis does)
    oldest = S.groupby('pid').vrank.min()
    S['v112'] = S.pid.map(oldest >= V112)
    D['v112'] = D.pid.map(oldest >= V112)
    # benchmark share (docs/reports/smart_benchmark.json), as build_findings_synthesis.benchmark()
    ref = json.loads(BENCH.read_text(encoding='utf-8'))
    bkey = {(g['complexity'], g['planIndex']): float(g['score']) for g in ref['games']}
    S['benchmark'] = [bkey.get((r.scenario, r.planIndex), np.nan) for r in S.itertuples()]
    S['share'] = S.score / S.benchmark
    # Unfloored score (score is max(0, points - penalty)) and the early-build rescale: P01/P02 ran
    # with half task weights (v1.0-v1.2). Penalty rates do not depend on the weights (they cancel in
    # weight/totalWeight), so the score the SAME play would have earned under the current weights is
    # points/scale - penalty.
    S['net'] = S.completionPoints - S.penalty
    S['share_net'] = S.net / S.benchmark
    S['score_rescaled'] = np.maximum(0, S.completionPoints / S.taskWeightScale - S.penalty)
    S['share_rescaled'] = S.score_rescaled / S.benchmark
    S['scoreEff'] = S.score / S.availablePoints

    # session-level reliance rates
    def rates(g):
        gen = g[g.residual == 0]
        tac = g[g.tac_confirmed == 1]
        return pd.Series(dict(
            n_dec=len(g), manual_rate=g.manual.mean(), early_rate=g.early.mean(),
            post_rate=((g.manual == 1) & (g.early == 0)).mean(),
            edited_rate=g.edited.mean(),
            post_unedited_rate=((g.manual == 1) & (g.early == 0) & (g.edited == 0)).mean(),
            uptake=g.took.mean(), manual_rate_gen=gen.manual.mean() if len(gen) else np.nan,
            n_tac=len(tac), tac_consult=tac.tac_consulted.mean() if len(tac) else np.nan,
            tac_unmod=tac.tac_unmod.mean() if len(tac) else np.nan))
    R = pd.DataFrame([dict(pid=k[0], run=k[1], **rates(g)) for k, g in D.groupby(['pid', 'run'])])
    S = S.merge(R, on=['pid', 'run'], how='left')
    return S, D


def sessions() -> pd.DataFrame:
    return _load()[0].copy()


def decisions() -> pd.DataFrame:
    return _load()[1].copy()


def check_against_synthesis():
    """Assert the decision rows reproduce build_findings_synthesis.load_decisions(), and the
    per-mission penalty reconstruction sums to session_ended.penaltyAccrued."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        from build_findings_synthesis import load_decisions
    ref = load_decisions()
    D, S = decisions(), sessions()
    out = dict(n_ref=len(ref), n_mine=len(D))
    a = ref.sort_values(['pid', 'run', 'idx']).reset_index(drop=True)
    b = D.sort_values(['pid', 'run', 'idx']).reset_index(drop=True)
    same = len(a) == len(b)
    if same:
        for col in ('choice', 'ncolours', 'ndrones', 'residual', 'odd', 'cons_total'):
            same &= bool((a[col].values == b[col].values).all())
        same &= bool((a.early.fillna(False).astype(bool).values & (a.manual == 1).values
                      == (b.early == 1).values).all())
        same &= bool(((a.outcome == 'all_completed').values == (b.status == 'all_completed').values).all())
    out['rows_match'] = same
    diff = (S.penaltyRecon - S.penalty).abs()
    out['penalty_recon_max_abs_err'] = float(diff.max())
    out['penalty_recon_sessions_off_by_gt1'] = int((diff > 1).sum())
    pdiff = (S.pointsRecon - S.completionPoints).abs()
    out['points_recon_sessions_off'] = int((pdiff > 0).sum())
    return out


if __name__ == '__main__':
    print(check_against_synthesis())
    S = sessions()
    print(S[['pid', 'run', 'game', 'version', 'score', 'benchmark', 'share', 'manual_rate',
             'early_rate', 'post_rate', 'uptake']].to_string())
