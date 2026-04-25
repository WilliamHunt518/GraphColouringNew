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


# ── Tutorial director ─────────────────────────────────────────────────────────

class TutorialDirector:
    def __init__(self, world: RobotWorld) -> None:
        self._world        = world
        self._steps        = _make_steps(world)
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
                hint_override = "Fix all clashes first, then press SPACE"

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
        gs["selected_ids"].update({0, 1, 2, 3})          # pre-select
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
        spd  = (w.v_min + w.v_max) / 2
        cfgs = []
        for i, (fx, fy, ch) in enumerate([
            (0.20, 0.35, "red"),   (0.50, 0.25, "green"), (0.80, 0.35, "blue"),
            (0.20, 0.65, "green"), (0.50, 0.75, "blue"),  (0.80, 0.65, "red"),
        ]):
            ang = rng.uniform(0, 2 * math.pi)
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
            body="The assistant is not perfect and sometimes makes mistakes "
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


# ── Tutorial game loop ────────────────────────────────────────────────────────

def run_tutorial(
    seed: int = 0,
    screen: Optional[pygame.Surface] = None,
    output_dir: Optional[str] = None,
    arena_monitor: int = 0,
    panel_monitor: int = 1,
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

    director = TutorialDirector(world)

    game_state: Dict = {
        "selected_ids":     set(),
        "pending_suggestion": None,
        "last_action":      None,
        "popup_drone_id":   None,
        "world":            world,
    }

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
    prev_clashing       = False
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
                                                  mode="M2", instant=True)
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
                            _apply_suggestion(world, proposed, logger, mode="M3", instant=True)
                            old_sel = list(selected_ids)
                            selected_ids  = set()
                            popup_drone_id = None
                            game_state["selected_ids"]   = selected_ids
                            game_state["popup_drone_id"] = None
                            game_state["last_action"]    = "auto_assign_applied"
                            logger.log_group_deselected(old_sel, world.elapsed)
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
                                              mode="M2", instant=True)
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
                            _apply_suggestion(world, proposed, logger, mode="M3", instant=True)
                            old_sel = list(selected_ids)
                            selected_ids  = set()
                            popup_drone_id = None
                            game_state["selected_ids"]   = selected_ids
                            game_state["popup_drone_id"] = None
                            game_state["last_action"]    = "auto_assign_applied"
                            logger.log_group_deselected(old_sel, world.elapsed)

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
                now_clashing = world.is_clashing
                if now_clashing and not prev_clashing:
                    logger.log_clash_start(world.elapsed, list(world.clashing_pairs))
                elif not now_clashing and prev_clashing:
                    logger.log_clash_end(world.elapsed, world.clash_seconds)
                prev_clashing = now_clashing
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
