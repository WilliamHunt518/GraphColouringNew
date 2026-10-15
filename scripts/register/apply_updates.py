#!/usr/bin/env python3
"""Merge analysts' between-pass content changes into docs/analysis/register/findings.yaml.

    python scripts/register/apply_updates.py pass3            # merge every pass2/<area>.pass3.yaml
    python scripts/register/apply_updates.py pass3 --check    # report only

Each update file (see docs/analysis/register/pass2/BRIEF_PASS3.md) is
    findings: {<finding-id>: {title?, headline?, reply?, open?, sections: {<sid>: {field: value}}, new_sections: [...]}}
Fields replace; new sections go after the named section (`after: null` = first). An unknown finding or section id is
an error, so a typo never silently drops content. findings.yaml's header comment is kept; the rest is re-dumped.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
REG = BASE / 'docs' / 'analysis' / 'register'
FINDINGS = REG / 'findings.yaml'
FIELDS = {'title', 'headline', 'reply', 'done', 'open', 'confidence', 'links'}
SFIELDS = {'title', 'text', 'how', 'numbers', 'chart', 'reply', 'done', 'role', 'tier', 'codes', 'atoms', 'sharedWith'}


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else 'pass3'
    txt = FINDINGS.read_text(encoding='utf-8')
    header, F = txt[:txt.index('\nfindings:') + 1], yaml.safe_load(txt)['findings']
    by = {f['id']: f for f in F}
    errs = []
    for p in sorted((REG / 'pass2').glob('*.%s.yaml' % tag)):
        up = (yaml.safe_load(p.read_text(encoding='utf-8')) or {}).get('findings') or {}
        for fid, u in up.items():
            f = by.get(fid)
            if not f:
                errs.append('%s: unknown finding %s' % (p.name, fid)); continue
            for k in FIELDS & set(u):
                f[k] = u[k]
            secs = {s['id']: s for s in f['sections']}
            for sid, su in (u.get('sections') or {}).items():
                if sid not in secs:
                    errs.append('%s: %s has no section %s' % (p.name, fid, sid)); continue
                bad = set(su) - SFIELDS
                if bad:
                    errs.append('%s: %s#%s unknown fields %s' % (p.name, fid, sid, sorted(bad)))
                secs[sid].update({k: v for k, v in su.items() if k in SFIELDS})
            for ns in u.get('new_sections') or []:
                ns = dict(ns); after = ns.pop('after', None)
                if ns['id'] in secs:
                    errs.append('%s: %s already has section %s' % (p.name, fid, ns['id'])); continue
                i = 0 if after is None else next((j + 1 for j, s in enumerate(f['sections']) if s['id'] == after), None)
                if i is None:
                    errs.append('%s: %s new section %s after unknown %s' % (p.name, fid, ns['id'], after)); continue
                f['sections'].insert(i, ns); secs[ns['id']] = ns
            print('%s: %s (%d section edits, %d new)' % (p.name, fid, len(u.get('sections') or {}), len(u.get('new_sections') or [])))
    if errs:
        raise SystemExit('\n'.join(errs))
    if '--check' not in sys.argv:
        FINDINGS.write_text(header + yaml.safe_dump(dict(findings=F), sort_keys=False, allow_unicode=True, width=110),
                            encoding='utf-8')
        print('wrote', FINDINGS.relative_to(BASE))


if __name__ == '__main__':
    main()
