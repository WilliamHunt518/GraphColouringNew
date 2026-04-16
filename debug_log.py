"""
debug_log.py — lightweight file logger for diagnosing session flow issues.

Writes every call to  logs/debug/session_<timestamp>.log
Import anywhere with:  from debug_log import dbg
"""
from __future__ import annotations

import os
import time
import traceback
from pathlib import Path

_LOG_DIR = Path(__file__).parent / "logs" / "debug"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_ts = time.strftime("%Y%m%d_%H%M%S")
_LOG_PATH = _LOG_DIR / f"session_{_ts}.log"
_fh = _LOG_PATH.open("w", encoding="utf-8", buffering=1)   # line-buffered


def dbg(msg: str, *, exc: bool = False) -> None:
    """Write a timestamped debug line.  Pass exc=True to also dump the current exception."""
    t = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
    line = f"[{t}] {msg}"
    print(line, file=_fh)
    if exc:
        traceback.print_exc(file=_fh)
    _fh.flush()


dbg(f"debug_log initialised — writing to {_LOG_PATH}")
