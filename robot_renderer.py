from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import pygame

from robot_world import (
    CHANNELS,
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
    # List of (label, is_done) pairs; None means no checklist for this step
    checklist: Optional[List[Tuple[str, bool]]] = None

# M1 popup geometry
POPUP_W      = 108
POPUP_BTN_H  = 30
POPUP_PAD    = 6
POPUP_H      = POPUP_PAD + (POPUP_BTN_H + POPUP_PAD) * 3

# Mini-graph node radii
MINI_RAD     = 18   # suggestion nodes
MINI_RAD_NBR = 10   # neighbour nodes
MINI_PAD     = 40   # inset from mini-graph border


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
        "small":       sf("segoeui", 16),
        "medium":      sf("segoeui", 20),
        "large":       sf("segoeui", 30, bold=True),
        "title":       sf("segoeui", 23, bold=True),
        "huge":        sf("segoeui", 48, bold=True),
        "popup":       sf("segoeui", 18, bold=True),
        "tiny":        sf("segoeui", 14),
        "tut_heading": sf("segoeui", 35, bold=True),
        "tut_body":    sf("segoeui", 24),
        "tut_hint":    sf("segoeui", 21),
    }


class RobotRenderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.window_w, self.window_h = screen.get_size()
        self.arena_w = self.window_w - PANEL_W
        self.arena_h = self.window_h
        self.panel_x = self.arena_w

        self.fonts = _make_fonts()
        self._panel_w:   int = PANEL_W
        self._panel_pad: int = PANEL_PAD
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
        self._drone_modes: Dict[int, str] = {}
        self._agent_log: List[Tuple[float, str]] = []
        self._flex_mode: bool = False
        self._world: Optional[RobotWorld] = None
        self._panel_hover_pos: Optional[Tuple[int, int]] = None
        self._recording_enabled: bool = False
        self.recording_checkbox_rect: Optional[pygame.Rect] = None

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

    def handle_resize(self, new_screen: pygame.Surface) -> None:
        """Update renderer layout after the arena window is resized."""
        self.screen = new_screen
        self._ps    = new_screen
        self.window_w, self.window_h = new_screen.get_size()
        if self._panel_surface is not None:
            self.arena_w = self.window_w
        else:
            self.arena_w = max(1, self.window_w - PANEL_W)
        self.panel_x = self.arena_w
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
            self._panel_w   = PANEL_W
            self._panel_pad = PANEL_PAD
        else:
            # Panel window fills its entire surface
            surf_w = surf.get_width()
            self._panel_offset_x = 0
            self._panel_w   = surf_w
            self._panel_pad = 60
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
        drone_modes: Optional[Dict[int, str]] = None,
        agent_log: Optional[List[Tuple[float, str]]] = None,
        panel_hover_pos: Optional[Tuple[int, int]] = None,
        recording_enabled: bool = False,
    ) -> None:
        selected_ids       = selected_ids or set()
        suggestion_overrides = suggestion_overrides or {}

        # Per-frame world state
        self._switch_duration = world.switch_duration
        self._tutorial_disabled = frozenset(tutorial_callout.disabled_buttons) if tutorial_callout else frozenset()
        self._flex_mode       = drone_modes is not None
        self._drone_modes     = drone_modes if drone_modes is not None else {}
        self._agent_log       = agent_log   if agent_log   is not None else []
        self._world           = world
        self._panel_hover_pos   = panel_hover_pos
        self._recording_enabled = recording_enabled

        # Clear hit-test state
        self.popup_rects.clear()
        self.hud_button_rects.clear()
        self.suggestion_node_rects.clear()
        self.suggestion_channel_btn_rects.clear()
        self.suggestion_apply_rect    = None
        self.suggestion_cancel_rect   = None
        self.recording_checkbox_rect  = None

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

        # Arena always shows actual drone channels — the suggestion is displayed
        # only in the panel mini-graph and is never pre-applied visually here.
        self._draw_robots(world, popup_drone_id, selected_ids, None)

        if drag_rect is not None:
            self._draw_drag_box(drag_rect)

        # Panel — compact top + suggestion or hints + log at bottom
        n_assigned    = sum(1 for r in world.robots if r.channel is not None)
        panel_h       = self._ps.get_height()
        # In flex mode with no group selection, show mode buttons for the suggested
        # drones so the user can change autonomy level while a suggestion is showing.
        if self._flex_mode and not selected_ids and suggestion is not None:
            compact_sel = set(suggestion.keys())
        else:
            compact_sel = selected_ids
        content_start = self._draw_compact_top(world, compact_sel, state, n_assigned)
        log_top       = panel_h
        if state != "SETUP" and self._agent_log:
            log_top = self._draw_agent_log()
        if suggestion is not None:
            self._draw_suggestion_panel(
                world, suggestion, suggestion_overrides, pending_infeasible,
                start_y=content_start, end_y=log_top,
                selected_node=popup_drone_id,
            )
        else:
            self._draw_no_suggestion_content(start_y=content_start, end_y=log_top, state=state)

        # M1 arena popup — always in flex mode; only without suggestion otherwise
        if popup_drone_id is not None and state in ("PLAYING", "SETUP"):
            if suggestion is None or self._flex_mode:
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
            pygame.draw.circle(self._prox_surf, fill, pos, int(world.warn_radius))
            pygame.draw.circle(self._prox_surf, ring, pos, int(world.warn_radius), 1)

        self.screen.blit(self._prox_surf, (0, 0))

    def _draw_edges(self, world: RobotWorld) -> None:
        robots = world.robots
        for i, j in world.edges:
            clashing = (i, j) in world.clashing_pairs
            col = (255, 65, 65) if clashing else COL_NORMAL_EDGE
            w   = 4 if clashing else 2
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
            # Skip suggestion color override if the drone is already switching
            # (e.g. after a manual M1 change that triggered the flex monitor)
            in_suggestion = (suggestion_channels is not None
                             and r.id in suggestion_channels
                             and r.switching_to is None)
            display_ch    = suggestion_channels[r.id] if in_suggestion else r.channel

            if r.id == popup_drone_id:
                pygame.draw.circle(self.screen, COL_SELECTED_1, (cx, cy), rad + 6, 3)
            elif in_suggestion:
                pygame.draw.circle(self.screen, COL_SELECTED_GRP, (cx, cy), rad + 6, 3)
            elif r.id in selected_ids:
                pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), rad + 20, 10)

            if display_ch is None:
                body_col = COL_UNCOLOURED
            elif in_suggestion:
                body_col = CHANNEL_FILL[display_ch]
            else:
                body_col = CHANNEL_DIM[r.channel] if r.switching_to else CHANNEL_FILL[r.channel]
            pygame.draw.circle(self.screen, body_col, (cx, cy), rad)

            watch_mode = self._drone_modes.get(r.id)
            if watch_mode == "suggest":
                pygame.draw.circle(self.screen, (255, 160, 20), (cx, cy), rad + 14, 5)
            elif watch_mode == "auto":
                pygame.draw.circle(self.screen, (40, 220, 175), (cx, cy), rad + 14, 5)

            if r.id in clashing:
                # Pulsing outer ring to draw attention to clashing drones
                _t = pygame.time.get_ticks() / 1000.0
                _pulse = (math.sin(_t * math.pi * 3.0) + 1) / 2  # 0→1→0 at 1.5 Hz
                _prad = int(rad + 22 + _pulse * 6)
                _rg = int(60 + _pulse * 160)
                pygame.draw.circle(self.screen, (255, _rg, 30), (cx, cy), _prad, 2)
                pygame.draw.circle(self.screen, (255, 70, 70), (cx, cy), rad, 3)

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
        pw = self._px + self._panel_w
        pygame.draw.line(self._ps, COL_PANEL_BORDER,
                         (self._px + 4, y), (pw - 4, y), 1)

    def _draw_hud(
        self,
        world: RobotWorld,
        selected_ids: Set[int],
        state: str = "PLAYING",
        n_assigned: int = 0,
        compact_suggestion: bool = False,
    ) -> None:
        px = self._px + self._panel_pad
        f  = self.fonts

        if state == "SETUP":
            self._ps.blit(f["title"].render("SETUP", True, COL_TITLE), (px, 12))
            self._panel_sep(46)

            n_total  = len(world.robots)
            all_done = n_assigned == n_total
            count_col = COL_CLASH_OK if all_done else COL_WARN_TEXT
            self._ps.blit(f["large"].render(f"{n_assigned} / {n_total}", True, count_col), (px, 54))
            self._ps.blit(f["small"].render("drones assigned", True, COL_DIM_TEXT), (px, 94))
            self._panel_sep(118)

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

            y = 128
            for text, col in hints:
                s = f["tiny"].render(text, True, col)
                self._ps.blit(s, (px, y))
                y += 20

            if selected_ids:
                self._panel_sep(y + 4)
                self._draw_group_buttons(selected_ids, start_y=y + 12)
            return

        self._ps.blit(f["title"].render("AGENT PANEL", True, COL_TITLE), (px, 12))
        self._panel_sep(46)

        remaining = max(0.0, world.duration - world.elapsed)
        mins, secs = int(remaining) // 60, int(remaining) % 60
        timer_col = COL_TIMER_LOW if remaining < 20 else COL_TIMER_OK
        self._ps.blit(f["large"].render(f"{mins}:{secs:02d}", True, timer_col), (px, 54))
        self._ps.blit(f["small"].render("remaining", True, COL_DIM_TEXT), (px, 92))

        clash_col = COL_CLASH_BAD if world.clash_seconds > 0 else COL_CLASH_OK
        self._ps.blit(f["large"].render(f"{world.clash_seconds:.1f}s", True, clash_col), (px, 120))
        self._ps.blit(
            f["small"].render("clash time  (lower is better)", True, COL_DIM_TEXT),
            (px, 158),
        )

        self._panel_sep(178)

        if selected_ids:
            self._draw_group_buttons(selected_ids, start_y=188,
                                     show_instructions=not compact_suggestion)
        elif not compact_suggestion:
            self._draw_instructions(start_y=188)

    def _draw_group_buttons(self, selected_ids: Set[int], start_y: int, show_instructions: bool = True) -> None:
        px  = self._px + self._panel_pad
        pw  = self._panel_w - self._panel_pad * 2
        f   = self.fonts
        k   = len(selected_ids)

        self._ps.blit(
            f["small"].render(f"{k} drone{'s' if k != 1 else ''} selected", True, COL_SELECTED_GRP),
            (px, start_y),
        )

        btn_h = 36
        gap   = 12

        if self._flex_mode:
            all_suggest = bool(selected_ids) and all(
                self._drone_modes.get(d) == "suggest" for d in selected_ids)
            all_auto = bool(selected_ids) and all(
                self._drone_modes.get(d) == "auto" for d in selected_ids)

            ws_rect = pygame.Rect(px, start_y + 26, pw, btn_h)
            if "watch_suggest" in self._tutorial_disabled:
                pygame.draw.rect(self._ps, (55, 45, 10), ws_rect, border_radius=6)
                pygame.draw.rect(self._ps, (100, 90, 40), ws_rect, 2, border_radius=6)
                s = self.fonts["popup"].render("Suggest", True, (110, 100, 60))
            else:
                ws_fill = (90, 65, 10) if all_suggest else (60, 48, 8)
                ws_bdr  = (200, 160, 40) if all_suggest else (255, 200, 50)
                ws_col  = (220, 200, 100) if all_suggest else (255, 225, 120)
                pygame.draw.rect(self._ps, ws_fill, ws_rect, border_radius=6)
                pygame.draw.rect(self._ps, ws_bdr,  ws_rect, 2, border_radius=6)
                s = self.fonts["popup"].render("Suggest", True, ws_col)
                self.hud_button_rects["watch_suggest"] = ws_rect
            self._ps.blit(s, s.get_rect(center=ws_rect.center))

            wa_rect = pygame.Rect(px, start_y + 26 + btn_h + gap, pw, btn_h)
            if "watch_auto" in self._tutorial_disabled:
                pygame.draw.rect(self._ps, (8, 40, 35), wa_rect, border_radius=6)
                pygame.draw.rect(self._ps, (30, 90, 75), wa_rect, 2, border_radius=6)
                s = self.fonts["popup"].render("Auto", True, (50, 110, 95))
            else:
                wa_fill = (10, 65, 55) if all_auto else (8, 50, 45)
                wa_bdr  = (40, 180, 140) if all_auto else (50, 220, 175)
                wa_col  = (100, 220, 190) if all_auto else (120, 255, 210)
                pygame.draw.rect(self._ps, wa_fill, wa_rect, border_radius=6)
                pygame.draw.rect(self._ps, wa_bdr,  wa_rect, 2, border_radius=6)
                s = self.fonts["popup"].render("Auto", True, wa_col)
                self.hud_button_rects["watch_auto"] = wa_rect
            self._ps.blit(s, s.get_rect(center=wa_rect.center))

            um_rect = pygame.Rect(px, start_y + 26 + (btn_h + gap) * 2, pw, btn_h)
            any_watched = any(self._drone_modes.get(d) for d in selected_ids)
            if "unwatch" in self._tutorial_disabled:
                pygame.draw.rect(self._ps, (35, 30, 42), um_rect, border_radius=6)
                pygame.draw.rect(self._ps, (70, 65, 85), um_rect, 2, border_radius=6)
                s = self.fonts["popup"].render("Manual", True, (85, 80, 105))
            else:
                um_fill = (55, 30, 10) if any_watched else (32, 30, 38)
                um_bdr  = (210, 130, 50) if any_watched else (110, 100, 125)
                um_col  = (240, 180, 110) if any_watched else (160, 150, 180)
                pygame.draw.rect(self._ps, um_fill, um_rect, border_radius=6)
                pygame.draw.rect(self._ps, um_bdr,  um_rect, 2, border_radius=6)
                s = self.fonts["popup"].render("Manual", True, um_col)
                self.hud_button_rects["unwatch"] = um_rect
            self._ps.blit(s, s.get_rect(center=um_rect.center))

        else:
            sug_rect = pygame.Rect(px, start_y + 26, pw, btn_h)
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

            auto_rect = pygame.Rect(px, start_y + 26 + btn_h + gap, pw, btn_h)
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

        if self._flex_mode:
            sep_y = start_y + 26 + (btn_h + gap) * 3 + 4
        else:
            sep_y = start_y + 26 + btn_h * 2 + gap + 16
        if show_instructions:
            self._panel_sep(sep_y)
            self._draw_instructions(start_y=sep_y + 10)

    def _draw_instructions(self, start_y: int) -> None:
        px = self._px + self._panel_pad
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
            y += 20

    # ── Agent log panel ───────────────────────────────────────────────────────

    _LOG_MAX_ENTRIES = 3   # show up to 3 recent auto-fix entries
    _LOG_ARROW_W     = 44  # width of the before→after arrow column
    _LOG_CELL_GAP    = 6   # vertical gap between rows
    _LOG_HDR_H       = 22  # "Agent log" header height

    def _draw_agent_log(self) -> int:
        ps      = self._ps
        px      = self._px + self._panel_pad
        pw      = self._panel_w - self._panel_pad * 2
        f       = self.fonts
        panel_h = ps.get_height()

        # Only entries with a valid before-snapshot (5-tuple from auto-fix)
        entries = [e for e in self._agent_log if len(e) >= 3 and e[2] is not None]
        entries = entries[-self._LOG_MAX_ENTRIES:]
        if not entries:
            return panel_h

        arrow_w = self._LOG_ARROW_W
        n_rows  = len(entries)
        # Cap total block to 35% of panel height so it doesn't crowd the HUD
        max_block_h = max(80, int(panel_h * 0.35))
        row_budget  = (max_block_h - self._LOG_HDR_H - 4) // n_rows
        cell_h      = max(40, row_budget - self._LOG_CELL_GAP)
        cell_w      = min(cell_h, (pw - arrow_w) // 2)
        cell_h      = cell_w
        row_h       = cell_h + self._LOG_CELL_GAP
        block_h     = self._LOG_HDR_H + 4 + n_rows * row_h
        block_top   = panel_h - block_h - 10

        self._panel_sep(block_top - 6)
        ps.blit(f["small"].render("Agent log", True, COL_DIM_TEXT), (px, block_top))

        y = block_top + self._LOG_HDR_H + 4
        for entry in entries:
            snap_before = entry[2] if len(entry) > 2 else None
            drone_ids   = list(entry[3]) if len(entry) > 3 else []
            clash_delta = int(entry[4]) if len(entry) > 4 and entry[4] is not None else None

            # Before cell
            if snap_before:
                self._draw_log_snapshot(ps, px, y, cell_w, cell_h, snap_before)
            else:
                pygame.draw.rect(ps, COL_MINIGRAPH_BG, (px, y, cell_w, cell_h), border_radius=4)

            # Arrow + annotation
            ax0   = px + cell_w + 4
            ax1   = px + cell_w + arrow_w - 4
            mid_y = y + cell_h // 2
            tip_x = ax1
            pygame.draw.line(ps, COL_DIM_TEXT, (ax0, mid_y), (tip_x - 6, mid_y), 2)
            pygame.draw.line(ps, COL_DIM_TEXT, (tip_x, mid_y), (tip_x - 6, mid_y - 4), 2)
            pygame.draw.line(ps, COL_DIM_TEXT, (tip_x, mid_y), (tip_x - 6, mid_y + 4), 2)
            if clash_delta is not None and clash_delta < 0:
                lbl = f"{clash_delta}cls"
                ls  = f["tiny"].render(lbl, True, COL_CLASH_OK)
                ps.blit(ls, ls.get_rect(centerx=(ax0 + ax1) // 2, bottom=mid_y - 2))

            # After cell (live)
            after_x = px + cell_w + arrow_w
            if drone_ids and self._world is not None:
                self._draw_live_drone_cell(ps, after_x, y, cell_w, cell_h, drone_ids)
            else:
                pygame.draw.rect(ps, COL_MINIGRAPH_BG, (after_x, y, cell_w, cell_h), border_radius=4)
                pygame.draw.rect(ps, (60, 60, 85), (after_x, y, cell_w, cell_h), 1, border_radius=4)

            y += row_h

        return block_top

    # ── Compact top section (title/timer/clash + mode buttons) ────────────────

    def _draw_compact_top(
        self,
        world: RobotWorld,
        selected_ids: Set[int],
        state: str,
        n_assigned: int,
    ) -> int:
        """Draw compact header with status + mode buttons. Returns y where middle zone begins."""
        ps = self._ps
        px = self._px + self._panel_pad
        pw = self._panel_w - self._panel_pad * 2
        f  = self.fonts
        y  = 10

        if state == "SETUP":
            ps.blit(f["title"].render("SETUP", True, COL_TITLE), (px, y))
            n_total   = len(world.robots)
            all_done  = n_assigned == n_total
            count_col = COL_CLASH_OK if all_done else COL_WARN_TEXT
            count_s   = f["medium"].render(f"{n_assigned}/{n_total} coloured", True, count_col)
            ps.blit(count_s, (px + pw - count_s.get_width(), y + 2))
            y += 32
            hint = "All set! SPACE to start." if all_done else f"{n_total - n_assigned} unassigned"
            ps.blit(f["tiny"].render(hint, True, COL_TIMER_OK if all_done else COL_WARN_TEXT), (px, y))
            y += 20
        else:
            remaining = max(0.0, world.duration - world.elapsed)
            mins, secs_r = int(remaining) // 60, int(remaining) % 60
            timer_col = COL_TIMER_LOW if remaining < 20 else COL_TIMER_OK
            timer_s   = f["medium"].render(f"{mins}:{secs_r:02d}", True, timer_col)
            ps.blit(timer_s, (px, y))
            clash_s = f["medium"].render(
                f"Clash: {world.clash_seconds:.1f}s", True,
                COL_CLASH_BAD if world.clash_seconds > 0 else COL_CLASH_OK,
            )
            ps.blit(clash_s, (px + pw - clash_s.get_width(), y))
            y += 30

        if selected_ids:
            y += 4
            y = self._draw_side_buttons(selected_ids, y)
            y += 4

        self._panel_sep(y + 4)
        return y + 10

    def _draw_side_buttons(self, selected_ids: Set[int], start_y: int) -> int:
        """Draw mode-assignment buttons in a horizontal row. Returns bottom y of row."""
        ps  = self._ps
        px  = self._px + self._panel_pad
        pw  = self._panel_w - self._panel_pad * 2
        f   = self.fonts
        BTN_H = 38

        hover = self._panel_hover_pos

        if self._flex_mode:
            GAP        = 6
            btn_w      = (pw - GAP * 2) // 3
            all_sug    = all(self._drone_modes.get(d) == "suggest" for d in selected_ids)
            all_auto   = all(self._drone_modes.get(d) == "auto"    for d in selected_ids)
            any_watched = any(self._drone_modes.get(d) for d in selected_ids)
            spec = [
                ("unwatch",       "Manual",  not any_watched,
                 (55, 30, 10), (210, 130, 50), (240, 180, 110),
                 (35, 30, 42), (70, 65, 85),   (85, 80, 105)),
                ("watch_suggest", "Suggest", all_sug,
                 (90, 65, 10), (200, 160, 40), (220, 200, 100),
                 (55, 45, 10), (100, 90, 40),  (110, 100, 60)),
                ("watch_auto",    "Auto",    all_auto,
                 (10, 65, 55), (40, 180, 140), (100, 220, 190),
                 (8, 40, 35),  (30, 90, 75),   (50, 110, 95)),
            ]
            for i, (key, label, active, af, ab, ac, df, db, dc) in enumerate(spec):
                bx   = px + i * (btn_w + GAP)
                rect = pygame.Rect(bx, start_y, btn_w, BTN_H)
                if key in self._tutorial_disabled:
                    pygame.draw.rect(ps, df, rect, border_radius=5)
                    pygame.draw.rect(ps, db, rect, 2, border_radius=5)
                    s = f["small"].render(label, True, dc)
                else:
                    is_hov = hover is not None and rect.collidepoint(hover)
                    fill   = tuple(min(255, v + 55) for v in af) if is_hov else af
                    border = tuple(min(255, v + 55) for v in ab) if is_hov else ab
                    pygame.draw.rect(ps, fill,   rect, border_radius=5)
                    pygame.draw.rect(ps, border, rect, 2, border_radius=5)
                    if is_hov:
                        pygame.draw.rect(ps, (255, 255, 255), rect, 1, border_radius=5)
                    s = f["small"].render(label, True, ac)
                    self.hud_button_rects[key] = rect
                ps.blit(s, s.get_rect(center=rect.center))
        else:
            GAP   = 8
            k     = len(selected_ids)
            btn_w = (pw - GAP) // 2
            spec2 = [
                ("suggest",     f"Suggest ({k})",  COL_BTN_SUGGEST, (42, 52, 48), (68, 78, 72), (80, 100, 90),  (220, 255, 220)),
                ("auto_assign", f"Auto ({k})",      COL_BTN_AUTO,    (38, 44, 58), (62, 68, 86), (70, 80, 110), (200, 220, 255)),
            ]
            for i, (key, label, active_col, df, db, dc, tc) in enumerate(spec2):
                bx   = px + i * (btn_w + GAP)
                rect = pygame.Rect(bx, start_y, btn_w, BTN_H)
                if key in self._tutorial_disabled:
                    pygame.draw.rect(ps, df, rect, border_radius=5)
                    pygame.draw.rect(ps, db, rect, 1, border_radius=5)
                    s = f["small"].render(label, True, dc)
                else:
                    is_hov = hover is not None and rect.collidepoint(hover)
                    fill   = tuple(min(255, v + 55) for v in active_col) if is_hov else active_col
                    border = tuple(min(255, v + 55) for v in COL_BTN_BORDER) if is_hov else COL_BTN_BORDER
                    pygame.draw.rect(ps, fill,   rect, border_radius=5)
                    pygame.draw.rect(ps, border, rect, 1, border_radius=5)
                    if is_hov:
                        pygame.draw.rect(ps, (255, 255, 255), rect, 1, border_radius=5)
                    s = f["small"].render(label, True, tc)
                    self.hud_button_rects[key] = rect
                ps.blit(s, s.get_rect(center=rect.center))

        return start_y + BTN_H

    def _draw_no_suggestion_content(self, start_y: int, end_y: int, state: str = "PLAYING") -> None:
        """Draw instructions in the middle zone when no suggestion is active."""
        ps  = self._ps
        px  = self._px + self._panel_pad
        pw  = self._panel_w - self._panel_pad * 2
        f   = self.fonts
        sw  = self._switch_duration
        delay_text = "instant" if sw == 0 else f"{sw:.0f} s"

        # Select All button
        BTN_H = 32
        sel_rect = pygame.Rect(px, start_y + 6, pw, BTN_H)
        hover  = self._panel_hover_pos
        is_hov = hover is not None and sel_rect.collidepoint(hover)
        pygame.draw.rect(ps, (60, 60, 82) if is_hov else (40, 40, 58), sel_rect, border_radius=5)
        pygame.draw.rect(ps, (150, 150, 195) if is_hov else (90, 90, 125), sel_rect, 1, border_radius=5)
        s = f["small"].render("Select All  (Ctrl+A)", True, (185, 185, 220))
        ps.blit(s, s.get_rect(center=sel_rect.center))
        self.hud_button_rects["select_all"] = sel_rect
        start_y = start_y + 6 + BTN_H + 6

        if state == "SETUP":
            hints = [
                "Assign channels before starting:",
                "",
                "Click a drone → pick channel (M1)",
                "Drag or Ctrl+click → group select",
                "Suggest → review in panel (M2)",
                "Auto-assign → apply at once (M3)",
                "",
                "ESC — quit",
            ]
        elif self._flex_mode:
            hints = [
                "Select a drone, then:",
                "  Sug — agent proposes a change",
                "  Auto — agent applies instantly",
                "  Manual — you control directly",
                "",
                "Click a drone (M1) → set channel",
                "Amber ring = approaching link",
                "Red line = channel clash",
                f"Switch delay: {delay_text}",
                "",
                "ESC — quit",
            ]
        else:
            hints = [
                "Select drones, then:",
                "  Suggest (M2) — review proposal",
                "  Auto-assign (M3) — apply now",
                "",
                "Click drone (M1) — assign directly",
                "Drag / Ctrl+click — group select",
                "",
                "Amber ring = approaching link",
                "Red line = channel clash",
                f"Switch delay: {delay_text}",
                "",
                "ESC — quit",
            ]

        zone_h  = max(1, end_y - start_y)
        line_h  = 20
        total_h = len(hints) * line_h
        y = start_y + max(10, (zone_h - total_h) // 2)
        for h in hints:
            s = f["tiny"].render(h, True, COL_DIM_TEXT)
            ps.blit(s, (px, y))
            y += line_h

    def _draw_live_drone_cell(
        self, ps, sx: int, sy: int, sw: int, sh: int, drone_ids: List[int],
    ) -> None:
        pygame.draw.rect(ps, COL_MINIGRAPH_BG, (sx, sy, sw, sh), border_radius=4)
        pygame.draw.rect(ps, (50, 80, 55), (sx, sy, sw, sh), 1, border_radius=4)
        world = self._world
        if world is None:
            return
        robots = [world.robots[did] for did in drone_ids if did < len(world.robots)]
        if not robots:
            return
        xs    = [r.x for r in robots]
        ys    = [r.y for r in robots]
        cx_   = sum(xs) / len(xs)
        cy_   = sum(ys) / len(ys)
        half_w = max((max(xs) - min(xs)) / 2 + world.arena_w * 0.04, world.arena_w * 0.12)
        half_h = max((max(ys) - min(ys)) / 2 + world.arena_h * 0.04, world.arena_h * 0.12)
        x_lo  = cx_ - half_w
        y_lo  = cy_ - half_h
        pad   = 8
        r_dot = max(5, sw // 18)
        id_set    = {r.id for r in robots}
        clash_set = {(min(a, b), max(a, b)) for a, b in world.clashing_pairs}

        def to_cell(wx, wy):
            nx  = (wx - x_lo) / (2 * half_w)
            ny  = (wy - y_lo) / (2 * half_h)
            px_ = int(sx + pad + nx * (sw - 2 * pad))
            py_ = int(sy + pad + ny * (sh - 2 * pad))
            return (
                max(sx + r_dot + 2, min(sx + sw - r_dot - 2, px_)),
                max(sy + r_dot + 2, min(sy + sh - r_dot - 2, py_)),
            )

        for i, j in world.edges:
            if i not in id_set or j not in id_set:
                continue
            pi = to_cell(world.robots[i].x, world.robots[i].y)
            pj = to_cell(world.robots[j].x, world.robots[j].y)
            is_clash = (min(i, j), max(i, j)) in clash_set
            pygame.draw.line(ps, COL_CLASH_EDGE if is_clash else COL_NORMAL_EDGE, pi, pj, 1)

        for r in robots:
            pos = to_cell(r.x, r.y)
            ch  = r.channel
            col = (CHANNEL_DIM.get(ch, COL_UNCOLOURED) if r.switching_to
                   else CHANNEL_FILL.get(ch, COL_UNCOLOURED))
            pygame.draw.circle(ps, col, pos, r_dot)
            pygame.draw.circle(ps, (200, 200, 220), pos, r_dot, 1)

    def _draw_log_snapshot(self, ps, sx: int, sy: int, sw: int, sh: int, snap) -> None:
        """Render a compact mini-graph cell for one agent-log entry.

        snap format: (nodes, edges) tuple where
          nodes = [(id, norm_x, norm_y, ch_before, ch_after), ...]
          edges = [(i, j), ...]  robot-ID pairs that were connected at capture time
        Older list-format snaps (no edges, 4-tuple nodes) are also handled for compat.
        """
        pygame.draw.rect(ps, COL_MINIGRAPH_BG, (sx, sy, sw, sh), border_radius=4)
        pygame.draw.rect(ps, (60, 60, 85),     (sx, sy, sw, sh), 1, border_radius=4)

        # Parse snap format
        if isinstance(snap, tuple) and len(snap) == 2 and isinstance(snap[0], list):
            nodes, edges = snap
        else:
            nodes = snap   # legacy list format
            edges = []

        if not nodes:
            return

        pad   = 8
        r_dot = 8
        f     = self.fonts

        # Build position + channel map keyed by robot ID
        pos_map: dict = {}
        for item in nodes:
            if len(item) == 5:
                did, nx, ny, ch_before, ch_after = item
            else:
                did, nx, ny, ch_after = item
                ch_before = ch_after
            x = int(sx + pad + nx * (sw - 2 * pad))
            y = int(sy + pad + ny * (sh - 2 * pad))
            x = max(sx + r_dot + 2, min(sx + sw - r_dot - 2, x))
            y = max(sy + r_dot + 2, min(sy + sh - r_dot - 2, y))
            pos_map[did] = (x, y, ch_before, ch_after)

        # Draw edges first (behind nodes)
        for i, j in edges:
            if i not in pos_map or j not in pos_map:
                continue
            pi = pos_map[i][:2]
            pj = pos_map[j][:2]
            ch_i = pos_map[i][3]   # after-channel for i
            ch_j = pos_map[j][3]   # after-channel for j
            is_clash = ch_i is not None and ch_i == ch_j
            col = COL_CLASH_EDGE if is_clash else COL_NORMAL_EDGE
            pygame.draw.line(ps, col, pi, pj, 1)

        # Draw nodes
        for did, (x, y, ch_before, ch_after) in pos_map.items():
            col_after = CHANNEL_FILL.get(ch_after, COL_UNCOLOURED)
            pygame.draw.circle(ps, col_after, (x, y), r_dot)
            pygame.draw.circle(ps, (200, 200, 220), (x, y), r_dot, 1)

            # If the channel changed, draw a before-colour ring to show the transition
            if ch_before is not None and ch_before != ch_after:
                col_before = CHANNEL_FILL.get(ch_before, COL_UNCOLOURED)
                pygame.draw.circle(ps, col_before, (x, y), r_dot + 4, 2)

    # ── Compact suggestion panel (flex mode) ─────────────────────────────────

    def _draw_compact_suggestion_panel(
        self,
        world: RobotWorld,
        suggestion: Dict[int, str],
        overrides: Dict[int, str],
        infeasible: bool,
    ) -> None:
        ps      = self._ps
        px      = self._px + self._panel_pad
        pw      = self._panel_w - self._panel_pad * 2
        f       = self.fonts
        panel_h = ps.get_height()

        # Geometry: compact section pinned to bottom with fixed height
        MG_H      = 90   # mini-graph height
        BTN_H     = 36
        COMP_H    = 10 + 22 + 6 + MG_H + 6 + BTN_H + 10  # ~90px header+graph+btn
        bottom_y  = panel_h - COMP_H - 6

        self._panel_sep(bottom_y)
        y = bottom_y + 8

        # Header row
        hdr = f["small"].render("SUGGESTION", True, (220, 200, 80))
        ps.blit(hdr, (px, y))
        if infeasible:
            ws = f["tiny"].render("⚠ partial", True, COL_WARN_TEXT)
            ps.blit(ws, ws.get_rect(right=px + pw, centery=y + 8))
        y += 22 + 4

        # Mini live graph
        mg_x = self._px + self._panel_pad
        mg_w = pw
        pygame.draw.rect(ps, COL_MINIGRAPH_BG, (mg_x - 1, y - 1, mg_w + 2, MG_H + 2), border_radius=4)
        pygame.draw.rect(ps, COL_PANEL_BORDER, (mg_x - 1, y - 1, mg_w + 2, MG_H + 2), 1, border_radius=4)

        sug_ids  = set(suggestion.keys())
        nbr_ids: set[int] = set()
        for i, j in world.edges:
            if i in sug_ids and j not in sug_ids:
                nbr_ids.add(j)
            elif j in sug_ids and i not in sug_ids:
                nbr_ids.add(i)
        shown_ids = sug_ids | nbr_ids

        cpad = 14  # smaller padding than full suggestion panel

        def _to_mini(rx: float, ry: float) -> Tuple[int, int]:
            nx = mg_x + cpad + (rx / world.arena_w) * (mg_w - 2 * cpad)
            ny = y    + cpad + (ry / world.arena_h) * (MG_H - 2 * cpad)
            return int(nx), int(ny)

        def _eff_ch(did: int) -> Optional[str]:
            return overrides.get(did, world.robots[did].channel)

        for i, j in world.edges:
            if i not in shown_ids or j not in shown_ids:
                continue
            pi = _to_mini(world.robots[i].x, world.robots[i].y)
            pj = _to_mini(world.robots[j].x, world.robots[j].y)
            ch_i = _eff_ch(i); ch_j = _eff_ch(j)
            is_clash = ch_i is not None and ch_i == ch_j
            pygame.draw.line(ps, COL_CLASH_EDGE if is_clash else COL_NORMAL_EDGE, pi, pj,
                             2 if is_clash else 1)

        for did in nbr_ids:
            r   = world.robots[did]
            pos = _to_mini(r.x, r.y)
            ch  = r.channel
            col = CHANNEL_DIM[ch] if ch else (45, 45, 60)
            pygame.draw.circle(ps, col, pos, 7)
            pygame.draw.circle(ps, (90, 90, 110), pos, 7, 1)

        for did in sug_ids:
            r   = world.robots[did]
            pos = _to_mini(r.x, r.y)
            ch  = overrides.get(did)
            col = CHANNEL_FILL[ch] if ch else COL_UNCOLOURED
            pygame.draw.circle(ps, col, pos, 11)
            pygame.draw.circle(ps, (200, 200, 220), pos, 11, 1)
            lbl = f["tiny"].render(str(did), True, (240, 240, 240))
            ps.blit(lbl, lbl.get_rect(center=pos))

        y += MG_H + 6

        # Apply / Cancel buttons
        half        = (pw - 10) // 2
        apply_rect  = pygame.Rect(px,             y, half, BTN_H)
        cancel_rect = pygame.Rect(px + half + 10, y, half, BTN_H)
        pygame.draw.rect(ps, COL_BTN_APPLY,  apply_rect,  border_radius=8)
        pygame.draw.rect(ps, COL_BTN_BORDER, apply_rect,  1, border_radius=8)
        pygame.draw.rect(ps, COL_BTN_CANCEL, cancel_rect, border_radius=8)
        pygame.draw.rect(ps, COL_BTN_BORDER, cancel_rect, 1, border_radius=8)
        ps.blit(f["popup"].render("Apply",  True, (220, 255, 220)),
                f["popup"].render("Apply",  True, (220, 255, 220)).get_rect(center=apply_rect.center))
        ps.blit(f["popup"].render("Cancel", True, (200, 200, 215)),
                f["popup"].render("Cancel", True, (200, 200, 215)).get_rect(center=cancel_rect.center))
        self.suggestion_apply_rect  = apply_rect
        self.suggestion_cancel_rect = cancel_rect

    # ── Suggestion panel with live mini-graph ─────────────────────────────────

    def _draw_suggestion_panel(
        self,
        world: RobotWorld,
        suggestion: Dict[int, str],
        overrides: Dict[int, str],
        infeasible: bool,
        start_y: int = 0,
        end_y: Optional[int] = None,
        selected_node: Optional[int] = None,
    ) -> None:
        px = self._px + self._panel_pad
        pw = self._panel_w - self._panel_pad * 2
        f  = self.fonts
        ps = self._ps
        panel_h = ps.get_height()
        if end_y is None:
            end_y = panel_h

        # Label
        ps.blit(f["small"].render("SUGGESTION", True, (220, 200, 80)), (px, start_y + 4))
        if infeasible:
            ws = f["tiny"].render("⚠ partial", True, COL_WARN_TEXT)
            ps.blit(ws, ws.get_rect(right=px + pw, centery=start_y + 12))

        # ── Mini live graph ───────────────────────────────────────────────────
        mg_y = start_y + 26
        mg_w = pw
        suggestion_ids_set = set(suggestion.keys())
        has_node_selected  = (selected_node is not None and selected_node in suggestion_ids_set)
        # Accurate accounting of pixels consumed below the mini-graph:
        #   14px gap, then node picker (84px) or hint (60px), optional infeasible (32px),
        #   then 70px for separator+apply/cancel (sep@14 + btn@44 + margin@12).
        node_section   = 84 if has_node_selected else 60
        infer_section  = 32 if infeasible else 0
        bottom_section = 14 + node_section + infer_section + 70
        mg_h_max = max(80, end_y - mg_y - bottom_section)
        mg_aspect = world.arena_h / world.arena_w if world.arena_w > 0 else 1.0
        mg_h_ideal = int(mg_w * mg_aspect)
        mg_h = max(80, min(mg_h_ideal, mg_h_max))
        mg_x = self._px + self._panel_pad

        pygame.draw.rect(ps, COL_MINIGRAPH_BG,
                         (mg_x - 1, mg_y - 1, mg_w + 2, mg_h + 2), border_radius=4)
        pygame.draw.rect(ps, COL_PANEL_BORDER,
                         (mg_x - 1, mg_y - 1, mg_w + 2, mg_h + 2), 1, border_radius=4)

        # Node sets
        suggestion_ids = suggestion_ids_set
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

        y = mg_y + mg_h + 14

        # ── Channel buttons for selected node ─────────────────────────────────
        if selected_node is not None and selected_node in suggestion_ids:
            self._panel_sep(y)
            y += 10
            lbl = f["small"].render(f"D{selected_node}: pick channel", True, COL_HUD_TEXT)
            ps.blit(lbl, (px, y))
            y += 24

            btn_w   = (pw - 16) // 3
            cur_ch  = overrides.get(selected_node)
            for idx, ch in enumerate(CHANNELS):
                bx       = px + idx * (btn_w + 8)
                btn_rect = pygame.Rect(bx, y, btn_w, 40)
                is_cur   = (cur_ch == ch)
                fill     = CHANNEL_DIM[ch]   if is_cur else CHANNEL_FILL[ch]
                border   = (60, 60, 75)      if is_cur else (200, 200, 210)
                tcol     = (80, 80, 95)      if is_cur else (240, 240, 255)
                label    = CHANNEL_LABEL[ch] + (" ✓" if is_cur else "")
                pygame.draw.rect(ps, fill,   btn_rect, border_radius=6)
                pygame.draw.rect(ps, border, btn_rect, 2 if is_cur else 1, border_radius=6)
                s = f["popup"].render(label, True, tcol)
                ps.blit(s, s.get_rect(center=btn_rect.center))
                self.suggestion_channel_btn_rects[ch] = btn_rect
            y += 50
        else:
            self._panel_sep(y)
            y += 10
            for hint in ("Click a node to select it,", "then pick a channel below."):
                ps.blit(f["small"].render(hint, True, COL_DIM_TEXT), (px, y))
                y += 22
            y += 6

        # Infeasible warning
        if infeasible:
            self._panel_sep(y)
            y += 8
            ps.blit(
                f["small"].render("⚠ Cannot fully resolve — minimised", True, COL_WARN_TEXT),
                (px, y),
            )
            y += 24

        # ── Apply / Cancel pinned to bottom of zone ──────────────────────────
        by = end_y - 56
        if by < y + 14:
            by = y + 14          # push down only if content overlaps
        by = min(by, end_y - 52) # hard cap so buttons never exceed end_y
        self._panel_sep(by - 14)

        half        = (pw - 10) // 2
        apply_rect  = pygame.Rect(px,             by, half, 44)
        cancel_rect = pygame.Rect(px + half + 10, by, half, 44)

        pygame.draw.rect(ps, COL_BTN_APPLY,  apply_rect,  border_radius=8)
        pygame.draw.rect(ps, COL_BTN_BORDER, apply_rect,  1, border_radius=8)
        pygame.draw.rect(ps, COL_BTN_CANCEL, cancel_rect, border_radius=8)
        pygame.draw.rect(ps, COL_BTN_BORDER, cancel_rect, 1, border_radius=8)

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
        n_check  = len(callout.checklist) if callout.checklist else 0
        STRIP_H  = (max(200, 92 + n_check * 30 + 24)) if n_check else 200
        strip = pygame.Surface((self.arena_w, STRIP_H), pygame.SRCALPHA)
        strip.fill(COL_CALLOUT_BG)
        self.screen.blit(strip, (0, 0))
        pygame.draw.line(self.screen, COL_CALLOUT_BDR, (0, STRIP_H), (self.arena_w, STRIP_H), 2)

        f   = self.fonts
        pad = 20
        cx  = self.arena_w // 2

        # Heading
        head_surf = f["tut_heading"].render(callout.heading, True, (200, 230, 255))
        self.screen.blit(head_surf, head_surf.get_rect(centerx=cx, y=12))

        if callout.checklist:
            # Compact single-line body, then 2-column checklist
            body_s = f["medium"].render(callout.body, True, (180, 180, 210))
            self.screen.blit(body_s, body_s.get_rect(centerx=cx, y=60))

            items   = callout.checklist
            row_h   = 30
            box_sz  = 16
            y_start = 92

            for i, (desc, done) in enumerate(items):
                x_c = pad
                y_c = y_start + i * row_h

                box_rect = pygame.Rect(x_c, y_c + 1, box_sz, box_sz)
                if done:
                    pygame.draw.rect(self.screen, (35, 140, 55), box_rect, border_radius=3)
                    pygame.draw.rect(self.screen, (80, 210, 100), box_rect, 1, border_radius=3)
                    # Checkmark lines
                    bx, by = box_rect.x, box_rect.y
                    pygame.draw.line(self.screen, (160, 255, 160),
                                     (bx + 3, by + 8), (bx + 6, by + 12), 2)
                    pygame.draw.line(self.screen, (160, 255, 160),
                                     (bx + 6, by + 12), (bx + 13, by + 4), 2)
                    text_col = (160, 245, 160)
                else:
                    pygame.draw.rect(self.screen, (30, 30, 50), box_rect, border_radius=3)
                    pygame.draw.rect(self.screen, (80, 80, 115), box_rect, 1, border_radius=3)
                    text_col = (160, 160, 195)

                ts = f["small"].render(desc, True, text_col)
                self.screen.blit(ts, (x_c + box_sz + 6, y_c + 1))

        else:
            # Standard body text (word-wrap at ~110 chars per line)
            body_lines = _wrap_text(callout.body, max_chars=110)
            y = 64
            for line in body_lines:
                s = f["tut_body"].render(line, True, (210, 210, 230))
                self.screen.blit(s, s.get_rect(centerx=cx, y=y))
                y += 30

        # Hint at bottom-right of strip
        if callout.hint_override is not None:
            hint = callout.hint_override
            if callout.checklist:
                all_done = all(done for _, done in callout.checklist)
                hint_col = (140, 220, 140) if all_done else (220, 190, 80)
            else:
                hint_col = (210, 200, 90)
        elif callout.advance_on_space:
            hint = "SPACE to continue"
            hint_col = (140, 220, 140)
        else:
            hint = "Complete the action above"
            hint_col = (220, 180, 80)
        hs = f["tut_hint"].render(hint, True, hint_col)
        self.screen.blit(hs, (self.arena_w - hs.get_width() - pad, STRIP_H - hs.get_height() - 8))

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
