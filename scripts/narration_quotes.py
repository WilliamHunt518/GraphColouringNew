"""Quote bank over the debriefs: assemble the source text, then render what was coded from it.

Two commands, and the split between them is the point:

    assemble   deterministic. Gathers each participant's debrief into one file to read.
    render     deterministic. Turns hand-authored quotes.json files into cross-linked output.

The judgement in the middle -- reading a debrief and deciding which sentences are worth keeping
and what they are about -- is not automated and is not pretending to be. It is the same shape as
the P05 `codes.json` pass: a human or an LLM reads the assembled text and writes `quotes.json`.
Keeping that step visible is what makes the result auditable; a script that "extracted themes"
would just be hiding the same judgement behind a function call.

    python scripts/narration_quotes.py assemble --participants P36 P10 P21
    python scripts/narration_quotes.py render

## Where a debrief lives

Not always in the `interview` phase. For four participants the recording stopped at `done` and the
debrief happened while the final survey was still on screen, so it sits in `survey2` -- which for
them runs 6-9 minutes against a usual 1-2. `debrief_segments()` picks up both, by duration and
word count rather than by a hardcoded participant list, so a re-segment cannot silently drop one.
Four early participants have no debrief audio at all; theirs is in `Results/Interviews/<pid>.docx`
and this reports them rather than pretending they are silent.

## Themes

Grounded in the questions actually asked, recovered from the recordings rather than invented --
"how did you find that", "what about the two different agents", "what about the two scenarios",
"did that develop at all", "how do you feel about AI tools generally". THEMES below is that guide
plus the topics participants raised unprompted often enough to need a home.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NARRATION = ROOT / 'Results' / 'Narration'
INTERVIEWS = ROOT / 'Results' / 'Interviews'
QUOTES_OUT = NARRATION / '_quotes'

# A debrief that landed in survey2 rather than interview: the survey phase normally takes a
# minute or two, so this is a wide margin, not a fine judgement.
DEBRIEF_MIN_SECONDS = 240.0
DEBRIEF_MIN_WORDS = 300

THEMES: dict[str, str] = {
    'overall_experience': 'How they found the task overall; enjoyment, difficulty, engagement.',
    'agent_comparison': 'Strategic vs Tactical Assistant — which was more useful or more trusted, '
                        'and on what grounds. The core question.',
    'scenario_comparison': 'The two scenarios against each other; which felt harder or busier.',
    'trust_trajectory': 'Whether reliance changed over the session or between the two.',
    'verification': 'Checking, spot-checking, or consciously not checking the advice.',
    'manual_override': 'Why they built an allocation or plan by hand instead of taking a card.',
    'interface_legibility': 'Display, wording or information they could not read or find. Matters '
                            'because low reliance and a rational response to an unreadable display '
                            'look identical in the logs (STUDY_BUILD.md § 14).',
    'general_ai_disposition': 'Views on AI tools outside this task; where they would and would not '
                              'delegate.',
    'real_world_transfer': 'Whether something like this would work in practice, and what is missing.',
    'design_suggestions': 'Concrete changes they asked for.',
}

# Optional, per quote. Left free-form-ish on purpose: a controlled vocabulary invented before
# reading the transcripts would be the tail wagging the dog.
STANCES = ['prefers_strategic', 'prefers_tactical', 'prefers_neither', 'trusts_both',
           'distrusts_both', 'conditional', 'not_applicable']


# ── assemble ──────────────────────────────────────────────────────────────────────────────────

def segments_for(pid: str) -> dict | None:
    path = NARRATION / ('%s_s1' % pid) / 'segments.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def debrief_segments(seg: dict) -> list[dict]:
    """Which phases of this sitting hold debrief material.

    `interview` always when it has anything in it; `survey2` as well when it ran long enough and
    carried enough speech to be a debrief rather than a survey. Detected, not hardcoded.
    """
    out = []
    for s in seg['segments']:
        if s['kind'] == 'interview' and s['wordCount'] > 50:
            out.append(s)
        elif (s['name'] == 'survey2' and s['durationSec'] >= DEBRIEF_MIN_SECONDS
              and s['wordCount'] >= DEBRIEF_MIN_WORDS):
            out.append(s)
    return sorted(out, key=lambda s: s['videoStart'])


def participants() -> list[str]:
    return sorted(d.name[:-3] for d in NARRATION.glob('*_s1') if (d / 'segments.json').exists())


def assemble(pid: str, verbose: bool = True) -> Path | None:
    seg = segments_for(pid)
    if seg is None:
        print('%-7s no segments.json -- run narration_segments.py first' % pid, file=sys.stderr)
        return None

    parts = debrief_segments(seg)
    docx = INTERVIEWS / ('%s.docx' % pid)
    if not parts:
        note = ('see %s' % docx.relative_to(ROOT)) if docx.exists() else 'NO DEBRIEF ANYWHERE'
        if verbose:
            print('%-7s no debrief in audio -- %s' % (pid, note))
        return None

    d = NARRATION / ('%s_s1' % pid)
    lines = ['# Debrief: %s%s' % (pid, '   [CONSULTED EXPERT]' if seg['consultedExpert'] else ''),
             '# anchor %s +-%.1fs; timestamps are video time into %s.mp4'
             % (seg['anchor']['source'], seg['anchor']['uncertaintySec'], pid),
             '# sources: %s' % ', '.join('%s (%.0fs, %d words)'
                                         % (p['name'], p['durationSec'], p['wordCount'])
                                         for p in parts)]
    if docx.exists():
        lines.append('# NOTE: a written interview also exists at %s' % docx.relative_to(ROOT))
    lines.append('')

    for p in parts:
        lines.append('')
        lines.append('=== %s ===' % p['name'])
        src = d / 'segments' / _stem(seg, p)
        for raw in src.read_text(encoding='utf-8').splitlines():
            if raw and not raw.startswith('#'):
                lines.append(raw)

    dest = d / 'debrief.txt'
    dest.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    if verbose:
        print('%-7s %s (%d words from %s)'
              % (pid, dest.relative_to(ROOT), sum(p['wordCount'] for p in parts),
                 '+'.join(p['name'] for p in parts)))
    return dest


def _stem(seg: dict, part: dict) -> str:
    idx = seg['segments'].index(part)
    return '%02d_%s.txt' % (idx, part['name'])


# ── render ────────────────────────────────────────────────────────────────────────────────────

def quote_id(pid: str, theme: str, video_start: float) -> str:
    """Stable and meaningful: participant, theme, and the second it was said.

    Seconds-into-the-video is the useful third component because it is exactly what you need to go
    and watch the moment, and it cannot collide within a participant and theme.
    """
    return '%s/%s/%d' % (pid, theme, round(video_start))


def load_quotes() -> list[dict]:
    out = []
    for path in sorted(NARRATION.glob('*_s1/quotes.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        pid = data['participantId']
        seg = segments_for(pid) or {}
        for q in data.get('quotes', []):
            unknown = q['theme'] not in THEMES
            if unknown:
                print('warning: %s has unknown theme %r' % (pid, q['theme']), file=sys.stderr)
            out.append(dict(q, participantId=pid, consultedExpert=seg.get('consultedExpert', False),
                            id=quote_id(pid, q['theme'], q['videoStart'])))
    return out


def hms(t: float) -> str:
    t = max(0.0, t)
    return '%d:%02d:%02d' % (int(t // 3600), int(t % 3600 // 60), int(t % 60))


def render(quotes: list[dict]) -> None:
    themes_dir, people_dir = QUOTES_OUT / 'themes', QUOTES_OUT / 'participants'
    for d in (themes_dir, people_dir):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob('*.md'):
            old.unlink()

    by_theme: dict[str, list[dict]] = {}
    by_pid: dict[str, list[dict]] = {}
    for q in quotes:
        by_theme.setdefault(q['theme'], []).append(q)
        by_pid.setdefault(q['participantId'], []).append(q)

    for theme, description in THEMES.items():
        qs = sorted(by_theme.get(theme, []), key=lambda q: (q['participantId'], q['videoStart']))
        lines = ['# %s' % theme, '', description, '',
                 '%d quotes from %d participants.'
                 % (len(qs), len({q['participantId'] for q in qs})), '']
        for q in qs:
            flag = ' **[expert]**' if q['consultedExpert'] else ''
            lines.append('### `%s`%s' % (q['id'], flag))
            lines.append('%s at %s%s' % (q['participantId'], hms(q['videoStart']),
                                         ' — *%s*' % q['stance'] if q.get('stance') else ''))
            lines.append('')
            lines.append('> %s' % q['text'].replace('\n', ' '))
            if q.get('note'):
                lines.append('')
                lines.append('%s' % q['note'])
            lines.append('')
            lines.append('See also: [%s](../participants/%s.md)'
                         % (q['participantId'], q['participantId']))
            lines.append('')
        (themes_dir / ('%s.md' % theme)).write_text('\n'.join(lines), encoding='utf-8')

    for pid, qs in sorted(by_pid.items()):
        seg = segments_for(pid) or {}
        expert = seg.get('consultedExpert', False)
        lines = ['# %s%s' % (pid, ' — consulted expert' if expert else ''), '',
                 '%d quotes across %d themes.' % (len(qs), len({q['theme'] for q in qs})), '']
        for theme in THEMES:
            mine = sorted([q for q in qs if q['theme'] == theme], key=lambda q: q['videoStart'])
            if not mine:
                continue
            lines.append('## %s' % theme)
            lines.append('')
            lines.append('[all %s quotes](../themes/%s.md)' % (theme, theme))
            lines.append('')
            for q in mine:
                lines.append('- `%s` (%s%s)' % (q['id'], hms(q['videoStart']),
                                                ', %s' % q['stance'] if q.get('stance') else ''))
                lines.append('  > %s' % q['text'].replace('\n', ' '))
                if q.get('note'):
                    lines.append('  ')
                    lines.append('  %s' % q['note'])
            lines.append('')
        (people_dir / ('%s.md' % pid)).write_text('\n'.join(lines), encoding='utf-8')

    index = ['# Quote bank', '',
             '%d quotes, %d participants, %d themes.'
             % (len(quotes), len(by_pid), len([t for t in THEMES if by_theme.get(t)])), '',
             'Verbatim participant speech — identifiable, gitignored, never commit or paste into a '
             'hosted tool. See docs/NARRATION.md, "Handling and ethics".', '',
             '## Themes', '']
    for theme, description in THEMES.items():
        qs = by_theme.get(theme, [])
        index.append('- [%s](themes/%s.md) — %d quotes, %d participants. %s'
                     % (theme, theme, len(qs), len({q['participantId'] for q in qs}), description))
    index += ['', '## Participants', '']
    for pid, qs in sorted(by_pid.items()):
        expert = (segments_for(pid) or {}).get('consultedExpert', False)
        index.append('- [%s](participants/%s.md) — %d quotes%s'
                     % (pid, pid, len(qs), ' **(consulted expert)**' if expert else ''))
    (QUOTES_OUT / 'README.md').write_text('\n'.join(index) + '\n', encoding='utf-8')

    print('rendered %d quotes: %d themes, %d participants -> %s'
          % (len(quotes), len([t for t in THEMES if by_theme.get(t)]), len(by_pid),
             QUOTES_OUT.relative_to(ROOT)))


# ── driver ────────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('assemble', help='gather each debrief into one readable file')
    sp.add_argument('--participants', nargs='*')

    sub.add_parser('render', help='turn quotes.json files into the cross-linked quote bank')

    sub.add_parser('themes', help='print the theme list')

    args = ap.parse_args()

    if args.cmd == 'themes':
        for theme, description in THEMES.items():
            print('%-24s %s' % (theme, description))
        print('\nstances: %s' % ', '.join(STANCES))
        return

    if args.cmd == 'assemble':
        pids = args.participants or participants()
        made = [p for p in (assemble(pid) for pid in pids) if p]
        print('\nassembled %d debriefs' % len(made))
        return

    render(load_quotes())


if __name__ == '__main__':
    main()
