#!/usr/bin/env python3
"""List every note in the open pass that is still in responses.json, so none is missed when acting on a pass.

    python scripts/register/open_notes.py

A note stays until clear_acted.py moves it to acted.json, so everything listed here is either a request not yet
done or a judgement the researcher is keeping (a verdict's reason, "one of the better ones"). Each is marked with
whether findings.yaml already has a `done` reply for its key.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clear_acted import RESPONSES, done_keys  # noqa: E402


def main() -> None:
    R = json.loads(RESPONSES.read_text(encoding='utf-8'))
    done = done_keys()
    rows = [(k, c, c['note']) for k, c in R['cards'].items() if (c.get('note') or '').strip()]
    rows += [(k + '@' + q, c, t) for k, c in R['cards'].items() for q, t in (c.get('qnotes') or {}).items() if t.strip()]
    print('pass %s: %d open notes (a key with @ is a comment on one quote)' % (R['pass'], len(rows)))
    for k, c, t in rows:
        print('\n%s  [%s%s]' % (k, c.get('verdict') or c.get('role') or '-', ', has done reply' if k in done else ''))
        print('  ' + t.strip().replace('\n', '\n  '))


if __name__ == '__main__':
    main()
