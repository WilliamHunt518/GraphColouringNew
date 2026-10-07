"""Workstream F (round 2) -- shared loader for "how operators handle the strategic cards".

Read-only over Results/Participants/*.json. Writes nothing.

`decisions()` returns one row per strategic decision, with the SAME pairing rule as
`build_findings_synthesis.load_decisions()` (a `strategic_choice` counts only if a
`strategic_modal_opened` carrying both cards preceded it for that mission); row-for-row agreement
with the builder is asserted on every call. On top of the builder's columns it carries what
workstream F needs:

  * per-colour need (sum of primaries, the badge reading), card true assets, operator's chosen assets;
  * the reserve the operator saw when the modal opened (`reserveStateAvailable`, the displayed one)
    and at the moment of choice -- the ± picker is capped at the latter;
  * the card-preview sequence (`strategic_card_previewed`) and the manual-edit trail
    (`manual_allocation_edited`) for THIS opening of the modal (both reset on every re-open, so a
    dismissed modal's clicks are not carried into the next one);
  * queue / in-flight / time-left context at the choice;
  * game = scenario x planSeedIndex (session number where planSeedIndex is missing), order = the
    scenario of the person's session 1, swapped = P31-P36.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts' / 'analysis_round1'))
warnings.filterwarnings('ignore')

import build_findings_synthesis as B  # noqa: E402  (read-only: loader for the cross-check)

PARTICIPANTS = ROOT / 'Results' / 'Participants'
EXCLUDE = {'P09'}
COLOURS = ('Blue', 'Red', 'Green')
CARD = ('aggressive', 'conservative')
SWAPPED = {'P31', 'P32', 'P33', 'P34', 'P35', 'P36'}


def _v112(v):
    try:
        major, minor = str(v).replace('study-v', '').split('.')[:2]
        return (int(major), int(minor)) >= (1, 12)
    except Exception:
        return False


def decisions() -> pd.DataFrame:
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
        order = starts[0].get('complexity')
        version = starts[0].get('appVersion')
        for run, events in enumerate(log['sessions'], start=1):
            start = next(e for e in events if e['type'] == 'session_start')
            scenario = start.get('complexity')
            plan = start.get('planSeedIndex') or run
            fate = {e['missionId']: e.get('outcome') for e in events if e['type'] == 'mission_completed'}
            for e in events:
                if e['type'] == 'mission_abandoned':
                    fate[e['missionId']] = 'abandoned'
            residual = {e['missionId'] for e in events
                        if e['type'] == 'mission_arrived' and e.get('isResidual')}
            need, tasks, pending, idx = {}, {}, {}, 0
            for ev in events:
                t = ev['type']
                if t == 'mission_arrived':
                    tot = {c: 0 for c in COLOURS}
                    for task in ev.get('tasks', []):
                        for c, n in primary[str(task['type'])].items():
                            tot[c] += n
                    need[ev['missionId']] = tot
                    tasks[ev['missionId']] = tuple(sorted(int(task['type']) for task in ev.get('tasks', [])))
                elif t == 'strategic_modal_opened':
                    req = need.get(ev['missionId'])
                    cards = {c['name']: c for c in ev.get('strategiesPresented', [])}
                    if not req or len(cards) < 2:
                        continue
                    cons, aggr = cards['Conservative'], cards['Aggressive']
                    pending[ev['missionId']] = dict(
                        opened=ev['timestamp'], req=req,
                        cons=dict(cons['trueAssets']), aggr=dict(aggr['trueAssets']),
                        cons_disp=dict(cons['displayedAssets']), aggr_disp=dict(aggr['displayedAssets']),
                        cons_time=cons['displayedCompletionTime'], aggr_time=aggr['displayedCompletionTime'],
                        reveal=max(c['revealDelayMs'] for c in cards.values()),
                        res_open=dict(ev.get('reserveStateAvailable') or ev.get('reserveState')),
                        previews=[], edits=[])
                elif t == 'strategic_card_previewed' and ev['missionId'] in pending:
                    pending[ev['missionId']]['previews'].append((ev.get('strategyName'), ev.get('latencyMs')))
                elif t == 'manual_allocation_edited' and ev['missionId'] in pending:
                    pending[ev['missionId']]['edits'].append((dict(ev.get('allocation') or {}), ev.get('latencyMs')))
                elif t == 'strategic_choice' and ev['missionId'] in pending:
                    m = pending.pop(ev['missionId'])
                    mid, choice = ev['missionId'], ev.get('choiceType')
                    req = m['req']
                    chosen = {c: int((ev.get('assetsChosen') or {}).get(c, 0)) for c in COLOURS}
                    ctx = ev.get('context') or {}
                    ct, at = sum(m['cons'].values()), sum(m['aggr'].values())
                    row = dict(
                        pid=pid, run=run, version=version, v112=int(_v112(version)),
                        scenario=scenario, planIndex=plan, game='%s%d' % (scenario[0].upper(), plan),
                        order=order, swapped=int(pid in SWAPPED), idx=idx,
                        missionId=mid, mkey='%s%d:%s' % (scenario[0].upper(), plan, mid),
                        tasks=tasks.get(mid), category=ev.get('missionCategory'),
                        residual=int(mid in residual or mid.endswith('-R')),
                        choice=choice, took=int(choice in CARD), manual=int(choice == 'manual'),
                        early=ev.get('manualBeforeCardsLoaded'),
                        editedFrom=ev.get('editedFromStrategy'),
                        ncolours=sum(1 for c in COLOURS if req[c] > 0), ndrones=sum(req.values()),
                        cons_total=ct, aggr_total=at,
                        dominated=int(ct >= at and m['cons_time'] >= m['aggr_time']),
                        odd=int(any(m['cons'].get(c, 0) > 0 and req[c] == 0 for c in COLOURS)),
                        committed=sum(chosen.values()),
                        secs=(ev['timestamp'] - m['opened']) / 1000.0, reveal_s=m['reveal'] / 1000.0,
                        queued=ctx.get('missionsQueued'), active=ctx.get('missionsActive'),
                        recov=len(ctx.get('recoveryPendingMissionIds') or []),
                        left=ev.get('timeRemainingInSession'), elapsed=ev.get('elapsed'),
                        previews=m['previews'], edits=m['edits'],
                        fate=fate.get(mid, 'inflight'))
                    res_choice = dict(ev.get('reserveStateAvailable') or ev.get('reserveState'))
                    for c in COLOURS:
                        row['need_' + c] = req[c]
                        row['cons_' + c] = int(m['cons'].get(c, 0))
                        row['aggr_' + c] = int(m['aggr'].get(c, 0))
                        row['chosen_' + c] = chosen[c]
                        row['resO_' + c] = int(m['res_open'].get(c, 0))
                        row['resC_' + c] = int(res_choice.get(c, 0))
                        # sequential floor: the most of this colour any single task needs (drones are
                        # reused across tasks run in series, so this is the minimum that can finish)
                        row['floor_' + c] = max([int(primary[str(k)].get(c, 0)) for k in (tasks.get(mid) or ())] or [0])
                    row['res_open'] = sum(row['resO_' + c] for c in COLOURS)
                    row['res_choice'] = sum(row['resC_' + c] for c in COLOURS)
                    rows.append(row)
                    idx += 1
    df = pd.DataFrame(rows)
    _check(df)
    df['early'] = df['early'].map({True: 1, False: 0})
    df['npreview'] = df.previews.map(len)
    df['prev_names'] = df.previews.map(lambda p: frozenset(n for n, _ in p))
    df['prev_both'] = df.prev_names.map(lambda s: int(len(s) == 2))
    df['prev_cons'] = df.prev_names.map(lambda s: int('Conservative' in s))
    df['order_s'] = (df.order == 'strategic').astype(int)   # 1 = Strategic Heavy first
    return df


def _check(df):
    ref = B._quietly(B.load_decisions)
    a = df[['pid', 'run', 'idx', 'choice', 'odd', 'ncolours', 'ndrones', 'cons_total', 'aggr_total',
            'dominated', 'committed']].reset_index(drop=True)
    b = ref[['pid', 'run', 'idx', 'choice', 'odd', 'ncolours', 'ndrones', 'cons_total', 'aggr_total',
             'dominated', 'committed']].reset_index(drop=True)
    assert len(a) == len(b), (len(a), len(b))
    assert (a.values == b.values).all(), 'decision table disagrees with build_findings_synthesis'


# ── small-sample GEE helpers ─────────────────────────────────────────────────────────────────

def gee(formula, data, binomial=False, group='pid'):
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    return smf.gee(formula, group, data=data, family=fam,
                   cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type='bias_reduced')


def term(res, name, exp=False):
    from scipy import stats
    b, se = float(res.params[name]), float(res.bse[name])
    z = b / se if se > 0 else np.nan
    p = float(2 * stats.norm.sf(abs(z))) if se > 0 else np.nan
    lo, hi = b - 1.96 * se, b + 1.96 * se
    if exp:
        return dict(est=np.exp(b), lo=np.exp(lo), hi=np.exp(hi), p=p, b=b)
    return dict(est=b, lo=lo, hi=hi, p=p, b=b)
