"""Cut a sitting's transcript into the phases it is actually made of.

One recording is one participant's whole visit, and the parts of it answer different questions:

    intake     demographics + the AI-attitude battery. Form-filling; rarely says anything.
    session 1  think-aloud while working, plus researcher exchanges. The decision-level data.
    survey 1   NASA-TLX / trust / TAM. People start volunteering opinions here, unprompted.
    between    the 30 s inter-session screen.
    session 2  as session 1, other scenario.
    survey 2   as survey 1.
    interview  the semi-structured debrief. Longest and richest part of most sittings.

Treating all of that as one undifferentiated transcript throws away the thing that makes a quote
interpretable -- whether it was said mid-decision, right after scoring themselves, or in
considered hindsight twenty minutes later. This splits it.

    python scripts/narration_segments.py --list
    python scripts/narration_segments.py --participants P36 P30 P19
    python scripts/narration_segments.py                     # everyone with a transcript

Output, per participant, next to the transcript in `Results/Narration/<pid>_s1/`:

    segments.json            boundaries, anchor provenance, per-segment word counts
    segments/NN_kind.txt     that phase's speech, timestamped, human-readable
    segments/NN_kind.jsonl   the same with word timings, for tooling

Nothing here is committed -- `Results/Narration/` is gitignored, and a segment transcript is as
identifiable as the audio it came from. See NARRATION.md, "Handling and ethics".

## Where the clock comes from

Every phase boundary is already in the event log as a `phase_change` with an exact `wallClock`,
so the ONLY unknown is the wall-clock time of video frame 0. Two ways to get it, in order of
preference:

1. **An existing `alignment.json`** whose timer-OCR reads cluster on session 1. Exact. Note that
   such a file usually reports `ok: false` and a huge `residualMax` -- that is not a failure, it
   is one recording containing two sessions, so the reads form two clusters ~631 s apart and the
   single-offset fit rightly refuses to average them. `_ocr_anchor` clusters first, then takes the
   earliest cluster, which is session 1's.
2. **File mtime minus duration.** mtime is when ffmpeg finished writing, so this lands slightly
   BEFORE the true first frame -- ffmpeg finalises the container after the last frame, and mtime
   has coarse granularity. Measured against the five known-good OCR offsets (P01/P03/P04/P06/P07)
   the bias is a consistent +1.7 to +5.4 s, hence `MTIME_STARTUP_LATENCY` below; residual after
   correcting is under +-2 s.

+-2 s is fine for cutting phase blocks, and NOT fine for placing an utterance inside a single
decision window. Anything needing that precision should go through the pipeline's `align` step
per session, not this. `segments.json` records which anchor was used and its uncertainty so a
reader can tell the difference.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from narration_core import parse_iso, redact  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RECORDINGS = ROOT / 'Results' / 'Recordings'
NARRATION = ROOT / 'Results' / 'Narration'
PARTICIPANTS = ROOT / 'Results' / 'Participants'

# Calibrated on the five recordings that have a trustworthy timer-OCR offset; see the module
# docstring. Recompute with --calibrate if the recording rig changes.
MTIME_STARTUP_LATENCY = 3.0
MTIME_UNCERTAINTY = 2.0

# P36 is a serving military officer -- the only participant with domain expertise in the task the
# scenario simulates, recruited last. Their narration is worth far more per word than anyone
# else's and is correspondingly unrepresentative, so it is flagged here and travels with the data
# rather than living in someone's memory. Whether to pool or separate them is an analysis
# decision; this only makes the decision possible.
CONSULTED_EXPERTS = {'P36'}

# Name redaction is OFF by default, and that is deliberate. The researcher's own name is "Will",
# which `redact()` matches case-insensitively and whole-word -- so switching it on by default
# silently rewrote "I will say" to "I [name] say" 217 times across the corpus before this was
# caught. A redaction that corrupts the sentence is worse than none here: these files never leave
# the gitignored tree, and the person reading them is the person whose name it would remove.
# Pass --redact explicitly, with names that are not also ordinary words.
DEFAULT_REDACT: list[str] = []

# Names that are also common English words. Redacting one of these mangles the transcript, so it
# is worth a loud warning rather than a silent corruption that only shows up mid-analysis.
AMBIGUOUS_NAMES = {'will', 'hunt', 'mark', 'grace', 'may', 'june', 'bill', 'rose', 'art', 'sue',
                   'drew', 'frank', 'hope', 'jack', 'mike', 'pat', 'ray', 'rich', 'victor'}

PHASE_KIND = {'playing': 'session', 'survey': 'survey', 'between': 'between', 'done': 'interview'}


# ── the sitting's shape, from the log ─────────────────────────────────────────────────────────

def phase_boundaries(log: dict) -> list[dict]:
    """Every `phase_change` across the whole sitting, in order, flattened across sessions.

    Sessions are separate lists in the export but one continuous recording, so they are walked as
    one stream. `sessionNumber` is carried through because a `playing` phase is only interpretable
    alongside which scenario it was.
    """
    out = []
    for n, events in enumerate(log['sessions'], start=1):
        complexity = None
        for ev in events:
            if ev['type'] == 'session_start':
                complexity = ev.get('complexity')
            if ev['type'] != 'phase_change':
                continue
            out.append(dict(wall=parse_iso(ev['wallClock']), fromPhase=ev.get('fromPhase'),
                            toPhase=ev.get('toPhase'), sessionNumber=n, complexity=complexity))
    out.sort(key=lambda b: b['wall'])
    return out


# ── the one unknown: wall clock of video frame 0 ──────────────────────────────────────────────

def video_duration(path: Path) -> float:
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'csv=p=0', str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


def _cluster(offsets: list[float], tol: float = 3.0) -> list[list[float]]:
    """Group offsets that agree to within `tol`. One group per session in the recording."""
    groups: list[list[float]] = []
    for o in sorted(offsets):
        if groups and o - groups[-1][-1] <= tol:
            groups[-1].append(o)
        else:
            groups.append([o])
    return groups


def _ocr_anchor(pid: str, session_one_start: datetime.datetime) -> dict | None:
    """Session 1's offset from an existing alignment.json, ignoring its overall `ok` verdict.

    The file's own fit spans both sessions and so is legitimately not ok; the individual reads are
    still good. Only a cluster with at least three agreeing reads is trusted.
    """
    path = NARRATION / ('%s_s1' % pid) / 'alignment.json'
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    duration = float(data.get('sessionDuration') or 480.0)
    offsets = [r['videoT'] - (duration - r['remaining'])
               for r in data.get('reads', []) if r.get('remaining') is not None]
    if not offsets:
        return None
    first = _cluster(offsets)[0]          # earliest cluster == session 1
    if len(first) < 3:
        return None
    offset = sum(first) / len(first)
    spread = max(first) - min(first)
    return dict(source='timer-ocr', offsetSec=offset, uncertaintySec=max(spread / 2.0, 0.5),
                reads=len(first),
                videoStartWallClock=(session_one_start
                                     - datetime.timedelta(seconds=offset)).isoformat())


def _mtime_anchor(video: Path, duration: float, session_one_start: datetime.datetime) -> dict:
    ended = datetime.datetime.fromtimestamp(video.stat().st_mtime, datetime.timezone.utc)
    start = ended - datetime.timedelta(seconds=duration - MTIME_STARTUP_LATENCY)
    return dict(source='mtime', offsetSec=(session_one_start - start).total_seconds(),
                uncertaintySec=MTIME_UNCERTAINTY, reads=0,
                videoStartWallClock=start.isoformat())


def anchor_for(pid: str, video: Path, duration: float,
               session_one_start: datetime.datetime) -> dict:
    return _ocr_anchor(pid, session_one_start) or _mtime_anchor(video, duration, session_one_start)


# ── segments ──────────────────────────────────────────────────────────────────────────────────

def build_segments(pid: str, log: dict, anchor: dict, duration: float) -> list[dict]:
    """The A-F blocks, in video time.

    Derived from the phase stream rather than hardcoded, so a sitting that deviates (an abandoned
    session, a third session) still segments correctly instead of silently mislabelling.
    """
    start_wall = parse_iso(anchor['videoStartWallClock'])

    def v(wall: datetime.datetime) -> float:
        return (wall - start_wall).total_seconds()

    bounds = phase_boundaries(log)
    if not bounds:
        raise SystemExit('%s: no phase_change events' % pid)

    segs = [dict(kind='intake', videoStart=0.0, videoEnd=v(bounds[0]['wall']),
                 sessionNumber=None, complexity=None)]
    for i, b in enumerate(bounds):
        end = v(bounds[i + 1]['wall']) if i + 1 < len(bounds) else duration
        kind = PHASE_KIND.get(b['toPhase'], b['toPhase'] or 'unknown')
        segs.append(dict(kind=kind, videoStart=v(b['wall']), videoEnd=end,
                         sessionNumber=b['sessionNumber'],
                         complexity=b['complexity'] if kind == 'session' else None))

    # Session time is only meaningful inside a `playing` phase, and there it is exactly
    # video minus that phase's own start -- no separate fit needed.
    for s in segs:
        s['sessionTimeOffset'] = s['videoStart'] if s['kind'] == 'session' else None
        s['durationSec'] = max(0.0, s['videoEnd'] - s['videoStart'])

    counts: dict[str, int] = {}
    for s in segs:
        counts[s['kind']] = counts.get(s['kind'], 0) + 1
        s['index'] = len([x for x in segs if x is s or segs.index(x) < segs.index(s)])
        suffix = str(counts[s['kind']]) if s['kind'] in ('session', 'survey', 'between') else ''
        s['name'] = s['kind'] + suffix
        s['id'] = '%s/%s' % (pid, s['name'])
    return segs


def merge_runs(items: list[dict], merge_gap: float, max_span: float) -> list[dict]:
    """Glue whisper's acoustic fragments back into things that read like sentences.

    Whisper cuts on silence, not on meaning, and how finely varies wildly between recordings --
    P36's sitting came back as 2525 fragments of two or three words each, which is unreadable as
    a transcript even though the words are right. Adjacent fragments separated by less than
    `merge_gap` are joined, up to `max_span` so one unbroken monologue does not become a single
    twenty-minute paragraph with one timestamp on it.
    """
    out: list[dict] = []
    for it in items:
        prev = out[-1] if out else None
        if (prev is not None
                and it['videoStart'] - prev['videoEnd'] <= merge_gap
                and it['videoEnd'] - prev['videoStart'] <= max_span):
            prev['videoEnd'] = it['videoEnd']
            prev['text'] = (prev['text'] + ' ' + it['text']).strip()
            prev['words'].extend(it['words'])
        else:
            out.append(dict(it))
    return out


def slice_transcript(segments: list[dict], transcript: dict, names: list[str],
                     merge_gap: float = 0.6, max_span: float = 30.0) -> None:
    """Attach each whisper segment to the phase it falls in.

    A segment straddling a boundary is assigned by its MIDPOINT and then appears once, in one
    phase. The alternative -- duplicating it -- would double-count words and make any per-phase
    rate measure wrong; a boundary-straddling sentence is rare and always visible at the top or
    bottom of a file.
    """
    for s in segments:
        s['utterances'] = []
    for seg in transcript.get('segments', []):
        start, end = seg.get('start'), seg.get('end')
        text = (seg.get('text') or '').strip()
        if start is None or end is None or not text:
            continue
        mid = (float(start) + float(end)) / 2.0
        for s in segments:
            if s['videoStart'] <= mid < s['videoEnd']:
                s['utterances'].append(dict(
                    videoStart=float(start), videoEnd=float(end),
                    sessionTime=(float(start) - s['sessionTimeOffset']
                                 if s['sessionTimeOffset'] is not None else None),
                    text=redact(text, names),
                    words=[dict(start=w['start'], end=w['end'], word=redact(w['word'], names))
                           for w in (seg.get('words') or [])
                           if w.get('start') is not None]))
                break
    for s in segments:
        s['utterances'] = merge_runs(s['utterances'], merge_gap, max_span)
        # Session time is recomputed after merging: a merged utterance starts where its FIRST
        # fragment did, and reusing the pre-merge value would point at the wrong moment.
        for u in s['utterances']:
            u['sessionTime'] = (u['videoStart'] - s['sessionTimeOffset']
                                if s['sessionTimeOffset'] is not None else None)
        s['wordCount'] = sum(len(u['text'].split()) for u in s['utterances'])
        s['speechSec'] = round(sum(u['videoEnd'] - u['videoStart'] for u in s['utterances']), 1)
        s['utteranceCount'] = len(s['utterances'])


def hms(t: float) -> str:
    t = max(0.0, t)
    return '%d:%02d:%02d' % (int(t // 3600), int(t % 3600 // 60), int(t % 60))


def write_segment_files(outdir: Path, pid: str, segs: list[dict], anchor: dict) -> None:
    d = outdir / 'segments'
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob('*'):
        old.unlink()
    for i, s in enumerate(segs):
        stem = '%02d_%s' % (i, s['name'])
        lines = ['# %s  %s' % (s['id'], s['kind']),
                 '# video %s - %s (%.0f s)' % (hms(s['videoStart']), hms(s['videoEnd']),
                                               s['durationSec'])]
        if s['complexity']:
            lines.append('# scenario: %s (session %s)' % (s['complexity'], s['sessionNumber']))
        lines.append('# anchor: %s +-%.1fs -- timestamps are video time%s'
                     % (anchor['source'], anchor['uncertaintySec'],
                        '; (s+N) is session time' if s['sessionTimeOffset'] is not None else ''))
        lines.append('')
        for u in s['utterances']:
            stamp = '[%s]' % hms(u['videoStart'])
            if u['sessionTime'] is not None:
                stamp += ' (s+%5.1f)' % u['sessionTime']
            lines.append('%s %s' % (stamp, u['text']))
        (d / (stem + '.txt')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        with (d / (stem + '.jsonl')).open('w', encoding='utf-8') as fh:
            for u in s['utterances']:
                fh.write(json.dumps(u) + '\n')

    meta = [{k: v for k, v in s.items() if k != 'utterances'} for s in segs]
    (outdir / 'segments.json').write_text(json.dumps(dict(
        participantId=pid, consultedExpert=pid in CONSULTED_EXPERTS,
        anchor=anchor, segments=meta), indent=1), encoding='utf-8')


# ── driver ────────────────────────────────────────────────────────────────────────────────────

def participants() -> list[str]:
    out = []
    for d in sorted(NARRATION.glob('*_s1')):
        pid = d.name[:-3]
        if (d / 'transcript.raw.json').exists() and (PARTICIPANTS / ('%s.json' % pid)).exists():
            out.append(pid)
    return out


def process(pid: str, names: list[str], verbose: bool = True) -> dict:
    outdir = NARRATION / ('%s_s1' % pid)
    log = json.loads((PARTICIPANTS / ('%s.json' % pid)).read_text(encoding='utf-8'))
    transcript = json.loads((outdir / 'transcript.raw.json').read_text(encoding='utf-8'))
    video = RECORDINGS / ('%s.mp4' % pid)
    duration = video_duration(video) if video.exists() else float(transcript.get('durationSec') or 0)

    session_one_start = parse_iso(log['sessions'][0][0]['wallClock'])
    anchor = anchor_for(pid, video, duration, session_one_start)
    segs = build_segments(pid, log, anchor, duration)
    slice_transcript(segs, transcript, names)
    write_segment_files(outdir, pid, segs, anchor)

    # A transcript shorter than the sitting means the audio was trimmed before transcription;
    # the later phases will read as empty and that is a data problem, not a quiet participant.
    covered = float(transcript.get('durationSec') or 0)
    truncated = covered < duration - 60

    if verbose:
        flag = ' [EXPERT]' if pid in CONSULTED_EXPERTS else ''
        print('%-7s anchor=%-9s +-%.1fs  video=%s%s' % (pid, anchor['source'],
                                                        anchor['uncertaintySec'], hms(duration), flag))
        if truncated:
            print('        WARNING: transcript covers only %s of %s -- audio was trimmed'
                  % (hms(covered), hms(duration)))
        for s in segs:
            print('        %-10s %8s-%-8s %5.0fs %6d words %5.0fs speech'
                  % (s['name'], hms(s['videoStart']), hms(s['videoEnd']),
                     s['durationSec'], s['wordCount'], s['speechSec']))
    return dict(pid=pid, anchor=anchor, segments=segs, truncated=truncated)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--participants', nargs='*', help='default: everyone with a transcript')
    ap.add_argument('--list', action='store_true', help='who can be segmented, and stop')
    ap.add_argument('--redact', nargs='*', default=DEFAULT_REDACT,
                    help='names to strip; OFF by default -- see AMBIGUOUS_NAMES before using it')
    args = ap.parse_args()

    for name in args.redact:
        if name.lower() in AMBIGUOUS_NAMES:
            print('warning: --redact %r is also an ordinary word; every occurrence of it becomes '
                  '"[name]", including the ones that are not names.' % name, file=sys.stderr)

    pids = args.participants or participants()
    if args.list:
        for pid in participants():
            print('  %s%s' % (pid, '  [consulted expert]' if pid in CONSULTED_EXPERTS else ''))
        return

    rows = []
    for pid in pids:
        try:
            rows.append(process(pid, args.redact))
        except Exception as exc:                       # one bad sitting must not stop the rest
            print('%-7s FAILED: %s' % (pid, exc), file=sys.stderr)
    print('\nsegmented %d participants' % len(rows))
    bad = [r['pid'] for r in rows if r['truncated']]
    if bad:
        print('transcripts that do not cover the whole sitting: %s' % ', '.join(bad))


if __name__ == '__main__':
    main()
