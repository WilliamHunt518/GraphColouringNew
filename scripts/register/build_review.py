#!/usr/bin/env python3
"""Build the findings review page, Results/findings_review.html.

    python scripts/register/build_review.py

Inputs
  docs/analysis/register/cards.yaml        the register (one card per claim) and the current pass number
  docs/analysis/register/responses.json    your notes for the CURRENT pass (written by review_server.py,
                                           or by hand from an exported file); embedded so a rebuilt page
                                           never loses them
  docs/analysis/register/passes/pass*.json notes from earlier passes, shown on each card as history
  Results/findings_combined.html           the combined page's payload, reused for every chart so the
                                           review page can never show a different number

The page is self-contained (charts, quotes, your notes) and works opened straight from disk; served by
review_server.py it also saves every note to responses.json as you type.
Holds verbatim participant speech -- do not circulate.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
REG = BASE / 'docs' / 'analysis' / 'register'
CARDS = REG / 'cards.yaml'
RESPONSES = REG / 'responses.json'
PASSES = REG / 'passes'
COMBINED = BASE / 'Results' / 'findings_combined.html'
TEMPLATE = BASE / 'scripts' / 'register' / 'review_template.html'
COMMON_CSS = BASE / 'scripts' / 'findings_common.css'
COMMON_JS = BASE / 'scripts' / 'findings_common.js'
OUT = BASE / 'Results' / 'findings_review.html'


def payload() -> dict:
    html = COMBINED.read_text(encoding='utf-8')
    i = html.find('{"generated"')
    if i < 0:
        raise SystemExit('no payload in %s -- build it first (scripts/build_findings_synthesis.py)' % COMBINED)
    return json.JSONDecoder().raw_decode(html[i:].replace('<\\/', '</'))[0]


def check(cards: list) -> None:
    ids = [c['id'] for c in cards]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    bad = [(c['id'], l['to']) for c in cards for l in (c.get('links') or []) if l['to'] not in ids]
    if dup or bad:
        raise SystemExit('register errors -- duplicate ids %s; links to missing cards %s' % (dup, bad))


def main() -> None:
    reg = yaml.safe_load(CARDS.read_text(encoding='utf-8'))
    cards, cur = reg['cards'], int(reg.get('pass', 1))
    check(cards)
    responses = json.loads(RESPONSES.read_text(encoding='utf-8')) if RESPONSES.exists() else {'pass': cur, 'cards': {}}
    if responses.get('pass') != cur:
        raise SystemExit('responses.json is for pass %s but cards.yaml says pass %s -- archive it into passes/ first'
                         % (responses.get('pass'), cur))
    history = {}
    for f in sorted(PASSES.glob('pass*.json'), key=lambda p: int(re.sub(r'\D', '', p.stem) or 0)):
        old = json.loads(f.read_text(encoding='utf-8'))
        for cid, r in (old.get('cards') or {}).items():
            if r.get('verdict') or (r.get('note') or '').strip() or r.get('links'):
                history.setdefault(cid, []).append(dict(pass_=old.get('pass'), **r))
    for v in history.values():
        for x in v:
            x['pass'] = x.pop('pass_')
    blob = dict(pass_=cur, cards=cards, responses=responses, history=history,
                built=datetime.now().strftime('%Y-%m-%d %H:%M'))
    blob['pass'] = blob.pop('pass_')
    enc = lambda o: json.dumps(o, separators=(',', ':'), ensure_ascii=True, default=str).replace('</', '<\\/')
    html = (TEMPLATE.read_text(encoding='utf-8')
            .replace('/*__COMMON_CSS__*/', COMMON_CSS.read_text(encoding='utf-8'))
            .replace('/*__COMMON_JS__*/', COMMON_JS.read_text(encoding='utf-8'))
            .replace('/*__DATA__*/null', enc(payload()))
            .replace('/*__REGISTER__*/null', enc(blob)))
    OUT.write_text(html, encoding='utf-8')
    active = [c for c in cards if (c.get('status') or 'active') == 'active']
    done = sum(1 for c in active if (responses['cards'].get(c['id']) or {}).get('verdict')
               or ((responses['cards'].get(c['id']) or {}).get('note') or '').strip())
    print('wrote %s (%.0f KB): pass %d, %d active cards (%d retired/merged), %d with a response, history for %d'
          % (OUT.relative_to(BASE), OUT.stat().st_size / 1024, cur, len(active), len(cards) - len(active), done, len(history)))
    print('NOTE: the page holds verbatim participant speech -- do not circulate it.')


if __name__ == '__main__':
    main()
