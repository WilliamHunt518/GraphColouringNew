#!/usr/bin/env python3
"""Cut long verbatim passages out of the narration transcripts, from hand-written start/end phrases.

    python scripts/register/build_passages.py            # build docs/analysis/register/passages/built.json
    python scripts/register/build_passages.py --check    # report only

Input: docs/analysis/register/passages/<PID>.yaml (one file per participant read in full), each
    pid: P36
    read: {date, scope, verdict}          # what was read and the call made about this person
    passages:
      - id: p36-staff-process              # unique, stable
        title: ...                         # a few words, for the list
        parts: [{seg: interview, from: "well it's kind of this how", to: "trust in that process"}, ...]
        prompt: {seg: interview, from: "...", to: "..."}   # optional: the researcher's question just before
        speaker: participant | mixed       # mixed = the cut contains researcher words that could not be cut out
        context: ...                       # what was happening (one line)
        topics: [...]                      # theme keys (see themes in docs/analysis/register/passages/README.md)
        why: ...                           # why this passage matters, in a sentence
        links: [f-tier-trust, ...]         # register findings it bears on (optional; standalone passages have none)
        refs: [{to: f-x#section, kind: agrees | qualifies | beyond, point: ...}]   # optional links back to results,
                                           # shown on the quote card (checked by add_qual_findings.py)
Transcripts: Results/Narration/<PID>_s1/segments/NN_<seg>.txt (seg = session1, survey1, between1, session2, survey2,
interview). Lines are '[h:mm:ss] (s+N) text'. A part's text runs from the first occurrence of `from` to the first
occurrence of `to` after it, within one segment, lines joined by spaces, so the cut is verbatim by construction (only
whitespace is normalised). Parts are joined with ' […] ' unless the second starts where the first ended. Each part
must be found exactly once; an ambiguous or missing phrase is an error (lengthen the phrase).

Output built.json: {id: {pid, title, text, prompt, at, seg, videoStart, videoEnd, words, ...}} for build_review.py.
Holds verbatim participant speech: never circulate (as the quote files).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
PDIR = BASE / 'docs' / 'analysis' / 'register' / 'passages'
NARR = BASE / 'Results' / 'Narration'
LINE = re.compile(r'\[(\d+):(\d\d):(\d\d)\](?:\s*\(s\+\s*(-?[\d.]+)\))?\s?(.*)')


def segment(pid: str, seg: str):
    """(joined text, [(char offset, video seconds, session seconds or None)]) for one transcript segment."""
    hits = list((NARR / f'{pid}_s1' / 'segments').glob(f'*_{seg}.txt'))
    if len(hits) != 1:
        raise SystemExit(f'{pid}: segment {seg!r} not found ({len(hits)} matches)')
    text, marks = '', []
    for raw in hits[0].read_text(encoding='utf-8', errors='replace').splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        h, mi, s, sess, body = m.groups()
        if text:
            text += ' '
        marks.append((len(text), int(h) * 3600 + int(mi) * 60 + int(s), float(sess) if sess else None))
        text += re.sub(r'\s+', ' ', body.strip())
    return text, marks


def norm(s):
    return re.sub(r'\s+', ' ', s.strip())


def cut(pid, part, cache, errs, where):
    seg = part['seg']
    if seg not in cache:
        cache[seg] = segment(pid, seg)
    text, marks = cache[seg]
    low = text.lower()
    a, b = norm(part['from']).lower(), norm(part['to']).lower()
    i = low.find(a)
    if i < 0:
        errs.append(f'{where}: start phrase not found in {seg}: {part["from"]!r}'); return None
    if low.find(a, i + 1) >= 0:
        errs.append(f'{where}: start phrase occurs more than once in {seg}: {part["from"]!r}'); return None
    j = low.find(b, i)
    if j < 0:
        errs.append(f'{where}: end phrase not found after the start in {seg}: {part["to"]!r}'); return None
    j += len(b)
    t0 = max((v for off, v, _ in marks if off <= i), default=None)
    t1 = max((v for off, v, _ in marks if off <= j), default=None)
    s0 = max(((off, s) for off, _, s in marks if off <= i), default=(0, None))[1]
    return dict(text=text[i:j], start=i, end=j, atEnd=(j >= len(text)), seg=seg, videoStart=t0, videoEnd=t1, session=s0)


def hms(sec):
    return '%d:%02d:%02d' % (sec // 3600, sec % 3600 // 60, sec % 60) if sec is not None else ''


def main():
    errs, out, people = [], {}, {}
    for f in sorted(PDIR.glob('P*.yaml')):
        d = yaml.safe_load(f.read_text(encoding='utf-8')) or {}
        pid = d['pid']
        people[pid] = dict(read=d.get('read') or {}, n=len(d.get('passages') or []))
        cache = {}
        for p in d.get('passages') or []:
            where = f'{f.name}:{p["id"]}'
            if p['id'] in out:
                errs.append(f'{where}: duplicate id'); continue
            parts = [cut(pid, x, cache, errs, where) for x in p['parts']]
            if any(x is None for x in parts):
                continue
            text = parts[0]['text']
            for prev, x in zip(parts, parts[1:]):
                if x['seg'] != prev['seg']:      # running on from the end of one segment into the start of the next
                    gap = not (prev['atEnd'] and x['start'] == 0)
                else:
                    gap = x['start'] > prev['end'] + 1
                text += (' […] ' if gap else ' ') + x['text']
            prompt = None
            if p.get('prompt'):
                q = cut(pid, p['prompt'], cache, errs, where + ' (prompt)')
                prompt = q['text'] if q else None
            segname = parts[0]['seg']
            out[p['id']] = dict(
                pid=pid, title=p.get('title', ''), text=text, prompt=prompt, words=len(text.split()),
                seg=segname, at=('%s %s' % (segname, hms(parts[0]['videoStart']))),
                videoStart=parts[0]['videoStart'], videoEnd=parts[-1]['videoEnd'] or parts[0]['videoStart'],
                session=parts[0]['session'], speaker=p.get('speaker', 'participant'),
                context=p.get('context', ''), topics=p.get('topics') or [], why=p.get('why', ''),
                links=p.get('links') or [], refs=p.get('refs') or [])
    if errs:
        raise SystemExit('\n'.join(errs))
    words = sum(x['words'] for x in out.values())
    print('%d passages from %d people, %d words (median %d)' % (len(out), len(people), words,
          sorted(x['words'] for x in out.values())[len(out) // 2] if out else 0))
    if '--check' not in sys.argv:
        (PDIR / 'built.json').write_text(json.dumps(dict(passages=out, people=people), ensure_ascii=False, indent=1, default=str),
                                         encoding='utf-8')
        print('wrote', (PDIR / 'built.json').relative_to(BASE))


if __name__ == '__main__':
    main()
