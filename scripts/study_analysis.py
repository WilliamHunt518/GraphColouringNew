#!/usr/bin/env python3
"""
Log-only analysis of the participant study -- the replacement for the agent_scenario_* pipeline
behind docs/reports/two-tiers-two-scenarios.html.

The old pipeline pooled every build window and treated completion rate as the outcome. This one is
organised around the design the study actually ran: a 2x2 CROSSOVER. Every participant ran both
scenarios (Strategic Heavy, Tactical Heavy), in counterbalanced order, so every measure has two
sources of within-person change -- the scenario, and simply being on your second run -- and the two
can only be separated by comparing the two order groups. The questions it answers:

  performance   score (the number participants were chasing) alongside completion, normalised by
                the points actually on offer so the two scenarios are comparable
  learning      run 1 vs run 2 for performance AND for reliance on each assistant, with the
                scenario effect separated out; plus a run-2-only between-subjects view that treats
                run 1 as a warm-up
  drift         reliance across the 8 minutes of each run (early / mid / late thirds)
  category      reliance by mission size (A..E), controlling for scenario and run
  failures      every drone-failure recovery episode, classified by what the operator did, and
                whether heavy reliance on the assistants goes with abandoning recoverable missions
  outliers      robust-z screen on performance and engagement, with every headline recomputed
                with and without the flagged participants

Only Results/Participants/ is read (pilots are not participants). The participant id is the FILE
name: a few logs still carry an un-anonymised in-app id (see docs/Participants.xlsx), which must
never reach the report.

Usage:  python scripts/study_analysis.py            # writes docs/reports/study_analysis.json + page
        python scripts/study_analysis.py --print    # also prints a text summary
"""
import json, math, argparse, random, warnings
from pathlib import Path
import sys

import numpy as np
from scipy import stats

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / 'scripts'))
from agent_scenario_stats import events, vrank   # noqa: E402

LOG_DIR = BASE / 'Results' / 'Participants'
OUT_JSON = BASE / 'docs' / 'reports' / 'study_analysis.json'
OUT_HTML = BASE / 'docs' / 'reports' / 'two-tiers-two-scenarios.html'
TEMPLATE = BASE / 'scripts' / 'study_analysis_template.html'

SESSION_S = 480
CATS = ['A', 'B', 'C', 'D', 'E']

# P09 ran with agent faults ON (eps 0.2/0.2) -- the only session in the dataset where the
# assistants were ever wrong -- and did not follow the study (see the anonymisation notes). Its
# second session also has no decisions at all. It is a different experiment, not an outlier.
EXCLUDE_ALWAYS = {'P09': 'agent faults on (eps=0.2) and the participant did not follow the task; '
                         'session 2 has no decisions'}

COHORTS = [
    dict(key='v112', label='study-v1.12 onward', minrank=vrank('study-v1.12'),
         note='Identical games and behaviour for every participant: the cleanest comparison. v1.13 '
              'only adds the game-order swap, which replays the same four games in the other order.'),
    dict(key='v14', label='study-v1.4 onward', minrank=vrank('study-v1.4'),
         note='Adds P03-P11. Same scoring, fleet, scenarios and failure hazard as v1.12; earlier '
              'builds differ in the recovery Suggest button (v1.5), recovery-plan wiping (v1.6) and '
              'strategy-card score bars (v1.7). Use to check that a v1.12 result is not a fluke.'),
]


# ---------------------------------------------------------------------------------------------
# Reading the logs
# ---------------------------------------------------------------------------------------------

def is_card(ct):
    return ct in ('aggressive', 'conservative')


TYPE_OF = {'B': 'Blue', 'R': 'Red', 'G': 'Green'}


def coverable(comp, ids):
    """Can these drones staff the task, on its primary or its substitute composition?"""
    if not comp:
        return False
    have = {}
    for i in ids:
        k = TYPE_OF.get((i or ' ')[0])
        have[k] = have.get(k, 0) + 1
    ok = lambda req: bool(req) and all(have.get(k, 0) >= v for k, v in req.items())
    return ok(comp.get('primary')) or ok(comp.get('substitute'))


