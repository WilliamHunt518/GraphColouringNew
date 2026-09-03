#!/usr/bin/env python3
"""
Aggregate agent x scenario statistics across every collected study log.

Counterpart to scripts/study_report.py, which profiles participants one at a time. This one
pools SESSIONS and asks two questions the per-participant view cannot answer:

  1. Do operators treat the two ASSISTANTS differently? (strategic tier vs tactical tier)
  2. Does that differ between the two SCENARIOS? (Strategic Heavy vs Tactical Heavy)

...and it answers both inside each COHORT WINDOW, because the build changed underneath the data
several times (see docs/STUDY_BUILD.md / docs/SCENARIOS.md) and not every window is poolable.

Emits JSON on stdout.  Usage:  python scripts/agent_scenario_stats.py [--out stats.json]
"""
import json, glob, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# -- build ordering, so a cohort can be expressed as "version >= X" ----------------------------
# Pre-tag runs logged no appVersion at all; they are ordered by wall clock and treated as < v1.0.
VERSION_ORDER = ['pre-tag', 'study-v1.0', 'study-v1.1', 'study-v1.2', 'study-v1.3',
                 'study-v1.4', 'study-v1.5', 'study-v1.6', 'study-v1.7']


def vrank(v):
    v = v or 'pre-tag'
    return VERSION_ORDER.index(v) if v in VERSION_ORDER else 0


def events(session):
    """Sessions serialise as a list, or (older exports) as an object keyed by index."""
    evs = list(session.values()) if isinstance(session, dict) else list(session)
    return sorted([e for e in evs if isinstance(e, dict)], key=lambda e: e.get('seq', 0))


def pairs(plan):
    """A plan (list of {taskId, assetIds}) as a set of (task, drone) pairs -- the unit of overlap."""
    out = set()
    for step in plan or []:
        for a in step.get('assetIds') or []:
            out.add((step.get('taskId'), a))
    return out


def jaccard(a, b):
    if not a and not b:
        return None
    return len(a & b) / len(a | b) if (a | b) else None


