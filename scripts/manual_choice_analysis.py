"""What is an operator doing when they build the allocation themselves?

`choiceType == 'manual'` is the study's headline non-reliance signal, and the debriefs say it is at
least four different acts: pre-empting the assistant on a mission simple enough not to need it,
interpolating between the only two cards on offer, benchmarking the agent against yourself, and
editing a card as a first draft. This script tests the ones the logs can see.

    python scripts/manual_choice_analysis.py       # needs numpy/pandas/statsmodels

## The instrument that makes this possible

The strategic cards are deliberately not readable for the first 4.0-5.0 s (`CARD_REVEAL_MIN_MS` /
`CARD_REVEAL_SPAN_MS`), simulating an "Analysing..." pause. Manual entry is available immediately.
`strategic_choice` therefore logs **`manualBeforeCardsLoaded`** -- whether the operator committed to
building it themselves before the recommendation existed on screen.

A Manual choice made before the cards loaded is not a rejection of the advice: the advice had not
been given. Treating it as low reliance measures something that never happened. The delay is a
design feature and stays; it is also what makes the pre-emption observable.

## A trap this script is built to avoid

Manual is used far more on small, low-criticality missions. So any average taken over Manual
decisions -- "Manual commits fewer drones" -- is an average over a non-random slice of missions,
and says as much about which missions people build by hand as about what they do when they build
one. Every comparison here is therefore either matched on mission by construction
(`deltaVsConservative` compares against what that card would have committed FOR THAT SAME MISSION)
or broken out by mission size and criticality before anything is concluded. Done that way, the
headline "Manual preserves reserve" turns out to hold only for small missions and to reverse for
large ones.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parent.parent
PARTICIPANTS = ROOT / 'Results' / 'Participants'
EXCLUDE = {'P09'}

# A = lowest penalty rate (0.05/s), E = highest (0.4/s). Ordered so it can enter a model linearly.
CRITICALITY = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5}


def load() -> pd.DataFrame:
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
            # mission_completed lands long AFTER the choice that set the mission up, so it has to
            # be collected in its own pass -- reading it inline silently yields no outcomes at all.
            completed = {e['missionId']: e for e in events if e['type'] == 'mission_completed'}
            scenario, need, pending, idx = None, {}, {}, 0

            for ev in events:
                if ev['type'] == 'session_start':
                    scenario = ev.get('complexity')

                elif ev['type'] == 'mission_arrived':
                    total = {'Blue': 0, 'Red': 0, 'Green': 0}
                    for task in ev.get('tasks', []):
                        for colour, n in primary[str(task['type'])].items():
                            total[colour] += n
                    need[ev['missionId']] = total

                elif ev['type'] == 'strategic_modal_opened':
                    req = need.get(ev['missionId'])
                    cards = {c['name']: c for c in ev.get('strategiesPresented', [])}
                    if not req or len(cards) < 2:
                        continue
                    cons, aggr = cards['Conservative'], cards['Aggressive']
                    cons_total = sum(cons['trueAssets'].values())
                    aggr_total = sum(aggr['trueAssets'].values())
                    pending[ev['missionId']] = dict(
                        opened_at=ev['timestamp'],
                        cons_total=cons_total, aggr_total=aggr_total,
                        # Dominated: no cheaper in drones AND no faster. Nothing visible recommends it.
                        dominated=int(cons_total >= aggr_total and
                                      cons['displayedCompletionTime'] >= aggr['displayedCompletionTime']),
                        odd=int(any(cons['trueAssets'].get(c, 0) > 0 and req[c] == 0 for c in req)),
                        ncolours=sum(1 for c in req if req[c] > 0),
                        ndrones=sum(req.values()))

                elif ev['type'] == 'strategic_choice' and ev['missionId'] in pending:
                    m = pending.pop(ev['missionId'])
                    done = completed.get(ev['missionId'])
                    d_cons = ev.get('deltaVsConservative') or {}
                    d_aggr = ev.get('deltaVsAggressive') or {}
                    choice = ev.get('choiceType')
                    rows.append(dict(
                        pid=pid, run=run, scenario=scenario, idx=idx, choice=choice,
                        manual=int(choice == 'manual'),
                        category=ev.get('missionCategory'),
                        criticality=CRITICALITY.get(ev.get('missionCategory'), np.nan),
                        ncolours=m['ncolours'], ndrones=m['ndrones'],
                        cons_total=m['cons_total'], aggr_total=m['aggr_total'],
                        dominated=m['dominated'], odd=m['odd'],
                        committed=sum((ev.get('assetsChosen') or {}).values()),
                        d_cons=sum(d_cons.values()) if d_cons else np.nan,
                        d_aggr=sum(d_aggr.values()) if d_aggr else np.nan,
                        early=ev.get('manualBeforeCardsLoaded'),
                        secs=(ev['timestamp'] - m['opened_at']) / 1000.0,
                        outcome=done.get('outcome') if done else None,
                        reward=done.get('rewardEarned') if done else None,
                        max_reward=done.get('maxReward') if done else None))
                    idx += 1
    return pd.DataFrame(rows)


def gee(formula: str, data: pd.DataFrame, family=None):
    return smf.gee(formula, 'pid', data=data,
                   family=family or sm.families.Gaussian(),
                   cov_struct=sm.cov_struct.Exchangeable()).fit()


def rule(title: str) -> None:
    print('\n' + '=' * 78)
    print(title)
    print('=' * 78)


def main() -> None:
    df = load()
    manual = df[df.manual == 1]
    print('%d strategic decisions, %d Manual, %d participants (P09 excluded)'
          % (len(df), len(manual), df.pid.nunique()))

    rule('1 · HOW OFTEN DOES MANUAL PRE-EMPT THE RECOMMENDATION?')
    flag = manual.early.dropna()
    print('\nmanualBeforeCardsLoaded logged on %d of %d Manual choices.' % (len(flag), len(manual)))
    print('Committed to Manual BEFORE the cards finished loading: %d of %d = %.1f%%'
          % (flag.sum(), len(flag), 100 * flag.mean()))
    print('\nBy number of colours the mission needs:')
    for n in sorted(manual.ncolours.unique()):
        s = manual[manual.ncolours == n].early.dropna()
        if len(s) >= 5:
            print('  %d-colour  %5.1f%% pre-empted (n=%d)' % (n, 100 * s.mean(), len(s)))
    print('\nOn the simplest missions a MAJORITY of Manual choices are made before the operator has')
    print('seen the advice. Those are not rejections of a recommendation -- there was none yet.')

    rule('2 · IS MANUAL ACTUALLY FASTER?  (modal opening -> choice, seconds)')
    print('\n%-8s %-13s %6s %8s' % ('colours', 'route', 'n', 'median'))
    for n in sorted(df.ncolours.unique()):
        for route in ('manual', 'aggressive', 'conservative'):
            s = df[(df.ncolours == n) & (df.choice == route)].secs.dropna()
            if len(s) >= 5:
                print('%-8d %-13s %6d %8.1f' % (n, route, len(s), s.median()))
    m = gee('secs ~ manual + ncolours + ndrones + C(scenario)', df.dropna(subset=['secs']))
    print('\nAdjusted for mission composition: Manual takes %+.1f s longer (p=%.3f).'
          % (m.params['manual'], m.pvalues['manual']))
    print('\nNo -- Manual is SLOWER, even on one-colour missions where the cards cost a 4-5 s wait.')
    print('Section 1 is about when the DECISION was made, not how long the allocation took.')
    print('Participants who call Manual the faster route (P29) are describing the former.')

    rule('3 · WHAT DOES IT COST ON THAT MISSION?')
    few = df[(df.ncolours < 3) & df.outcome.notna()]
    share = pd.crosstab(few.manual, few.outcome, normalize='index') * 100
    share.index = ['took a card', 'manual']
    print('\nOutcome share (%), few-colour missions only:')
    print(share.round(1).to_string())
    print('\nReward captured (rewardEarned / maxReward):')
    for label, v in (('took a card', 0), ('manual', 1)):
        s = few[(few.manual == v) & few.max_reward.gt(0)]
        print('  %-12s %.1f%% (n=%d)' % (label, 100 * (s.reward / s.max_reward).mean(), len(s)))
    print('\nNothing. Manual does at least as well on the mission it was used for.')

    rule('4 · WHAT DOES MANUAL COMMIT, vs THE CARDS IT DECLINED?')
    print('\nSELECTION — Manual is used more on small, low-criticality missions:')
    sel = df.groupby('category').agg(n=('manual', 'size'), manual_pct=('manual', 'mean'),
                                     colours=('ncolours', 'mean'), drones=('ndrones', 'mean'))
    sel['manual_pct'] = (100 * sel['manual_pct']).round(1)
    print(sel.round(2).to_string())

    print('\nDELTA vs Conservative (matched on mission), by criticality:')
    for cat in ['A', 'B', 'C', 'D', 'E']:
        s = manual[manual.category == cat].d_cons.dropna()
        if len(s) >= 5:
            print('  %s  %+.2f drones (n=%d)' % (cat, s.mean(), len(s)))

    sized = manual.dropna(subset=['d_cons']).copy()
    sized['band'] = pd.qcut(sized.ndrones, 3, labels=['small', 'mid', 'large'])
    print('\nDELTA vs Conservative, by mission size:')
    for band, s in sized.groupby('band', observed=True):
        print('  %-6s %+.2f drones (n=%3d, mean need %.1f)'
              % (band, s.d_cons.mean(), len(s), s.ndrones.mean()))
    m = gee('d_cons ~ ncolours + ndrones + criticality + C(scenario)', sized)
    print('\n  size b=%+.3f p=%.4f | colours b=%+.3f p=%.3f | criticality b=%+.3f p=%.3f'
          % (m.params['ndrones'], m.pvalues['ndrones'], m.params['ncolours'],
             m.pvalues['ncolours'], m.params['criticality'], m.pvalues['criticality']))
    print('\nTHE SAVING REVERSES. Operators trim on small missions and ADD on large ones. Mission')
    print('size drives it; criticality has no independent effect once size is in the model (the two')
    print('are correlated — category E needs ~15 drones, category A ~5). So "Manual preserves')
    print('reserve" is true of small missions and false of big ones.')

    rule('5 · IS MANUAL AN INTERPOLATION BETWEEN THE TWO CARDS?')
    print('\nP17: "I wanted it to be somewhere between those two levels" (also P22, P28).')
    both = manual.dropna(subset=['cons_total', 'aggr_total']).copy()
    lo = both[['cons_total', 'aggr_total']].min(axis=1)
    hi = both[['cons_total', 'aggr_total']].max(axis=1)
    both['position'] = np.where(both.committed < lo, 'below both',
                                np.where(both.committed > hi, 'above both', 'between'))
    counts = both['position'].value_counts()
    pct = both['position'].value_counts(normalize=True) * 100
    print('\nWhere the manual allocation sits (total drones), n=%d:' % len(both))
    for k in ['between', 'below both', 'above both']:
        if k in counts.index:
            print('  %-11s %5.1f%%  (n=%d)' % (k, pct[k], counts[k]))
    both['band'] = pd.qcut(both.ndrones, 3, labels=['small', 'mid', 'large'])
    print('\nBy mission size (%% of that band):')
    print((pd.crosstab(both['band'], both['position'], normalize='index') * 100).round(1).to_string())
    print('\nMean drones committed:')
    print(both.groupby('band', observed=True)[['cons_total', 'committed', 'aggr_total']]
          .mean().round(1).to_string())
    print('\nBoth stories are true, of different missions: on large missions Manual interpolates')
    print('between the cards; on small ones it undercuts BOTH.')

    rule('6 · ON SMALL MISSIONS THE "CONSERVATIVE" CARD IS OFTEN DOMINATED')
    cards = df.dropna(subset=['cons_total', 'aggr_total']).copy()
    cards['bigger'] = (cards.cons_total > cards.aggr_total).astype(int)
    cards['band'] = pd.qcut(cards.ndrones, 3, labels=['small', 'mid', 'large'])
    print('\nConservative commits MORE drones than Aggressive in %.1f%% of card pairs (n=%d):'
          % (100 * cards.bigger.mean(), len(cards)))
    for band, s in cards.groupby('band', observed=True):
        print('  %-6s %5.1f%%   (mean Conservative %.1f vs Aggressive %.1f, n=%d)'
              % (band, 100 * s.bigger.mean(), s.cons_total.mean(), s.aggr_total.mean(), len(s)))
    print('\nConservative is also the slower card by design, so where it is not smaller it is')
    print('dominated on every axis the operator can see: %.1f%% of decisions.'
          % (100 * cards.dominated.mean()))
    print('\nChoice share (%) by whether Conservative was dominated:')
    print((pd.crosstab(cards.dominated, cards.choice, normalize='index') * 100).round(1).to_string())
    print('\nBUT — like the stray-colour flag, it adds nothing once mission composition is in the')
    print('model. Both are symptoms of small missions, and mission size is the real variable:')
    m = gee('took_card ~ dominated + odd + ncolours + ndrones + C(scenario) + C(run) + idx',
            cards.assign(took_card=(cards.choice != 'manual').astype(int)),
            family=sm.families.Binomial())
    for term in ('dominated', 'odd', 'ncolours', 'ndrones'):
        print('  %-11s b=%+.3f  p=%.3f' % (term, m.params[term], m.pvalues[term]))


if __name__ == '__main__':
    main()
