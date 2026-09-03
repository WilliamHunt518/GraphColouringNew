#!/usr/bin/env python3
"""
Build the standalone aggregate report: docs/reports/two-tiers-two-scenarios.html

One command, no arguments, no network, no dependencies beyond the standard library:

    python scripts/build_agent_report.py

It re-reads every log under logs/, recomputes the cohort aggregates, and writes a single
self-contained HTML file you can open by double-clicking it -- offline, forever, no server. The
computed numbers are written alongside it as JSON so they can be checked or re-plotted elsewhere.

Pipeline:
    agent_scenario_stats.py      one row per completed session, straight from the event logs
    agent_scenario_aggregate.py  cohort x scenario x tier rollups, contrasts, attitude scales
    agent_report_template.html   the page; this script injects the data and escapes it to ASCII

Re-run it whenever a participant is added. Nothing in the output is hand-written.
"""
import json, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / 'scripts'))

from agent_scenario_stats import load_all                       # noqa: E402
from agent_scenario_aggregate import COHORTS, in_cohort, cell, \
    contrasts, order_effect, attitudes, SCEN                    # noqa: E402

TEMPLATE = BASE / 'scripts' / 'agent_report_template.html'
OUT_DIR = BASE / 'docs' / 'reports'
OUT_HTML = OUT_DIR / 'two-tiers-two-scenarios.html'
OUT_JSON = OUT_DIR / 'aggregate.json'

# Session-level lists that no figure reads. Dropping them keeps the embedded payload small enough
# that the page stays comfortable to open and to diff.
DROP_VALUES = ('planOverlap', 'score', 'penalty', 'tlx', 'failures', 'drags',
               'completion', 'meanMissionTime')


def build_aggregate():
    rows = load_all()
    out = {'cohorts': []}
    for c in COHORTS:
        sel = [r for r in rows if in_cohort(r, c)]
        if not sel:
            continue
        entry = dict({k: v for k, v in c.items() if k not in ('minrank', 'maxrank')},
                     overall=cell(sel))
        for s in SCEN:
            entry[s] = cell([r for r in sel if r['scenario'] == s])
        entry['dateRange'] = [min((r['wallClock'] or '')[:10] for r in sel),
                              max((r['wallClock'] or '')[:10] for r in sel)]
        entry['contrasts'] = contrasts(sel)
        entry['orderEffect'] = order_effect(sel)
        entry['attitudes'] = attitudes(sel)
        out['cohorts'].append(entry)
    return out, rows


def slim(agg):
    for c in agg['cohorts']:
        for bucket in ('overall', 'strategic', 'tactical'):
            for key in DROP_VALUES:
                s = c[bucket].get(key)
                if isinstance(s, dict):
                    s.pop('values', None)
    return agg


def ascii_only(src):
    """Escape every non-ASCII character, so the page renders correctly however it is served --
    off a disk with no charset header, out of a zip, or from the artifact host.

    Markup takes numeric HTML entities; the script block takes JS unicode escapes, since entities
    are not decoded inside <script>.
    """
    src = src.replace('─', '-')
    marker = '<script>\n'
    head, sep, tail = src.partition(marker)
    head = ''.join(c if ord(c) < 128 else '&#x%x;' % ord(c) for c in head)
    tail = ''.join(c if ord(c) < 128 else '\\u%04x' % ord(c) for c in tail)
    return head + sep + tail


def main():
    agg, rows = build_aggregate()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # The JSON sidecar keeps the raw per-session rows; the embedded copy does not need them.
    OUT_JSON.write_text(json.dumps({'cohorts': agg['cohorts'], 'sessions': rows}, indent=1),
                        encoding='utf-8')

    payload = json.dumps(slim(agg), separators=(',', ':'))   # ensure_ascii keeps it ASCII already
    payload = payload.replace('</', '<\\/')                  # never close the host <script> early

    html = ascii_only(TEMPLATE.read_text(encoding='utf-8')).replace('__DATA__', payload)
    if '__DATA__' in html or not payload:
        raise SystemExit('template placeholder or payload missing')
    if any(ord(ch) > 127 for ch in html):
        raise SystemExit('non-ASCII survived escaping')
    OUT_HTML.write_text(html, encoding='utf-8')

    people = len({r['pid'] for r in rows})
    battery = agg['cohorts'][0]['attitudes']['withBattery']
    print('%d sessions / %d participants (%d with the AI-attitude battery)' % (len(rows), people, battery))
    print('  %s  (%.0f KB)' % (OUT_HTML.relative_to(BASE), OUT_HTML.stat().st_size / 1024))
    print('  %s  (%.0f KB)' % (OUT_JSON.relative_to(BASE), OUT_JSON.stat().st_size / 1024))


if __name__ == '__main__':
    main()
