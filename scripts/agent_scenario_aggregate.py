#!/usr/bin/env python3
"""
Roll the per-session rows from agent_scenario_stats.py up into cohort x scenario x tier aggregates,
and emit the JSON the aggregate report page renders.

Cohort windows are not arbitrary. Each one is a boundary where the build changed something that
makes the data on either side mean different things (docs/STUDY_BUILD.md, docs/SCENARIOS.md):

  all       every complete session
  pilot     pre-tag builds. The tactical agent ran in GREEDY mode: it committed one step at a
            time, so its "plan" was a single task (mean plan length 1.0). Agreement with a
            one-step plan is not the same measurement as agreement with a whole-mission plan.
  study     study-v1.0+. Tactical agent switched to PLAN-ALL (plans of 3-5 tasks), recovery_opened
            started logging, and the scenario set settled at v2.1.
  outcomes  study-v1.2+. session_ended.taskOutcomes exists, so completion can be scored over the
            work the operator actually took on rather than over every task that ever spawned.
  hazard    study-v1.4+. Drone failures fire on every machine (before v1.4 a high-refresh display
            could see ZERO failures all session), and substitute compositions work.
  recovery  study-v1.5+. The recovery planner's Suggest button actually returns a plan.

Usage:  python scripts/agent_scenario_aggregate.py [--out aggregate.json]
"""
import json, argparse, math
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(BASE / 'scripts'))
from agent_scenario_stats import load_all, vrank   # noqa: E402

COHORTS = [
    dict(key='all', label='All sessions', short='All',
         note='Every complete session ever collected. Metrics that only exist in later builds are '
              'scored over the sessions that carry them, never imputed.'),
    dict(key='pilot', label='Pilot era (pre-tag builds)', short='Pilot',
         maxrank=vrank('pre-tag'),
         note='Tactical agent in greedy mode: it suggested one task at a time, so tactical '
              'agreement here is agreement with a single step, not with a whole-mission plan.'),
    dict(key='study', label='Study build (study-v1.0+)', short='v1.0+',
         minrank=vrank('study-v1.0'),
         note='Tactical agent switched to plan-all (3-5 task plans) and the scenario set settled '
              'at v2.1. This is the first window where both tiers offer a comparable decision.'),
    dict(key='outcomes', label='Task outcomes logged (study-v1.2+)', short='v1.2+',
         minrank=vrank('study-v1.2'),
         note='session_ended.taskOutcomes exists, so completion can be scored over the work the '
              'operator actually took on.'),
    dict(key='hazard', label='Honest failure model (study-v1.4+)', short='v1.4+',
         minrank=vrank('study-v1.4'),
         note='Drone failures fire at the intended rate on every machine. Before v1.4 a '
              'high-refresh display could meet no failures at all.'),
    dict(key='recovery', label='Recovery Suggest works (study-v1.5+)', short='v1.5+',
         minrank=vrank('study-v1.5'),
         note='The recovery planner’s Suggest button returns a plan instead of nothing, so '
              'agent use during a failure is measurable for the first time.'),
]

SCEN = ['strategic', 'tactical']


