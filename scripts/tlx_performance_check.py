#!/usr/bin/env python3
"""
Checks whether NASA-TLX's `performance` item was read correctly, by correlating it against each
session's actual completion rate.

`performance` is the one TLX item that runs the opposite way to the other five: the question is
phrased positively ("How successful were you...") but the slider's higher-numbered end is Failure,
not Perfect (see docs/STUDY_BUILD.md § 19). A participant who anchors on the positive question
wording and drags right to mean "very successful" ends up backwards from what the scale records.

If read correctly, a higher completion rate should pull `performance` DOWN (toward 0 = Perfect):
correlation should be negative. A positive correlation is the signature of participants dragging it
the intuitive-but-wrong way.

Usage:  python scripts/tlx_performance_check.py
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(BASE / 'scripts'))
from agent_scenario_stats import events   # noqa: E402

# Sessions where the researcher verbally corrected the participant before they answered —
# trust these regardless of which side of the v1.12 UI fix they fall on.
VERBALLY_CORRECTED = {'Eike', 'Reuben'}


def pearson(pairs):
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if n < 3:
        return None, n
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx <= 0 or syy <= 0:
        return None, n
    return sxy / (sxx * syy) ** 0.5, n


def load_rows():
    rows = []
    for f in sorted(Path(BASE / 'logs').glob('**/*.json')):
        p = str(f).replace(chr(92), '/')
        if 'sar_snapshot' in p or '/auto/' in p or p.endswith('summary.json') or p.endswith('faultTest.json'):
            continue
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict) or 'sessions' not in d:
            continue
        pid = d.get('participantId')
        for i, sess in enumerate(d['sessions']):
            evs = events(sess)
            tlx = next((e for e in evs if e.get('type') == 'survey_response' and e.get('surveyName') == 'nasa_tlx'), None)
            ended = next((e for e in evs if e.get('type') == 'session_ended'), None)
            if not tlx or not ended:
                continue
            resp = tlx.get('responses') or {}
            perf = resp.get('performance')
            outcomes = ended.get('taskOutcomes') or {}
            completed, failed = outcomes.get('completed'), outcomes.get('failed')
            rate = (completed / (completed + failed)) if (completed is not None and failed is not None and completed + failed > 0) else None
            rows.append(dict(pid=pid, session=i + 1, performance=perf, completionRate=rate,
                              corrected=pid in VERBALLY_CORRECTED))
    return rows


def main():
    rows = load_rows()
    corrected = [r for r in rows if r['corrected']]
    uncorrected = [r for r in rows if not r['corrected']]

    r_all, n_all = pearson([(r['completionRate'], r['performance']) for r in rows])
    r_unc, n_unc = pearson([(r['completionRate'], r['performance']) for r in uncorrected])
    r_cor, n_cor = pearson([(r['completionRate'], r['performance']) for r in corrected])

    print('performance vs completionRate (0=Perfect..20=Failure; correct reading => negative r)')
    print(f'  all sessions:                r={r_all}  n={n_all}')
    print(f'  never verbally corrected:    r={r_unc}  n={n_unc}')
    print(f'  verbally corrected (v1.11):  r={r_cor}  n={n_cor}')
    print()
    for r in rows:
        flag = ' <- corrected' if r['corrected'] else ''
        print(f"  {r['pid']:10s} s{r['session']}  performance={r['performance']}  "
              f"completionRate={r['completionRate'] if r['completionRate'] is None else round(r['completionRate'], 2)}{flag}")


if __name__ == '__main__':
    main()
