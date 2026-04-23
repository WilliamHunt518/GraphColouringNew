from __future__ import annotations
import math
import sys
from typing import Dict, List, Optional, Set, Tuple

import pygame

from robot_world import RobotWorld, SPEED_MIN, SPEED_MAX
from robot_renderer import RobotRenderer, PANEL_W
from game_logger import GameLogger
from agents.channel_agent import ChannelAdvisor


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
) -> None:
    for drone_id, ch in channels.items():
        robot = world.robots[drone_id]
        if ch != robot.channel and robot.switching_to is None:
            world.request_switch(drone_id, ch)
            logger.log_switch_requested(drone_id, robot.channel, ch, world.elapsed, mode=mode)


def _quit(logger: GameLogger, world: RobotWorld) -> None:
    logger.log_quit(world.elapsed, world.clash_seconds)
    logger.close()
    pygame.quit()
    sys.exit()


# ── Main game loop ────────────────────────────────────────────────────────────

def run_game(
    seed: int = 42,
    n_robots: int = 12,
    duration: float = 90.0,
    v_min: float = SPEED_MIN,
    v_max: float = SPEED_MAX,
    epsilon: float = 0.20,
    complexity: str = "medium",
) -> None:
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("Drone Channel Assignment")
    clock = pygame.time.Clock()

    window_w, window_h = screen.get_size()
    arena_w = window_w - PANEL_W

    def make_world() -> RobotWorld:
        return RobotWorld(n_robots, seed, duration,
                          arena_w=arena_w, arena_h=window_h,
                          v_min=v_min, v_max=v_max)

    logger  = GameLogger()
    world   = make_world()
    renderer = RobotRenderer(screen)
    advisor  = ChannelAdvisor(epsilon=epsilon, seed=seed + 1000)

    logger.log_game_start(seed, n_robots, complexity, duration, v_min, v_max)

    # ── Game state ────────────────────────────────────────────────────────────
    state = "PAUSED"

    # M1 single-drone popup
    popup_drone_id: Optional[int] = None

    # M2/M3 group selection
    selected_ids: Set[int] = set()

    # Drag / bounding-box selection
    mouse_down_pos: Optional[Tuple[int, int]] = None
    drag_pos:       Optional[Tuple[int, int]] = None
    is_dragging: bool = False
    DRAG_THRESHOLD = 5

    # Suggestion (M2 review panel)
    pending_suggestion:  Optional[Dict[int, str]] = None
    suggestion_overrides: Dict[int, str] = {}
    pending_infeasible: bool = False

    prev_clashing = False

    # ── Event loop ────────────────────────────────────────────────────────────
    while True:
        dt = clock.tick(60) / 1000.0
        dt = min(dt, 0.05)

        for event in pygame.event.get():

            # ── Quit / keys ───────────────────────────────────────────────────
            if event.type == pygame.QUIT:
                _quit(logger, world)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    _quit(logger, world)

                elif event.key == pygame.K_SPACE and state == "PAUSED":
                    state = "PLAYING"

                elif state == "ENDED":
                    if event.key == pygame.K_r:
                        world = make_world()
                        advisor = ChannelAdvisor(epsilon=epsilon, seed=seed + 1000)
                        state = "PAUSED"
                        popup_drone_id       = None
                        selected_ids         = set()
                        pending_suggestion   = None
                        suggestion_overrides = {}
                        pending_infeasible   = False
                        mouse_down_pos       = None
                        drag_pos             = None
                        is_dragging          = False
                        prev_clashing        = False
                        logger.log_game_start(seed, n_robots, complexity, duration, v_min, v_max)
                    elif event.key == pygame.K_q:
                        _quit(logger, world)

            # ── Mouse button DOWN ─────────────────────────────────────────────
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state != "PLAYING":
                    continue
                mx, my = event.pos

                # 1. Suggestion panel buttons take highest priority
                if pending_suggestion is not None:
                    handled = False

                    # Per-drone channel-override buttons
                    for drone_id, ch, rect in renderer.suggestion_drone_rects:
                        if rect.collidepoint(mx, my):
                            old = suggestion_overrides.get(drone_id)
                            suggestion_overrides[drone_id] = ch
                            if old and old != ch:
                                logger.log_suggestion_modified(
                                    drone_id, pending_suggestion[drone_id], ch, world.elapsed
                                )
                            handled = True
                            break

                    # Apply
                    if not handled and renderer.suggestion_apply_rect \
                            and renderer.suggestion_apply_rect.collidepoint(mx, my):
                        n_overrides = sum(
                            1 for did, ch in suggestion_overrides.items()
                            if pending_suggestion.get(did) != ch
                        )
                        logger.log_suggestion_applied(suggestion_overrides, n_overrides, world.elapsed)
                        _apply_suggestion(world, suggestion_overrides, logger, mode="M2")
                        pending_suggestion   = None
                        suggestion_overrides = {}
                        selected_ids         = set()
                        handled = True

                    # Cancel
                    if not handled and renderer.suggestion_cancel_rect \
                            and renderer.suggestion_cancel_rect.collidepoint(mx, my):
                        logger.log_suggestion_cancelled(world.elapsed)
                        pending_suggestion   = None
                        suggestion_overrides = {}
                        handled = True

                    continue  # Block all other arena interaction while panel is open

                # 2. HUD group-action buttons
                if selected_ids:
                    if "suggest" in renderer.hud_button_rects \
                            and renderer.hud_button_rects["suggest"].collidepoint(mx, my):
                        current_channels = {r.id: r.channel for r in world.robots}
                        proposed, infeasible = advisor.suggest(
                            list(selected_ids), current_channels, world.edges
                        )
                        logger.log_suggestion_requested(list(selected_ids), current_channels, world.elapsed)
                        logger.log_suggestion_shown(list(selected_ids), proposed, infeasible, world.elapsed)
                        pending_suggestion   = proposed
                        suggestion_overrides = dict(proposed)
                        pending_infeasible   = infeasible
                        popup_drone_id       = None
                        continue

                    if "auto_assign" in renderer.hud_button_rects \
                            and renderer.hud_button_rects["auto_assign"].collidepoint(mx, my):
                        current_channels = {r.id: r.channel for r in world.robots}
                        proposed, infeasible = advisor.suggest(
                            list(selected_ids), current_channels, world.edges
                        )
                        logger.log_auto_assign_applied(list(selected_ids), proposed, infeasible, world.elapsed)
                        _apply_suggestion(world, proposed, logger, mode="M3")
                        selected_ids  = set()
                        popup_drone_id = None
                        continue

                # 3. M1 popup channel buttons
                if popup_drone_id is not None and renderer.popup_rects:
                    for ch, rect in renderer.popup_rects.items():
                        if rect.collidepoint(mx, my):
                            robot = world.robots[popup_drone_id]
                            if robot.switching_to is None and ch != robot.channel:
                                world.request_switch(popup_drone_id, ch)
                                logger.log_switch_requested(
                                    popup_drone_id, robot.channel, ch, world.elapsed, mode="M1"
                                )
                            popup_drone_id = None
                            break
                    else:
                        # Click not on any popup button — start tracking for drag/click
                        if mx < arena_w:
                            mouse_down_pos = (mx, my)
                            drag_pos       = (mx, my)
                    continue

                # 4. Start drag tracking for arena clicks
                if mx < arena_w:
                    mouse_down_pos = (mx, my)
                    drag_pos       = (mx, my)
                    is_dragging    = False

            # ── Mouse MOTION ──────────────────────────────────────────────────
            elif event.type == pygame.MOUSEMOTION:
                if mouse_down_pos is not None and pygame.mouse.get_pressed()[0]:
                    mx, my = event.pos
                    drag_pos = (mx, my)
                    dx = mx - mouse_down_pos[0]
                    dy = my - mouse_down_pos[1]
                    if math.sqrt(dx * dx + dy * dy) > DRAG_THRESHOLD:
                        is_dragging = True

            # ── Mouse button UP ───────────────────────────────────────────────
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if state != "PLAYING" or mouse_down_pos is None:
                    mouse_down_pos = None
                    drag_pos       = None
                    is_dragging    = False
                    continue

                mx, my = event.pos
                ctrl = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)

                if is_dragging and drag_pos is not None:
                    # Bounding-box group selection
                    x0, y0 = mouse_down_pos
                    x1, y1 = drag_pos
                    box = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
                    new_sel = {r.id for r in world.robots if box.collidepoint(int(r.x), int(r.y))}

                    if ctrl:
                        selected_ids ^= new_sel   # toggle
                    else:
                        selected_ids = new_sel

                    if selected_ids:
                        popup_drone_id = None
                        logger.log_group_selected(list(selected_ids), "box", world.elapsed)
                    else:
                        popup_drone_id = None

                else:
                    # Plain click
                    clicked = _drone_at((mx, my), world, arena_w)

                    if clicked is not None:
                        if ctrl:
                            # Ctrl+click: toggle drone in group selection
                            if clicked in selected_ids:
                                selected_ids.discard(clicked)
                            else:
                                selected_ids.add(clicked)
                            popup_drone_id = None
                            if selected_ids:
                                logger.log_group_selected(list(selected_ids), "ctrl_click", world.elapsed)
                        elif selected_ids:
                            # Group active + plain click: close group, open M1 for this drone
                            selected_ids   = set()
                            popup_drone_id = clicked if clicked != popup_drone_id else None
                        else:
                            # No group: toggle M1 popup
                            popup_drone_id = clicked if clicked != popup_drone_id else None
                    else:
                        # Click on empty space: clear everything
                        selected_ids   = set()
                        popup_drone_id = None

                mouse_down_pos = None
                drag_pos       = None
                is_dragging    = False

        # ── Simulation tick ───────────────────────────────────────────────────
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

        # ── Render ────────────────────────────────────────────────────────────
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
        pygame.display.flip()
