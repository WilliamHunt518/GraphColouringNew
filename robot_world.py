from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import Optional

CHANNELS = ("red", "green", "blue")
SWITCH_DURATION = 3.0
SPEED_MIN = 7.0
SPEED_MAX = 15.0
TURN_INTERVAL_MIN = 4.0
TURN_INTERVAL_MAX = 9.0
STEER_RATE        = math.pi / 2   # max heading correction, radians/second
ROBOT_RADIUS = 18

WARN_RADIUS     = 182.0
CONNECT_RADIUS  = WARN_RADIUS * 2
APPROACH_RADIUS = CONNECT_RADIUS * 1.25

# Arena width at which the pixel radii above were calibrated
# (1920-px-wide monitor minus the 310-px side panel).
# At runtime, RobotWorld scales all radii to the actual arena_w so that
# gameplay topology is identical across different monitor resolutions.
_REFERENCE_ARENA_W = 1610.0

_DEFAULT_ARENA_W = 750
_DEFAULT_ARENA_H = 700

COMPLEXITY_PRESETS = {
    "easy":   (8,   7.0, 15.0),
    "medium": (12,  7.0, 15.0),
    "hard":   (16, 10.0, 20.0),
}


@dataclass
class Robot:
    id: int
    x: float
    y: float
    vx: float
    vy: float
    channel: Optional[str] = None
    switching_to: Optional[str] = None
    switch_elapsed: float = 0.0
    next_turn_in: float = 0.0
    radius: int = ROBOT_RADIUS
    heading: float = 0.0


class RobotWorld:
    def __init__(
        self,
        n_robots: int = 12,
        seed: int = 42,
        duration: float = 90.0,
        arena_w: int = _DEFAULT_ARENA_W,
        arena_h: int = _DEFAULT_ARENA_H,
        v_min: float = SPEED_MIN,
        v_max: float = SPEED_MAX,
        switch_duration: float = SWITCH_DURATION,
    ) -> None:
        self.rng = random.Random(seed)
        self.n_robots = n_robots
        self.duration = duration
        self.arena_w = arena_w
        self.arena_h = arena_h
        self.v_min = v_min
        self.v_max = v_max
        self.switch_duration = switch_duration
        self.elapsed = 0.0
        self.clash_seconds = 0.0

        _scale = arena_w / _REFERENCE_ARENA_W
        self.warn_radius     = WARN_RADIUS     * _scale
        self.connect_radius  = CONNECT_RADIUS  * _scale
        self.approach_radius = APPROACH_RADIUS * _scale
        self.robot_radius    = max(6, round(ROBOT_RADIUS * _scale))

        self.robots: list[Robot] = []
        self._init_robots(n_robots)

        self.edges: list[tuple[int, int]] = []
        self.clashing_pairs: set[tuple[int, int]] = set()
        self.warning_pairs: set[tuple[int, int]] = set()

    def _init_robots(self, n: int) -> None:
        n_cols = min(4, n)
        n_rows = math.ceil(n / n_cols)
        col_pos = [(i + 0.5) / n_cols for i in range(n_cols)]
        row_pos = [(i + 0.5) / n_rows for i in range(n_rows)]
        grid = [(c * self.arena_w, r * self.arena_h) for r in row_pos for c in col_pos]
        jitter = min(self.arena_w, self.arena_h) * 0.04

        rr = self.robot_radius
        for i in range(n):
            bx, by = grid[i % len(grid)]
            x = max(rr, min(self.arena_w - rr,
                            bx + self.rng.uniform(-jitter, jitter)))
            y = max(rr, min(self.arena_h - rr,
                            by + self.rng.uniform(-jitter, jitter)))
            angle = self.rng.uniform(0, 2 * math.pi)
            speed = self.rng.uniform(self.v_min, self.v_max)
            self.robots.append(Robot(
                id=i, x=x, y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                channel=None,
                next_turn_in=self.rng.uniform(0, TURN_INTERVAL_MAX),
                heading=angle,
                radius=rr,
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
                # Commit a moderate heading change and pick a new speed
                deviation = self.rng.uniform(-math.pi / 3, math.pi / 3)
                r.heading += deviation
                new_speed = self.rng.uniform(self.v_min, self.v_max)
                speed = math.sqrt(r.vx * r.vx + r.vy * r.vy)
                if speed > 0:
                    r.vx = r.vx / speed * new_speed
                    r.vy = r.vy / speed * new_speed
                r.next_turn_in = self.rng.uniform(TURN_INTERVAL_MIN, TURN_INTERVAL_MAX)

            # Gradually steer toward the committed heading
            current_angle = math.atan2(r.vy, r.vx)
            diff = (r.heading - current_angle + math.pi) % (2 * math.pi) - math.pi
            turn = max(-STEER_RATE * dt, min(STEER_RATE * dt, diff))
            if turn != 0:
                new_angle = current_angle + turn
                speed = math.sqrt(r.vx * r.vx + r.vy * r.vy)
                r.vx = math.cos(new_angle) * speed
                r.vy = math.sin(new_angle) * speed

            r.x += r.vx * dt
            r.y += r.vy * dt
            self._clamp(r)

    def _clamp(self, r: Robot) -> None:
        m = r.radius
        bounced = False
        if r.x < m:
            r.x = m; r.vx = abs(r.vx); bounced = True
        elif r.x > self.arena_w - m:
            r.x = self.arena_w - m; r.vx = -abs(r.vx); bounced = True
        if r.y < m:
            r.y = m; r.vy = abs(r.vy); bounced = True
        elif r.y > self.arena_h - m:
            r.y = self.arena_h - m; r.vy = -abs(r.vy); bounced = True
        if bounced:
            r.heading = math.atan2(r.vy, r.vx)

    def _avoid_collisions(self) -> None:
        robots = self.robots
        n = len(robots)
        min_dist = self.robot_radius * 2 + 2

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
                nx_, ny_ = dx / dist, dy / dist
                ri.x -= nx_ * overlap; ri.y -= ny_ * overlap
                rj.x += nx_ * overlap; rj.y += ny_ * overlap
                rel_vx = ri.vx - rj.vx
                rel_vy = ri.vy - rj.vy
                rel_v_n = rel_vx * nx_ + rel_vy * ny_
                if rel_v_n > 0:
                    ri.vx -= rel_v_n * nx_; ri.vy -= rel_v_n * ny_
                    rj.vx += rel_v_n * nx_; rj.vy += rel_v_n * ny_
                self._clamp(ri); self._clamp(rj)

    def _update_switches(self, dt: float) -> None:
        for r in self.robots:
            if r.switching_to is not None:
                r.switch_elapsed += dt
                if r.switch_elapsed >= self.switch_duration:
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
                if dist <= self.connect_radius:
                    self.edges.append((i, j))
                    if robots[i].channel is not None and robots[i].channel == robots[j].channel:
                        self.clashing_pairs.add((i, j))
                elif dist <= self.approach_radius:
                    self.warning_pairs.add((i, j))

    def _accumulate_clashes(self, dt: float) -> None:
        n = len(self.clashing_pairs)
        if n:
            # Each simultaneous clashing pair contributes independently,
            # so 2 pairs = 2× rate, 3 pairs = 3× rate, etc.
            self.clash_seconds += dt * n

    @property
    def is_clashing(self) -> bool:
        return bool(self.clashing_pairs)
