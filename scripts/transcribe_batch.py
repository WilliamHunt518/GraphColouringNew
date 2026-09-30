"""Batch-transcribe session recordings, resumably.

`narration_pipeline.py` does one session at a time and that is the right shape for tuning a
single recording. Transcribing the whole study is a different job: ~33 sittings, ~13 hours of
audio, and a machine you want back. This walks the whole set, skips anything already done, and
can be stopped at any point -- a session is only "done" once `transcript.raw.json` exists, so an
interrupted run costs at most the session it was in the middle of.

    python scripts/transcribe_batch.py --list             # what is outstanding
    python scripts/transcribe_batch.py --limit 4          # do the next four sittings
    python scripts/transcribe_batch.py                    # do the lot

Each recording is one participant's ENTIRE sitting (session 1, the break, session 2, and the
interview afterwards) -- see NARRATION.md. So the unit here is the recording, transcribed once
into `<pid>_s1/`, not one pass per session: a second pass over the same audio for `_s2` would
transcribe the same speech twice. Where an `_s2/` directory already exists with its own trimmed
`audio.wav` (cut by hand for alignment), that clip is picked up and transcribed too.

Transcription needs a GPU to be worth starting. On CPU it runs slower than realtime, which for
this corpus is a multi-day proposition -- use `--device cpu --model distil-large-v3` only to try
one session, never the whole set.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDINGS = ROOT / 'Results' / 'Recordings'
NARRATION = ROOT / 'Results' / 'Narration'
PIPELINE = ROOT / 'scripts' / 'narration_pipeline.py'

# faster-whisper on CUDA needs cuDNN/cuBLAS, which CTranslate2 does not ship on Windows; the
# pipeline gets them by importing torch first. That torch has to be a build new enough for the
# card (cu128 for Blackwell), which is why this is its own environment rather than the base one.
DEFAULT_VENV = Path.home() / '.venvs' / 'narration' / 'Scripts' / 'python.exe'


class Target:
    """One audio file to transcribe, and where its output goes."""

    def __init__(self, pid: str, session: int, video: Path | None, outdir: Path):
        self.pid, self.session, self.video, self.outdir = pid, session, video, outdir

    @property
    def audio(self) -> Path:
        return self.outdir / 'audio.wav'

    @property
    def transcript(self) -> Path:
        return self.outdir / 'transcript.raw.json'

    @property
    def done(self) -> bool:
        return self.transcript.exists()

    def __str__(self) -> str:
        return '%s s%d' % (self.pid, self.session)


def discover() -> list[Target]:
    """Every session that could be transcribed, in participant order.

    Two sources, deliberately kept distinct: the recordings themselves (the full sitting, which
    becomes `_s1`) and any hand-trimmed `_s2` clip that someone has already cut for alignment.
    """
    targets: dict[tuple[str, int], Target] = {}

    for video in sorted(RECORDINGS.glob('*.mp4')):
        pid = video.stem
        if '_' in pid:          # P07_2.mp4 and friends: a retake fragment, not a sitting
            continue
        targets[(pid, 1)] = Target(pid, 1, video, NARRATION / ('%s_s1' % pid))

    for d in sorted(NARRATION.glob('*_s*')):
        if not d.is_dir():
            continue
        pid, _, s = d.name.rpartition('_s')
        if not s.isdigit():
            continue
        key = (pid, int(s))
        if key not in targets and (d / 'audio.wav').exists():
            targets[key] = Target(pid, int(s), None, d)

    return [targets[k] for k in sorted(targets)]


def extract_audio(t: Target) -> None:
    if t.audio.exists():
        return
    if t.video is None:
        raise SystemExit('%s has no audio.wav and no source video' % t)
    t.outdir.mkdir(parents=True, exist_ok=True)
    print('  extracting audio from %s' % t.video.name, flush=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(t.video),
                    '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(t.audio)],
                   check=True)


def transcribe(t: Target, python: str, args) -> None:
    cmd = [python, str(PIPELINE), '--participant', t.pid, '--session', str(t.session),
           'transcribe', '--model', args.model, '--device', args.device,
           '--compute-type', args.compute_type, '--beam-size', str(args.beam_size)]
    env = dict(os.environ, HF_HUB_DISABLE_SYMLINKS_WARNING='1')
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)


def duration(path: Path) -> float:
    """Seconds of audio, or 0 if ffprobe isn't there -- this is only for the ETA."""
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                              '-of', 'csv=p=0', str(path)], capture_output=True, text=True)
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--list', action='store_true', help='show what is outstanding and stop')
    ap.add_argument('--limit', type=int, help='transcribe at most this many sessions, then stop')
    ap.add_argument('--participants', nargs='*', help='only these participant ids')
    ap.add_argument('--python', default=str(DEFAULT_VENV) if DEFAULT_VENV.exists() else sys.executable,
                    help='interpreter that has faster-whisper + a CUDA torch')
    ap.add_argument('--model', default='large-v3')
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--compute-type', default='float16')
    ap.add_argument('--beam-size', type=int, default=5)
    args = ap.parse_args()

    targets = discover()
    if args.participants:
        want = set(args.participants)
        targets = [t for t in targets if t.pid in want]

    pending = [t for t in targets if not t.done]
    print('%d sessions known, %d already transcribed, %d outstanding'
          % (len(targets), len(targets) - len(pending), len(pending)))

    if args.list:
        for t in targets:
            mark = 'done' if t.done else ('audio' if t.audio.exists() else 'video only')
            print('  %-12s %s' % (str(t), mark))
        return

    if args.limit:
        pending = pending[:args.limit]

    for i, t in enumerate(pending, 1):
        print('\n[%d/%d] %s' % (i, len(pending), t), flush=True)
        started = time.time()
        try:
            extract_audio(t)
            secs = duration(t.audio)
            transcribe(t, args.python, args)
        except subprocess.CalledProcessError as exc:
            print('  FAILED (%s) -- moving on; rerun to retry' % exc, file=sys.stderr, flush=True)
            continue
        took = time.time() - started
        print('  %s in %.0fs (%.1fx realtime)' % (t, took, secs / took if took else 0), flush=True)

    left = [t for t in discover() if not t.done]
    print('\n%d sessions still outstanding' % len(left))


if __name__ == '__main__':
    main()
