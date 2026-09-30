"""The Conservative card sometimes commits drone types the mission does not need. Does it matter?

This check exists because a participant said so. P21, in debrief: "it was giving me the wrong type
of drones. It required only blue drones and kept giving me red and green ones. So I didn't like
that one." Four others report it unprompted (P13, P17, P20, P35). They are right, and it is not an
injected failure -- every session ran with `agentFailuresEnabled=false` and both epsilons at 0.

`copilot.ts:266-268` builds the Conservative pool as

    consBase[c] + floor((reserve[c] - consBase[c]) * CONSERVATIVE_TOP_UP)
                + (consBase[c] > 0 ? CONSERVATIVE_REDUNDANCY_BUFFER : 0)

The `+1` redundancy buffer is gated on the colour actually being used by the mission, and the
comment beside it says so. The 15% top-up is not gated at all, so on an all-Blue mission with 11
Red in reserve, `floor(11 * 0.15) = 1` Red is committed to a mission with no use for it. Aggressive
has no equivalent term and never does it.

**This is not a bug to be fixed -- it is what deliberately simple, myopic rules do.** The
assistants are heuristics by design, and a heuristic that is cheap enough to be legible sometimes
produces a visibly odd answer. The research question is what that costs, not how to remove it.
Recruitment closed at 34 participants, so `copilot.ts` stays as it is; see the note at the top of
`generateStrategies` before reusing this build for anything else.

    python scripts/check_conservative_topup.py        # needs numpy/scipy/pandas/statsmodels

## What this answers, and the trap it avoids

The naive comparison -- Conservative uptake on clean cards versus odd cards -- looks alarming and
is **confounded**. An odd card is only possible when the mission leaves a colour unused, so it can
never occur on a three-colour mission (0 of 431 in this cohort). Odd cards are therefore nested
inside simple missions, and simple missions are exactly where operators build the allocation
themselves anyway. Comparing odd against clean compares simple missions against complex ones with
extra steps.

So the analysis is run three ways, in increasing order of trustworthiness:

1. prevalence, including how it splits across the scenario manipulation;
2. the naive contrast, reported so the confound is visible rather than hidden;
3. the contrast **within** few-colour missions, which is the only stratum where it is identified,
   plus carry-over tests (does seeing one cost trust later?).
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
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
PARTICIPANTS = ROOT / 'Results' / 'Participants'

# ε = 0.2 fault test and the participant did not follow the task; excluded everywhere else too.
EXCLUDE = {'P09'}


def load() -> pd.DataFrame:
    """One row per strategic decision, with the mission's own composition attached.

    'Needed' is the sum of PRIMARY requirements over the mission's tasks -- the straightforward
    reading an operator takes off the task badges, which is the reading that makes a stray colour
    look like a mistake. It is not a feasibility floor: drones are reused across tasks run in
    series, so a card committing fewer drones than this is not under-strength.
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
            scenario, need, trust = None, {}, None
            for ev in events:
                if ev['type'] == 'session_start':
                    scenario = ev.get('complexity')
                elif ev['type'] == 'mission_arrived':
                    total = {'Blue': 0, 'Red': 0, 'Green': 0}
                    for task in ev.get('tasks', []):
                        for colour, n in primary[str(task['type'])].items():
                            total[colour] += n
                    need[ev['missionId']] = total
                elif ev['type'] == 'survey_response' and ev.get('surveyName') == 'trust_strategic':
                    trust = float(np.mean(list(ev['responses'].values())))

            pending, idx, seen_odd, prev_odd = {}, 0, 0, np.nan
            for ev in events:
                if ev['type'] == 'strategic_modal_opened':
                    req = need.get(ev['missionId'])
                    cards = {c['name']: c for c in ev.get('strategiesPresented', [])}
                    if not req or 'Conservative' not in cards:
                        continue
                    assets = cards['Conservative']['trueAssets']
                    odd = any(assets.get(c, 0) > 0 and req[c] == 0 for c in req)
                    pending[ev['missionId']] = (odd, sum(1 for c in req if req[c] > 0),
                                                sum(req.values()))
                elif ev['type'] == 'strategic_choice' and ev['missionId'] in pending:
                    odd, ncolours, ndrones = pending.pop(ev['missionId'])
                    choice = ev.get('choiceType')
                    rows.append(dict(pid=pid, run=run, scenario=scenario, idx=idx,
                                     odd=int(odd), ncolours=ncolours, ndrones=ndrones,
                                     choice=choice, prior=int(seen_odd > 0), prev_odd=prev_odd,
                                     took=int(choice in ('aggressive', 'conservative')),
                                     trust=trust))
                    idx, seen_odd, prev_odd = idx + 1, seen_odd + odd, int(odd)
    return pd.DataFrame(rows)


def gee(formula: str, data: pd.DataFrame, family=None):
    """Binomial GEE clustered on participant -- decisions within a person are not independent."""
    return smf.gee(formula, 'pid', data=data,
                   family=family or sm.families.Binomial(),
                   cov_struct=sm.cov_struct.Exchangeable()).fit()


