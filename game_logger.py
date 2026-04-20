from __future__ import annotations
import json
import time
from pathlib import Path


class GameLogger:
    def __init__(self, output_dir: str = "logs") -> None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._path = Path(output_dir) / f"game_{ts}.jsonl"
        self._fh = self._path.open("a", encoding="utf-8")

    def log(self, event_type: str, **kwargs: object) -> None:
        record = {"ts": time.time(), "event": event_type, **kwargs}
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
