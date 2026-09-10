#!/usr/bin/env python3
"""
Turn a session recording into narration joined to the event log.

    python scripts/narration_pipeline.py probe      --video V --out DIR
    python scripts/narration_pipeline.py audio      --video V
    python scripts/narration_pipeline.py transcribe --audio A
    python scripts/narration_pipeline.py align      --video V --log L --session N
    python scripts/narration_pipeline.py join       --log L --session N
    python scripts/narration_pipeline.py all        --video V --log L --session N

This is a SKELETON. The logic that decides what numbers mean lives in `narration_core.py` and is
unit-tested (`scripts/test_narration.py`); this file is the thin adapter over ffmpeg, Whisper and
OpenCV/Tesseract, and every default in it -- the timer ROI above all -- is a guess until it has
been run against a real recording. `docs/NARRATION.md` is the tuning guide.

Nothing here is imported at module load: the heavy dependencies are imported inside the step that
needs them, so `--help`, `probe` and `join` work on a machine with nothing installed.

Outputs land in logs/narration/<participant>_s<session>/ and are NOT committed -- audio and
transcripts are identifiable data. See .gitignore.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / 'scripts'))

from narration_core import (  # noqa: E402
    Alignment, alignment_from_wallclock, attach_utterances, decision_windows, find_stalls,
    fit_alignment, parse_clock, redact_utterances, remaining_to_elapsed, speech_measures,
    utterances_from_segments, whisper_prompt,
)

# The recorder writes %USERPROFILE%\Videos\sar_demo_<yyyyMMdd>_<HHmmss>.mp4 (record-screens.ps1:96).
FILENAME_TS = re.compile(r'sar_demo_(\d{8})_(\d{6})')

# Fraction-of-frame box around the session countdown in the primary window's header.
# A GUESS. The header sits top-left of the primary monitor, but the recording is all monitors side
# by side, so the real box depends on monitor count, order and resolution. Run `probe` first.
DEFAULT_TIMER_ROI = (0.35, 0.0, 0.10, 0.045)


def die(msg: str, hint: str = '') -> None:
    print('error: ' + msg, file=sys.stderr)
    if hint:
        print('       ' + hint, file=sys.stderr)
    raise SystemExit(2)


def need_ffmpeg() -> str:
    exe = shutil.which('ffmpeg')
    if not exe:
        die('ffmpeg is not on PATH.', 'winget install Gyan.FFmpeg, then open a NEW terminal.')
    return exe


def out_dir(args) -> Path:
    d = Path(args.out) if args.out else BASE / 'logs' / 'narration' / (
        '%s_s%d' % (args.participant or 'unknown', args.session or 1))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_session(log_path: str, session_no: int) -> tuple[list, dict]:
    """Return (events, session_start) for one session of a study export."""
    d = json.loads(Path(log_path).read_text(encoding='utf-8'))
    sessions = d.get('sessions') or []
    if not 1 <= session_no <= len(sessions):
        die('session %d not in %s (it has %d)' % (session_no, log_path, len(sessions)))
    raw = sessions[session_no - 1]
    events = list(raw.values()) if isinstance(raw, dict) else list(raw)
    events = [e for e in events if isinstance(e, dict)]
    start = next((e for e in events if e.get('type') == 'session_start'), None)
    if not start:
        die('session %d has no session_start event' % session_no)
    return events, start


# ── step: probe ───────────────────────────────────────────────────────────────────────────────

def cmd_probe(args) -> None:
    """Dump a few frames so you can find the timer and measure its box.

    Do this once per recording rig. Open the PNGs, note the pixel box around the countdown, divide
    by the frame size, and pass the result to `align --roi`.
    """
    ff = need_ffmpeg()
    d = out_dir(args)
    for t in (args.at or [5, 60, 240]):
        dest = d / ('probe_%04d.png' % int(t))
        subprocess.run([ff, '-y', '-loglevel', 'error', '-ss', str(t), '-i', args.video,
                        '-frames:v', '1', str(dest)], check=True)
        print('wrote %s' % dest)
    print('\nOpen those, find the countdown (m:ss) in the primary window header, and note its box.')
    print('Then:  --roi X,Y,W,H   as fractions of the frame, e.g. 0.35,0.0,0.10,0.045')


# ── step: audio ───────────────────────────────────────────────────────────────────────────────

def cmd_audio(args) -> Path:
    """Extract 16 kHz mono WAV -- what every Whisper build wants, and ~100x smaller than the MP4."""
    ff = need_ffmpeg()
    d = out_dir(args)
    dest = d / 'audio.wav'
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', args.video,
                    '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(dest)], check=True)
    print('wrote %s (%.1f MB)' % (dest, dest.stat().st_size / 1e6))
    return dest


# ── step: transcribe ──────────────────────────────────────────────────────────────────────────

def cmd_transcribe(args) -> Path:
    """faster-whisper with word timestamps and a domain prompt.

    Word timestamps are not optional here: without them an utterance cannot be placed inside a
    decision window with any precision, and the pause/rate measures have nothing to work from.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        die('faster-whisper is not installed.',
            'pip install faster-whisper   (CPU is fine; add a CUDA torch build if you have one)')

    d = out_dir(args)
    audio = Path(args.audio) if args.audio else d / 'audio.wav'
    if not audio.exists():
        die('no audio at %s' % audio, 'run the `audio` step first')

    print('loading %s on %s (%s)…' % (args.model, args.device, args.compute_type))
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments, info = model.transcribe(
        str(audio),
        language=args.language,
        word_timestamps=True,
        initial_prompt=whisper_prompt(),
        vad_filter=True,                      # long silences are the norm; VAD keeps them out
        vad_parameters=dict(min_silence_duration_ms=700),
        beam_size=args.beam_size,
    )
    out = []
    for s in segments:
        out.append(dict(
            start=s.start, end=s.end, text=s.text,
            words=[dict(start=w.start, end=w.end, word=w.word, probability=w.probability)
                   for w in (s.words or [])],
            avgLogprob=getattr(s, 'avg_logprob', None),
            noSpeechProb=getattr(s, 'no_speech_prob', None),
        ))
        print('\r  %d segments, to %.0fs' % (len(out), s.end), end='', flush=True)
    print()

    if args.diarize:
        out = _diarize(out, audio, args)

    dest = d / 'transcript.raw.json'
    dest.write_text(json.dumps(dict(
        model=args.model, language=info.language, languageProbability=info.language_probability,
        durationSec=info.duration, diarized=bool(args.diarize), segments=out,
    ), indent=1), encoding='utf-8')
    print('wrote %s (%d segments)' % (dest, len(out)))
    return dest


