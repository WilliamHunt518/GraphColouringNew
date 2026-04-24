"""
panel_window.py — detachable side-panel window using SDL2 multi-window support.

Falls back gracefully if pygame._sdl2 is unavailable (older pygame builds).
"""
from __future__ import annotations
from typing import List, Optional, Tuple

import pygame

try:
    from pygame._sdl2.video import Window as _SDLWindow
    _HAS_SDL2 = True
except ImportError:
    _HAS_SDL2 = False


def is_supported() -> bool:
    return _HAS_SDL2


def get_secondary_monitor_offset() -> Tuple[int, int]:
    """Return the top-left pixel position of the second monitor, or (0, 0)."""
    n = pygame.display.get_num_displays()
    if n < 2:
        return (0, 0)
    # pygame 2.4+ exposes per-display bounds
    try:
        bounds = pygame.display.get_display_bounds(1)
        return (bounds[0], bounds[1])
    except Exception:
        # Fallback: assume second monitor is to the right of the first
        try:
            w0, _ = pygame.display.get_desktop_sizes()[0]
            return (w0, 0)
        except Exception:
            return (1920, 0)


class DetachedPanelWindow:
    """
    A separate OS window that renders the side panel content.

    Usage:
        win = DetachedPanelWindow(panel_w, window_h)
        # Each frame: draw to win.surface, then call win.flip()
        # Events: filter pygame.event.get() by win.window_id
    """

    def __init__(self, panel_w: int, panel_h: int) -> None:
        if not _HAS_SDL2:
            raise RuntimeError(
                "pygame._sdl2.video is not available — "
                "upgrade to pygame 2.x to use the detached panel."
            )
        ox, oy = get_secondary_monitor_offset()
        self._win = _SDLWindow(
            "Drone Assistant Panel",
            size=(panel_w, panel_h),
            position=(ox, oy),
        )
        self._win.resizable = False
        self.surface: pygame.Surface = self._win.get_surface()
        self.window_id: int = self._win.id
        self._panel_w = panel_w
        self._panel_h = panel_h

    def flip(self) -> None:
        self._win.flip()

    def close(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass

    def filter_events(self, events: List[pygame.event.Event]) -> Tuple[
        List[pygame.event.Event],  # events for the panel window
        List[pygame.event.Event],  # remaining events for main window
    ]:
        panel_evts: List[pygame.event.Event] = []
        main_evts:  List[pygame.event.Event] = []
        for e in events:
            wid = getattr(e, "window", None)
            if wid is not None:
                eid = getattr(wid, "id", None) if hasattr(wid, "id") else None
                if eid == self.window_id:
                    panel_evts.append(e)
                    continue
            main_evts.append(e)
        return panel_evts, main_evts
