"""
StudyLogger — writes JSONL event logs for downstream analysis.

All events are written to ``<output_dir>/<participant_id>_<timestamp>/events.jsonl``.
Each line is a JSON object with at minimum ``{"ts": <float>, "event": "<type>", ...}``.

Thread-safe: a threading.Lock protects all writes.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from study.config import StudyConfig
from problems.scoring import ScoringResult


class StudyLogger:
    """
    JSONL event logger for one experiment session.

    Parameters
    ----------
    output_dir:
        Parent directory under which a per-session subdirectory is created.
    participant_id:
        Participant identifier string (used in the directory name).
    """

    def __init__(self, output_dir: Path, participant_id: str) -> None:
        ts_str = time.strftime("%Y%m%d_%H%M%S")
        self._session_dir = output_dir / f"{participant_id}_{ts_str}"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._session_dir / "events.jsonl"
        self._lock = threading.Lock()
        self._session_start = time.time()

        # Open file eagerly so it exists even if the session crashes immediately
        self._fh = self._path.open("a", encoding="utf-8")

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    # ------------------------------------------------------------------
    # Core write
    # ------------------------------------------------------------------

    def log(self, event_type: str, **kwargs: Any) -> None:
        """Write one JSONL event record."""
        record: Dict[str, Any] = {"ts": time.time(), "event": event_type}
        record.update(kwargs)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def log_session_start(self, config: StudyConfig) -> None:
        self.log(
            "session_start",
            participant_id=config.participant_id,
            mode=config.mode,
            graph=config.graph_def.name,
            colours=config.colours,
            seed=config.seed,
            max_attempts=config.max_attempts,
            points_config={
                owner: pts
                for owner, pts in config.points_config.points_by_owner.items()
            },
        )

    def log_attempt_start(self, attempt: int) -> None:
        self.log("attempt_start", attempt=attempt)

    def log_node_ready(self, attempt: int, node: str, node_index: int) -> None:
        self.log("node_ready", attempt=attempt, node=node, node_index=node_index)

    def log_proposals_shown(
        self,
        attempt: int,
        node: str,
        proposals: List[Dict[str, str]],
    ) -> None:
        """proposals: list of {agent, colour}"""
        self.log("proposals_shown", attempt=attempt, node=node, proposals=proposals)

    def log_explanation_click(self, attempt: int, node: str, agent: str) -> None:
        self.log("explanation_click", attempt=attempt, node=node, agent=agent)

    def log_colour_chosen(
        self,
        attempt: int,
        node: str,
        colour: str,
        source: str,
        decision_time_s: float,
        agents_agreed: bool,
    ) -> None:
        self.log(
            "colour_chosen",
            attempt=attempt,
            node=node,
            colour=colour,
            source=source,
            decision_time_s=round(decision_time_s, 3),
            agents_agreed=agents_agreed,
        )

    def log_plan_step_shown(self, attempt: int, node: str, plan_colour: str) -> None:
        self.log("plan_step_shown", attempt=attempt, node=node, plan_colour=plan_colour)

    def log_plan_accepted(self, attempt: int, node: str) -> None:
        self.log("plan_accepted", attempt=attempt, node=node)

    def log_plan_modified(
        self, attempt: int, node: str, plan_colour: str, chosen_colour: str
    ) -> None:
        self.log(
            "plan_modified",
            attempt=attempt,
            node=node,
            plan_colour=plan_colour,
            chosen_colour=chosen_colour,
        )

    def log_plan_explanation_clicked(self, attempt: int, node: str) -> None:
        self.log("plan_explanation_clicked", attempt=attempt, node=node)

    def log_deliberation_log_opened(self, attempt: int) -> None:
        self.log("deliberation_log_opened", attempt=attempt)

    def log_attempt_complete(
        self,
        attempt: int,
        assignment: Dict[str, str],
        score: ScoringResult,
        elapsed_s: float,
    ) -> None:
        self.log(
            "attempt_complete",
            attempt=attempt,
            assignment=assignment,
            score={"total": score.total, "by_owner": score.by_owner},
            elapsed_s=round(elapsed_s, 2),
        )

    def log_replay_requested(self, attempt: int) -> None:
        self.log("replay_requested", attempt=attempt)

    def log_abandonment(self, attempt: int, node_index: int, reason: str = "") -> None:
        self.log("abandonment", attempt=attempt, node_index=node_index, reason=reason)

    def log_session_end(
        self,
        total_attempts: int,
        score_trajectory: List[int],
    ) -> None:
        self.log(
            "session_end",
            total_attempts=total_attempts,
            score_trajectory=score_trajectory,
            session_elapsed_s=round(time.time() - self._session_start, 2),
        )

    def close(self) -> None:
        with self._lock:
            self._fh.close()
