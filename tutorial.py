"""
tutorial.py — scripted 8-step guided tutorial for the drone channel assignment task.

Entry point: run_tutorial(screen, output_dir, seed)
"""
from __future__ import annotations
import math
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

import pygame

from robot_world import RobotWorld, SPEED_MIN, SPEED_MAX, SWITCH_DURATION
from robot_renderer import RobotRenderer, TutorialCallout, PANEL_W


def _make_log_snapshot(world: RobotWorld, ids: list, proposed: dict) -> list:
    """Return a log snapshot: list of (id, norm_x, norm_y, channel_after).
    Positions are normalized relative to the bounding box of involved drones
    so they spread out in the mini-graph even when clustered.
    """
    robots = [world.robots[did] for did in ids if did < len(world.robots)]
    if not robots:
        return []
    xs = [r.x for r in robots]
    ys = [r.y for r in robots]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    # Ensure a minimum view radius so drones don't all stack at the same pixel
    half_w = max((max(xs) - min(xs)) / 2 + world.arena_w * 0.04, world.arena_w * 0.12)
    half_h = max((max(ys) - min(ys)) / 2 + world.arena_h * 0.04, world.arena_h * 0.12)
    x_lo, y_lo = cx - half_w, cy - half_h
    return [
        (r.id,
         (r.x - x_lo) / (2 * half_w),
         (r.y - y_lo) / (2 * half_h),
         proposed.get(r.id, r.channel))
        for r in robots
    ]
from game_logger import GameLogger
from agents.channel_agent import ChannelAdvisor
from robot_game import _StudyExit, _apply_suggestion
from panel_window import DetachedPanelWindow, is_supported as panel_detach_supported, monitor_rect


# ── Tutorial step definition ──────────────────────────────────────────────────

@dataclass
class TutorialStep:
    number: int
    total: int
    heading: str
    body: str
    highlight_ids: List[int]             = field(default_factory=list)
    highlight_color: Tuple[int,int,int]  = (255, 240, 60)
    advance_on_space: bool               = True
    freeze: bool                         = True
    min_time: float                      = 0.0   # seconds before SPACE can advance
    disabled_buttons: frozenset          = field(default_factory=frozenset)
    completion_check: Optional[Callable[[dict], bool]] = None
    setup_fn: Optional[Callable[[RobotWorld, dict], None]] = None
    preserve_suggestion: bool            = False  # keep pending_suggestion across step transition
    run_flex_monitor: bool               = False  # run lightweight flex-tick each frame (flex tutorial only)
    hint_locked: Optional[str]          = None   # overrides "Fix all clashes" hint when step is locked


# ── Tutorial director ─────────────────────────────────────────────────────────

class TutorialDirector:
    def __init__(self, world: RobotWorld, flex_mode: bool = False) -> None:
        self._world        = world
        self._steps        = _make_flex_steps(world) if flex_mode else _make_steps(world)
        self._index        = 0
        self._pulse        = 0.0
        self._entered      = False
        self._step_elapsed = 0.0
        self._step_unlocked = False  # True once completion_check passes on an advance_on_space step

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_done(self) -> bool:
        return self._index >= len(self._steps)

    @property
    def is_frozen(self) -> bool:
        if self.is_done:
            return False
        return self._steps[self._index].freeze

    @property
    def current_callout(self) -> Optional[TutorialCallout]:
        if self.is_done:
            return None
        s = self._steps[self._index]

        hint_override = None
        if s.advance_on_space and s.min_time > 0:
            remaining = max(0.0, s.min_time - self._step_elapsed)
            if remaining > 0:
                hint_override = f"Free play  —  {remaining:.0f}s before you can continue"
            else:
                hint_override = "SPACE to continue when ready"
        elif s.advance_on_space and s.completion_check is not None:
            if self._step_unlocked:
                hint_override = "SPACE to continue"
            else:
                hint_override = s.hint_locked if s.hint_locked is not None else "Fix all clashes first, then press SPACE"

        return TutorialCallout(
            heading=f"Step {s.number} of {s.total} — {s.heading}",
            body=s.body,
            highlight_ids=s.highlight_ids,
            highlight_color=s.highlight_color,
            pulse_phase=self._pulse,
            dim_arena=(s.advance_on_space and not s.highlight_ids and s.min_time == 0),
            advance_on_space=s.advance_on_space,
            disabled_buttons=s.disabled_buttons,
            hint_override=hint_override,
        )

    def enter_step(self, game_state: dict) -> None:
        if self.is_done or self._entered:
            return
        self._entered = True
        step = self._steps[self._index]
        if step.setup_fn:
            step.setup_fn(self._world, game_state)
        self._world._detect_edges()

    def tick(self, dt: float, game_state: dict) -> bool:
        if self.is_done:
            return True
        self._pulse        = (self._pulse + dt * 1.3) % 1.0
        self._step_elapsed += dt

        if not self._entered:
            self.enter_step(game_state)

        step = self._steps[self._index]
        if step.completion_check and step.completion_check(game_state):
            if step.advance_on_space:
                self._step_unlocked = True   # unlock space; user must press it to advance
            else:
                self._advance(game_state)
        return self.is_done

    def on_space(self, game_state: dict) -> None:
        if self.is_done:
            return
        s = self._steps[self._index]
        if s.advance_on_space and self._step_elapsed >= s.min_time:
            if s.completion_check is None or self._step_unlocked:
                self._advance(game_state)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _advance(self, game_state: dict) -> None:
        self._index        += 1
        self._entered       = False
        self._pulse         = 0.0
        self._step_elapsed  = 0.0
        self._step_unlocked = False
        game_state["last_action"]  = None
        game_state["selected_ids"].clear()
        game_state["popup_drone_id"] = None
        # Preserve suggestion state if the incoming step needs it (e.g. step 6b)
        next_step = self._steps[self._index] if self._index < len(self._steps) else None
        if next_step is None or not next_step.preserve_suggestion:
            game_state["pending_suggestion"] = None
            game_state.pop("tutorial_forced_suggestion", None)


# ── Step setup helpers ────────────────────────────────────────────────────────

def _place(world: RobotWorld, configs: List[Tuple]) -> None:
    """configs: list of (id, fx, fy, channel, vx, vy)"""
    aw, ah = world.arena_w, world.arena_h
    for did, fx, fy, ch, vx, vy in configs:
        r = world.robots[did]
        r.x, r.y         = fx * aw, fy * ah
        r.vx, r.vy       = vx, vy
        r.heading        = math.atan2(vy, vx) if (vx or vy) else r.heading
        r.channel        = ch
        r.switching_to   = None
        r.switch_elapsed = 0.0


