from __future__ import annotations
import math
import sys
from typing import Optional

import pygame

from robot_world import RobotWorld
from robot_renderer import RobotRenderer, PANEL_W
from game_logger import GameLogger


def _robot_at(pos: tuple[int, int], world: RobotWorld, arena_w: int) -> Optional[int]:
    mx, my = pos
    if mx >= arena_w:
        return None
    for r in world.robots:
        dx, dy = mx - r.x, my - r.y
        if math.sqrt(dx * dx + dy * dy) <= r.radius + 4:
            return r.id
    return None


def run_game(seed: int = 42, n_robots: int = 12, duration: float = 120.0) -> None:
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("Robot Channel Switching")
    clock = pygame.time.Clock()

    window_w, window_h = screen.get_size()
    arena_w = window_w - PANEL_W

    def make_world() -> RobotWorld:
        return RobotWorld(n_robots, seed, duration, arena_w=arena_w, arena_h=window_h)

    logger = GameLogger()
    world = make_world()
    renderer = RobotRenderer(screen)

    state = "PAUSED"
    selected_id: Optional[int] = None
    prev_clashing = False

    logger.log("game_start", seed=seed, n_robots=n_robots, duration=duration,
               window_w=window_w, window_h=window_h)

    while True:
        dt = clock.tick(60) / 1000.0
        dt = min(dt, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit(logger, world)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # ESC always exits
                    _quit(logger, world)

                elif event.key == pygame.K_SPACE and state == "PAUSED":
                    state = "PLAYING"

                elif state == "ENDED":
                    if event.key == pygame.K_r:
                        world = make_world()
                        state = "PAUSED"
                        selected_id = None
                        prev_clashing = False
                        logger.log("game_start", seed=seed, n_robots=n_robots,
                                   duration=duration)
                    elif event.key == pygame.K_q:
                        _quit(logger, world)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state != "PLAYING":
                    continue

                mx, my = event.pos

                # Check popup channel buttons first (highest priority)
                if selected_id is not None and renderer.popup_rects:
                    hit_popup = False
                    for ch, rect in renderer.popup_rects.items():
                        if rect.collidepoint(mx, my):
                            robot = world.robots[selected_id]
                            if robot.switching_to is None and ch != robot.channel:
                                if world.request_switch(selected_id, ch):
                                    logger.log("switch_requested",
                                               robot_id=selected_id,
                                               from_channel=robot.channel,
                                               to_channel=ch,
                                               elapsed=world.elapsed)
                            selected_id = None
                            hit_popup = True
                            break
                    if hit_popup:
                        continue

                # Click in arena: select robot or deselect
                if mx < arena_w:
                    clicked = _robot_at(event.pos, world, arena_w)
                    if clicked is not None:
                        # Toggle selection
                        selected_id = clicked if clicked != selected_id else None
                    else:
                        selected_id = None  # click empty space = deselect

        if state == "PLAYING":
            world.update(dt)

            now_clashing = world.is_clashing
            if now_clashing and not prev_clashing:
                logger.log("clash_start", elapsed=world.elapsed,
                           pairs=list(world.clashing_pairs))
            elif not now_clashing and prev_clashing:
                logger.log("clash_end", elapsed=world.elapsed,
                           clash_seconds_so_far=world.clash_seconds)
            prev_clashing = now_clashing

            if world.is_over():
                state = "ENDED"
                logger.log("game_end",
                           elapsed=world.elapsed,
                           clash_seconds=world.clash_seconds,
                           clash_pct=world.clash_seconds / world.duration * 100)

        renderer.draw_frame(world, selected_id, state)
        pygame.display.flip()


def _quit(logger: GameLogger, world: RobotWorld) -> None:
    logger.log("quit", elapsed=world.elapsed, clash_seconds=world.clash_seconds)
    logger.close()
    pygame.quit()
    sys.exit()
