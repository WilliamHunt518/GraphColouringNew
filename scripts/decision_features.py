#!/usr/bin/env python3
"""
Per-DECISION feature table, one row per strategic_choice / tactical_confirmed / failure_recovery
event across every collected log -- not the per-session rollups agent_scenario_stats.py produces.

Why this exists: agent_scenario_aggregate.py's cohort/participant view answers "how much did this
person use the agent overall". It cannot answer "under what conditions, at the moment of the
decision, did they lean on it" -- mission criticality, how much else was active, how far into the
session -- because that context lives on the event itself and gets thrown away once a session is
rolled up to one row. At n ~ 12 participants but ~200 decisions, this is where the real sample size
is.

Also emits a per-participant "reliance signature": behavioural rates (manual/edit/consult/chain)
independent of the attitude-survey/trust numbers already in aggregate.json, meant to sit next to
them, not replace them.

Usage:  python scripts/decision_features.py [--out docs/reports/decision_features.json]
"""
import json, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(BASE / 'scripts'))
from agent_scenario_stats import events, vrank, pairs, jaccard   # noqa: E402

DECISION_TYPES = ('strategic_choice', 'tactical_confirmed', 'failure_recovery')


def context_snapshot(e):
    c = e.get('context') or {}
    return dict(
        missionsActive=c.get('missionsActive'), missionsQueued=c.get('missionsQueued'),
        tasksPending=c.get('tasksPending'), tasksExecuting=c.get('tasksExecuting'),
        dronesAvailable=c.get('dronesAvailable'), penaltyAccrued=c.get('penaltyAccrued'),
    )


def decision_row(e, pid, path, version, scenario, session_index):
    base = dict(
        pid=pid, path=path, version=version, scenario=scenario, sessionIndex=session_index,
        decisionType=e['type'], missionId=e.get('missionId'), missionCategory=e.get('missionCategory'),
        seq=e.get('seq'), elapsed=e.get('elapsed'),
        latencySec=(e['latencyMs'] / 1000) if isinstance(e.get('latencyMs'), (int, float)) else None,
        **context_snapshot(e),
    )
    if e['type'] == 'strategic_choice':
        delta = e.get('deltaVsAggressive') or {}
        deltaC = e.get('deltaVsConservative') or {}
        base.update(
            choiceType=e.get('choiceType'),
            manualBeforeCardsLoaded=e.get('manualBeforeCardsLoaded'),
            edited=e.get('editedFromStrategy') is not None,
            deviationFromAggressive=sum(abs(v) for v in delta.values()) if delta else None,
            deviationFromConservative=sum(abs(v) for v in deltaC.values()) if deltaC else None,
            strategyCardCount=e.get('strategyCardCount'),
        )
    elif e['type'] == 'tactical_confirmed':
        agent_plan, final_plan = e.get('agentPlan'), e.get('finalPlan')
        orders = [step.get('order') for step in (agent_plan or []) if step.get('order') is not None]
        base.update(
            modifiedFromAgentPlan=e.get('modifiedFromAgentPlan'),
            chainingUsed=e.get('chainingUsed'),
            suggestUsedCount=e.get('suggestUsedCount'),
            hasAgentPlan=bool(agent_plan),
            planOverlap=jaccard(pairs(agent_plan), pairs(final_plan)) if agent_plan else None,
            agentPlanSteps=len(orders) if orders else None,
            tacticalFailureFired=e.get('tacticalFailureFired'),
        )
    elif e['type'] == 'failure_recovery':
        base.update(
            recoveryType=e.get('recoveryType'), wasAgentSuggested=e.get('wasAgentSuggested'),
            recoveryReason=e.get('recoveryReason'),
            tasksStillUnassigned=len(e.get('tasksStillUnassigned') or []),
        )
    return base