def _make_steps(world: RobotWorld) -> List[TutorialStep]:
    N       = 10
    DB_ALL  = frozenset({"suggest", "auto_assign"})   # both disabled
    DB_AUTO = frozenset({"auto_assign"})              # must use Suggest
    DB_SUG  = frozenset({"suggest"})                  # must use Auto-assign

    # ── Step 1: Welcome + scoring ────────────────────────────────────────────
    def setup_1(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.18, 0.30, "red",   0, 0),
            (1, 0.50, 0.30, "green", 0, 0),
            (2, 0.82, 0.30, "blue",  0, 0),
            (3, 0.18, 0.70, "green", 0, 0),
            (4, 0.50, 0.70, "blue",  0, 0),
            (5, 0.82, 0.70, "red",   0, 0),
        ])

    # ── Step 2: Clash demo ───────────────────────────────────────────────────
    # D0/D1/D2 form a tight K3 triangle so they all connect at any resolution
    # (max separation ≈ 154px at 2560px wide, well under CONNECT_RADIUS=364px).
    def setup_2(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.44, 0.47, "red",   0, 0),
            (1, 0.50, 0.47, "red",   0, 0),
            (2, 0.47, 0.53, "red",   0, 0),
            (3, 0.10, 0.80, "green", 0, 0),
            (4, 0.72, 0.82, "blue",  0, 0),
            (5, 0.88, 0.22, "green", 0, 0),
        ])

    # ── Step 3: M1 fix ───────────────────────────────────────────────────────
    def setup_3(w: RobotWorld, gs: dict) -> None:
        setup_2(w, gs)

    def check_3(gs: dict) -> bool:
        return not gs["world"].clashing_pairs

    # ── Step 4: Group select ─────────────────────────────────────────────────
    def setup_4(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.30, 0.38, "green", 0, 0),
            (1, 0.42, 0.48, "green", 0, 0),
            (2, 0.30, 0.58, "green", 0, 0),
            (3, 0.42, 0.38, "green", 0, 0),
            (4, 0.80, 0.28, "blue",  0, 0),
            (5, 0.80, 0.72, "red",   0, 0),
        ])

    def check_4(gs: dict) -> bool:
        return gs["selected_ids"] >= {0, 1, 2, 3}

    # ── Step 5: M2 suggest + apply (agent is correct) ───────────────────────
    # Inherits positions from setup_4. At typical study screen widths the
    # D0–D3 cluster forms K4-minus-one-edge (D2–D3 are just out of range),
    # so the forced suggestion below is always clash-free in the mini-graph.
    def setup_5(w: RobotWorld, gs: dict) -> None:
        # Reposition D2 and D3 so their fractional separation (~0.316) is well above
        # the fractional CONNECT_RADIUS (~0.226), guaranteeing the forced suggestion
        # {D2:blue, D3:blue} is always clash-free at every monitor width.
        _place(w, [
            (2, 0.22, 0.50, "green", 0, 0),
            (3, 0.48, 0.32, "green", 0, 0),
        ])
        gs["selected_ids"].update({0, 1, 2, 3})
        gs["tutorial_forced_suggestion"] = {0: "red", 1: "green", 2: "blue", 3: "blue"}

    def check_5(gs: dict) -> bool:
        return gs["last_action"] == "suggestion_applied"

    # ── Step 6a: Select & suggest to get to the review screen ───────────────
    # Same tight K3 cluster as steps 2/3. Bad suggestion assigns all 3 green.
    def setup_6a(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.44, 0.47, "red",   0, 0),
            (1, 0.50, 0.47, "red",   0, 0),
            (2, 0.47, 0.53, "red",   0, 0),
            (3, 0.10, 0.80, "green", 0, 0),
            (4, 0.72, 0.82, "blue",  0, 0),
            (5, 0.88, 0.22, "green", 0, 0),
        ])
        # Pre-arm the bad suggestion so it fires when Suggest is clicked
        gs["tutorial_forced_suggestion"] = {0: "red", 1: "green", 2: "green"}

    def check_6a(gs: dict) -> bool:
        # Advance once the user has clicked Suggest and seen the proposal
        return gs["last_action"] == "suggestion_shown"

    # ── Step 6b: Spot the mistake and override ───────────────────────────────
    def setup_6b(w: RobotWorld, gs: dict) -> None:
        # No world reset — the bad suggestion is already visible in the panel.
        # Keep the forced suggestion key so the mini-graph still shows the clash.
        pass

    def check_6b(gs: dict) -> bool:
        return (gs["last_action"] == "suggestion_applied"
                and not gs["world"].clashing_pairs)

    # ── Step 7: M3 auto-assign ───────────────────────────────────────────────
    # Same K3 cluster positions, now on blue.
    def setup_7(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.44, 0.47, "blue",  0, 0),
            (1, 0.50, 0.47, "blue",  0, 0),
            (2, 0.47, 0.53, "blue",  0, 0),
            (3, 0.15, 0.25, "red",   0, 0),
            (4, 0.82, 0.25, "red",   0, 0),
            (5, 0.82, 0.75, "green", 0, 0),
        ])

    def check_7(gs: dict) -> bool:
        return gs["last_action"] == "auto_assign_applied"

    # ── Step 8: Unsolvable K4 cluster ────────────────────────────────────────
    # Four drones in a tight 0.06-fractional square so all 6 pairs connect at
    # any resolution (max pair distance ≈ 264px at 2560×1440 < CONNECT_RADIUS).
    # With only 3 channels, at least one pair MUST share (pigeonhole principle).
    def setup_8(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.40, 0.44, "red",   0, 0),
            (1, 0.46, 0.44, "green", 0, 0),
            (2, 0.40, 0.50, "blue",  0, 0),
            (3, 0.46, 0.50, "red",   0, 0),   # matches D0 → immediate clash
            (4, 0.78, 0.28, "blue",  0, 0),
            (5, 0.78, 0.72, "green", 0, 0),
        ])

    # Step 8 advances on SPACE (no automatic completion); user explores then moves on.

    # ── Step 9: Free practice ────────────────────────────────────────────────
    def setup_9(w: RobotWorld, gs: dict) -> None:
        import random as _rng
        rng  = _rng.Random(99)
        cfgs = []
        for i, (fx, fy, ch) in enumerate([
            (0.20, 0.35, "red"),   (0.50, 0.25, "green"), (0.80, 0.35, "blue"),
            (0.20, 0.65, "green"), (0.50, 0.75, "blue"),  (0.80, 0.65, "red"),
        ]):
            ang = rng.uniform(0, 2 * math.pi)
            spd = rng.uniform(w.v_min, w.v_max)
            cfgs.append((i, fx, fy, ch, math.cos(ang) * spd, math.sin(ang) * spd))
        _place(w, cfgs)
        for r in w.robots:
            r.heading = math.atan2(r.vy, r.vx)

    return [
        TutorialStep(1, N,
            heading="Welcome",
            body="Your task: manage radio channels for a drone swarm. "
                 "SCORING — every second that two drones on the SAME channel are within range, "
                 "the clash timer ticks up. This is worse when multiple clashes happen simultaneously. "
                 "Lower clash time = better. "
                 "Press SPACE to continue.",
            highlight_ids=[], advance_on_space=True, freeze=True,
            disabled_buttons=DB_ALL, setup_fn=setup_1),

        TutorialStep(2, N,
            heading="Channel Clashes",
            body="D0, D1, and D2 are all on RED and close enough to interfere — shown by the red lines. "
                 "To stop the clashes you must move at least two of them onto different channels. Press SPACE.",
            highlight_ids=[0, 1, 2], highlight_color=(230, 60, 60),
            advance_on_space=True, freeze=True,
            disabled_buttons=DB_ALL, setup_fn=setup_2),

        TutorialStep(3, N,
            heading="Fix a Clash — Mode 1 (click a drone)",
            body="Click each highlighted drone to open its channel menu and pick a different channel. "
                 "No two touching drones can share a channel — "
                 "the red clash lines will disappear when all three have unique channels.",
            highlight_ids=[0, 1, 2], highlight_color=(255, 240, 60),
            advance_on_space=True, freeze=True,
            completion_check=check_3, disabled_buttons=DB_ALL, setup_fn=setup_3),

        TutorialStep(4, N,
            heading="Group Select",
            body="Instead of assigning manually, you use the AI assistant "
                 "To do this, drag a selection box around them "
                 "(or hold Ctrl and click to build up the group one by one). "
                 "Drag a box over the 4 highlighted drones D0–D3 now.",
            highlight_ids=[0, 1, 2, 3], highlight_color=(90, 200, 255),
            advance_on_space=False, freeze=True,
            completion_check=check_4, disabled_buttons=DB_ALL, setup_fn=setup_4),

        TutorialStep(5, N,
            heading="Suggest & Review — Mode 2",
            body="Well done. D0–D3 are selected and all clashing on the same channel. "
                 "Click 'Suggest' on the agent panel — the assistant will recommend new channels. "
                 "Review the mini-graph preview, then click Apply.",
            highlight_ids=[0, 1, 2, 3], highlight_color=(90, 200, 255),
            advance_on_space=False, freeze=True,
            completion_check=check_5, disabled_buttons=DB_AUTO, setup_fn=setup_5),

        TutorialStep(6, N,
            heading="That worked correctly. Now do it again — Suggest for D0, D1 & D2",
            body="D0, D1, and D2 are clashing on RED again. Select all three (drag or Ctrl+click), "
                 "then click Suggest. We'll check what the assistant recommends.",
            highlight_ids=[0, 1, 2], highlight_color=(230, 60, 60),
            advance_on_space=False, freeze=True,
            completion_check=check_6a, disabled_buttons=DB_AUTO, setup_fn=setup_6a),

        TutorialStep(7, N,
            heading="Spot the Mistake — Override a Bad Suggestion",
            body="The assistant is not perfect and sometimes makes mistakes — this applies to "
                 "both Suggest and Auto-assign modes. "
                 "Here, the assistant put D1 and D2 both on GREEN — they will STILL clash "
                 "(red line in the mini-graph). On the agent panel, manually fix this suggested configuration, "
                 "then click Apply.",
            highlight_ids=[0, 1, 2], highlight_color=(230, 60, 60),
            advance_on_space=False, freeze=True,
            completion_check=check_6b, disabled_buttons=DB_AUTO, setup_fn=setup_6b,
            preserve_suggestion=True),

        TutorialStep(8, N,
            heading="Auto-Assign — Mode 3",
            body="If you want to, you can skip the review process of the suggestion mode and auto assign, "
                 "this is the same, but accepts the agent's suggestion without presenting it to you first. "
                 "D0, D1, and D2 are clashing again. Select all three (drag or Ctrl+click), "
                 "then click 'Auto-assign' — channels are applied instantly without a review step.",
            highlight_ids=[0, 1, 2], highlight_color=(255, 160, 40),
            advance_on_space=False, freeze=True,
            completion_check=check_7, disabled_buttons=DB_SUG, setup_fn=setup_7),

        TutorialStep(9, N,
            heading="When There's No Perfect Solution",
            body="Sometimes the problem can't be solved."
                 "D0–D3 are all within range of each other — a complete group of 4. "
                 "With only 3 channels, the best you can do is 1 clashing pair. Try to find the best solution. "
                 "Use any mode to experiment, then press SPACE to continue.",
            highlight_ids=[0, 1, 2, 3], highlight_color=(230, 60, 60),
            advance_on_space=True, freeze=True,
            disabled_buttons=frozenset(), setup_fn=setup_8),

        TutorialStep(10, N,
            heading="Free Practice",
            body="All modes covered — including handling the unavoidable! "
                 "The drones are now moving. Use M1 (click), M2 (Suggest), or M3 (Auto-assign) "
                 "freely. Try to keep clash time low. Get used to using all modes and think about when you prefer each. "
                 "Press SPACE when you're ready to start the real trial.",
            highlight_ids=[], advance_on_space=True, freeze=False,
            min_time=30.0, disabled_buttons=frozenset(), setup_fn=setup_9),
    ]


