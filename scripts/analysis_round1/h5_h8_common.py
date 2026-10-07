"""Shared loaders for H5 (strategic trust drop) and H8 (the illogical Conservative card).

Read-only over `Results/Participants/*.json`. Nothing here writes anywhere.

`decisions()` is a superset of `build_findings_synthesis.load_decisions()`: the same pairing rule
(a `strategic_choice` counts only if a `strategic_modal_opened` with both cards preceded it for that
mission), so the two tables have identical rows -- `decisions()` asserts that on every call -- but
it also carries the mission id, the mission's eventual fate, which drone types the Conservative card
padded, what the operator committed, and the manual-edit trail. Those are what H5 and H8 need and
the builder's table drops.

Mission fate (per mission, per session):
  * 'abandoned'  -- a `mission_abandoned` event for that mission id;
  * 'partial' / 'none_completed' -- `mission_completed.outcome` other than all_completed (some
    tasks failed);
  * 'ok'         -- `mission_completed.outcome == 'all_completed'`;
  * 'inflight'   -- neither: still running when the timer ended (listed in
    `session_ended.inFlightMissionIds`; checked -- every unresolved chosen mission is in that list).
  A residual (`<id>-R`) is its own mission with its own allocation decision, so its fate is its
  own and is NOT folded into the parent: the parent's failure is already recorded as the parent's
  abandonment, and the residual's allocation is a fresh choice (card or manual) whose credibility
  consequences attach to that choice.
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
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
warnings.filterwarnings('ignore')

import build_findings_synthesis as B  # noqa: E402  (read-only use: loaders + gee/term helpers)

PARTICIPANTS = ROOT / 'Results' / 'Participants'
EXCLUDE = {'P09'}
COLOURS = ('Blue', 'Red', 'Green')
CARD = ('aggressive', 'conservative')
BAD_FATES = ('abandoned', 'partial', 'none_completed')

# Brief template's complete list of debrief quotes describing the strategic assistant
# over-allocating (scripts/findings_brief_template.html, const OVERALLOC). Copied, not edited.
OVERALLOC = ['P01/agent_comparison/1596', 'P13/agent_comparison/1795', 'P17/agent_comparison/1393',
             'P19/trust_trajectory/1907', 'P20/trust_trajectory/1551', 'P21/agent_comparison/2103',
             'P28/agent_comparison/1796', 'P33/agent_comparison/1608', 'P35/agent_comparison/1793',
             'P36/agent_comparison/1892']


def _files():
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid not in EXCLUDE:
            yield pid, json.loads(Path(path).read_text(encoding='utf-8'))


def decisions() -> pd.DataFrame:
    rows = []
    for pid, log in _files():
        starts = [e for s in log['sessions'] for e in s if e['type'] == 'session_start']
        if not starts:
            continue
        primary = starts[0]['taskPrimary']
        for run, events in enumerate(log['sessions'], start=1):
            fate = {}
            for e in events:
                if e['type'] == 'mission_completed':
                    fate[e['missionId']] = e.get('outcome')
            for e in events:
                if e['type'] == 'mission_abandoned':
                    fate[e['missionId']] = 'abandoned'
            residual = {e['missionId'] for e in events
                        if e['type'] == 'mission_arrived' and e.get('isResidual')}
            start = next(e for e in events if e['type'] == 'session_start')
            scenario, version = start.get('complexity'), start.get('appVersion')
            plan = start.get('planSeedIndex') or run
            need, pending, edits, idx = {}, {}, {}, 0
            for ev in events:
                t = ev['type']
                if t == 'mission_arrived':
                    tot = {c: 0 for c in COLOURS}
                    for task in ev.get('tasks', []):
                        for c, n in primary[str(task['type'])].items():
                            tot[c] += n
                    need[ev['missionId']] = tot
                elif t == 'strategic_modal_opened':
                    req = need.get(ev['missionId'])
                    cards = {c['name']: c for c in ev.get('strategiesPresented', [])}
                    if not req or len(cards) < 2:
                        continue
                    cons, aggr = cards['Conservative']['trueAssets'], cards['Aggressive']['trueAssets']
                    pending[ev['missionId']] = dict(
                        opened=ev['timestamp'], req=req, cons=cons, aggr=aggr,
                        unneeded=[c for c in COLOURS if cons.get(c, 0) > 0 and req[c] == 0],
                        aggr_unneeded=[c for c in COLOURS if aggr.get(c, 0) > 0 and req[c] == 0])
                    edits[ev['missionId']] = []
                elif t == 'manual_allocation_edited' and ev['missionId'] in pending:
                    edits[ev['missionId']].append(ev.get('allocation') or {})
                elif t == 'strategic_choice' and ev['missionId'] in pending:
                    m = pending.pop(ev['missionId'])
                    mid, choice = ev['missionId'], ev.get('choiceType')
                    chosen = ev.get('assetsChosen') or {}
                    req = m['req']
                    rows.append(dict(
                        pid=pid, run=run, version=version, scenario=scenario, planIndex=plan,
                        idx=idx, missionId=mid, elapsed=ev.get('elapsed'),
                        residual=int(mid in residual or mid.endswith('-R')),
                        choice=choice, took=int(choice in CARD), manual=int(choice == 'manual'),
                        early=ev.get('manualBeforeCardsLoaded'),
                        editedFrom=ev.get('editedFromStrategy'),
                        ncolours=sum(1 for c in COLOURS if req[c] > 0),
                        ndrones=sum(req.values()),
                        odd=int(bool(m['unneeded'])), unneeded=m['unneeded'],
                        aggr_odd=int(bool(m['aggr_unneeded'])),
                        chosen=chosen, cons=m['cons'], aggr=m['aggr'],
                        chosen_unneeded=sum(chosen.get(c, 0) for c in m['unneeded']),
                        edit_trail=edits.pop(mid, []),
                        fate=fate.get(mid, 'inflight')))
                    idx += 1
    df = pd.DataFrame(rows)
    _check_against_builder(df)
    return df


def _check_against_builder(df: pd.DataFrame) -> None:
    """Row-for-row agreement with the builder's decision table (same pairing rule)."""
    ref = B._quietly(B.load_decisions)
    a = df[['pid', 'run', 'idx', 'choice', 'odd', 'ncolours', 'ndrones']].reset_index(drop=True)
    b = ref[['pid', 'run', 'idx', 'choice', 'odd', 'ncolours', 'ndrones']].reset_index(drop=True)
    assert len(a) == len(b), (len(a), len(b))
    assert (a.values == b.values).all(), 'decision table disagrees with build_findings_synthesis'