def wilson(k, n, z=1.96):
    """Wilson score interval -- behaves at the small n this study actually has."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def rate(k, n):
    return dict(k=k, n=n, p=(k / n if n else None), ci=wilson(k, n) if n else None)


def summarise(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    def q(f):
        if n == 1:
            return vals[0]
        i = f * (n - 1)
        lo, hi = int(math.floor(i)), int(math.ceil(i))
        return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)
    return dict(n=n, mean=sum(vals) / n, median=q(0.5), q1=q(0.25), q3=q(0.75),
                lo=vals[0], hi=vals[-1], values=vals)


def in_cohort(row, c):
    if 'minrank' in c and row['vrank'] < c['minrank']:
        return False
    if 'maxrank' in c and row['vrank'] > c['maxrank']:
        return False
    return True


def cell(rows):
    """All agent/scenario metrics for one bucket of sessions."""
    # -- strategic tier: uptake = a card was taken rather than a manual bundle built -------------
    s_take = sum(r['strategicTaken'] for r in rows)
    s_all = sum(r['strategicChoices'] for r in rows)
    s_unedited = sum(r['strategicTaken'] - r['strategicEdited'] for r in rows)

    # -- tactical tier: uptake = the agent's plan was pulled in at least once --------------------
    # P-1333 predates suggestUsedCount; its sessions are excluded from uptake rather than counted
    # as zero, which is what a missing field would otherwise look like.
    t_rows = [r for r in rows if r['hasSuggestField']]
    t_cons = sum(r['tacticalConsulted'] for r in t_rows)
    t_all = sum(r['tacticalConfirms'] for r in t_rows)
    t_unmod = sum(r['tacticalUnmodified'] for r in rows)
    t_withplan = sum(r['tacticalWithPlan'] for r in rows)

    rec = sum(r['recoveries'] for r in rows)
    rec_a = sum(r['recoveriesAgent'] for r in rows)

    parts = sorted({r['pid'] for r in rows})
    return dict(
        sessions=len(rows), participants=len(parts), participantIds=parts,
        versions=sorted({r['version'] for r in rows}),
        tacticalModes=sorted({r['tacticalMode'] for r in rows if r['tacticalMode']}),
        strategicUptake=rate(s_take, s_all),
        strategicUnedited=rate(s_unedited, s_take),
        tacticalUptake=rate(t_cons, t_all),
        tacticalUnmodified=rate(t_unmod, t_withplan),
        tacticalUptakeSessions=len(t_rows),
        recoveryAgent=rate(rec_a, rec),
        strategicLatency=summarise([v for r in rows for v in r['strategicLatency']]),
        tacticalLatency=summarise([v for r in rows for v in r['tacticalLatency']]),
        planOverlap=summarise([v for r in rows for v in r['tacticalOverlap']]),
        cardMix=dict(
            aggressive=sum(r['choiceAggressive'] for r in rows),
            conservative=sum(r['choiceConservative'] for r in rows),
            manual=sum(r['choiceManual'] for r in rows),
        ),
        # per-participant rates, for dot overlays -- the honest view at this n
        perParticipant=[dict(
            pid=r['pid'], scenario=r['scenario'], version=r['version'],
            strategicUptake=(r['strategicTaken'] / r['strategicChoices']) if r['strategicChoices'] else None,
            tacticalUptake=(r['tacticalConsulted'] / r['tacticalConfirms'])
            if (r['hasSuggestField'] and r['tacticalConfirms']) else None,
            completion=r['ownCompletionRate'], score=r['score'], penalty=r['penalty'],
            meanMissionTime=r['meanMissionTime'], tlx=r['tlxMean'],
            failures=r['failures'], drags=r['drags'],
        ) for r in rows],
        # performance -- only meaningful where the field exists
        completion=summarise([r['ownCompletionRate'] for r in rows]),
        score=summarise([r['score'] for r in rows]),
        penalty=summarise([r['penalty'] for r in rows]),
        meanMissionTime=summarise([r['meanMissionTime'] for r in rows]),
        tlx=summarise([r['tlxMean'] for r in rows]),
        failures=summarise([r['failures'] for r in rows]),
        drags=summarise([float(r['drags']) for r in rows if r['drags'] > 0]),
    )


def contrasts(rows):
    """Each participant against themselves: tactical-heavy minus strategic-heavy.

    At this n the within-participant contrast is the only comparison that isn't swamped by who
    happened to sit in which chair -- every participant ran both scenarios, so their own pair
    controls for skill, and the direction of the difference is readable even when the level is not.
    """
    out = []
    by = {}
    for r in rows:
        by.setdefault(r['pid'], []).append(r)
    for pid, rs in sorted(by.items()):
        s = next((x for x in rs if x['scenario'] == 'strategic'), None)
        t = next((x for x in rs if x['scenario'] == 'tactical'), None)
        if not s or not t:
            continue   # P-6921 only ever ran one scenario
        def g(row, f):
            return f(row)
        def upt(x):
            return (x['strategicTaken'] / x['strategicChoices']) if x['strategicChoices'] else None
        def tupt(x):
            return (x['tacticalConsulted'] / x['tacticalConfirms']) \
                if (x['hasSuggestField'] and x['tacticalConfirms']) else None
        def unmod(x):
            return (x['tacticalUnmodified'] / x['tacticalWithPlan']) if x['tacticalWithPlan'] else None
        def mmt(x):
            # 0 means no mission was ever completed, not an instant mission.
            return x['meanMissionTime'] or None
        entry = dict(pid=pid, version=s['version'],
                     strategicFirst=s['sessionIndex'] < t['sessionIndex'])
        for name, f in [('completion', lambda x: x['ownCompletionRate']),
                        ('strategicUptake', upt), ('tacticalUptake', tupt),
                        ('tacticalUnmodified', unmod), ('meanMissionTime', mmt),
                        ('tlx', lambda x: x['tlxMean']), ('penalty', lambda x: x['penalty'])]:
            a, b = g(s, f), g(t, f)
            entry[name] = None if (a is None or b is None) else dict(strategic=a, tactical=b, delta=b - a)
        out.append(entry)
    return out


def order_effect(rows):
    """Session 1 vs session 2, pooled -- the learning/order confound on the scenario contrast."""
    out = []
    for idx in (1, 2):
        sel = [r for r in rows if r['sessionIndex'] == idx]
        if not sel:
            continue
        t = [r for r in sel if r['hasSuggestField']]
        out.append(dict(
            session=idx, sessions=len(sel),
            scenarios={s: len([r for r in sel if r['scenario'] == s]) for s in SCEN},
            strategicUptake=rate(sum(r['strategicTaken'] for r in sel),
                                 sum(r['strategicChoices'] for r in sel)),
            tacticalUptake=rate(sum(r['tacticalConsulted'] for r in t),
                                sum(r['tacticalConfirms'] for r in t)),
            tacticalUnmodified=rate(sum(r['tacticalUnmodified'] for r in sel),
                                    sum(r['tacticalWithPlan'] for r in sel)),
            completion=summarise([r['ownCompletionRate'] for r in sel]),
        ))
    return out


def pearson(pairs):
    """Correlation plus its n. At this sample size it is reported as description, never inference:
    the page prints n beside every r and refuses to draw a fit line below n = 5."""
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if n < 3:
        return dict(n=n, r=None)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx <= 0 or syy <= 0:
        return dict(n=n, r=None)
    return dict(n=n, r=sxy / math.sqrt(sxx * syy))


def attitudes(rows):
    """One record per participant: pre-study disposition, post-session trust in each assistant,
    and the behavioural uptake of each -- everything needed to ask whether disposition predicts
    which assistant a person leans on.

    Trust is averaged over a participant's sessions (the same two scales run after every session).
    Straight-lined responses -- every trust item and every TLX item identical, i.e. sliders never
    moved -- are carried but flagged, and excluded from the correlations.
    """
    by = {}
    for r in rows:
        by.setdefault(r['pid'], []).append(r)

    people = []
    for pid, rs in sorted(by.items()):
        att = rs[0].get('attitudes') or {}
        ts = [r['trustStrategic']['mean'] for r in rs if r.get('trustStrategic')]
        tt = [r['trustTactical']['mean'] for r in rs if r.get('trustTactical')]
        flat = all(r.get('straightlined') for r in rs) and len(rs) > 0

        s_take = sum(r['strategicTaken'] for r in rs)
        s_all = sum(r['strategicChoices'] for r in rs)
        t_rows = [r for r in rs if r['hasSuggestField']]
        t_cons = sum(r['tacticalConsulted'] for r in t_rows)
        t_all = sum(r['tacticalConfirms'] for r in t_rows)
        s_up = (s_take / s_all) if s_all else None
        t_up = (t_cons / t_all) if t_all else None

        # Per-item trust profile, averaged over the participant's sessions.
        def items(key):
            acc = {}
            for r in rs:
                blk = r.get(key)
                if not blk:
                    continue
                for k, v in blk['items'].items():
                    acc.setdefault(k, []).append(v)
            return {k: sum(v) / len(v) for k, v in acc.items()} or None

        people.append(dict(
            pid=pid, versions=sorted({r['version'] for r in rs}),
            sessions=len(rs), straightlined=flat,
            aias=att.get('aias'), verification=att.get('verification'),
            delegation=att.get('delegation'), hasBattery=bool(att.get('hasBattery')),
            delegHumanFinalSay=att.get('delegHumanFinalSay'),
            delegTrustSuggestOverDecide=att.get('delegTrustSuggestOverDecide'),
            errorDetectability=att.get('errorDetectability'),
            autonomyExperience=att.get('autonomyExperience'),
            experienceMean=att.get('experienceMean'),
            raw=att.get('raw') or {},
            trustStrategic=(sum(ts) / len(ts)) if ts else None,
            trustTactical=(sum(tt) / len(tt)) if tt else None,
            trustDelta=((sum(tt) / len(tt)) - (sum(ts) / len(ts))) if (ts and tt) else None,
            trustItemsStrategic=items('trustStrategic'), trustItemsTactical=items('trustTactical'),
            strategicUptake=s_up, tacticalUptake=t_up,
            uptakeDelta=(t_up - s_up) if (s_up is not None and t_up is not None) else None,
            tlx=summarise([r['tlxMean'] for r in rs]),
        ))

    usable = [p for p in people if not p['straightlined']]

    def corr(xk, yk, src=None):
        return pearson([(p[xk], p[yk]) for p in (src or usable)])

    return dict(
        people=people,
        withBattery=len([p for p in usable if p['hasBattery']]),
        straightlined=[p['pid'] for p in people if p['straightlined']],
        correlations=dict(
            # Does disposition predict which assistant you lean on, or how much you trust each?
            aiasVsTrustDelta=corr('aias', 'trustDelta'),
            aiasVsTrustStrategic=corr('aias', 'trustStrategic'),
            aiasVsTrustTactical=corr('aias', 'trustTactical'),
            aiasVsUptakeDelta=corr('aias', 'uptakeDelta'),
            verificationVsTrustDelta=corr('verification', 'trustDelta'),
            delegationVsTrustDelta=corr('delegation', 'trustDelta'),
            # The only disposition-adjacent axis with more than two people behind it.
            experienceVsTrustDelta=corr('experienceMean', 'trustDelta'),
            experienceVsTrustStrategic=corr('experienceMean', 'trustStrategic'),
            experienceVsTrustTactical=corr('experienceMean', 'trustTactical'),
            experienceVsUptakeDelta=corr('experienceMean', 'uptakeDelta'),
            # Does stated trust track what people actually did?
            trustStrategicVsUptake=corr('trustStrategic', 'strategicUptake'),
            trustTacticalVsUptake=corr('trustTactical', 'tacticalUptake'),
            trustDeltaVsUptakeDelta=corr('trustDelta', 'uptakeDelta'),
        ),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    a = ap.parse_args()

    rows = load_all()
    out = dict(cohorts=[], sessions=rows, generated=None)
    for c in COHORTS:
        sel = [r for r in rows if in_cohort(r, c)]
        if not sel:
            continue
        entry = dict({k: v for k, v in c.items() if k not in ('minrank', 'maxrank')},
                     overall=cell(sel))
        for s in SCEN:
            entry[s] = cell([r for r in sel if r['scenario'] == s])
        entry['dateRange'] = [min((r['wallClock'] or '')[:10] for r in sel),
                              max((r['wallClock'] or '')[:10] for r in sel)]
        entry['contrasts'] = contrasts(sel)
        entry['orderEffect'] = order_effect(sel)
        entry['attitudes'] = attitudes(sel)
        out['cohorts'].append(entry)

    js = json.dumps(out, indent=1)
    if a.out:
        Path(a.out).write_text(js, encoding='utf-8')
        print('%d cohorts, %d sessions -> %s' % (len(out['cohorts']), len(rows), a.out))
    else:
        print(js)


if __name__ == '__main__':
    main()