# ── Flexible tutorial steps ──────────────────────────────────────────────────
# Position convention: y ≥ 0.38 for all static drone placements so they stay
# below the 200 px tutorial callout strip at the top of the arena.
#
# Phase 1 (steps 1–3):  Clash basics — penalty, manual fix, K4 limit
# Phase 2 (steps 4–6):  Pre-flight setup — manual, Watch:Suggest, Watch:Auto
# Phase 3 (steps 7–10): Live demos — setup (frozen) then launch (live) for each mode
# Phase 4 (step 11):    Free practice

def _make_flex_steps(world: RobotWorld) -> List[TutorialStep]:
    N       = 16
    DB_ALL  = frozenset({"watch_suggest", "watch_auto", "unwatch"})
    DB_AUTO = frozenset({"watch_auto"})    # allow Watch:Suggest and Unwatch
    DB_SUG  = frozenset({"watch_suggest"}) # allow Watch:Auto and Unwatch

    # ────────────── PHASE 1: Clash basics (steps 1–4) ──────────────────────────
    # K3 clashing group (D0–D2) + connected pair on different channels (D3–D4)
    # + isolated singleton (D5).

    def setup_clash(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.44, 0.55, "red",   0, 0),
            (1, 0.50, 0.55, "red",   0, 0),
            (2, 0.47, 0.62, "red",   0, 0),
            (3, 0.18, 0.65, "green", 0, 0),
            (4, 0.26, 0.65, "blue",  0, 0),
            (5, 0.82, 0.72, "green", 0, 0),
        ])
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    def check_3(gs: dict) -> bool:
        return not gs["world"].clashing_pairs

    def setup_4(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.40, 0.47, "red",   0, 0), (1, 0.46, 0.47, "green", 0, 0),
            (2, 0.40, 0.53, "blue",  0, 0), (3, 0.46, 0.53, "red",   0, 0),
            (4, 0.78, 0.42, "blue",  0, 0), (5, 0.78, 0.75, "green", 0, 0),
        ])
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    # ────────────── PHASE 2: Pre-flight setup (steps 5–7) ──────────────────────
    _PREFLIGHT = [
        (0, 0.20, 0.50, None, 0, 0),
        (1, 0.30, 0.44, None, 0, 0),
        (2, 0.30, 0.56, None, 0, 0),
        (3, 0.70, 0.44, None, 0, 0),
        (4, 0.80, 0.50, None, 0, 0),
        (5, 0.70, 0.56, None, 0, 0),
    ]

    def setup_5(w: RobotWorld, gs: dict) -> None:
        _place(w, _PREFLIGHT)
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    def check_5(gs: dict) -> bool:
        return all(r.channel is not None for r in gs["world"].robots)

    def setup_6(w: RobotWorld, gs: dict) -> None:
        _place(w, _PREFLIGHT)
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()
        gs["tutorial_forced_suggestion"] = {
            0: "red", 1: "green", 2: "blue",
            3: "red", 4: "green", 5: "blue",
        }

    def check_6(gs: dict) -> bool:
        return gs["last_action"] == "suggestion_applied"

    def setup_7(w: RobotWorld, gs: dict) -> None:
        _place(w, _PREFLIGHT)
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    def check_7(gs: dict) -> bool:
        return gs["last_action"] == "auto_assign_applied"

    # ────────────── PHASE 3: Algorithm + delay explanation (steps 8–9) ──────────

    def setup_8(w: RobotWorld, gs: dict) -> None:
        # Show the two K3 clusters so the body text makes visual sense
        _place(w, [
            (0, 0.20, 0.50, "red",   0, 0),
            (1, 0.30, 0.44, "green", 0, 0),
            (2, 0.30, 0.56, "blue",  0, 0),
            (3, 0.70, 0.44, "red",   0, 0),
            (4, 0.80, 0.50, "green", 0, 0),
            (5, 0.70, 0.56, "blue",  0, 0),
        ])
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    def setup_9(w: RobotWorld, gs: dict) -> None:
        # Show two drones close together clashing, with D0 shown mid-switch
        w.switch_duration = SWITCH_DURATION  # enable real delay for display
        _place(w, [
            (0, 0.45, 0.58, "red",   0, 0),
            (1, 0.52, 0.58, "red",   0, 0),
            (2, 0.20, 0.45, "green", 0, 0),
            (3, 0.80, 0.45, "blue",  0, 0),
            (4, 0.20, 0.75, "blue",  0, 0),
            (5, 0.80, 0.75, "green", 0, 0),
        ])
        # Manually place D0 mid-switch so the countdown arc is visible
        r0 = w.robots[0]
        r0.switching_to  = "green"
        r0.switch_elapsed = SWITCH_DURATION * 0.5
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    # ────────────── PHASE 4: Live moving demos (steps 10–15) ───────────────────
    # D0–D2: all on RED, flying toward arena centre → guaranteed clash.
    # drone_modes set in setup steps carry into live steps (not cleared by _launch).

    def _place_triangle_static(w: RobotWorld, gs: dict) -> None:
        w.switch_duration = SWITCH_DURATION
        aw, ah = w.arena_w, w.arena_h
        for did, fx, fy in [(0, 0.22, 0.38), (1, 0.78, 0.38), (2, 0.50, 0.86)]:
            r = w.robots[did]
            r.x, r.y         = fx * aw, fy * ah
            r.vx, r.vy       = 0.0, 0.0
            r.channel        = "red"
            r.switching_to   = None
            r.switch_elapsed = 0.0
        _place(w, [
            (3, 0.10, 0.80, "blue",  0, 0),
            (4, 0.90, 0.80, "green", 0, 0),
            (5, 0.92, 0.40, "blue",  0, 0),
        ])
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    def _launch_triangle(w: RobotWorld, gs: dict) -> None:
        spd    = w.arena_w * 0.015
        aw, ah = w.arena_w, w.arena_h
        cx, cy = aw * 0.50, ah * 0.50
        for did, fx, fy in [(0, 0.22, 0.38), (1, 0.78, 0.38), (2, 0.50, 0.86)]:
            px, py = fx * aw, fy * ah
            dx, dy = cx - px, cy - py
            dist   = math.sqrt(dx * dx + dy * dy)
            r = w.robots[did]
            r.x, r.y         = px, py
            r.vx, r.vy       = dx / dist * spd, dy / dist * spd
            r.heading        = math.atan2(r.vy, r.vx)
            r.channel        = "red"  # force red so clash is guaranteed
            r.switching_to   = None
            r.switch_elapsed = 0.0
            r.next_turn_in   = 20.0
        _place(w, [
            (3, 0.10, 0.80, "blue",  0, 0),
            (4, 0.90, 0.80, "green", 0, 0),
            (5, 0.92, 0.40, "blue",  0, 0),
        ])
        # drone_modes intentionally NOT cleared — watch carries over from setup step

    # Step 10: Watch:Suggest setup
    def setup_10(w: RobotWorld, gs: dict) -> None:
        _place_triangle_static(w, gs)
        # All red, no forced suggestion — advisor gives all-red (no-op) so
        # drones stay red and clash when they fly together in the live step.

    def check_10(gs: dict) -> bool:
        dm = gs.get("drone_modes", {})
        return dm.get(0) == "suggest" and dm.get(1) == "suggest" and dm.get(2) == "suggest"

    # Step 11: Watch:Suggest live
    def setup_11(w: RobotWorld, gs: dict) -> None:
        _launch_triangle(w, gs)

    def check_11(gs: dict) -> bool:
        return gs["last_action"] == "suggestion_applied"

    # Step 12: Watch:Suggest mistake — forced bad suggestion with D1 and D2 both green
    def setup_12(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.44, 0.47, "red",   0, 0),
            (1, 0.50, 0.47, "red",   0, 0),
            (2, 0.47, 0.53, "red",   0, 0),
            (3, 0.10, 0.80, "green", 0, 0),
            (4, 0.72, 0.82, "blue",  0, 0),
            (5, 0.88, 0.22, "green", 0, 0),
        ])
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()
        # Bad suggestion: D1 and D2 both green — they're connected so they still clash
        gs["tutorial_forced_suggestion"] = {0: "red", 1: "green", 2: "green"}

    def check_12(gs: dict) -> bool:
        return (gs["last_action"] == "suggestion_applied"
                and not gs["world"].clashing_pairs)

    # Step 13: Watch:Auto setup
    def setup_13(w: RobotWorld, gs: dict) -> None:
        _place_triangle_static(w, gs)

    def check_13(gs: dict) -> bool:
        dm = gs.get("drone_modes", {})
        return dm.get(0) == "auto" and dm.get(1) == "auto" and dm.get(2) == "auto"

    # Step 14: Watch:Auto live
    def setup_14(w: RobotWorld, gs: dict) -> None:
        gs["last_action"] = None  # ensure check_14 waits for the live event
        _launch_triangle(w, gs)

    def check_14(gs: dict) -> bool:
        return gs["last_action"] == "auto_assign_applied"

    # Step 15: Watch:Auto limitation — K4 cluster, infeasible assignment
    def setup_15(w: RobotWorld, gs: dict) -> None:
        _place(w, [
            (0, 0.40, 0.44, "red",   0, 0),
            (1, 0.46, 0.44, "green", 0, 0),
            (2, 0.40, 0.50, "blue",  0, 0),
            (3, 0.46, 0.50, "red",   0, 0),  # matches D0 → immediate clash
            (4, 0.78, 0.28, "blue",  0, 0),
            (5, 0.78, 0.72, "green", 0, 0),
        ])
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    def check_15(gs: dict) -> bool:
        return gs["last_action"] == "auto_assign_applied"

    # ────────────── PHASE 5: Free practice (step 16) ───────────────────────────

    def setup_16(w: RobotWorld, gs: dict) -> None:
        import random as _rng
        rng = _rng.Random(99)
        cfgs = []
        for i, (fx, fy, ch) in enumerate([
            (0.20, 0.40, "red"),   (0.50, 0.38, "green"), (0.80, 0.40, "blue"),
            (0.20, 0.70, "green"), (0.50, 0.75, "blue"),  (0.80, 0.70, "red"),
        ]):
            ang = rng.uniform(0, 2 * math.pi)
            spd = rng.uniform(w.v_min, w.v_max)
            cfgs.append((i, fx, fy, ch, math.cos(ang) * spd, math.sin(ang) * spd))
        _place(w, cfgs)
        for r in w.robots:
            r.heading = math.atan2(r.vy, r.vx)
        dm = gs.get("drone_modes")
        if dm is not None:
            dm.clear()

    return [
        # ── Phase 1: Clash basics ─────────────────────────────────────────────

        TutorialStep(1, N,
            heading="What Is a Clash?",
            body="Two drones on the SAME channel, within range of each other = a CLASH. "
                 "D0, D1, D2 are all on RED — the red lines show every clashing pair. "
                 "D3 and D4 are also in range of each other but on DIFFERENT channels — "
                 "no clash there. Press SPACE to continue.",
            highlight_ids=[0, 1, 2], highlight_color=(230, 60, 60),
            advance_on_space=True, freeze=True,
            disabled_buttons=DB_ALL, setup_fn=setup_clash),

        TutorialStep(2, N,
            heading="The Clash Penalty",
            body="Every second a clashing pair exists, the clash timer ticks up. "
                 "With D0–D2 all touching, that's 3 clashing pairs at once — "
                 "the timer runs 3× faster. More simultaneous clashes = faster penalty. "
                 "Your goal: keep clash time as low as possible. Press SPACE.",
            highlight_ids=[0, 1, 2], highlight_color=(230, 60, 60),
            advance_on_space=True, freeze=True,
            disabled_buttons=DB_ALL, setup_fn=setup_clash),

        TutorialStep(3, N,
            heading="Fix a Clash — Click a Drone",
            body="Click each highlighted drone to open its channel menu. "
                 "Pick a channel not shared by any connected neighbour. "
                 "The red clash lines disappear when all three have unique channels. "
                 "Fix the clashes, then press SPACE.",
            highlight_ids=[0, 1, 2], highlight_color=(255, 240, 60),
            advance_on_space=True, freeze=True,
            completion_check=check_3, disabled_buttons=DB_ALL, setup_fn=setup_clash,
            hint_locked="Fix all clashes first, then press SPACE"),

        TutorialStep(4, N,
            heading="Some Problems Can't Be Fully Solved",
            body="D0–D3 are all within range of each other — a group of 4. "
                 "With only 3 channels available, at least one pair must always share a channel. "
                 "The best you can do is pick which pair clashes. "
                 "Try any mode to experiment, then press SPACE.",
            highlight_ids=[0, 1, 2, 3], highlight_color=(230, 60, 60),
            advance_on_space=True, freeze=True,
            disabled_buttons=frozenset(), setup_fn=setup_4),

        # ── Phase 2: Pre-flight setup ─────────────────────────────────────────

        TutorialStep(5, N,
            heading="Pre-Flight Setup — Manual",
            body="Before launch, all drones are unassigned (shown white). "
                 "Edges between drones show which pairs are in range of each other. "
                 "Click each drone and assign a channel so that no two connected drones share one. "
                 "Press SPACE when all are assigned.",
            highlight_ids=[0, 1, 2, 3, 4, 5], highlight_color=(200, 200, 200),
            advance_on_space=True, freeze=True,
            completion_check=check_5, disabled_buttons=DB_ALL, setup_fn=setup_5,
            hint_locked="Assign a channel to every drone first"),

        TutorialStep(6, N,
            heading="Pre-Flight Setup — Watch: Suggest",
            body="All 6 drones are unassigned again. "
                 "Drag a selection box over all of them, then click 'Watch: Suggest'. "
                 "The agent proposes an initial assignment AND starts watching those drones — "
                 "if they clash later during flight, a fix suggestion fires automatically. "
                 "Review the mini-graph, then click Apply.",
            highlight_ids=[0, 1, 2, 3, 4, 5], highlight_color=(90, 200, 255),
            advance_on_space=False, freeze=True,
            completion_check=check_6, disabled_buttons=DB_AUTO, setup_fn=setup_6),

        TutorialStep(7, N,
            heading="Pre-Flight Setup — Watch: Auto",
            body="All 6 drones are unassigned again. "
                 "Drag a selection box over all of them, then click 'Watch: Auto'. "
                 "Channels are assigned instantly without a review step, AND a watch is set — "
                 "any future clashes among these drones are fixed automatically the moment they form.",
            highlight_ids=[0, 1, 2, 3, 4, 5], highlight_color=(40, 220, 175),
            advance_on_space=False, freeze=True,
            completion_check=check_7, disabled_buttons=DB_SUG, setup_fn=setup_7),

        # ── Phase 3: Algorithm and delay ─────────────────────────────────────

        TutorialStep(8, N,
            heading="How the Agent Decides",
            body="The agent uses a greedy approach: it looks at which drones are connected, "
                 "then assigns channels one by one — always picking a channel not already used "
                 "by a connected neighbour. The most constrained drones (most neighbours) are "
                 "assigned first. It is fast and usually good, but early choices can limit later "
                 "options, so it is not perfect. Press SPACE.",
            highlight_ids=[], advance_on_space=True, freeze=True,
            disabled_buttons=DB_ALL, setup_fn=setup_8),

        TutorialStep(9, N,
            heading="Channel Switch Delay",
            body=f"Switching a channel takes {SWITCH_DURATION:.0f} seconds — the drone keeps "
                 f"its old channel while switching, so the clash continues until the switch "
                 f"completes. The arc and countdown on D0 show this. "
                 f"Amber rings appear before drones enter range — act then, not after. "
                 f"Press SPACE.",
            highlight_ids=[0, 1], highlight_color=(255, 200, 50),
            advance_on_space=True, freeze=True,
            disabled_buttons=DB_ALL, setup_fn=setup_9),

        # ── Phase 4: Live demos ───────────────────────────────────────────────

        TutorialStep(10, N,
            heading="Watch: Suggest — Set the Watch",
            body="D0, D1, D2 are on RED, static for now. "
                 "Select all three (drag a box or Ctrl+click) and click 'Watch: Suggest'. "
                 "The drones will be set to watched — orange rings confirm. "
                 "Press SPACE to launch.",
            highlight_ids=[0, 1, 2], highlight_color=(90, 200, 255),
            advance_on_space=True, freeze=True,
            completion_check=check_10, disabled_buttons=DB_AUTO, setup_fn=setup_10,
            hint_locked="Select D0–D2 and click 'Watch: Suggest' first"),

        TutorialStep(11, N,
            heading="Watch: Suggest — Automatic Trigger",
            body="D0–D2 are flying toward the centre, all on RED (orange rings = Watch: Suggest active). "
                 "When they converge and clash, the suggestion fires automatically. "
                 "Apply the suggestion when it appears, then press SPACE.",
            highlight_ids=[0, 1, 2], highlight_color=(255, 160, 20),
            advance_on_space=True, freeze=False,
            completion_check=check_11, disabled_buttons=DB_AUTO, setup_fn=setup_11,
            run_flex_monitor=True),

        TutorialStep(12, N,
            heading="Watch: Suggest — Spot the Mistake",
            body="The agent isn't always right. D0–D2 are clashing again. "
                 "Select them and click 'Watch: Suggest'. Look at the mini-graph carefully: "
                 "can you spot the mistake? The agent put two drones on the same channel. "
                 "Click the affected drone in the mini-graph, pick a different channel, then Apply.",
            highlight_ids=[0, 1, 2], highlight_color=(230, 60, 60),
            advance_on_space=False, freeze=True,
            completion_check=check_12, disabled_buttons=DB_AUTO, setup_fn=setup_12),

        TutorialStep(13, N,
            heading="Watch: Auto — Set the Watch",
            body="Same triangle scenario. Select D0, D1, D2 and click 'Watch: Auto'. "
                 "Channels are assigned instantly — teal rings confirm the watch is set. "
                 "Press SPACE to launch.",
            highlight_ids=[0, 1, 2], highlight_color=(40, 220, 175),
            advance_on_space=True, freeze=True,
            completion_check=check_13, disabled_buttons=DB_SUG, setup_fn=setup_13,
            hint_locked="Select D0–D2 and click 'Watch: Auto' first"),

        TutorialStep(14, N,
            heading="Watch: Auto — Automatic Fix",
            body="D0–D2 are flying toward the centre with Watch: Auto active (teal rings). "
                 "When they clash, the fix fires instantly — you don't need to do anything. "
                 "Watch it happen, then press SPACE.",
            highlight_ids=[0, 1, 2], highlight_color=(40, 220, 175),
            advance_on_space=True, freeze=False,
            completion_check=check_14, disabled_buttons=DB_SUG, setup_fn=setup_14,
            run_flex_monitor=True),

        TutorialStep(15, N,
            heading="Watch: Auto — Has Limits Too",
            body="Watch: Auto also cannot solve the impossible. "
                 "D0–D3 are all in range of each other. Select all four and click 'Watch: Auto'. "
                 "The agent assigns channels instantly, but with a group of 4 and only 3 channels, "
                 "one clash will always remain — even Watch: Auto has limits. Press SPACE when done.",
            highlight_ids=[0, 1, 2, 3], highlight_color=(230, 60, 60),
            advance_on_space=True, freeze=True,
            completion_check=check_15, disabled_buttons=DB_SUG, setup_fn=setup_15,
            hint_locked="Select D0–D3 and click 'Watch: Auto' first"),

        # ── Phase 5: Free practice ────────────────────────────────────────────

        TutorialStep(16, N,
            heading="Free Practice",
            body="All modes covered! Drones are now moving. "
                 "Click a drone to assign manually, 'Watch: Suggest' for reviewed fixes, "
                 "'Watch: Auto' for instant automatic fixes, or 'Set: Manual' to remove a watch "
                 "from drones you want to control yourself. "
                 "Press SPACE when you're ready to begin the real trial.",
            highlight_ids=[], advance_on_space=True, freeze=False,
            min_time=30.0, disabled_buttons=frozenset(), setup_fn=setup_16),
    ]


