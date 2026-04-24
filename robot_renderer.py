from __future__ import annotations
import math
from dataclasses import dataclass, field
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
COL_UNCOLOURED   = (65, 65, 80)
COL_MINIGRAPH_BG = (18, 18, 32)

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
CHANNEL_LABEL  = {"red": "RED", "green": "GRN", "blue": "BLU"}
CHANNEL_ABBREV = {"red": "R",   "green": "G",   "blue": "B"}

# Tutorial callout colour
COL_CALLOUT_BG  = (20, 20, 40, 215)
COL_CALLOUT_BDR = (90, 160, 255)


@dataclass
class TutorialCallout:
    heading: str
    body: str
    highlight_ids: List[int]          = field(default_factory=list)
    highlight_color: Tuple[int,int,int] = (255, 240, 60)
    pulse_phase: float                = 0.0
    dim_arena: bool                   = False
    advance_on_space: bool            = True
    disabled_buttons: frozenset       = field(default_factory=frozenset)
    hint_override: Optional[str]      = None

# M1 popup geometry
POPUP_W      = 108
POPUP_BTN_H  = 30
POPUP_PAD    = 6
POPUP_H      = POPUP_PAD + (POPUP_BTN_H + POPUP_PAD) * 3

# Mini-graph node radii
MINI_RAD     = 9    # suggestion nodes
MINI_RAD_NBR = 5    # neighbour nodes
MINI_PAD     = 16   # inset from mini-graph border


