#!/usr/bin/env python3
"""Pass 5: how typical is P36? (the researcher's note on q-practitioner#own-play: "a clear way of saying he's normal
in X, Y, Z, but different in this way").

    python scripts/register/pass2/typical.py      # writes docs/analysis/register/pass2/typical.json

One value per person (33, P09 excluded) for every habit the findings measure, their score, their trust ratings
and the pre-study questionnaire, then where P36 falls in each: percentile rank among the 33 (ties share the
middle rank) and a band. Typical = the middle half (25th-75th percentile); "leans high / low" = the next 15
points either side; "unusual" = beyond the 10th / 90th. Habits come from handover.person_table (the same numbers
as the size and speed findings), the queue choice from queue_order.decisions(), trust from the per-session survey
means, and the questionnaire from build_findings_synthesis.load_people. Nothing is tested: with one person, the
point is only to place them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import handover as HO  # noqa: E402
import queue_order as QO  # noqa: E402

BASE = Path(__file__).resolve().parents[3]
OUT = BASE / 'docs' / 'analysis' / 'register' / 'pass2' / 'typical.json'
WHO = 'P36'
EXP = ['None', 'A little', 'Moderate', 'Extensive']

# key, label, group, format (pct / pp / s / n / z / scale:<lo>-<hi> / exp = None, A little, Moderate, Extensive as 0-3)
ROWS = [
    ('took', 'Strategy cards taken', 'How they played', 'pct'),
    ('sGap', 'Card uptake: three-type minus one-type missions', 'How they played', 'pp'),
    ('preempt', 'Decided before the cards loaded', 'How they played', 'pct'),
    ('spare', 'Hand builds: drones above the Conservative card', 'How they played', 'n'),
    ('stratSecs', 'Seconds per strategic decision (median)', 'How they played', 's'),
    ('suggest', 'Plans with Suggest pressed', 'How they played', 'pct'),
    ('tGap', 'Suggest: big minus small plans', 'How they played', 'pp'),
    ('kept', 'Suggest plans kept unedited', 'How they played', 'pct'),
    ('tacSecs', 'Seconds per tactical plan (median)', 'How they played', 's'),
    ('oldest', 'Opened the oldest waiting mission', 'How they played', 'pct'),
    ('zgame', 'Score within game (SD units)', 'How it went', 'z'),
    ('trustS', 'Trust in the Strategic Assistant', 'How it went', 'scale:1-7'),
    ('trustT', 'Trust in the Tactical Assistant', 'How it went', 'scale:1-7'),
    ('aias', 'Attitude to AI (AIAS-4)', 'Before the study', 'scale:1-10'),
    ('verification', 'Verification propensity', 'Before the study', 'scale:1-7'),
    ('delegation', 'Keeps authority with the human (delegation scale)', 'Before the study', 'scale:1-7'),
    ('command_experience', 'Command experience (emergency, dispatch, military)', 'Before the study', 'exp'),
    ('drone_experience', 'Experience operating drones', 'Before the study', 'exp'),
    ('autonomy_experience', 'Experience of automation or AI assistants', 'Before the study', 'exp'),
    ('age', 'Age', 'Before the study', 'n'),
]


def band(p):
    if p < 10 or p > 90:
        return 'unusual'
    if p < 25 or p > 75:
        return 'leans'
    return 'typical'


def main():
    import build_findings_synthesis as b
    import wD_common as WD
    S, T, P, _who = HO.load()
    PT = HO.person_table(S, T, P)
    man = S[S.took == 0]
    PT['spare'] = (man.committed - man.cons_total).groupby(man.pid).mean()
    D, _ = QO.decisions()
    PT['oldest'] = D.groupby('pid').oldest.mean()
    WS = HO.quiet(WD.build)[0]
    PT['trustS'] = WS.groupby('pid').trust_s.mean()
    PT['trustT'] = WS.groupby('pid').trust_t.mean()
    _sess, people = HO.quiet(b.load_people)
    for k in ('aias', 'verification', 'delegation'):
        PT[k] = pd.Series({p: pd.to_numeric(v.get(k), errors='coerce') for p, v in people.items()})
    for k in ('age', 'command_experience', 'drone_experience', 'autonomy_experience'):
        PT[k] = pd.Series({p: EXP.index(x) if x in EXP else pd.to_numeric(x, errors='coerce')
                           for p, v in people.items() for x in [(v.get('dem') or {}).get(k)]})
    PT = PT[PT.index.isin(S.pid.unique())]
    assert WHO in PT.index
    rows = []
    for key, label, group, fmt in ROWS:
        v = PT[key].dropna()
        me = PT.at[WHO, key]
        if pd.isna(me):
            continue
        below, equal = (v < me).sum(), (v == me).sum()
        pr = 100 * (below + 0.5 * equal) / len(v)               # percentile rank, ties sharing the middle
        rows.append(dict(key=key, label=label, group=group, fmt=fmt, me=HO.r(me), n=int(len(v)),
                         median=HO.r(v.median()), q1=HO.r(v.quantile(.25)), q3=HO.r(v.quantile(.75)),
                         pctRank=HO.r(pr, 1), band=band(pr), side='high' if pr > 50 else 'low',
                         people=[[p, HO.r(x)] for p, x in v.items()]))
        print('%-50s P36 %8.3f  median %8.3f  IQR [%.3f, %.3f]  rank %5.1f  %s' % (
            label, me, v.median(), v.quantile(.25), v.quantile(.75), pr, band(pr)))
    out = dict(who=WHO, n=int(len(PT)), rows=rows,
               typical=[x['key'] for x in rows if x['band'] == 'typical'],
               leans=[x['key'] for x in rows if x['band'] == 'leans'],
               unusual=[x['key'] for x in rows if x['band'] == 'unusual'])
    OUT.write_text(json.dumps(HO.clean(out), indent=1), encoding='utf-8')
    print('wrote', OUT.relative_to(BASE))


if __name__ == '__main__':
    main()
