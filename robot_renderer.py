from __future__ import annotations
import math
from typing import Optional

import pygame

from robot_world import (
    CHANNELS, WARN_RADIUS, ROBOT_RADIUS,
    SWITCH_DURATION, RobotWorld, Robot,
)

PANEL_W = 260
PANEL_PAD = 14

COL_ARENA_BG     = (28, 28, 42)
COL_PANEL_BG     = (22, 22, 35)
COL_PANEL_BORDER = (70, 70, 95)
COL_WARN_RING    = (255, 165,  0)
COL_CLASH_EDGE   = (230,  50, 50)
COL_NORMAL_EDGE  = (150, 150, 165)
COL_SELECTED     = (255, 240,  60)
COL_HUD_TEXT     = (210, 210, 225)
COL_DIM_TEXT     = (130, 130, 150)
COL_TITLE        = (240, 240, 255)
COL_TIMER_OK     = (100, 220, 120)
COL_TIMER_LOW    = (240,  80,  80)
COL_CLASH_BAD    = (230,  80,  80)
COL_CLASH_OK     = (100, 200, 120)
COL_POPUP_BG     = (35, 35, 55)
COL_POPUP_BORDER = (90, 90, 120)

CHANNEL_FILL = {
    "red":   (210,  55,  55),
    "green": ( 55, 190,  80),
    "blue":  ( 55, 110, 210),
}
CHANNEL_DIM = {
    "red":   (100,  35,  35),
    "green": ( 35,  90,  45),
    "blue":  ( 35,  60, 110),
}
CHANNEL_LABEL = {"red": "RED", "green": "GREEN", "blue": "BLUE"}

POPUP_W   = 108
POPUP_BTN_H = 30
POPUP_PAD = 6
POPUP_H   = POPUP_PAD + (POPUP_BTN_H + POPUP_PAD) * 3  # 6 + 3*(30+6) = 114


def _make_fonts() -> dict[str, pygame.font.Font]:
    def sf(name: str, size: int, bold: bool = False) -> pygame.font.Font:
        f = pygame.font.SysFont(name, size, bold=bold)
        return f if f is not None else pygame.font.Font(None, size)
    return {
        "small":  sf("segoeui", 14),
        "medium": sf("segoeui", 17),
        "large":  sf("segoeui", 26, bold=True),
        "title":  sf("segoeui", 20, bold=True),
        "huge":   sf("segoeui", 42, bold=True),
        "popup":  sf("segoeui", 15, bold=True),
    }


class RobotRenderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.window_w, self.window_h = screen.get_size()
        self.arena_w = self.window_w - PANEL_W
        self.arena_h = self.window_h
        self.panel_x = self.arena_w

        self.fonts = _make_fonts()
        self._prox_surf = pygame.Surface((self.arena_w, self.arena_h), pygame.SRCALPHA)

        # Hit-test rects updated each frame during popup drawing
        self.popup_rects: dict[str, pygame.Rect] = {}

        # Panel Y anchors
        self._sep1_y   = 40
        self._timer_y  = 50
        self._clash_y  = 114
        self._sep2_y   = 162
        self._instr_y  = 170

    # ── Public ─────────────────────────────────────────────────────────────────

    def draw_frame(
        self,
        world: RobotWorld,
        selected_id: Optional[int],
        state: str,
    ) -> None:
        self.screen.fill(COL_ARENA_BG)
        pygame.draw.rect(self.screen, COL_PANEL_BG,
                         (self.panel_x, 0, PANEL_W, self.window_h))
        pygame.draw.line(self.screen, COL_PANEL_BORDER,
                         (self.panel_x, 0), (self.panel_x, self.window_h), 2)

        self._draw_proximity_circles(world)
        self._draw_edges(world)
        self._draw_robots(world, selected_id)
        self._draw_hud(world)

        # Draw popup over the selected robot (after everything else in arena)
        self.popup_rects.clear()
        if selected_id is not None and state == "PLAYING":
            self._draw_robot_popup(world.robots[selected_id])

        if state == "PAUSED":
            self._draw_paused_overlay()
        elif state == "ENDED":
            self._draw_end_overlay(world)

    # ── Arena ──────────────────────────────────────────────────────────────────

    def _draw_proximity_circles(self, world: RobotWorld) -> None:
        self._prox_surf.fill((0, 0, 0, 0))

        # Which robots are in connected or approaching state
        connected_robots: set[int] = set()
        for i, j in world.edges:
            connected_robots.add(i); connected_robots.add(j)
        warning_robots: set[int] = set()
        for i, j in world.warning_pairs:
            warning_robots.add(i); warning_robots.add(j)

        for r in world.robots:
            pos = (int(r.x), int(r.y))
            if r.id in connected_robots:
                fill = (255, 165, 0, 22)
                ring = (255, 165, 0, 160)
            elif r.id in warning_robots:
                fill = (255, 200, 50, 14)
                ring = (255, 200, 50, 90)
            else:
                fill = (90, 90, 110, 8)
                ring = (90, 90, 110, 35)
            pygame.draw.circle(self._prox_surf, fill, pos, int(WARN_RADIUS))
            pygame.draw.circle(self._prox_surf, ring, pos, int(WARN_RADIUS), 1)

        self.screen.blit(self._prox_surf, (0, 0))

    def _draw_edges(self, world: RobotWorld) -> None:
        robots = world.robots
        for i, j in world.edges:
            clashing = (i, j) in world.clashing_pairs
            col = COL_CLASH_EDGE if clashing else COL_NORMAL_EDGE
            w = 3 if clashing else 2
            pygame.draw.line(
                self.screen, col,
                (int(robots[i].x), int(robots[i].y)),
                (int(robots[j].x), int(robots[j].y)), w,
            )

    def _draw_robots(self, world: RobotWorld, selected_id: Optional[int]) -> None:
        clashing_robots: set[int] = set()
        for i, j in world.clashing_pairs:
            clashing_robots.add(i); clashing_robots.add(j)

        for r in world.robots:
            cx, cy, rad = int(r.x), int(r.y), r.radius

            if r.id == selected_id:
                pygame.draw.circle(self.screen, COL_SELECTED, (cx, cy), rad + 6, 3)

            body_col = CHANNEL_DIM[r.channel] if r.switching_to else CHANNEL_FILL[r.channel]
            pygame.draw.circle(self.screen, body_col, (cx, cy), rad)

            if r.id in clashing_robots:
                pygame.draw.circle(self.screen, (255, 60, 60), (cx, cy), rad, 2)

            if r.switching_to is not None:
                self._draw_switch_countdown(r)

            lbl = self.fonts["small"].render(f"R{r.id}", True, (240, 240, 240))
            self.screen.blit(lbl, lbl.get_rect(center=(cx, cy - rad - 11)))

    def _draw_switch_countdown(self, r: Robot) -> None:
        cx, cy = int(r.x), int(r.y)
        progress = min(r.switch_elapsed / SWITCH_DURATION, 1.0)
        arc_rad = r.radius + 8
        rect = pygame.Rect(cx - arc_rad, cy - arc_rad, arc_rad * 2, arc_rad * 2)
        if progress > 0.01:
            pygame.draw.arc(
                self.screen, (255, 255, 255), rect,
                math.pi / 2 - 2 * math.pi * progress,
                math.pi / 2, 3,
            )
        secs_left = max(0.0, SWITCH_DURATION - r.switch_elapsed)
        txt = self.fonts["small"].render(f"{secs_left:.1f}", True, (255, 255, 255))
        self.screen.blit(txt, txt.get_rect(center=(cx, cy)))
        dot_col = CHANNEL_FILL.get(r.switching_to, (180, 180, 180))
        pygame.draw.circle(self.screen, dot_col, (cx, cy + r.radius + 10), 5)

    # ── Floating popup ─────────────────────────────────────────────────────────

    def _draw_robot_popup(self, robot: Robot) -> None:
        cx, cy = int(robot.x), int(robot.y)

        # Position above the robot; flip below if near top edge
        gap = robot.radius + 18
        popup_x = cx - POPUP_W // 2
        popup_y = cy - gap - POPUP_H

        if popup_y < 4:
            popup_y = cy + gap  # show below instead

        # Clamp horizontally inside arena
        popup_x = max(4, min(self.arena_w - POPUP_W - 4, popup_x))

        # Background card
        rect = pygame.Rect(popup_x, popup_y, POPUP_W, POPUP_H)
        pygame.draw.rect(self.screen, COL_POPUP_BG, rect, border_radius=8)
        pygame.draw.rect(self.screen, COL_POPUP_BORDER, rect, 2, border_radius=8)

        # Connector line from popup to robot
        line_x = cx
        if popup_y > cy:
            pygame.draw.line(self.screen, COL_POPUP_BORDER,
                             (line_x, cy + robot.radius + 4),
                             (line_x, popup_y), 1)
        else:
            pygame.draw.line(self.screen, COL_POPUP_BORDER,
                             (line_x, cy - robot.radius - 4),
                             (line_x, popup_y + POPUP_H), 1)

        if robot.switching_to is not None:
            # Show "switching…" text instead of buttons
            secs = max(0.0, SWITCH_DURATION - robot.switch_elapsed)
            msg1 = self.fonts["small"].render("Switching →", True, COL_WARN_RING)
            msg2 = self.fonts["popup"].render(
                CHANNEL_LABEL[robot.switching_to], True, CHANNEL_FILL[robot.switching_to])
            msg3 = self.fonts["small"].render(f"{secs:.1f}s", True, COL_DIM_TEXT)
            mid_y = popup_y + POPUP_H // 2
            self.screen.blit(msg1, msg1.get_rect(centerx=cx, y=mid_y - 30))
            self.screen.blit(msg2, msg2.get_rect(centerx=cx, y=mid_y - 10))
            self.screen.blit(msg3, msg3.get_rect(centerx=cx, y=mid_y + 14))
        else:
            # Channel buttons
            for idx, ch in enumerate(CHANNELS):
                btn_y = popup_y + POPUP_PAD + idx * (POPUP_BTN_H + POPUP_PAD)
                btn_rect = pygame.Rect(popup_x + POPUP_PAD, btn_y,
                                       POPUP_W - POPUP_PAD * 2, POPUP_BTN_H)
                self.popup_rects[ch] = btn_rect

                is_current = robot.channel == ch
                fill   = CHANNEL_DIM[ch]   if is_current else CHANNEL_FILL[ch]
                border = (60, 60, 75)      if is_current else (200, 200, 210)
                tcol   = (80, 80, 95)      if is_current else (240, 240, 255)
                label  = CHANNEL_LABEL[ch] + (" ✓" if is_current else "")

                pygame.draw.rect(self.screen, fill, btn_rect, border_radius=5)
                pygame.draw.rect(self.screen, border, btn_rect, 2, border_radius=5)
                s = self.fonts["popup"].render(label, True, tcol)
                self.screen.blit(s, s.get_rect(center=btn_rect.center))

    # ── Right panel ────────────────────────────────────────────────────────────

    def _panel_sep(self, y: int) -> None:
        pygame.draw.line(self.screen, COL_PANEL_BORDER,
                         (self.panel_x + 4, y), (self.window_w - 4, y), 1)

    def _draw_hud(self, world: RobotWorld) -> None:
        px = self.panel_x + PANEL_PAD
        f = self.fonts

        self.screen.blit(f["title"].render("ROBOT CHANNELS", True, COL_TITLE), (px, 12))
        self._panel_sep(self._sep1_y)

        remaining = max(0.0, world.duration - world.elapsed)
        mins, secs = int(remaining) // 60, int(remaining) % 60
        timer_col = COL_TIMER_LOW if remaining < 20 else COL_TIMER_OK
        self.screen.blit(f["large"].render(f"{mins}:{secs:02d}", True, timer_col), (px, self._timer_y))
        self.screen.blit(f["small"].render("remaining", True, COL_DIM_TEXT), (px, self._timer_y + 34))

        clash_col = COL_CLASH_BAD if world.clash_seconds > 0 else COL_CLASH_OK
        self.screen.blit(f["large"].render(f"{world.clash_seconds:.1f}s", True, clash_col), (px, self._clash_y))
        self.screen.blit(f["small"].render("clash time  (lower = better)", True, COL_DIM_TEXT),
                         (px, self._clash_y + 34))

        self._panel_sep(self._sep2_y)

        hints = [
            "Click robot → choose channel",
            "  in the popup that appears.",
            "",
            "5 s delay to switch.",
            "Circles overlap = link forms.",
            "Red line = channel clash.",
            "",
            "ESC — quit",
        ]
        y = self._instr_y
        for h in hints:
            self.screen.blit(f["small"].render(h, True, COL_DIM_TEXT), (px, y))
            y += 19

    # ── Overlays ───────────────────────────────────────────────────────────────

    def _draw_paused_overlay(self) -> None:
        overlay = pygame.Surface((self.arena_w, self.arena_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        cx = self.arena_w // 2
        cy = self.arena_h // 2

        self.screen.blit(
            self.fonts["huge"].render("READY", True, COL_TITLE),
            self.fonts["huge"].render("READY", True, COL_TITLE).get_rect(centerx=cx, y=cy - 90),
        )
        sub = self.fonts["large"].render("Press  SPACE  to start", True, COL_TIMER_OK)
        self.screen.blit(sub, sub.get_rect(centerx=cx, y=cy - 20))

        hints = [
            "Click a robot → pick RED / GREEN / BLUE in the popup above it",
            "Channel switch takes 5 seconds — plan ahead!",
            "Circles overlap = robots are linked.  Red line = channel clash.",
            "Goal: minimise total clash time over 2 minutes.",
        ]
        y = cy + 36
        for h in hints:
            s = self.fonts["small"].render(h, True, COL_DIM_TEXT)
            self.screen.blit(s, s.get_rect(centerx=cx, y=y))
            y += 22

    def _draw_end_overlay(self, world: RobotWorld) -> None:
        overlay = pygame.Surface((self.window_w, self.window_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 185))
        self.screen.blit(overlay, (0, 0))

        pct = (world.clash_seconds / world.duration * 100) if world.duration else 0
        clean = world.duration - world.clash_seconds

        box_w, box_h = 500, 330
        box_x = (self.window_w - box_w) // 2
        box_y = (self.window_h - box_h) // 2
        pygame.draw.rect(self.screen, (30, 30, 48), (box_x, box_y, box_w, box_h), border_radius=14)
        pygame.draw.rect(self.screen, COL_PANEL_BORDER, (box_x, box_y, box_w, box_h), 2, border_radius=14)

        rows = [
            ("GAME OVER",                                                   "huge",   COL_TITLE),
            (f"Duration:      {world.duration:.0f} s",                     "medium", COL_HUD_TEXT),
            (f"Clash time:    {world.clash_seconds:.1f} s  ({pct:.1f}%)", "medium", COL_CLASH_BAD),
            (f"Clean time:    {clean:.1f} s",                              "medium", COL_CLASH_OK),
            ("",                                                            None,     None),
            ("R — play again          Q — quit",                           "small",  COL_DIM_TEXT),
        ]
        y = box_y + 28
        cx = self.window_w // 2
        for text, fkey, col in rows:
            if fkey is None:
                y += 12; continue
            s = self.fonts[fkey].render(text, True, col)
            self.screen.blit(s, s.get_rect(centerx=cx, y=y))
            y += s.get_height() + 14
