from __future__ import annotations
import math
import sys
from typing import Dict, Optional, Set, Tuple

import pygame

from robot_world import RobotWorld, SPEED_MIN, SPEED_MAX, SWITCH_DURATION
from robot_renderer import RobotRenderer, PANEL_W
from game_logger import GameLogger
from agents.channel_agent import ChannelAdvisor


class _StudyExit(Exception):
    """Raised instead of sys.exit() when study_mode=True."""


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
) -> Optional[Dict]:
    _owns_display = screen is None
    if _owns_display:
        pygame.init()
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("Drone Channel Assignment")

    clock = pygame.time.Clock()
    window_w, window_h = screen.get_size()
    arena_w = window_w - PANEL_W

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

    mouse_down_pos:  Optional[Tuple[int, int]] = None
    drag_pos:        Optional[Tuple[int, int]] = None
    is_dragging:     bool = False
    DRAG_THRESHOLD = 5

    pending_suggestion:   Optional[Dict[int, str]] = None
    suggestion_overrides: Dict[int, str]           = {}
    pending_infeasible:   bool = False

    prev_clashing = False
    last_action:  Optional[str] = None
    result:       Optional[Dict] = None
    study_advance = False   # set True when user presses SPACE on ENDED in study_mode

    # ── Event loop ────────────────────────────────────────────────────────────
    try:
        while True:
            dt = clock.tick(60) / 1000.0
            dt = min(dt, 0.05)
            study_advance = False

            for event in pygame.event.get():

                # ── Quit / keys ───────────────────────────────────────────────
                if event.type == pygame.QUIT:
                    _handle_quit()

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        _handle_quit()

                    elif event.key == pygame.K_SPACE and state == "PAUSED":
                        state = "SETUP"
                        world._detect_edges()

                    elif event.key == pygame.K_SPACE and state == "SETUP":
                        if all(r.channel is not None for r in world.robots):
                            state = "PLAYING"
                            logger.log("play_started", elapsed=world.elapsed)

                    elif state == "ENDED":
                        if study_mode and event.key == pygame.K_SPACE:
                            study_advance = True
                        elif not study_mode:
                            if event.key == pygame.K_r:
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
                                prev_clashing        = False
                                last_action          = None
                                result               = None
                                logger.log_game_start(seed, n_robots, complexity, duration, v_min, v_max)
                            elif event.key == pygame.K_q:
                                _handle_quit()

                # ── Mouse button DOWN ─────────────────────────────────────────
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if state not in ("PLAYING", "SETUP"):
                        continue
                    mx, my = event.pos
                    instant = (state == "SETUP")

                    # ── Suggestion mode ───────────────────────────────────────
                    if pending_suggestion is not None:
                        if popup_drone_id is not None:
                            for ch, rect in renderer.suggestion_channel_btn_rects.items():
                                if rect.collidepoint(mx, my):
                                    suggestion_overrides[popup_drone_id] = ch
                                    if pending_suggestion.get(popup_drone_id) != ch:
                                        logger.log_suggestion_modified(
                                            popup_drone_id,
                                            pending_suggestion.get(popup_drone_id, ch),
                                            ch, world.elapsed,
                                        )
                                    break

                        if renderer.suggestion_apply_rect \
                                and renderer.suggestion_apply_rect.collidepoint(mx, my):
                            n_overrides = sum(
                                1 for did, ch in suggestion_overrides.items()
                                if pending_suggestion.get(did) != ch
                            )
                            logger.log_suggestion_applied(suggestion_overrides, n_overrides, world.elapsed)
                            _apply_suggestion(world, suggestion_overrides, logger,
                                              mode="M2", instant=instant)
                            pending_suggestion   = None
                            suggestion_overrides = {}
                            selected_ids         = set()
                            popup_drone_id       = None
                            last_action          = "suggestion_applied"
                            continue

                        if renderer.suggestion_cancel_rect \
                                and renderer.suggestion_cancel_rect.collidepoint(mx, my):
                            logger.log_suggestion_cancelled(world.elapsed)
                            pending_suggestion   = None
                            suggestion_overrides = {}
                            popup_drone_id       = None
                            continue

                        mouse_down_pos = (mx, my)
                        drag_pos       = (mx, my)
                        is_dragging    = False
                        continue

                    # ── HUD group-action buttons ──────────────────────────────
                    if selected_ids:
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
                            continue

                        if "auto_assign" in renderer.hud_button_rects \
                                and renderer.hud_button_rects["auto_assign"].collidepoint(mx, my):
                            current_channels = {r.id: r.channel for r in world.robots}
                            proposed, infeasible = advisor.suggest(
                                list(selected_ids), current_channels, world.edges,
                                near_pairs=list(world.warning_pairs),
                            )
                            logger.log_auto_assign_applied(list(selected_ids), proposed, infeasible, world.elapsed)
                            _apply_suggestion(world, proposed, logger, mode="M3", instant=instant)
                            selected_ids = set()
                            popup_drone_id = None
                            last_action    = "auto_assign_applied"
                            continue

                    # ── M1 popup channel buttons ──────────────────────────────
                    if popup_drone_id is not None and renderer.popup_rects:
                        for ch, rect in renderer.popup_rects.items():
                            if rect.collidepoint(mx, my):
                                robot = world.robots[popup_drone_id]
                                if instant:
                                    if ch != robot.channel:
                                        logger.log_switch_requested(
                                            popup_drone_id, robot.channel, ch, world.elapsed, mode="M1"
                                        )
                                        robot.channel      = ch
                                        robot.switching_to = None
                                        world._detect_edges()
                                elif robot.switching_to is None and ch != robot.channel:
                                    world.request_switch(popup_drone_id, ch)
                                    logger.log_switch_requested(
                                        popup_drone_id, robot.channel, ch, world.elapsed, mode="M1"
                                    )
                                last_action    = "M1_switch"
                                popup_drone_id = None
                                break
                        else:
                            if mx < arena_w:
                                mouse_down_pos = (mx, my)
                                drag_pos       = (mx, my)
                        continue

                    if mx < arena_w:
                        mouse_down_pos = (mx, my)
                        drag_pos       = (mx, my)
                        is_dragging    = False

                # ── Mouse MOTION ──────────────────────────────────────────────
                elif event.type == pygame.MOUSEMOTION:
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
                            for did, rect in renderer.suggestion_node_rects.items():
                                if rect.collidepoint(mx, my):
                                    popup_drone_id = did if did != popup_drone_id else None
                                    break
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
                        selected_ids = (selected_ids ^ new_sel) if ctrl else new_sel
                        popup_drone_id = None
                        if selected_ids:
                            logger.log_group_selected(list(selected_ids), "box", world.elapsed)
                            last_action = "group_selected"
                    else:
                        clicked = _drone_at((mx, my), world, arena_w)
                        if clicked is not None:
                            if ctrl:
                                if clicked in selected_ids:
                                    selected_ids.discard(clicked)
                                else:
                                    selected_ids.add(clicked)
                                popup_drone_id = None
                                if selected_ids:
                                    logger.log_group_selected(list(selected_ids), "ctrl_click", world.elapsed)
                                    last_action = "group_selected"
                            elif selected_ids:
                                selected_ids   = set()
                                popup_drone_id = clicked if clicked != popup_drone_id else None
                            else:
                                popup_drone_id = clicked if clicked != popup_drone_id else None
                        else:
                            selected_ids   = set()
                            popup_drone_id = None

                    mouse_down_pos = None; drag_pos = None; is_dragging = False

            # Exit game loop when user advances past ENDED in study mode
            if study_advance and result is not None:
                break

            # ── Simulation tick ───────────────────────────────────────────────
            if state == "PLAYING":
                world.update(dt)

                now_clashing = world.is_clashing
                if now_clashing and not prev_clashing:
                    logger.log_clash_start(world.elapsed, list(world.clashing_pairs))
                elif not now_clashing and prev_clashing:
                    logger.log_clash_end(world.elapsed, world.clash_seconds)
                prev_clashing = now_clashing

                if world.is_over():
                    state = "ENDED"
                    logger.log_game_end(world.elapsed, world.clash_seconds)
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

            renderer.draw_frame(
                world, state,
                popup_drone_id=popup_drone_id,
                selected_ids=selected_ids,
                drag_rect=drag_rect,
                suggestion=pending_suggestion,
                suggestion_overrides=suggestion_overrides,
                pending_infeasible=pending_infeasible,
            )

            if state == "ENDED" and study_mode:
                _draw_study_continue_hint(screen, renderer)

            pygame.display.flip()

    except _StudyExit:
        result = result or {
            "seed": seed, "complexity": complexity,
            "duration": world.duration, "elapsed": world.elapsed,
            "clash_seconds": world.clash_seconds,
            "clash_pct": 0.0, "completed": False,
        }
    finally:
        logger.close()

    if study_mode:
        return result
    return None


def _draw_study_continue_hint(screen: pygame.Surface, renderer: RobotRenderer) -> None:
    s = renderer.fonts["medium"].render("SPACE — continue to next trial", True, (180, 255, 180))
    screen.blit(s, s.get_rect(centerx=screen.get_width() // 2,
                               centery=screen.get_height() // 2 + 175))
