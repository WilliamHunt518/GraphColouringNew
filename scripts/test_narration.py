#!/usr/bin/env python3
"""
Regression test for the narration pipeline's pure core.
Run: python scripts/test_narration.py

There is no video yet, and there does not need to be: everything that decides what a number MEANS
-- clock parsing, alignment, stall detection, decision windows, utterance overlap, redaction --
is stdlib-only and testable against synthetic data. The parts that need ffmpeg, Whisper and OpenCV
are thin adapters in narration_pipeline.py and are checked by running them on a real recording.

If a real session later disagrees with one of these assertions, the assertion is the thing to fix
-- and it should be updated here first, so the disagreement is recorded rather than argued about.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from narration_core import (  # noqa: E402
    Alignment, alignment_from_wallclock, attach_utterances, decision_windows, find_stalls,
    fit_alignment, glossary, parse_clock, redact, remaining_to_elapsed, speech_measures,
    utterances_from_segments, whisper_prompt,
)

failures = 0


def check(label, cond, detail=''):
    global failures
    print('%s  %s%s' % ('PASS' if cond else 'FAIL', label, ('  -- ' + str(detail)) if detail else ''))
    if not cond:
        failures += 1


def approx(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol


# ── 1. clock parsing: the OCR feed is noisy by nature ─────────────────────────────────────────
check('reads a normal countdown', approx(parse_clock('7:59'), 479))
check('reads a single-digit minute with padding', approx(parse_clock(' 0:07 '), 7))
check('tolerates a full stop for the colon (common OCR slip)', approx(parse_clock('7.59'), 479))
check('tolerates O read for zero', approx(parse_clock('O:07'), 7))
check('rejects a non-clock', parse_clock('Score: 0') is None)
check('rejects impossible seconds', parse_clock('7:75') is None)
check('rejects an empty read', parse_clock('') is None and parse_clock(None) is None)
check('remaining converts to elapsed against the session length',
      approx(remaining_to_elapsed(479, 480), 1))

# ── 2. alignment: fixed slope, honest residuals ────────────────────────────────────────────────
{
    # A clean session: the video started 12.4 s before the session did.
    'clean': None
}
clean = [(12.4 + e, e) for e in (0, 30, 60, 120, 300, 470)]
a = fit_alignment(clean)
check('recovers the offset from clean samples', approx(a.offset, 12.4, 1e-9), a)
check('clean fit reports no residual', approx(a.residual_max, 0.0, 1e-9))
check('clean fit is usable', a.ok)
check('maps video time to session time', approx(a.to_session(112.4), 100))
check('maps session time back to video time', approx(a.to_video(100), 112.4))

# One badly-read frame must not move the offset -- that is the whole point of the median.
noisy = clean + [(999.0, 5.0)]
b = fit_alignment(noisy)
check('a single misread frame does not shift the offset', approx(b.offset, 12.4, 1e-9), b)
check('but it is reported, not hidden', b.residual_max > 100 and not b.ok, b.residual_max)

check('an empty sample set is not silently trusted', not fit_alignment([]).ok)
check('a single sample is not enough to trust', not fit_alignment([(10.0, 0.0)]).ok)

# ── 3. stalls: session time standing still while the video rolls ───────────────────────────────
# MAX_TICK_GAP_MS pauses simulated time when the primary window is hidden. Video keeps rolling.
stalled = [(10, 0), (40, 30), (100, 40), (130, 70)]   # 60 s of video, 10 s of session, mid-run
st = find_stalls(stalled)
check('detects a stall', len(st) == 1, st)
check('measures how much session time was lost', st and approx(st[0]['lostSeconds'], 50.0), st)
check('a clean session has no stalls', find_stalls(clean) == [])

# The alignment fit must NOT quietly absorb a stall into the offset.
check('a stalled session fails the alignment check', not fit_alignment(stalled).ok)

# ── 4. wall-clock fallback ────────────────────────────────────────────────────────────────────
w = alignment_from_wallclock('2026-09-01T12:27:20Z', '2026-09-01T12:27:32.702Z')
check('wall-clock anchor gives the session start offset', approx(w.offset, 12.702, 1e-3), w)
check('wall-clock anchor is labelled as the weaker source', w.source == 'wallclock-filename')

# ── 5. decision windows ───────────────────────────────────────────────────────────────────────
EVENTS = [
    dict(seq=1, type='session_start', elapsed=0),
    dict(seq=2, type='strategic_modal_opened', missionId='M001', elapsed=20.0,
         strategiesPresented=[{'name': 'Aggressive'}, {'name': 'Conservative'}]),
    dict(seq=3, type='strategic_choice', missionId='M001', elapsed=44.4, choiceType='aggressive',
         wasAgentSuggestion=True, latencyMs=24400),
    dict(seq=4, type='tactical_opened', missionId='M001', elapsed=44.4, agentPlan=[{'taskId': 'T1'}]),
    dict(seq=5, type='tactical_confirmed', missionId='M001', elapsed=58.0,
         modifiedFromAgentPlan=True, suggestUsedCount=1),
    dict(seq=6, type='strategic_modal_opened', missionId='M002', elapsed=100.0),
    dict(seq=7, type='strategic_dismissed', missionId='M002', elapsed=104.0),
    dict(seq=8, type='recovery_opened', missionId='M001', elapsed=250.0,
         recoveryReason='drone_failure', failedDroneId='G01'),
    # never resolved -- session ends first
    dict(seq=9, type='session_ended', elapsed=480.0),
]
W = decision_windows(EVENTS, pre_roll=5.0, post_roll=3.0)
kinds = [(w['kind'], w['missionId']) for w in W]
check('finds every decision', len(W) == 4, kinds)
check('windows come out in time order', [w['openedAt'] for w in W] == sorted(w['openedAt'] for w in W))
strat = [w for w in W if w['kind'] == 'strategic' and w['missionId'] == 'M001'][0]
check('pre-roll extends the window backwards', approx(strat['start'], 15.0))
check('post-roll extends it forwards', approx(strat['end'], 47.4))
check('records the decision duration', approx(strat['durationSec'], 24.4))
check('carries the choice onto the window', strat['closeEvent']['choiceType'] == 'aggressive')
check('carries what was shown', len(strat['openEvent']['strategiesPresented']) == 2)
dismissed = [w for w in W if w['missionId'] == 'M002'][0]
check('a dismissal closes a strategic window', dismissed['closeEvent']['type'] == 'strategic_dismissed')
rec = [w for w in W if w['kind'] == 'recovery'][0]
check('an unresolved recovery is kept, not dropped', rec['closed'] is False)
check('and is clipped to the end of the session', approx(rec['end'], 480.0))

# A second mission's closer must not be stolen by the first mission's opener.
TWO = [
    dict(seq=1, type='strategic_modal_opened', missionId='M001', elapsed=10.0),
    dict(seq=2, type='strategic_modal_opened', missionId='M002', elapsed=12.0),
    dict(seq=3, type='strategic_choice', missionId='M002', elapsed=15.0, choiceType='manual'),
    dict(seq=4, type='strategic_choice', missionId='M001', elapsed=20.0, choiceType='conservative'),
]
TW = decision_windows(TWO, pre_roll=0, post_roll=0)
by_mission = {w['missionId']: w for w in TW}
check('interleaved decisions pair by mission, not by order',
      approx(by_mission['M001']['closedAt'], 20.0) and approx(by_mission['M002']['closedAt'], 15.0),
      [(w['missionId'], w['closedAt']) for w in TW])

# ── 6. utterances ─────────────────────────────────────────────────────────────────────────────
ALIGN = Alignment(offset=10.0, samples=5, residual_max=0.1, source='test')
SEGMENTS = [
    # video time -> session time is v - 10
    dict(start=28.0, end=29.5, text='Right, so it wants six drones.', speaker='P',
         words=[dict(start=28.0, end=28.4, word='Right', probability=0.9)]),
    dict(start=29.9, end=31.0, text='That seems like a lot.', speaker='P'),   # gap 0.4 -> merges
    dict(start=33.0, end=34.0, text='Take your time.', speaker='R'),          # other speaker
    dict(start=200.0, end=201.0, text='', speaker='P'),                       # empty -> dropped
]
U = utterances_from_segments(SEGMENTS, ALIGN, merge_gap=0.6)
check('drops empty segments and merges the rest into two utterances',
      len(U) == 2, [u['text'] for u in U])
check('merges a same-speaker run across a short gap',
      U[0]['text'] == 'Right, so it wants six drones. That seems like a lot.', U[0]['text'])
check('does not merge across speakers', U[1]['speaker'] == 'R')
check('converts segment times to session time', approx(U[0]['start'], 18.0) and approx(U[0]['end'], 21.0))
check('converts word times too', approx(U[0]['words'][0]['start'], 18.0))

WINDOWS = [dict(id='w1', start=15.0, end=22.0), dict(id='w2', start=21.5, end=30.0)]
attach_utterances(WINDOWS, U)
check('an utterance lands in the window it overlaps', WINDOWS[0]['utteranceCount'] == 1)
check('an utterance spanning two windows is counted in both',
      U[0]['windowIds'] == ['w1'] and U[1]['windowIds'] == ['w2'], [u['windowIds'] for u in U])
check('window word counts are filled in', WINDOWS[0]['wordCount'] == 11, WINDOWS[0]['wordCount'])

# Boundary case: an utterance that merely touches a window edge is not counted.
EDGE = [dict(start=10.0, end=20.0, speaker='P', text='x', words=[])]
EW = [dict(id='e', start=20.0, end=30.0)]
attach_utterances(EW, EDGE)
check('a zero-length touch does not count as being in the window', EW[0]['utteranceCount'] == 0)

# ── 7. speech measures ────────────────────────────────────────────────────────────────────────
M = speech_measures(U[:1], span=20.0)
check('counts words from the text, not from partial word timings', M['words'] == 11, M)
check('pause share is a fraction', 0.0 <= M['pauseShare'] <= 1.0, M['pauseShare'])
check('an empty span does not divide by zero', speech_measures([], 0.0)['wordsPerMin'] is None)
check('disfluency is None when there are no word timings to judge from',
      speech_measures([dict(start=0, end=1, speaker='P', text='hello there', words=[])],
                      1.0)['disfluencyPer100'] is None)

DIS = [dict(start=0, end=2, speaker='P', text='um so uh yes',
            words=[dict(start=0, end=0.2, word=w) for w in ('um', 'so', 'uh', 'yes')])]
check('counts disfluencies', approx(speech_measures(DIS, 2.0)['disfluencyPer100'], 50.0),
      speech_measures(DIS, 2.0))

# ── 8. redaction ──────────────────────────────────────────────────────────────────────────────
check('removes a named person', redact('Thanks George, done.', ['George']) == 'Thanks [name], done.')
check('is case-insensitive', redact('george said', ['George']) == '[name] said')
check('does not eat a word that merely contains the name',
      redact('Georgetown', ['George']) == 'Georgetown')
check('removes an email', '[email]' in redact('mail me at a.b@c.co.uk', []))
check('leaves ordinary speech alone',
      redact('I trust the tactical one more.', ['George']) == 'I trust the tactical one more.')

# ── 9. vocabulary ─────────────────────────────────────────────────────────────────────────────
G = glossary()
check('glossary includes drone ids that Whisper mangles', 'Lifter-7' in G and 'Camera-11' in G)
check('glossary includes both strategy card names', 'Aggressive' in G and 'Conservative' in G)
P = whisper_prompt()
check('the prompt reads as prose, not a word list', P.endswith('.') and P.count(':') == 0)
check('the prompt mentions the vocabulary', 'Lifter-7' in P)

print('\n' + ('ALL PASS' if failures == 0 else '%d FAILED' % failures))
sys.exit(0 if failures == 0 else 1)
