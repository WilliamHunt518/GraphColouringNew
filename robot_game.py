from __future__ import annotations
import datetime
import math
import sys
from typing import Dict, List, Optional, Set, Tuple

import pygame

import os
from screen_recorder import ScreenRecorder

from robot_world import (
    RobotWorld, SPEED_MIN, SPEED_MAX, SWITCH_DURATION,
    WARN_RADIUS, CONNECT_RADIUS, APPROACH_RADIUS, ROBOT_RADIUS, _REFERENCE_ARENA_W,
)
from robot_renderer import RobotRenderer, PANEL_W
from game_logger import GameLogger
from agents.channel_agent import ChannelAdvisor
from panel_window import DetachedPanelWindow, is_supported as panel_detach_supported, monitor_rect


class _StudyExit(Exception):
    """Raised instead of sys.exit() when study_mode=True."""


def _make_log_snapshot(world: RobotWorld, ids: list, proposed: dict):
    """Return log snapshot as (nodes, edges).
    nodes: list of (id, norm_x, norm_y, ch_before, ch_after)
    edges: list of (i, j) robot-ID pairs that are currently connected
    Positions are normalised relative to the bounding box of the involved drones.
    Returns None if ids is empty.
    """
    robots = [world.robots[did] for did in ids if did < len(world.robots)]
    if not robots:
        return None
    xs = [r.x for r in robots]
    ys = [r.y for r in robots]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    half_w = max((max(xs) - min(xs)) / 2 + world.arena_w * 0.04, world.arena_w * 0.12)
    half_h = max((max(ys) - min(ys)) / 2 + world.arena_h * 0.04, world.arena_h * 0.12)
    x_lo, y_lo = cx - half_w, cy - half_h
    id_set = {r.id for r in robots}
    nodes = [
        (r.id,
         (r.x - x_lo) / (2 * half_w),
         (r.y - y_lo) / (2 * half_h),
         r.channel,
         proposed.get(r.id, r.channel))
        for r in robots
    ]
    edges = [(i, j) for (i, j) in world.edges if i in id_set and j in id_set]
    return (nodes, edges)


# ── Windowed (single-monitor) layout constants ────────────────────────────────
WINDOWED_ARENA_W = 1200
WINDOWED_ARENA_H = 760
WINDOWED_ARENA_X = 60
WINDOWED_ARENA_Y = 60
WINDOWED_PANEL_W = 380
WINDOWED_PANEL_X = WINDOWED_ARENA_X + WINDOWED_ARENA_W + 8
WINDOWED_PANEL_Y = WINDOWED_ARENA_Y


# ── Helpers ───────────────────────────────────────────────────────────────────

def _drone_at(pos: Tuple[int, int], world: RobotWorld, arena_w: int) -> Optional[int]:
    mx, my = pos
    if mx >= arena_w:
        return None
    for r in world.robots:
        dx, dy = mx - r.x, my - r.y
        if math.sqrt(dx * dx + dy * dy) <= r.radius + 4:
            return r.id
    return None


def _make_drag_rect(
    start: Tuple[int, int], current: Tuple[int, int]
) -> Tuple[int, int, int, int]:
    x0, y0 = start
    x1, y1 = current
    return (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))


def _apply_suggestion(
    world: RobotWorld,
    channels: Dict[int, str],
    logger: GameLogger,
    mode: str,
    instant: bool = False,
) -> None:
    for drone_id, ch in channels.items():
        robot = world.robots[drone_id]
        if instant:
            if ch != robot.channel:
                logger.log_switch_requested(drone_id, robot.channel, ch, world.elapsed, mode=mode)
                robot.channel = ch
                robot.switching_to = None
        else:
            if ch != robot.channel and robot.switching_to is None:
                world.request_switch(drone_id, ch)
                logger.log_switch_requested(drone_id, robot.channel, ch, world.elapsed, mode=mode)
    if instant:
        world._detect_edges()


# ── Main game loop ────────────────────────────────────────────────────────────