def _diarize(segments: list, audio: Path, args) -> list:
    """Label segments with a speaker.

    This matters more than it looks: the researcher is in the room and talking, and a researcher
    prompt can CAUSE an utterance. Keep both speakers -- code only the participant, but keep the
    prompts as context, or you will read answers as spontaneous thoughts.
    """
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        print('warning: pyannote.audio not installed; leaving every segment speaker "unknown"',
              file=sys.stderr)
        for s in segments:
            s['speaker'] = 'unknown'
        return segments

    pipe = Pipeline.from_pretrained('pyannote/speaker-diarization-3.1',
                                    use_auth_token=args.hf_token)
    turns = [(t.start, t.end, spk)
             for t, _, spk in pipe(str(audio), num_speakers=args.speakers).itertracks(yield_label=True)]
    for s in segments:
        mid = (s['start'] + s['end']) / 2.0
        s['speaker'] = next((spk for a, b, spk in turns if a <= mid <= b), 'unknown')
    return segments


# ── step: align ───────────────────────────────────────────────────────────────────────────────

def cmd_align(args) -> Path:
    """Read the on-screen countdown at intervals and fit video time -> session time.

    Why OCR the timer rather than trust the filename: the filename is the moment the PowerShell
    script started (not ffmpeg's first frame), to the second, in local time -- and, decisively, it
    cannot see a stall. `MAX_TICK_GAP_MS` pauses simulated time when the primary window is hidden,
    so wall-clock alignment drifts in exactly the sessions where something odd happened. The
    countdown is ground truth for the axis the logs use.
    """
    d = out_dir(args)
    events, start = load_session(args.log, args.session)
    duration = float(start.get('sessionDuration') or 480)

    samples, reads = [], []
    if not args.no_ocr:
        samples, reads = _ocr_timer(args, duration)

    if samples:
        align = fit_alignment(samples, tolerance=args.tolerance)
    elif args.video and FILENAME_TS.search(Path(args.video).name):
        m = FILENAME_TS.search(Path(args.video).name)
        local = datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S').astimezone()
        align = alignment_from_wallclock(local, start['wallClock'], args.startup_latency)
        print('warning: no usable timer reads; fell back to the filename anchor (weaker)',
              file=sys.stderr)
    else:
        die('could not align: no timer reads and no sar_demo_<ts> filename to fall back on.',
            'run `probe` and pass a corrected --roi')

    stalls = find_stalls(samples) if samples else []
    payload = dict(alignment=align.as_dict(), sessionDuration=duration,
                   sessionStartWallClock=start.get('wallClock'),
                   roi=list(args.roi), reads=reads, stalls=stalls)
    dest = d / 'alignment.json'
    dest.write_text(json.dumps(payload, indent=1), encoding='utf-8')

    print('%s' % align)
    if stalls:
        print('WARNING: %d stall(s); simulated time paused while the video kept rolling:' % len(stalls))
        for s in stalls:
            print('  video %.0f-%.0fs lost %.1fs of session time' %
                  (s['videoFrom'], s['videoTo'], s['lostSeconds']))
        print('  A single offset is wrong across a stall. Split the session or re-run alignment')
        print('  separately on each side before trusting utterance placement after the first one.')
    if not align.ok:
        print('WARNING: alignment did not pass its own check -- eyeball the video before using it.')
    print('wrote %s' % dest)
    return dest


