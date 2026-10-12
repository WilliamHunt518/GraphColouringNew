#!/usr/bin/env python3
"""Assemble docs/analysis/register/findings.yaml from the per-area fragments written between passes.

    python scripts/register/assemble_findings.py            # write findings.yaml, report coverage
    python scripts/register/assemble_findings.py --check    # report only

Inputs: docs/analysis/register/pass2/<area>.findings.yaml (one per analysis area, each with `findings:` and
`retire:`). Areas are placed in AREA_ORDER; findings keep their order inside an area. Cards listed under
`retire:` get `status: retired` in cards.yaml (a line inserted under the card's id -- the file's comments
and layout are left alone). Reports every active card that no finding carries.

From pass 2 on, findings.yaml is the source of truth and is edited directly between passes; rerunning this
overwrites it, so only rerun while the fragments are still the thing being edited.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
REG = BASE / 'docs' / 'analysis' / 'register'
FRAG = REG / 'pass2'
OUT = REG / 'findings.yaml'
CARDS = REG / 'cards.yaml'
AREA_ORDER = ['style', 'handover', 'load', 'flaw', 'recovery', 'methods']

HEADER = """# Findings -- the review units from pass 2 on (Results/findings_review.html).
#
# Each finding is one page: a headline and several sections, each with its own chart, a plain
# "how this was worked out", the figures, the pass-1 cards (atoms, in cards.yaml) it stands for and the
# qualitative codes whose quotes support it. An atom may sit in more than one finding; a section repeated
# in another finding is marked `sharedWith`. `replies` answer the researcher's pass-1 note on each atom.
# Charts are drawn by scripts/register/pass2/<area>.charts.js from docs/analysis/register/pass2/<area>.json,
# which scripts/register/pass2/<area>.py writes.
#
# Assembled %s by scripts/register/assemble_findings.py from the pass-2 area fragments; edited directly
# between passes after that. Never rename an id -- responses key on it.

"""


def main() -> None:
    frags = {p.name.split('.')[0]: yaml.safe_load(p.read_text(encoding='utf-8')) or {}
             for p in FRAG.glob('*.findings.yaml')}
    order = [a for a in AREA_ORDER if a in frags] + sorted(set(frags) - set(AREA_ORDER))
    findings, retire = [], []
    for a in order:
        for f in frags[a].get('findings') or []:
            f.setdefault('source', a)
            findings.append(f)
        retire += [dict(r, area=a) for r in frags[a].get('retire') or []]
    cards = yaml.safe_load(CARDS.read_text(encoding='utf-8'))['cards']
    ids = {c['id'] for c in cards}
    carried = {x for f in findings for x in (f.get('absorbs') or [])}
    rid = {r['card'] for r in retire}
    print('areas: %s' % ', '.join('%s (%d)' % (a, len(frags[a].get('findings') or [])) for a in order))
    print('%d findings, %d atoms carried, %d retired' % (len(findings), len(carried), len(rid)))
    for what, s in (('unknown atom ids', (carried | rid) - ids), ('carried AND retired', carried & rid),
                    ('neither carried nor retired', ids - carried - rid)):
        if s:
            print('  %s: %s' % (what, ', '.join(sorted(s))))
    if '--check' in sys.argv:
        return
    from datetime import date
    OUT.write_text(HEADER % date.today().isoformat() + yaml.safe_dump(dict(findings=findings), sort_keys=False,
                   allow_unicode=True, width=110), encoding='utf-8')
    txt = CARDS.read_text(encoding='utf-8')
    for r in retire:
        if r['card'] not in ids or r['card'] in carried:
            continue
        pat = re.compile(r'(\n  id: %s\n)(?!  status:)' % re.escape(r['card']))
        txt = pat.sub(lambda m: m.group(1) + '  status: retired   # pass 1: %s\n' % r['why'].replace('\n', ' ')[:150], txt)
    CARDS.write_text(txt, encoding='utf-8')
    print('wrote', OUT.relative_to(BASE), 'and retired statuses in', CARDS.relative_to(BASE))


if __name__ == '__main__':
    main()