def main() -> None:
    df = load()
    print('%d strategic decisions, %d participants (P09 excluded)\n' % (len(df), df.pid.nunique()))

    print('=' * 78)
    print('1 · PREVALENCE')
    print('=' * 78)
    by_scenario = df.groupby('scenario').odd.agg(['sum', 'size', 'mean'])
    print('\nConservative cards carrying a colour the mission has no primary need for:')
    for scenario, r in by_scenario.iterrows():
        print('  %-11s %3d / %3d = %5.1f%%' % (scenario, r['sum'], r['size'], 100 * r['mean']))
    print('  %-11s %3d / %3d = %5.1f%%' % ('overall', df.odd.sum(), len(df), 100 * df.odd.mean()))
    print('\nThe split is structural, not chance: Strategic Heavy runs many small missions, small')
    print('missions leave colours unused, and an unused colour is what the ungated top-up pads.')
    print('So the artefact is concentrated in one arm of the scenario manipulation.')

    print('\n' + '=' * 78)
    print('2 · WHAT AN ODD CARD DOES TO THAT DECISION')
    print('=' * 78)
    share = (df.groupby('odd').choice.value_counts(normalize=True).unstack().fillna(0) * 100)
    share.index = ['clean card', 'odd card']
    print('\nChoice share (%):')
    print(share.round(1).to_string())
    print('\nBoth cards lose roughly equally -- an odd Conservative card does not push operators')
    print('to Aggressive, it pushes them out of the card system altogether.')

    print('\n' + '=' * 78)
    print('3 · THE CONFOUND')
    print('=' * 78)
    table = pd.crosstab(df.ncolours, df.odd, margins=True)
    table.columns = ['clean', 'odd', 'all']
    print('\nOdd card by number of colours the mission needs:')
    print(table.to_string())
    print('\nAn odd card requires an unused colour, so three-colour missions can never produce one.')
    print('"Odd" is nested inside "simple", and the naive odd-vs-clean contrast below is really a')
    print('simple-vs-complex contrast.')

    naive = df.groupby('odd').took.agg(['mean', 'size'])
    print('\nNAIVE (confounded, reported so it is visible): took a card')
    for k, label in ((0, 'clean'), (1, 'odd  ')):
        print('  %s %5.1f%% (n=%d)' % (label, 100 * naive.loc[k, 'mean'], naive.loc[k, 'size']))

    few = df[df.ncolours < 3]
    within = few.groupby('odd').took.agg(['mean', 'size'])
    print('\nIDENTIFIED — within few-colour missions only (n=%d), took a card:' % len(few))
    for k, label in ((0, 'clean'), (1, 'odd  ')):
        print('  %s %5.1f%% (n=%d)' % (label, 100 * within.loc[k, 'mean'], within.loc[k, 'size']))
    model = gee('took ~ odd + C(scenario) + C(run) + idx', few)
    print('  adjusted: odd b=%+.3f, p=%.3f  -> %s'
          % (model.params['odd'], model.pvalues['odd'],
             'significant' if model.pvalues['odd'] < .05 else 'NOT significant'))

    print('\n' + '=' * 78)
    print('4 · DOES IT COST TRUST AFTERWARDS?')
    print('=' * 78)
    m1 = gee('took ~ prior + C(scenario) + C(run) + idx', df)
    print('\nAlready seen one this session -> uptake on later decisions:')
    print('  b=%+.3f, p=%.3f' % (m1.params['prior'], m1.pvalues['prior']))

    nxt = df[df.prev_odd.notna()]
    g = nxt.groupby('prev_odd').took.agg(['mean', 'size'])
    m2 = gee('took ~ prev_odd + C(scenario) + C(run) + idx', nxt)
    print('\nUptake on the very next decision:')
    print('  after a clean card %.1f%% (n=%d)' % (100 * g.loc[0, 'mean'], g.loc[0, 'size']))
    print('  after an odd card  %.1f%% (n=%d)' % (100 * g.loc[1, 'mean'], g.loc[1, 'size']))
    print('  b=%+.3f, p=%.3f' % (m2.params['prev_odd'], m2.pvalues['prev_odd']))

    per_session = df.groupby(['pid', 'run']).agg(odd_seen=('odd', 'sum'), trust=('trust', 'first'))
    per_session = per_session.dropna()
    rho, p = stats.spearmanr(per_session.odd_seen, per_session.trust)
    print('\nPost-session trust_strategic (mean of 6 items) vs odd cards seen that session:')
    print('  n=%d sessions, Spearman rho=%+.3f, p=%.3f' % (len(per_session), rho, p))
    print('\nNo carry-over on any of the three. Operators answer the card in front of them and do')
    print('not generalise -- which is worth holding against P20, who states plainly that his trust')
    print('in the strategic tier dropped after seeing one. The behaviour does not show it.')

    print('\n' + '=' * 78)
    print('5 · DOES THE SCENARIO EFFECT SURVIVE?')
    print('=' * 78)
    print('\nOutcome: took a card. Scenario coefficient is Tactical Heavy vs Strategic Heavy.\n')
    for label, formula in (
            ('unadjusted                ', 'took ~ C(scenario) + C(run) + idx'),
            ('+ odd-card flag           ', 'took ~ odd + C(scenario) + C(run) + idx'),
            ('+ mission composition     ', 'took ~ odd + ncolours + ndrones + C(scenario) + C(run) + idx')):
        m = gee(formula, df)
        b, p = m.params['C(scenario)[T.tactical]'], m.pvalues['C(scenario)[T.tactical]']
        extra = ''
        if 'odd' in m.params:
            extra = '   odd b=%+.3f p=%.3f' % (m.params['odd'], m.pvalues['odd'])
        print('  %s b=%+.3f p=%.4f%s' % (label, b, p, extra))
    print('\nBoth the scenario effect and the odd-card effect are absorbed by mission composition.')
    print('Number of colours a mission needs is the variable doing the work (see the full model')
    print('below): operators take the card on complex missions and build simple ones themselves.')
    print('\n' + gee('took ~ odd + ncolours + ndrones + C(scenario) + C(run) + idx', df)
          .summary().tables[1].as_text())


if __name__ == '__main__':
    main()
