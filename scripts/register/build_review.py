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
  docs/analysis/register/findings.yaml     from pass 2: the findings (bigger, multi-section pages that absorb
                                           atomic cards). When present, the page reviews findings, not cards
  docs/analysis/register/pass2/*.json      analysis outputs behind the findings' charts, embedded as DATA.pass2.<stem>
  scripts/register/pass2/*.charts.js       chart functions for those outputs, inlined after the pass-1 charts

The page is self-contained (charts, quotes, your notes) and works opened straight from disk; served by
review_server.py it also saves every note to responses.json as you type.
Holds verbatim participant speech -- do not circulate.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
REG = BASE / 'docs' / 'analysis' / 'register'
CARDS = REG / 'cards.yaml'
RESPONSES = REG / 'responses.json'
PASSES = REG / 'passes'
COMBINED = BASE / 'Results' / 'findings_combined.html'
FINDINGS = REG / 'findings.yaml'
PASS2_DATA = REG / 'pass2'
PASS2_CHARTS = BASE / 'scripts' / 'register' / 'pass2'
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


def check(cards: list, findings: list, charts_js: str) -> None:
    ids = [c['id'] for c in cards]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    bad = [(c['id'], l['to']) for c in cards for l in (c.get('links') or []) if l['to'] not in ids]
    if dup or bad:
        raise SystemExit('register errors -- duplicate ids %s; links to missing cards %s' % (dup, bad))
    if not findings:
        return
    fids = [f['id'] for f in findings]
    fdup = sorted({i for i in fids if fids.count(i) > 1} | (set(fids) & set(ids)))
    absorbed = {a for f in findings for a in (f.get('absorbs') or [])}
    atoms = {a for f in findings for s in f.get('sections') or [] for a in (s.get('atoms') or [])} | absorbed
    missing = sorted(atoms - set(ids))
    badref = sorted({x for f in findings for s in f.get('sections') or [] for x in (s.get('sharedWith') or [])} - set(fids))
    badref += sorted({l['to'] for f in findings for l in (f.get('links') or [])} - set(fids) - set(ids))
    if fdup or missing:
        raise SystemExit('findings errors -- duplicate ids %s; unknown atoms %s' % (fdup, missing))
    if badref:
        print('WARNING: links/sharedWith to findings that do not exist: %s' % ', '.join(sorted(set(badref))))
    loose = [c['id'] for c in cards if (c.get('status') or 'active') == 'active' and c['id'] not in absorbed]
    if loose:
        print('WARNING: active cards no finding absorbs (retire them or absorb them): %s' % ', '.join(loose))
    nochart = sorted({s['chart'] for f in findings for s in f.get('sections') or [] if s.get('chart')
                      and ("'%s'" % s['chart']) not in charts_js and ('%s:' % s['chart']) not in charts_js})
    if nochart:
        print('WARNING: chart keys with no chart function: %s' % ', '.join(nochart))


def acted(cur: int) -> dict:
    """Notes from the open pass that Claude has acted on and cleared (clear_acted.py), shown beside the `done` reply."""
    p = BASE / 'docs' / 'analysis' / 'register' / 'acted.json'
    d = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    return d.get('notes') or {} if d.get('pass') == cur else {}


def demos() -> list:
    """The on-screen clips (docs/analysis/register/demos.yaml); the clips themselves are in Results/review_media/."""
    p = BASE / 'docs' / 'analysis' / 'register' / 'demos.yaml'
    return (yaml.safe_load(p.read_text(encoding='utf-8')) or {}).get('demos') or [] if p.exists() else []


def audio() -> dict:
    """{quote id: {file, start, end}} for the clips scripts/register/build_audio.py cut into Results/review_media/audio/."""
    p = BASE / 'Results' / 'review_media' / 'audio' / 'index.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def main() -> None:
    reg = yaml.safe_load(CARDS.read_text(encoding='utf-8'))
    cards, cur = reg['cards'], int(reg.get('pass', 1))
    findings = (yaml.safe_load(FINDINGS.read_text(encoding='utf-8')) or {}).get('findings') or [] if FINDINGS.exists() else []
    charts_js = ''.join('\n/* ── %s ── */\n' % f.name + f.read_text(encoding='utf-8')
                        for f in sorted(PASS2_CHARTS.glob('*.charts.js')))
    check(cards, findings, charts_js + TEMPLATE.read_text(encoding='utf-8'))
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
    # Claude's replies by the pass whose note they answer: closed passes from passes/replies.yaml, the last pass live
    replies = {k: {int(p): r for p, r in v.items()} for k, v in
               (yaml.safe_load((PASSES / 'replies.yaml').read_text(encoding='utf-8')) or {}).items()}         if (PASSES / 'replies.yaml').exists() else {}
    for f in findings:
        for k, x in [(f['id'], f)] + [(f['id'] + '#' + s['id'], s) for s in f['sections']]:
            if x.get('reply'):
                replies.setdefault(k, {})[cur - 1] = x['reply']
            if x.get('done'):          # answers a note made in the open pass (becomes `reply` when the pass closes)
                replies.setdefault(k, {})[cur] = x['done']
    sys.path.insert(0, str(Path(__file__).parent))
    from apply_quotes import bank, code_labels      # the quote analysts' quotes (verbatim speech) + codebook labels
    blob = dict(pass_=cur, cards=cards, findings=findings, responses=responses, history=history, replies=replies,
                quotes=bank(), codeLabels=code_labels(), demos=demos(), audio=audio(), acted=acted(cur), built=datetime.now().strftime('%Y-%m-%d %H:%M'))
    blob['pass'] = blob.pop('pass_')
    enc = lambda o: json.dumps(o, separators=(',', ':'), ensure_ascii=True, default=str).replace('</', '<\\/')
    data = payload()
    data['pass2'] = {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in sorted(PASS2_DATA.glob('*.json'))}
    html = (TEMPLATE.read_text(encoding='utf-8')
            .replace('/*__COMMON_CSS__*/', COMMON_CSS.read_text(encoding='utf-8'))
            .replace('/*__COMMON_JS__*/', COMMON_JS.read_text(encoding='utf-8'))
            .replace('/*__PASS2_CHARTS__*/', charts_js)
            .replace('/*__DATA__*/null', enc(data))
            .replace('/*__REGISTER__*/null', enc(blob)))
    OUT.write_text(html, encoding='utf-8')
    active = [c for c in cards if (c.get('status') or 'active') == 'active']
    units = [f['id'] for f in findings] if findings else [c['id'] for c in active]
    done = sum(1 for i in units if (responses['cards'].get(i) or {}).get('verdict')
               or ((responses['cards'].get(i) or {}).get('note') or '').strip())
    print('wrote %s (%.0f KB): pass %d, %d findings, %d active cards (%d retired/merged), %d with a response, history for %d'
          % (OUT.relative_to(BASE), OUT.stat().st_size / 1024, cur, len(findings), len(active), len(cards) - len(active), done, len(history)))
    print('NOTE: the page holds verbatim participant speech -- do not circulate it.')


if __name__ == '__main__':
    main()
