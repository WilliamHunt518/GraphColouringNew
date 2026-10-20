#!/usr/bin/env python3
"""Insert the qualitative findings (docs/analysis/register/passages/themes.yaml) into findings.yaml.

    python scripts/register/add_qual_findings.py            # write
    python scripts/register/add_qual_findings.py --check    # report only

Each finding in themes.yaml replaces the finding with the same id (or is inserted after `after:`, in file order), with
`area` set from the file. Every passage id it cites (ps:<id>) must exist in passages/built.json (run
scripts/register/build_passages.py first), and every other quote id must be in the quote bank, so a typo never
silently drops a quote. findings.yaml's header comment is kept; the rest is re-dumped.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
REG = BASE / 'docs' / 'analysis' / 'register'
FINDINGS, THEMES = REG / 'findings.yaml', REG / 'passages' / 'themes.yaml'
sys.path.insert(0, str(Path(__file__).parent))


def main() -> None:
    from apply_quotes import OWN_FINDING, bank, misplaced
    B = bank()
    known = set(B)
    T = yaml.safe_load(THEMES.read_text(encoding='utf-8'))
    txt = FINDINGS.read_text(encoding='utf-8')
    header, F = txt[:txt.index('\nfindings:') + 1], yaml.safe_load(txt)['findings']
    errs = []
    new = []
    for f in T['findings']:
        f = dict(f, area=T['area'])
        for s in f['sections']:
            for q in (s.get('qual') or {}).get('featured', []) + (s.get('qual') or {}).get('more', []):
                if q not in known and not q.startswith('ev'):
                    errs.append('%s#%s: unknown quote %s' % (f['id'], s['id'], q))
            for q in misplaced(B, f['id'], (s.get('qual') or {}).get('featured', []) + (s.get('qual') or {}).get('more', [])):
                errs.append('%s#%s: %s belongs only in %s' % (f['id'], s['id'], q, OWN_FINDING[B[q]['pid']]))
            for r in s.get('refs') if isinstance(s.get('refs'), list) else []:    # links back to the results
                fid, _, sid = r['to'].partition('#')
                tgt = next((x for x in F + T['findings'] if x['id'] == fid), None)
                if not tgt or not any(x['id'] == sid for x in tgt['sections']):
                    errs.append('%s#%s: ref to unknown section %s' % (f['id'], s['id'], r['to']))
                if 'ps:' + r['ps'] not in known:
                    errs.append('%s#%s: ref names unknown passage %s' % (f['id'], s['id'], r['ps']))
                if r.get('kind') not in ('agrees', 'qualifies', 'beyond'):
                    errs.append('%s#%s: ref kind must be agrees / qualifies / beyond' % (f['id'], s['id']))
        new.append(f)
    for qid, q in B.items():                       # a passage's own links back (passages/<PID>.yaml `refs`)
        for r in q.get('refs') or []:
            fid, _, sid = r['to'].partition('#')
            tgt = next((x for x in F + T['findings'] if x['id'] == fid), None)
            if not tgt or not any(x['id'] == sid for x in tgt['sections']):
                errs.append('%s: ref to unknown section %s' % (qid, r['to']))
            if r.get('kind') not in ('agrees', 'qualifies', 'beyond'):
                errs.append('%s: ref kind must be agrees / qualifies / beyond' % qid)
    if errs:
        raise SystemExit('\n'.join(errs))
    ids = {f['id'] for f in new}
    F = [f for f in F if f['id'] not in ids]
    at = next((i + 1 for i, f in enumerate(F) if f['id'] == T.get('after')), len(F))
    F[at:at] = new
    n = sum(len(f['sections']) for f in new)
    q = sum(len((s.get('qual') or {}).get('featured', [])) + len((s.get('qual') or {}).get('more', []))
            for f in new for s in f['sections'])
    print('%d qualitative findings, %d sections, %d passage references' % (len(new), n, q))
    if '--check' not in sys.argv:
        FINDINGS.write_text(header + yaml.safe_dump(dict(findings=F), sort_keys=False, allow_unicode=True, width=110),
                            encoding='utf-8')
        print('wrote', FINDINGS.relative_to(BASE))


if __name__ == '__main__':
    main()