def _ocr_timer(args, duration: float):
    """Sample frames and OCR the countdown box. Returns (samples, per-read log)."""
    try:
        import cv2
        import pytesseract
    except ImportError:
        die('opencv-python and pytesseract are needed for timer OCR.',
            'pip install opencv-python pytesseract  +  winget install UB-Mannheim.TesseractOCR\n'
            '       (or pass --no-ocr to fall back to the filename anchor)')

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        die('could not open %s' % args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    length = total / fps if fps else 0
    x, y, w, h = args.roi

    samples, reads = [], []
    step = args.every
    t = args.skip
    while t < max(length - 1, 0):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok:
            break
        H, W = frame.shape[:2]
        crop = frame[int(y * H):int((y + h) * H), int(x * W):int((x + w) * W)]
        if crop.size:
            grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            grey = cv2.resize(grey, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            # The header is light text on a dark bar; Tesseract wants the opposite.
            _, grey = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            txt = pytesseract.image_to_string(
                grey, config='--psm 7 -c tessedit_char_whitelist=0123456789:.')
            remaining = parse_clock(txt)
            reads.append(dict(videoT=round(t, 2), raw=txt.strip(), remaining=remaining))
            if remaining is not None and 0 <= remaining <= duration:
                samples.append((t, remaining_to_elapsed(remaining, duration)))
        t += step
    cap.release()
    print('OCR: %d/%d frames gave a usable clock' % (len(samples), len(reads)))
    if reads and not samples:
        print('  every read failed -- the ROI is almost certainly wrong. Sample raw reads: %s'
              % [r['raw'] for r in reads[:5]], file=sys.stderr)
    return samples, reads


# ── step: speakerid ───────────────────────────────────────────────────────────────────────────

def cmd_speakerid(args) -> None:
    """Label each transcript segment 'researcher' or 'participant' by voice similarity to a
    reference clip of the researcher, using resemblyzer -- no HuggingFace token needed (unlike
    --diarize/pyannote above), because the researcher is always the same one person across every
    session, so a single short reference clip is reusable for every participant.

    Rewrites transcript.raw.json's segments in place with a 'speaker' field; `join` already
    respects that field when merging into utterances, so nothing downstream needs to change.
    Run BEFORE `join` (or re-run it after -- `join` just re-reads whatever is on disk).

    Why not real librosa: it needs numba, which is broken in this machine's base environment
    against the numpy also installed there, and conda-installed so pip can't fix it. See
    `_librosa_shim.py` and docs/NARRATION.md "Speaker identification".
    """
    sys.path.insert(0, str(BASE / 'scripts'))
    import _librosa_shim
    _librosa_shim.install()
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
    except ImportError:
        die('resemblyzer is not installed.', 'pip install resemblyzer webrtcvad soundfile audioread')
    try:
        import soundfile as sf
    except ImportError:
        die('soundfile is not installed.', 'pip install soundfile')
    import numpy as np

    d = out_dir(args)
    tr_path = Path(args.transcript) if args.transcript else d / 'transcript.raw.json'
    if not tr_path.exists():
        die('no transcript at %s' % tr_path, 'run the `transcribe` step first')
    blob = json.loads(tr_path.read_text(encoding='utf-8'))
    segments = blob.get('segments', [])

    audio_path = Path(args.audio) if args.audio else d / 'audio.wav'
    if not audio_path.exists():
        die('no audio at %s' % audio_path, 'run the `audio` step first')
    full_wav, sr = sf.read(str(audio_path), dtype='float32', always_2d=False)
    if full_wav.ndim > 1:
        full_wav = full_wav.mean(axis=1)

    print('loading voice encoder...')
    enc = VoiceEncoder('cpu')
    ref_wav = preprocess_wav(args.ref)
    ref_emb = enc.embed_utterance(ref_wav)

    def cosine(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    counts = {'researcher': 0, 'participant': 0, 'unknown': 0}
    for s in segments:
        start, end = s.get('start'), s.get('end')
        if start is None or end is None:
            s['speaker'] = 'unknown'
            counts['unknown'] += 1
            continue
        clip = full_wav[max(0, int(start * sr)):int(end * sr)]
        if len(clip) < sr * 0.3:            # too short for a usable embedding
            s['speaker'] = 'unknown'
            counts['unknown'] += 1
            continue
        w = preprocess_wav(clip, source_sr=sr)
        if len(w) < sr * 0.2:               # VAD trimmed it to near-nothing
            s['speaker'] = 'unknown'
            counts['unknown'] += 1
            continue
        sim = cosine(ref_emb, enc.embed_utterance(w))
        s['speaker'] = 'researcher' if sim >= args.threshold else 'participant'
        s['speakerSim'] = round(sim, 3)
        counts[s['speaker']] += 1

    tr_path.write_text(json.dumps(blob, indent=1), encoding='utf-8')
    print('wrote %s' % tr_path)
    print('%d researcher, %d participant, %d unknown (of %d segments), threshold=%.2f'
          % (counts['researcher'], counts['participant'], counts['unknown'], len(segments), args.threshold))
    print('This is a coarse binary voice-similarity classifier, not validated diarization -- spot-check')
    print('a few labels against the video before trusting it. Re-run `join` to pick up the labels.')


# ── step: join ────────────────────────────────────────────────────────────────────────────────

def cmd_join(args) -> Path:
    """Put the transcript on the session clock and hang it off each decision."""
    d = out_dir(args)
    events, start = load_session(args.log, args.session)

    ali_path = Path(args.alignment) if args.alignment else d / 'alignment.json'
    if ali_path.exists():
        blob = json.loads(ali_path.read_text(encoding='utf-8'))['alignment']
        align = Alignment(blob['offset'], blob['samples'], blob['residualMax'],
                          blob['residualMedian'], blob['source'], blob['tolerance'])
    else:
        print('warning: no alignment.json; assuming video and session start together (offset 0)',
              file=sys.stderr)
        align = Alignment(0.0, 0, 0.0, 0.0, 'assumed-zero')

    tr_path = Path(args.transcript) if args.transcript else d / 'transcript.raw.json'
    segments = []
    if tr_path.exists():
        segments = json.loads(tr_path.read_text(encoding='utf-8')).get('segments', [])
    else:
        print('warning: no transcript at %s; emitting windows with no narration' % tr_path,
              file=sys.stderr)

    utterances = utterances_from_segments(segments, align, merge_gap=args.merge_gap)
    if args.redact:
        utterances = redact_utterances(utterances, args.redact)

    windows = decision_windows(events, pre_roll=args.pre_roll, post_roll=args.post_roll)
    attach_utterances(windows, utterances)
    for w in windows:
        w['speech'] = speech_measures(w['utterances'], w['end'] - w['start'])

    (d / 'utterances.jsonl').write_text(
        '\n'.join(json.dumps(u) for u in utterances) + ('\n' if utterances else ''),
        encoding='utf-8')
    dest = d / 'windows.json'
    dest.write_text(json.dumps(dict(
        participantId=start.get('participantId') or args.participant,
        sessionNumber=start.get('sessionNumber'), complexity=start.get('complexity'),
        appVersion=start.get('appVersion'), alignment=align.as_dict(),
        preRoll=args.pre_roll, postRoll=args.post_roll,
        windows=windows,
    ), indent=1), encoding='utf-8')

    spoken = sum(w['utteranceCount'] for w in windows)
    silent = [w['id'] for w in windows if w['utteranceCount'] == 0]
    print('wrote %s' % (d / 'utterances.jsonl'))
    print('wrote %s' % dest)
    print('%d decisions, %d utterances attached, %d decisions with no narration'
          % (len(windows), spoken, len(silent)))
    if silent and len(silent) > len(windows) / 2:
        print('  More than half the decisions are silent. Either the participant went quiet, or')
        print('  the alignment is off -- check alignment.json before reading anything into this.')
    return dest


def cmd_all(args) -> None:
    cmd_audio(args)
    args.audio = None
    cmd_transcribe(args)
    cmd_align(args)
    cmd_join(args)


# ── step: clips ───────────────────────────────────────────────────────────────────────────────

def safe_window_id(window_id: str) -> str:
    """windowId is 'kind:missionId:seconds' -- ':' is illegal in a Windows filename."""
    return window_id.replace(':', '_')


def _load_codes(narration_dir: Path) -> dict:
    path = narration_dir / 'codes.json'
    if not path.exists():
        return {}
    d = json.loads(path.read_text(encoding='utf-8'))
    return {c['windowId']: c for c in d.get('codings', [])}


_WORD_RE = re.compile(r"[^a-z0-9' ]")


def _quote_span(utterances: list[dict], quote: str) -> tuple[float, float] | None:
    """Best-effort (start, end) session-time span of `quote`'s words inside this window's
    attached utterances, using word-level timestamps -- or None if nothing matches confidently.

    A curated quote (codes.json) is a hand-trimmed excerpt of what was actually said, sometimes
    spliced from the tail of one utterance and the head of the next (Whisper's segment cuts don't
    know or care where a decision boundary is), and sometimes from an utterance that overlaps
    several decision windows (a fast-talking multitasking burst -- see docs/NARRATION.md
    "Tuning"). The window's own openedAt/closedAt is the UI action; this is the speech act.
    `clips` unions both so a card's clip always contains the words on the card, not just
    whichever window nominally owns the timestamp.

    One `find_longest_match` over the WHOLE flat transcript (not a per-utterance or sliding-window
    score) is what makes this robust to a quote spanning an utterance boundary: a symmetric
    similarity ratio between a short quote and one candidate utterance's full (much longer) text
    is a bad metric regardless of whether the quote is actually there, since ratio is penalised by
    the length mismatch either way. Coverage of the single best contiguous verbatim run is not.
    """
    words = [(_WORD_RE.sub('', (w.get('word') or '').lower()), w['start'], w['end'])
             for u in utterances for w in (u.get('words') or [])
             if w.get('start') is not None and _WORD_RE.sub('', (w.get('word') or '').lower())]
    q_tokens = [_WORD_RE.sub('', t.lower()) for t in quote.split()]
    q_tokens = [t for t in q_tokens if t]
    if not words or not q_tokens:
        return None

    flat = [w[0] for w in words]
    flat_joined = ' '.join(flat)
    q_joined = ' '.join(q_tokens)
    match = difflib.SequenceMatcher(None, flat_joined, q_joined, autojunk=False).find_longest_match(
        0, len(flat_joined), 0, len(q_joined))
    if match.size < 0.4 * len(q_joined):
        return None   # even the single best run barely overlaps the quote -- don't guess

    # Map the character offset back to a word index, then take a generous window of words around
    # it -- generous because the character->word mapping only needs to land close, not exactly.
    pos, anchor = 0, 0
    for i, w in enumerate(flat):
        if pos <= match.a < pos + len(w):
            anchor = i
            break
        pos += len(w) + 1   # +1 for the joining space
    lo = max(0, anchor - 2)
    hi = min(len(words), lo + len(q_tokens) + 4)
    return words[lo][1], words[hi - 1][2]


def cmd_clips(args) -> None:
    """Cut a short mp4 (screen + mic) for each decision window, straight from the source video.

    The clip's span is the UNION of the window's own [openedAt, closedAt] (the UI action) and,
    when codes.json has a coded quote for this window, that quote's own word-level span (the
    speech act) -- so a card's embedded clip always contains what its quote says, even when that
    quote was actually spoken nearer a neighbouring decision (the shared-burst case; see
    docs/NARRATION.md). `--pad` adds context at both ends; `--max-duration` only ever shrinks that
    padding -- it never truncates the decision's own span, so a long recovery still plays in full
    rather than silently cutting off before its own close event.

    Needs `align` to have already produced alignment.json; refuses to guess offset 0, since a
    wrong clip is worse than no clip.
    """
    d = out_dir(args)
    win_path = d / 'windows.json'
    if not win_path.exists():
        die('no windows.json at %s' % win_path, 'run the `join` step first')
    data = json.loads(win_path.read_text(encoding='utf-8'))
    blob = data.get('alignment')
    if not blob:
        die('windows.json has no alignment recorded')
    align = Alignment(blob['offset'], blob['samples'], blob['residualMax'],
                      blob['residualMedian'], blob['source'], blob['tolerance'])
    if not align.ok:
        print('warning: alignment did not pass its own check -- clips may be off; eyeball one '
              'before trusting the rest', file=sys.stderr)
    codes = _load_codes(d)

    windows = data['windows']
    if args.window_id:
        windows = [w for w in windows if w['id'] == args.window_id]
        if not windows:
            die('no window with id %r in %s' % (args.window_id, win_path))

    ff = need_ffmpeg()
    out_clips = d / 'clips'
    out_clips.mkdir(parents=True, exist_ok=True)
    written = []
    for w in windows:
        open_t, close_t = w.get('openedAt'), w.get('closedAt')
        core_start = open_t if open_t is not None else w['start']
        core_end = close_t if close_t is not None else w['end']

        coding = codes.get(w['id'])
        if coding and coding.get('quote'):
            qspan = _quote_span(w.get('utterances', []), coding['quote'])
            if qspan:
                core_start, core_end = min(core_start, qspan[0]), max(core_end, qspan[1])

        pad = args.pad
        core_len = core_end - core_start
        if core_len + 2 * pad > args.max_duration:
            pad = max(0.0, (args.max_duration - core_len) / 2.0)
            if core_len > args.max_duration:
                print('warning: %s is %.1fs, longer than --max-duration %.1fs -- showing it in '
                      'full anyway (raise --max-duration to also restore padding)'
                      % (w['id'], core_len, args.max_duration), file=sys.stderr)
        span_start = max(0.0, core_start - pad)
        span_end = core_end + pad
        v_start, v_end = align.to_video(span_start), align.to_video(span_end)
        dest = out_clips / (safe_window_id(w['id']) + '.mp4')
        subprocess.run([
            ff, '-y', '-loglevel', 'error', '-ss', str(v_start), '-i', args.video,
            '-t', str(v_end - v_start),
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
            '-c:a', 'aac', '-movflags', '+faststart', str(dest),
        ], check=True)
        written.append((w['id'], dest, v_end - v_start))
        print('wrote %s  (%.1fs, video %.1f-%.1fs)' % (dest.relative_to(BASE), v_end - v_start, v_start, v_end))
    print('%d clip(s) in %s' % (len(written), out_clips.relative_to(BASE)))


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────

def roi_type(s: str):
    parts = [float(x) for x in s.split(',')]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError('need X,Y,W,H as fractions of the frame')
    return tuple(parts)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--participant'), p.add_argument('--session', type=int, default=1)
    p.add_argument('--out', help='output directory (default logs/narration/<pid>_s<n>/)')
    sub = p.add_subparsers(dest='cmd', required=True)

    def common_video(sp):
        sp.add_argument('--video', required=True)

    sp = sub.add_parser('probe', help='dump frames so you can find the timer box')
    common_video(sp)
    sp.add_argument('--at', type=float, nargs='*', help='seconds to sample (default 5 60 240)')
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser('audio', help='extract 16 kHz mono wav')
    common_video(sp)
    sp.set_defaults(func=cmd_audio)

    sp = sub.add_parser('transcribe', help='faster-whisper with word timestamps')
    sp.add_argument('--audio')
    sp.add_argument('--model', default='large-v3',
                    help='large-v3 | distil-large-v3 | medium (default large-v3)')
    sp.add_argument('--device', default='auto', help='auto | cpu | cuda')
    sp.add_argument('--compute-type', default='auto', help='auto | int8 | float16')
    sp.add_argument('--language', default='en')
    sp.add_argument('--beam-size', type=int, default=5)
    sp.add_argument('--diarize', action='store_true', help='label participant vs researcher')
    sp.add_argument('--speakers', type=int, default=2)
    sp.add_argument('--hf-token', help='HuggingFace token for the pyannote model')
    sp.set_defaults(func=cmd_transcribe)

    sp = sub.add_parser('align', help='fit video time -> session time from the on-screen timer')
    common_video(sp)
    sp.add_argument('--log', required=True, help='the study export JSON')
    sp.add_argument('--roi', type=roi_type, default=DEFAULT_TIMER_ROI,
                    help='timer box as X,Y,W,H fractions (run `probe` to find it)')
    sp.add_argument('--every', type=float, default=20.0, help='sample interval, seconds')
    sp.add_argument('--skip', type=float, default=2.0, help='skip this much at the start')
    sp.add_argument('--tolerance', type=float, default=1.5, help='max residual to call it aligned')
    sp.add_argument('--no-ocr', action='store_true', help='use the filename anchor instead')
    sp.add_argument('--startup-latency', type=float, default=0.0,
                    help='measured ffmpeg warm-up, for the filename anchor')
    sp.set_defaults(func=cmd_align)

    sp = sub.add_parser('speakerid', help='label segments researcher/participant by voice similarity (no HF token)')
    sp.add_argument('--ref', required=True,
                    help='wav clip of only the researcher talking (soundfile-readable -- if you '
                         'only have an mp4, extract audio first: ffmpeg -i clip.mp4 -vn -ac 1 '
                         '-ar 16000 ref.wav)')
    sp.add_argument('--audio'), sp.add_argument('--transcript')
    sp.add_argument('--threshold', type=float, default=0.62)
    sp.set_defaults(func=cmd_speakerid)

    sp = sub.add_parser('join', help='attach narration to each decision')
    sp.add_argument('--log', required=True)
    sp.add_argument('--transcript'), sp.add_argument('--alignment')
    sp.add_argument('--pre-roll', type=float, default=5.0)
    sp.add_argument('--post-roll', type=float, default=3.0)
    sp.add_argument('--merge-gap', type=float, default=0.6)
    sp.add_argument('--redact', nargs='*', default=[], help='names to remove from the transcript')
    sp.set_defaults(func=cmd_join)

    sp = sub.add_parser('clips', help='cut a short mp4 per decision window, straight from the source video')
    common_video(sp)
    sp.add_argument('--window-id', help='cut just this one window (default: every window)')
    sp.add_argument('--pad', type=float, default=2.0, help='seconds of context before/after the decision')
    sp.add_argument('--max-duration', type=float, default=25.0, help='hard cap per clip, seconds')
    sp.set_defaults(func=cmd_clips)

    sp = sub.add_parser('all', help='audio -> transcribe -> align -> join')
    common_video(sp)
    sp.add_argument('--log', required=True)
    sp.add_argument('--roi', type=roi_type, default=DEFAULT_TIMER_ROI)
    sp.add_argument('--model', default='large-v3')
    sp.add_argument('--device', default='auto'), sp.add_argument('--compute-type', default='auto')
    sp.add_argument('--language', default='en'), sp.add_argument('--beam-size', type=int, default=5)
    sp.add_argument('--diarize', action='store_true'), sp.add_argument('--speakers', type=int, default=2)
    sp.add_argument('--hf-token')
    sp.add_argument('--every', type=float, default=20.0), sp.add_argument('--skip', type=float, default=2.0)
    sp.add_argument('--tolerance', type=float, default=1.5)
    sp.add_argument('--no-ocr', action='store_true')
    sp.add_argument('--startup-latency', type=float, default=0.0)
    sp.add_argument('--pre-roll', type=float, default=5.0), sp.add_argument('--post-roll', type=float, default=3.0)
    sp.add_argument('--merge-gap', type=float, default=0.6)
    sp.add_argument('--redact', nargs='*', default=[])
    sp.add_argument('--transcript'), sp.add_argument('--alignment')
    sp.set_defaults(func=cmd_all)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
