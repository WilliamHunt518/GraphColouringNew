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
  This also covers the two questionnaire streams, which no report had ever used: the post-session
  NASA-TLX and per-assistant trust scales (`survey_response` events), and the pre-study
  demographics, prior-experience items and AI-disposition batteries (the `demographics` block).
  The scoring of the batteries is imported from `agent_scenario_stats.score_attitudes` and the
  crossover estimator from `study_analysis.crossover` rather than rewritten here -- see the import
  block below for why.
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
import sys
import warnings
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / 'scripts'))

# The questionnaire scoring and the crossover test are IMPORTED, not re-written. Both already exist
# and are already the canonical version used elsewhere: `score_attitudes` implements the scoring
# docs/STUDY_BUILD.md section 10 specifies (which items reverse-key, which are excluded from a
# composite), and `crossover` is the Jones & Kenward 2x2 analysis the log-only report runs on every
# performance measure. Reimplementing either here would let the two pages drift apart.
from agent_scenario_stats import (AIAS_ITEMS, DELEG_ITEMS, DELEG_REVERSED,  # noqa: E402
                                  EXPERIENCE_LEVELS, VERIF_ITEMS, VERIF_MODERATOR, VERIF_REVERSED,
                                  score_attitudes)
from study_analysis import crossover, spearman, welch  # noqa: E402
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
            scenario, need, pending, idx = None, {}, {}, 0
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
                        **{k: m[k] for k in
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
    # second pass rather than inline -- the same trap as mission_completed above. The post-session
    # trust survey has exactly the same shape and used to be read inline, which silently produced
    # nothing at all: `trust` was reset at the top of each run and only assigned when the survey
    # event was reached, which is the LAST thing in a session, so every decision row carried None
    # and the carry-over trust correlation ran on n = 0. It is attached here instead.
    scores, trust_s = {}, {}
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, events in enumerate(log['sessions'], start=1):
            for ev in events:
                if ev['type'] == 'session_ended':
                    scores[(pid, run)] = ev.get('score')
                elif ev['type'] == 'survey_response' and ev.get('surveyName') == 'trust_strategic':
                    vals = [v for v in (ev.get('responses') or {}).values()
                            if isinstance(v, (int, float))]
                    if vals:
                        trust_s[(pid, run)] = float(np.mean(vals))
    df['sessionScore'] = [scores.get((r.pid, r.run)) for r in df.itertuples()]
    df['trust'] = [trust_s.get((r.pid, r.run)) for r in df.itertuples()]
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


# ── the questionnaires: between-session surveys, and what people brought with them ────────────
#
# Everything below reads the two instrument streams the behavioural analysis above ignores:
#
#   * after EVERY session -- NASA-TLX (6 sliders, 0-20) and two six-item 7-point trust scales, one
#     per assistant, with IDENTICAL item stems. Same instrument twice per person, so the tier
#     contrast is within-person and paired, and the scenario contrast is a crossover like any other
#     per-session measure.
#   * before session 1 -- demographics, five prior-experience items, and the three AI-disposition
#     batteries (AIAS-4, verification propensity, delegation boundary) added in study-v1.3.
#
# Neither stream had ever been reported. They were collected, logged, and scored by
# `agent_scenario_stats.score_attitudes`, and then read by nothing.

TLX_ITEMS = ['mental_demand', 'physical_demand', 'temporal_demand', 'performance', 'effort',
             'frustration']
TLX_LABEL = {'mental_demand': 'Mental demand', 'physical_demand': 'Physical demand',
             'temporal_demand': 'Time pressure', 'performance': 'Own performance (high = failure)',
             'effort': 'Effort', 'frustration': 'Frustration'}
# The two trust scales share these six stems verbatim, prefixed `strat_`/`tact_`. That is what
# makes the tier difference a paired contrast rather than two unrelated numbers.
TRUST_STEMS = ['reliable', 'trust', 'performs', 'confident', 'useful', 'follow']
TRUST_STEM_LABEL = {'reliable': 'is reliable', 'trust': 'I trust its recommendations',
                    'performs': 'performs well', 'confident': 'I feel confident using it',
                    'useful': 'provides useful guidance',
                    'follow': 'I would follow it without hesitation'}
FREQUENCY_LEVELS = {'Never': 0, 'Rarely': 1, 'Occasionally': 2, 'Weekly': 3, 'Daily': 4}
# Prior-experience axes, each with the coding its answer options use. Ordinal, so a median split is
# the only defensible grouping -- the gaps between 'A little' and 'Moderate' are not units.
EXPERIENCE_AXES = [
    ('autonomy_experience', 'Automation / AI assistants', EXPERIENCE_LEVELS),
    ('strategy_experience', 'Real-time strategy games', EXPERIENCE_LEVELS),
    ('sim_experience', 'Simulation software', EXPERIENCE_LEVELS),
    ('command_experience', 'Dispatch / command / ATC', EXPERIENCE_LEVELS),
    ('drone_experience', 'Operating drones', EXPERIENCE_LEVELS),
    ('gaming_frequency', 'Plays video games', FREQUENCY_LEVELS),
]
# Behaviour the questionnaires are tested against. Each is a per-session rate, averaged per person
# for the person-level tests. The three reliance measures are deliberately the SAME definitions the
# log-only report's reliance ladder uses, so a disposition result here can be read next to it.
BEHAVIOURS = [('took', 'Took a strategy card'), ('consult', 'Consulted the tactical plan'),
              ('accept', 'Took the tactical plan unmodified'), ('secs', 'Strategic decision time'),
              ('score', 'Session score')]


def _quietly(fn):
    """Run `fn` with warnings suppressed. Used only where the warning is expected and documented."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn()


def f(x):
    """None for anything JSON cannot carry meaningfully -- absence, never a silent zero."""
    if x is None:
        return None
    x = float(x)
    return None if (np.isnan(x) or np.isinf(x)) else x


def alpha(mat):
    """Cronbach's alpha. Rows are respondents, columns items; None if it cannot be computed.

    Reported for every composite on the page because two of them are bespoke, and a null result
    from an unreliable scale is a fact about the scale, not about the operators.
    """
    m = np.array([r for r in mat if all(v is not None for v in r)], float)
    if m.shape[0] < 3 or m.shape[1] < 2:
        return None
    k = m.shape[1]
    tv = m.sum(axis=1).var(ddof=1)
    return f(k / (k - 1) * (1 - m.var(axis=0, ddof=1).sum() / tv)) if tv > 0 else None


def holm(ps):
    """Holm-Bonferroni adjusted p-values, in the input order.

    Every questionnaire test on this page is exploratory and none was pre-registered, so the whole
    family is corrected and both the raw and adjusted value are shown. Without this, a page running
    ~50 correlations at n = 32 would be guaranteed to display two or three 'findings'.
    """
    idx = sorted(range(len(ps)), key=lambda i: (ps[i] is None, ps[i]))
    out, run = [None] * len(ps), 0.0
    m = sum(1 for p in ps if p is not None)
    for rank, i in enumerate(x for x in idx if ps[x] is not None):
        run = max(run, min(1.0, ps[i] * (m - rank)))
        out[i] = run
    return out


def load_people():
    """One row per session (surveys + the behaviour they are tested against), one dict per person.

    Behaviour is recomputed here rather than taken from `load_decisions` because the tactical and
    recovery tiers never enter that table -- it is a strategic-decision table by construction, and
    half the question here is whether a disposition predicts use of one tier but not the other.
    """
    sess, people = [], {}
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        dem = log.get('demographics') or {}
        people[pid] = dict(score_attitudes(dem), pid=pid, dem=dem)
        for run, events in enumerate(log['sessions'], start=1):
            start = next((e for e in events if e['type'] == 'session_start'), {})
            end = next((e for e in events if e['type'] == 'session_ended'), {})
            sv = {e['surveyName']: (e.get('responses') or {})
                  for e in events if e['type'] == 'survey_response'}
            tlx, ts, tt = sv.get('nasa_tlx', {}), sv.get('trust_strategic', {}), sv.get('trust_tactical', {})
            # Raw TLX (the unweighted mean of the six subscales): no pairwise-comparison weights
            # were collected, which is the standard RTLX simplification. The `performance` slider is
            # NOT reverse-scored -- the app reproduces NASA's own anchors, Perfect on the left and
            # Failure on the right, so a high raw value already means a bad self-rating and
            # contributes to workload in the same direction as the other five.
            mean = lambda d: f(np.mean(list(d.values()))) if d else None
            items_s = {k.split('_', 1)[1]: v for k, v in ts.items()}
            items_t = {k.split('_', 1)[1]: v for k, v in tt.items()}

            confirms = [e for e in events if e['type'] == 'tactical_confirmed']
            # Identical to the log-only report's reliance ladder: 'consulted' is having pressed
            # Suggest at all (the planner starts empty, so it is a real decision), 'accepted' is
            # consulting and then deploying the agent's plan unmodified.
            consulted = [e for e in confirms if (e.get('suggestUsedCount') or 0) > 0]
            unmod = [e for e in consulted
                     if e.get('agentPlan') and not e.get('modifiedFromAgentPlan')]
            choices = [e for e in events if e['type'] == 'strategic_choice']
            cards = [e for e in choices if e.get('choiceType') in ('aggressive', 'conservative')]
            lat = [e['latencyMs'] / 1000 for e in choices if e.get('latencyMs')]

            sess.append(dict(
                pid=pid, run=run, scenario=start.get('complexity'),
                version=start.get('appVersion'),
                rtlx=f(np.mean([tlx[k] for k in TLX_ITEMS])) if len(tlx) == len(TLX_ITEMS) else None,
                **{('tlx_' + k): tlx.get(k) for k in TLX_ITEMS},
                trust_s=mean(ts), trust_t=mean(tt),
                trust_d=(mean(tt) - mean(ts)) if (ts and tt) else None,
                items_s=items_s, items_t=items_t,
                # A respondent who left every slider and every button where it started has answered
                # nothing; flagged rather than quietly averaged in.
                flat=bool(tlx and ts and tt
                          and len(set(list(tlx.values()) + list(ts.values())
                                      + list(tt.values()))) == 1),
                nstrat=len(choices), nconf=len(confirms),
                took=f(len(cards) / len(choices)) if choices else None,
                consult=f(len(consulted) / len(confirms)) if confirms else None,
                accept=f(len(unmod) / len(confirms)) if confirms else None,
                secs=f(np.median(lat)) if lat else None,
                score=end.get('score')))
    return sess, people


def per_person(sess, keys):
    """Average each session-level measure within person -- the unit the dispositions live at."""
    out = {}
    for s in sess:
        out.setdefault(s['pid'], {k: [] for k in keys})
        for k in keys:
            if s.get(k) is not None:
                out[s['pid']][k].append(float(s[k]))
    return {pid: {k: (f(np.mean(v)) if v else None) for k, v in d.items()} for pid, d in out.items()}


def analyse_selfreport(sess, people) -> dict:
    """What operators reported after each session: workload, and trust in each assistant."""
    ok = [s for s in sess if s['rtlx'] is not None and s['trust_s'] is not None]
    ids = sorted(people)
    per = per_person(sess, [k for k, _ in BEHAVIOURS] + ['rtlx', 'trust_s', 'trust_t'])

    def desc(key, src=None):
        v = [x[key] for x in (src or ok) if x.get(key) is not None]
        return dict(key=key, mean=f(np.mean(v)), sd=f(np.std(v, ddof=1)), n=len(v),
                    lo=f(min(v)), hi=f(max(v)))

    # 1 · the tier contrast, paired within person over both of their sessions ---------------------
    a = np.array([per[p]['trust_s'] for p in ids], float)
    b = np.array([per[p]['trust_t'] for p in ids], float)
    d = b - a
    t, pv = stats.ttest_rel(b, a)
    ci = stats.t.ppf(.975, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d))
    gap = dict(n=len(d), diff=f(d.mean()), t=f(t), p=f(pv), dz=f(d.mean() / d.std(ddof=1)),
               lo=f(d.mean() - ci), hi=f(d.mean() + ci),
               # Ties are inevitable on a 6-item mean of a 7-point scale, so scipy falls back to
               # the normal approximation and warns about it. Expected, and the t-test above is the
               # primary test -- this is the distribution-free check beside it.
               wilcoxon=f(_quietly(lambda: stats.wilcoxon(b, a).pvalue)),
               higherTactical=int((d > 0).sum()), higherStrategic=int((d < 0).sum()),
               tied=int((d == 0).sum()),
               # per-session rather than per-person, for the same contrast at the unit the
               # instrument was actually administered at
               sessionDiff=f(np.mean([s['trust_d'] for s in ok])),
               sessionP=f(stats.ttest_rel([s['trust_t'] for s in ok],
                                          [s['trust_s'] for s in ok]).pvalue),
               nSessions=len(ok))

    # 2 · which item carries it -------------------------------------------------------------------
    items = []
    for stem in TRUST_STEMS:
        vs = [s['items_s'][stem] for s in ok if stem in s['items_s']]
        vt = [s['items_t'][stem] for s in ok if stem in s['items_t']]
        items.append(dict(stem=stem, label=TRUST_STEM_LABEL[stem],
                          strategic=f(np.mean(vs)), tactical=f(np.mean(vt)),
                          diff=f(np.mean(vt) - np.mean(vs)), n=len(vs)))

    # 3 · the crossover, run on the questionnaires exactly as on every performance measure --------
    cross = []
    for key, label in (('rtlx', 'Workload (raw TLX, 0-20)'),
                       ('trust_s', 'Trust in the Strategic Assistant'),
                       ('trust_t', 'Trust in the Tactical Assistant'),
                       ('trust_d', 'Trust gap (tactical - strategic)'),
                       ('took', 'Took a strategy card'),
                       ('consult', 'Consulted the tactical plan'),
                       ('score', 'Session score')):
        r = crossover(sess, key)
        if not r.get('scenario'):
            continue
        cross.append(dict(key=key, label=label, n=r['n'], means=r['means'],
                          scenario=r['scenario'], run=r['run'], carryover=r['carryover']))
    tlxCross = []
    for key in TLX_ITEMS:
        r = crossover(sess, 'tlx_' + key)
        if r.get('scenario'):
            tlxCross.append(dict(key=key, label=TLX_LABEL[key], n=r['n'], means=r['means'],
                                 scenario=r['scenario'], run=r['run']))

    # 4 · do the questionnaires track behaviour? --------------------------------------------------
    # Session-level, so each pairing is a report and the behaviour it followed. The survey is
    # administered AFTER the session, which fixes the direction the correlation can be read in:
    # it cannot be reliance caused by a trust level measured later.
    link = [dict(label='Trust in Strategic Assistant / took a card that session', tier='strategic',
                 **spearman([s['trust_s'] for s in ok], [s['took'] for s in ok])),
            dict(label='Trust in Tactical Assistant / consulted the plan', tier='tactical',
                 **spearman([s['trust_t'] for s in ok], [s['consult'] for s in ok])),
            dict(label='Trust in Tactical Assistant / took the plan unmodified', tier='tactical',
                 **spearman([s['trust_t'] for s in ok], [s['accept'] for s in ok])),
            dict(label='Workload / took a card that session', tier='workload',
                 **spearman([s['rtlx'] for s in ok], [s['took'] for s in ok])),
            dict(label='Workload / session score', tier='workload',
                 **spearman([s['rtlx'] for s in ok], [s['score'] for s in ok]))]

    # Within-person change, which removes every stable difference between people at once: if a
    # person found their second session harder, did they lean on the assistants more in it?
    dr, dt, dc, dts = [], [], [], []
    for pid in ids:
        r = {s['run']: s for s in sess if s['pid'] == pid}
        if 1 in r and 2 in r and None not in (r[1]['rtlx'], r[2]['rtlx']):
            dr.append(r[2]['rtlx'] - r[1]['rtlx'])
            dt.append((r[2]['took'] or 0) - (r[1]['took'] or 0))
            dc.append((r[2]['consult'] or 0) - (r[1]['consult'] or 0))
            dts.append((r[2]['trust_s'] or 0) - (r[1]['trust_s'] or 0))
    within = [dict(label='Change in workload / change in card uptake', **spearman(dr, dt)),
              dict(label='Change in workload / change in tactical consulting', **spearman(dr, dc)),
              dict(label='Change in workload / change in strategic trust', **spearman(dr, dts))]

    # 5 · the same question asked of the debriefs --------------------------------------------------
    # The coder tagged each `agent_comparison` quote with a stance. Counted over PEOPLE, not quotes,
    # and a person can hold more than one stance across a debrief, so these do not sum to n.
    stance = Counter()
    for path in sorted(NARRATION.glob('*_s1/quotes.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        for st in {q.get('stance') for q in data.get('quotes', [])
                   if q['theme'] == 'agent_comparison' and q.get('stance')}:
            stance[st] += 1

    return dict(
        n=dict(sessions=len(ok), people=len(ids), flat=sum(1 for s in sess if s['flat'])),
        tlx=[desc('rtlx')] + [dict(desc('tlx_' + k), label=TLX_LABEL[k]) for k in TLX_ITEMS],
        trust=[dict(desc('trust_s'), label='Strategic Assistant'),
               dict(desc('trust_t'), label='Tactical Assistant')],
        gap=gap, items=items, crossover=cross, tlxCrossover=tlxCross, link=link, within=within,
        slopes=[dict(pid=p, a=per[p]['trust_s'], b=per[p]['trust_t']) for p in ids],
        alpha=dict(strategic=alpha([[s['items_s'].get(k) for k in TRUST_STEMS] for s in ok]),
                   tactical=alpha([[s['items_t'].get(k) for k in TRUST_STEMS] for s in ok])),
        stance=dict(stance), stanceCoded=len(list(NARRATION.glob('*_s1/quotes.json'))))


def analyse_disposition(sess, people) -> dict:
    """What operators brought with them, and whether any of it predicted how they used either tier."""
    ids = sorted(people)
    per = per_person(sess, [k for k, _ in BEHAVIOURS] + ['rtlx', 'trust_s', 'trust_t'])
    dem = {p: people[p]['dem'] for p in ids}

    # 1 · who they were ---------------------------------------------------------------------------
    ages = [dem[p].get('age') for p in ids if isinstance(dem[p].get('age'), (int, float))]
    counts = lambda key, order=None: [
        dict(label=k, n=v) for k, v in sorted(Counter(dem[p].get(key) for p in ids).items(),
                                              key=lambda kv: (order.index(kv[0]) if order and kv[0] in order else 99,
                                                              kv[0] or ''))]
    sample = dict(
        n=len(ids),
        age=dict(mean=f(np.mean(ages)), sd=f(np.std(ages, ddof=1)), lo=min(ages), hi=max(ages),
                 n=len(ages)),
        gender=counts('gender'),
        education=counts('education', ['Secondary / high school', 'Undergraduate degree',
                                       'Postgraduate / master’s', 'Doctorate', 'Other']),
        gaming=counts('gaming_frequency', list(FREQUENCY_LEVELS)),
        experience=[dict(label=label,
                         levels=[dict(label=lv, n=sum(1 for p in ids if dem[p].get(key) == lv))
                                 for lv in lvmap])
                    for key, label, lvmap in EXPERIENCE_AXES],
        # Free text, so grouped by hand into the only distinction that matters for generalisability:
        # this sample is almost entirely computing/engineering postgraduates.
        fieldStem=sum(1 for p in ids if any(
            w in (dem[p].get('field') or '').lower()
            for w in ('computer', 'comput', 'engineer', 'robot', 'ai', 'artificial', 'machine '
                      'learning', 'reinforcement', 'electron', 'electrical', 'physic', 'math'))),
        comprehension=[dict(key=k, agree=sum(1 for p in ids if dem[p].get(k) in
                                             ('Agree', 'Strongly agree')))
                       for k in ('understand_role', 'understand_missions', 'understand_strategic',
                                 'understand_tactical', 'understand_scoring')])

    # 2 · the batteries ---------------------------------------------------------------------------
    raws = {p: people[p].get('raw') or {} for p in ids}

    def battery(items, rev, top):
        return [[(top + 1 - raws[p][k]) if k in rev else raws[p][k] for k in items]
                for p in ids if all(k in raws[p] for k in items)]

    def dd(key, top):
        v = [people[p][key] for p in ids if people[p].get(key) is not None]
        return dict(mean=f(np.mean(v)), sd=f(np.std(v, ddof=1)), lo=f(min(v)), hi=f(max(v)),
                    n=len(v), top=top)
    batteries = [
        dict(key='aias', label='AIAS-4 (general attitude to AI)', scale='1-10', validated=True,
             alpha=alpha(battery(AIAS_ITEMS, set(), 10)), **dd('aias', 10)),
        dict(key='verification', label='Verification propensity', scale='1-7', validated=False,
             alpha=alpha(battery(VERIF_ITEMS, VERIF_REVERSED, 7)), **dd('verification', 7)),
        dict(key='delegation', label='Delegation boundary (human authority)', scale='1-7',
             validated=False, alpha=alpha(battery(DELEG_ITEMS, DELEG_REVERSED, 7)),
             **dd('delegation', 7))]

    # 3 · disposition against behaviour, one family, Holm-corrected together -----------------------
    # Composites first, then the two single items that were written to map onto this study's own
    # recommend-versus-decide contrast, then prior experience as a continuous measure.
    predictors = [('aias', 'AIAS-4 attitude to AI'),
                  ('verification', 'Verification propensity'),
                  ('delegation', 'Delegation boundary'),
                  ('delegTrustSuggestOverDecide', '“Trust AI more for suggesting than deciding”'),
                  ('delegHumanFinalSay', '“A human should make the final decision”'),
                  ('errorDetectability', '“Hard to tell when AI has erred”'),
                  ('experienceMean', 'Prior experience (mean of five items)'),
                  ('autonomyExperience', 'Experience with automation / AI')]
    cells = []
    for pkey, plabel in predictors:
        xs = [people[p].get(pkey) for p in ids]
        for bkey, blabel in BEHAVIOURS:
            r = spearman(xs, [per[p][bkey] for p in ids])
            cells.append(dict(predictor=pkey, predictorLabel=plabel, behaviour=bkey,
                              behaviourLabel=blabel, **r))
    for cell, adj in zip(cells, holm([c['p'] for c in cells])):
        cell['holm'] = f(adj)
    # Does disposition predict the SELF-REPORT, if not the behaviour? If post-session trust were a
    # trait being expressed rather than a reading taken on the session, it should.
    onTrust = [dict(predictor=pkey, predictorLabel=plabel, behaviour=bkey, behaviourLabel=blabel,
                    **spearman([people[p].get(pkey) for p in ids], [per[p][bkey] for p in ids]))
               for pkey, plabel in predictors[:3]
               for bkey, blabel in (('trust_s', 'Reported trust, strategic'),
                                    ('trust_t', 'Reported trust, tactical'),
                                    ('rtlx', 'Reported workload'))]

    # 4 · the tier-differential test ---------------------------------------------------------------
    # Delegation items 1-2 were written against this study's own structure: the Strategic Assistant
    # recommends and the operator decides, the Tactical Assistant plans the execution. If that
    # distinction is what operators are responding to, the item should predict the GAP between how
    # much they used each tier, not either level on its own.
    tierGap = []
    gaps = [(per[p]['took'] - per[p]['consult'])
            if None not in (per[p]['took'], per[p]['consult']) else None for p in ids]
    for pkey in ('delegTrustSuggestOverDecide', 'delegHumanFinalSay', 'delegation', 'aias'):
        tierGap.append(dict(predictor=pkey,
                            label=dict(predictors).get(pkey, pkey),
                            **spearman([people[p].get(pkey) for p in ids], gaps)))

    # 5 · prior experience as a grouping -----------------------------------------------------------
    # Median split on each ordinal axis, Welch between the groups -- the same test the log-only
    # report uses for between-group contrasts, chosen there because the groups need not share a
    # spread. Two axes are reported but cannot really be tested: nearly everyone answered 'None'.
    groups = []
    for key, label, lvmap in EXPERIENCE_AXES:
        vals = {p: lvmap.get(dem[p].get(key)) for p in ids}
        present = [v for v in vals.values() if v is not None]
        if not present:
            continue
        med = float(np.median(present))
        hi = [p for p in ids if vals[p] is not None and vals[p] > med]
        lo = [p for p in ids if vals[p] is not None and vals[p] <= med]
        rows = []
        for bkey, blabel in BEHAVIOURS:
            w = welch([per[p][bkey] for p in hi], [per[p][bkey] for p in lo])
            if w:
                rows.append(dict(behaviour=bkey, behaviourLabel=blabel, high=w['meanA'],
                                 low=w['meanB'], diff=w['diff'], p=w['p'], d=w['d']))
        groups.append(dict(key=key, label=label, median=med, nHigh=len(hi), nLow=len(lo),
                           floored=min(len(hi), len(lo)) < 8, rows=rows))

    # 6 · what the sample could have detected ------------------------------------------------------
    # Stated rather than left implicit, because almost everything in this part of the page is a
    # null and a null is only informative next to the effect it could have found.
    n = len([p for p in ids if people[p].get('aias') is not None])
    zb = stats.norm.ppf(.8) + stats.norm.ppf(.975)
    detectable = f(np.tanh(zb / np.sqrt(max(n - 3, 1))))

    return dict(
        sample=sample, batteries=batteries,
        coverage=dict(n=len(ids), withBattery=n,
                      missing=[p for p in ids if people[p].get('aias') is None]),
        cells=cells, onTrust=onTrust, tierGap=tierGap, groups=groups,
        nTests=len(cells), nNominal=sum(1 for c in cells if c['p'] is not None and c['p'] < .05),
        nHolm=sum(1 for c in cells if c['holm'] is not None and c['holm'] < .05),
        detectable=detectable, nDetect=n)


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
    sess, people = load_people()
    payload = dict(generated=date.today().isoformat(),
                   computed=analyse(df),
                   selfreport=analyse_selfreport(sess, people),
                   disposition=analyse_disposition(sess, people),
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
