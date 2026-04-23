from __future__ import annotations
import math
from typing import Dict, List, Optional, Set, Tuple

import pygame

from robot_world import (
    CHANNELS, WARN_RADIUS, ROBOT_RADIUS,
    SWITCH_DURATION, RobotWorld, Robot,
)

PANEL_W = 310
PANEL_PAD = 14

# ── Colours ───────────────────────────────────────────────────────────────────
COL_ARENA_BG     = (28, 28, 42)
COL_PANEL_BG     = (22, 22, 35)
COL_PANEL_BORDER = (70, 70, 95)
COL_WARN_RING    = (255, 165,  0)
COL_CLASH_EDGE   = (230,  50, 50)
COL_NORMAL_EDGE  = (150, 150, 165)
COL_SELECTED_1   = (255, 240,  60)   # M1 single-select ring
COL_SELECTED_GRP = (90,  200, 255)   # M2/M3 group-select ring
COL_HUD_TEXT     = (210, 210, 225)
COL_DIM_TEXT     = (130, 130, 150)
COL_TITLE        = (240, 240, 255)
COL_TIMER_OK     = (100, 220, 120)
COL_TIMER_LOW    = (240,  80,  80)
COL_CLASH_BAD    = (230,  80,  80)
COL_CLASH_OK     = (100, 200, 120)
COL_POPUP_BG     = (35, 35, 55)
COL_POPUP_BORDER = (90, 90, 120)
COL_BTN_SUGGEST  = (40, 130,  80)
COL_BTN_AUTO     = (40,  90, 160)
COL_BTN_APPLY    = (40, 140,  60)
COL_BTN_CANCEL   = (80,  80, 100)
COL_BTN_BORDER   = (180, 180, 200)
COL_WARN_TEXT    = (230, 160,  40)
COL_DRAG_BOX     = (90, 200, 255, 120)

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
CHANNEL_LABEL = {"red": "RED", "green": "GRN", "blue": "BLU"}
CHANNEL_ABBREV = {"red": "R", "green": "G", "blue": "B"}

# M1 popup geometry
POPUP_W      = 108
POPUP_BTN_H  = 30
POPUP_PAD    = 6
POPUP_H      = POPUP_PAD + (POPUP_BTN_H + POPUP_PAD) * 3

