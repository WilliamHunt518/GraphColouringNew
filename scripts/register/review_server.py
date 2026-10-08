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
import sys
import threading
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
ROOT = BASE / 'Results'
RESPONSES = BASE / 'docs' / 'analysis' / 'register' / 'responses.json'
PORT = int(os.environ.get('REVIEW_PORT', 8766))
LOCK = threading.Lock()


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
            return self._json(404, {'error': 'no responses yet'})
        return super().do_GET()

    def do_POST(self):
        if self.path.split('?')[0] != '/api/responses':
            return self._json(404, {'error': 'unknown endpoint'})
        try:
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
            assert isinstance(data.get('cards'), dict) and isinstance(data.get('pass'), int)
        except Exception as ex:                    # never overwrite good notes with a malformed body
            return self._json(400, {'error': 'bad body: %s' % ex})
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
