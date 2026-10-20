#!/usr/bin/env python3
"""Serve the findings review page and save your notes to disk as you type.

    python scripts/register/review_server.py          # then review in the browser tab it opens

Serves Results/ on http://127.0.0.1:8766 (this machine only) and answers
  GET  /api/responses   -> docs/analysis/register/responses.json
  POST /api/responses   <- the page's notes, written atomically; the previous copy is kept as
                           responses.bak.json, so one bad save can always be undone
Stop it with Ctrl+C. Without it the page still works from disk and keeps notes in the browser
(Export notes to hand them over).
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
import sys
import threading
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
ROOT = BASE / 'Results'
RESPONSES = BASE / 'docs' / 'analysis' / 'register' / 'responses.json'
PORT = int(os.environ.get('REVIEW_PORT', 8766))
LOCK = threading.Lock()
CARDS = BASE / 'docs' / 'analysis' / 'register' / 'cards.yaml'


def current_pass() -> int:
    """The open pass (cards.yaml `pass:`), so a tab left open from an earlier pass can never overwrite this one's notes."""
    m = re.search(r'^pass:\s*(\d+)', CARDS.read_text(encoding='utf-8'), re.M)
    return int(m.group(1)) if m else 0


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):          # quiet: only saves and errors
        if self.command == 'POST' or (args and str(args[1])[:1] in '45'):
            sys.stderr.write('%s %s\n' % (self.log_date_time_string(), fmt % args))

    def _json(self, code, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split('?')[0] == '/api/responses':
            if RESPONSES.exists():
                return self._json(200, json.loads(RESPONSES.read_text(encoding='utf-8')))
            return self._json(200, {'pass': current_pass(), 'cards': {}})      # no notes yet; 200 so the page knows the server is here
        if self.headers.get('Range') and self._range():
            return
        return super().do_GET()

    def _range(self):
        """Byte ranges for the demo clips: without them a browser cannot seek a video (the base handler ignores Range)."""
        m = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers.get('Range', '').strip())
        path = Path(self.translate_path(self.path))
        if not m or not path.is_file():
            return False
        size = path.stat().st_size
        a, b = m.groups()
        start, end = (int(a), int(b) if b else size - 1) if a else (max(0, size - int(b or 0)), size - 1)
        end = min(end, size - 1)
        if start > end:
            self.send_response(416); self.send_header('Content-Range', 'bytes */%d' % size); self.end_headers()
            return True
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(str(path)))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        with open(path, 'rb') as fh:
            fh.seek(start)
            self.wfile.write(fh.read(end - start + 1))
        return True

    def do_POST(self):
        if self.path.split('?')[0] != '/api/responses':
            return self._json(404, {'error': 'unknown endpoint'})
        try:
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
            assert isinstance(data.get('cards'), dict) and isinstance(data.get('pass'), int)
        except Exception as ex:                    # never overwrite good notes with a malformed body
            return self._json(400, {'error': 'bad body: %s' % ex})
        if data['pass'] != current_pass():         # a stale tab from an earlier pass: refuse, keep the file
            return self._json(409, {'error': 'notes are for pass %s but pass %s is open -- reload the page'
                                             % (data['pass'], current_pass())})
        acted = RESPONSES.with_name('acted.json')     # notes Claude has acted on (clear_acted.py): a stale tab must not revive them
        if acted.exists():
            for k, old in (json.loads(acted.read_text(encoding='utf-8')).get('notes') or {}).items():
                card, _, qid = k.partition('@')       # <card>@<quote id>: a comment on one quote
                r = data['cards'].get(card)
                gone = {(o.get('note') or '').strip() for o in old}
                if r and qid and ((r.get('qnotes') or {}).get(qid) or '').strip() in gone:
                    r['qnotes'] = {x: v for x, v in r['qnotes'].items() if x != qid}
                elif r and not qid and (r.get('note') or '').strip() in gone:
                    r['note'] = ''
        with LOCK:
            RESPONSES.parent.mkdir(parents=True, exist_ok=True)
            if RESPONSES.exists():
                RESPONSES.with_name('responses.bak.json').write_text(RESPONSES.read_text(encoding='utf-8'), encoding='utf-8')
            tmp = RESPONSES.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding='utf-8')
            os.replace(tmp, RESPONSES)
        return self._json(200, {'ok': True, 'cards': len(data['cards'])})


def main():
    page = ROOT / 'findings_review.html'
    if not page.exists():
        sys.exit('Results/findings_review.html is missing -- run scripts/register/build_review.py first')
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), functools.partial(Handler, directory=str(ROOT)))
    url = 'http://127.0.0.1:%d/findings_review.html' % PORT
    print('Review page: %s\nNotes save to %s\nCtrl+C to stop.' % (url, RESPONSES.relative_to(BASE)))
    if '--no-browser' not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')


if __name__ == '__main__':
    main()
