from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import Optional

CHANNELS = ("red", "green", "blue")
SWITCH_DURATION = 5.0
SPEED_MIN = 10.0
SPEED_MAX = 22.0
TURN_INTERVAL_MIN = 1.0
TURN_INTERVAL_MAX = 3.5
ROBOT_RADIUS = 14

# Circles drawn around each robot have this radius.
# An edge forms when two circles overlap, i.e. dist < WARN_RADIUS * 2.
WARN_RADIUS = 140.0
CONNECT_RADIUS = WARN_RADIUS * 2   # = 280 px

# "Approaching" zone: circles not yet overlapping but getting close
APPROACH_RADIUS = CONNECT_RADIUS * 1.25  # = 350 px

_DEFAULT_ARENA_W = 750
_DEFAULT_ARENA_H = 700


@dataclass
class Robot:
    id: int
    x: float
    y: float
    vx: float
    vy: float
    channel: str
    switching_to: Optional[str] = None
    switch_elapsed: float = 0.0
    next_turn_in: float = 0.0
    radius: int = ROBOT_RADIUS


class RobotWorld:
    def __init__(
        self,
        n_robots: int = 12,
        seed: int = 42,
        duration: float = 120.0,
        arena_w: int = _DEFAULT_ARENA_W,
        arena_h: int = _DEFAULT_ARENA_H,
    ) -> None:
        self.rng = random.Random(seed)
        self.n_robots = n_robots
        self.duration = duration
        self.arena_w = arena_w
        self.arena_h = arena_h
        self.elapsed = 0.0
        self.clash_seconds = 0.0

        self.robots: list[Robot] = []
        self._init_robots(n_robots)

        self.edges: list[tuple[int, int]] = []
        self.clashing_pairs: set[tuple[int, int]] = set()
        self.warning_pairs: set[tuple[int, int]] = set()  # approaching but not yet connected

    def _init_robots(self, n: int) -> None:
        cols = [0.20, 0.40, 0.60, 0.80]
        rows = [0.25, 0.50, 0.75]
        grid = [(c * self.arena_w, r * self.arena_h) for r in rows for c in cols]

        channels_pool = list(CHANNELS) * ((n // len(CHANNELS)) + 1)
        self.rng.shuffle(channels_pool)

        jitter = min(self.arena_w, self.arena_h) * 0.04

        for i in range(n):
            bx, by = grid[i % len(grid)]
            x = max(ROBOT_RADIUS, min(self.arena_w - ROBOT_RADIUS,
                                      bx + self.rng.uniform(-jitter, jitter)))
            y = max(ROBOT_RADIUS, min(self.arena_h - ROBOT_RADIUS,
                                      by + self.rng.uniform(-jitter, jitter)))
            angle = self.rng.uniform(0, 2 * math.pi)
            speed = self.rng.uniform(SPEED_MIN, SPEED_MAX)
            self.robots.append(Robot(
                id=i, x=x, y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                channel=channels_pool[i],
                next_turn_in=self.rng.uniform(0, TURN_INTERVAL_MAX),
            ))

    def request_switch(self, robot_id: int, new_channel: str) -> bool:
        r = self.robots[robot_id]
        if r.switching_to is not None or new_channel == r.channel:
            return False
        r.switching_to = new_channel
        r.switch_elapsed = 0.0
        return True

    def is_over(self) -> bool:
        return self.elapsed >= self.duration

    def update(self, dt: float) -> None:
        self.elapsed += dt
        self._move_robots(dt)
        self._avoid_collisions()
        self._update_switches(dt)
        self._detect_edges()
        self._accumulate_clashes(dt)

    def _move_robots(self, dt: float) -> None:
        for r in self.robots:
            r.next_turn_in -= dt
            if r.next_turn_in <= 0:
                current_angle = math.atan2(r.vy, r.vx)
                nudge = self.rng.uniform(-math.pi / 2, math.pi / 2)
                new_angle = current_angle + nudge
                new_speed = self.rng.uniform(SPEED_MIN, SPEED_MAX)
                r.vx = math.cos(new_angle) * new_speed
                r.vy = math.sin(new_angle) * new_speed
                r.next_turn_in = self.rng.uniform(TURN_INTERVAL_MIN, TURN_INTERVAL_MAX)

            r.x += r.vx * dt
            r.y += r.vy * dt
            self._clamp(r)

    def _clamp(self, r: Robot) -> None:
        m = r.radius
        if r.x < m:
            r.x = m; r.vx = abs(r.vx)
        elif r.x > self.arena_w - m:
            r.x = self.arena_w - m; r.vx = -abs(r.vx)
        if r.y < m:
            r.y = m; r.vy = abs(r.vy)
        elif r.y > self.arena_h - m:
            r.y = self.arena_h - m; r.vy = -abs(r.vy)

    def _avoid_collisions(self) -> None:
        robots = self.robots
        n = len(robots)
        min_dist = ROBOT_RADIUS * 2 + 2  # 2px buffer

        for i in range(n):
            for j in range(i + 1, n):
                ri, rj = robots[i], robots[j]
                dx = rj.x - ri.x
                dy = rj.y - ri.y
                dist_sq = dx * dx + dy * dy
                if dist_sq >= min_dist * min_dist or dist_sq == 0:
                    continue

                dist = math.sqrt(dist_sq)
                overlap = (min_dist - dist) * 0.5
                nx, ny = dx / dist, dy / dist

                # Push positions apart equally
                ri.x -= nx * overlap
                ri.y -= ny * overlap
                rj.x += nx * overlap
                rj.y += ny * overlap

                # Cancel the approaching component of relative velocity
                rel_vx = ri.vx - rj.vx
                rel_vy = ri.vy - rj.vy
                rel_v_n = rel_vx * nx + rel_vy * ny
                if rel_v_n > 0:  # only if still approaching
                    ri.vx -= rel_v_n * nx
                    ri.vy -= rel_v_n * ny
                    rj.vx += rel_v_n * nx
                    rj.vy += rel_v_n * ny

                # Re-clamp both to arena bounds after push
                self._clamp(ri)
                self._clamp(rj)

    def _update_switches(self, dt: float) -> None:
        for r in self.robots:
            if r.switching_to is not None:
                r.switch_elapsed += dt
                if r.switch_elapsed >= SWITCH_DURATION:
                    r.channel = r.switching_to
                    r.switching_to = None
                    r.switch_elapsed = 0.0

    def _detect_edges(self) -> None:
        self.edges.clear()
        self.clashing_pairs.clear()
        self.warning_pairs.clear()
        robots = self.robots
        n = len(robots)
        for i in range(n):
            for j in range(i + 1, n):
                dx = robots[i].x - robots[j].x
                dy = robots[i].y - robots[j].y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= CONNECT_RADIUS:
                    self.edges.append((i, j))
                    if robots[i].channel == robots[j].channel:
                        self.clashing_pairs.add((i, j))
                elif dist <= APPROACH_RADIUS:
                    self.warning_pairs.add((i, j))

    def _accumulate_clashes(self, dt: float) -> None:
        if self.clashing_pairs:
            self.clash_seconds += dt

    @property
    def is_clashing(self) -> bool:
        return len(self.clashing_pairs) > 0
