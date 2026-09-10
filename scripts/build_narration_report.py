#!/usr/bin/env python3
"""
Build a local-only "decision cards" viewer over everything the narration pipeline has produced.

    python scripts/build_narration_report.py

Reads every logs/narration/<pid>_s<n>/windows.json (docs/NARRATION.md) and writes one
self-contained HTML file, embedding the narration alongside each decision event, to

    logs/narration/decision-cards.html

That output path is INSIDE logs/narration/, which is gitignored -- deliberately. The page embeds
verbatim (redacted) participant speech, which is identifiable data under the same ethics-approval
terms as the audio and transcripts it's built from (see docs/NARRATION.md "Handling and ethics"):
runs locally, never committed, never uploaded. Unlike docs/reports/two-tiers-two-scenarios.html
(pooled, anonymous, committed), this file must never be added to git or pasted into an Artifact.

Re-run it whenever a new session gets run through narration_pipeline.py's `join` step.
"""
import glob
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TEMPLATE = BASE / 'scripts' / 'narration_report_template.html'
OUT = BASE / 'logs' / 'narration' / 'decision-cards.html'

# Per-utterance word-level timing is only needed for the pipeline's own speech_measures() call,
# already computed into `speech`; dropping it here keeps the embedded payload an order of
# magnitude smaller without losing anything the page renders.
DROP_UTTERANCE_KEYS = ('words', 'windowIds', 'segments')


def load_codings(narration_dir: Path) -> dict:
    """logs/narration/<pid>_s<n>/codes.json -- optional, hand-coded (see docs/NARRATION.md
    "No coding scheme"). Absent for any session not yet coded; callers must handle that."""
    path = narration_dir / 'codes.json'
    if not path.exists():
        return {}
    d = json.loads(path.read_text(encoding='utf-8'))
    return dict(
        coder=d.get('coder'), limitations=d.get('limitations', []), narrative=d.get('narrative'),
        byWindowId={c['windowId']: c for c in d.get('codings', [])},
    )


def safe_window_id(window_id: str) -> str:
    """Mirrors narration_pipeline.py's safe_window_id -- ':' is illegal in a Windows filename."""
    return window_id.replace(':', '_')


def load_sessions() -> list[dict]:
    sessions = []
    for path in sorted(glob.glob(str(BASE / 'logs' / 'narration' / '*' / 'windows.json'))):
        narration_dir = Path(path).parent
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        coding = load_codings(narration_dir)
        windows = []
        for w in d.get('windows', []):
            ww = dict(w)
            ww['utterances'] = [
                {k: v for k, v in u.items() if k not in DROP_UTTERANCE_KEYS}
                for u in w.get('utterances', [])
            ]
            ww['coding'] = coding.get('byWindowId', {}).get(w['id'])
            clip = narration_dir / 'clips' / (safe_window_id(w['id']) + '.mp4')
            if clip.exists():
                # Relative to the report's own location (logs/narration/decision-cards.html), so
                # it keeps working wherever the whole logs/narration/ tree is opened from.
                ww['clipPath'] = narration_dir.name + '/clips/' + clip.name
            windows.append(ww)
        sessions.append(dict(
            participantId=d.get('participantId'), sessionNumber=d.get('sessionNumber'),
            complexity=d.get('complexity'), appVersion=d.get('appVersion'),
            alignment=d.get('alignment'), preRoll=d.get('preRoll'), postRoll=d.get('postRoll'),
            windows=windows,
            coder=coding.get('coder'), limitations=coding.get('limitations', []),
            narrative=coding.get('narrative'),
        ))
    return sessions


def build_findings(sessions: list[dict]) -> dict:
    """Aggregate code frequencies across every coded window found, plus a reason x objective-choice
    cross-tab. Pooled across whatever sessions have a codes.json -- today that's one session, one
    participant, so this is a within-session summary, not a cross-participant finding; the page
    says so explicitly rather than implying otherwise."""
    reason_counts: dict[str, int] = {}
    trust_counts: dict[str, int] = {}
    cross: dict[str, dict[str, int]] = {}
    coded_windows = 0
    total_windows = 0
    coders = set()
    for s in sessions:
        total_windows += len(s['windows'])
        if s.get('coder'):
            coders.add(s['coder'])
        for w in s['windows']:
            c = w.get('coding')
            if not c:
                continue
            coded_windows += 1
            close = w.get('closeEvent') or {}
            if w['kind'] == 'strategic':
                choice = close.get('choiceType') or 'n/a'
            elif w['kind'] == 'tactical':
                choice = 'modified' if close.get('modifiedFromAgentPlan') else 'agent-plan-used'
            elif w['kind'] == 'recovery':
                choice = close.get('recoveryType') or ('agent' if close.get('wasAgentSuggested') else 'manual')
            else:
                choice = 'n/a'
            for r in c.get('reasonCodes', []):
                reason_counts[r] = reason_counts.get(r, 0) + 1
                bucket = cross.setdefault(r, {})
                bucket[choice] = bucket.get(choice, 0) + 1
            t = c.get('trustCode')
            if t:
                trust_counts[t] = trust_counts.get(t, 0) + 1
    return dict(
        codedWindows=coded_windows, totalWindows=total_windows, coders=sorted(coders),
        reasonCounts=reason_counts, trustCounts=trust_counts, crossTab=cross,
    )


def ascii_only(src: str) -> str:
    """Same escaping as build_agent_report.py -- see that file for why."""
    marker = '<script>\n'
    head, sep, tail = src.partition(marker)
    head = ''.join(c if ord(c) < 128 else '&#x%x;' % ord(c) for c in head)
    tail = ''.join(c if ord(c) < 128 else '\\u%04x' % ord(c) for c in tail)
    return head + sep + tail


def main() -> None:
    sessions = load_sessions()
    if not sessions:
        print('no logs/narration/*/windows.json found -- run narration_pipeline.py ... join first',
              file=sys.stderr)
        raise SystemExit(1)

    findings = build_findings(sessions)
    payload = json.dumps({'sessions': sessions, 'findings': findings}, separators=(',', ':'), ensure_ascii=True)
    payload = payload.replace('</', '<\\/')

    html = ascii_only(TEMPLATE.read_text(encoding='utf-8')).replace('__DATA__', payload)
    if '__DATA__' in html:
        raise SystemExit('template placeholder missing')
    if any(ord(ch) > 127 for ch in html):
        raise SystemExit('non-ASCII survived escaping')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding='utf-8')

    n_windows = sum(len(s['windows']) for s in sessions)
    n_spoken = sum(1 for s in sessions for w in s['windows'] if w['utteranceCount'] > 0)
    print('%d session(s), %d decisions, %d with narration attached, %d coded'
          % (len(sessions), n_windows, n_spoken, findings['codedWindows']))
    print('  %s  (%.0f KB)' % (OUT.relative_to(BASE), OUT.stat().st_size / 1024))
    print('  gitignored (logs/narration/) -- open it locally, never commit or upload it')


if __name__ == '__main__':
    main()