def sessions() -> pd.DataFrame:
    """Per-session survey + behaviour table from the builder (trust_s, trust_t, took, ...)."""
    sess, _ = B._quietly(B.load_people)
    return pd.DataFrame(sess)


def session_events():
    """(pid, run, events) for every analysed session -- for counts the tables do not carry."""
    for pid, log in _files():
        for run, events in enumerate(log['sessions'], start=1):
            yield pid, run, events


def versions() -> dict:
    out = {}
    for pid, log in _files():
        for s in log['sessions']:
            for e in s:
                if e['type'] == 'session_start':
                    out.setdefault(pid, e.get('appVersion'))
    return out


def v112plus(pid_versions: dict) -> set:
    def ok(v):
        try:
            major, minor = v.replace('study-v', '').split('.')[:2]
            return (int(major), int(minor)) >= (1, 12)
        except Exception:
            return False
    return {p for p, v in pid_versions.items() if ok(v)}


def spearman_ci(x, y, n_boot=4000, seed=20261007):
    """Spearman rho, two-sided p, Fisher-z CI (Bonett & Wright SE) and a bootstrap percentile CI."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    n = len(x)
    r, p = stats.spearmanr(x, y)
    if n > 3 and abs(r) < 1:
        se = np.sqrt((1 + r * r / 2) / (n - 3))
        z = np.arctanh(r)
        lo, hi = np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)
    else:
        lo = hi = np.nan
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        if np.ptp(x[i]) == 0 or np.ptp(y[i]) == 0:
            continue
        boots.append(stats.spearmanr(x[i], y[i])[0])
    blo, bhi = np.percentile(boots, [2.5, 97.5])
    return dict(rho=float(r), p=float(p), n=int(n), lo=float(lo), hi=float(hi),
                blo=float(blo), bhi=float(bhi))


def fmt_rho(d):
    return ('rho = %+.3f, Fisher-z 95%% CI [%+.3f, %+.3f], bootstrap [%+.3f, %+.3f], p = %.3f, n = %d'
            % (d['rho'], d['lo'], d['hi'], d['blo'], d['bhi'], d['p'], d['n']))


def partial_spearman(x, y, covars: pd.DataFrame):
    """Spearman partial correlation: Pearson on rank-residuals after regressing ranks on covariates."""
    import statsmodels.api as sm
    rx, ry = stats.rankdata(x), stats.rankdata(y)
    X = sm.add_constant(covars.astype(float).values)
    ex = rx - X @ np.linalg.lstsq(X, rx, rcond=None)[0]
    ey = ry - X @ np.linalg.lstsq(X, ry, rcond=None)[0]
    r, _ = stats.pearsonr(ex, ey)
    n, k = len(x), X.shape[1] - 1
    t = r * np.sqrt((n - 2 - k) / (1 - r * r))
    p = 2 * stats.t.sf(abs(t), n - 2 - k)
    return float(r), float(p), n


def detectable_rho(n, power=.80, alpha=.05):
    """Smallest |rho| detectable two-sided at the given power (Fisher-z approximation)."""
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    return float(np.tanh((za + zb) / np.sqrt(n - 3)))