# ── Tutorial game loop ────────────────────────────────────────────────────────

def run_tutorial(
    seed: int = 0,
    screen: Optional[pygame.Surface] = None,
    output_dir: Optional[str] = None,
    arena_monitor: int = 0,
    panel_monitor: int = 1,
    flex_mode: bool = False,
) -> Dict:
    _owns_display = screen is None
    if _owns_display:
        _ab = monitor_rect(arena_monitor)
        if _ab:
            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{_ab[0]},{_ab[1]}'
        os.environ.setdefault('SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS', '0')
        os.environ.setdefault('SDL_MOUSE_FOCUS_CLICKTHROUGH', '1')
        pygame.init()
        os.environ.pop('SDL_VIDEO_WINDOW_POS', None)

        if _ab:
            screen = pygame.display.set_mode((_ab[2], _ab[3]), pygame.NOFRAME)
        else:
            info = pygame.display.Info()
            screen = pygame.display.set_mode(
                (info.current_w, info.current_h), pygame.NOFRAME
            )
        pygame.display.set_caption("Drone Channel Assignment — Tutorial")

    clock    = pygame.time.Clock()
    window_w, window_h = screen.get_size()
    # Panel is always in a separate window; arena uses the full screen width
    arena_w  = window_w

    world    = RobotWorld(n_robots=6, seed=seed, duration=99999,
                          arena_w=arena_w, arena_h=window_h,
                          v_min=SPEED_MIN, v_max=SPEED_MAX,
                          switch_duration=0.0)
    renderer = RobotRenderer(screen)
    advisor  = ChannelAdvisor(epsilon=0.0, seed=seed)

    log_dir  = output_dir or "logs"
    log_file = "game_events.jsonl" if output_dir else None
    logger   = GameLogger(output_dir=log_dir, filename=log_file)
    logger.log("tutorial_start", ts=time.time())

    director = TutorialDirector(world, flex_mode=flex_mode)

    flex_drone_modes: Dict[int, str] = {}
    tut_agent_log: list = []  # (elapsed, msg, snapshot) entries for flex tutorial panel

    game_state: Dict = {
        "selected_ids":     set(),
        "pending_suggestion": None,
        "last_action":      None,
        "popup_drone_id":   None,
        "world":            world,
    }
    if flex_mode:
        game_state["drone_modes"] = flex_drone_modes

    from robot_game import _drone_at

    selected_ids:       Set[int]           = game_state["selected_ids"]
    popup_drone_id:     Optional[int]      = None
    pending_suggestion: Optional[Dict[int,str]] = None
    suggestion_overrides: Dict[int,str]    = {}
    pending_infeasible  = False
    panel_detached      = False
    _panel_win: Optional[DetachedPanelWindow] = None

    # Open the panel window immediately on the chosen monitor
    if panel_detach_supported():
        try:
            _pb = monitor_rect(panel_monitor)
            if _pb is None:
                n_mon = pygame.display.get_num_displays()
                pmon  = min(panel_monitor, n_mon - 1)
                _raw  = pygame.display.get_display_bounds(pmon)
                _pb   = (_raw[0], _raw[1], _raw[2], _raw[3])
            _panel_win = DetachedPanelWindow(_pb[2], _pb[3], pos_x=_pb[0], pos_y=_pb[1])
            renderer.set_panel_surface(_panel_win.get_fresh_surface())
            panel_detached = True
            logger.log("tutorial_panel_opened", monitor=panel_monitor)
        except Exception as exc:
            logger.log("tutorial_panel_open_failed", reason=str(exc))

    mouse_down_pos:     Optional[Tuple[int,int]] = None
    drag_pos:           Optional[Tuple[int,int]] = None
    is_dragging         = False
    DRAG_THRESHOLD      = 5
    prev_clash_pairs:   frozenset = frozenset()
    prev_warning_pairs: frozenset = frozenset()
    step_start_ts       = time.time()

    def _sync_from_gs() -> None:
        nonlocal popup_drone_id, pending_suggestion, selected_ids
        popup_drone_id     = game_state["popup_drone_id"]
        pending_suggestion = game_state["pending_suggestion"]
        selected_ids       = game_state["selected_ids"]

    def _on_step_advance(prev_idx: int, keep_suggestion: bool = False) -> None:
        nonlocal selected_ids, popup_drone_id, pending_suggestion
        nonlocal suggestion_overrides, pending_infeasible, step_start_ts
        _log_step_transition(logger, prev_idx, step_start_ts)
        step_start_ts = time.time()
        _sync_from_gs()
        if not keep_suggestion:
            suggestion_overrides = {}
            pending_infeasible   = False
        else:
            # Re-sync overrides from the preserved suggestion
            if pending_suggestion is not None:
                suggestion_overrides = dict(pending_suggestion)

    # ── Flexible-tutorial helpers ─────────────────────────────────────────────
    def _handle_watch_suggest() -> None:
        nonlocal pending_suggestion, suggestion_overrides, pending_infeasible, popup_drone_id
        for did in list(selected_ids):
            if flex_drone_modes.get(did) == "suggest":
                del flex_drone_modes[did]
            else:
                flex_drone_modes[did] = "suggest"
        logger.log("watch_mode_set", drones=list(selected_ids), mode="suggest", elapsed=world.elapsed)
        active = [d for d in selected_ids if flex_drone_modes.get(d) == "suggest"]
        if active:
            cur    = {r.id: r.channel for r in world.robots}
            forced = game_state.get("tutorial_forced_suggestion")
            if forced is not None:
                proposed, infeas = forced, False
            else:
                proposed, infeas = advisor.suggest(
                    active, cur, world.edges, near_pairs=list(world.warning_pairs))
            logger.log_suggestion_requested(list(selected_ids), cur, world.elapsed)
            logger.log_suggestion_shown(active, proposed, infeas, world.elapsed)
            pending_suggestion   = proposed
            suggestion_overrides = dict(proposed)
            pending_infeasible   = infeas
            popup_drone_id       = None
            game_state["pending_suggestion"] = pending_suggestion
            game_state["last_action"]        = "suggestion_shown"

    def _handle_watch_auto() -> None:
        nonlocal popup_drone_id
        for did in list(selected_ids):
            if flex_drone_modes.get(did) == "auto":
                del flex_drone_modes[did]
            else:
                flex_drone_modes[did] = "auto"
        logger.log("watch_mode_set", drones=list(selected_ids), mode="auto", elapsed=world.elapsed)
        active = [d for d in selected_ids if flex_drone_modes.get(d) == "auto"]
        if active:
            cur = {r.id: r.channel for r in world.robots}
            proposed, infeas = advisor.suggest(
                active, cur, world.edges, near_pairs=list(world.warning_pairs))
            logger.log_auto_assign_applied(active, proposed, infeas, world.elapsed)
            snap = _make_log_snapshot(world, active, proposed)
            ids_str = ",".join(f"D{d}" for d in sorted(active))
            tut_agent_log.append((world.elapsed, f"{world.elapsed:.1f}s  {ids_str}: auto-fixed", snap))
            _apply_suggestion(world, proposed, logger, mode="M3", instant=True)
            old_sel = list(selected_ids)
            selected_ids.clear()
            popup_drone_id = None
            game_state["selected_ids"]   = selected_ids
            game_state["popup_drone_id"] = None
            game_state["last_action"]    = "auto_assign_applied"
            logger.log_group_deselected(old_sel, world.elapsed)

    def _handle_unwatch() -> None:
        cleared = [d for d in selected_ids if d in flex_drone_modes]
        for did in cleared:
            del flex_drone_modes[did]
        logger.log("watch_cleared", drones=cleared, elapsed=world.elapsed)

    _tut_sug_ts = [-999.0]  # elapsed time of last auto-triggered suggestion

    def _tut_flex_monitor() -> None:
        nonlocal pending_suggestion, suggestion_overrides, pending_infeasible

        # Keep D0–D2 aimed at the arena centre until they're nearly there.
        # Runs every frame AFTER world.update(), overriding any heading/speed
        # perturbations from the physics so convergence is guaranteed.
        aw, ah = world.arena_w, world.arena_h
        cx, cy = aw * 0.50, ah * 0.50
        aim_spd   = aw * 0.015  # ~40% slower than original 0.025
        threshold = aw * 0.04  # stop correcting once within ~4% of arena width
        for did in (0, 1, 2):
            r = world.robots[did]
            dx, dy = cx - r.x, cy - r.y
            dist_sq = dx * dx + dy * dy
            if dist_sq > threshold * threshold:
                dist = math.sqrt(dist_sq)
                r.vx = dx / dist * aim_spd
                r.vy = dy / dist * aim_spd
                r.heading = math.atan2(r.vy, r.vx)

        if not flex_drone_modes or pending_suggestion is not None:
            return
        clashing = {i for pair in world.clashing_pairs for i in pair}

        # Auto-mode drones: request switch (respects switch_duration, same as live game)
        auto_watched = [d for d in flex_drone_modes
                        if d in clashing and flex_drone_modes[d] == "auto"]
        if auto_watched:
            cur = {r.id: r.channel for r in world.robots}
            proposed, infeas = advisor.suggest(
                auto_watched, cur, world.edges, near_pairs=list(world.warning_pairs))
            logger.log_auto_assign_applied(auto_watched, proposed, infeas, world.elapsed)
            snap = _make_log_snapshot(world, auto_watched, proposed)
            ids_str = ",".join(f"D{d}" for d in sorted(auto_watched))
            tut_agent_log.append((world.elapsed, f"{world.elapsed:.1f}s  {ids_str}: auto-fixed", snap))
            _apply_suggestion(world, proposed, logger, mode="flex_auto", instant=False)
            game_state["last_action"] = "auto_assign_applied"
            return

        # Suggest-mode drones: show proposal (3-second refire guard)
        if world.elapsed - _tut_sug_ts[0] < 3.0:
            return
        sug_watched = [d for d in flex_drone_modes
                       if d in clashing and flex_drone_modes[d] == "suggest"]
        if not sug_watched:
            return
        cur = {r.id: r.channel for r in world.robots}
        proposed, infeas = advisor.suggest(
            sug_watched, cur, world.edges, near_pairs=list(world.warning_pairs))
        pending_suggestion   = proposed
        suggestion_overrides = dict(proposed)
        pending_infeasible   = infeas
        game_state["pending_suggestion"] = pending_suggestion
        game_state["last_action"]        = "suggestion_shown"
        _tut_sug_ts[0] = world.elapsed
        logger.log_suggestion_shown(sug_watched, proposed, infeas, world.elapsed)

    try:
        while True:
            dt = clock.tick(60) / 1000.0
            dt = min(dt, 0.05)

            # Sync aliases back from game_state (director may have mutated them)
            _sync_from_gs()
            game_state["selected_ids"] = selected_ids

            raw_events = pygame.event.get()
            # Split events if panel is detached
            panel_events: List[pygame.event.Event] = []
            if panel_detached and _panel_win is not None:
                panel_events, raw_events = _panel_win.filter_events(raw_events)

            for event in raw_events:
                if event.type == pygame.QUIT:
                    logger.log("tutorial_quit", elapsed=world.elapsed, step=director._index + 1)
                    raise _StudyExit()

                elif event.type == pygame.KEYDOWN:
                    logger.log("tutorial_key_down",
                               key=event.key, key_name=pygame.key.name(event.key),
                               step=director._index + 1, elapsed=world.elapsed)
                    if event.key == pygame.K_ESCAPE:
                        logger.log("tutorial_quit", elapsed=world.elapsed, step=director._index + 1)
                        raise _StudyExit()
                    elif event.key == pygame.K_SPACE:
                        prev_step = director._index
                        director.on_space(game_state)
                        if director._index != prev_step:
                            next_step = director._steps[director._index] if director._index < len(director._steps) else None
                            keep = (next_step is not None and next_step.preserve_suggestion)
                            _on_step_advance(prev_step, keep_suggestion=keep)

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    logger.log("tutorial_mouse_down", x=mx, y=my,
                               step=director._index + 1, elapsed=world.elapsed)

                    # ── Suggestion panel buttons (inline panel only) ──────────
                    if pending_suggestion is not None:
                        if not panel_detached:
                            # Panel button hits only apply when panel is inline
                            if popup_drone_id is not None:
                                for ch, rect in renderer.suggestion_channel_btn_rects.items():
                                    if rect.collidepoint(mx, my):
                                        old_ch = suggestion_overrides.get(popup_drone_id)
                                        suggestion_overrides[popup_drone_id] = ch
                                        if old_ch != ch:
                                            logger.log("tutorial_suggestion_channel_picked",
                                                       drone_id=popup_drone_id, channel=ch,
                                                       step=director._index + 1, elapsed=world.elapsed)
                                        break
                            if renderer.suggestion_apply_rect \
                                    and renderer.suggestion_apply_rect.collidepoint(mx, my):
                                n_overrides = sum(
                                    1 for did, ch in suggestion_overrides.items()
                                    if pending_suggestion.get(did) != ch
                                )
                                logger.log_suggestion_applied(suggestion_overrides, n_overrides, world.elapsed)
                                _apply_suggestion(world, suggestion_overrides, logger,
                                                  mode="M2", instant=director.is_frozen)
                                pending_suggestion    = None
                                suggestion_overrides  = {}
                                selected_ids          = set()
                                popup_drone_id        = None
                                game_state["last_action"]          = "suggestion_applied"
                                game_state["pending_suggestion"]   = None
                                game_state["popup_drone_id"]       = None
                                game_state["selected_ids"]         = selected_ids
                                continue
                            if renderer.suggestion_cancel_rect \
                                    and renderer.suggestion_cancel_rect.collidepoint(mx, my):
                                logger.log_suggestion_cancelled(world.elapsed)
                                pending_suggestion  = None
                                suggestion_overrides = {}
                                popup_drone_id      = None
                                game_state["pending_suggestion"] = None
                                game_state["popup_drone_id"]     = None
                                continue
                        # Either inline (no button hit) or detached: block arena interaction
                        mouse_down_pos = (mx, my); drag_pos = (mx, my); is_dragging = False
                        continue

                    # ── HUD group-action buttons (inline panel only) ──────────
                    if selected_ids and not panel_detached:
                        if "suggest" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["suggest"].collidepoint(mx, my):
                            cur = {r.id: r.channel for r in world.robots}
                            forced = game_state.get("tutorial_forced_suggestion")
                            if forced is not None:
                                proposed, infeas = forced, False
                            else:
                                proposed, infeas = advisor.suggest(
                                    list(selected_ids), cur, world.edges,
                                    near_pairs=list(world.warning_pairs))
                            logger.log_suggestion_requested(list(selected_ids), cur, world.elapsed)
                            logger.log_suggestion_shown(list(selected_ids), proposed, infeas, world.elapsed)
                            pending_suggestion   = proposed
                            suggestion_overrides = dict(proposed)
                            pending_infeasible   = infeas
                            popup_drone_id       = None
                            game_state["pending_suggestion"] = pending_suggestion
                            game_state["last_action"]        = "suggestion_shown"
                            continue

                        if "auto_assign" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["auto_assign"].collidepoint(mx, my):
                            cur = {r.id: r.channel for r in world.robots}
                            proposed, infeas = advisor.suggest(
                                list(selected_ids), cur, world.edges,
                                near_pairs=list(world.warning_pairs))
                            logger.log_auto_assign_applied(list(selected_ids), proposed, infeas, world.elapsed)
                            _apply_suggestion(world, proposed, logger, mode="M3", instant=director.is_frozen)
                            old_sel = list(selected_ids)
                            selected_ids  = set()
                            popup_drone_id = None
                            game_state["selected_ids"]   = selected_ids
                            game_state["popup_drone_id"] = None
                            game_state["last_action"]    = "auto_assign_applied"
                            logger.log_group_deselected(old_sel, world.elapsed)
                            continue

                        if flex_mode and "watch_suggest" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["watch_suggest"].collidepoint(mx, my):
                            _handle_watch_suggest()
                            continue

                        if flex_mode and "watch_auto" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["watch_auto"].collidepoint(mx, my):
                            _handle_watch_auto()
                            continue

                        if flex_mode and "unwatch" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["unwatch"].collidepoint(mx, my):
                            _handle_unwatch()
                            continue

                    # ── M1 popup ──────────────────────────────────────────────
                    if popup_drone_id is not None and renderer.popup_rects:
                        for ch, rect in renderer.popup_rects.items():
                            if rect.collidepoint(mx, my):
                                robot = world.robots[popup_drone_id]
                                if ch != robot.channel:
                                    robot.channel      = ch
                                    robot.switching_to = None
                                    world._detect_edges()
                                    logger.log_switch_requested(
                                        popup_drone_id, robot.channel, ch, world.elapsed, mode="M1")
                                else:
                                    logger.log("tutorial_m1_same_channel",
                                               drone_id=popup_drone_id, channel=ch,
                                               step=director._index + 1, elapsed=world.elapsed)
                                old_popup = popup_drone_id
                                game_state["last_action"]    = "M1_switch"
                                popup_drone_id               = None
                                game_state["popup_drone_id"] = None
                                logger.log_popup_dismissed(old_popup, world.elapsed)
                                break
                        else:
                            if mx < renderer.arena_w:
                                mouse_down_pos = (mx, my); drag_pos = (mx, my)
                        continue

                    if mx < renderer.arena_w:
                        mouse_down_pos = (mx, my); drag_pos = (mx, my); is_dragging = False
                    else:
                        logger.log("tutorial_panel_click_miss", x=mx, y=my,
                                   step=director._index + 1, elapsed=world.elapsed)

                elif event.type == pygame.MOUSEMOTION:
                    if mouse_down_pos is not None and pygame.mouse.get_pressed()[0]:
                        mx, my   = event.pos
                        drag_pos = (mx, my)
                        dx, dy   = mx - mouse_down_pos[0], my - mouse_down_pos[1]
                        if math.sqrt(dx*dx + dy*dy) > DRAG_THRESHOLD:
                            is_dragging = True

                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if pending_suggestion is not None:
                        if mouse_down_pos is not None and not is_dragging:
                            mx, my = event.pos
                            for did, rect in renderer.suggestion_node_rects.items():
                                if rect.collidepoint(mx, my):
                                    prev_popup = popup_drone_id
                                    popup_drone_id = did if did != popup_drone_id else None
                                    game_state["popup_drone_id"] = popup_drone_id
                                    if popup_drone_id is not None:
                                        logger.log_suggestion_node_selected(did, world.elapsed)
                                    elif prev_popup is not None:
                                        logger.log_suggestion_node_deselected(prev_popup, world.elapsed)
                                    break
                            else:
                                logger.log("tutorial_suggestion_panel_miss",
                                           x=event.pos[0], y=event.pos[1],
                                           step=director._index + 1, elapsed=world.elapsed)
                        mouse_down_pos = None; drag_pos = None; is_dragging = False
                        continue

                    if mouse_down_pos is None:
                        is_dragging = False; continue

                    mx, my = event.pos
                    ctrl   = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)

                    if is_dragging and drag_pos:
                        x0, y0 = mouse_down_pos; x1, y1 = drag_pos
                        box    = pygame.Rect(min(x0,x1), min(y0,y1), abs(x1-x0), abs(y1-y0))
                        new_sel = {r.id for r in world.robots if box.collidepoint(int(r.x), int(r.y))}
                        prev_sel = list(selected_ids)
                        selected_ids = (selected_ids ^ new_sel) if ctrl else new_sel
                        popup_drone_id = None
                        game_state["selected_ids"]   = selected_ids
                        game_state["popup_drone_id"] = None
                        if selected_ids:
                            logger.log_group_selected(list(selected_ids), "box", world.elapsed)
                            game_state["last_action"] = "group_selected"
                        elif prev_sel:
                            logger.log_group_deselected(prev_sel, world.elapsed)
                    else:
                        clicked = _drone_at((mx, my), world, renderer.arena_w)
                        if clicked is not None:
                            if ctrl:
                                if clicked in selected_ids:
                                    selected_ids.discard(clicked)
                                    logger.log("tutorial_ctrl_deselect", drone_id=clicked,
                                               step=director._index + 1, elapsed=world.elapsed)
                                else:
                                    selected_ids.add(clicked)
                                    logger.log("tutorial_ctrl_select", drone_id=clicked,
                                               step=director._index + 1, elapsed=world.elapsed)
                                popup_drone_id = None
                                game_state["selected_ids"]   = selected_ids
                                game_state["popup_drone_id"] = None
                                if selected_ids:
                                    logger.log_group_selected(list(selected_ids), "ctrl_click", world.elapsed)
                                    game_state["last_action"] = "group_selected"
                            elif selected_ids:
                                old_sel = list(selected_ids)
                                selected_ids   = set()
                                popup_drone_id = clicked if clicked != popup_drone_id else None
                                game_state["selected_ids"]   = selected_ids
                                game_state["popup_drone_id"] = popup_drone_id
                                logger.log_group_deselected(old_sel, world.elapsed)
                                if popup_drone_id is not None:
                                    logger.log_popup_opened(popup_drone_id, world.elapsed)
                            else:
                                new_popup = clicked if clicked != popup_drone_id else None
                                if popup_drone_id is not None and new_popup is None:
                                    logger.log_popup_dismissed(popup_drone_id, world.elapsed)
                                elif new_popup is not None:
                                    logger.log_popup_opened(new_popup, world.elapsed)
                                popup_drone_id = new_popup
                                game_state["popup_drone_id"] = popup_drone_id
                        else:
                            prev_sel = list(selected_ids)
                            prev_popup = popup_drone_id
                            selected_ids   = set()
                            popup_drone_id = None
                            game_state["selected_ids"]   = selected_ids
                            game_state["popup_drone_id"] = None
                            if prev_sel:
                                logger.log_group_deselected(prev_sel, world.elapsed)
                            if prev_popup is not None:
                                logger.log_popup_dismissed(prev_popup, world.elapsed)
                            logger.log_arena_click_miss(mx, my, world.elapsed)

                    mouse_down_pos = None; drag_pos = None; is_dragging = False

            # ── Events from panel window ──────────────────────────────────────
            for event in panel_events:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos

                    # Suggestion panel buttons
                    if pending_suggestion is not None:
                        if popup_drone_id is not None:
                            for ch, rect in renderer.suggestion_channel_btn_rects.items():
                                if rect.collidepoint(mx, my):
                                    old_ch = suggestion_overrides.get(popup_drone_id)
                                    suggestion_overrides[popup_drone_id] = ch
                                    if old_ch != ch:
                                        logger.log("tutorial_suggestion_channel_picked",
                                                   drone_id=popup_drone_id, channel=ch,
                                                   step=director._index + 1, elapsed=world.elapsed)
                                    break
                        if renderer.suggestion_apply_rect \
                                and renderer.suggestion_apply_rect.collidepoint(mx, my):
                            n_overrides = sum(
                                1 for did, ch in suggestion_overrides.items()
                                if pending_suggestion.get(did) != ch
                            )
                            logger.log_suggestion_applied(suggestion_overrides, n_overrides, world.elapsed)
                            _apply_suggestion(world, suggestion_overrides, logger,
                                              mode="M2", instant=director.is_frozen)
                            pending_suggestion    = None
                            suggestion_overrides  = {}
                            selected_ids          = set()
                            popup_drone_id        = None
                            game_state["last_action"]          = "suggestion_applied"
                            game_state["pending_suggestion"]   = None
                            game_state["popup_drone_id"]       = None
                            game_state["selected_ids"]         = selected_ids
                        elif renderer.suggestion_cancel_rect \
                                and renderer.suggestion_cancel_rect.collidepoint(mx, my):
                            logger.log_suggestion_cancelled(world.elapsed)
                            pending_suggestion   = None
                            suggestion_overrides = {}
                            popup_drone_id       = None
                            game_state["pending_suggestion"] = None
                            game_state["popup_drone_id"]     = None

                    # HUD group-action buttons
                    elif selected_ids:
                        if "suggest" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["suggest"].collidepoint(mx, my):
                            cur = {r.id: r.channel for r in world.robots}
                            forced = game_state.get("tutorial_forced_suggestion")
                            if forced is not None:
                                proposed, infeas = forced, False
                            else:
                                proposed, infeas = advisor.suggest(
                                    list(selected_ids), cur, world.edges,
                                    near_pairs=list(world.warning_pairs))
                            logger.log_suggestion_requested(list(selected_ids), cur, world.elapsed)
                            logger.log_suggestion_shown(list(selected_ids), proposed, infeas, world.elapsed)
                            pending_suggestion   = proposed
                            suggestion_overrides = dict(proposed)
                            pending_infeasible   = infeas
                            popup_drone_id       = None
                            game_state["pending_suggestion"] = pending_suggestion
                            game_state["last_action"]        = "suggestion_shown"
                        elif "auto_assign" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["auto_assign"].collidepoint(mx, my):
                            cur = {r.id: r.channel for r in world.robots}
                            proposed, infeas = advisor.suggest(
                                list(selected_ids), cur, world.edges,
                                near_pairs=list(world.warning_pairs))
                            logger.log_auto_assign_applied(list(selected_ids), proposed, infeas, world.elapsed)
                            _apply_suggestion(world, proposed, logger, mode="M3", instant=director.is_frozen)
                            old_sel = list(selected_ids)
                            selected_ids  = set()
                            popup_drone_id = None
                            game_state["selected_ids"]   = selected_ids
                            game_state["popup_drone_id"] = None
                            game_state["last_action"]    = "auto_assign_applied"
                            logger.log_group_deselected(old_sel, world.elapsed)
                        elif flex_mode and "watch_suggest" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["watch_suggest"].collidepoint(mx, my):
                            _handle_watch_suggest()
                        elif flex_mode and "watch_auto" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["watch_auto"].collidepoint(mx, my):
                            _handle_watch_auto()
                        elif flex_mode and "unwatch" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["unwatch"].collidepoint(mx, my):
                            _handle_unwatch()

                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if pending_suggestion is not None:
                        mx, my = event.pos
                        for did, rect in renderer.suggestion_node_rects.items():
                            if rect.collidepoint(mx, my):
                                prev_popup = popup_drone_id
                                popup_drone_id = did if did != popup_drone_id else None
                                game_state["popup_drone_id"] = popup_drone_id
                                if popup_drone_id is not None:
                                    logger.log_suggestion_node_selected(did, world.elapsed)
                                elif prev_popup is not None:
                                    logger.log_suggestion_node_deselected(prev_popup, world.elapsed)
                                break

            # ── Director tick ─────────────────────────────────────────────────
            prev_idx = director._index
            if director.tick(dt, game_state):
                break
            if director._index != prev_idx:
                next_step = director._steps[director._index] if director._index < len(director._steps) else None
                keep = (next_step is not None and next_step.preserve_suggestion)
                _on_step_advance(prev_idx, keep_suggestion=keep)

            # ── Physics ───────────────────────────────────────────────────────
            if not director.is_frozen:
                world.update(dt)
                now_clash_pairs = frozenset(world.clashing_pairs)
                if now_clash_pairs != prev_clash_pairs:
                    if not prev_clash_pairs and now_clash_pairs:
                        logger.log_clash_start(world.elapsed, list(now_clash_pairs))
                    elif prev_clash_pairs and not now_clash_pairs:
                        logger.log_clash_end(world.elapsed, world.clash_seconds)
                    else:
                        added   = [list(p) for p in now_clash_pairs - prev_clash_pairs]
                        removed = [list(p) for p in prev_clash_pairs - now_clash_pairs]
                        logger.log_clash_update(
                            world.elapsed, [list(p) for p in now_clash_pairs],
                            added, removed, world.clash_seconds,
                        )
                    prev_clash_pairs = now_clash_pairs

                now_warning_pairs = frozenset(world.warning_pairs)
                if now_warning_pairs != prev_warning_pairs:
                    if not prev_warning_pairs and now_warning_pairs:
                        logger.log_warning_start(world.elapsed, [list(p) for p in now_warning_pairs])
                    elif prev_warning_pairs and not now_warning_pairs:
                        logger.log_warning_end(world.elapsed)
                    else:
                        added_w   = [list(p) for p in now_warning_pairs - prev_warning_pairs]
                        removed_w = [list(p) for p in prev_warning_pairs - now_warning_pairs]
                        logger.log_warning_update(
                            world.elapsed, [list(p) for p in now_warning_pairs],
                            added_w, removed_w,
                        )
                    prev_warning_pairs = now_warning_pairs
                # Flex monitor: fires suggestion when watched drones clash
                if flex_mode and not director.is_done:
                    step = director._steps[director._index]
                    if step.run_flex_monitor:
                        _tut_flex_monitor()
            else:
                world._detect_edges()

            # ── Render ────────────────────────────────────────────────────────
            drag_rect = (
                _make_drag_rect(mouse_down_pos, drag_pos)
                if is_dragging and mouse_down_pos and drag_pos else None
            )

            # Refresh the panel surface — it becomes stale after each flip()
            if panel_detached and _panel_win is not None:
                renderer.refresh_panel_surface(_panel_win.get_fresh_surface())

            renderer.draw_frame(
                world, "PLAYING",
                popup_drone_id=popup_drone_id,
                selected_ids=selected_ids,
                drag_rect=drag_rect,
                suggestion=pending_suggestion,
                suggestion_overrides=suggestion_overrides,
                pending_infeasible=pending_infeasible,
                tutorial_callout=director.current_callout,
                panel_detached=panel_detached,
                drone_modes=flex_drone_modes if flex_mode else None,
                agent_log=tut_agent_log[-6:] if flex_mode else None,
            )
            pygame.display.flip()
            if panel_detached and _panel_win is not None:
                _panel_win.flip()

    except _StudyExit:
        pass
    finally:
        if _panel_win is not None:
            _panel_win.close()
        logger.log("tutorial_complete", steps_completed=director._index, ts=time.time())
        logger.close()

    return {
        "is_tutorial": True,
        "completed": director._index >= len(director._steps),
        "elapsed": world.elapsed,
        "clash_seconds": world.clash_seconds,
        "clash_pct": 0.0,
        "seed": seed, "complexity": "tutorial", "duration": 0.0,
    }


def _log_step_transition(logger: GameLogger, step_idx: int, step_start: float) -> None:
    duration = time.time() - step_start
    logger.log("tutorial_step_completed", step=step_idx + 1, duration_s=round(duration, 2))


def _make_drag_rect(
    start: Tuple[int,int], current: Tuple[int,int]
) -> Tuple[int,int,int,int]:
    x0, y0 = start; x1, y1 = current
    return (min(x0,x1), min(y0,y1), abs(x1-x0), abs(y1-y0))


def run_flexible_tutorial(
    seed: int = 0,
    screen: Optional[pygame.Surface] = None,
    output_dir: Optional[str] = None,
    arena_monitor: int = 0,
    panel_monitor: int = 1,
) -> Dict:
    """Entry point for the flexible-mode tutorial (Watch: Suggest / Watch: Auto)."""
    return run_tutorial(
        seed=seed,
        screen=screen,
        output_dir=output_dir,
        arena_monitor=arena_monitor,
        panel_monitor=panel_monitor,
        flex_mode=True,
    )
