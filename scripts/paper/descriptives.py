#!/usr/bin/env python3
"""Descriptive overview tables for the paper (by scenario, and by game).

    C:/Users/Work/anaconda3/python.exe scripts/paper/descriptives.py <outDir>

Writes <outDir>/tab_descriptives.tex (one row per measure, Strategic Heavy vs Tactical Heavy, mean (SD) over the 33
sessions of each, with a paired Wilcoxon test since every person played one session of each), and
<outDir>/tab_games.tex (the same measures by the four fixed games). Uses the analysis loaders of the review register
(scripts/register/pass2/handover.py) so every behavioural measure is defined exactly as in the findings; NASA-TLX and
trust come from the raw survey_response events. P09 is excluded, as everywhere.
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts' / 'register' / 'pass2'))


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def raw_sessions() -> pd.DataFrame:
    """Per participant-file session: missions arrived (non-residual), tasks completed, failures, abandonments, TLX,
    trust. pid = file stem (some files carry an anonymised participantId)."""
    rows = []
    for f in sorted(glob.glob(str(BASE / 'Results' / 'Participants' / 'P*.json'))):
        pid = Path(f).stem
        if pid == 'P09':
            continue
        d = json.loads(Path(f).read_text(encoding='utf-8'))
        for s in d['sessions']:
            ev = s.get('events', s) if isinstance(s, dict) else s
            st = next(e for e in ev if e.get('type') == 'session_start')
            r = dict(pid=pid, run=st['sessionNumber'])
            r['missions'] = sum(1 for e in ev if e.get('type') == 'mission_arrived' and not e.get('isResidual'))
            r['tasksDone'] = sum(1 for e in ev if e.get('type') == 'task_completed')
            r['droneFailures'] = sum(1 for e in ev if e.get('type') == 'drone_failure')
            r['abandoned'] = sum(1 for e in ev if e.get('type') == 'mission_abandoned')
            for e in ev:
                if e.get('type') != 'survey_response':
                    continue
                R = e.get('responses') or {}
                if e.get('surveyName') == 'nasa_tlx':
                    # Performance runs Perfect (0) -> Failure (20) like the other five, so the raw mean is the usual
                    # unweighted ("raw") TLX: higher = more workload.
                    vals = [R[k] for k in ('mental_demand', 'physical_demand', 'temporal_demand', 'performance',
                                           'effort', 'frustration') if isinstance(R.get(k), (int, float))]
                    r['tlx'] = np.mean(vals) if vals else np.nan
                    for k in ('mental_demand', 'temporal_demand', 'performance', 'effort', 'frustration'):
                        r['tlx_' + k] = R.get(k, np.nan)
                elif e.get('surveyName') in ('trust_strategic', 'trust_tactical'):
                    vals = [v for v in R.values() if isinstance(v, (int, float))]
                    r['trust_' + e['surveyName'].split('_')[1][:5]] = np.mean(vals) if vals else np.nan
            rows.append(r)
    return pd.DataFrame(rows)


MEASURES = [
    # key, label, format, scale
    ('missions', 'Missions arrived (non-residual)', '{:.1f}', 1),
    ('n_dec', 'Strategic decisions made', '{:.1f}', 1),
    ('n_tac', 'Tactical plans confirmed', '{:.1f}', 1),
    ('tasksDone', 'Tasks completed', '{:.1f}', 1),
    ('pointsRescaled', 'Completion points$^a$', '{:.0f}', 1),
    ('penalty', 'Time penalty (points)', '{:.0f}', 1),
    ('score_rescaled', 'Score (points $-$ penalty)$^a$', '{:.0f}', 1),
    ('uptake', 'Strategy card chosen (\\% of decisions)', '{:.0f}', 100),
    ('early_rate', 'Built by hand before cards loaded (\\%)', '{:.0f}', 100),
    ('edited_rate', 'Strategy card edited, then deployed (\\%)', '{:.0f}', 100),
    ('tac_consult', 'Tactical suggestion requested (\\% of plans)', '{:.0f}', 100),
    ('tac_unmod', 'Suggested plan kept unmodified (\\% of plans)', '{:.0f}', 100),
    ('droneFailures', 'Drone failures', '{:.1f}', 1),
    ('abandoned', 'Missions abandoned', '{:.1f}', 1),
    ('tlx', 'NASA-TLX, raw mean (0--20)', '{:.1f}', 1),
    ('tlx_mental_demand', '\\quad Mental demand', '{:.1f}', 1),
    ('tlx_temporal_demand', '\\quad Temporal demand', '{:.1f}', 1),
    ('tlx_performance', '\\quad Performance (0 = perfect)', '{:.1f}', 1),
    ('tlx_effort', '\\quad Effort', '{:.1f}', 1),
    ('tlx_frustration', '\\quad Frustration', '{:.1f}', 1),
    ('trust_strat', 'Trust, Strategic Assistant (1--7)', '{:.2f}', 1),
    ('trust_tacti', 'Trust, Tactical Assistant (1--7)', '{:.2f}', 1),
]


def pfmt(p):
    if p is None or not np.isfinite(p):
        return '--'
    return '$<$.001' if p < .001 else ('%.3f' % p).lstrip('0')


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    import handover as H
    S, T, P, who = quiet(H.load)
    P = P.copy()
    P['pointsRescaled'] = P.pointsRecon / P.taskWeightScale      # P01/P02 ran at half task weights
    R = raw_sessions()
    D = P.merge(R, on=['pid', 'run'], how='left', validate='one_to_one')
    assert D.missions.notna().all(), 'raw/loader session mismatch'
    D['scen'] = D.scenario.map({'strategic': 'SH', 'tactical': 'TH'})
    lines = []
    for key, lab, fmt, sc in MEASURES:
        w = D.pivot_table(index='pid', columns='scen', values=key, aggfunc='first') * sc
        a, b = w.get('SH'), w.get('TH')
        ok = a.notna() & b.notna()
        p = stats.wilcoxon(a[ok], b[ok]).pvalue if ok.sum() > 5 and (a[ok] != b[ok]).any() else np.nan
        cell = lambda x: '%s (%s)' % (fmt.format(x.mean()), fmt.format(x.std()))
        lines.append('%s & %s & %s & %s \\\\' % (lab, cell(a.dropna()), cell(b.dropna()), pfmt(p)))
    tab = ['\\begin{table}[htbp]', '\\centering', '\\small',
           '\\caption{Descriptive overview by scenario: mean (SD) over the 33 sessions of each scenario. Every participant '
           'played one session of each, so $p$ is a paired Wilcoxon signed-rank test (33 pairs; fewer where a measure is '
           'undefined, e.g.\\ no manual decisions). Behavioural measures use the definitions of Section~\\ref{sec:measures}. '
           '$^a$P01 and P02 ran at half the later task weights; their points are doubled here.}',
           '\\label{tab:descriptives}', '\\begin{tabular}{lccr}', '\\toprule',
           '\\textbf{Measure (per session)} & \\textbf{Strategic Heavy} & \\textbf{Tactical Heavy} & $p$ \\\\', '\\midrule',
           *lines, '\\bottomrule', '\\end{tabular}', '\\end{table}']
    (out / 'tab_descriptives.tex').write_text('\n'.join(tab) + '\n', encoding='utf-8')

    # by game
    G = ['strategic|1', 'strategic|2', 'tactical|1', 'tactical|2']
    GL = {'strategic|1': 'SH1', 'strategic|2': 'SH2', 'tactical|1': 'TH1', 'tactical|2': 'TH2'}
    glines = []
    for key, lab, fmt, sc in MEASURES:
        cells = []
        for g in G:
            x = D.loc[D.game == g, key].dropna() * sc
            cells.append('%s (%s)' % (fmt.format(x.mean()), fmt.format(x.std())) if len(x) else '--')
        glines.append('%s & %s \\\\' % (lab, ' & '.join(cells)))
    n = D.groupby('game').pid.nunique()
    tabg = ['\\begin{table}[htbp]', '\\centering', '\\footnotesize',
            '\\caption{The same measures by the four fixed games (mean (SD) over sessions). SH = Strategic Heavy, TH = '
            'Tactical Heavy; the number is the mission stream (plan index), not the session order. Sessions per game: %s.}'
            % ', '.join('%s %d' % (GL[g], n[g]) for g in G),
            '\\label{tab:games}', '\\begin{tabular}{lcccc}', '\\toprule',
            '\\textbf{Measure} & ' + ' & '.join('\\textbf{%s}' % GL[g] for g in G) + ' \\\\', '\\midrule',
            *glines, '\\bottomrule', '\\end{tabular}', '\\end{table}']
    (out / 'tab_games.tex').write_text('\n'.join(tabg) + '\n', encoding='utf-8')
    D.to_csv(out / 'descriptives_sessions.csv', index=False)
    print('\n'.join(lines))
    print('wrote', out / 'tab_descriptives.tex', 'and tab_games.tex')


if __name__ == '__main__':
    main()
