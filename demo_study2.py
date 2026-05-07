"""
demo_study2.py — Study 2 concept demo: subswarm flocking + planned migrations.

Three independent subswarms (Alpha, Bravo, Charlie) flock via Reynolds Boids
within their own territory. At a preplanned time drones migrate between
subswarms, increasing the destination's density and triggering new clashes.

Controls:  SPACE = advance step   ESC = quit
"""
from __future__ import annotations
import copy, math, os, random, sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

import pygame

# ── Reference arena dimensions (all radius constants are calibrated here) ────
_REF_W = 980.0
_REF_H = 520.0   # arena-only reference height (excludes strip)

# ── Colours ───────────────────────────────────────────────────────────────────
COL_ARENA   = (22, 22, 35)
COL_STRIP   = (14, 14, 26)
COL_BORDER  = (90, 160, 255)
COL_TEXT    = (210, 210, 225)
COL_DIM     = (120, 120, 145)
COL_HEAD    = (200, 230, 255)
COL_HINT    = (140, 220, 140)
COL_HINT_B  = (220, 180,  80)
COL_CLASH   = (230,  50,  50)
COL_WARN_E  = (255, 165,   0)
COL_NORM_E  = (115, 115, 140)
COL_MIGRATE = (255, 240,  80)

CHANNEL_FILL = {
    "red":   (210,  55,  55),
    "green": ( 55, 190,  80),
    "blue":  ( 55, 110, 210),
}
CHANNEL_ABBREV = {"red": "R", "green": "G", "blue": "B"}
CHANNELS = ("red", "green", "blue")

SW_RGBA  = [(255, 140,  60, 30), ( 55, 200, 185, 30), (170,  85, 255, 30)]
SW_RING  = [(255, 160,  80),     ( 65, 220, 205),      (190, 105, 255)]
SW_NAMES = ["Alpha", "Bravo", "Charlie"]

# ── Reference physics constants (pixels at _REF_W = 980) ─────────────────────
_ROBOT_R      = 19
_CONNECT_R    = 60.0     # link radius — just above equilibrium spacing for 7-drone clusters
_WARN_R       = 34.0
_HOME_R       = 120.0    # larger dead-zone gives 7-drone clusters room to breathe
_MAX_DIST     = 210.0    # hard-cap: redirect straight toward center
_SEP_DIST     = 72.0     # separation neighbourhood
_ALIGN_DIST   = 140.0    # alignment + local cohesion neighbourhood
_CTR_MARGIN   = 90.0     # subswarm-center wall margin
# Minimum center-to-center distance (= 2 × bubble_r with a safety margin).
# Repulsion starts outside this radius so bubbles never visually touch.
_CLUSTER_SEP  = 260.0    # reference px — centre repulsion kicks in below this
_CTR_REPEL_K  = 1200.0   # centre-repulsion impulse magnitude
# Cross-swarm drone repulsion — prevents drones from different groups mixing.
_CROSS_SEP    = 60.0     # reference px — push away foreign drones within this range
_CROSS_K      = 180.0    # cross-swarm repulsion magnitude

SEP_K     = 95.0    # separation acceleration magnitude
ALIGN_K   = 1.3     # alignment gain (fraction of velocity diff per second)
COH_K     = 12.0    # cohesion toward neighbour centroid (px/s²)
HOME_K    = 35.0    # home-radius pull
JITTER_K  = 3.0     # random perturbation amplitude (px/s²)

SPEED_MIN   = 3.0
SPEED_MAX   = 18.0   # slower drones — more deliberate jostling

CTR_SPD      = 7.0   # subswarm centre wanders slowly
CTR_TURN_MIN = 12.0
CTR_TURN_MAX = 22.0

SWITCH_DUR   = 3.0
MIGRATE_SPD  = 55.0   # reference px/s for migration flight (scales too)
MIGRATE_TIME = 26.0    # world-seconds when migration fires
FPS          = 60
STRIP_FRAC   = 0.25    # annotation strip = this fraction of window height


# ── Data structures ───────────────────────────────────────────────────────────
@dataclass
class Drone:
    id:             int
    x:              float
    y:              float
    vx:             float
    vy:             float
    heading:        float
    channel:        str
    switching_to:   Optional[str] = None
    switch_elapsed: float         = 0.0
    subswarm:       int           = 0
    migrating:      bool          = False
    migrate_tx:     float         = 0.0
    migrate_ty:     float         = 0.0
    migrate_dest:   int           = 0