def read_session(evs, pid, run):
    """One session -> (session row, decision rows, recovery episodes). None if incomplete."""
    start = next((e for e in evs if e['type'] == 'session_start'), None)
    end = next((e for e in evs if e['type'] == 'session_ended'), None)
    if not start or not end:
        return None
    scen = start.get('complexity')
    ver = start.get('appVersion') or 'pre-tag'

    cat_of = {}
    avail_points = 0
    arrived = 0
    n_tasks = 0
    work = 0   # drone-seconds of on-task work the game asks for (primary composition x base time)
    for e in evs:
        if e['type'] == 'mission_arrived':
            cat_of[e['missionId']] = e.get('category')
            if not e.get('isResidual'):
                arrived += 1
                avail_points += e.get('maxReward') or 0
                for c in (e.get('taskCompositions') or {}).values():
                    n_tasks += 1
                    work += sum((c.get('primary') or {}).values()) * (c.get('baseTime') or 0)

    decisions, episodes = [], []
    open_rec = {}
    comps, deployed, dead = {}, {}, set()   # for the busy-drone feasibility check below
    for e in evs:
        t, m = e['type'], e.get('missionId')
        el = e.get('elapsed')
        cat = e.get('missionCategory') or cat_of.get(m)
        base = dict(pid=pid, run=run, scenario=scen, missionId=m, category=cat, elapsed=el,
                    third=None if el is None else min(2, int(el // (SESSION_S / 3))))
        if t == 'mission_arrived':
            comps.update(e.get('taskCompositions') or {})
        elif t == 'drone_failure':
            dead.add(e.get('droneId'))
        if t == 'tactical_confirmed':
            deployed.setdefault(m, set()).update(e.get('assetsDeployed') or [])
        elif t == 'failure_recovery':
            for a in e.get('repairedAssignments') or []:
                deployed.setdefault(m, set()).update(a.get('assetIds') or [])
        if t == 'strategic_choice':
            ct = e.get('choiceType')
            # Editing a card turns the choice into 'manual' (editedFromStrategy says which card it
            # started from), so a taken card is always taken as-is. The ladder keeps the rungs apart.
            if is_card(ct):
                ladder = 'accept'
            elif e.get('editedFromStrategy') is not None:
                ladder = 'edit'
            elif e.get('manualBeforeCardsLoaded'):
                ladder = 'manual-blind'
            else:
                ladder = 'manual'
            decisions.append(dict(base, tier='strategic', choice=ct, ladder=ladder,
                                  used=is_card(ct), accepted=is_card(ct),
                                  blind=ladder == 'manual-blind',
                                  latency=(e.get('latencyMs') or 0) / 1000))
        elif t == 'tactical_confirmed':
            consulted = (e.get('suggestUsedCount') or 0) > 0
            unmod = consulted and bool(e.get('agentPlan')) and not e.get('modifiedFromAgentPlan')
            decisions.append(dict(base, tier='tactical', used=consulted, accepted=unmod,
                                  ladder='accept' if unmod else 'edit' if consulted else 'manual',
                                  latency=(e.get('latencyMs') or 0) / 1000))
        elif t == 'recovery_opened':
            # feasibleWithOnMissionDrones only counts drones NOT executing a task -- the same pool
            # the recovery Suggest button draws on. The operator, though, can chain a busy drone
            # after its current task by hand. So a failure that is unfixable from idle drones but
            # fixable once busy mission drones are counted is exactly the Suggest blind spot:
            # Suggest finds nothing, a manual chain works.
            idle = e.get('onMissionDroneIds') or []
            everyone = (deployed.get(m, set()) | set(idle)) - dead
            busy_ok = all(coverable(comps.get(x), everyone) for x in e.get('affectedTaskIds') or [])
            open_rec[m] = dict(pid=pid, run=run, scenario=scen, missionId=m, category=cat,
                               opened=el, feasible=e.get('feasibleWithOnMissionDrones'),
                               feasibleWithBusy=bool(busy_ok),
                               reason=e.get('recoveryReason'), suggest=0, drags=0,
                               lastSuggest=None)
        elif m in open_rec:
            ep = open_rec[m]
            if t == 'tactical_suggest_used' and e.get('recoveryMode'):
                ep['suggest'] += 1
                ep['lastSuggest'] = el
            elif t == 'tactical_assignment_changed':
                ep['drags'] += 1
            elif t in ('failure_recovery', 'mission_abandoned'):
                ep.update(outcome='recovered' if t == 'failure_recovery' else 'abandoned',
                          agentPlan=bool(e.get('wasAgentSuggested')) if t == 'failure_recovery' else None,
                          latency=el - ep['opened'],
                          suggestToOutcome=(el - ep['lastSuggest']) if ep['lastSuggest'] is not None else None)
                episodes.append(open_rec.pop(m))
    for ep in open_rec.values():
        ep.update(outcome='unresolved', agentPlan=None, latency=SESSION_S - ep['opened'],
                  suggestToOutcome=None)
        episodes.append(ep)
    for ep in episodes:
        ep['pattern'] = episode_pattern(ep)
        # recovery decisions share the reliance scale: Suggest used or not
        decisions.append(dict(pid=pid, run=run, scenario=scen, missionId=ep['missionId'],
                              category=ep['category'], elapsed=ep['opened'],
                              third=min(2, int(ep['opened'] // (SESSION_S / 3))),
                              tier='recovery', used=ep['suggest'] > 0,
                              accepted=bool(ep.get('agentPlan')), latency=ep['latency']))

    outc = end.get('taskOutcomes') or {}
    done, failed = outc.get('completed'), outc.get('failed')
    never = outc.get('failedOnNeverAllocatedMissions')
    own = None
    if None not in (done, failed, never) and done + failed - never > 0:
        own = done / (done + failed - never)

    def rate(tier, key):
        ds = [d for d in decisions if d['tier'] == tier]
        return (sum(d[key] for d in ds) / len(ds)) if ds else None

    score = end.get('score')
    # Which game this session played. Before study-v1.13 the plan seed index was always the session
    # number; from v1.13 session_start logs it (it differs when swapGames is on).
    game_idx = start.get('planSeedIndex') or run
    row = dict(
        pid=pid, run=run, scenario=scen, version=ver, vrank=vrank(ver),
        swapped=bool(start.get('swapGames')), gameIndex=game_idx, game=f'{scen}|{game_idx}',
        epsS=start.get('epsilonStrategic'), epsT=start.get('epsilonTactical'),
        score=score, completionPoints=end.get('completionPoints'), penalty=end.get('penaltyAccrued'),
        availablePoints=avail_points, nTasks=n_tasks, workDroneSec=work,
        scoreEff=(score / avail_points) if (score is not None and avail_points) else None,
        completion=own, missionsArrived=arrived,
        meanMissionTime=end.get('meanMissionTime') or None,
        nStrategic=len([d for d in decisions if d['tier'] == 'strategic']),
        nTactical=len([d for d in decisions if d['tier'] == 'tactical']),
        strategicUse=rate('strategic', 'used'), strategicBlind=rate('strategic', 'blind'),
        tacticalUse=rate('tactical', 'used'), tacticalAccept=rate('tactical', 'accepted'),
        recoveryUse=rate('recovery', 'used'),
        failures=len([e for e in evs if e['type'] == 'drone_failure']),
        episodes=len(episodes),
        abandons=len([e for e in episodes if e['outcome'] == 'abandoned']),
        abandonsFeasible=len([e for e in episodes if e['outcome'] == 'abandoned' and e['feasible']]),
        drags=len([e for e in evs if e['type'] == 'tactical_assignment_changed']),
    )
    both = [v for v in (row['strategicUse'], row['tacticalUse']) if v is not None]
    row['reliance'] = sum(both) / len(both) if both else None
    return row, decisions, episodes


def episode_pattern(ep):
    """What the operator did with a failure, in the terms the report uses.

    'suggest-then-abandon' is the pattern the known Suggest quirk produces: the operator asks the
    Tactical Assistant for a fix, makes no manual edit at all, and abandons -- even though the
    mission's own drones could re-staff the broken task (feasibleWithOnMissionDrones). An operator
    who treats the assistant's silence (or its plan) as the last word, rather than trying by hand,
    is the over-reliance signature this is meant to pick out.
    """
    if ep['outcome'] == 'recovered':
        return 'recovered-agent' if ep['agentPlan'] else 'recovered-manual'
    if ep['outcome'] == 'unresolved':
        return 'unresolved'
    if not ep['feasible'] and ep.get('feasibleWithBusy'):
        return 'abandon-busy'
    if not ep['feasible']:
        return 'abandon-infeasible'
    if ep['suggest'] > 0 and ep['drags'] == 0:
        return 'suggest-then-abandon'
    if ep['drags'] > 0:
        return 'tried-then-abandon'
    return 'abandon-untried'


PATTERNS = [
    ('recovered-agent', 'Recovered with Suggest'),
    ('recovered-manual', 'Recovered by hand'),
    ('abandon-infeasible', 'Abandoned: not fixable with mission drones'),
    ('abandon-busy', 'Abandoned: fix needed a busy drone (Suggest blind spot)'),
    ('tried-then-abandon', 'Abandoned after manual edits'),
    ('suggest-then-abandon', 'Abandoned right after Suggest (fixable)'),
    ('abandon-untried', 'Abandoned without trying (fixable)'),
    ('unresolved', 'Left open at session end'),
]


def load():
    sessions, decisions, episodes = [], [], []
    for f in sorted(LOG_DIR.glob('*.json')):
        pid = f.stem
        d = json.loads(f.read_text(encoding='utf-8'))
        for i, s in enumerate(d.get('sessions') or []):
            r = read_session(events(s), pid, i + 1)
            if not r or r[0]['scenario'] not in ('strategic', 'tactical'):
                continue
            sessions.append(r[0]); decisions += r[1]; episodes += r[2]
    # order group: which scenario came first
    first = {s['pid']: s['scenario'] for s in sessions if s['run'] == 1}
    # Game load. Within each scenario the two games differ in how much work they ask for; the one
    # asking for more is the heavier. A participant's game set is heavy or light as a whole: without
    # the swap, strategic-first players get both heavier games and tactical-first players both
    # lighter ones; the swap reverses that. So load is a between-person factor, and it is only
    # separable from order once both order groups have been run with and without the swap.
    work = {}
    for s in sessions:
        work.setdefault(s['scenario'], {})[s['gameIndex']] = s['workDroneSec']
    heavy_idx = {sc: max(w, key=w.get) for sc, w in work.items() if len(w) == 2}
    person_load = {}
    for s in sessions:
        s['gameLoad'] = 'heavy' if heavy_idx.get(s['scenario']) == s['gameIndex'] else 'light'
        person_load.setdefault(s['pid'], set()).add(s['gameLoad'])
    swapped = {s['pid']: s['swapped'] for s in sessions}
    for coll in (sessions, decisions, episodes):
        for x in coll:
            x['order'] = 'SF' if first.get(x['pid']) == 'strategic' else 'TF'
            ls = person_load.get(x['pid'], set())
            x['load'] = next(iter(ls)) if len(ls) == 1 else 'mixed'
            x['swapped'] = swapped.get(x['pid'], False)
    return sessions, decisions, episodes


# ---------------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------------

def fnum(x):
    if x is None:
        return None
    x = float(x)
    return None if (math.isnan(x) or math.isinf(x)) else x


def describe(vals):
    v = np.array([x for x in vals if x is not None], dtype=float)
    if not len(v):
        return None
    return dict(n=int(len(v)), mean=fnum(v.mean()), sd=fnum(v.std(ddof=1)) if len(v) > 1 else None,
                median=fnum(np.median(v)), q1=fnum(np.percentile(v, 25)),
                q3=fnum(np.percentile(v, 75)), lo=fnum(v.min()), hi=fnum(v.max()))


def welch(a, b):
    a = np.array([x for x in a if x is not None], float)
    b = np.array([x for x in b if x is not None], float)
    if len(a) < 2 or len(b) < 2:
        return None
    t, p = stats.ttest_ind(a, b, equal_var=False)
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1)) if (va + vb) > 0 else None
    diff = a.mean() - b.mean()
    se = math.sqrt(va + vb)
    tc = stats.t.ppf(0.975, df) if df else None
    sp = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    return dict(diff=fnum(diff), ci=[fnum(diff - tc * se), fnum(diff + tc * se)] if tc else None,
                t=fnum(t), df=fnum(df), p=fnum(p), d=fnum(diff / sp) if sp > 0 else None,
                na=len(a), nb=len(b), meanA=fnum(a.mean()), meanB=fnum(b.mean()))


def crossover(sessions, metric):
    """Standard 2x2 crossover analysis (Jones & Kenward) on one per-session metric.

    For each participant d = run2 - run1. In the strategic-first group d = (Tactical - Strategic)
    + run effect; in the tactical-first group d = (Strategic - Tactical) + run effect. So:
      scenario effect (Tactical - Strategic) = (mean d_SF - mean d_TF) / 2, tested by Welch t on d
      run effect (run 2 - run 1)             = (mean d_SF + mean d_TF) / 2, tested on d_SF vs -d_TF
      carry-over / order interaction         = tested on the per-person SUM between groups
    Welch rather than pooled variance because the groups are 10 vs 8 and need not share a spread.
    """
    by = {}
    for s in sessions:
        by.setdefault(s['pid'], {})[s['run']] = s
    dS, dT, sS, sT, people = [], [], [], [], []
    for pid, rr in sorted(by.items()):
        if 1 not in rr or 2 not in rr:
            continue
        a, b = rr[1].get(metric), rr[2].get(metric)
        if a is None or b is None:
            continue
        grp = 'SF' if rr[1]['scenario'] == 'strategic' else 'TF'
        (dS if grp == 'SF' else dT).append(b - a)
        (sS if grp == 'SF' else sT).append(b + a)
        people.append(dict(pid=pid, order=grp, run1=a, run2=b,
                           strategic=a if grp == 'SF' else b, tactical=b if grp == 'SF' else a))
    if len(dS) < 2 or len(dT) < 2:
        return dict(metric=metric, n=len(people), people=people)
    scen = welch(dS, dT)
    run = welch(dS, [-x for x in dT])
    carry = welch(sS, sT)
    half = lambda w: None if w is None else dict(w, diff=w['diff'] / 2,
                                                  ci=[w['ci'][0] / 2, w['ci'][1] / 2] if w['ci'] else None)
    # paired, ignoring order -- what a naive analysis would report; shown for contrast
    naive_scen = stats.ttest_rel([p['tactical'] for p in people], [p['strategic'] for p in people])
    naive_run = stats.ttest_rel([p['run2'] for p in people], [p['run1'] for p in people])
    return dict(
        metric=metric, n=len(people), nSF=len(dS), nTF=len(dT), people=people,
        scenario=half(scen), run=half(run), carryover=carry,
        means=dict(
            strategic=fnum(np.mean([p['strategic'] for p in people])),
            tactical=fnum(np.mean([p['tactical'] for p in people])),
            run1=fnum(np.mean([p['run1'] for p in people])),
            run2=fnum(np.mean([p['run2'] for p in people])),
            cells={f'{g}{r}': fnum(np.mean([p[f'run{r}'] for p in people if p['order'] == g]))
                   for g in ('SF', 'TF') for r in (1, 2)},
        ),
        naive=dict(scenarioP=fnum(naive_scen.pvalue), runP=fnum(naive_run.pvalue)),
    )


def between(sessions, metric, run):
    """One run only, between subjects: Tactical Heavy vs Strategic Heavy."""
    sel = [s for s in sessions if s['run'] == run]
    return welch([s[metric] for s in sel if s['scenario'] == 'tactical'],
                 [s[metric] for s in sel if s['scenario'] == 'strategic'])


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 4:
        return dict(n=len(pairs), rho=None, p=None)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r, p = stats.spearmanr([a for a, _ in pairs], [b for _, b in pairs])
    return dict(n=len(pairs), rho=fnum(r), p=fnum(p))


def gee_logit(rows, y, xs, group='pid'):
    """Logistic GEE, exchangeable within participant: the decision-level model that respects the
    fact that 300 decisions come from 18 people, not 300. Returns odds ratios with 95% CIs."""
    import pandas as pd
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    df = pd.DataFrame(rows)
    df = df.dropna(subset=[y] + [x.split('(')[-1].rstrip(')') for x in xs if '(' not in x] or [y])
    df[y] = df[y].astype(float)
    if df[y].nunique() < 2 or df[group].nunique() < 4:
        return None
    formula = f'{y} ~ ' + ' + '.join(xs)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            m = smf.gee(formula, group, df, family=sm.families.Binomial(),
                        cov_struct=sm.cov_struct.Exchangeable()).fit()
    except Exception as ex:   # separation etc.
        return dict(error=str(ex))
    out = []
    ci = m.conf_int()
    for name in m.params.index:
        if name == 'Intercept':
            continue
        out.append(dict(term=name, OR=fnum(math.exp(m.params[name])),
                        lo=fnum(math.exp(ci.loc[name, 0])), hi=fnum(math.exp(ci.loc[name, 1])),
                        p=fnum(m.pvalues[name])))
    return dict(n=int(len(df)), groups=int(df[group].nunique()), terms=out)


def perm_test_diff(a, b, n=20000, seed=7):
    """Two-sample permutation p for a difference in means (small, lumpy participant-level data)."""
    a = [x for x in a if x is not None]; b = [x for x in b if x is not None]
    if len(a) < 2 or len(b) < 2:
        return None
    obs = abs(np.mean(a) - np.mean(b))
    pool = a + b
    rng = random.Random(seed)
    hit = 0
    for _ in range(n):
        rng.shuffle(pool)
        if abs(np.mean(pool[:len(a)]) - np.mean(pool[len(a):])) >= obs - 1e-12:
            hit += 1
    return (hit + 1) / (n + 1)


# ---------------------------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------------------------

PERF = [('score', 'Score'), ('scoreEff', 'Score / points available'),
        ('completion', 'Completion (own missions)'), ('penalty', 'Penalty accrued'),
        ('completionPoints', 'Points earned'), ('meanMissionTime', 'Mean mission time (s)')]
USE = [('strategicUse', 'Strategic: card taken'),
       ('strategicBlind', 'Strategic: manual before cards loaded'),
       ('tacticalUse', 'Tactical: Suggest consulted'), ('tacticalAccept', 'Tactical: plan kept unedited'),
       ('recoveryUse', 'Recovery: Suggest used')]


def outliers(sessions):
    """Robust (median/MAD) z-scores per participant on performance and engagement.

    z is computed within each game (scenario x game index -- each is a different fixed mission
    stream, see GAME_NOTE) and run, so a hard game is not itself an outlier.

    Flag rule: a participant is flagged when they are consistently far below everyone else -- their
    robust z, AVERAGED over both runs, is below -2 on score-per-point-available or on the number of
    decisions made. One bad run is deliberately not enough: a poor first run followed by a normal
    second one is the learning effect this study is about, not a participant to drop. Completion is
    shown but not used to flag -- it bunches near 80-90%, so its MAD is tiny and ordinary sessions
    reach |z| > 3.

    Flagged participants are NOT removed from the default view -- every headline is recomputed
    without them, and the page shows both.
    """
    def rz(vals):
        v = np.array(vals, float)
        med = np.median(v); mad = np.median(np.abs(v - med)) * 1.4826
        return (v - med) / mad if mad > 0 else np.zeros_like(v)

    out = []
    runs = {}
    for s in sessions:
        runs.setdefault(s['pid'], {})[s['run']] = s
    pids = sorted(p for p, r in runs.items() if 1 in r and 2 in r)
    # z within game (scenario x game index) and run, so a hard game is not itself an outlier, and
    # the same game played first or second is treated as a different situation.
    z = {}
    for key in ('scoreEff', 'completion', 'nDecisions'):
        for game in sorted({s['game'] for s in sessions}):
            for run in (1, 2):
                cell = [s for s in sessions if s['game'] == game and s['run'] == run
                        and s['pid'] in pids]
                vals = [(s['nStrategic'] + s['nTactical']) if key == 'nDecisions' else s[key]
                        for s in cell]
                if any(v is None for v in vals) or len(vals) < 4:
                    continue
                for s, zz in zip(cell, rz(vals)):
                    z[(s['pid'], s['run'], key)] = float(zz)
    for pid in pids:
        zs = {k: [z.get((pid, r, k)) for r in (1, 2)] for k in ('scoreEff', 'completion', 'nDecisions')}
        reasons = []
        means = {k: (float(np.mean([v for v in vs if v is not None])) if any(v is not None for v in vs) else None)
                 for k, vs in zs.items()}
        if means['scoreEff'] is not None and means['scoreEff'] < -2:
            reasons.append('score per available point far below the rest in both runs (mean z %.1f)' % means['scoreEff'])
        if means['nDecisions'] is not None and means['nDecisions'] < -2:
            reasons.append('made far fewer decisions than the rest (mean z %.1f)' % means['nDecisions'])
        s1, s2 = runs[pid][1], runs[pid][2]
        out.append(dict(pid=pid, z={k: [fnum(v) for v in vs] for k, vs in zs.items()},
                        meanZ={k: fnum(v) for k, v in means.items()},
                        flagged=bool(reasons), reasons=reasons,
                        scoreEff=[fnum(s1['scoreEff']), fnum(s2['scoreEff'])],
                        decisions=[s1['nStrategic'] + s1['nTactical'], s2['nStrategic'] + s2['nTactical']],
                        order=s1['order']))
    return out


def reliance_drift(decisions):
    """Use rate by third of the session, per tier x run, averaged over PARTICIPANTS (each person
    weighs the same however many decisions they made)."""
    out = {}
    for tier in ('strategic', 'tactical'):
        for run in (1, 2):
            cells = []
            for third in range(3):
                per = {}
                for d in decisions:
                    if d['tier'] == tier and d['run'] == run and d['third'] == third:
                        per.setdefault(d['pid'], []).append(d['used'])
                vals = [np.mean(v) for v in per.values()]
                cells.append(dict(third=third, n=len(vals), decisions=sum(len(v) for v in per.values()),
                                  mean=fnum(np.mean(vals)) if vals else None,
                                  se=fnum(np.std(vals, ddof=1) / math.sqrt(len(vals))) if len(vals) > 1 else None))
            out[f'{tier}{run}'] = cells
    return out


LADDERS = {
    'strategic': [('accept', 'Took a card as offered'), ('edit', 'Started from a card, edited it'),
                  ('manual', 'Built by hand after cards shown'), ('manual-blind', 'Built by hand before cards loaded')],
    'tactical': [('accept', 'Kept the suggested plan'), ('edit', 'Suggested, then modified'),
                 ('manual', 'Built by hand, never consulted')],
}


def ladders(decisions):
    """Share of decisions on each rung of the reliance ladder, per tier x scenario x run, averaged
    over participants."""
    out = {}
    for tier, rungs in LADDERS.items():
        for scen in ('strategic', 'tactical'):
            for run in (1, 2):
                per = {}
                for d in decisions:
                    if d['tier'] == tier and d['scenario'] == scen and d['run'] == run:
                        per.setdefault(d['pid'], []).append(d['ladder'])
                out[f'{tier}|{scen}|{run}'] = dict(
                    people=len(per), decisions=sum(len(v) for v in per.values()),
                    shares={k: fnum(np.mean([v.count(k) / len(v) for v in per.values()])) if per else None
                            for k, _ in rungs})
    return out


def by_category(decisions):
    """Use rate by mission category, per tier and scenario, participant-averaged, plus a GEE with
    category as a linear trend (A=0 .. E=4) controlling for scenario and run."""
    out = dict(cells={}, models={}, mix={})
    for tier in ('strategic', 'tactical', 'recovery'):
        for scen in ('all', 'strategic', 'tactical'):
            cells = []
            for c in CATS:
                per = {}
                for d in decisions:
                    if d['tier'] == tier and d['category'] == c and (scen == 'all' or d['scenario'] == scen):
                        per.setdefault(d['pid'], []).append(d['used'])
                vals = [np.mean(v) for v in per.values()]
                n_dec = sum(len(v) for v in per.values())
                cells.append(dict(cat=c, people=len(vals), decisions=n_dec,
                                  mean=fnum(np.mean(vals)) if vals else None,
                                  pooled=fnum(np.mean([x for v in per.values() for x in v])) if n_dec else None,
                                  se=fnum(np.std(vals, ddof=1) / math.sqrt(len(vals))) if len(vals) > 1 else None))
            out['cells'][f'{tier}|{scen}'] = cells
        rows = [dict(pid=d['pid'], used=float(d['used']), catN=CATS.index(d['category']),
                     tacScen=float(d['scenario'] == 'tactical'), run2=float(d['run'] == 2))
                for d in decisions if d['tier'] == tier and d['category'] in CATS]
        out['models'][tier] = gee_logit(rows, 'used', ['catN', 'tacScen', 'run2'])
        # within-person: each participant's own slope of use on category (who automates big vs small)
        slopes = []
        per = {}
        for r in rows:
            per.setdefault(r['pid'], []).append(r)
        for pid, rs in per.items():
            xs = [r['catN'] for r in rs]; ys = [r['used'] for r in rs]
            if len(set(xs)) >= 2 and len(rs) >= 5:
                slopes.append(dict(pid=pid, slope=fnum(np.polyfit(xs, ys, 1)[0]), n=len(rs),
                                   meanUse=fnum(np.mean(ys))))
        out['models'][tier + 'Slopes'] = slopes
    for scen in ('strategic', 'tactical'):
        mix = {c: 0 for c in CATS}
        for d in decisions:
            if d['tier'] == 'strategic' and d['scenario'] == scen and d['category'] in mix:
                mix[d['category']] += 1
        out['mix'][scen] = mix
    return out


def failure_analysis(sessions, episodes, decisions):
    pats = {k: 0 for k, _ in PATTERNS}
    for e in episodes:
        pats[e['pattern']] += 1
    # per participant: how much they lean on the assistants in NORMAL decisions (recovery excluded,
    # so the predictor is not built from the outcome) vs what they do when a drone fails
    people = []
    for pid in sorted({s['pid'] for s in sessions}):
        ds = [d for d in decisions if d['pid'] == pid and d['tier'] in ('strategic', 'tactical')]
        es = [e for e in episodes if e['pid'] == pid]
        fe = [e for e in es if e['feasible']]
        sd = [d['used'] for d in ds if d['tier'] == 'strategic']
        td = [d['used'] for d in ds if d['tier'] == 'tactical']
        people.append(dict(
            pid=pid, order=next(s['order'] for s in sessions if s['pid'] == pid),
            reliance=fnum(np.mean([np.mean(sd) if sd else np.nan, np.mean(td) if td else np.nan])),
            strategicUse=fnum(np.mean(sd)) if sd else None,
            tacticalUse=fnum(np.mean(td)) if td else None,
            episodes=len(es), feasibleEpisodes=len(fe),
            abandonRate=fnum(np.mean([e['outcome'] == 'abandoned' for e in es])) if es else None,
            abandonFeasibleRate=fnum(np.mean([e['outcome'] == 'abandoned' for e in fe])) if fe else None,
            recoverySuggestRate=fnum(np.mean([e['suggest'] > 0 for e in es])) if es else None,
            suggestThenAbandon=len([e for e in es if e['pattern'] == 'suggest-then-abandon']),
            untriedAbandon=len([e for e in es if e['pattern'] == 'abandon-untried']),
            patterns={k: len([e for e in es if e['pattern'] == k]) for k, _ in PATTERNS},
            meanScoreEff=fnum(np.mean([s['scoreEff'] for s in sessions if s['pid'] == pid])),
        ))
    withep = [p for p in people if p['feasibleEpisodes'] > 0]
    corr = dict(
        relianceVsAbandonFeasible=spearman([p['reliance'] for p in withep],
                                            [p['abandonFeasibleRate'] for p in withep]),
        tacticalUseVsAbandonFeasible=spearman([p['tacticalUse'] for p in withep],
                                               [p['abandonFeasibleRate'] for p in withep]),
        strategicUseVsAbandonFeasible=spearman([p['strategicUse'] for p in withep],
                                                [p['abandonFeasibleRate'] for p in withep]),
        relianceVsAbandonAll=spearman([p['reliance'] for p in people if p['episodes']],
                                      [p['abandonRate'] for p in people if p['episodes']]),
        abandonFeasibleVsScore=spearman([p['abandonFeasibleRate'] for p in withep],
                                        [p['meanScoreEff'] for p in withep]),
    )
    # tertile split on reliance, so the page can show the shape rather than just a rho
    rel_sorted = sorted(withep, key=lambda p: p['reliance'])
    k = len(rel_sorted)
    groups = []
    for gi, lab in enumerate(('Low reliance', 'Middle', 'High reliance')):
        g = rel_sorted[gi * k // 3:(gi + 1) * k // 3]
        eps = [e for e in episodes if e['pid'] in {p['pid'] for p in g} and e['feasible']]
        groups.append(dict(label=lab, people=len(g),
                           relianceRange=[fnum(g[0]['reliance']), fnum(g[-1]['reliance'])] if g else None,
                           episodes=len(eps),
                           abandonFeasible=fnum(np.mean([e['outcome'] == 'abandoned' for e in eps])) if eps else None,
                           personMean=fnum(np.mean([p['abandonFeasibleRate'] for p in g])) if g else None,
                           patterns={kk: len([e for e in eps if e['pattern'] == kk]) for kk, _ in PATTERNS}))
    # episode-level model: does this person's reliance predict abandoning a FIXABLE mission,
    # beyond the run and scenario it happened in?
    rel = {p['pid']: p['reliance'] for p in people}
    rows = [dict(pid=e['pid'], abandoned=float(e['outcome'] == 'abandoned'),
                 reliance=rel[e['pid']] * 10,   # per 10 percentage points
                 run2=float(e['run'] == 2), tacScen=float(e['scenario'] == 'tactical'))
            for e in episodes if e['feasible'] and e['outcome'] != 'unresolved' and rel.get(e['pid']) is not None]
    model = gee_logit(rows, 'abandoned', ['reliance', 'run2', 'tacScen'])
    # does clicking Suggest in a recovery go with abandoning more or less (feasible episodes)?
    fe = [e for e in episodes if e['feasible'] and e['outcome'] != 'unresolved']
    sug = [e for e in fe if e['suggest'] > 0]
    nos = [e for e in fe if e['suggest'] == 0]
    return dict(
        patterns=pats, patternLabels=PATTERNS, people=people, correlations=corr, groups=groups,
        model=model,
        suggestSplit=dict(
            withSuggest=dict(n=len(sug), abandoned=len([e for e in sug if e['outcome'] == 'abandoned'])),
            withoutSuggest=dict(n=len(nos), abandoned=len([e for e in nos if e['outcome'] == 'abandoned'])),
        ),
        feasibleEpisodes=len(fe), totalEpisodes=len(episodes),
        blindSpot=[{k: e.get(k) for k in ('pid', 'run', 'scenario', 'missionId', 'category', 'suggest',
                                           'drags', 'outcome', 'latency', 'suggestToOutcome')}
                   for e in episodes if not e['feasible'] and e.get('feasibleWithBusy')],
        episodes=[{k: e.get(k) for k in ('pid', 'run', 'scenario', 'missionId', 'category', 'feasible',
                                          'suggest', 'drags', 'outcome', 'pattern', 'latency',
                                          'suggestToOutcome')} for e in episodes],
        byRun={str(r): dict(n=len([e for e in fe if e['run'] == r]),
                            abandoned=len([e for e in fe if e['run'] == r and e['outcome'] == 'abandoned']))
               for r in (1, 2)},
    )


def reliance_vs_performance(sessions):
    people = {}
    for s in sessions:
        people.setdefault(s['pid'], []).append(s)
    pts = []
    for pid, ss in sorted(people.items()):
        pts.append(dict(pid=pid,
                        strategicUse=fnum(np.mean([s['strategicUse'] for s in ss if s['strategicUse'] is not None])),
                        tacticalUse=fnum(np.mean([s['tacticalUse'] for s in ss if s['tacticalUse'] is not None])),
                        scoreEff=fnum(np.mean([s['scoreEff'] for s in ss])),
                        completion=fnum(np.mean([s['completion'] for s in ss if s['completion'] is not None]))))
    # within-person: does the run where you used the assistant more go with the better score, once
    # the run and scenario effects are taken out? Residualise both on run+scenario cell means.
    def resid(metric):
        cell = {}
        for s in sessions:
            cell.setdefault((s['run'], s['scenario']), []).append(s[metric])
        cm = {k: np.mean([v for v in vs if v is not None]) for k, vs in cell.items()}
        return {(s['pid'], s['run']): (s[metric] - cm[(s['run'], s['scenario'])]) if s[metric] is not None else None
                for s in sessions}
    within = {}
    for use in ('strategicUse', 'tacticalUse'):
        ru, rs = resid(use), resid('scoreEff')
        d_use, d_sc = [], []
        for pid in people:
            if (pid, 1) in ru and (pid, 2) in ru and None not in (ru[(pid, 1)], ru[(pid, 2)]):
                d_use.append(ru[(pid, 2)] - ru[(pid, 1)])
                d_sc.append(rs[(pid, 2)] - rs[(pid, 1)])
        within[use] = spearman(d_use, d_sc)
    return dict(
        people=pts,
        between=dict(strategic=spearman([p['strategicUse'] for p in pts], [p['scoreEff'] for p in pts]),
                     tactical=spearman([p['tacticalUse'] for p in pts], [p['scoreEff'] for p in pts])),
        within=within,
    )


def balance(sessions):
    """Order x game-load table -- the recruitment tracker. Balanced means every cell equal."""
    ppl = {}
    for s in sessions:
        ppl[s['pid']] = (s['order'], s['load'])
    cells = {f'{o}|{l}': sorted(p for p, v in ppl.items() if v == (o, l))
             for o in ('SF', 'TF') for l in ('heavy', 'light')}
    return dict(cells=cells, counts={k: len(v) for k, v in cells.items()})


def load_contrast(sessions, metric):
    """Heavy-game vs light-game participants on one metric, each person averaged over both runs.
    Only free of order once both order groups appear in both load groups (see balance())."""
    per = {}
    for s in sessions:
        if s[metric] is not None:
            per.setdefault(s['pid'], []).append(s)
    heavy = [np.mean([x[metric] for x in v]) for v in per.values() if v[0]['load'] == 'heavy']
    light = [np.mean([x[metric] for x in v]) for v in per.values() if v[0]['load'] == 'light']
    return welch(heavy, light)


GAME_NOTE = ('Every participant used seed 42, and the mission stream is seeded by seed ^ session '
             'number (gameReducer.ts). So each scenario x run cell is one fixed game, played only by one '
             'order group: the four cells are four different games.')


def games(sessions):
    """One entry per game (scenario x game index), with how often it was played first or second."""
    out = {}
    for game in sorted({s['game'] for s in sessions}):
        cell = [s for s in sessions if s['game'] == game]
        if cell:
            out[game] = dict(
                scenario=cell[0]['scenario'], gameIndex=cell[0]['gameIndex'], load=cell[0]['gameLoad'],
                asRun1=len([s for s in cell if s['run'] == 1]), asRun2=len([s for s in cell if s['run'] == 2]),
                people=len(cell), availablePoints=sorted({s['availablePoints'] for s in cell}),
                missions=sorted({s['missionsArrived'] for s in cell}),
                tasks=sorted({s['nTasks'] for s in cell}),
                workDroneSec=sorted({s['workDroneSec'] for s in cell}),
                score=describe([s['score'] for s in cell]),
                scoreEff=describe([s['scoreEff'] for s in cell]))
    return out


def power(n_pairs, n_a, n_b):
    """Smallest standardised effect detectable at 80% power, alpha .05 two-sided -- so the page
    can say what this n can and cannot see instead of a blanket 'not enough people'."""
    from statsmodels.stats.power import TTestPower, TTestIndPower
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        paired = TTestPower().solve_power(nobs=n_pairs, alpha=.05, power=.8) if n_pairs > 2 else None
        indep = TTestIndPower().solve_power(nobs1=n_a, ratio=n_b / n_a, alpha=.05, power=.8)             if min(n_a, n_b) > 2 else None
    return dict(pairedD=fnum(paired), run2OnlyD=fnum(indep), nPairs=n_pairs, nA=n_a, nB=n_b)


def analyse(sessions, decisions, episodes):
    pids = sorted({s['pid'] for s in sessions})
    order_n = {g: len({s['pid'] for s in sessions if s['order'] == g}) for g in ('SF', 'TF')}
    metrics = PERF + USE
    return dict(
        n=len(pids), pids=pids, sessions=len(sessions), orderN=order_n,
        power=power(len(pids), order_n['SF'], order_n['TF']),
        nDecisions={t: len([d for d in decisions if d['tier'] == t]) for t in ('strategic', 'tactical', 'recovery')},
        crossover={m: crossover(sessions, m) for m, _ in metrics},
        run2only={m: between(sessions, m, 2) for m, _ in metrics},
        run1only={m: between(sessions, m, 1) for m, _ in metrics},
        cellsDesc={m: {f'{sc}|{r}': describe([s[m] for s in sessions if s['scenario'] == sc and s['run'] == r])
                       for sc in ('strategic', 'tactical') for r in (1, 2)} for m, _ in metrics},
        drift=reliance_drift(decisions),
        ladders=ladders(decisions),
        games=games(sessions),
        balance=balance(sessions),
        loadContrast={m: load_contrast(sessions, m) for m, _ in metrics},
        category=by_category(decisions),
        failures=failure_analysis(sessions, episodes, decisions),
        useVsPerf=reliance_vs_performance(sessions),
        scoreVsCompletion=spearman([s['scoreEff'] for s in sessions], [s['completion'] for s in sessions]),
        sessionRows=[{k: s[k] for k in ('pid', 'run', 'scenario', 'order', 'version', 'score', 'scoreEff',
                                        'completion', 'penalty', 'availablePoints', 'strategicUse',
                                        'tacticalUse', 'strategicBlind', 'tacticalAccept', 'recoveryUse',
                                        'nStrategic', 'nTactical', 'failures', 'episodes', 'abandons',
                                        'abandonsFeasible', 'reliance', 'game', 'gameLoad', 'load',
                                        'swapped')} for s in sessions],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--print', action='store_true')
    a = ap.parse_args()

    S, D, E = load()
    out = dict(metricsPerf=PERF, metricsUse=USE, patterns=PATTERNS, ladders=LADDERS, cohorts=[],
               excludedAlways=EXCLUDE_ALWAYS, gameNote=GAME_NOTE,
               generated=__import__('datetime').date.today().isoformat())
    for c in COHORTS:
        keep = lambda x: x['pid'] not in EXCLUDE_ALWAYS and x_rank.get(x['pid'], -1) >= c['minrank']
        x_rank = {}
        for s in S:   # a participant's cohort is set by their OLDEST session's build
            x_rank[s['pid']] = min(x_rank.get(s['pid'], 99), s['vrank'])
        s1 = [s for s in S if keep(s)]
        d1 = [d for d in D if keep(d)]
        e1 = [e for e in E if keep(e)]
        ol = outliers(s1)
        flagged = {o['pid'] for o in ol if o['flagged']}
        entry = dict(key=c['key'], label=c['label'], note=c['note'], outliers=ol,
                     versions=sorted({s['version'] for s in s1}, key=vrank),
                     full=analyse(s1, d1, e1))
        if flagged:
            f = lambda xs: [x for x in xs if x['pid'] not in flagged]
            entry['trimmed'] = analyse(f(s1), f(d1), f(e1))
        out['cohorts'].append(entry)

    OUT_JSON.write_text(json.dumps(out, indent=1), encoding='utf-8')
    if TEMPLATE.exists():
        html = TEMPLATE.read_text(encoding='utf-8')
        payload = json.dumps(out, separators=(',', ':'), ensure_ascii=True).replace('</', '<\\/')
        OUT_HTML.write_text(html.replace('/*__DATA__*/null', payload), encoding='utf-8')
        print('wrote', OUT_HTML.relative_to(BASE))
    print('wrote', OUT_JSON.relative_to(BASE))
    if a.print:
        summary(out)


def summary(out):
    for c in out['cohorts']:
        for variant in ('full', 'trimmed'):
            if variant not in c:
                continue
            r = c[variant]
            print(f"\n==== {c['label']} [{variant}]  n={r['n']} {r['orderN']} decisions={r['nDecisions']}")
            if variant == 'full':
                print('  outliers:', [(o['pid'], o['reasons']) for o in c['outliers'] if o['flagged']])
            for m, lab in PERF + USE:
                x = r['crossover'][m]
                if 'scenario' not in x:
                    continue
                sc, ru, co = x['scenario'], x['run'], x['carryover']
                r2 = r['run2only'][m]
                print(f"  {lab:34s} S={x['means']['strategic']:.3g} T={x['means']['tactical']:.3g} "
                      f"| scen T-S={sc['diff']:+.3g} p={sc['p']:.3f} | run2-1={ru['diff']:+.3g} p={ru['p']:.3f} "
                      f"| carry p={co['p']:.2f} | run2-only T-S={r2['diff']:+.3g} p={r2['p']:.3f}")
            f = r['failures']
            print('  patterns', f['patterns'])
            print('  suggestSplit', f['suggestSplit'], 'byRun', f['byRun'])
            print('  corr', {k: (v['rho'] and round(v['rho'], 2), v['p'] and round(v['p'], 3), v['n'])
                             for k, v in f['correlations'].items()})
            print('  groups', [(g['label'], g['relianceRange'], g['episodes'], g['abandonFeasible']) for g in f['groups']])
            print('  model', f['model'])
            cat = r['category']
            for tier in ('strategic', 'tactical', 'recovery'):
                cells = cat['cells'][f'{tier}|all']
                print(f"  cat {tier}:", [(x['cat'], x['decisions'], x['mean'] and round(x['mean'], 2)) for x in cells])
                print('     model', cat['models'][tier])
            print('  mix', cat['mix'])
            print('  drift', {k: [(x['mean'] and round(x['mean'], 2)) for x in v] for k, v in r['drift'].items()})
            print('  useVsPerf', r['useVsPerf']['between'], r['useVsPerf']['within'])
            print('  scoreVsCompletion', r['scoreVsCompletion'])


if __name__ == '__main__':
    main()
