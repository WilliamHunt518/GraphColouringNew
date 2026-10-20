#!/usr/bin/env python3
"""Cut the demo clips listed in docs/analysis/register/demos.yaml from the session recordings.

    python scripts/register/build_demos.py            # cut any clip that is missing
    python scripts/register/build_demos.py --force    # re-cut every clip
    python scripts/register/build_demos.py --frames   # also write a still every 2 s per clip, to check the `look` notes

Each clip comes in three views (both screens at half size; the strategic screen alone; the tactical screen alone), 15 fps, NO AUDIO (the narration is a participant's voice). Session time -> video time via the session's
`sessionTimeOffset` in Results/Narration/<pid>_s1/segments.json. Output goes to Results/review_media/ (gitignored, like
Results/Recordings/), with a poster frame per clip and an optional full-resolution close-up (`zoom`). Needs ffmpeg on PATH.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
DEMOS = BASE / 'docs' / 'analysis' / 'register' / 'demos.yaml'
REC = BASE / 'Results' / 'Recordings'
NARR = BASE / 'Results' / 'Narration'
OUT = BASE / 'Results' / 'review_media'
# The rig records both monitors side by side, 4480x1392: the strategic screen is x 0-1920 (its browser window sits at
# y ~120-1270, black above and below) and the tactical screen is x 1920-4480 at full height. One file per view:
VIEWS = {'': 'scale=2240:-2',                                 # both screens, whole frame, half size
         '_strat': 'crop=1920:1150:0:120',                    # strategic screen only, full size
         '_tac': 'crop=2560:1392:1920:0,scale=1920:-2'}       # tactical screen only (it is the higher-resolution one)


def offset(pid: str, session: int) -> float:
    segs = json.loads((NARR / f'{pid}_s1' / 'segments.json').read_text(encoding='utf-8'))['segments']
    for s in segs:
        if s['kind'] == 'session' and s['name'] == f'session{session}' and s.get('sessionTimeOffset') is not None:
            return float(s['sessionTimeOffset'])
    raise SystemExit(f'{pid}: no offset for session {session} in segments.json')


def run(args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y'] + args, check=True)


def main() -> None:
    if not shutil.which('ffmpeg'):
        raise SystemExit('ffmpeg not found on PATH')
    OUT.mkdir(parents=True, exist_ok=True)
    force, frames = '--force' in sys.argv, '--frames' in sys.argv
    for d in yaml.safe_load(DEMOS.read_text(encoding='utf-8'))['demos']:
        src = REC / f"{d['pid']}.mp4"
        if not src.exists() or not (NARR / f"{d['pid']}_s1" / 'segments.json').exists():
            print('skip %s: no recording %s' % (d['id'], src.name)); continue
        t0 = offset(d['pid'], d['session']) + d['from']
        dur = d['to'] - d['from']
        for suf, vf in VIEWS.items():
            mp4, jpg = OUT / f"{d['id']}{suf}.mp4", OUT / f"{d['id']}{suf}.jpg"
            if force or not mp4.exists():
                run(['-ss', '%.2f' % t0, '-i', str(src), '-t', '%.2f' % dur, '-an', '-vf', f'{vf},fps=15',
                     '-c:v', 'libx264', '-preset', 'slow', '-crf', '30', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(mp4)])
            if force or not jpg.exists():
                run(['-ss', '%.2f' % (t0 + d.get('poster', dur / 2)), '-i', str(src), '-frames:v', '1', '-vf', vf, '-q:v', '4', str(jpg)])
        mp4 = OUT / f"{d['id']}.mp4"
        z = d.get('zoom')
        zf = OUT / f"{d['id']}_zoom.jpg"
        if z and (force or not zf.exists()):
            run(['-ss', '%.2f' % (t0 + z['at']), '-i', str(src), '-frames:v', '1', '-vf', 'crop=' + z['crop'], '-q:v', '3', str(zf)])
        if frames:
            fd = OUT / 'frames' / d['id']
            fd.mkdir(parents=True, exist_ok=True)
            run(['-ss', '%.2f' % t0, '-i', str(src), '-t', '%.2f' % dur, '-vf', 'scale=1600:-2,fps=0.5', '-q:v', '5',
                 str(fd / 'f%02d.jpg')])
        print('%-20s %s s%d %5.1f-%5.1f s  (video %.1f s)  %.0f kB' % (d['id'], d['pid'], d['session'], d['from'], d['to'],
                                                                     t0, mp4.stat().st_size / 1024))


if __name__ == '__main__':
    main()