@dataclass
class Center:
    x:            float
    y:            float
    vx:           float
    vy:           float
    heading:      float
    next_turn_in: float


# ── World ─────────────────────────────────────────────────────────────────────
class SubswarmWorld:
    """3 subswarms of 4 drones. Reynolds Boids within each swarm; no inter-swarm edges."""

    MIGS = [(0, 2, 2), (1, 2, 2)]  # (src_subswarm, dst_subswarm, n_drones)

    def __init__(self, arena_w: int, arena_h: int, seed: int = 7) -> None:
        self.arena_w = arena_w
        self.arena_h = arena_h
        scale = arena_w / _REF_W

        # Scale all distance constants to actual arena
        self.robot_r    = max(8, round(_ROBOT_R    * scale))
        self.connect_r  = _CONNECT_R  * scale
        self.warn_r     = _WARN_R     * scale
        self.home_r     = _HOME_R     * scale
        self.max_dist   = _MAX_DIST   * scale
        self.sep_dist   = _SEP_DIST   * scale
        self.align_dist = _ALIGN_DIST * scale
        self.ctr_margin   = _CTR_MARGIN  * scale
        self.cruise       = 12.0        * scale
        self.speed_max    = SPEED_MAX   * scale
        self.speed_min    = SPEED_MIN   * scale
        self.ctr_spd      = CTR_SPD     * scale
        self.migrate_spd  = MIGRATE_SPD * scale
        self.cluster_sep  = _CLUSTER_SEP * scale   # centre-repulsion radius
        self.cross_sep    = _CROSS_SEP   * scale   # cross-swarm drone repulsion radius

        self.rng             = random.Random(seed)
        self.elapsed         = 0.0
        self.migration_fired = False
        self.migration_done  = False

        # Subswarm-center initial positions (proportional)
        init = [(0.20, 0.28), (0.80, 0.28), (0.50, 0.72)]
        self.centers: List[Center] = []
        for fx, fy in init:
            ang = self.rng.uniform(0, 2 * math.pi)
            self.centers.append(Center(
                x=fx * arena_w, y=fy * arena_h,
                vx=math.cos(ang) * self.ctr_spd,
                vy=math.sin(ang) * self.ctr_spd,
                heading=ang,
                next_turn_in=self.rng.uniform(CTR_TURN_MIN, CTR_TURN_MAX),
            ))

        self.drones: List[Drone] = []
        self._init_drones()

        self.edges:    Set[Tuple[int, int]] = set()
        self.clashing: Set[Tuple[int, int]] = set()
        self.warning:  Set[Tuple[int, int]] = set()

    # 7 drones per swarm: same-channel drones spaced ≈120° apart to avoid immediate clashes.
    # Positions k=0..6 are at 0°,51°,103°,154°,206°,257°,309°.
    # Channel assignment [R,G,R,G,B,R,B] places the 3 R-drones at k=0,2,5 (≈103° min gap)
    # and same-channel G/B pairs at k=1,3 and k=4,6 (≈103° apart).
    _DRONES_PER_SWARM = 7
    _SWARM_CH = [CHANNELS[0], CHANNELS[1], CHANNELS[0],
                 CHANNELS[1], CHANNELS[2], CHANNELS[0], CHANNELS[2]]

    def _init_drones(self) -> None:
        did = 0
        for sw in range(3):
            cx, cy = self.centers[sw].x, self.centers[sw].y
            for k in range(self._DRONES_PER_SWARM):
                ang = 2 * math.pi * k / self._DRONES_PER_SWARM + self.rng.uniform(-0.2, 0.2)
                off = self.home_r * 0.55
                x = max(self.robot_r + 4, min(self.arena_w - self.robot_r - 4,
                                              cx + math.cos(ang) * off))
                y = max(self.robot_r + 4, min(self.arena_h - self.robot_r - 4,
                                              cy + math.sin(ang) * off))
                speed = self.cruise * self.rng.uniform(0.4, 0.8)
                vang  = self.rng.uniform(0, 2 * math.pi)
                self.drones.append(Drone(
                    id=did, x=x, y=y,
                    vx=math.cos(vang) * speed,
                    vy=math.sin(vang) * speed,
                    heading=vang,
                    channel=self._SWARM_CH[k],
                    subswarm=sw,
                ))
                did += 1

    # ── tick ──────────────────────────────────────────────────────────────────
    def tick(self, dt: float, paused: bool = False) -> None:
        if not paused:
            self.elapsed += dt
            self._move_centers(dt)
            self._repel_centers(dt)
            self._boids(dt)
            self._finish_migration()
        self._detect_edges()
        self._detect_clashes()

    # ── centre-to-centre repulsion ────────────────────────────────────────────
    def _repel_centers(self, dt: float) -> None:
        """Keep subswarm attractors far enough apart so their bubbles never overlap."""
        for i, ci in enumerate(self.centers):
            for cj in self.centers[i + 1:]:
                dx, dy = ci.x - cj.x, ci.y - cj.y
                dist = math.sqrt(dx * dx + dy * dy) or 0.001
                if dist < self.cluster_sep:
                    # Quadratic impulse — strongest when very close
                    mag = _CTR_REPEL_K * (1.0 - dist / self.cluster_sep) ** 2 * dt
                    nx, ny = dx / dist, dy / dist
                    ci.vx += nx * mag;  ci.vy += ny * mag
                    cj.vx -= nx * mag;  cj.vy -= ny * mag
        # Re-clamp centre speeds after impulse
        for c in self.centers:
            spd = math.sqrt(c.vx ** 2 + c.vy ** 2) or 0.001
            cap = self.ctr_spd * 3.0
            if spd > cap:
                c.vx = c.vx / spd * cap
                c.vy = c.vy / spd * cap

    # ── migration ─────────────────────────────────────────────────────────────
    def fire_migration(self) -> None:
        if self.migration_fired:
            return
        self.migration_fired = True
        for src, dst, n in self.MIGS:
            pool = [d for d in self.drones if d.subswarm == src and not d.migrating]
            chosen = self.rng.sample(pool, min(n, len(pool)))
            cdst = self.centers[dst]
            for d in chosen:
                d.migrating    = True
                d.migrate_dest = dst
                a = self.rng.uniform(0, 2 * math.pi)
                d.migrate_tx = cdst.x + math.cos(a) * self.home_r * 0.40
                d.migrate_ty = cdst.y + math.sin(a) * self.home_r * 0.40
                d.migrate_tx = max(self.robot_r + 4,
                                   min(self.arena_w - self.robot_r - 4, d.migrate_tx))
                d.migrate_ty = max(self.robot_r + 4,
                                   min(self.arena_h - self.robot_r - 4, d.migrate_ty))

    def _finish_migration(self) -> None:
        for d in self.drones:
            if not d.migrating:
                continue
            dx, dy = d.migrate_tx - d.x, d.migrate_ty - d.y
            if math.sqrt(dx * dx + dy * dy) < self.robot_r * 2:
                d.migrating = False
                d.subswarm  = d.migrate_dest
                ang = self.rng.uniform(0, 2 * math.pi)
                d.vx = math.cos(ang) * self.cruise * 0.6
                d.vy = math.sin(ang) * self.cruise * 0.6
                d.heading = ang
        if self.migration_fired and not self.migration_done:
            if not any(d.migrating for d in self.drones):
                self.migration_done = True

    # ── physics ───────────────────────────────────────────────────────────────
    def _move_centers(self, dt: float) -> None:
        for c in self.centers:
            c.next_turn_in -= dt
            if c.next_turn_in <= 0:
                c.heading += self.rng.uniform(-math.pi / 3, math.pi / 3)
                c.vx = math.cos(c.heading) * self.ctr_spd
                c.vy = math.sin(c.heading) * self.ctr_spd
                c.next_turn_in = self.rng.uniform(CTR_TURN_MIN, CTR_TURN_MAX)
            c.x += c.vx * dt
            c.y += c.vy * dt
            m = self.ctr_margin
            if c.x < m:
                c.x = m;                 c.vx =  abs(c.vx); c.heading = math.atan2(c.vy, c.vx)
            elif c.x > self.arena_w - m:
                c.x = self.arena_w - m;  c.vx = -abs(c.vx); c.heading = math.atan2(c.vy, c.vx)
            if c.y < m:
                c.y = m;                 c.vy =  abs(c.vy); c.heading = math.atan2(c.vy, c.vx)
            elif c.y > self.arena_h - m:
                c.y = self.arena_h - m;  c.vy = -abs(c.vy); c.heading = math.atan2(c.vy, c.vx)

    def _boids(self, dt: float) -> None:
        """Reynolds Boids: separation + alignment + cohesion + home barrier."""
        # Group non-migrating drones by subswarm
        by_sw: Dict[int, List[Drone]] = {i: [] for i in range(3)}
        for d in self.drones:
            if not d.migrating:
                by_sw[d.subswarm].append(d)

        for sw_id, members in by_sw.items():
            ctr = self.centers[sw_id]
            for d in members:
                ax, ay = 0.0, 0.0

                # ── per-neighbour terms ───────────────────────────────────────
                align_vx = align_vy = 0.0
                coh_x    = coh_y    = 0.0
                n_local  = 0

                for o in members:
                    if o.id == d.id:
                        continue
                    dx, dy = o.x - d.x, o.y - d.y
                    dist = math.sqrt(dx * dx + dy * dy) or 0.001

                    # Separation: push away from too-close neighbours
                    if dist < self.sep_dist:
                        w = (1.0 - dist / self.sep_dist) ** 2
                        ax -= (dx / dist) * SEP_K * w
                        ay -= (dy / dist) * SEP_K * w

                    # Alignment + local cohesion (same neighbourhood)
                    if dist < self.align_dist:
                        align_vx += o.vx;  align_vy += o.vy
                        coh_x    += o.x;   coh_y    += o.y
                        n_local  += 1

                if n_local:
                    # Alignment: steer toward average velocity of neighbours
                    ax += ALIGN_K * (align_vx / n_local - d.vx)
                    ay += ALIGN_K * (align_vy / n_local - d.vy)

                    # Local cohesion: move toward centroid of neighbours
                    ncx = coh_x / n_local - d.x
                    ncy = coh_y / n_local - d.y
                    nd  = math.sqrt(ncx * ncx + ncy * ncy) or 0.001
                    ax += (ncx / nd) * COH_K
                    ay += (ncy / nd) * COH_K

                # ── home barrier (toward swarm-centre object) ─────────────────
                cdx, cdy = ctr.x - d.x, ctr.y - d.y
                cdist = math.sqrt(cdx * cdx + cdy * cdy) or 0.001

                if cdist > self.home_r:
                    # Quadratic pull — gets strong well before max_dist
                    excess = (cdist - self.home_r) / self.home_r
                    pull   = HOME_K * excess * (1.0 + excess)
                    ax += (cdx / cdist) * pull
                    ay += (cdy / cdist) * pull

                # Hard-cap: if way outside, override velocity directly
                if cdist > self.max_dist:
                    d.vx = (cdx / cdist) * self.cruise
                    d.vy = (cdy / cdist) * self.cruise
                    ax = ay = 0.0   # skip accumulated forces this frame

                # ── cross-swarm repulsion (prevent group mixing) ──────────────
                for o in self.drones:
                    if o.subswarm == d.subswarm or o.migrating:
                        continue
                    sdx, sdy = d.x - o.x, d.y - o.y
                    sdist = math.sqrt(sdx * sdx + sdy * sdy) or 0.001
                    if sdist < self.cross_sep:
                        push = _CROSS_K * (1.0 - sdist / self.cross_sep) ** 2
                        ax += (sdx / sdist) * push
                        ay += (sdy / sdist) * push

                # ── random jitter (organic motion) ────────────────────────────
                ax += self.rng.gauss(0.0, JITTER_K)
                ay += self.rng.gauss(0.0, JITTER_K)

                # ── integrate velocity ─────────────────────────────────────────
                d.vx += ax * dt
                d.vy += ay * dt

                # Clamp speed
                spd = math.sqrt(d.vx ** 2 + d.vy ** 2) or 0.001
                if spd > self.speed_max:
                    d.vx = d.vx / spd * self.speed_max
                    d.vy = d.vy / spd * self.speed_max
                elif spd < self.speed_min:
                    d.vx = d.vx / spd * self.speed_min
                    d.vy = d.vy / spd * self.speed_min

                # ── move + wall bounce ────────────────────────────────────────
                d.x += d.vx * dt
                d.y += d.vy * dt
                r = self.robot_r + 2
                if d.x < r:
                    d.x = r;                d.vx =  abs(d.vx)
                elif d.x > self.arena_w - r:
                    d.x = self.arena_w - r; d.vx = -abs(d.vx)
                if d.y < r:
                    d.y = r;                d.vy =  abs(d.vy)
                elif d.y > self.arena_h - r:
                    d.y = self.arena_h - r; d.vy = -abs(d.vy)

                d.heading = math.atan2(d.vy, d.vx)

                # Channel switch bookkeeping
                if d.switching_to:
                    d.switch_elapsed += dt
                    if d.switch_elapsed >= SWITCH_DUR:
                        d.channel        = d.switching_to
                        d.switching_to   = None
                        d.switch_elapsed = 0.0

        # Move migrating drones (fly straight to target)
        for d in self.drones:
            if not d.migrating:
                continue
            tdx, tdy = d.migrate_tx - d.x, d.migrate_ty - d.y
            dist = math.sqrt(tdx * tdx + tdy * tdy) or 0.001
            d.vx = (tdx / dist) * self.migrate_spd
            d.vy = (tdy / dist) * self.migrate_spd
            d.x += d.vx * dt
            d.y += d.vy * dt
            d.heading = math.atan2(d.vy, d.vx)

    def _detect_edges(self) -> None:
        self.edges.clear()
        self.warning.clear()
        drones = self.drones
        for i, a in enumerate(drones):
            for b in drones[i + 1:]:
                if a.subswarm != b.subswarm or a.migrating or b.migrating:
                    continue
                dx, dy = a.x - b.x, a.y - b.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= self.connect_r:
                    self.edges.add((a.id, b.id))
                elif dist <= self.connect_r + self.warn_r:
                    self.warning.add((a.id, b.id))

    def _detect_clashes(self) -> None:
        self.clashing.clear()
        for (i, j) in self.edges:
            di, dj = self.drones[i], self.drones[j]
            if (di.channel and dj.channel and di.channel == dj.channel
                    and not di.switching_to and not dj.switching_to):
                self.clashing.add((i, j))


