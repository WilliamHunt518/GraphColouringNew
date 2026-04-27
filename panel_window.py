"""
panel_window.py — separate side-panel window using SDL2 multi-window support.

Uses SDL2 Renderer + Texture upload rather than Window.get_surface(), which
is incompatible with hardware-accelerated main displays.

Falls back gracefully if pygame._sdl2 is unavailable (older pygame builds).
"""
from __future__ import annotations
import sys
from typing import List, Optional, Tuple

import pygame

try:
    from pygame._sdl2.video import Window as _SDLWindow
    _HAS_SDL2 = True
except ImportError:
    _HAS_SDL2 = False


def is_supported() -> bool:
    return _HAS_SDL2


def monitor_rect(index: int) -> Optional[Tuple[int, int, int, int]]:
    """
    Return (x, y, w, h) for monitor at *index* using Win32 ctypes.

    Critically, this works BEFORE pygame.init() is called, so it can be used
    to set SDL_VIDEO_WINDOW_POS before SDL2 creates its window — preventing
    Windows from moving or resizing the window after creation.

    DPI note: EnumDisplayMonitors returns logical (scaled) coordinates if the
    process is DPI-unaware. SDL2 uses physical pixels. We set DPI awareness
    first so both use the same coordinate space.

    Returns None on non-Windows platforms or if the query fails.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        # Without DPI awareness, EnumDisplayMonitors returns logical (scaled)
        # coords. SDL2 sets per-monitor DPI awareness internally and works in
        # physical pixels, so we must match that here.
        # OSError (E_ACCESSDENIED) means it's already set — that's fine.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        except OSError:
            pass

        rects: List[Tuple[int, int, int, int]] = []

        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_void_p,              # HMONITOR
            ctypes.c_void_p,              # HDC
            ctypes.POINTER(wintypes.RECT),
            ctypes.c_ssize_t,             # LPARAM
        )

        def _cb(hMon: int, hDC: int,
                lpRect: "ctypes.POINTER[wintypes.RECT]",
                dwData: int) -> int:
            r = lpRect.contents
            rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return 1  # TRUE — continue enumeration

        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MONITORENUMPROC(_cb), 0
        )
        if 0 <= index < len(rects):
            return rects[index]
        return rects[0] if rects else None
    except Exception:
        return None


class DetachedPanelWindow:
    """
    A separate OS window that renders the side panel content.

    Drawing workflow each frame:
      surf = panel_win.get_fresh_surface()  # always the same Surface — draw to it
      renderer.draw_frame(...)              # draws panel content onto surf
      panel_win.flip()                     # uploads surf to GPU and presents
    """

    def __init__(self, width: int, height: int,
                 pos_x: int = 0, pos_y: int = 0) -> None:
        if not _HAS_SDL2:
            raise RuntimeError(
                "pygame._sdl2.video not available — upgrade to pygame 2.x."
            )

        from pygame._sdl2.video import Renderer as _SDLRenderer

        self._win = _SDLWindow(
            "Agent Panel",
            size=(width, height),
            position=(pos_x, pos_y),
        )
        self._win.resizable = True
        try:
            self._win.focus()
        except Exception:
            pass
        try:
            self._win.show()
        except Exception:
            pass

        # Hardware renderer for the panel window
        self._renderer = _SDLRenderer(self._win)

        # CPU-side surface used for all panel drawing.
        # Unlike SDL_GetWindowSurface() surfaces, this is always valid — it's
        # a plain Python-managed Surface, not a hardware-backed SDL surface.
        self._cpu_surf = pygame.Surface((width, height))

        self.window_id: int = self._win.id
        self._width  = width
        self._height = height

    def get_fresh_surface(self) -> pygame.Surface:
        """
        Return the CPU drawing surface for this frame.
        Always valid — draw panel content here, then call flip().
        """
        return self._cpu_surf

    def flip(self) -> None:
        """Upload the CPU surface to the GPU and present the panel window."""
        from pygame._sdl2.video import Texture as _SDLTexture
        tex = _SDLTexture.from_surface(self._renderer, self._cpu_surf)
        self._renderer.clear()
        self._renderer.blit(tex, pygame.Rect(0, 0, self._width, self._height))
        self._renderer.present()

    def handle_resize(self, new_w: int, new_h: int) -> None:
        """Recreate the CPU surface after the panel window is resized."""
        self._width    = new_w
        self._height   = new_h
        self._cpu_surf = pygame.Surface((new_w, new_h))

    def close(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass

    def filter_events(
        self, events: List[pygame.event.Event]
    ) -> Tuple[List[pygame.event.Event], List[pygame.event.Event]]:
        """Split events into (panel_window_events, main_window_events)."""
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
