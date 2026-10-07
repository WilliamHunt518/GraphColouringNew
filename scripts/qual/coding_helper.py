"""Qual coding helper: validate coded evidence against the source transcripts and build the outputs.

Usage: python scripts/qual/coding_helper.py <evidence.tsv>
Input TSV columns (no header): pid, code, source, location, led, excerpt.
  - " ... " in an excerpt marks an omission; it is written out as " […] ".
Checks: every excerpt fragment occurs verbatim in that participant's source text; excerpt <= 40 words.
Writes docs/analysis/qual/evidence.csv and docs/analysis/qual/codes_matrix.csv. Read-only on Results/.
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'analysis_round1'))
from h6_extract_text import debrief, interview_paragraphs  # noqa: E402

BASE = Path(__file__).resolve().parents[2]
OUT = BASE / 'docs' / 'analysis' / 'qual'
CODES = ['C%02d' % i for i in range(1, 29)]
PIDS = ['P01', 'P02', 'P03', 'P04', 'P05', 'P06', 'P07', 'P10', 'P11', 'P12', 'P13', 'P14', 'P15',
        'P16', 'P17', 'P18', 'P19', 'P20', 'P21', 'P22', 'P24', 'P25', 'P26', 'P27', 'P28', 'P29',
        'P30', 'P31', 'P32', 'P33', 'P34', 'P35', 'P36']


def norm(s):
    return re.sub(r'\s+', ' ', s.replace('’', "'").replace('“', '"').replace('”', '"')).strip().lower()


def main(path):
    rows = [l.rstrip('\n').split('\t') for l in open(path, encoding='utf-8') if l.strip()]
    texts, sources = {}, {}
    for pid in PIDS:
        d, p = debrief(pid), interview_paragraphs(pid)
        texts[(pid, 'debrief')] = norm(re.sub(r'\[\d+:\d+:\d+\]', ' ', d)) if d else ''
        texts[(pid, 'interview')] = norm(' '.join(p)) if p else ''
        sources[pid] = '+'.join(s for s, t in (('debrief', d), ('interview', p)) if t)
    problems, out = 0, []
    for pid, code, src, loc, led, exc in rows:
        assert pid in PIDS and code in CODES and src in ('debrief', 'interview') and led in '01', (pid, code)
        frags = [f for f in re.split(r' \.\.\. |…', exc) if f.strip()]
        for f in frags:
            if norm(f) not in texts[(pid, src)]:
                problems += 1
                print('NOT VERBATIM', pid, code, loc, '|', f)
        exc_out = exc.replace(' ... ', ' […] ')
        n = len(exc_out.split())
        if n > 40:
            problems += 1
            print('TOO LONG (%d words)' % n, pid, code, loc)
        out.append(dict(pid=pid, code=code, source=src, location=loc, led=led, excerpt=exc_out))
    out.sort(key=lambda r: (PIDS.index(r['pid']), r['code'], r['source'], r['location']))
    with open(OUT / 'evidence.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['pid', 'code', 'source', 'location', 'led', 'excerpt'])
        w.writeheader()
        w.writerows(out)
    present = {(r['pid'], r['code']) for r in out}
    with open(OUT / 'codes_matrix.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['pid', 'sources'] + CODES)
        for pid in PIDS:
            w.writerow([pid, sources[pid]] + [int((pid, c) in present) for c in CODES])
    counts = {c: sum((p, c) in present for p in PIDS) for c in CODES}
    led_only = {c: [p for p in PIDS if (p, c) in present and
                    all(r['led'] == '1' for r in out if r['pid'] == p and r['code'] == c)] for c in CODES}
    for c in CODES:
        print(c, counts[c], 'led-only:', ','.join(led_only[c]) or '-')
    print('rows', len(out), 'problems', problems)


if __name__ == '__main__':
    main(sys.argv[1])
