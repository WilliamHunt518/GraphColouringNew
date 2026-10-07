"""H6 helper: print one participant's debrief + interview text (read-only on Results/).

Usage: python scripts/analysis_round1/h6_extract_text.py P20 [P21 ...]
Interview paragraphs are numbered (0-based, non-empty paragraphs only) -- the `interview@paraN`
references in docs/analysis/round1/h6_codes.csv point at these numbers.
Never prints quotes.json (which carries the existing stance codes).
"""
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

BASE = Path(__file__).resolve().parents[2]
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def interview_paragraphs(pid):
    path = BASE / 'Results' / 'Interviews' / f'{pid}.docx'
    if not path.exists():
        return None
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    out = []
    for p in root.iter(W + 'p'):
        text = ''.join(t.text or '' for t in p.iter(W + 't')).strip()
        if text:
            out.append(text)
    return out


def debrief(pid):
    path = BASE / 'Results' / 'Narration' / f'{pid}_s1' / 'debrief.txt'
    return path.read_text(encoding='utf-8') if path.exists() else None


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for pid in sys.argv[1:]:
        print('#' * 30, pid)
        d = debrief(pid)
        print('--- debrief.txt:', 'present' if d else 'absent')
        if d:
            print(d)
        paras = interview_paragraphs(pid)
        print('--- interview docx:', 'present (%d paras)' % len(paras) if paras else 'absent')
        if paras:
            for i, t in enumerate(paras):
                print('[para%d] %s' % (i, t))
