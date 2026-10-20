#!/usr/bin/env python3
"""Cut an audio clip for every quote on the review page, so a transcription can be checked by ear.

    python scripts/register/build_audio.py            # locate every quote, cut any clip that is missing or has moved
    python scripts/register/build_audio.py --force    # re-cut every clip
    python scripts/register/build_audio.py --check    # locate only, report what could not be found

Quotes: the quote bank (apply_quotes.bank(): analyst quotes and the long passages) plus the coded excerpts
(docs/analysis/qual/evidence.csv, ids ev<N>). Each is found in its speaker's word-timed transcript
(Results/Narration/<pid>_s*/transcript.raw.json, the times are into that folder's audio.wav) by matching a few words
at its start and a few at its end (case and punctuation ignored, so lightly tidied quotes still match); cuts marked
[…] and [bracketed] words are skipped over, and the clip runs from the first word to the last, so it includes any cut
material. Output: Results/review_media/audio/<id>.mp3 and index.json {id: {file, start, end}}, which build_review.py
embeds. Results/review_media/ is gitignored: these are participants' voices, never commit or circulate them.
Needs ffmpeg on PATH.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
NARR = BASE / 'Results' / 'Narration'
OUT = BASE / 'Results' / 'review_media' / 'audio'
EVIDENCE = BASE / 'docs' / 'analysis' / 'qual' / 'evidence.csv'
sys.path.insert(0, str(Path(__file__).parent))
PAD0, PAD1 = 0.4, 0.7           # seconds of lead-in and tail around the first and last word
CUT = re.compile(r'\[[^\]]*\]|…|\.\.\.')


def norm(w: str) -> str:
    w = w.lower().replace('’', "'").replace('‘', "'")
    return re.sub(r"^'+|'+$", '', re.sub(r"[^\w']+", '', w))


def stream(pid: str):
    """[(norm word, start, end, audio path)] across the person's recordings, in order."""
    out = []
    for d in sorted(NARR.glob(f'{pid}_s*')):
        raw, wav = d / 'transcript.raw.json', d / 'audio.wav'
        if not (raw.exists() and wav.exists()):
            continue
        for s in json.loads(raw.read_text(encoding='utf-8'))['segments']:
            for w in s.get('words') or []:
                n = norm(w['word'])
                if n:
                    out.append((n, w['start'], w['end'], wav))
    return out


def grams(S, k):
    ix = {}
    for i in range(len(S) - k + 1):
        ix.setdefault(tuple(x[0] for x in S[i:i + k]), []).append(i)
    return ix


def locate(text: str, S, G):
    """(start s, end s, wav) of the quote in stream S, or None."""
    pieces = [[norm(w) for w in p.split()] for p in CUT.split(text)]
    toks = [w for p in pieces for w in p if w]
    if not toks:
        return None
    head, tail = toks[:8], toks[-8:]

    def anchors(seq, from_end):       # the k-gram nearest the quote's edge that occurs at all, longest k first
        for k in (5, 4, 3, 2):
            for o in range(len(seq) - k + 1):
                o2 = len(seq) - k - o if from_end else o
                hits = G[k].get(tuple(seq[o2:o2 + k]), [])
                if hits:
                    return sorted(i + len(seq) - 1 - o2 if from_end else i - o2 for i in hits)
        return []

    best = None
    starts, ends = anchors(head, False), anchors(tail, True)
    for a in starts:
        for b in ends:
            if a <= b < a + 3 * len(toks) + 60 and 0 <= a and b < len(S) and S[a][3] == S[b][3]:
                if best is None or b - a < best[1] - best[0]:
                    best = (a, b)
                break
    if best is None:
        return None
    a, b = best
    have = {x[0] for x in S[a:b + 1]}
    if sum(t in have for t in toks) < 0.75 * len(toks):      # anchored on a stray phrase: better no clip than a wrong one
        return None
    return max(0.0, S[a][1] - PAD0), S[b][2] + PAD1, S[a][3]


def quotes():
    from apply_quotes import bank
    out = {k: (v['pid'], v['text']) for k, v in bank().items() if v.get('pid') and v.get('text') and not v.get('paraphrase')}
    with open(EVIDENCE, encoding='utf-8') as fh:
        for i, r in enumerate(csv.DictReader(fh)):
            out['ev%d' % i] = (r['pid'], r['excerpt'])
    return out


def main() -> None:
    check, force = '--check' in sys.argv, '--force' in sys.argv
    if not check and not shutil.which('ffmpeg'):
        raise SystemExit('ffmpeg not found on PATH')
    OUT.mkdir(parents=True, exist_ok=True)
    idx_path = OUT / 'index.json'
    old = json.loads(idx_path.read_text(encoding='utf-8')) if idx_path.exists() else {}
    Q, cache, idx, miss, cut = quotes(), {}, {}, [], 0
    for qid, (pid, text) in sorted(Q.items()):
        if pid not in cache:
            S = stream(pid)
            cache[pid] = (S, {k: grams(S, k) for k in (2, 3, 4, 5)}) if S else None
        if not cache[pid]:
            continue                                   # no recording on this machine (or an interview by notes)
        hit = locate(text, *cache[pid])
        if not hit:
            miss.append(qid); continue
        t0, t1, wav = hit
        name = re.sub(r'[^\w.-]', '_', qid) + '.mp3'
        idx[qid] = dict(file='review_media/audio/' + name, start=round(t0, 2), end=round(t1, 2))
        if check:
            continue
        moved = (old.get(qid) or {}).get('start') != idx[qid]['start'] or (old.get(qid) or {}).get('end') != idx[qid]['end']
        if force or moved or not (OUT / name).exists():
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '%.2f' % t0, '-t', '%.2f' % (t1 - t0), '-i', str(wav),
                            '-ac', '1', '-c:a', 'libmp3lame', '-b:a', '64k', str(OUT / name)], check=True)
            cut += 1
    print('%d quotes: %d located, %d not found, %d with no recording here; %d clips cut' % (
        len(Q), len(idx), len(miss), len(Q) - len(idx) - len(miss), cut))
    if miss:
        print('not found:', ' '.join(miss[:40]) + (' …' if len(miss) > 40 else ''))
    if not check:
        idx_path.write_text(json.dumps(idx, indent=0), encoding='utf-8')


if __name__ == '__main__':
    main()
