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

# Every session runs the same 480s clock regardless of complexity preset (missionGen.ts
# SESSION_DURATION_BY_COMPLEXITY) -- fixed here so "early/mid/late in the session" buckets are
# comparable across scenarios.
SESSION_DURATION_S = 480


def automation_score(r):
    """Unified 0 / 0.5 / 1 reliance scale across all three decision types, so "how willing were
    they to automate" can be pooled or compared by context instead of read off separate booleans:
      0   = built/chosen by hand, agent not used for this decision
      0.5 = consulted the agent's suggestion, then changed it
      1   = took the agent's suggestion as given
    None when the decision type/build carries no automation signal to score (e.g. a strategic
    choice that is neither a card nor manual, or a build predating a needed field).

    Strategic: picking a card at all IS consulting the agent (the cards are its output) --
    `manualBeforeCardsLoaded` is a stronger, separately-logged signal of declining without
    looking, not needed to score this. Tactical: `suggestUsedCount` is the actual behavioural
    signal for "chose to automate" (RQ2 -- an operator can confirm a plan that happens to match
    the agent's baseline without ever asking for it), so an unconsulted plan scores 0 even if it
    incidentally lines up with what the agent would have suggested.
    """
    t = r['decisionType']
    if t == 'strategic_choice':
        ct = r.get('choiceType')
        if ct == 'manual':
            return 0.0
        if ct in ('aggressive', 'conservative'):
            return 0.5 if r.get('edited') else 1.0
        return None
    if t == 'tactical_confirmed':
        if not (r.get('suggestUsedCount') or 0) > 0:
            return 0.0
        if not r.get('hasAgentPlan'):
            return 0.5   # consulted, but nothing logged to compare the result against
        return 0.5 if r.get('modifiedFromAgentPlan') else 1.0
    if t == 'failure_recovery':
        return 1.0 if r.get('wasAgentSuggested') else 0.0
    return None


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
    base['automationScore'] = automation_score(base)
    return base


def load_decisions():
    rows = []
    sep = chr(92)
    for f in sorted(Path(BASE / 'logs').glob('**/*.json')):
        p = str(f).replace(sep, '/')
        if 'sar_snapshot' in p or '/auto/' in p or p.endswith('summary.json'):
            continue   # snapshots are partial; /auto/ is synthetic — see agent_scenario_stats.py.
                       # (P09, formerly "faultTest.json", is a real participant and is included.)
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict) or 'sessions' not in d:
            continue
        rel = str(f.relative_to(BASE)).replace(sep, '/')
        # file name is the anonymised id under logs/Participants/ -- see agent_scenario_stats.py
        pid = f.stem if rel.startswith('logs/Participants/') else d.get('participantId')
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
        # Willingness to automate, on the shared 0/0.5/1 scale (see automation_score) -- separate
        # from the rates above because it is comparable across all three decision types.
        meanAutomationStrategic=mean(r['automationScore'] for r in strat),
        meanAutomationTactical=mean(r['automationScore'] for r in tac),
        meanAutomationRecovery=mean(r['automationScore'] for r in rec),
        # does the objectively busiest moment coincide with the self-reported "task_load" reason?
        # cross-reference against logs/narration/<pid>_s<n>/codes.json by hand -- not joined here,
        # narration codes are gitignored (identifiable), this file is not.
    )


# ── willingness to automate, by context (task 1's actual question) ───────────────────────────
# Not "how much did they use the agent overall" (participant_signature already answers that) but
# "under what circumstances did they lean on it more or less": as a session wears on, on harder
# missions, and while more is going on at once.

MISSION_CATEGORY_ORDER = ['A', 'B', 'C', 'D', 'E']   # ascending size/difficulty, see missionGen.ts
LOAD_VARS = ('missionsActive', 'missionsQueued', 'tasksPending', 'tasksExecuting', 'dronesAvailable')


def scored(rows):
    return [r for r in rows if isinstance(r.get('automationScore'), (int, float))]