# ── Demo step definitions ─────────────────────────────────────────────────────
@dataclass
class DemoStep:
    heading:       str
    body:          str
    min_time:      float                 = 0.0
    auto_advance:  bool                  = False
    freeze:        bool                  = False
    on_enter:      Optional[Callable]    = None
    advance_check: Optional[Callable]   = None   # (world) -> bool
    body_fn:       Optional[Callable]   = None   # (world) -> str override


def _make_steps(world: SubswarmWorld) -> List[DemoStep]:
    return [
        # 0 ── title (auto)
        DemoStep(
            heading="Study 2 — Subswarm-Structured Channel Assignment",
            body=(
                "This demo previews an extension of the channel assignment task. "
                "Drones are organised into independent subswarms that flock together, "
                "and at scheduled intervals groups migrate between swarms."
            ),
            min_time=5.0, auto_advance=True,
        ),
        # 1 ── subswarm structure (frozen, SPACE)
        DemoStep(
            heading="Three independent subswarms",
            body=(
                "Alpha (orange), Bravo (teal) and Charlie (purple) each contain "
                "seven drones that flock around a shared territory centre. "
                "Drones from different subswarms are always out of radio range — "
                "interference only ever occurs within a group."
            ),
            freeze=True,
        ),
        # 2 ── live interference (SPACE after 14 s)
        DemoStep(
            heading="Within-subswarm interference",
            body=(
                "As drones jostle within their territory, connections form and break. "
                "Clashing pairs (same channel, within range) appear in red. "
                "Each subswarm can be managed manually, supervised, or fully automated — "
                "independently of the others."
            ),
            min_time=14.0,
        ),
        # 3 ── migration countdown (auto when elapsed ≥ MIGRATE_TIME)
        DemoStep(
            heading="Migration event approaching",
            body="",
            body_fn=lambda w: (
                f"In {max(0.0, MIGRATE_TIME - w.elapsed):.0f}s: "
                "2 drones from Alpha and 2 from Bravo will relocate to Charlie. "
                "This simulates a mission re-tasking that increases Charlie's density."
            ),
            advance_check=lambda w: w.elapsed >= MIGRATE_TIME,
        ),
        # 4 ── migration in progress (auto when migration_done)
        DemoStep(
            heading="Migration in progress",
            body=(
                "Highlighted drones are flying to Charlie. "
                "On arrival they join Charlie's channel neighbourhood — "
                "their existing channels may clash with Charlie's drones."
            ),
            advance_check=lambda w: w.migration_done,
            on_enter=lambda w: w.fire_migration(),
        ),
        # 5 ── post-migration (SPACE after 12 s)
        DemoStep(
            heading="Charlie now has eleven drones",
            body=(
                "With eleven drones and only three channels, multiple clashes are "
                "unavoidable until the assignment is restructured. "
                "This is an ideal scenario to deploy agent automation on Charlie "
                "while Alpha and Bravo remain quiet enough for manual control."
            ),
            min_time=12.0,
        ),
        # 6 ── meta-agent (frozen, SPACE)
        DemoStep(
            heading="The meta-agent (Study 2 goal)",
            body=(
                "Study 2 introduces a meta-agent that monitors swarm complexity "
                "and inferred operator workload, then recommends autonomy levels per subswarm. "
                'Here it would suggest: "Automate Charlie — complexity exceeds manual threshold." '
                "The study tests whether following such guidance improves performance and trust."
            ),
            freeze=True,
        ),
        # 7 ── close (frozen, SPACE / ESC)
        DemoStep(
            heading="Summary",
            body=(
                "Subswarm structure + planned migrations create natural variation in task "
                "complexity over time, support selective autonomy, and provide a testbed "
                "for meta-level autonomy recommendations. "
                "Press SPACE or ESC to exit."
            ),
            freeze=True,
        ),
    ]


