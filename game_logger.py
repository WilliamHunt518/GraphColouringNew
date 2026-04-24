from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class GameLogger:
    def __init__(self, output_dir: str = "logs", filename: Optional[str] = None) -> None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fname = filename if filename else f"game_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
        self._path = Path(output_dir) / fname
        self._fh = self._path.open("a", encoding="utf-8")

    def log(self, event_type: str, **kwargs: Any) -> None:
        record = {"ts": time.time(), "event": event_type, **kwargs}
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    # ── Convenience methods ────────────────────────────────────────────────────

    def log_game_start(
        self, seed: int, n_drones: int, complexity: str,
        duration: float, v_min: float, v_max: float,
    ) -> None:
        self.log("game_start", seed=seed, n_drones=n_drones, complexity=complexity,
                 duration=duration, v_min=v_min, v_max=v_max)

    def log_switch_requested(
        self, drone_id: int, from_ch: str, to_ch: str, elapsed: float, mode: str = "M1"
    ) -> None:
        self.log("switch_requested", drone_id=drone_id,
                 from_channel=from_ch, to_channel=to_ch,
                 elapsed=elapsed, mode=mode)

    def log_group_selected(
        self, drone_ids: List[int], method: str, elapsed: float
    ) -> None:
        self.log("group_selected", drone_ids=drone_ids, method=method, elapsed=elapsed)

    def log_suggestion_requested(
        self, drone_ids: List[int], current_channels: Dict[int, str], elapsed: float
    ) -> None:
        self.log("suggestion_requested", drone_ids=drone_ids,
                 current_channels={str(k): v for k, v in current_channels.items()},
                 elapsed=elapsed)

    def log_suggestion_shown(
        self, drone_ids: List[int], proposed: Dict[int, str],
        infeasible: bool, elapsed: float,
    ) -> None:
        self.log("suggestion_shown", drone_ids=drone_ids,
                 proposed_channels={str(k): v for k, v in proposed.items()},
                 infeasible=infeasible, elapsed=elapsed)

    def log_suggestion_modified(
        self, drone_id: int, proposed_ch: str, overridden_to: str, elapsed: float
    ) -> None:
        self.log("suggestion_modified", drone_id=drone_id,
                 proposed=proposed_ch, overridden_to=overridden_to, elapsed=elapsed)

    def log_suggestion_applied(
        self, final_channels: Dict[int, str], n_overrides: int, elapsed: float
    ) -> None:
        self.log("suggestion_applied",
                 final_channels={str(k): v for k, v in final_channels.items()},
                 n_overrides=n_overrides, elapsed=elapsed)

    def log_suggestion_cancelled(self, elapsed: float) -> None:
        self.log("suggestion_cancelled", elapsed=elapsed)

    def log_auto_assign_applied(
        self, drone_ids: List[int], proposed: Dict[int, str],
        infeasible: bool, elapsed: float,
    ) -> None:
        self.log("auto_assign_applied", drone_ids=drone_ids,
                 proposed_channels={str(k): v for k, v in proposed.items()},
                 infeasible=infeasible, elapsed=elapsed)

    def log_clash_start(self, elapsed: float, pairs: list) -> None:
        self.log("clash_start", elapsed=elapsed, pairs=pairs)

    def log_clash_end(self, elapsed: float, clash_seconds_so_far: float) -> None:
        self.log("clash_end", elapsed=elapsed, clash_seconds_so_far=clash_seconds_so_far)

    def log_game_end(self, elapsed: float, clash_seconds: float) -> None:
        pct = clash_seconds / elapsed * 100 if elapsed else 0
        self.log("game_end", elapsed=elapsed, clash_seconds=clash_seconds, clash_pct=pct)

    def log_quit(self, elapsed: float, clash_seconds: float) -> None:
        self.log("quit", elapsed=elapsed, clash_seconds=clash_seconds)

    def close(self) -> None:
        self._fh.close()