def read_session(sess, pid, path, idx):
    evs = events(sess)
    def by(t):
        return [e for e in evs if e.get('type') == t]
    start = next(iter(by('session_start')), None)
    end = next(iter(by('session_ended')), None)
    if not start or not end:
        return None   # abandoned mid-run; nothing to aggregate

    scen = start.get('complexity')
    ver = start.get('appVersion') or 'pre-tag'

    # -- strategic tier ------------------------------------------------------------------------
    choices = by('strategic_choice')
    opens = by('strategic_modal_opened')
    ctype = {}
    for c in choices:
        ctype[c.get('choiceType')] = ctype.get(c.get('choiceType'), 0) + 1
    taken = [c for c in choices if c.get('choiceType') in ('aggressive', 'conservative')]
    edited = [c for c in taken if c.get('editedFromStrategy') is not None]
    s_lat = [c['latencyMs'] / 1000 for c in choices if isinstance(c.get('latencyMs'), (int, float))]

    # -- tactical tier -------------------------------------------------------------------------
    confirms = by('tactical_confirmed')
    # Consultation: did the operator ever pull the agent's plan in? The planner starts empty, so
    # suggestUsedCount == 0 means the plan was built without ever seeing the agent's.
    # The earliest logs (P-1333) predate the field; there, absence is NOT a zero, and
    # `hasSuggestField` below lets the aggregate drop those sessions instead of miscounting them.
    has_suggest = bool(confirms) and all('suggestUsedCount' in c for c in confirms)
    consulted = [c for c in confirms if (c.get('suggestUsedCount') or 0) > 0]
    # Conformance: of the confirmations where the agent HAD suggested the tasks in question,
    # how many went out untouched. (modifiedFromAgentPlan is only meaningful for those.)
    withplan = [c for c in confirms if c.get('agentPlan')]
    unmod = [c for c in withplan if not c.get('modifiedFromAgentPlan')]
    t_lat = [c['latencyMs'] / 1000 for c in confirms if isinstance(c.get('latencyMs'), (int, float))]
    # Version-independent overlap: how much of the final plan the agent actually authored.
    ov = [j for j in (jaccard(pairs(c.get('agentPlan')), pairs(c.get('finalPlan'))) for c in confirms)
          if j is not None]

    drags = by('tactical_assignment_changed')

    # -- recovery (the tactical tier under duress) ---------------------------------------------
    recs = by('failure_recovery')
    rec_agent = [r for r in recs if r.get('wasAgentSuggested')]

    # -- workload ------------------------------------------------------------------------------
    tlx = next((s for s in by('survey_response') if s.get('surveyName') == 'nasa_tlx'), None)
    tlx_vals = []
    if tlx and isinstance(tlx.get('responses'), dict):
        tlx_vals = [v for v in tlx['responses'].values() if isinstance(v, (int, float))]
    # performance is reverse-keyed on the TLX; left raw here and flagged in the report.
    tlx_mean = sum(tlx_vals) / len(tlx_vals) if tlx_vals else None

    # -- post-session trust, one scale per assistant -------------------------------------------
    # Same six item stems on both scales (confident / follow / performs / reliable / trust /
    # useful, 7-point), so the tactical-minus-strategic difference is a within-person paired
    # contrast rather than two unrelated numbers.
    def trust(name):
        sv = next((s for s in by('survey_response') if s.get('surveyName') == name), None)
        r = sv.get('responses') if sv and isinstance(sv.get('responses'), dict) else None
        if not r:
            return None
        items = {k.split('_', 1)[1]: v for k, v in r.items() if isinstance(v, (int, float))}
        if not items:
            return None
        return dict(items=items, mean=sum(items.values()) / len(items))

    t_strat, t_tac = trust('trust_strategic'), trust('trust_tactical')
    # A respondent who left every slider on its default answers nothing: flag rather than average
    # a straight line in with real variance.
    flat_vals = ([v for v in (t_strat or {}).get('items', {}).values()] +
                 [v for v in (t_tac or {}).get('items', {}).values()])
    straightlined = bool(flat_vals) and len(set(flat_vals)) == 1 and \
        bool(tlx_vals) and len(set(tlx_vals)) == 1

    outcomes = end.get('taskOutcomes') or {}
    done, failed = outcomes.get('completed'), outcomes.get('failed')
    never = outcomes.get('failedOnNeverAllocatedMissions')
    # Completion over work the operator actually took on: exclude tasks of missions never allocated.
    own_failed = (failed - never) if (failed is not None and never is not None) else None
    own_rate = None
    if done is not None and own_failed is not None and (done + own_failed) > 0:
        own_rate = done / (done + own_failed)

    return dict(
        pid=pid, path=path, sessionIndex=idx, scenario=scen, version=ver, vrank=vrank(ver),
        wallClock=start.get('wallClock'), seed=start.get('seed'),
        failureRate=start.get('failureRatePerDroneSecond'),
        tacticalMode=start.get('tacticalMode'),
        epsilonStrategic=start.get('epsilonStrategic'), epsilonTactical=start.get('epsilonTactical'),
        # strategic
        strategicOffers=len(opens), strategicChoices=len(choices),
        choiceAggressive=ctype.get('aggressive', 0), choiceConservative=ctype.get('conservative', 0),
        choiceManual=ctype.get('manual', 0),
        strategicTaken=len(taken), strategicEdited=len(edited),
        strategicDismissed=len(by('strategic_dismissed')),
        strategicLatency=s_lat,
        manualEdits=len(by('manual_allocation_edited')),
        cardPreviews=len(by('strategic_card_previewed')),
        # tactical
        tacticalConfirms=len(confirms), tacticalConsulted=len(consulted),
        hasSuggestField=has_suggest,
        tacticalWithPlan=len(withplan), tacticalUnmodified=len(unmod),
        tacticalLatency=t_lat, tacticalOverlap=ov,
        suggestClicks=len(by('tactical_suggest_used')), drags=len(drags),
        # recovery
        failures=len(by('drone_failure')), recoveries=len(recs), recoveriesAgent=len(rec_agent),
        abandons=len(by('mission_abandoned')),
        # performance
        score=end.get('score'), completionPoints=end.get('completionPoints'),
        penalty=end.get('penaltyAccrued'), meanMissionTime=end.get('meanMissionTime'),
        greenEfficiency=end.get('greenEfficiency'),
        missionsArrived=len([m for m in by('mission_arrived') if not m.get('isResidual')]),
        missionsCompleted=len(by('mission_completed')),
        tasksCompleted=done, tasksFailed=failed, tasksFailedNeverAllocated=never,
        ownCompletionRate=own_rate,
        tlxMean=tlx_mean,
        trustStrategic=t_strat, trustTactical=t_tac,
        trustDelta=(t_tac['mean'] - t_strat['mean']) if (t_strat and t_tac) else None,
        straightlined=straightlined,
        loggedAgentFollowRate=end.get('agentFollowRate'),
        loggedTacticalFollowRate=end.get('tacticalFollowRate'),
    )


