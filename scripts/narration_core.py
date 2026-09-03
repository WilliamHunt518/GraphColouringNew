#!/usr/bin/env python3
"""
Pure logic for the narration pipeline: clocks, alignment, decision windows, redaction.

Deliberately **standard library only**. Everything that needs ffmpeg, Whisper or OpenCV lives in
`narration_pipeline.py`; everything that decides *what a number means* lives here, so it can be
unit-tested without a video, a GPU or a model download. `scripts/test_narration.py` pins it.

Read `docs/NARRATION.md` first -- it explains the three clocks and why alignment is done the way
it is.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

# ── the three clocks ──────────────────────────────────────────────────────────────────────────
#
#   video time    v  seconds from the recording's first frame. What Whisper timestamps are in.
#   session time  e  seconds since the session started. What every event's `elapsed` is in.
#   wall clock       ISO-8601 UTC. What every event's `wallClock` is in.
#
# The pipeline works in SESSION time, because that is the axis the logs already use and the axis a
# reader thinks in ("what did they say 4 seconds before they clicked Aggressive?").

CLOCK_RE = re.compile(r'^\s*(\d{1,2})\s*[:.]\s*(\d{2})\s*$')


def parse_clock(text: str) -> Optional[float]:
    """Read the on-screen countdown ("7:59") as seconds REMAINING, or None if it isn't a clock.

    OCR noise is the norm, not the exception: this returns None for anything that doesn't look
    exactly like m:ss so a garbled frame is dropped rather than silently poisoning the fit.
    """
    if text is None:
        return None
    m = CLOCK_RE.match(str(text).replace('O', '0').replace('o', '0'))
    if not m:
        return None
    minutes, seconds = int(m.group(1)), int(m.group(2))
    if seconds >= 60 or minutes > 59:
        return None
    return float(minutes * 60 + seconds)


def remaining_to_elapsed(remaining: float, duration: float) -> float:
    """The header counts DOWN. Logs count up. `duration` is session_start.sessionDuration."""
    return duration - remaining


def parse_iso(ts: str) -> datetime:
    """Parse an event `wallClock` (…Z) into an aware UTC datetime."""
    s = ts.strip()
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── alignment ─────────────────────────────────────────────────────────────────────────────────

class Alignment:
    """Maps video time to session time: e = v - offset.

    A single offset is correct while the simulation and the recording both run in real time. They
    can come apart: `MAX_TICK_GAP_MS` in gameReducer.ts deliberately PAUSES simulated time when the
    primary window loses visibility, so session time plateaus while the video keeps rolling. That
    is why `residual_max` matters -- a large one is not noise, it is a stall, and the transcript
    after it is offset by however long the stall lasted.
    """

    def __init__(self, offset: float, samples: int = 0, residual_max: float = 0.0,
                 residual_median: float = 0.0, source: str = 'unknown',
                 tolerance: float = 1.5):
        self.offset = offset
        self.samples = samples
        self.residual_max = residual_max
        self.residual_median = residual_median
        self.source = source
        self.tolerance = tolerance

    @property
    def ok(self) -> bool:
        """False means: do not trust this alignment without looking at the video."""
        return self.samples >= 2 and self.residual_max <= self.tolerance

    def to_session(self, video_t: float) -> float:
        return video_t - self.offset

    def to_video(self, session_t: float) -> float:
        return session_t + self.offset

    def as_dict(self) -> dict:
        return dict(offset=self.offset, samples=self.samples, residualMax=self.residual_max,
                    residualMedian=self.residual_median, source=self.source,
                    tolerance=self.tolerance, ok=self.ok)

    def __repr__(self) -> str:
        return ('Alignment(offset=%.3f, n=%d, residual_max=%.3f, source=%r, ok=%s)'
                % (self.offset, self.samples, self.residual_max, self.source, self.ok))


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError('median of empty sequence')
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def fit_alignment(samples: Iterable[tuple[float, float]], tolerance: float = 1.5,
                  source: str = 'timer-ocr') -> Alignment:
    """Fit e = v - offset from (video_t, session_elapsed) pairs.

    The slope is FIXED at 1 rather than fitted. Both clocks are real time, so any fitted slope
    away from 1 would be OCR error or a stall being smeared across the whole session -- a
    two-parameter fit hides exactly the failure we most want to see. So: take the median offset
    (robust to a few misread frames) and report the residuals honestly.
    """
    pairs = [(float(v), float(e)) for v, e in samples]
    if not pairs:
        return Alignment(0.0, 0, float('inf'), float('inf'), source, tolerance)
    offsets = [v - e for v, e in pairs]
    offset = _median(offsets)
    residuals = [abs(o - offset) for o in offsets]
    return Alignment(offset, len(pairs), max(residuals), _median(residuals), source, tolerance)


def alignment_from_wallclock(video_started_at: str | datetime, session_start_wallclock: str,
                             startup_latency: float = 0.0) -> Alignment:
    """Fallback anchor: the recorder's filename timestamp against `session_start.wallClock`.

    Weaker than the timer, and the skeleton says so: the filename is written when the PowerShell
    script starts, not when ffmpeg's first frame lands, it has one-second granularity, and it is
    local time. Use it to sanity-check the OCR fit or when the header was cropped out of frame --
    not as the primary anchor. `startup_latency` is your measured ffmpeg warm-up, if you calibrate
    one.
    """
    started = video_started_at if isinstance(video_started_at, datetime) else parse_iso(video_started_at)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    session0 = parse_iso(session_start_wallclock)
    # Session start happened this many seconds after the first frame => that is the offset.
    offset = (session0 - started).total_seconds() - startup_latency
    return Alignment(offset, samples=1, residual_max=0.0, residual_median=0.0,
                     source='wallclock-filename', tolerance=3.0)


def find_stalls(samples: Iterable[tuple[float, float]], min_gap: float = 2.0) -> list[dict]:
    """Where did session time stand still while the video kept rolling?

    Returns one entry per detected plateau. A session with any of these needs a piecewise
    alignment (or, better, re-running the analysis on a session that was not left hidden) -- see
    the note on Alignment.
    """
    pairs = sorted(((float(v), float(e)) for v, e in samples), key=lambda p: p[0])
    out = []
    for (v0, e0), (v1, e1) in zip(pairs, pairs[1:]):
        dv, de = v1 - v0, e1 - e0
        if dv - de >= min_gap:
            out.append(dict(videoFrom=v0, videoTo=v1, sessionFrom=e0, sessionTo=e1,
                            lostSeconds=round(dv - de, 3)))
    return out


# ── decision windows ──────────────────────────────────────────────────────────────────────────
#
# A "window" is the span of a single operator decision, from the moment the interface offered it
# to the moment they committed. These are the spans worth reading a transcript against; the rest
# of a session is mostly silence and mouse movement.

WINDOW_SPECS = [
    # kind,        opener,                    closers (first match wins)
    ('strategic', 'strategic_modal_opened', ('strategic_choice', 'strategic_dismissed')),
    ('tactical', 'tactical_opened', ('tactical_confirmed',)),
    ('recovery', 'recovery_opened', ('failure_recovery', 'mission_abandoned')),
]

# Fields worth carrying into a decision card, per event type. Everything else stays in the log.
CARRY = {
    'strategic_modal_opened': ('missionCategory', 'strategiesPresented', 'activeMissions',
                               'currentPenaltyAccrued'),
    'strategic_choice': ('choiceType', 'wasAgentSuggestion', 'assetsChosen', 'latencyMs',
                         'editedFromStrategy', 'manualBeforeCardsLoaded'),
    'strategic_dismissed': (),
    'tactical_opened': ('strategyChosen', 'agentPlan', 'dronePool', 'unassignedTaskIds'),
    'tactical_confirmed': ('modifiedFromAgentPlan', 'suggestUsedCount', 'changedTaskIds',
                           'chainingUsed', 'latencyMs', 'agentPlan', 'finalPlan'),
    'recovery_opened': ('recoveryReason', 'failedDroneId', 'failedDroneType', 'affectedTaskIds',
                        'feasibleWithOnMissionDrones', 'tasksRemaining'),
    'failure_recovery': ('recoveryType', 'wasAgentSuggested', 'repairedTaskIds', 'latencyMs'),
    'mission_abandoned': ('abandonedReason', 'rewardCarriedOver', 'rewardLost'),
}


def event_time(ev: dict) -> Optional[float]:
    """Session-relative seconds for an event, from `elapsed` or `timestamp` (ms)."""
    if isinstance(ev.get('elapsed'), (int, float)):
        return float(ev['elapsed'])
    if isinstance(ev.get('timestamp'), (int, float)):
        return float(ev['timestamp']) / 1000.0
    return None


def _carry(ev: dict) -> dict:
    keys = CARRY.get(ev.get('type'), ())
    return {k: ev[k] for k in keys if k in ev}


def decision_windows(events: list[dict], pre_roll: float = 5.0, post_roll: float = 3.0,
                     session_end: Optional[float] = None) -> list[dict]:
    """Pair each decision opener with its closer and return the spans to read narration against.

    `pre_roll` catches the operator reacting to the panel appearing before they touch anything;
    `post_roll` catches the far more common case of them explaining the choice just AFTER
    clicking. Both are knobs -- expect to tune them once you have heard real sessions.

    An unclosed window (session ended mid-decision) is kept and clipped, flagged `closed: False`:
    those are often the most interesting ones and dropping them would bias the sample toward
    decisions people found easy.
    """
    evs = [e for e in events if isinstance(e, dict)]
    evs.sort(key=lambda e: (e.get('seq') if isinstance(e.get('seq'), int) else 0))
    if session_end is None:
        ends = [event_time(e) for e in evs if e.get('type') == 'session_ended']
        session_end = next((t for t in ends if t is not None), None)

    windows = []
    for kind, opener, closers in WINDOW_SPECS:
        used_closers: set[int] = set()
        for i, ev in enumerate(evs):
            if ev.get('type') != opener:
                continue
            t_open = event_time(ev)
            if t_open is None:
                continue
            mission = ev.get('missionId')
            close_ev, close_idx, t_close = None, None, None
            for j in range(i + 1, len(evs)):
                cand = evs[j]
                if cand.get('type') not in closers or cand.get('missionId') != mission:
                    continue
                if j in used_closers:
                    continue
                t = event_time(cand)
                if t is None or t < t_open:
                    continue
                close_ev, close_idx, t_close = cand, j, t
                break
            if close_idx is not None:
                used_closers.add(close_idx)

            end = t_close if t_close is not None else session_end
            if end is None:
                end = t_open
            w = dict(
                id='%s:%s:%d' % (kind, mission, int(round(t_open))),
                kind=kind, missionId=mission,
                openedAt=t_open, closedAt=t_close,
                closed=close_ev is not None,
                start=max(0.0, t_open - pre_roll),
                end=end + (post_roll if close_ev is not None else 0.0),
                durationSec=(t_close - t_open) if t_close is not None else None,
                openEvent=dict(type=opener, **_carry(ev)),
                closeEvent=(dict(type=close_ev['type'], **_carry(close_ev)) if close_ev else None),
            )
            windows.append(w)

    windows.sort(key=lambda w: w['openedAt'])
    return windows


# ── utterances ────────────────────────────────────────────────────────────────────────────────

def utterances_from_segments(segments: list[dict], alignment: Alignment,
                             merge_gap: float = 0.6) -> list[dict]:
    """Whisper segments (video time) -> utterances (session time), merging same-speaker runs.

    Whisper cuts on acoustics, not on meaning, so a single spoken thought routinely arrives as
    three segments. Merging adjacent same-speaker segments separated by less than `merge_gap`
    gives units that read like sentences, which is what a coder needs.
    """
    out: list[dict] = []
    for seg in segments:
        start, end = seg.get('start'), seg.get('end')
        if start is None or end is None:
            continue
        text = (seg.get('text') or '').strip()
        if not text:
            continue
        speaker = seg.get('speaker') or 'unknown'
        s, e = alignment.to_session(float(start)), alignment.to_session(float(end))
        if out and out[-1]['speaker'] == speaker and s - out[-1]['end'] <= merge_gap:
            prev = out[-1]
            prev['end'] = e
            prev['text'] = (prev['text'] + ' ' + text).strip()
            prev['words'].extend(_words(seg, alignment))
            prev['segments'] += 1
        else:
            out.append(dict(start=s, end=e, speaker=speaker, text=text,
                            words=_words(seg, alignment), segments=1))
    return out


def _words(seg: dict, alignment: Alignment) -> list[dict]:
    words = []
    for w in seg.get('words') or []:
        if w.get('start') is None or w.get('end') is None:
            continue
        words.append(dict(word=(w.get('word') or '').strip(),
                          start=alignment.to_session(float(w['start'])),
                          end=alignment.to_session(float(w['end'])),
                          probability=w.get('probability')))
    return words


def attach_utterances(windows: list[dict], utterances: list[dict],
                      min_overlap: float = 0.05) -> list[dict]:
    """Put each utterance in every window it overlaps.

    Overlap, not containment: a sentence that starts before the panel opens and finishes after is
    exactly the sentence you want. `min_overlap` drops the degenerate case of an utterance that
    merely touches a boundary. Windows can overlap each other (a recovery while a tactical plan is
    open), so an utterance may legitimately appear in two -- that is a real property of the task,
    not double counting, and `windowIds` on the utterance records it.
    """
    for w in windows:
        w['utterances'] = []
    for u in utterances:
        u['windowIds'] = []
        for w in windows:
            overlap = min(u['end'], w['end']) - max(u['start'], w['start'])
            if overlap > min_overlap:
                w['utterances'].append(u)
                u['windowIds'].append(w['id'])
    for w in windows:
        w['utteranceCount'] = len(w['utterances'])
        w['spokenSeconds'] = round(sum(u['end'] - u['start'] for u in w['utterances']), 2)
        w['wordCount'] = sum(len((u.get('text') or '').split()) for u in w['utterances'])
    return windows


# ── speech measures (cheap workload proxies) ──────────────────────────────────────────────────

DISFLUENCIES = ('um', 'uh', 'er', 'erm', 'hmm', 'mm', 'ah', 'eh')


def speech_measures(utterances: list[dict], span: float) -> dict:
    """Rate, pause share and disfluency density over a span of session time.

    These are proxies, not measurements: a pause is concentration or overload and the timing alone
    cannot tell you which. They are here because they cost nothing once word timings exist, and
    because you have a per-session NASA-TLX to validate them against.
    """
    if span <= 0:
        return dict(spanSec=0.0, words=0, wordsPerMin=None, pauseShare=None, disfluencyPer100=None)
    # Count from the text, not from the word-timing list: a merged utterance can carry timings for
    # only some of its segments (Whisper occasionally omits them), and counting those would
    # silently under-report exactly the busy stretches we care about.
    n_words = sum(len((u.get('text') or '').split()) for u in utterances)
    spoken = sum(u['end'] - u['start'] for u in utterances)
    words = [w for u in utterances for w in (u.get('words') or [])]
    disf = sum(1 for w in words
               if re.sub(r'[^a-z]', '', (w.get('word') or '').lower()) in DISFLUENCIES)
    return dict(
        spanSec=round(span, 2),
        words=n_words,
        wordsPerMin=round(n_words / span * 60.0, 1) if n_words else 0.0,
        pauseShare=round(max(0.0, 1.0 - spoken / span), 3),
        # Needs word timings to be meaningful; None means "not measurable here", not "none found".
        disfluencyPer100=(round(disf / len(words) * 100.0, 2) if words else None),
    )


# ── redaction ─────────────────────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b')
PHONE_RE = re.compile(r'\b(?:\+?\d[\d\s-]{7,}\d)\b')


def redact(text: str, names: Iterable[str] = (), placeholder: str = '[name]') -> str:
    """Blunt de-identification: named people, emails, phone numbers.

    Deliberately crude and deliberately explicit -- it is a first pass over a transcript a human
    still has to read, not a guarantee. Participants say their own name, yours, and occasionally a
    supervisor's; pass all of them in. Case-insensitive, whole-word.
    """
    out = text
    for name in sorted({n.strip() for n in names if n and n.strip()}, key=len, reverse=True):
        out = re.sub(r'\b%s\b' % re.escape(name), placeholder, out, flags=re.IGNORECASE)
    out = EMAIL_RE.sub('[email]', out)
    out = PHONE_RE.sub('[phone]', out)
    return out


def redact_utterances(utterances: list[dict], names: Iterable[str] = ()) -> list[dict]:
    for u in utterances:
        u['text'] = redact(u.get('text', ''), names)
        for w in u.get('words') or []:
            w['word'] = redact(w.get('word', ''), names)
    return utterances


# ── domain vocabulary ─────────────────────────────────────────────────────────────────────────

def glossary(max_drone_index: int = 11) -> list[str]:
    """Terms to bias the transcriber with.

    Whisper mangles `Lifter-7` into "lifter seven", "lift a seven" or "Lyfter 7" unless primed,
    and drone ids are precisely what links an utterance to a task. Mirrors the display names in
    `src/utils/missionGen.ts` (ASSET_TYPE_LABEL / droneLabel) -- if those change, change this.
    """
    terms = [
        'Strategic Assistant', 'Tactical Assistant', 'Aggressive', 'Conservative',
        'Suggest', 'Deploy', 'Reassign', 'Abort Mission', 'reserve', 'hub', 'loiter',
        'Recce', 'Recon', 'Supply Drop', 'Precision Supply Drop', 'Search and Service',
        'mission', 'task', 'drone', 'allocate', 'allocation', 'chain', 'lockout', 'penalty',
    ]
    for label in ('Fast', 'Lifter', 'Camera'):
        terms.append(label)
        terms.extend('%s-%d' % (label, i) for i in range(1, max_drone_index + 1))
    return terms


def whisper_prompt(extra: Iterable[str] = ()) -> str:
    """`initial_prompt` for Whisper: a plain sentence listing the vocabulary.

    Whisper conditions on this as if it were preceding speech, so it must read as prose, not as a
    word list with punctuation it will try to imitate.
    """
    terms = glossary() + list(extra)
    return ('A drone search-and-rescue command exercise. The speaker mentions ' +
            ', '.join(terms) + '.')