def _wrap_text(text: str, max_chars: int = 90) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return lines


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
        self.popup_rects:                Dict[str, pygame.Rect] = {}
        self.hud_button_rects:           Dict[str, pygame.Rect] = {}
        self.suggestion_node_rects:      Dict[int, pygame.Rect] = {}
        self.suggestion_channel_btn_rects: Dict[str, pygame.Rect] = {}
        self.suggestion_apply_rect:  Optional[pygame.Rect] = None
        self.suggestion_cancel_rect: Optional[pygame.Rect] = None

        # Updated each frame from world
        self._switch_duration: float = SWITCH_DURATION
        self._tutorial_disabled: frozenset = frozenset()

        # Detached panel support
        self._panel_surface: Optional[pygame.Surface] = None  # set when detached
        self._panel_offset_x: int = 0  # x coord where panel starts on screen (0 when detached)

        # Active panel drawing targets — set at start of each frame
        self._ps: pygame.Surface = screen          # current panel surface
        self._px: int = self.panel_x              # current panel origin x

    # ── Public entry point ────────────────────────────────────────────────────

    def update_screen(self, new_screen: pygame.Surface) -> None:
        """Replace the main display surface (call after pygame.display.set_mode)."""
        self.screen = new_screen
        self._ps    = new_screen          # reset active panel target too
        self.window_w, self.window_h = new_screen.get_size()
        # Recreate alpha compositing surfaces at the correct size
        self._prox_surf = pygame.Surface((self.arena_w, self.window_h), pygame.SRCALPHA)
        self._drag_surf  = pygame.Surface((self.arena_w, self.window_h), pygame.SRCALPHA)

    def set_panel_surface(self, surf: Optional[pygame.Surface]) -> None:
        """
        Attach an external surface for the side panel (separate window mode).
        Call once at setup (or when the panel window changes). For the per-frame
        SDL2 surface refresh, use refresh_panel_surface() instead.
        """
        self._panel_surface = surf
        if surf is None:
            self._panel_offset_x = self.panel_x
            self.arena_w = self.window_w - PANEL_W
        else:
            # Center PANEL_W content if the panel window is wider
            surf_w = surf.get_width()
            self._panel_offset_x = max(0, (surf_w - PANEL_W) // 2)
            # Arena expands to fill the full main window
            self.arena_w = self.window_w
        # Recreate compositing surfaces to match the new arena width
        self._prox_surf = pygame.Surface((self.arena_w, self.window_h), pygame.SRCALPHA)
        self._drag_surf  = pygame.Surface((self.arena_w, self.window_h), pygame.SRCALPHA)

    def refresh_panel_surface(self, surf: pygame.Surface) -> None:
        """
        Replace the panel surface reference each frame (SDL2 surfaces become
        stale after flip()).  Does not recompute layout or recreate surfaces.
        """
        self._panel_surface = surf

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
        tutorial_callout: Optional[TutorialCallout] = None,
        panel_detached: bool = False,
    ) -> None:
        selected_ids       = selected_ids or set()
        suggestion_overrides = suggestion_overrides or {}

        # Per-frame world state
        self._switch_duration = world.switch_duration
        self._tutorial_disabled = frozenset(tutorial_callout.disabled_buttons) if tutorial_callout else frozenset()

        # Clear hit-test state
        self.popup_rects.clear()
        self.hud_button_rects.clear()
        self.suggestion_node_rects.clear()
        self.suggestion_channel_btn_rects.clear()
        self.suggestion_apply_rect  = None
        self.suggestion_cancel_rect = None

        # Set active panel drawing targets for this frame
        if panel_detached and self._panel_surface is not None:
            self._ps = self._panel_surface
            self._px = self._panel_offset_x
        else:
            self._ps = self.screen
            self._px = self.panel_x

        # Backgrounds
        self.screen.fill(COL_ARENA_BG)
        if not panel_detached:
            pygame.draw.rect(self.screen, COL_PANEL_BG,
                             (self.panel_x, 0, PANEL_W, self.window_h))
            pygame.draw.line(self.screen, COL_PANEL_BORDER,
                             (self.panel_x, 0), (self.panel_x, self.window_h), 2)
        else:
            self._ps.fill(COL_PANEL_BG)

        self._draw_proximity_circles(world)
        self._draw_edges(world)

        # Show proposed channels on arena drones when suggestion is active
        suggestion_channels = suggestion_overrides if suggestion is not None else None
        self._draw_robots(world, popup_drone_id, selected_ids, suggestion_channels)

        if drag_rect is not None:
            self._draw_drag_box(drag_rect)

        # Panel (all methods now use self._ps / self._px)
        if suggestion is not None:
            self._draw_suggestion_panel(
                world, suggestion, suggestion_overrides, pending_infeasible,
                selected_node=popup_drone_id,
            )
        else:
            n_assigned = sum(1 for r in world.robots if r.channel is not None)
            self._draw_hud(world, selected_ids, state, n_assigned)

        # M1 arena popup — only in normal (non-suggestion) mode
        if popup_drone_id is not None and suggestion is None and state in ("PLAYING", "SETUP"):
            self._draw_robot_popup(world.robots[popup_drone_id])

        # Tutorial callout (drawn after everything else so it sits on top)
        if tutorial_callout is not None:
            self._draw_tutorial_callout(tutorial_callout, world)

        # State overlays (skip PAUSED overlay when tutorial handles dimming)
        if state == "PAUSED" and tutorial_callout is None:
            self._draw_paused_overlay()
        elif state == "SETUP" and tutorial_callout is None:
            n_assigned = sum(1 for r in world.robots if r.channel is not None)
            self._draw_setup_banner(all_assigned=(n_assigned == len(world.robots)))
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
        suggestion_channels: Optional[Dict[int, str]] = None,
    ) -> None:
        clashing: set[int] = set()
        for i, j in world.clashing_pairs:
            clashing.add(i); clashing.add(j)

        for r in world.robots:
            cx, cy, rad = int(r.x), int(r.y), r.radius
            in_suggestion = suggestion_channels is not None and r.id in suggestion_channels
            display_ch    = suggestion_channels[r.id] if in_suggestion else r.channel

            if r.id == popup_drone_id:
                pygame.draw.circle(self.screen, COL_SELECTED_1, (cx, cy), rad + 6, 3)
            elif in_suggestion:
                pygame.draw.circle(self.screen, COL_SELECTED_GRP, (cx, cy), rad + 6, 3)
            elif r.id in selected_ids:
                pygame.draw.circle(self.screen, COL_SELECTED_GRP, (cx, cy), rad + 6, 3)

            if display_ch is None:
                body_col = COL_UNCOLOURED
            elif in_suggestion:
                body_col = CHANNEL_FILL[display_ch]
            else:
                body_col = CHANNEL_DIM[r.channel] if r.switching_to else CHANNEL_FILL[r.channel]
            pygame.draw.circle(self.screen, body_col, (cx, cy), rad)

            if r.id in clashing:
                pygame.draw.circle(self.screen, (255, 60, 60), (cx, cy), rad, 2)

            if r.switching_to is not None and not in_suggestion:
                self._draw_switch_countdown(r)

            lbl = self.fonts["tiny"].render(f"D{r.id}", True, (240, 240, 240))
            self.screen.blit(lbl, lbl.get_rect(center=(cx, cy - rad - 11)))

    def _draw_switch_countdown(self, r: Robot) -> None:
        cx, cy = int(r.x), int(r.y)
        if self._switch_duration > 0:
            progress  = min(r.switch_elapsed / self._switch_duration, 1.0)
            secs_left = max(0.0, self._switch_duration - r.switch_elapsed)
        else:
            progress  = 1.0
            secs_left = 0.0

        arc_rad = r.radius + 8
        rect = pygame.Rect(cx - arc_rad, cy - arc_rad, arc_rad * 2, arc_rad * 2)
        if progress > 0.01:
            pygame.draw.arc(
                self.screen, (255, 255, 255), rect,
                math.pi / 2 - 2 * math.pi * progress,
                math.pi / 2, 3,
            )
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

    # ── M1 popup ──────────────────────────────────────────────────────────────

    def _draw_robot_popup(self, robot: Robot, effective_channel: Optional[str] = None) -> None:
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

        if robot.switching_to is not None and effective_channel is None:
            secs   = max(0.0, self._switch_duration - robot.switch_elapsed)
            mid_y  = popup_y + POPUP_H // 2
            s1 = self.fonts["small"].render("Switching →", True, COL_WARN_RING)
            s2 = self.fonts["popup"].render(
                CHANNEL_LABEL[robot.switching_to], True, CHANNEL_FILL[robot.switching_to])
            s3 = self.fonts["small"].render(f"{secs:.1f}s", True, COL_DIM_TEXT)
            self.screen.blit(s1, s1.get_rect(centerx=cx, y=mid_y - 30))
            self.screen.blit(s2, s2.get_rect(centerx=cx, y=mid_y - 10))
            self.screen.blit(s3, s3.get_rect(centerx=cx, y=mid_y + 14))
        else:
            current_ch = effective_channel if effective_channel is not None else robot.channel
            for idx, ch in enumerate(CHANNELS):
                btn_y    = popup_y + POPUP_PAD + idx * (POPUP_BTN_H + POPUP_PAD)
                btn_rect = pygame.Rect(popup_x + POPUP_PAD, btn_y,
                                       POPUP_W - POPUP_PAD * 2, POPUP_BTN_H)
                self.popup_rects[ch] = btn_rect
                is_current = current_ch == ch
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
        pw = self._px + PANEL_W
        pygame.draw.line(self._ps, COL_PANEL_BORDER,
                         (self._px + 4, y), (pw - 4, y), 1)

    def _draw_hud(
        self,
        world: RobotWorld,
        selected_ids: Set[int],
        state: str = "PLAYING",
        n_assigned: int = 0,
    ) -> None:
        px = self._px + PANEL_PAD
        f  = self.fonts

        if state == "SETUP":
            self._ps.blit(f["title"].render("SETUP", True, COL_TITLE), (px, 12))
            self._panel_sep(40)

            n_total  = len(world.robots)
            all_done = n_assigned == n_total
            count_col = COL_CLASH_OK if all_done else COL_WARN_TEXT
            self._ps.blit(f["large"].render(f"{n_assigned} / {n_total}", True, count_col), (px, 52))
            self._ps.blit(f["small"].render("drones assigned", True, COL_DIM_TEXT), (px, 86))
            self._panel_sep(108)

            hints: list[tuple[str, tuple[int, int, int]]] = [
                ("Click drone → pick channel (M1)", COL_DIM_TEXT),
                ("Drag / Ctrl+click → group select", COL_DIM_TEXT),
                ("Suggest → review in panel (M2)", COL_DIM_TEXT),
                ("Auto-assign → apply at once (M3)", COL_DIM_TEXT),
                ("", COL_DIM_TEXT),
            ]
            if all_done:
                hints += [("All set!  SPACE to start.", COL_TIMER_OK)]
            else:
                hints += [(f"⚠  {n_total - n_assigned} drone(s) unassigned", COL_WARN_TEXT)]
            hints += [("", COL_DIM_TEXT), ("ESC — quit", COL_DIM_TEXT)]

            y = 118
            for text, col in hints:
                s = f["tiny"].render(text, True, col)
                self._ps.blit(s, (px, y))
                y += 17

            if selected_ids:
                self._panel_sep(y + 4)
                self._draw_group_buttons(selected_ids, start_y=y + 12)
            return

        self._ps.blit(f["title"].render("DRONE CHANNELS", True, COL_TITLE), (px, 12))
        self._panel_sep(40)

        remaining = max(0.0, world.duration - world.elapsed)
        mins, secs = int(remaining) // 60, int(remaining) % 60
        timer_col = COL_TIMER_LOW if remaining < 20 else COL_TIMER_OK
        self._ps.blit(f["large"].render(f"{mins}:{secs:02d}", True, timer_col), (px, 50))
        self._ps.blit(f["small"].render("remaining", True, COL_DIM_TEXT), (px, 84))

        clash_col = COL_CLASH_BAD if world.clash_seconds > 0 else COL_CLASH_OK
        self._ps.blit(f["large"].render(f"{world.clash_seconds:.1f}s", True, clash_col), (px, 110))
        self._ps.blit(
            f["small"].render("clash time  (lower is better)", True, COL_DIM_TEXT),
            (px, 144),
        )

        self._panel_sep(162)

        if selected_ids:
            self._draw_group_buttons(selected_ids, start_y=170)
        else:
            self._draw_instructions(start_y=170)

    def _draw_group_buttons(self, selected_ids: Set[int], start_y: int) -> None:
        px  = self._px + PANEL_PAD
        pw  = PANEL_W - PANEL_PAD * 2
        f   = self.fonts
        k   = len(selected_ids)

        self._ps.blit(
            f["small"].render(f"{k} drone{'s' if k != 1 else ''} selected", True, COL_SELECTED_GRP),
            (px, start_y),
        )

        btn_h = 32
        gap   = 10

        sug_rect = pygame.Rect(px, start_y + 22, pw, btn_h)
        if "suggest" in self._tutorial_disabled:
            pygame.draw.rect(self._ps, (42, 52, 48), sug_rect, border_radius=6)
            pygame.draw.rect(self._ps, (68, 78, 72), sug_rect, 1, border_radius=6)
            s = f["popup"].render(f"Suggest  ({k})", True, (80, 100, 90))
        else:
            pygame.draw.rect(self._ps, COL_BTN_SUGGEST, sug_rect, border_radius=6)
            pygame.draw.rect(self._ps, COL_BTN_BORDER,  sug_rect, 1, border_radius=6)
            s = f["popup"].render(f"Suggest  ({k})", True, (220, 255, 220))
            self.hud_button_rects["suggest"] = sug_rect
        self._ps.blit(s, s.get_rect(center=sug_rect.center))

        auto_rect = pygame.Rect(px, start_y + 22 + btn_h + gap, pw, btn_h)
        if "auto_assign" in self._tutorial_disabled:
            pygame.draw.rect(self._ps, (38, 44, 58), auto_rect, border_radius=6)
            pygame.draw.rect(self._ps, (62, 68, 86), auto_rect, 1, border_radius=6)
            s = f["popup"].render(f"Auto-assign  ({k})", True, (70, 80, 110))
        else:
            pygame.draw.rect(self._ps, COL_BTN_AUTO, auto_rect, border_radius=6)
            pygame.draw.rect(self._ps, COL_BTN_BORDER, auto_rect, 1, border_radius=6)
            s = f["popup"].render(f"Auto-assign  ({k})", True, (200, 220, 255))
            self.hud_button_rects["auto_assign"] = auto_rect
        self._ps.blit(s, s.get_rect(center=auto_rect.center))

        self._panel_sep(start_y + 22 + btn_h * 2 + gap + 14)
        self._draw_instructions(start_y=start_y + 22 + btn_h * 2 + gap + 22)

    def _draw_instructions(self, start_y: int) -> None:
        px = self._px + PANEL_PAD
        sw = self._switch_duration
        delay_text = "instant" if sw == 0 else f"{sw:.0f} s"
        hints = [
            "Click drone → assign (M1)",
            "Drag → select group",
            "Ctrl+click → add/remove",
            "",
            "Suggest → review in panel (M2)",
            "Auto-assign → apply at once (M3)",
            "",
            f"Switch delay: {delay_text}",
            "Red line = channel clash",
            "Amber ring = approaching",
            "",
            "ESC — quit",
        ]
        y = start_y
        for h in hints:
            s = self.fonts["tiny"].render(h, True, COL_DIM_TEXT)
            self._ps.blit(s, (px, y))
            y += 17

    # ── Suggestion panel with live mini-graph ─────────────────────────────────

    def _draw_suggestion_panel(
        self,
        world: RobotWorld,
        suggestion: Dict[int, str],
        overrides: Dict[int, str],
        infeasible: bool,
        selected_node: Optional[int] = None,
    ) -> None:
        px = self._px + PANEL_PAD
        pw = PANEL_W - PANEL_PAD * 2
        f  = self.fonts
        ps = self._ps

        # Header
        ps.blit(f["title"].render("SUGGESTED CHANNELS", True, COL_TITLE), (px, 12))
        self._panel_sep(38)

        remaining = max(0.0, world.duration - world.elapsed)
        mins, secs_r = int(remaining) // 60, int(remaining) % 60
        timer_col = COL_TIMER_LOW if remaining < 20 else COL_TIMER_OK
        ps.blit(f["small"].render(f"⏱ {mins}:{secs_r:02d}", True, timer_col), (px, 44))
        ps.blit(
            f["small"].render(
                f"Clash: {world.clash_seconds:.1f}s", True,
                COL_CLASH_BAD if world.clash_seconds > 0 else COL_CLASH_OK,
            ),
            (px + pw // 2, 44),
        )
        self._panel_sep(64)

        # ── Mini live graph ───────────────────────────────────────────────────
        mg_y = 72
        mg_w = pw
        panel_h = ps.get_height()
        mg_aspect = world.arena_h / world.arena_w if world.arena_w > 0 else 1.0
        mg_h_ideal = int(mg_w * mg_aspect)
        bottom_reserve = 140
        mg_h = max(80, min(mg_h_ideal, panel_h - mg_y - bottom_reserve))
        mg_x = self._px + PANEL_PAD

        pygame.draw.rect(ps, COL_MINIGRAPH_BG,
                         (mg_x - 1, mg_y - 1, mg_w + 2, mg_h + 2), border_radius=4)
        pygame.draw.rect(ps, COL_PANEL_BORDER,
                         (mg_x - 1, mg_y - 1, mg_w + 2, mg_h + 2), 1, border_radius=4)

        # Node sets
        suggestion_ids: set[int] = set(suggestion.keys())
        neighbor_ids:   set[int] = set()
        for i, j in world.edges:
            if i in suggestion_ids and j not in suggestion_ids:
                neighbor_ids.add(j)
            elif j in suggestion_ids and i not in suggestion_ids:
                neighbor_ids.add(i)
        shown_ids = suggestion_ids | neighbor_ids

        def to_mini(rx: float, ry: float) -> Tuple[int, int]:
            nx = mg_x + MINI_PAD + (rx / world.arena_w) * (mg_w - 2 * MINI_PAD)
            ny = mg_y + MINI_PAD + (ry / world.arena_h) * (mg_h - 2 * MINI_PAD)
            return int(nx), int(ny)

        def effective_ch(did: int) -> Optional[str]:
            return overrides.get(did, world.robots[did].channel)

        for i, j in world.edges:
            if i not in shown_ids or j not in shown_ids:
                continue
            pi = to_mini(world.robots[i].x, world.robots[i].y)
            pj = to_mini(world.robots[j].x, world.robots[j].y)
            ch_i = effective_ch(i)
            ch_j = effective_ch(j)
            is_clash = (ch_i is not None and ch_i == ch_j)
            col = COL_CLASH_EDGE if is_clash else COL_NORMAL_EDGE
            lw  = 2 if is_clash else 1
            pygame.draw.line(ps, col, pi, pj, lw)

        for did in neighbor_ids:
            r   = world.robots[did]
            pos = to_mini(r.x, r.y)
            ch  = r.channel
            col = CHANNEL_DIM[ch] if ch else (45, 45, 60)
            pygame.draw.circle(ps, col,           pos, MINI_RAD_NBR)
            pygame.draw.circle(ps, (90, 90, 110), pos, MINI_RAD_NBR, 1)
            lbl = self.fonts["tiny"].render(str(did), True, (110, 110, 130))
            ps.blit(lbl, lbl.get_rect(center=pos))

        for did in suggestion_ids:
            r   = world.robots[did]
            pos = to_mini(r.x, r.y)
            ch  = overrides.get(did)
            col = CHANNEL_FILL[ch] if ch else COL_UNCOLOURED

            if did == selected_node:
                pygame.draw.circle(ps, COL_SELECTED_1, pos, MINI_RAD + 5, 2)

            pygame.draw.circle(ps, col,            pos, MINI_RAD)
            pygame.draw.circle(ps, (200, 200, 220), pos, MINI_RAD, 1)

            lbl = self.fonts["tiny"].render(str(did), True, (240, 240, 240))
            ps.blit(lbl, lbl.get_rect(center=pos))

            hit_r = MINI_RAD + 4
            self.suggestion_node_rects[did] = pygame.Rect(
                pos[0] - hit_r, pos[1] - hit_r, hit_r * 2, hit_r * 2,
            )

        y = mg_y + mg_h + 10

        # ── Channel buttons for selected node ─────────────────────────────────
        if selected_node is not None and selected_node in suggestion_ids:
            self._panel_sep(y)
            y += 8
            lbl = f["small"].render(f"D{selected_node}: pick channel", True, COL_HUD_TEXT)
            ps.blit(lbl, (px, y))
            y += 20

            btn_w   = (pw - 8) // 3
            cur_ch  = overrides.get(selected_node)
            for idx, ch in enumerate(CHANNELS):
                bx       = px + idx * (btn_w + 4)
                btn_rect = pygame.Rect(bx, y, btn_w, 28)
                is_cur   = (cur_ch == ch)
                fill     = CHANNEL_DIM[ch]   if is_cur else CHANNEL_FILL[ch]
                border   = (60, 60, 75)      if is_cur else (200, 200, 210)
                tcol     = (80, 80, 95)      if is_cur else (240, 240, 255)
                label    = CHANNEL_LABEL[ch] + (" ✓" if is_cur else "")
                pygame.draw.rect(ps, fill,   btn_rect, border_radius=5)
                pygame.draw.rect(ps, border, btn_rect, 2 if is_cur else 1, border_radius=5)
                s = f["popup"].render(label, True, tcol)
                ps.blit(s, s.get_rect(center=btn_rect.center))
                self.suggestion_channel_btn_rects[ch] = btn_rect
            y += 36
        else:
            self._panel_sep(y)
            y += 8
            for hint in ("Click a node to select it,", "then pick a channel below."):
                ps.blit(f["tiny"].render(hint, True, COL_DIM_TEXT), (px, y))
                y += 16
            y += 4

        # Infeasible warning
        if infeasible:
            self._panel_sep(y)
            y += 6
            ps.blit(
                f["tiny"].render("⚠ Cannot fully resolve — minimised", True, COL_WARN_TEXT),
                (px, y),
            )
            y += 18

        # ── Apply / Cancel pinned to bottom ───────────────────────────────────
        by = panel_h - 60
        if by < y + 16:
            by = y + 16
        self._panel_sep(by - 10)

        half        = (pw - 6) // 2
        apply_rect  = pygame.Rect(px,            by, half, 32)
        cancel_rect = pygame.Rect(px + half + 6, by, half, 32)

        pygame.draw.rect(ps, COL_BTN_APPLY,  apply_rect,  border_radius=6)
        pygame.draw.rect(ps, COL_BTN_BORDER, apply_rect,  1, border_radius=6)
        pygame.draw.rect(ps, COL_BTN_CANCEL, cancel_rect, border_radius=6)
        pygame.draw.rect(ps, COL_BTN_BORDER, cancel_rect, 1, border_radius=6)

        s = f["popup"].render("Apply", True, (220, 255, 220))
        ps.blit(s, s.get_rect(center=apply_rect.center))
        s = f["popup"].render("Cancel", True, (200, 200, 215))
        ps.blit(s, s.get_rect(center=cancel_rect.center))

        self.suggestion_apply_rect  = apply_rect
        self.suggestion_cancel_rect = cancel_rect

    # ── Tutorial callout ──────────────────────────────────────────────────────

    def _draw_tutorial_callout(
        self, callout: TutorialCallout, world: RobotWorld
    ) -> None:
        # Optional full-arena dim (behind everything else in the overlay stack)
        if callout.dim_arena:
            dim = pygame.Surface((self.arena_w, self.arena_h), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 110))
            self.screen.blit(dim, (0, 0))

        # Pulsing highlight rings on targeted drones
        pulse = (math.sin(callout.pulse_phase * 2 * math.pi) + 1) / 2  # 0→1
        r, g, b = callout.highlight_color
        for did in callout.highlight_ids:
            if did >= len(world.robots):
                continue
            robot = world.robots[did]
            cx, cy = int(robot.x), int(robot.y)
            for ring_r, base_alpha in ((28, 200), (42, 120), (58, 60)):
                alpha = int(base_alpha * (0.35 + 0.65 * pulse))
                rs = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(rs, (r, g, b, alpha), (ring_r + 2, ring_r + 2), ring_r, 2)
                self.screen.blit(rs, (cx - ring_r - 2, cy - ring_r - 2))

        # Instruction banner across top of arena
        STRIP_H = 118
        strip = pygame.Surface((self.arena_w, STRIP_H), pygame.SRCALPHA)
        strip.fill(COL_CALLOUT_BG)
        self.screen.blit(strip, (0, 0))
        pygame.draw.line(self.screen, COL_CALLOUT_BDR, (0, STRIP_H), (self.arena_w, STRIP_H), 2)

        f   = self.fonts
        pad = 14
        cx  = self.arena_w // 2

        # Heading
        head_surf = f["title"].render(callout.heading, True, (200, 230, 255))
        self.screen.blit(head_surf, head_surf.get_rect(centerx=cx, y=10))

        # Body (word-wrap at ~90 chars per line)
        body_lines = _wrap_text(callout.body, max_chars=90)
        y = 38
        for line in body_lines:
            s = f["small"].render(line, True, (210, 210, 230))
            self.screen.blit(s, s.get_rect(centerx=cx, y=y))
            y += 20

        # Hint at bottom-right of strip
        if callout.hint_override is not None:
            hint = callout.hint_override
            hint_col = (210, 200, 90)
        elif callout.advance_on_space:
            hint = "SPACE to continue"
            hint_col = (140, 220, 140)
        else:
            hint = "Complete the action above"
            hint_col = (220, 180, 80)
        hs = f["tiny"].render(hint, True, hint_col)
        self.screen.blit(hs, (self.arena_w - hs.get_width() - pad, STRIP_H - hs.get_height() - 6))

    # ── State overlays ────────────────────────────────────────────────────────

    def _draw_paused_overlay(self) -> None:
        overlay = pygame.Surface((self.arena_w, self.arena_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        cx, cy = self.arena_w // 2, self.arena_h // 2
        s = self.fonts["huge"].render("READY", True, COL_TITLE)
        self.screen.blit(s, s.get_rect(centerx=cx, y=cy - 100))
        s = self.fonts["large"].render("Press  SPACE  to set starting channels", True, COL_TIMER_OK)
        self.screen.blit(s, s.get_rect(centerx=cx, y=cy - 30))
        sw = self._switch_duration
        delay_text = "instant" if sw == 0 else f"{sw:.0f} s"
        hints = [
            "You will assign channels before the timer begins.",
            "",
            "During the game:",
            "Click a drone → pick channel  (M1 — manual, one at a time)",
            "Drag or Ctrl+click to select a group, then:",
            "  Suggest (M2): review & edit proposal in the side panel",
            "  Auto-assign (M3): apply immediately without review",
            f"Channel switch takes {delay_text} — act early!",
            "Amber ring = approaching link.  Red line = clash.",
            "Goal: minimise total clash time.",
        ]
        y = cy + 30
        for h in hints:
            s = self.fonts["small"].render(h, True, COL_DIM_TEXT)
            self.screen.blit(s, s.get_rect(centerx=cx, y=y))
            y += 22

    def _draw_setup_banner(self, all_assigned: bool = False) -> None:
        banner_h = 36
        banner = pygame.Surface((self.arena_w, banner_h), pygame.SRCALPHA)
        banner.fill((40, 60, 90, 200))
        self.screen.blit(banner, (0, 0))
        if all_assigned:
            msg = "SETUP  ·  All drones assigned  ·  SPACE to start timer"
            col = (180, 255, 180)
        else:
            msg = "SETUP  ·  Assign all drones before starting  ·  Use Suggest / Auto-assign for groups"
            col = (180, 220, 255)
        s = self.fonts["medium"].render(msg, True, col)
        self.screen.blit(s, s.get_rect(centerx=self.arena_w // 2, centery=banner_h // 2))

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
            ("R — play again          Q — quit",                       "small",  COL_DIM_TEXT),
        ]
        y  = box_y + 28
        cx = self.window_w // 2
        for text, fkey, col in rows:
            if fkey is None:
                y += 12; continue
            s = self.fonts[fkey].render(text, True, col)
            self.screen.blit(s, s.get_rect(centerx=cx, y=y))
            y += s.get_height() + 14