# ── Drawing ───────────────────────────────────────────────────────────────────
def _wrap(text: str, font: pygame.font.Font, max_w: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if font.size(test)[0] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_scene(
    screen: pygame.Surface,
    world: SubswarmWorld,
    step_idx: int,
    fonts: dict,
    pulse: float,
    arena_h: int,
) -> None:
    win_w = screen.get_width()

    arena_surf = screen.subsurface((0, 0, win_w, arena_h))
    arena_surf.fill(COL_ARENA)

    # ── centroid of each swarm (bubbles + labels follow actual drones) ───────
    sw_cx: List[float] = []
    sw_cy: List[float] = []
    for i in range(3):
        members = [d for d in world.drones if d.subswarm == i and not d.migrating]
        if members:
            sw_cx.append(sum(d.x for d in members) / len(members))
            sw_cy.append(sum(d.y for d in members) / len(members))
        else:
            sw_cx.append(world.centers[i].x)
            sw_cy.append(world.centers[i].y)

    # ── subswarm territory bubbles ────────────────────────────────────────────
    bubble_r = int(world.home_r * 0.95)
    for i in range(3):
        bub = pygame.Surface((bubble_r * 2, bubble_r * 2), pygame.SRCALPHA)
        # Gradient-like: inner slightly lighter, outer ring bold
        pygame.draw.circle(bub, SW_RGBA[i], (bubble_r, bubble_r), bubble_r)
        pygame.draw.circle(bub, (*SW_RING[i], 40), (bubble_r, bubble_r), bubble_r, 1)
        pygame.draw.circle(bub, (*SW_RING[i], 90), (bubble_r, bubble_r), bubble_r, 3)
        arena_surf.blit(bub, (int(sw_cx[i]) - bubble_r, int(sw_cy[i]) - bubble_r))

    # ── proximity halos (faint warn-radius disc around each drone, study-1 style)
    rr = world.robot_r
    prox_r = int(world.connect_r)
    prox_surf = pygame.Surface((prox_r * 2, prox_r * 2), pygame.SRCALPHA)
    for d in world.drones:
        if d.migrating:
            continue
        prox_surf.fill((0, 0, 0, 0))
        sw_col = SW_RING[d.subswarm]
        pygame.draw.circle(prox_surf, (*sw_col, 9),  (prox_r, prox_r), prox_r)
        pygame.draw.circle(prox_surf, (*sw_col, 22), (prox_r, prox_r), prox_r, 1)
        arena_surf.blit(prox_surf, (int(d.x) - prox_r, int(d.y) - prox_r))

    # ── edges — study-1 widths: 4 px clash, 2 px normal, 2 px warn ───────────
    dr = {d.id: d for d in world.drones}
    for (i, j) in world.warning:
        di, dj = dr[i], dr[j]
        pygame.draw.line(arena_surf, COL_WARN_E,
                         (int(di.x), int(di.y)), (int(dj.x), int(dj.y)), 2)
    for (i, j) in world.edges:
        di, dj = dr[i], dr[j]
        if (i, j) in world.clashing:
            pygame.draw.line(arena_surf, (255, 65, 65),
                             (int(di.x), int(di.y)), (int(dj.x), int(dj.y)), 4)
        else:
            pygame.draw.line(arena_surf, (150, 150, 165),
                             (int(di.x), int(di.y)), (int(dj.x), int(dj.y)), 2)

    # ── migration trails ──────────────────────────────────────────────────────
    for d in world.drones:
        if d.migrating:
            pygame.draw.line(arena_surf, (*COL_MIGRATE, 90),
                             (int(d.x), int(d.y)),
                             (int(d.migrate_tx), int(d.migrate_ty)), 2)

    # ── drones ────────────────────────────────────────────────────────────────
    clashing_ids = {i for pair in world.clashing for i in pair}
    for d in world.drones:
        cx, cy = int(d.x), int(d.y)

        # Body colour: dimmed when switching (study-1 pattern)
        if d.switching_to:
            fill = (55, 55, 75)
        else:
            fill = CHANNEL_FILL.get(d.channel, (80, 80, 100))
        pygame.draw.circle(arena_surf, fill, (cx, cy), rr)

        # Subswarm identity ring (thick, 3 px)
        ring_col = COL_MIGRATE if d.migrating else SW_RING[d.subswarm]
        pygame.draw.circle(arena_surf, ring_col, (cx, cy), rr, 3)

        # Clash pulse — double ring, pulsing alpha (study-1 style)
        if d.id in clashing_ids:
            alpha = int(130 + 90 * math.sin(pulse * 2 * math.pi))
            for ring_off in (rr + 5, rr + 10):
                sz = ring_off * 2 + 4
                ps = pygame.Surface((sz, sz), pygame.SRCALPHA)
                pygame.draw.circle(ps, (255, 65, 65, alpha),
                                   (sz // 2, sz // 2), ring_off, 2)
                arena_surf.blit(ps, (cx - sz // 2, cy - sz // 2))

        # Migration halo — bright pulsing gold ring
        if d.migrating:
            ha = int(170 + 80 * math.sin(pulse * 2 * math.pi))
            sz = (rr + 12) * 2 + 4
            hs = pygame.Surface((sz, sz), pygame.SRCALPHA)
            pygame.draw.circle(hs, (*COL_MIGRATE, ha), (sz // 2, sz // 2), rr + 12, 3)
            arena_surf.blit(hs, (cx - sz // 2, cy - sz // 2))

        # Channel label — bold, centred
        lbl = fonts["label"].render(CHANNEL_ABBREV.get(d.channel, "?"), True, (245, 245, 255))
        arena_surf.blit(lbl, (cx - lbl.get_width() // 2, cy - lbl.get_height() // 2))

    # ── subswarm name labels (follow centroid) ────────────────────────────────
    for i in range(3):
        n_active = sum(1 for d in world.drones if d.subswarm == i and not d.migrating)
        tag = f"{SW_NAMES[i]}  ({n_active})"
        lbl = fonts["swlabel"].render(tag, True, SW_RING[i])
        # Shadow for legibility over the bubble fill
        shad = fonts["swlabel"].render(tag, True, (10, 10, 20))
        ty = max(4, int(sw_cy[i]) - bubble_r - lbl.get_height() - 6)
        arena_surf.blit(shad, (int(sw_cx[i]) - lbl.get_width() // 2 + 1, ty + 1))
        arena_surf.blit(lbl,  (int(sw_cx[i]) - lbl.get_width() // 2,     ty))

    # ── migration countdown overlay ───────────────────────────────────────────
    if step_idx == 3 and not world.migration_fired:
        secs_left = max(0.0, MIGRATE_TIME - world.elapsed)
        if secs_left < 10.0:
            big = fonts["countdown"].render(f"{secs_left:.0f}", True, COL_MIGRATE)
            tag = fonts["label"].render("Migration in", True, COL_MIGRATE)
            mx, my = win_w // 2, arena_h // 2
            ow, oh = max(big.get_width(), tag.get_width()) + 40, 90
            ov = pygame.Surface((ow, oh), pygame.SRCALPHA)
            ov.fill((10, 10, 20, 170))
            arena_surf.blit(ov, (mx - ow // 2, my - oh // 2))
            arena_surf.blit(tag, (mx - tag.get_width() // 2, my - oh // 2 + 8))
            arena_surf.blit(big, (mx - big.get_width() // 2, my - oh // 2 + 32))

    # ── HUD ───────────────────────────────────────────────────────────────────
    t_lbl = fonts["small"].render(f"t = {world.elapsed:.0f}s", True, COL_DIM)
    arena_surf.blit(t_lbl, (8, 8))
    n_clash = len(world.clashing)
    if n_clash:
        c_lbl = fonts["small"].render(f"Clashes: {n_clash}", True, COL_CLASH)
        arena_surf.blit(c_lbl, (8, 8 + t_lbl.get_height() + 2))



# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    os.environ.setdefault('SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS', '0')

    # Resolve monitor bounds before pygame.init() (mirrors study-1 pattern)
    _mon = None
    try:
        from panel_window import monitor_rect
        _mon = monitor_rect(0)
    except Exception:
        pass

    if _mon:
        os.environ['SDL_VIDEO_WINDOW_POS'] = f'{_mon[0]},{_mon[1]}'
    pygame.init()
    os.environ.pop('SDL_VIDEO_WINDOW_POS', None)

    if _mon:
        screen = pygame.display.set_mode((_mon[2], _mon[3]), pygame.NOFRAME)
    else:
        info = pygame.display.Info()
        screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)

    pygame.display.set_caption("Study 2 Demo — Subswarm Channel Assignment")
    clock = pygame.time.Clock()

    win_w, win_h = screen.get_size()
    arena_h = win_h

    # Scale fonts to screen height
    fsc = win_h / 700.0

    def _font(size: int, bold: bool = False) -> pygame.font.Font:
        scaled = max(10, round(size * fsc))
        for name in ("segoeui", "arial", ""):
            try:
                return pygame.font.SysFont(name, scaled, bold=bold)
            except Exception:
                pass
        return pygame.font.Font(None, scaled)

    fonts = {
        "heading":   _font(30, bold=True),
        "body":      _font(21),
        "label":     _font(17, bold=True),   # channel letter inside drone
        "swlabel":   _font(20, bold=True),   # subswarm name above bubble
        "small":     _font(15),
        "hint":      _font(20, bold=True),
        "countdown": _font(52, bold=True),
    }

    world = SubswarmWorld(arena_w=win_w, arena_h=arena_h, seed=7)
    steps = _make_steps(world)
    idx   = 0
    s_t   = 0.0   # time within current step (real seconds)
    pulse = 0.0

    # Snapshot at start of each step for backward navigation
    snapshots: List[Optional[SubswarmWorld]] = [None] * len(steps)
    snapshots[0] = copy.deepcopy(world)

    if steps[0].on_enter:
        steps[0].on_enter(world)

    def goto_step(new_idx: int) -> None:
        nonlocal world, idx, s_t
        if snapshots[new_idx] is None:
            snapshots[new_idx] = copy.deepcopy(world)
        world = copy.deepcopy(snapshots[new_idx])
        idx = new_idx
        s_t = 0.0
        if steps[idx].on_enter:
            steps[idx].on_enter(world)

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        step = steps[idx]

        # ── events ────────────────────────────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key in (pygame.K_SPACE, pygame.K_RIGHT):
                    if idx == len(steps) - 1:
                        running = False
                    elif (s_t >= step.min_time
                          and step.advance_check is None
                          and not step.auto_advance):
                        goto_step(idx + 1)
                elif ev.key == pygame.K_LEFT:
                    if idx > 0:
                        goto_step(idx - 1)

        # ── tick ──────────────────────────────────────────────────────────────
        world.tick(dt, paused=step.freeze)
        s_t   += dt
        pulse  = (pulse + dt * 1.4) % 1.0

        # ── auto-advance ──────────────────────────────────────────────────────
        if idx < len(steps) - 1:
            if step.auto_advance and s_t >= step.min_time:
                goto_step(idx + 1)
            elif step.advance_check is not None and step.advance_check(world):
                goto_step(idx + 1)

        # ── draw ──────────────────────────────────────────────────────────────
        draw_scene(screen, world, idx, fonts, pulse, arena_h)
        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