def load_decisions():
    rows = []
    sep = chr(92)
    for f in sorted(Path(BASE / 'logs').glob('**/*.json')):
        p = str(f).replace(sep, '/')
        if 'sar_snapshot' in p or '/auto/' in p or p.endswith('summary.json') or p.endswith('faultTest.json'):
            continue   # dev run exercising ε>0, not a participant — see agent_scenario_stats.py
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict) or 'sessions' not in d:
            continue
        pid = d.get('participantId')
        rel = str(f.relative_to(BASE)).replace(sep, '/')
        for i, sess in enumerate(d['sessions']):
            evs = events(sess)
            start = next((e for e in evs if e.get('type') == 'session_start'), None)
            if not start:
                continue
            version = start.get('appVersion') or 'pre-tag'
            scenario = start.get('complexity')
            for e in evs:
                if e.get('type') in DECISION_TYPES:
                    rows.append(decision_row(e, pid, rel, version, scenario, i + 1))
    return rows


def rate(numer, denom):
    return (numer / denom) if denom else None


def mean(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return (sum(vals) / len(vals)) if vals else None


def participant_signature(pid, rows):
    strat = [r for r in rows if r['decisionType'] == 'strategic_choice']
    tac = [r for r in rows if r['decisionType'] == 'tactical_confirmed']
    rec = [r for r in rows if r['decisionType'] == 'failure_recovery']

    manual = [r for r in strat if r['choiceType'] == 'manual']
    taken = [r for r in strat if r['choiceType'] in ('aggressive', 'conservative')]
    edited = [r for r in taken if r['edited']]
    manual_before_load = [r for r in manual if r.get('manualBeforeCardsLoaded')]

    tac_with_field = [r for r in tac if r.get('suggestUsedCount') is not None]
    consulted = [r for r in tac_with_field if (r.get('suggestUsedCount') or 0) > 0]
    with_plan = [r for r in tac if r.get('hasAgentPlan')]
    unmodified = [r for r in with_plan if not r['modifiedFromAgentPlan']]
    chained = [r for r in tac if r.get('chainingUsed')]

    return dict(
        pid=pid, nStrategic=len(strat), nTactical=len(tac), nRecovery=len(rec),
        strategicManualRate=rate(len(manual), len(strat)),
        strategicManualBeforeLoadRate=rate(len(manual_before_load), len(manual)),
        strategicEditRate=rate(len(edited), len(taken)),
        meanStrategicLatencySec=mean(r['latencySec'] for r in strat),
        meanStrategicDeviationFromChosenCard=mean(
            (r['deviationFromAggressive'] if r['choiceType'] == 'aggressive'
             else r['deviationFromConservative'] if r['choiceType'] == 'conservative' else None)
            for r in taken
        ),
        tacticalConsultRate=rate(len(consulted), len(tac_with_field)),
        tacticalUnmodifiedRate=rate(len(unmodified), len(with_plan)),
        tacticalChainingRate=rate(len(chained), len(tac)),
        meanTacticalLatencySec=mean(r['latencySec'] for r in tac),
        meanPlanOverlap=mean(r['planOverlap'] for r in with_plan),
        recoveryAgentRate=rate(len([r for r in rec if r['wasAgentSuggested']]), len(rec)),
        meanMissionsActiveAtStrategicChoice=mean(r['missionsActive'] for r in strat),
        meanTasksPendingAtStrategicChoice=mean(r['tasksPending'] for r in strat),
        meanMissionsActiveAtTacticalConfirm=mean(r['missionsActive'] for r in tac),
        # does the objectively busiest moment coincide with the self-reported "task_load" reason?
        # cross-reference against logs/narration/<pid>_s<n>/codes.json by hand -- not joined here,
        # narration codes are gitignored (identifiable), this file is not.
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    a = ap.parse_args()

    decisions = load_decisions()
    by_pid = {}
    for r in decisions:
        by_pid.setdefault(r['pid'], []).append(r)
    participants = [participant_signature(pid, rows) for pid, rows in sorted(by_pid.items())]

    out = dict(decisions=decisions, participants=participants)
    js = json.dumps(out, indent=1)
    if a.out:
        Path(a.out).write_text(js, encoding='utf-8')
        print('%d decisions across %d participants -> %s' % (len(decisions), len(participants), a.out))
    else:
        print(js)


if __name__ == '__main__':
    main()
