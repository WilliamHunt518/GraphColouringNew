#!/usr/bin/env python3
"""Merge the quote analysts' files (docs/analysis/register/qual/*.yaml) into findings.yaml.

    python scripts/register/apply_quotes.py            # write
    python scripts/register/apply_quotes.py --check    # report only

Each file (format: docs/analysis/register/qual/BRIEF_QUAL.md) holds new `quotes`, a `sections` map
("<finding>#<section>" -> summary / featured / more / codes) and optional `new_sections` (mini sections, by default
for the discussion finding). A section gets `qual: {summary, featured, more}`; quote ids are namespaced by file
(`qa:q-P05-01`) so two analysts can never collide, and `ev<N>` (row N of docs/analysis/qual/evidence.csv) is
left as is. build_review.py embeds the quotes themselves via `bank()`; the quote text never goes into
findings.yaml. Unknown findings, sections or quote ids are errors, so nothing is silently dropped.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
REG = BASE / 'docs' / 'analysis' / 'register'
QUAL = REG / 'qual'
FINDINGS = REG / 'findings.yaml'
EVIDENCE = BASE / 'docs' / 'analysis' / 'qual' / 'evidence.csv'
CODEBOOK = BASE / 'docs' / 'analysis' / 'qual' / 'CODEBOOK.md'
DISCUSSION = 'f-operator-wants'
# Participants quoted only in their own finding (the researcher's call, pass 5): a quote of theirs anywhere else is an error.
OWN_FINDING = {'P36': 'q-practitioner'}


def misplaced(B: dict, fid: str, qids) -> list:
    """Quote ids in `qids` from a participant who is kept to a finding other than `fid`."""
    return [q for q in qids if OWN_FINDING.get((B.get(q) or {}).get('pid'), fid) != fid]


def ns(stem: str, qid: str) -> str:
    return qid if re.fullmatch(r'ev\d+', qid) else '%s:%s' % (stem, qid)


def files():
    return [(p.stem, yaml.safe_load(p.read_text(encoding='utf-8')) or {}) for p in sorted(QUAL.glob('*.yaml'))]


PASSAGES = REG / 'passages' / 'built.json'
PSOURCE = {'session1': 'think-aloud', 'session2': 'think-aloud', 'survey1': 'questionnaire talk',
           'survey2': 'questionnaire talk', 'between1': 'questionnaire talk', 'interview': 'debrief'}


def bank() -> dict:
    """Every analyst quote, by namespaced id (embedded in the page; holds verbatim speech), plus the long passages
    (passages/built.json, from scripts/register/build_passages.py) as ps:<id>, flagged long."""
    out = {}
    for stem, d in files():
        for q in d.get('quotes') or []:
            q = dict(q); out[ns(stem, q.pop('id'))] = q
    if PASSAGES.exists():
        for pid_, p in json.loads(PASSAGES.read_text(encoding='utf-8'))['passages'].items():
            seg, at = p['seg'], p['at'].split(' ', 1)[-1]
            out['ps:' + pid_] = dict(pid=p['pid'], source=PSOURCE.get(seg, seg), long=True, title=p['title'],
                                     at=at if seg == 'interview' else '%s %s' % (seg.replace('session', 's'), at),
                                     text=p['text'], prompt=p.get('prompt'), mixed=p.get('speaker') == 'mixed',
                                     context=p.get('context', ''), why=p.get('why', ''), words=p['words'],
                                     refs=[dict(r, ps=pid_) for r in p.get('refs') or []])
    return out


def code_labels() -> dict:
    """C01 -> 'personal_strategy — describes a consistent personal strategy…' from the codebook table."""
    out = {}
    for m in re.finditer(r'^\| (C\d\d) `([^`]+)` \| [^|]+\| (.+?) \|$', CODEBOOK.read_text(encoding='utf-8'), re.M):
        out[m.group(1)] = {'name': m.group(2).replace('_', ' '), 'def': m.group(3).strip()}
    return out


def main() -> None:
    txt = FINDINGS.read_text(encoding='utf-8')
    header, F = txt[:txt.index('\nfindings:') + 1], yaml.safe_load(txt)['findings']
    by = {f['id']: f for f in F}
    with open(EVIDENCE, encoding='utf-8') as fh:
        n_ev = sum(1 for _ in csv.DictReader(fh))
    B = bank()
    known = set(B)
    errs, done = [], []

    def ids(stem, lst, where):
        out = []
        for q in lst or []:
            q = ns(stem, str(q))
            m = re.fullmatch(r'ev(\d+)', q)
            if (m and int(m.group(1)) >= n_ev) or (not m and q not in known):
                errs.append('%s: %s refers to unknown quote %s' % (stem, where, q))
            out.append(q)
        return out

    def qual(stem, u, where):
        return dict(summary=u.get('summary') or '', featured=ids(stem, u.get('featured'), where),
                    more=ids(stem, u.get('more'), where))

    for stem, d in files():
        for key, u in (d.get('sections') or {}).items():
            fid, _, sid = key.partition('#')
            s = next((x for x in (by.get(fid) or {}).get('sections') or [] if x['id'] == sid), None)
            if s is None:
                errs.append('%s: unknown section %s' % (stem, key)); continue
            s['qual'] = qual(stem, u, key)
            if u.get('codes') is not None:
                s['codes'] = list(u['codes'])
            done.append(key)
        for u in d.get('new_sections') or []:
            u = dict(u); fid = u.pop('finding', DISCUSSION); f = by.get(fid)
            if not f:
                errs.append('%s: new section for unknown finding %s' % (stem, fid)); continue
            sec = {k: u[k] for k in ('id', 'title', 'text', 'how', 'numbers', 'tier', 'role', 'codes') if k in u}
            sec.setdefault('tier', 'main'); sec['qual'] = qual(stem, u, fid + '#' + u['id'])
            old = next((x for x in f['sections'] if x['id'] == u['id']), None)
            if old is not None:
                old.update(sec)
            else:
                f['sections'].append(sec)
            done.append(fid + '#' + u['id'] + ' (new)')
    touched = {k.split(' ')[0] for k in done}       # the themes.yaml findings are add_qual_findings.py's to check
    for f in F:
        for s in f.get('sections') or []:
            if f['id'] + '#' + s['id'] not in touched:
                continue
            for q in misplaced(B, f['id'], (s.get('qual') or {}).get('featured', []) + (s.get('qual') or {}).get('more', [])):
                errs.append('%s#%s: %s belongs only in %s' % (f['id'], s['id'], q, OWN_FINDING[B[q]['pid']]))
    print('%d quotes in the bank; %d sections given quotes' % (len(known), len(done)))
    if errs:
        raise SystemExit('\n'.join(errs))
    if '--check' not in sys.argv:
        FINDINGS.write_text(header + yaml.safe_dump(dict(findings=F), sort_keys=False, allow_unicode=True, width=110),
                            encoding='utf-8')
        print('wrote', FINDINGS.relative_to(BASE))


if __name__ == '__main__':
    main()
