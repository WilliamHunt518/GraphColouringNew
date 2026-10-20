#!/usr/bin/env python3
"""Clear notes Claude has acted on mid-pass, so they do not trigger the same work again.

    python scripts/register/clear_acted.py f-size-decides f-flaw-odd#refusal ...   # these keys
    python scripts/register/clear_acted.py --done                                 # every key whose `done` answers it

Each cleared note moves to docs/analysis/register/acted.json ({pass, notes: {key: [{note, updated, cleared}]}}) and
its box in responses.json is emptied (verdict, role, links, tags and highlighted quotes stay). The page shows the
archived note next to Claude's `done` reply, under "Your note this pass". The key's `updated` is bumped so a reload
prefers the server copy over an older one in the browser, and review_server.py drops any acted note a stale tab
tries to push back. When the pass closes, fold acted.json into passes/passN.json (so the note history stays whole)
and start a fresh acted.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REG = Path(__file__).resolve().parents[2] / 'docs' / 'analysis' / 'register'
RESPONSES, ACTED, FINDINGS = REG / 'responses.json', REG / 'acted.json', REG / 'findings.yaml'


def done_keys() -> set:
    out = set()
    for f in yaml.safe_load(FINDINGS.read_text(encoding='utf-8'))['findings']:
        if f.get('done'):
            out.add(f['id'])
        out |= {f['id'] + '#' + s['id'] for s in f.get('sections') or [] if s.get('done')}
    return out


def main() -> None:
    R = json.loads(RESPONSES.read_text(encoding='utf-8'))
    A = json.loads(ACTED.read_text(encoding='utf-8')) if ACTED.exists() else {'pass': R['pass'], 'notes': {}}
    if A.get('pass') != R['pass']:
        raise SystemExit('acted.json is for pass %s but responses.json is pass %s: fold it into passes/ first' % (A.get('pass'), R['pass']))
    keys = done_keys() if '--done' in sys.argv else [a for a in sys.argv[1:] if not a.startswith('-')]
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    n = 0
    for k in sorted(keys):
        card, _, qid = k.partition('@')            # <card>@<quote id> = your comment on one quote (qnotes)
        r = R['cards'].get(card)
        txt = ((r or {}).get('qnotes') or {}).get(qid) if qid else (r or {}).get('note')
        if not (txt or '').strip():
            continue
        A['notes'].setdefault(k, []).append(dict(note=txt, updated=r.get('updated'), cleared=now))
        if qid:
            r['qnotes'] = {x: v for x, v in r['qnotes'].items() if x != qid}
        else:
            r['note'] = ''
        r['updated'] = now
        n += 1
        print('cleared', k)
    ACTED.write_text(json.dumps(A, indent=1, ensure_ascii=False), encoding='utf-8')
    RESPONSES.write_text(json.dumps(R, indent=1, ensure_ascii=False), encoding='utf-8')
    print('%d notes moved to %s' % (n, ACTED.name))


if __name__ == '__main__':
    main()