# ── pre-study AI-attitude battery (study-v1.3+) ───────────────────────────────────────────────
# Scored exactly as docs/STUDY_BUILD.md section 10 specifies. Responses are logged RAW, so the
# reverse-keyed items are flipped here, at analysis time.
AIAS_ITEMS = ['aias_improve_life', 'aias_improve_work', 'aias_future_use', 'aias_positive_humanity']
VERIF_ITEMS = ['verif_check_before_relying', 'verif_comfortable_unreviewed', 'verif_want_reasoning',
               'verif_happy_unsupervised', 'verif_overconfident', 'verif_reliable_no_check']
VERIF_REVERSED = {'verif_comfortable_unreviewed', 'verif_happy_unsupervised', 'verif_reliable_no_check'}
DELEG_ITEMS = ['deleg_human_final_say', 'deleg_trust_suggest_over_decide',
               'deleg_prefer_self_even_if_slower', 'deleg_not_when_lives_at_stake',
               'deleg_urgent_better_than_nothing']
DELEG_REVERSED = {'deleg_urgent_better_than_nothing'}
# Excluded from the verification composite by design: it measures perceived error-detectability,
# a moderator, not propensity to check.
VERIF_MODERATOR = 'verif_hard_to_detect_errors'

EXPERIENCE_LEVELS = {'None': 0, 'A little': 1, 'Moderate': 2, 'Extensive': 3}
EXPERIENCE_ITEMS = ['autonomy_experience', 'drone_experience', 'command_experience',
                    'sim_experience', 'strategy_experience']


def score_attitudes(dem):
    """Composite AI-attitude scores, or None for a build that never asked (absence, not zero)."""
    if not isinstance(dem, dict):
        dem = {}

    def composite(items, reversed_items, top):
        vals = [dem[k] for k in items if isinstance(dem.get(k), (int, float))]
        if len(vals) < len(items):
            return None   # partial batteries are not scored
        got = [(top + 1 - dem[k]) if k in reversed_items else dem[k] for k in items]
        return sum(got) / len(got)

    aias = composite(AIAS_ITEMS, set(), 10)
    verif = composite(VERIF_ITEMS, VERIF_REVERSED, 7)
    deleg = composite(DELEG_ITEMS, DELEG_REVERSED, 7)

    # Prior-autonomy exposure exists on every build that collected demographics at all, so it is
    # the only disposition-adjacent axis with more than two people behind it. It is NOT the AIAS.
    exp = [EXPERIENCE_LEVELS[dem[k]] for k in EXPERIENCE_ITEMS if dem.get(k) in EXPERIENCE_LEVELS]
    return dict(
        aias=aias, verification=verif, delegation=deleg,
        # Items 1-2 of the delegation block map onto the recommend-vs-decide contrast between the
        # two assistants; kept raw and separate from the composite.
        delegHumanFinalSay=dem.get('deleg_human_final_say'),
        delegTrustSuggestOverDecide=dem.get('deleg_trust_suggest_over_decide'),
        errorDetectability=dem.get(VERIF_MODERATOR),
        autonomyExperience=(EXPERIENCE_LEVELS.get(dem.get('autonomy_experience'))),
        experienceMean=(sum(exp) / len(exp)) if len(exp) == len(EXPERIENCE_ITEMS) else None,
        hasBattery=aias is not None,
        raw={k: dem[k] for k in (AIAS_ITEMS + VERIF_ITEMS + DELEG_ITEMS + [VERIF_MODERATOR])
             if k in dem},
        age=dem.get('age'), gender=dem.get('gender'), field=dem.get('field'),
    )


def load_all():
    out = []
    sep = chr(92)   # backslash, for Windows paths out of glob
    for f in sorted(glob.glob(str(BASE / 'logs' / '**' / '*.json'), recursive=True)):
        p = f.replace(sep, '/')
        if 'sar_snapshot' in p or '/auto/' in p or p.endswith('summary.json'):
            continue   # snapshots are partial; /auto/ is synthetic (headless harness), not people
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict) or 'sessions' not in d:
            continue
        pid = d.get('participantId')
        rel = str(Path(f).relative_to(BASE)).replace(sep, '/')
        att = score_attitudes(d.get('demographics'))
        for i, s in enumerate(d['sessions']):
            r = read_session(s, pid, rel, i + 1)
            if r and r.get('scenario') in ('strategic', 'tactical'):
                r['attitudes'] = att
                out.append(r)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    a = ap.parse_args()
    rows = load_all()
    js = json.dumps(rows, indent=1)
    if a.out:
        Path(a.out).write_text(js, encoding='utf-8')
        print('%d sessions -> %s' % (len(rows), a.out))
    else:
        print(js)
