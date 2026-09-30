#!/usr/bin/env python3
"""Build docs/reports/findings_synthesis.html -- the narrative results page.

The other two report pages each answer half the question. `two-tiers-two-scenarios.html` is the
log-only crossover analysis: performance, reliance, failures, outliers, with controls to switch
build window. `Results/Narration/decision-cards.html` is the per-decision narration. Neither one
tells you what the study found, because most of what it found lives in the join between them --
a behavioural regularity next to the sentence that explains it, or contradicts it.

This page is that join, written as an argument rather than a dashboard.

    python scripts/build_findings_synthesis.py          # needs numpy/pandas/scipy/statsmodels
    python scripts/build_findings_synthesis.py --print  # also dump the computed numbers

**Output lands in `Results/Narration/`, which is gitignored in full**, beside `decision-cards.html`
and the audio it is derived from. That is deliberate: the page embeds verbatim participant speech
alongside the pooled numbers, so it is identifiable data under the same terms as the recordings,
and it travels the way the rest of that data travels -- copied by hand, not through git. Regenerate
it locally; do not paste it into a hosted tool.

Everything needed to rebuild it IS committed (this script, its template, and
`docs/reports/smart_benchmark.json`), so the page is reproducible from the repo plus `Results/`.

## Where each number comes from

Three sources, kept distinct so a reader can audit any figure:

- **computed here** from `Results/Participants/*.json` -- everything about strategic decisions,
  card composition, pre-emption, timing and the artefact analyses. Recomputed on every build.
- **`docs/reports/study_analysis.json`** -- the crossover performance and reliance estimates, the
  reliance ladders, drift and failure-recovery episodes. Not recomputed; this page reads the
  numbers the existing pipeline already produced, so the two pages cannot disagree.
- **`Results/Narration/*_s1/quotes.json`** -- the coded debrief quotes, single-coder and
  uncalibrated (see docs/NARRATION.md). Every quote carries its participant and video timestamp.

P09 is excluded everywhere (ε = 0.2 fault test, participant did not follow the task).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

BASE = Path(__file__).resolve().parent.parent
PARTICIPANTS = BASE / 'Results' / 'Participants'
NARRATION = BASE / 'Results' / 'Narration'
STUDY_JSON = BASE / 'docs' / 'reports' / 'study_analysis.json'
TEMPLATE = BASE / 'scripts' / 'findings_synthesis_template.html'
OUT_HTML = BASE / 'Results' / 'Narration' / 'findings_synthesis.html'

EXCLUDE = {'P09'}
CRITICALITY = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5}


# ── decision-level table ──────────────────────────────────────────────────────────────────────

def load_decisions() -> pd.DataFrame:
    """One row per strategic decision.

    'Needed' is the sum of PRIMARY requirements across the mission's tasks -- the reading an
    operator takes off the task badges. It is not a feasibility floor: drones are reused across
    tasks run in series, so a card committing fewer than this is not under-strength.
    """
    rows = []
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        starts = [e for s in log['sessions'] for e in s if e['type'] == 'session_start']
        if not starts:
            continue
        primary = starts[0]['taskPrimary']

        for run, events in enumerate(log['sessions'], start=1):
            completed = {e['missionId']: e for e in events if e['type'] == 'mission_completed'}
            # A mission abandoned mid-flight re-enters as a residual (`<id>-R`) carrying its parent's
            # category while holding only the tasks that were left. Category is otherwise EXACTLY the
            # task count (A=2 ... E=6), so residuals are the one thing that breaks it as a load
            # measure -- they are flagged here and excluded wherever category is used as load.
            residual = {e['missionId'] for e in events
                        if e['type'] == 'mission_arrived' and e.get('isResidual')}
            ntasks = {e['missionId']: len(e.get('tasks', []))
                      for e in events if e['type'] == 'mission_arrived'}
            scenario, need, pending, idx, trust = None, {}, {}, 0, None
            plan_index, session_score = run, None

            for ev in events:
                t = ev['type']
                if t == 'session_start':
                    scenario = ev.get('complexity')
                    plan_index = ev.get('planSeedIndex') or run
                elif t == 'session_ended':
                    session_score = ev.get('score')
                elif t == 'mission_arrived':
                    total = {'Blue': 0, 'Red': 0, 'Green': 0}
                    for task in ev.get('tasks', []):
                        for colour, n in primary[str(task['type'])].items():
                            total[colour] += n
                    need[ev['missionId']] = total
                elif t == 'survey_response' and ev.get('surveyName') == 'trust_strategic':
                    trust = float(np.mean(list(ev['responses'].values())))
                elif t == 'strategic_modal_opened':
                    req = need.get(ev['missionId'])
                    cards = {c['name']: c for c in ev.get('strategiesPresented', [])}
                    if not req or len(cards) < 2:
                        continue
                    cons, aggr = cards['Conservative'], cards['Aggressive']
                    ct, at = sum(cons['trueAssets'].values()), sum(aggr['trueAssets'].values())
                    pending[ev['missionId']] = dict(
                        opened_at=ev['timestamp'], cons_total=ct, aggr_total=at,
                        dominated=int(ct >= at and cons['displayedCompletionTime']
                                      >= aggr['displayedCompletionTime']),
                        odd=int(any(cons['trueAssets'].get(c, 0) > 0 and req[c] == 0 for c in req)),
                        ncolours=sum(1 for c in req if req[c] > 0), ndrones=sum(req.values()),
                        reveal=max(c['revealDelayMs'] for c in cards.values()))
                elif t == 'strategic_choice' and ev['missionId'] in pending:
                    m = pending.pop(ev['missionId'])
                    done = completed.get(ev['missionId'])
                    dc = ev.get('deltaVsConservative') or {}
                    da = ev.get('deltaVsAggressive') or {}
                    choice = ev.get('choiceType')
                    rows.append(dict(
                        pid=pid, run=run, scenario=scenario, idx=idx, choice=choice,
                        planIndex=plan_index,
                        residual=int(ev['missionId'] in residual or ev['missionId'].endswith('-R')),
                        sessionScore=None,
                        ntasks=ntasks.get(ev['missionId']),
                        elapsed=ev.get('elapsed'),
                        manual=int(choice == 'manual'),
                        took=int(choice in ('aggressive', 'conservative')),
                        category=ev.get('missionCategory'),
                        criticality=CRITICALITY.get(ev.get('missionCategory'), np.nan),
                        trust=trust, **{k: m[k] for k in
                                        ('cons_total', 'aggr_total', 'dominated', 'odd',
                                         'ncolours', 'ndrones', 'reveal')},
                        committed=sum((ev.get('assetsChosen') or {}).values()),
                        d_cons=sum(dc.values()) if dc else np.nan,
                        d_aggr=sum(da.values()) if da else np.nan,
                        early=ev.get('manualBeforeCardsLoaded'),
                        secs=(ev['timestamp'] - m['opened_at']) / 1000.0,
                        outcome=done.get('outcome') if done else None,
                        reward=done.get('rewardEarned') if done else None,
                        max_reward=done.get('maxReward') if done else None))
                    idx += 1
    df = pd.DataFrame(rows)
    df['band'] = pd.qcut(df.ndrones, 3, labels=['small', 'mid', 'large'])
    # session_ended arrives after every decision in that session, so the score is attached in a
    # second pass rather than inline -- the same trap as mission_completed above.
    scores = {}
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, events in enumerate(log['sessions'], start=1):
            for ev in events:
                if ev['type'] == 'session_ended':
                    scores[(pid, run)] = ev.get('score')
    df['sessionScore'] = [scores.get((r.pid, r.run)) for r in df.itertuples()]
    return df


def gee(formula, data, binomial=False):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    return smf.gee(formula, 'pid', data=data, family=fam,
                   cov_struct=sm.cov_struct.Exchangeable()).fit()


def term(model, name):
    return dict(b=float(model.params[name]), p=float(model.pvalues[name]),
                lo=float(model.conf_int().loc[name, 0]), hi=float(model.conf_int().loc[name, 1]))


# ── the analyses the narrative rests on ───────────────────────────────────────────────────────

def analyse(df: pd.DataFrame) -> dict:
    out = {}
    manual = df[df.manual == 1]

    out['n'] = dict(participants=int(df.pid.nunique()), decisions=int(len(df)),
                    manual=int(len(manual)), sessions=int(df.groupby(['pid', 'run']).ngroups))

    # 1 · pre-emption ---------------------------------------------------------------------------
    flag = manual.early.dropna()
    out['preemption'] = dict(
        overall=float(flag.mean()), n=int(len(flag)),
        byColours=[dict(colours=int(n), share=float(s.mean()), n=int(len(s)))
                   for n, s in ((n, manual[manual.ncolours == n].early.dropna())
                                for n in sorted(manual.ncolours.unique())) if len(s) >= 5])

    # the reveal delay is drawn at random per mission -> a natural experiment on latency itself
    med = df.reveal.median()
    lo, hi = df[df.reveal <= med], df[df.reveal > med]
    pool = (lo.manual.sum() + hi.manual.sum()) / (len(lo) + len(hi))
    se = np.sqrt(pool * (1 - pool) * (1 / len(lo) + 1 / len(hi)))
    out['revealExperiment'] = dict(
        medianMs=float(med), shortShare=float(lo.manual.mean()), longShare=float(hi.manual.mean()),
        nShort=int(len(lo)), nLong=int(len(hi)),
        z=float((hi.manual.mean() - lo.manual.mean()) / se))

    # 2 · decision time -------------------------------------------------------------------------
    timed = df.dropna(subset=['secs'])
    out['timing'] = dict(
        rows=[dict(colours=int(n), route=r, n=int(len(s)), median=float(s.median()))
              for n in sorted(df.ncolours.unique())
              for r, s in ((r, timed[(timed.ncolours == n) & (timed.choice == r)].secs)
                           for r in ('manual', 'aggressive', 'conservative')) if len(s) >= 5],
        model=term(gee('secs ~ manual + ncolours + ndrones + C(scenario)', timed), 'manual'))

    # 3 · what manual commits -------------------------------------------------------------------
    sized = manual.dropna(subset=['d_cons'])
    m = gee('d_cons ~ ncolours + ndrones + criticality + C(scenario)', sized)
    out['delta'] = dict(
        byBand=[dict(band=str(b), mean=float(s.d_cons.mean()), n=int(len(s)),
                     need=float(s.ndrones.mean()))
                for b, s in sized.groupby('band', observed=True)],
        byCategory=[dict(category=c, mean=float(s.mean()), n=int(len(s)))
                    for c, s in ((c, sized[sized.category == c].d_cons) for c in 'ABCDE')
                    if len(s) >= 5],
        model=dict(size=term(m, 'ndrones'), colours=term(m, 'ncolours'),
                   criticality=term(m, 'criticality')))

    both = manual.dropna(subset=['cons_total', 'aggr_total']).copy()
    lo_c = both[['cons_total', 'aggr_total']].min(axis=1)
    hi_c = both[['cons_total', 'aggr_total']].max(axis=1)
    both['position'] = np.where(both.committed < lo_c, 'below both',
                                np.where(both.committed > hi_c, 'above both', 'between'))
    share = both['position'].value_counts(normalize=True)
    out['position'] = dict(
        overall={k: float(share.get(k, 0)) for k in ('between', 'below both', 'above both')},
        n=int(len(both)),
        byBand=[dict(band=str(b),
                     **{k: float((s.position == k).mean()) for k in
                        ('between', 'below both', 'above both')}, n=int(len(s)))
                for b, s in both.groupby('band', observed=True)],
        totals=[dict(band=str(b), conservative=float(s.cons_total.mean()),
                     manual=float(s.committed.mean()), aggressive=float(s.aggr_total.mean()))
                for b, s in both.groupby('band', observed=True)])

    # 4 · the artefact ---------------------------------------------------------------------------
    out['artefact'] = dict(
        prevalence=float(df.odd.mean()),
        byScenario=[dict(scenario=s, share=float(g.odd.mean()), n=int(len(g)))
                    for s, g in df.groupby('scenario')],
        choiceShare={str(k): {c: float(v) for c, v in row.items()} for k, row in
                     (pd.crosstab(df.odd, df.choice, normalize='index')).iterrows()},
        nesting=[dict(colours=int(c), clean=int((g.odd == 0).sum()), odd=int(g.odd.sum()))
                 for c, g in df.groupby('ncolours')],
        dominatedShare=float(df.dominated.mean()),
        consBiggerByBand=[dict(band=str(b), share=float((s.cons_total > s.aggr_total).mean()),
                               conservative=float(s.cons_total.mean()),
                               aggressive=float(s.aggr_total.mean()), n=int(len(s)))
                          for b, s in df.groupby('band', observed=True)],
        dominatedChoiceShare={str(k): {c: float(v) for c, v in row.items()} for k, row in
                              (pd.crosstab(df.dominated, df.choice, normalize='index')).iterrows()})

    few = df[df.ncolours < 3]
    out['artefact']['within'] = dict(
        clean=float(few[few.odd == 0].took.mean()), nClean=int((few.odd == 0).sum()),
        odd=float(few[few.odd == 1].took.mean()), nOdd=int((few.odd == 1).sum()),
        model=term(gee('took ~ odd + C(scenario) + C(run) + idx', few, binomial=True), 'odd'))

    # carry-over: three independent tests, all of them null
    df2 = df.copy()
    df2['prior'] = df2.groupby(['pid', 'run']).odd.transform(lambda s: (s.cumsum() - s).gt(0).astype(int))
    df2['prev_odd'] = df2.groupby(['pid', 'run']).odd.shift()
    nxt = df2.dropna(subset=['prev_odd'])
    per_session = df.groupby(['pid', 'run']).agg(seen=('odd', 'sum'), trust=('trust', 'first')).dropna()
    rho, p = stats.spearmanr(per_session.seen, per_session.trust)
    out['carryover'] = dict(
        prior=term(gee('took ~ prior + C(scenario) + C(run) + idx', df2, binomial=True), 'prior'),
        nextAfterClean=float(nxt[nxt.prev_odd == 0].took.mean()),
        nextAfterOdd=float(nxt[nxt.prev_odd == 1].took.mean()),
        nNextClean=int((nxt.prev_odd == 0).sum()), nNextOdd=int((nxt.prev_odd == 1).sum()),
        nextModel=term(gee('took ~ prev_odd + C(scenario) + C(run) + idx', nxt, binomial=True),
                       'prev_odd'),
        trustRho=float(rho), trustP=float(p), trustN=int(len(per_session)))

    # 5 · what actually drives reliance ---------------------------------------------------------
    models = []
    for label, formula in (
            # Labels are kept short because they are chart row labels with a fixed gutter; the
            # caption on the chart spells out what each model contains.
            ('Scenario only', 'took ~ C(scenario) + C(run) + idx'),
            ('+ artefact', 'took ~ odd + C(scenario) + C(run) + idx'),
            ('+ composition', 'took ~ odd + ncolours + ndrones + C(scenario) + C(run) + idx')):
        mm = gee(formula, df, binomial=True)
        entry = dict(label=label, scenario=term(mm, 'C(scenario)[T.tactical]'))
        for name in ('odd', 'ncolours', 'ndrones'):
            if name in mm.params:
                entry[name] = term(mm, name)
        models.append(entry)
    out['drivers'] = models
    out['relianceByColours'] = [dict(colours=int(c), took=float(g.took.mean()), n=int(len(g)))
                                for c, g in df.groupby('ncolours') if len(g) >= 10]

    # 5b · the same question asked with BOTH load measures ---------------------------------------
    # Colours-needed and mission category answer "how demanding was this mission?" differently.
    # Category is the task count (A=2..E=6) and also sets the penalty rate, so it is the better
    # proxy for "lots of tasks and drones" -- but only once residual missions are removed, since
    # they inherit a parent's category with a fraction of its work. Both are reported everywhere
    # so the clearer signal can be picked on the evidence rather than asserted.
    real = df[df.residual == 0]
    out['load'] = dict(
        residualN=int(df.residual.sum()), realN=int(len(real)),
        byColours=[dict(k=int(c), took=float(g.took.mean()), manual=float(g.manual.mean()),
                        preempt=float(g[g.manual == 1].early.dropna().mean())
                        if len(g[g.manual == 1].early.dropna()) >= 5 else None,
                        n=int(len(g)))
                   for c, g in df.groupby('ncolours') if len(g) >= 10],
        byCategory=[dict(k=c, took=float(g.took.mean()), manual=float(g.manual.mean()),
                         preempt=float(g[g.manual == 1].early.dropna().mean())
                         if len(g[g.manual == 1].early.dropna()) >= 5 else None,
                         n=int(len(g)), tasks=float(g.ntasks.mean()),
                         drones=float(g.ndrones.mean()))
                    for c, g in real.groupby('category') if len(g) >= 10],
        # the residual distortion, shown rather than just asserted
        residualShape=[dict(k=c,
                            realTasks=float(real[real.category == c].ntasks.mean()),
                            residTasks=float(df[(df.residual == 1) & (df.category == c)].ntasks.mean())
                            if (df[(df.residual == 1) & (df.category == c)]).shape[0] else None,
                            residN=int(((df.residual == 1) & (df.category == c)).sum()))
                       for c in 'ABCDE'],
        deltaByCategory=[dict(k=c, mean=float(g.d_cons.mean()), n=int(len(g)))
                         for c, g in real[real.manual == 1].dropna(subset=['d_cons'])
                         .groupby('category') if len(g) >= 5],
        modelColours=term(gee('took ~ ncolours + C(scenario) + C(run) + idx', df, binomial=True),
                          'ncolours'),
        modelCategory=term(gee('took ~ criticality + C(scenario) + C(run) + idx', real,
                               binomial=True), 'criticality'))

    # 5c · event study: does an illogical card change anything AFTER it? --------------------------
    # Each session is re-indexed so position 0 is the first illogical card the operator saw. If
    # trust were being spent, uptake would step down and stay down to the right of zero.
    ev_rows = []
    for (pid, run), g in df.groupby(['pid', 'run']):
        g = g.sort_values('idx')
        first = g[g.odd == 1].idx.min()
        if pd.isna(first):
            continue
        for _, r in g.iterrows():
            ev_rows.append(dict(pid=pid, run=run, rel=int(r.idx - first), took=int(r.took),
                                ncolours=int(r.ncolours), ndrones=int(r.ndrones),
                                idx=int(r.idx), scenario=r.scenario))
    ev = pd.DataFrame(ev_rows)
    band = ev[(ev.rel >= -4) & (ev.rel <= 6)]
    # The raw series is not interpretable on its own. Every decision BEFORE the first illogical card
    # is necessarily a three-colour mission -- a colour has to go unused for the top-up to pad one,
    # so a three-colour mission can never produce one. The pre-period is therefore made entirely of
    # the most complex missions, which is exactly where uptake is highest anyway. Holding
    # composition fixed (three-colour missions only, on both sides) is what makes the comparison
    # mean anything, so both series are carried and the page shows them together.
    ev['after'] = (ev.rel > 0).astype(int)
    c3 = ev[ev.ncolours == 3]          # sliced AFTER 'after' exists, or the matched model has no term
    adj = gee('took ~ after + ncolours + ndrones + idx + C(scenario)', ev[ev.rel != 0], binomial=True)
    matched = gee('took ~ after + idx + C(scenario)', c3[c3.rel != 0], binomial=True)
    out['eventStudy'] = dict(
        sessions=int(ev.groupby(['pid', 'run']).ngroups),
        points=[dict(rel=int(k), took=float(v.took.mean()), n=int(len(v)))
                for k, v in band.groupby('rel') if len(v) >= 8],
        matchedPoints=[dict(rel=int(k), took=float(v.took.mean()), n=int(len(v)))
                       for k, v in c3[(c3.rel >= -4) & (c3.rel <= 6)].groupby('rel') if len(v) >= 8],
        composition=[dict(window=w, colours=float(x.ncolours.mean()), drones=float(x.ndrones.mean()),
                          position=float(x.idx.mean()), took=float(x.took.mean()), n=int(len(x)))
                     for w, x in (('before', ev[ev.rel < 0]), ('the card itself', ev[ev.rel == 0]),
                                  ('after', ev[ev.rel > 0]))],
        beforeAfter=dict(before=float(ev[ev.rel < 0].took.mean()),
                         nBefore=int((ev.rel < 0).sum()),
                         after=float(ev[ev.rel > 0].took.mean()),
                         nAfter=int((ev.rel > 0).sum()),
                         matchedBefore=float(c3[c3.rel < 0].took.mean()),
                         nMatchedBefore=int((c3.rel < 0).sum()),
                         matchedAfter=float(c3[c3.rel > 0].took.mean()),
                         nMatchedAfter=int((c3.rel > 0).sum())),
        adjusted=term(adj, 'after'), matchedModel=term(matched, 'after'),
        # individual sessions, so the aggregate is not the only thing on offer
        examples=[dict(pid=pid, run=int(run),
                       series=[dict(rel=int(r.rel), took=int(r.took)) for _, r in g.iterrows()])
                  for (pid, run), g in ev.sort_values('rel').groupby(['pid', 'run'])
                  if len(g) >= 8 and (g.rel < 0).sum() >= 1][:8])

    # 5d · learning: within a session, and between the two -----------------------------------------
    d2 = df.copy()
    d2['third'] = d2.groupby(['pid', 'run']).idx.transform(
        lambda s: pd.cut(s.rank(pct=True), [0, 1 / 3, 2 / 3, 1], labels=['early', 'mid', 'late'],
                         include_lowest=True))
    out['learning'] = dict(
        withinByRun=[dict(run=int(r), third=str(t), took=float(g.took.mean()), n=int(len(g)))
                     for (r, t), g in d2.groupby(['run', 'third'], observed=True)],
        withinByScenario=[dict(scenario=sc, third=str(t), took=float(g.took.mean()), n=int(len(g)))
                          for (sc, t), g in d2.groupby(['scenario', 'third'], observed=True)],
        runMeans=[dict(run=int(r), took=float(g.took.mean()), manual=float(g.manual.mean()),
                       preempt=float(g[g.manual == 1].early.dropna().mean()),
                       secs=float(g.secs.median()), n=int(len(g)))
                  for r, g in df.groupby('run')],
        perPerson=[dict(pid=pid,
                        r1=float(g[g.run == 1].took.mean()) if (g.run == 1).any() else None,
                        r2=float(g[g.run == 2].took.mean()) if (g.run == 2).any() else None)
                   for pid, g in df.groupby('pid')
                   if (g.run == 1).sum() >= 3 and (g.run == 2).sum() >= 3],
        runModel=term(gee('took ~ C(run) + ncolours + ndrones + C(scenario)', df, binomial=True),
                      'C(run)[T.2]'))

    # 6 · outcome of building it yourself --------------------------------------------------------
    fewo = df[(df.ncolours < 3) & df.outcome.notna()]
    out['outcome'] = dict(
        rows=[dict(route='manual' if v else 'took a card',
                   **{k: float(x) for k, x in
                      (pd.crosstab(fewo.manual, fewo.outcome, normalize='index').loc[v]).items()},
                   reward=float((fewo[(fewo.manual == v) & fewo.max_reward.gt(0)].reward /
                                 fewo[(fewo.manual == v) & fewo.max_reward.gt(0)].max_reward).mean()))
              for v in (0, 1)])
    return out


# ── the other two sources ─────────────────────────────────────────────────────────────────────

def benchmark(df: pd.DataFrame) -> dict:
    """Participant score against a near-perfect automated operator on the SAME game.

    `scoreEff` in the existing report divides by the reward on offer from the missions a person
    actually completed, which is a moving denominator. This is a fixed one: `sim/engine.mts --games`
    runs the SMART ('redundant') policy through the real reducer over the four fixed games the study
    used, and reports the score it achieves -- penalties included, since score is already net of
    them. A participant's share of that is comparable across scenarios in a way raw score is not,
    because it divides by what the SAME mission stream actually yields to competent play.

    Regenerate with:  npx tsx sim/engine.mts --games --reps=5 > docs/reports/smart_benchmark.json

    Caveat worth keeping attached: SMART over-allocates and recovers perfectly, and only the mission
    stream is matched (drone-failure draws are not), so this is a strong reference line rather than a
    true optimum. Values above 100% are possible and mean the operator beat it on that game.
    """
    path = BASE / 'docs' / 'reports' / 'smart_benchmark.json'
    if not path.exists():
        return {}
    ref = json.loads(path.read_text(encoding='utf-8'))
    key = {(g['complexity'], g['planIndex']): g for g in ref['games']}
    rows = []
    for (pid, run), g in df.groupby(['pid', 'run']):
        scenario, plan = g.scenario.iloc[0], int(g.planIndex.iloc[0])
        score = g.sessionScore.iloc[0]
        ben = key.get((scenario, plan))
        if ben is None or score is None or not ben['score']:
            continue
        rows.append(dict(pid=pid, run=int(run), scenario=scenario, planIndex=plan,
                         score=float(score), benchmark=float(ben['score']),
                         share=float(score) / float(ben['score'])))
    if not rows:
        return {}
    b = pd.DataFrame(rows)
    return dict(
        games=[dict(scenario=g['complexity'], planIndex=g['planIndex'], score=g['score'],
                    penalty=g['penalty'], tasks=g['tasks'], taskCompletion=g['taskCompletion'],
                    n=int(((b.scenario == g['complexity']) & (b.planIndex == g['planIndex'])).sum()))
               for g in ref['games']],
        byScenario=[dict(scenario=sc, share=float(x.share.mean()), n=int(len(x)),
                         lo=float(x.share.quantile(.25)), hi=float(x.share.quantile(.75)))
                    for sc, x in b.groupby('scenario')],
        byGame=[dict(scenario=sc, planIndex=int(pi), share=float(x.share.mean()), n=int(len(x)))
                for (sc, pi), x in b.groupby(['scenario', 'planIndex'])],
        byRun=[dict(run=int(r), share=float(x.share.mean()), n=int(len(x)))
               for r, x in b.groupby('run')],
        sessions=[dict(pid=r.pid, run=r.run, scenario=r.scenario, share=r.share)
                  for r in b.itertuples()],
        overall=float(b.share.mean()), policy=ref.get('policy', 'SMART'))


def from_study_analysis() -> dict:
    """Headline crossover numbers, read rather than recomputed so the two pages cannot disagree."""
    if not STUDY_JSON.exists():
        return {}
    d = json.loads(STUDY_JSON.read_text(encoding='utf-8'))
    cohort = d['cohorts'][0]
    r = cohort['full']
    labels = dict(d['metricsPerf'] + d['metricsUse'])
    metrics = []
    for key, label in d['metricsPerf'] + d['metricsUse']:
        x = r['crossover'].get(key, {})
        if 'scenario' not in x:
            continue
        metrics.append(dict(key=key, label=label,
                            strategic=x['means']['strategic'], tactical=x['means']['tactical'],
                            scenarioDiff=x['scenario']['diff'], scenarioP=x['scenario']['p'],
                            runDiff=x['run']['diff'], runP=x['run']['p']))
    f = r['failures']
    return dict(
        cohort=cohort['label'], cohortNote=cohort['note'], n=r['n'], orderN=r['orderN'],
        nDecisions=r['nDecisions'], metrics=metrics, ladderKeys=d['ladders'],
        ladders=r['ladders'], drift=r['drift'],
        patterns=f['patterns'], patternLabels=dict(d['patterns']),
        suggestSplit=f['suggestSplit'],
        scoreVsCompletion=r['scoreVsCompletion'], power=r['power'], versions=cohort['versions'],
        labels=labels)


def load_quotes() -> dict:
    """Coded debrief quotes. Single coder, uncalibrated -- the page says so where it uses them."""
    quotes, coded = [], []
    for path in sorted(NARRATION.glob('*_s1/quotes.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        pid = data['participantId']
        coded.append(pid)
        seg = NARRATION / ('%s_s1' % pid) / 'segments.json'
        expert = False
        if seg.exists():
            expert = json.loads(seg.read_text(encoding='utf-8')).get('consultedExpert', False)
        for q in data.get('quotes', []):
            quotes.append(dict(id='%s/%s/%d' % (pid, q['theme'], round(q['videoStart'])),
                               pid=pid, expert=bool(expert), theme=q['theme'],
                               at=round(q['videoStart']), text=q['text'],
                               note=q.get('note', ''), stance=q.get('stance', '')))
    return dict(quotes=quotes, participants=sorted(set(coded)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--print', action='store_true')
    args = ap.parse_args()

    df = load_decisions()
    payload = dict(generated=date.today().isoformat(),
                   computed=analyse(df),
                   benchmark=benchmark(df),
                   study=from_study_analysis(),
                   narration=load_quotes())

    if not TEMPLATE.exists():
        raise SystemExit('missing template: %s' % TEMPLATE)
    html = TEMPLATE.read_text(encoding='utf-8')
    blob = json.dumps(payload, separators=(',', ':'), ensure_ascii=True,
                      default=float).replace('</', '<\\/')
    OUT_HTML.write_text(html.replace('/*__DATA__*/null', blob), encoding='utf-8')
    print('wrote %s (%.0f KB)' % (OUT_HTML.relative_to(BASE), OUT_HTML.stat().st_size / 1024))
    print('%d decisions, %d participants, %d quotes from %d participants'
          % (payload['computed']['n']['decisions'], payload['computed']['n']['participants'],
             len(payload['narration']['quotes']), len(payload['narration']['participants'])))
    print('NOTE: written into the gitignored Results/Narration/ tree -- it holds verbatim participant')
    print('      speech, so it moves by hand with the rest of the identifiable data, not via git.')
    if args.print:
        print(json.dumps(payload['computed'], indent=1, default=float))


if __name__ == '__main__':
    main()