def automation_cell(rows):
    s = scored(rows)
    return dict(n=len(s), meanAutomation=mean(r['automationScore'] for r in s),
                manualRate=rate(len([r for r in s if r['automationScore'] == 0]), len(s)),
                fullAutomationRate=rate(len([r for r in s if r['automationScore'] == 1]), len(s)))


def by_category(rows):
    return {cat: automation_cell([r for r in rows if r.get('missionCategory') == cat])
            for cat in MISSION_CATEGORY_ORDER}


def terciles(vals):
    """Cut points for a pooled, decision-type-specific low/mid/high split -- context variables
    live on very different scales for a strategic choice (queue depth) vs a tactical confirm
    (tasks mid-execution), so the tercile boundaries are computed separately per decision type
    rather than sharing one global cut."""
    vals = sorted(v for v in vals if isinstance(v, (int, float)))
    if len(vals) < 6:   # too few to split meaningfully
        return None
    return vals[len(vals) // 3], vals[2 * len(vals) // 3]


def load_bucket(val, cuts):
    if cuts is None or not isinstance(val, (int, float)):
        return None
    lo, hi = cuts
    return 'low' if val <= lo else 'high' if val > hi else 'mid'


def by_load(rows):
    out = {}
    for var in LOAD_VARS:
        cuts = terciles(r.get(var) for r in rows)
        buckets = {'low': [], 'mid': [], 'high': []}
        for r in rows:
            b = load_bucket(r.get(var), cuts)
            if b:
                buckets[b].append(r)
        out[var] = {b: automation_cell(rs) for b, rs in buckets.items()}
    return out


def by_time_in_session(rows):
    thirds = {'early': [], 'mid': [], 'late': []}
    for r in rows:
        e = r.get('elapsed')
        if not isinstance(e, (int, float)):
            continue
        third = 'early' if e < SESSION_DURATION_S / 3 else \
                'late' if e >= 2 * SESSION_DURATION_S / 3 else 'mid'
        thirds[third].append(r)
    return {k: automation_cell(rs) for k, rs in thirds.items()}


def by_session_number(rows):
    nums = sorted({r['sessionIndex'] for r in rows if r.get('sessionIndex') is not None})
    return {str(n): automation_cell([r for r in rows if r['sessionIndex'] == n]) for n in nums}


def automation_by_context(rows):
    """One breakdown per decision type (strategic/tactical/recovery pooled across participants),
    plus one pooled across all three -- each dimension answers a different half of task 1's
    question: byCategory = easy vs hard missions, byLoad = how much else was going on right now,
    byTimeInSession/bySessionNumber = does reliance drift over the course of the study."""
    out = {}
    groups = dict(all=rows,
                  strategic=[r for r in rows if r['decisionType'] == 'strategic_choice'],
                  tactical=[r for r in rows if r['decisionType'] == 'tactical_confirmed'],
                  recovery=[r for r in rows if r['decisionType'] == 'failure_recovery'])
    for name, rs in groups.items():
        out[name] = dict(
            overall=automation_cell(rs),
            byCategory=by_category(rs),
            byLoad=by_load(rs),
            byTimeInSession=by_time_in_session(rs),
            bySessionNumber=by_session_number(rs),
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    a = ap.parse_args()

    decisions = load_decisions()
    by_pid = {}
    for r in decisions:
        by_pid.setdefault(r['pid'], []).append(r)
    participants = [participant_signature(pid, rows) for pid, rows in sorted(by_pid.items())]
    automation = automation_by_context(decisions)

    out = dict(decisions=decisions, participants=participants, automationByContext=automation)
    js = json.dumps(out, indent=1)
    if a.out:
        Path(a.out).write_text(js, encoding='utf-8')
        print('%d decisions across %d participants -> %s' % (len(decisions), len(participants), a.out))
        overall = automation['all']['overall']
        print('  overall automation: mean=%.2f manual=%.0f%% full=%.0f%% (n=%d scored)' % (
            overall['meanAutomation'] or 0, 100 * (overall['manualRate'] or 0),
            100 * (overall['fullAutomationRate'] or 0), overall['n']))
    else:
        print(js)


if __name__ == '__main__':
    main()