def run_game(
    seed: int = 42,
    n_robots: int = 12,
    duration: float = 90.0,
    v_min: float = SPEED_MIN,
    v_max: float = SPEED_MAX,
    epsilon: float = 0.20,
    complexity: str = "medium",
    switch_duration: float = SWITCH_DURATION,
    study_mode: bool = False,
    output_dir: Optional[str] = None,
    screen: Optional[pygame.Surface] = None,
    arena_monitor: int = 0,
    panel_monitor: int = 1,
    agent_mode: str = "standard",
    windowed: bool = False,
    debug_mode: bool = False,
    record: bool = False,
) -> Optional[Dict]:
    _owns_display = screen is None
    if _owns_display:
        os.environ.setdefault('SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS', '0')
        os.environ.setdefault('SDL_MOUSE_FOCUS_CLICKTHROUGH', '1')
        if windowed:
            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{WINDOWED_ARENA_X},{WINDOWED_ARENA_Y}'
            pygame.init()
            os.environ.pop('SDL_VIDEO_WINDOW_POS', None)
            screen = pygame.display.set_mode((WINDOWED_ARENA_W, WINDOWED_ARENA_H), pygame.RESIZABLE)
            pygame.display.set_caption("Drone Channel Assignment — Arena")
        else:
            # Resolve monitor bounds BEFORE pygame.init() so SDL2 positions the
            # window correctly at creation — avoids Windows DX fullscreen
            # optimisations that trigger when a borderless window is repositioned
            # after creation to cover a monitor exactly.
            _ab = monitor_rect(arena_monitor)
            if _ab:
                os.environ['SDL_VIDEO_WINDOW_POS'] = f'{_ab[0]},{_ab[1]}'
            pygame.init()
            os.environ.pop('SDL_VIDEO_WINDOW_POS', None)
            if _ab:
                screen = pygame.display.set_mode((_ab[2], _ab[3]), pygame.NOFRAME)
            else:
                info = pygame.display.Info()
                screen = pygame.display.set_mode(
                    (info.current_w, info.current_h), pygame.NOFRAME
                )
            pygame.display.set_caption("Drone Channel Assignment")

    clock = pygame.time.Clock()
    window_w, window_h = screen.get_size()
    # Panel is always in a separate window, so arena uses the full screen width
    arena_w = window_w

    def make_world() -> RobotWorld:
        return RobotWorld(n_robots, seed, duration,
                          arena_w=arena_w, arena_h=window_h,
                          v_min=v_min, v_max=v_max,
                          switch_duration=switch_duration)

    log_dir  = output_dir or "logs"
    log_file = "game_events.jsonl" if output_dir else None
    logger   = GameLogger(output_dir=log_dir, filename=log_file)
    world    = make_world()
    renderer = RobotRenderer(screen)
    advisor  = ChannelAdvisor(epsilon=epsilon, seed=seed + 1000)

    logger.log_game_start(seed, n_robots, complexity, duration, v_min, v_max)

    def _handle_quit() -> None:
        logger.log_quit(world.elapsed, world.clash_seconds)
        logger.close()
        if study_mode:
            raise _StudyExit()
        if _owns_display:
            pygame.quit()
        sys.exit()

    # ── Game state ────────────────────────────────────────────────────────────
    state = "PAUSED"

    popup_drone_id:  Optional[int] = None
    selected_ids:    Set[int]      = set()

    mouse_down_pos:   Optional[Tuple[int, int]] = None
    drag_pos:         Optional[Tuple[int, int]] = None
    is_dragging:      bool = False
    DRAG_THRESHOLD  = 5
    panel_hover_pos:  Optional[Tuple[int, int]] = None

    pending_suggestion:   Optional[Dict[int, str]] = None
    suggestion_overrides: Dict[int, str]           = {}
    pending_infeasible:   bool = False

    prev_clash_pairs:   frozenset = frozenset()
    prev_warning_pairs: frozenset = frozenset()
    last_action:  Optional[str] = None
    result:       Optional[Dict] = None
    study_advance = False   # set True when user presses SPACE on ENDED in study_mode

    _debug_paused: bool = False

    # ── Recording state ───────────────────────────────────────────────────────
    _recorder:              ScreenRecorder = ScreenRecorder()
    _recording_frame_timer: float         = 0.0
    _RECORD_FPS = 30

    # Fixed physics timestep — decouples simulation from frame rate so that
    # identical seeds produce identical robot trajectories on any hardware.
    _SIM_DT = 1.0 / 60.0

    # ── Flexible-agent state ──────────────────────────────────────────────────
    _MONITOR_INTERVAL = 0.5
    _SUGGEST_REFIRE_DELAY = 3.0            # seconds after apply before re-suggesting
    drone_modes:    Dict[int, str]           = {}   # drone_id → "suggest" | "auto"
    agent_log:      list                     = []   # (elapsed, msg[, snapshot]) newest-last
    _monitor_timer: List[float]              = [0.0]
    _auto_cooldown: Dict[int, float]         = {}
    _flex_apply_ts: Dict[int, float]         = {}   # elapsed when suggestion last applied per drone

    # ── Flexible-agent monitoring tick ───────────────────────────────────────
    def _flex_tick(dt: float) -> None:
        nonlocal pending_suggestion, suggestion_overrides, pending_infeasible

        for did in list(_auto_cooldown):
            _auto_cooldown[did] -= dt
            if _auto_cooldown[did] <= 0:
                del _auto_cooldown[did]

        _monitor_timer[0] += dt
        if _monitor_timer[0] < _MONITOR_INTERVAL:
            return
        _monitor_timer[0] = 0.0

        if not drone_modes:
            return

        clashing_ids = {i for pair in world.clashing_pairs for i in pair}
        monitored_clashing = {did for did in drone_modes if did in clashing_ids}
        if not monitored_clashing:
            return

        # Connected components among all monitored drones via active edges
        monitored_set = set(drone_modes)
        adj: Dict[int, Set[int]] = {d: set() for d in monitored_set}
        for i, j in world.edges:
            if i in monitored_set and j in monitored_set:
                adj[i].add(j)
                adj[j].add(i)

        visited: Set[int] = set()
        components: List[Set[int]] = []
        for start in monitored_set:
            if start in visited:
                continue
            comp: Set[int] = set()
            stack = [start]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                comp.add(n)
                stack.extend(adj[n] - visited)
            components.append(comp)

        current_channels = {r.id: r.channel for r in world.robots if r.channel}

        for comp in components:
            if not (comp & monitored_clashing):
                continue

            modes_in_comp = {drone_modes[d] for d in comp}

            if "auto" in modes_in_comp and "suggest" in modes_in_comp:
                # Mixed component: handle each subgroup independently.
                # The other subgroup's channels are treated as fixed neighbours
                # by advisor.suggest() because they are not in selected_ids.

                # Auto subgroup — apply immediately
                auto_sub = [d for d in comp
                            if drone_modes.get(d) == "auto"
                            and d not in _auto_cooldown
                            and world.robots[d].switching_to is None]
                if auto_sub:
                    proposed, _ = advisor.suggest(
                        auto_sub, current_channels, list(world.edges),
                        near_pairs=list(world.warning_pairs),
                    )
                    _apply_suggestion(world, proposed, logger, mode="flex_auto_mixed", instant=False)
                    for did in auto_sub:
                        _auto_cooldown[did] = world.switch_duration + 0.5
                    ids_str = ",".join(f"D{d}" for d in sorted(auto_sub))
                    id_set  = set(auto_sub)
                    n_before = sum(1 for p in world.clashing_pairs if p[0] in id_set or p[1] in id_set)
                    snap    = _make_log_snapshot(world, auto_sub, {})
                    agent_log.append((world.elapsed, f"{world.elapsed:.1f}s  {ids_str}: auto-fixed", snap, list(auto_sub), -n_before))
                    if len(agent_log) > 50:
                        agent_log.pop(0)
                    logger.log_auto_assign_applied(auto_sub, proposed, False, world.elapsed)

                # Suggest subgroup — surface suggestion if none is already pending
                suggest_sub = [d for d in comp if drone_modes.get(d) == "suggest"]
                if suggest_sub and pending_suggestion is None \
                        and not any(d in _auto_cooldown for d in suggest_sub) \
                        and not any(
                            world.elapsed - _flex_apply_ts.get(d, -9999) < _SUGGEST_REFIRE_DELAY
                            for d in suggest_sub
                        ):
                    proposed, infeasible = advisor.suggest(
                        suggest_sub, current_channels, list(world.edges),
                        near_pairs=list(world.warning_pairs),
                    )
                    pending_suggestion   = proposed
                    suggestion_overrides = dict(proposed)
                    pending_infeasible   = infeasible
                    agent_log.append((world.elapsed, f"{world.elapsed:.1f}s  group: suggestion shown"))
                    if len(agent_log) > 50:
                        agent_log.pop(0)
                    logger.log_suggestion_shown(suggest_sub, proposed, infeasible, world.elapsed)

            elif "auto" in modes_in_comp:
                eligible = [d for d in comp
                            if d not in _auto_cooldown
                            and world.robots[d].switching_to is None]
                if not eligible:
                    continue
                proposed, _ = advisor.suggest(
                    eligible, current_channels, list(world.edges),
                    near_pairs=list(world.warning_pairs),
                )
                _apply_suggestion(world, proposed, logger, mode="flex_auto", instant=False)
                for did in eligible:
                    _auto_cooldown[did] = world.switch_duration + 0.5
                ids_str  = ",".join(f"D{d}" for d in sorted(eligible))
                id_set   = set(eligible)
                n_before = sum(1 for p in world.clashing_pairs if p[0] in id_set or p[1] in id_set)
                snap     = _make_log_snapshot(world, eligible, {})
                agent_log.append((world.elapsed, f"{world.elapsed:.1f}s  {ids_str}: auto-fixed", snap, list(eligible), -n_before))
                if len(agent_log) > 50:
                    agent_log.pop(0)
                logger.log_auto_assign_applied(eligible, proposed, False, world.elapsed)

            elif "suggest" in modes_in_comp and pending_suggestion is None \
                    and not any(d in _auto_cooldown for d in comp) \
                    and not any(
                        world.elapsed - _flex_apply_ts.get(d, -9999) < _SUGGEST_REFIRE_DELAY
                        for d in comp
                    ):
                proposed, infeasible = advisor.suggest(
                    list(comp), current_channels, list(world.edges),
                    near_pairs=list(world.warning_pairs),
                )
                pending_suggestion   = proposed
                suggestion_overrides = dict(proposed)
                pending_infeasible   = infeasible
                agent_log.append((world.elapsed,
                                   f"{world.elapsed:.1f}s  group: suggestion shown"))
                if len(agent_log) > 50:
                    agent_log.pop(0)
                logger.log_suggestion_shown(list(comp), proposed, infeasible, world.elapsed)

    # ── Open the panel window immediately on the chosen monitor ───────────────
    panel_detached = False
    _panel_win: Optional[DetachedPanelWindow] = None

    if panel_detach_supported():
        try:
            if windowed:
                _ph = screen.get_height()
                _panel_win = DetachedPanelWindow(
                    WINDOWED_PANEL_W, _ph,
                    pos_x=WINDOWED_PANEL_X, pos_y=WINDOWED_PANEL_Y,
                )
            else:
                _pb = monitor_rect(panel_monitor)
                if _pb is None:
                    n_mon = pygame.display.get_num_displays()
                    pmon  = min(panel_monitor, n_mon - 1)
                    _raw  = pygame.display.get_display_bounds(pmon)
                    _pb   = (_raw[0], _raw[1], _raw[2], _raw[3])
                _panel_win = DetachedPanelWindow(_pb[2], _pb[3], pos_x=_pb[0], pos_y=_pb[1])
            renderer.set_panel_surface(_panel_win.get_fresh_surface())
            panel_detached = True
            logger.log("panel_opened", monitor=panel_monitor, elapsed=0.0)
        except Exception as exc:
            logger.log("panel_open_failed", reason=str(exc), elapsed=0.0)

    # ── Event loop ────────────────────────────────────────────────────────────
    def _handle_panel_click(mx: int, my: int, instant: bool) -> bool:
        """
        Process a click at (mx, my) in panel-surface coordinates.
        Returns True if the click was consumed by the panel.
        """
        nonlocal pending_suggestion, suggestion_overrides, pending_infeasible
        nonlocal popup_drone_id, selected_ids, last_action

        # ── Suggestion panel ───────────────────────────────────────────────
        if pending_suggestion is not None:
            if popup_drone_id is not None:
                for ch, rect in renderer.suggestion_channel_btn_rects.items():
                    if rect.collidepoint(mx, my):
                        old_ch = suggestion_overrides.get(popup_drone_id)
                        suggestion_overrides[popup_drone_id] = ch
                        if pending_suggestion.get(popup_drone_id) != ch:
                            logger.log_suggestion_modified(
                                popup_drone_id,
                                pending_suggestion.get(popup_drone_id, ch),
                                ch, world.elapsed,
                            )
                        if old_ch != ch:
                            logger.log("suggestion_channel_picked",
                                       drone_id=popup_drone_id, channel=ch,
                                       elapsed=world.elapsed)
                        return True

            if renderer.suggestion_apply_rect \
                    and renderer.suggestion_apply_rect.collidepoint(mx, my):
                n_overrides = sum(
                    1 for did, ch in suggestion_overrides.items()
                    if pending_suggestion.get(did) != ch
                )
                logger.log_suggestion_applied(suggestion_overrides, n_overrides, world.elapsed)
                _apply_suggestion(world, suggestion_overrides, logger,
                                  mode="M2", instant=instant)
                if agent_mode == "flexible":
                    for did in suggestion_overrides:
                        _auto_cooldown[did] = world.switch_duration + 0.5
                        _flex_apply_ts[did] = world.elapsed
                pending_suggestion   = None
                suggestion_overrides = {}
                selected_ids         = set()
                popup_drone_id       = None
                last_action          = "suggestion_applied"
                return True

            if renderer.suggestion_cancel_rect \
                    and renderer.suggestion_cancel_rect.collidepoint(mx, my):
                logger.log_suggestion_cancelled(world.elapsed)
                pending_suggestion   = None
                suggestion_overrides = {}
                popup_drone_id       = None
                if agent_mode == "flexible":
                    for _ds, _dm in drone_modes.items():
                        if _dm == "suggest":
                            _flex_apply_ts[_ds] = world.elapsed
                return True

            # No suggestion button hit — fall through so mode buttons still work.

        # ── HUD group-action buttons ───────────────────────────────────────
        if agent_mode == "flexible":
            # Mode buttons apply to the selected drones; if none are selected they
            # fall back to the suggestion drones so the user can change autonomy
            # level even while a suggestion is being shown.
            flex_target = selected_ids if selected_ids else (
                set(pending_suggestion.keys()) if pending_suggestion else set()
            )
            if flex_target:
                if "watch_suggest" in renderer.hud_button_rects \
                        and renderer.hud_button_rects["watch_suggest"].collidepoint(mx, my):
                    for did in list(flex_target):
                        if drone_modes.get(did) == "suggest":
                            del drone_modes[did]
                        else:
                            drone_modes[did] = "suggest"
                    logger.log("watch_mode_set", drones=list(flex_target),
                               mode="suggest", elapsed=world.elapsed)
                    active_watch = [d for d in flex_target if drone_modes.get(d) == "suggest"]
                    if active_watch:
                        current_channels = {r.id: r.channel for r in world.robots}
                        proposed, infeasible = advisor.suggest(
                            active_watch, current_channels, world.edges,
                            near_pairs=list(world.warning_pairs),
                        )
                        logger.log_suggestion_requested(active_watch, current_channels, world.elapsed)
                        logger.log_suggestion_shown(active_watch, proposed, infeasible, world.elapsed)
                        pending_suggestion   = proposed
                        suggestion_overrides = dict(proposed)
                        pending_infeasible   = infeasible
                        popup_drone_id       = None
                        last_action          = "suggestion_shown"
                    return True

                if "watch_auto" in renderer.hud_button_rects \
                        and renderer.hud_button_rects["watch_auto"].collidepoint(mx, my):
                    for did in list(flex_target):
                        if drone_modes.get(did) == "auto":
                            del drone_modes[did]
                        else:
                            drone_modes[did] = "auto"
                    logger.log("watch_mode_set", drones=list(flex_target),
                               mode="auto", elapsed=world.elapsed)
                    active_watch = [d for d in flex_target if drone_modes.get(d) == "auto"]
                    if active_watch:
                        current_channels = {r.id: r.channel for r in world.robots}
                        proposed, infeasible = advisor.suggest(
                            active_watch, current_channels, world.edges,
                            near_pairs=list(world.warning_pairs),
                        )
                        logger.log_auto_assign_applied(active_watch, proposed, infeasible, world.elapsed)
                        _apply_suggestion(world, proposed, logger, mode="flex_watch_setup", instant=(state == "SETUP"))
                        for did in active_watch:
                            _auto_cooldown[did] = world.switch_duration + 0.5
                        old_sel = list(flex_target)
                        selected_ids   = set()
                        popup_drone_id = None
                        last_action    = "auto_assign_applied"
                        logger.log_group_deselected(old_sel, world.elapsed)
                    return True

                if "unwatch" in renderer.hud_button_rects \
                        and renderer.hud_button_rects["unwatch"].collidepoint(mx, my):
                    cleared = [d for d in flex_target if d in drone_modes]
                    for did in cleared:
                        del drone_modes[did]
                    # Switching to manual dismisses any suggestion for those drones
                    if pending_suggestion is not None and \
                            set(pending_suggestion.keys()) <= set(cleared):
                        pending_suggestion   = None
                        suggestion_overrides = {}
                        pending_infeasible   = False
                    old_sel = list(selected_ids)
                    selected_ids   = set()
                    popup_drone_id = None
                    if old_sel:
                        logger.log_group_deselected(old_sel, world.elapsed)
                    logger.log("watch_cleared", drones=cleared, elapsed=world.elapsed)
                    return True

        elif selected_ids:
            # Non-flex mode: Suggest and Auto-assign require an explicit selection.
            if "suggest" in renderer.hud_button_rects \
                    and renderer.hud_button_rects["suggest"].collidepoint(mx, my):
                current_channels = {r.id: r.channel for r in world.robots}
                proposed, infeasible = advisor.suggest(
                    list(selected_ids), current_channels, world.edges,
                    near_pairs=list(world.warning_pairs),
                )
                logger.log_suggestion_requested(list(selected_ids), current_channels, world.elapsed)
                logger.log_suggestion_shown(list(selected_ids), proposed, infeasible, world.elapsed)
                pending_suggestion   = proposed
                suggestion_overrides = dict(proposed)
                pending_infeasible   = infeasible
                popup_drone_id       = None
                last_action          = "suggestion_shown"
                return True

            if "auto_assign" in renderer.hud_button_rects \
                    and renderer.hud_button_rects["auto_assign"].collidepoint(mx, my):
                current_channels = {r.id: r.channel for r in world.robots}
                proposed, infeasible = advisor.suggest(
                    list(selected_ids), current_channels, world.edges,
                    near_pairs=list(world.warning_pairs),
                )
                logger.log_auto_assign_applied(list(selected_ids), proposed, infeasible, world.elapsed)
                _apply_suggestion(world, proposed, logger, mode="M3", instant=instant)
                old_sel  = list(selected_ids)
                selected_ids   = set()
                popup_drone_id = None
                last_action    = "auto_assign_applied"
                logger.log_group_deselected(old_sel, world.elapsed)
                return True

        return False

    _WINDOWRESIZED = getattr(pygame, 'WINDOWRESIZED', None)

    try:
        while True:
            dt = clock.tick(60) / 1000.0
            dt = min(dt, 0.05)
            study_advance = False

            raw_events: List[pygame.event.Event] = pygame.event.get()

            # If panel is detached, separate panel-window events
            panel_events: List[pygame.event.Event] = []
            if panel_detached and _panel_win is not None:
                panel_events, raw_events = _panel_win.filter_events(raw_events)

            for event in raw_events:

                # ── Quit / keys ───────────────────────────────────────────────
                if event.type == pygame.QUIT:
                    _handle_quit()

                elif event.type == pygame.KEYDOWN:
                    logger.log("key_down", key=event.key, key_name=pygame.key.name(event.key),
                               state=state, elapsed=world.elapsed)
                    if event.key == pygame.K_ESCAPE:
                        _handle_quit()

                    elif event.key == pygame.K_SPACE and state == "PAUSED":
                        state = "SETUP"
                        world._detect_edges()

                    elif event.key == pygame.K_SPACE and state == "SETUP":
                        if all(r.channel is not None for r in world.robots):
                            state = "PLAYING"
                            logger.log("play_started", elapsed=world.elapsed)
                            if record and not _recorder.active:
                                _aw, _ah = screen.get_size()
                                _rw, _rh = _aw, _ah
                                if panel_detached and _panel_win is not None:
                                    _rps = _panel_win.get_fresh_surface()
                                    _rw += _rps.get_width()
                                    _rh  = max(_rh, _rps.get_height())
                                _ts     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                _recdir = os.path.join(log_dir, "recordings")
                                os.makedirs(_recdir, exist_ok=True)
                                _recpath = os.path.join(_recdir, f"recording_{_ts}.mp4")
                                _ok      = _recorder.start(_recpath, _rw, _rh, fps=_RECORD_FPS)
                                logger.log("recording_started" if _ok else "recording_failed",
                                           path=_recpath, elapsed=world.elapsed)

                    elif event.key == pygame.K_p and state == "PLAYING" and debug_mode:
                        _debug_paused = not _debug_paused
                        logger.log("debug_pause_toggled", paused=_debug_paused,
                                   elapsed=world.elapsed)

                    elif state == "ENDED":
                        if study_mode and event.key == pygame.K_SPACE:
                            study_advance = True
                        elif not study_mode:
                            if event.key == pygame.K_r:
                                if _recorder.active:
                                    _recorder.stop()
                                _recording_frame_timer = 0.0
                                world   = make_world()
                                advisor = ChannelAdvisor(epsilon=epsilon, seed=seed + 1000)
                                state                = "PAUSED"
                                popup_drone_id       = None
                                selected_ids         = set()
                                pending_suggestion   = None
                                suggestion_overrides = {}
                                pending_infeasible   = False
                                mouse_down_pos       = None
                                drag_pos             = None
                                is_dragging          = False
                                prev_clash_pairs      = frozenset()
                                prev_warning_pairs    = frozenset()
                                last_action           = None
                                result               = None
                                drone_modes.clear()
                                agent_log.clear()
                                _monitor_timer[0]  = 0.0
                                _auto_cooldown.clear()
                                _debug_paused      = False
                                logger.log_game_start(seed, n_robots, complexity, duration, v_min, v_max)
                            elif event.key == pygame.K_q:
                                _handle_quit()

                # ── Arena window resize (windowed mode only) ──────────────────
                elif windowed and (
                    event.type == pygame.VIDEORESIZE or
                    (_WINDOWRESIZED is not None and event.type == _WINDOWRESIZED)
                ):
                    # Use get_surface() rather than event dimensions — avoids
                    # false triggers when SDL2 fires resize events for the
                    # panel window and they bleed into the arena event queue.
                    screen = pygame.display.get_surface()
                    new_w, new_h = screen.get_size()
                    old_w, old_h = arena_w, window_h
                    if new_w != old_w or new_h != old_h:
                        scale_x, scale_y = new_w / old_w, new_h / old_h
                        new_scale = new_w / _REFERENCE_ARENA_W
                        world.robot_radius    = max(6, round(ROBOT_RADIUS    * new_scale))
                        world.warn_radius     = WARN_RADIUS     * new_scale
                        world.connect_radius  = CONNECT_RADIUS  * new_scale
                        world.approach_radius = APPROACH_RADIUS * new_scale
                        world.arena_w         = new_w
                        world.arena_h         = new_h
                        for r in world.robots:
                            r.x      = max(world.robot_radius,
                                           min(new_w - world.robot_radius, r.x * scale_x))
                            r.y      = max(world.robot_radius,
                                           min(new_h - world.robot_radius, r.y * scale_y))
                            r.radius = world.robot_radius
                        arena_w  = new_w
                        window_w = new_w
                        window_h = new_h
                        renderer.handle_resize(screen)

                # ── Mouse button DOWN ─────────────────────────────────────────
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if state not in ("PLAYING", "SETUP"):
                        logger.log("click_ignored", x=event.pos[0], y=event.pos[1],
                                   state=state, elapsed=world.elapsed)
                        continue
                    mx, my = event.pos
                    instant = (state == "SETUP")

                    # ── M1 popup channel buttons ──────────────────────────────
                    if popup_drone_id is not None and renderer.popup_rects:
                        for ch, rect in renderer.popup_rects.items():
                            if rect.collidepoint(mx, my):
                                robot = world.robots[popup_drone_id]
                                _m1_changed = False
                                if instant:
                                    if ch != robot.channel:
                                        logger.log_switch_requested(
                                            popup_drone_id, robot.channel, ch, world.elapsed, mode="M1"
                                        )
                                        robot.channel      = ch
                                        robot.switching_to = None
                                        world._detect_edges()
                                        _m1_changed = True
                                elif robot.switching_to is None and ch != robot.channel:
                                    world.request_switch(popup_drone_id, ch)
                                    logger.log_switch_requested(
                                        popup_drone_id, robot.channel, ch, world.elapsed, mode="M1"
                                    )
                                    _m1_changed = True
                                elif ch == robot.channel:
                                    logger.log("m1_same_channel_clicked",
                                               drone_id=popup_drone_id, channel=ch,
                                               elapsed=world.elapsed)
                                if _m1_changed and pending_suggestion is not None:
                                    pending_suggestion   = None
                                    suggestion_overrides = {}
                                    pending_infeasible   = False
                                old_popup      = popup_drone_id
                                last_action    = "M1_switch"
                                popup_drone_id = None
                                logger.log_popup_dismissed(old_popup, world.elapsed)
                                break
                        else:
                            if mx < renderer.arena_w:
                                mouse_down_pos = (mx, my)
                                drag_pos       = (mx, my)
                        continue

                    if mx < renderer.arena_w:
                        mouse_down_pos = (mx, my)
                        drag_pos       = (mx, my)
                        is_dragging    = False

                # ── Mouse MOTION ──────────────────────────────────────────────
                elif event.type == pygame.MOUSEMOTION:
                    panel_hover_pos = None   # mouse in arena — clear panel highlight
                    if mouse_down_pos is not None and pygame.mouse.get_pressed()[0]:
                        mx, my = event.pos
                        drag_pos = (mx, my)
                        dx = mx - mouse_down_pos[0]
                        dy = my - mouse_down_pos[1]
                        if math.sqrt(dx * dx + dy * dy) > DRAG_THRESHOLD:
                            is_dragging = True

                # ── Mouse button UP ───────────────────────────────────────────
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if state not in ("PLAYING", "SETUP"):
                        mouse_down_pos = None; drag_pos = None; is_dragging = False
                        continue

                    if pending_suggestion is not None:
                        if mouse_down_pos is not None and not is_dragging:
                            mx, my = event.pos
                            panel_node_hit = False
                            for did, rect in renderer.suggestion_node_rects.items():
                                if rect.collidepoint(mx, my):
                                    prev_popup = popup_drone_id
                                    popup_drone_id = did if did != popup_drone_id else None
                                    if popup_drone_id is not None:
                                        logger.log_suggestion_node_selected(did, world.elapsed)
                                    elif prev_popup is not None:
                                        logger.log_suggestion_node_deselected(prev_popup, world.elapsed)
                                    panel_node_hit = True
                                    break
                            if not panel_node_hit and mx < renderer.arena_w:
                                clicked = _drone_at((mx, my), world, renderer.arena_w)
                                ctrl = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)
                                if agent_mode == "flexible":
                                    if clicked is not None:
                                        # Select the drone and open its popup; keep suggestion alive
                                        if ctrl:
                                            if clicked in selected_ids:
                                                selected_ids.discard(clicked)
                                            else:
                                                selected_ids.add(clicked)
                                            popup_drone_id = None
                                        else:
                                            selected_ids = {clicked}
                                            new_popup = clicked if clicked != popup_drone_id else None
                                            if popup_drone_id is not None and new_popup is None:
                                                logger.log_popup_dismissed(popup_drone_id, world.elapsed)
                                            elif new_popup is not None:
                                                logger.log_popup_opened(new_popup, world.elapsed)
                                            popup_drone_id = new_popup
                                    else:
                                        # Empty area: deselect but keep suggestion alive
                                        if selected_ids:
                                            logger.log_group_deselected(list(selected_ids), world.elapsed)
                                            selected_ids = set()
                                        if popup_drone_id is not None:
                                            logger.log_popup_dismissed(popup_drone_id, world.elapsed)
                                            popup_drone_id = None
                                else:
                                    # Non-flex: any arena click cancels the suggestion
                                    logger.log_suggestion_cancelled(world.elapsed)
                                    pending_suggestion   = None
                                    suggestion_overrides = {}
                                    pending_infeasible   = False
                                    if clicked is not None:
                                        popup_drone_id = clicked if clicked != popup_drone_id else None
                                        if popup_drone_id is not None:
                                            logger.log_popup_opened(popup_drone_id, world.elapsed)
                                        else:
                                            logger.log_popup_dismissed(clicked, world.elapsed)
                        mouse_down_pos = None; drag_pos = None; is_dragging = False
                        continue

                    if mouse_down_pos is None:
                        is_dragging = False
                        continue

                    mx, my = event.pos
                    ctrl = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)

                    if is_dragging and drag_pos is not None:
                        x0, y0 = mouse_down_pos
                        x1, y1 = drag_pos
                        box = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
                        new_sel = {r.id for r in world.robots if box.collidepoint(int(r.x), int(r.y))}
                        prev_sel = list(selected_ids)
                        selected_ids = (selected_ids ^ new_sel) if ctrl else new_sel
                        popup_drone_id = None
                        if selected_ids:
                            logger.log_group_selected(list(selected_ids), "box", world.elapsed)
                            last_action = "group_selected"
                        elif prev_sel:
                            logger.log_group_deselected(prev_sel, world.elapsed)
                    else:
                        clicked = _drone_at((mx, my), world, renderer.arena_w)
                        if clicked is not None:
                            if ctrl:
                                if clicked in selected_ids:
                                    selected_ids.discard(clicked)
                                    logger.log("ctrl_drone_deselected", drone_id=clicked,
                                               selected=list(selected_ids), elapsed=world.elapsed)
                                else:
                                    selected_ids.add(clicked)
                                    logger.log("ctrl_drone_selected", drone_id=clicked,
                                               selected=list(selected_ids), elapsed=world.elapsed)
                                popup_drone_id = None
                                if selected_ids:
                                    logger.log_group_selected(list(selected_ids), "ctrl_click", world.elapsed)
                                    last_action = "group_selected"
                            elif selected_ids:
                                old_sel        = list(selected_ids)
                                selected_ids   = set()
                                new_popup      = clicked if clicked != popup_drone_id else None
                                if popup_drone_id is not None and new_popup is None:
                                    logger.log_popup_dismissed(popup_drone_id, world.elapsed)
                                popup_drone_id = new_popup
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
                        else:
                            prev_sel = list(selected_ids)
                            prev_popup = popup_drone_id
                            selected_ids   = set()
                            popup_drone_id = None
                            if prev_sel:
                                logger.log_group_deselected(prev_sel, world.elapsed)
                            if prev_popup is not None:
                                logger.log_popup_dismissed(prev_popup, world.elapsed)
                            logger.log_arena_click_miss(mx, my, world.elapsed)

                    mouse_down_pos = None; drag_pos = None; is_dragging = False

            # ── Events from detached panel window ─────────────────────────────
            for event in panel_events:
                if _WINDOWRESIZED and event.type == _WINDOWRESIZED \
                        and windowed and _panel_win is not None:
                    _panel_win.handle_resize(event.x, event.y)
                    renderer.set_panel_surface(_panel_win.get_fresh_surface())
                elif event.type == pygame.MOUSEMOTION:
                    panel_hover_pos = event.pos
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if state not in ("PLAYING", "SETUP"):
                        continue
                    mx, my = event.pos
                    instant = (state == "SETUP")
                    _handle_panel_click(mx, my, instant)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if pending_suggestion is not None:
                        mx, my = event.pos
                        for did, rect in renderer.suggestion_node_rects.items():
                            if rect.collidepoint(mx, my):
                                prev_popup = popup_drone_id
                                popup_drone_id = did if did != popup_drone_id else None
                                if popup_drone_id is not None:
                                    logger.log_suggestion_node_selected(did, world.elapsed)
                                elif prev_popup is not None:
                                    logger.log_suggestion_node_deselected(prev_popup, world.elapsed)
                                break

            # Exit game loop when user advances past ENDED in study mode
            if study_advance and result is not None:
                break

            # ── Simulation tick ───────────────────────────────────────────────
            if state == "PLAYING" and not _debug_paused:
                world.update(_SIM_DT)
                if agent_mode == "flexible":
                    _flex_tick(_SIM_DT)
                    # Auto-dismiss a pending suggestion when its clash is gone.
                    # Use effective channels (switching_to if in-flight, else current)
                    # so the panel dismisses as soon as a fix is underway, not after it completes.
                    if pending_suggestion is not None:
                        sugg_ids = set(pending_suggestion.keys())
                        eff = {r.id: (r.switching_to if r.switching_to is not None else r.channel)
                               for r in world.robots}
                        future_clash_ids = set()
                        for i, j in world.edges:
                            ec_i = eff.get(i)
                            ec_j = eff.get(j)
                            if ec_i is not None and ec_j is not None and ec_i == ec_j:
                                future_clash_ids.add(i)
                                future_clash_ids.add(j)
                        if not any(d in future_clash_ids for d in sugg_ids):
                            logger.log("suggestion_auto_dismissed",
                                       reason="clash_resolved", elapsed=world.elapsed)
                            pending_suggestion   = None
                            suggestion_overrides = {}
                            pending_infeasible   = False

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

                if world.is_over():
                    state = "ENDED"
                    logger.log_game_end(world.elapsed, world.clash_seconds)
                    if _recorder.active:
                        _recorder.stop()
                        logger.log("recording_stopped", elapsed=world.elapsed)
                    pct    = world.clash_seconds / world.duration * 100 if world.duration else 0.0
                    result = {
                        "seed": seed, "complexity": complexity,
                        "duration": world.duration, "elapsed": world.elapsed,
                        "clash_seconds": world.clash_seconds,
                        "clash_pct": round(pct, 1), "completed": True,
                    }

            # ── Render ────────────────────────────────────────────────────────
            drag_rect = (
                _make_drag_rect(mouse_down_pos, drag_pos)
                if is_dragging and mouse_down_pos and drag_pos
                else None
            )

            # Refresh the panel surface each frame — it becomes stale after flip()
            if panel_detached and _panel_win is not None:
                renderer.refresh_panel_surface(_panel_win.get_fresh_surface())

            renderer.draw_frame(
                world, state,
                popup_drone_id=popup_drone_id,
                selected_ids=selected_ids,
                drag_rect=drag_rect,
                suggestion=pending_suggestion,
                suggestion_overrides=suggestion_overrides,
                pending_infeasible=pending_infeasible,
                panel_detached=panel_detached,
                drone_modes=drone_modes if agent_mode == "flexible" else None,
                agent_log=agent_log[-6:] if agent_mode == "flexible" else None,
                panel_hover_pos=panel_hover_pos,
            )

            if state == "ENDED" and study_mode:
                _draw_study_continue_hint(screen, renderer)

            if _debug_paused:
                _draw_debug_paused_overlay(screen, renderer)

            pygame.display.flip()
            if panel_detached and _panel_win is not None:
                _panel_win.flip()

            # ── Recording frame capture ───────────────────────────────────────
            if _recorder.active:
                _recording_frame_timer += dt
                if _recording_frame_timer >= 1.0 / _RECORD_FPS:
                    _recording_frame_timer -= 1.0 / _RECORD_FPS
                    _aw, _ah = screen.get_size()
                    comp = pygame.Surface((_recorder._w, _recorder._h))
                    comp.blit(screen, (0, 0))
                    if panel_detached and _panel_win is not None:
                        comp.blit(_panel_win.get_fresh_surface(), (_aw, 0))
                    # Arena cursor ring
                    _acx, _acy = pygame.mouse.get_pos()
                    pygame.draw.circle(comp, (255, 255, 255), (_acx, _acy), 9, 2)
                    pygame.draw.circle(comp, (0, 0, 0),       (_acx, _acy), 5, 1)
                    # Panel cursor ring
                    if panel_hover_pos is not None and panel_detached:
                        _pcx = panel_hover_pos[0] + _aw
                        _pcy = panel_hover_pos[1]
                        pygame.draw.circle(comp, (255, 230, 160), (_pcx, _pcy), 9, 2)
                        pygame.draw.circle(comp, (0, 0, 0),       (_pcx, _pcy), 5, 1)
                    _recorder.add_frame(comp)

    except _StudyExit:
        result = result or {
            "seed": seed, "complexity": complexity,
            "duration": world.duration, "elapsed": world.elapsed,
            "clash_seconds": world.clash_seconds,
            "clash_pct": 0.0, "completed": False,
        }
    finally:
        if _recorder.active:
            _recorder.stop()
        if _panel_win is not None:
            _panel_win.close()
        logger.close()

    if study_mode:
        return result
    return None


def _draw_study_continue_hint(screen: pygame.Surface, renderer: RobotRenderer) -> None:
    s = renderer.fonts["medium"].render("SPACE — continue to next trial", True, (180, 255, 180))
    screen.blit(s, s.get_rect(centerx=screen.get_width() // 2,
                               centery=screen.get_height() // 2 + 175))


def _draw_debug_paused_overlay(screen: pygame.Surface, renderer: RobotRenderer) -> None:
    w = screen.get_width()
    banner = pygame.Surface((w, 38), pygame.SRCALPHA)
    banner.fill((190, 30, 30, 210))
    screen.blit(banner, (0, 0))
    s = renderer.fonts["medium"].render("⏸  DEBUG PAUSED — P to resume", True, (255, 210, 210))
    screen.blit(s, s.get_rect(centerx=w // 2, centery=19))
