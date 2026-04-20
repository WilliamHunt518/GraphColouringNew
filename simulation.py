"""
ColourSession — orchestrates one complete experiment session.

Manages:
  - Building agents / planner from StudyConfig
  - Running up to max_attempts colouring attempts
  - Opening results windows between attempts
  - Writing session summary to the logger
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from debug_log import dbg

try:
    import tkinter as tk
except ImportError:
    tk = None  # type: ignore

from study.config import StudyConfig
from study.session import SessionManager
from study.logger import StudyLogger
from problems.graph_coloring import GraphColoring
from problems.scoring import PointsScorer
from agents.proposal_agent import ProposalAgent
from agents.planning_agent import PlanningAgent, Plan
from ui.colouring_ui import ColourStudyWindow


class ColourSession:
    """
    Runs one full participant session (up to max_attempts).

    Parameters
    ----------
    config:
        Complete study configuration.
    logger:
        StudyLogger for the session.
    """

    def __init__(self, config: StudyConfig, logger: StudyLogger) -> None:
        self._config = config
        self._logger = logger
        self._completed_attempts: List[Dict[str, str]] = []
        self._score_trajectory: List[int] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build all components, then run the attempt loop."""
        cfg = self._config
        dbg(f"ColourSession.run() start — mode={cfg.mode} max_attempts={cfg.max_attempts} graph={cfg.graph_def.name}")
        self._logger.log_session_start(cfg)

        scorer = PointsScorer(
            cfg.points_config,
            edges=cfg.graph_def.edges,
            node_regions=cfg.node_regions,
        )

        # Build agents / planner
        proposal_agents: List[ProposalAgent] = []
        planner: Optional[PlanningAgent] = None

        if cfg.mode == "mode1":
            proposal_agents = [
                ProposalAgent(ac, cfg.points_config) for ac in cfg.agent_configs
            ]
        else:
            quality = 0.8 if cfg.mode == "mode2a" else 0.3
            planner = PlanningAgent(
                agent_configs=cfg.agent_configs,
                points_config=cfg.points_config,
                node_order=cfg.graph_def.node_order,
                edges=cfg.graph_def.edges,
                quality=quality,
                seed=cfg.seed,
            )

        # Create the root Tk window once.
        # NOTE: do NOT withdraw root — if root is hidden and the colouring
        # Toplevel is destroyed, Windows briefly sees zero visible windows
        # and queues a quit event that kills the next wait_variable call.
        root = tk.Tk()
        root.title("Session Controller")
        root.geometry("1x1+0+0")
        root.resizable(False, False)

        # Single persistent Toplevel reused across all attempts.
        win_top = tk.Toplevel(root)
        win_top.deiconify()
        dbg("win_top created")

        # StringVar used to synchronise the loop with ColourStudyWindow
        # callbacks.  Values: "waiting" | "continue" | "finish" | "abandon"
        decision_var = tk.StringVar(value="waiting")

        for attempt_num in range(1, cfg.max_attempts + 1):
            dbg(f"--- ATTEMPT LOOP: attempt_num={attempt_num} of {cfg.max_attempts} ---")

            # Clear the previous attempt's widgets from the persistent window
            for child in list(win_top.winfo_children()):
                child.destroy()

            plan: Optional[Plan] = None
            if planner is not None:
                plan = planner.generate_plan(
                    attempt_number=attempt_num,
                    prior_attempts=list(self._completed_attempts),
                )

            session = SessionManager(cfg.graph_def.node_order)
            dbg(f"  SessionManager created, node_order len={len(session.node_order)}, first={session.node_order[0] if session.node_order else 'EMPTY'}")

            decision_var.set("waiting")
            _attempt_done: Dict[str, Dict] = {}

            def _on_complete(assignment: Dict[str, str], _store=_attempt_done, _num=attempt_num) -> None:
                dbg(f"  _on_complete called for attempt {_num}, assignment has {len(assignment)} nodes")
                _store["assignment"] = assignment

            def _on_decision(decision: str, _var=decision_var, _num=attempt_num) -> None:
                dbg(f"  _on_decision: attempt={_num} decision={decision!r}")
                _var.set(decision)

            # Pre-load previous attempt's colouring as visual starting point
            prior_assignment = self._completed_attempts[-1] if self._completed_attempts else None

            window = ColourStudyWindow(
                root=win_top,
                config=cfg,
                session=session,
                scorer=scorer,
                logger=self._logger,
                attempt_number=attempt_num,
                prior_attempts=list(self._completed_attempts),
                on_attempt_complete=_on_complete,
                on_session_decision=_on_decision,
                preloaded_assignment=prior_assignment,
                can_replay=(attempt_num < cfg.max_attempts),
                agents=proposal_agents if cfg.mode == "mode1" else None,
                plan=plan,
            )
            dbg(f"  ColourStudyWindow created, calling run()")
            window.run()
            dbg(f"  window.run() returned, waiting on decision_var")

            root.wait_variable(decision_var)
            decision = decision_var.get()
            dbg(f"  decision_var={decision!r}, _attempt_done keys={list(_attempt_done.keys())}")

            if decision == "abandon":
                dbg("  BREAK: window abandoned without finishing")
                break

            # Attempt completed (decision == "continue" or "finish")
            final_assignment = _attempt_done.get("assignment")
            if final_assignment is None:
                dbg("  BREAK: decision set but no assignment stored")
                break

            self._completed_attempts.append(final_assignment)
            final_score = scorer.score_assignment(final_assignment)
            self._score_trajectory.append(final_score.total)
            dbg(f"  score={final_score.total}, completed_attempts={len(self._completed_attempts)}")

            if decision == "continue":
                self._logger.log_replay_requested(attempt_num)
                dbg(f"  decision=continue, looping to attempt {attempt_num + 1}")
            else:  # "finish"
                dbg(f"  decision=finish, ending loop")
                break

        dbg(f"--- LOOP ENDED: completed {len(self._completed_attempts)} of {cfg.max_attempts} attempts ---")

        # Tear down the persistent window
        try:
            if win_top.winfo_exists():
                win_top.destroy()
        except Exception:
            pass

        # Session complete
        self._logger.log_session_end(
            total_attempts=len(self._completed_attempts),
            score_trajectory=self._score_trajectory,
        )
        self._logger.close()

        root.destroy()
        dbg("root.destroy() called — session fully complete")