# Suggestion panel row geometry
ROW_H        = 26
BTN_W        = 52
BTN_H        = 20


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
        "tiny":   sf("segoeui", 12),
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
        self._drag_surf  = pygame.Surface((self.arena_w, self.arena_h), pygame.SRCALPHA)

        # Hit-test rects — cleared and rebuilt each frame
        self.popup_rects: Dict[str, pygame.Rect] = {}
        self.hud_button_rects: Dict[str, pygame.Rect] = {}
        # Each entry: (drone_id, channel, rect)
        self.suggestion_drone_rects: List[Tuple[int, str, pygame.Rect]] = []
        self.suggestion_apply_rect:  Optional[pygame.Rect] = None
        self.suggestion_cancel_rect: Optional[pygame.Rect] = None

    # ── Public entry point ────────────────────────────────────────────────────

    def draw_frame(
        self,
        world: RobotWorld,
        state: str,
        popup_drone_id: Optional[int] = None,
        selected_ids: Optional[Set[int]] = None,
        drag_rect: Optional[Tuple[int, int, int, int]] = None,
        suggestion: Optional[Dict[int, str]] = None,
        suggestion_overrides: Optional[Dict[int, str]] = None,
        pending_infeasible: bool = False,
    ) -> None:
        selected_ids = selected_ids or set()
        suggestion_overrides = suggestion_overrides or {}

        # Clear hit-test state
        self.popup_rects.clear()
        self.hud_button_rects.clear()
        self.suggestion_drone_rects.clear()
        self.suggestion_apply_rect  = None
        self.suggestion_cancel_rect = None

        # Arena
        self.screen.fill(COL_ARENA_BG)
        # Panel background
        pygame.draw.rect(self.screen, COL_PANEL_BG,
                         (self.panel_x, 0, PANEL_W, self.window_h))
        pygame.draw.line(self.screen, COL_PANEL_BORDER,
                         (self.panel_x, 0), (self.panel_x, self.window_h), 2)

        self._draw_proximity_circles(world)
        self._draw_edges(world)
        self._draw_robots(world, popup_drone_id, selected_ids)

        if drag_rect is not None:
            self._draw_drag_box(drag_rect)

        # Panel
        if suggestion is not None:
            self._draw_suggestion_panel(
                world, suggestion, suggestion_overrides, pending_infeasible
            )
        else:
            self._draw_hud(world, selected_ids)

        # M1 popup (over arena, after panel so it's not hidden)
        if popup_drone_id is not None and state == "PLAYING" and suggestion is None:
            self._draw_robot_popup(world.robots[popup_drone_id])

        # State overlays
        if state == "PAUSED":
            self._draw_paused_overlay()
        elif state == "ENDED":
            self._draw_end_overlay(world)

    # ── Arena drawing ─────────────────────────────────────────────────────────

    def _draw_proximity_circles(self, world: RobotWorld) -> None:
        self._prox_surf.fill((0, 0, 0, 0))
        connected: set[int] = set()
        for i, j in world.edges:
            connected.add(i); connected.add(j)
        warning: set[int] = set()
        for i, j in world.warning_pairs:
            warning.add(i); warning.add(j)

        for r in world.robots:
            pos = (int(r.x), int(r.y))
            if r.id in connected:
                fill = (255, 165, 0, 22); ring = (255, 165, 0, 160)
            elif r.id in warning:
                fill = (255, 200, 50, 14); ring = (255, 200, 50, 90)
            else:
                fill = (90, 90, 110, 8); ring = (90, 90, 110, 35)
            pygame.draw.circle(self._prox_surf, fill, pos, int(WARN_RADIUS))
            pygame.draw.circle(self._prox_surf, ring, pos, int(WARN_RADIUS), 1)

        self.screen.blit(self._prox_surf, (0, 0))

    def _draw_edges(self, world: RobotWorld) -> None:
        robots = world.robots
        for i, j in world.edges:
            clashing = (i, j) in world.clashing_pairs
            col = COL_CLASH_EDGE if clashing else COL_NORMAL_EDGE
            w   = 3 if clashing else 2
            pygame.draw.line(
                self.screen, col,
                (int(robots[i].x), int(robots[i].y)),
                (int(robots[j].x), int(robots[j].y)), w,
            )

    def _draw_robots(
        self,
        world: RobotWorld,
        popup_drone_id: Optional[int],
        selected_ids: Set[int],
    ) -> None:
        clashing: set[int] = set()
        for i, j in world.clashing_pairs:
            clashing.add(i); clashing.add(j)

        for r in world.robots:
            cx, cy, rad = int(r.x), int(r.y), r.radius

            # Selection rings
            if r.id == popup_drone_id:
                pygame.draw.circle(self.screen, COL_SELECTED_1, (cx, cy), rad + 6, 3)
            elif r.id in selected_ids:
                pygame.draw.circle(self.screen, COL_SELECTED_GRP, (cx, cy), rad + 6, 3)

            body_col = CHANNEL_DIM[r.channel] if r.switching_to else CHANNEL_FILL[r.channel]
            pygame.draw.circle(self.screen, body_col, (cx, cy), rad)

            if r.id in clashing:
                pygame.draw.circle(self.screen, (255, 60, 60), (cx, cy), rad, 2)

            if r.switching_to is not None:
                self._draw_switch_countdown(r)

            lbl = self.fonts["tiny"].render(f"D{r.id}", True, (240, 240, 240))
            self.screen.blit(lbl, lbl.get_rect(center=(cx, cy - rad - 11)))

    def _draw_switch_countdown(self, r: Robot) -> None:
        cx, cy = int(r.x), int(r.y)
        progress = min(r.switch_elapsed / SWITCH_DURATION, 1.0)
        arc_rad  = r.radius + 8
        rect = pygame.Rect(cx - arc_rad, cy - arc_rad, arc_rad * 2, arc_rad * 2)
        if progress > 0.01:
            pygame.draw.arc(
                self.screen, (255, 255, 255), rect,
                math.pi / 2 - 2 * math.pi * progress,
                math.pi / 2, 3,
            )
        secs_left = max(0.0, SWITCH_DURATION - r.switch_elapsed)
        txt = self.fonts["tiny"].render(f"{secs_left:.1f}", True, (255, 255, 255))
        self.screen.blit(txt, txt.get_rect(center=(cx, cy)))
        dot_col = CHANNEL_FILL.get(r.switching_to, (180, 180, 180))
        pygame.draw.circle(self.screen, dot_col, (cx, cy + r.radius + 10), 5)

    def _draw_drag_box(self, drag_rect: Tuple[int, int, int, int]) -> None:
        self._drag_surf.fill((0, 0, 0, 0))
        x, y, w, h = drag_rect
        if w > 0 and h > 0:
            pygame.draw.rect(self._drag_surf, (90, 200, 255, 40), (x, y, w, h))
            pygame.draw.rect(self._drag_surf, (90, 200, 255, 200), (x, y, w, h), 1)
        self.screen.blit(self._drag_surf, (0, 0))

    # ── M1 single-drone popup ─────────────────────────────────────────────────

    def _draw_robot_popup(self, robot: Robot) -> None:
        cx, cy = int(robot.x), int(robot.y)
        gap     = robot.radius + 18
        popup_x = cx - POPUP_W // 2
        popup_y = cy - gap - POPUP_H
        if popup_y < 4:
            popup_y = cy + gap
        popup_x = max(4, min(self.arena_w - POPUP_W - 4, popup_x))

        rect = pygame.Rect(popup_x, popup_y, POPUP_W, POPUP_H)
        pygame.draw.rect(self.screen, COL_POPUP_BG,    rect, border_radius=8)
        pygame.draw.rect(self.screen, COL_POPUP_BORDER, rect, 2, border_radius=8)

        line_x = cx
        if popup_y > cy:
            pygame.draw.line(self.screen, COL_POPUP_BORDER,
                             (line_x, cy + robot.radius + 4), (line_x, popup_y), 1)
        else:
            pygame.draw.line(self.screen, COL_POPUP_BORDER,
                             (line_x, cy - robot.radius - 4), (line_x, popup_y + POPUP_H), 1)

        if robot.switching_to is not None:
            secs = max(0.0, SWITCH_DURATION - robot.switch_elapsed)
            mid_y = popup_y + POPUP_H // 2
            s1 = self.fonts["small"].render("Switching →", True, COL_WARN_RING)
            s2 = self.fonts["popup"].render(
                CHANNEL_LABEL[robot.switching_to], True, CHANNEL_FILL[robot.switching_to])
            s3 = self.fonts["small"].render(f"{secs:.1f}s", True, COL_DIM_TEXT)
            self.screen.blit(s1, s1.get_rect(centerx=cx, y=mid_y - 30))
            self.screen.blit(s2, s2.get_rect(centerx=cx, y=mid_y - 10))
            self.screen.blit(s3, s3.get_rect(centerx=cx, y=mid_y + 14))
        else:
            for idx, ch in enumerate(CHANNELS):
                btn_y   = popup_y + POPUP_PAD + idx * (POPUP_BTN_H + POPUP_PAD)
                btn_rect = pygame.Rect(popup_x + POPUP_PAD, btn_y,
                                       POPUP_W - POPUP_PAD * 2, POPUP_BTN_H)
                self.popup_rects[ch] = btn_rect
                is_current = robot.channel == ch
                fill   = CHANNEL_DIM[ch]   if is_current else CHANNEL_FILL[ch]
                border = (60, 60, 75)      if is_current else (200, 200, 210)
                tcol   = (80, 80, 95)      if is_current else (240, 240, 255)
                label  = CHANNEL_LABEL[ch] + (" ✓" if is_current else "")
                pygame.draw.rect(self.screen, fill,   btn_rect, border_radius=5)
                pygame.draw.rect(self.screen, border, btn_rect, 2, border_radius=5)
                s = self.fonts["popup"].render(label, True, tcol)
                self.screen.blit(s, s.get_rect(center=btn_rect.center))

    # ── Normal HUD panel ──────────────────────────────────────────────────────

    def _panel_sep(self, y: int) -> None:
        pygame.draw.line(self.screen, COL_PANEL_BORDER,
                         (self.panel_x + 4, y), (self.window_w - 4, y), 1)

    def _draw_hud(self, world: RobotWorld, selected_ids: Set[int]) -> None:
        px = self.panel_x + PANEL_PAD
        f  = self.fonts

        self.screen.blit(f["title"].render("DRONE CHANNELS", True, COL_TITLE), (px, 12))
        self._panel_sep(40)

        remaining = max(0.0, world.duration - world.elapsed)
        mins, secs = int(remaining) // 60, int(remaining) % 60
        timer_col = COL_TIMER_LOW if remaining < 20 else COL_TIMER_OK
        self.screen.blit(f["large"].render(f"{mins}:{secs:02d}", True, timer_col), (px, 50))
        self.screen.blit(f["small"].render("remaining", True, COL_DIM_TEXT), (px, 84))

        clash_col = COL_CLASH_BAD if world.clash_seconds > 0 else COL_CLASH_OK
        self.screen.blit(f["large"].render(f"{world.clash_seconds:.1f}s", True, clash_col), (px, 110))
        self.screen.blit(f["small"].render("clash time  (lower is better)", True, COL_DIM_TEXT),
                         (px, 144))

        self._panel_sep(162)

        if selected_ids:
            self._draw_group_buttons(selected_ids, start_y=170)
        else:
            self._draw_instructions(start_y=170)

    def _draw_group_buttons(self, selected_ids: Set[int], start_y: int) -> None:
        px  = self.panel_x + PANEL_PAD
        pw  = PANEL_W - PANEL_PAD * 2
        f   = self.fonts
        k   = len(selected_ids)

        self.screen.blit(
            f["small"].render(f"{k} drone{'s' if k != 1 else ''} selected", True, COL_SELECTED_GRP),
            (px, start_y),
        )

        btn_h = 32
        gap   = 10

        # Suggest button
        sug_rect = pygame.Rect(px, start_y + 22, pw, btn_h)
        pygame.draw.rect(self.screen, COL_BTN_SUGGEST, sug_rect, border_radius=6)
        pygame.draw.rect(self.screen, COL_BTN_BORDER,  sug_rect, 1, border_radius=6)
        s = f["popup"].render(f"Suggest  ({k})", True, (220, 255, 220))
        self.screen.blit(s, s.get_rect(center=sug_rect.center))
        self.hud_button_rects["suggest"] = sug_rect

        # Auto-assign button
        auto_rect = pygame.Rect(px, start_y + 22 + btn_h + gap, pw, btn_h)
        pygame.draw.rect(self.screen, COL_BTN_AUTO, auto_rect, border_radius=6)
        pygame.draw.rect(self.screen, COL_BTN_BORDER, auto_rect, 1, border_radius=6)
        s = f["popup"].render(f"Auto-assign  ({k})", True, (200, 220, 255))
        self.screen.blit(s, s.get_rect(center=auto_rect.center))
        self.hud_button_rects["auto_assign"] = auto_rect

        self._panel_sep(start_y + 22 + btn_h * 2 + gap + 14)
        self._draw_instructions(start_y=start_y + 22 + btn_h * 2 + gap + 22)

    def _draw_instructions(self, start_y: int) -> None:
        px = self.panel_x + PANEL_PAD
        hints = [
            "Click drone → assign (M1)",
            "Drag → select group",
            "Ctrl+click → add/remove",
            "",
            "Suggest: review & edit",
            "Auto-assign: apply at once",
            "",
            "Switch delay: 5 s",
            "Red line = channel clash",
            "Amber ring = approaching",
            "",
            "ESC — quit",
        ]
        y = start_y
        for h in hints:
            s = self.fonts["tiny"].render(h, True, COL_DIM_TEXT)
            self.screen.blit(s, (px, y))
            y += 17

    # ── Suggestion panel ──────────────────────────────────────────────────────

    def _draw_suggestion_panel(
        self,
        world: RobotWorld,
        suggestion: Dict[int, str],
        overrides: Dict[int, str],
        infeasible: bool,
    ) -> None:
        px = self.panel_x + PANEL_PAD
        pw = PANEL_W - PANEL_PAD * 2
        f  = self.fonts

        # ── Compact header ──────────────────────────────────────────────────
        self.screen.blit(f["title"].render("SUGGESTED CHANNELS", True, COL_TITLE), (px, 12))
        self._panel_sep(38)

        remaining = max(0.0, world.duration - world.elapsed)
        mins, secs = int(remaining) // 60, int(remaining) % 60
        timer_col = COL_TIMER_LOW if remaining < 20 else COL_TIMER_OK
        timer_s = f["small"].render(f"⏱ {mins}:{secs:02d}", True, timer_col)
        clash_s = f["small"].render(
            f"Clash: {world.clash_seconds:.1f}s", True,
            COL_CLASH_BAD if world.clash_seconds > 0 else COL_CLASH_OK,
        )
        self.screen.blit(timer_s, (px, 44))
        self.screen.blit(clash_s, (px + pw // 2, 44))
        self._panel_sep(64)

        y = 70
        if infeasible:
            warn_s = f["tiny"].render("⚠ Cannot fully resolve — minimised", True, COL_WARN_TEXT)
            self.screen.blit(warn_s, (px, y))
            y += 18
        else:
            info_s = f["tiny"].render("Review and edit, then Apply.", True, COL_DIM_TEXT)
            self.screen.blit(info_s, (px, y))
            y += 18

        self._panel_sep(y + 2)
        y += 8

        # ── Per-drone rows ──────────────────────────────────────────────────
        drone_ids = sorted(suggestion.keys())
        for drone_id in drone_ids:
            current_ch  = world.robots[drone_id].channel
            effective   = overrides.get(drone_id, suggestion[drone_id])

            # Drone label
            lbl_s = f["tiny"].render(f"D{drone_id:02d}", True, COL_HUD_TEXT)
            self.screen.blit(lbl_s, (px, y + 4))

            # Current channel pill
            pill_x = px + 34
            pill_rect = pygame.Rect(pill_x, y + 2, 46, ROW_H - 6)
            pygame.draw.rect(self.screen, CHANNEL_DIM[current_ch], pill_rect, border_radius=4)
            pill_s = f["tiny"].render(CHANNEL_LABEL[current_ch], True, (200, 200, 200))
            self.screen.blit(pill_s, pill_s.get_rect(center=pill_rect.center))

            # Arrow
            arr_s = f["tiny"].render("→", True, COL_DIM_TEXT)
            self.screen.blit(arr_s, (pill_x + 50, y + 4))

            # 3 channel buttons
            btn_x_start = pill_x + 68
            for ch in CHANNELS:
                is_selected = (effective == ch)
                fill   = CHANNEL_FILL[ch] if is_selected else CHANNEL_DIM[ch]
                border = (220, 220, 230)  if is_selected else (60, 60, 75)
                btn_rect = pygame.Rect(btn_x_start, y + 2, BTN_W, BTN_H)
                pygame.draw.rect(self.screen, fill,   btn_rect, border_radius=4)
                pygame.draw.rect(self.screen, border, btn_rect, 1, border_radius=4)
                abbrev = f["tiny"].render(CHANNEL_ABBREV[ch], True,
                                          (255, 255, 255) if is_selected else (120, 120, 140))
                self.screen.blit(abbrev, abbrev.get_rect(center=btn_rect.center))
                self.suggestion_drone_rects.append((drone_id, ch, btn_rect))
                btn_x_start += BTN_W + 3

            y += ROW_H

        # ── Apply / Cancel ──────────────────────────────────────────────────
        self._panel_sep(y + 4)
        y += 10

        half = (pw - 6) // 2
        apply_rect  = pygame.Rect(px,          y, half, 32)
        cancel_rect = pygame.Rect(px + half + 6, y, half, 32)

        pygame.draw.rect(self.screen, COL_BTN_APPLY,  apply_rect,  border_radius=6)
        pygame.draw.rect(self.screen, COL_BTN_BORDER, apply_rect,  1, border_radius=6)
        pygame.draw.rect(self.screen, COL_BTN_CANCEL, cancel_rect, border_radius=6)
        pygame.draw.rect(self.screen, COL_BTN_BORDER, cancel_rect, 1, border_radius=6)

        s = f["popup"].render("Apply", True, (220, 255, 220))
        self.screen.blit(s, s.get_rect(center=apply_rect.center))
        s = f["popup"].render("Cancel", True, (200, 200, 215))
        self.screen.blit(s, s.get_rect(center=cancel_rect.center))

        self.suggestion_apply_rect  = apply_rect
        self.suggestion_cancel_rect = cancel_rect

    # ── State overlays ────────────────────────────────────────────────────────

    def _draw_paused_overlay(self) -> None:
        overlay = pygame.Surface((self.arena_w, self.arena_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        cx, cy = self.arena_w // 2, self.arena_h // 2
        s = self.fonts["huge"].render("READY", True, COL_TITLE)
        self.screen.blit(s, s.get_rect(centerx=cx, y=cy - 90))
        s = self.fonts["large"].render("Press  SPACE  to start", True, COL_TIMER_OK)
        self.screen.blit(s, s.get_rect(centerx=cx, y=cy - 20))
        hints = [
            "Click a drone → pick channel (M1 — manual)",
            "Drag or Ctrl+click to select a group, then Suggest or Auto-assign",
            "Suggest (M2): review the agent's proposal before applying",
            "Auto-assign (M3): apply immediately without review",
            "Channel switch takes 5 s — act early!",
            "Amber ring = approaching link.  Red line = clash.",
            "Goal: minimise total clash time.",
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

        pct   = (world.clash_seconds / world.duration * 100) if world.duration else 0
        clean = world.duration - world.clash_seconds

        box_w, box_h = 520, 310
        box_x = (self.window_w - box_w) // 2
        box_y = (self.window_h - box_h) // 2
        pygame.draw.rect(self.screen, (30, 30, 48), (box_x, box_y, box_w, box_h), border_radius=14)
        pygame.draw.rect(self.screen, COL_PANEL_BORDER, (box_x, box_y, box_w, box_h), 2, border_radius=14)

        rows = [
            ("TRIAL OVER",                                                      "huge",   COL_TITLE),
            (f"Duration:      {world.duration:.0f} s",                          "medium", COL_HUD_TEXT),
            (f"Clash time:    {world.clash_seconds:.1f} s  ({pct:.1f}%)",       "medium", COL_CLASH_BAD),
            (f"Clean time:    {clean:.1f} s",                                   "medium", COL_CLASH_OK),
            ("",                                                                 None,     None),
            ("R — play again          Q — quit",                                "small",  COL_DIM_TEXT),
        ]
        y  = box_y + 28
        cx = self.window_w // 2
        for text, fkey, col in rows:
            if fkey is None:
                y += 12; continue
            s = self.fonts[fkey].render(text, True, col)
            self.screen.blit(s, s.get_rect(centerx=cx, y=y))
            y += s.get_height() + 14
