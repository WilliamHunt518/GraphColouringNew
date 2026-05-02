from __future__ import annotations
import subprocess
from typing import Optional

import pygame


class ScreenRecorder:
    """Records pygame Surfaces to an MP4 file via an ffmpeg subprocess pipe."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._w = 0
        self._h = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, output_path: str, w: int, h: int, fps: int = 30) -> bool:
        """Spawn ffmpeg and begin recording.  Returns True on success."""
        if self._proc is not None:
            self.stop()
        # h264 requires even dimensions
        w += w % 2
        h += h % 2
        self._w, self._h = w, h
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{w}x{h}",
            "-r", str(fps),
            "-i", "pipe:0",
            "-vcodec", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "18",
            output_path,
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (FileNotFoundError, OSError):
            self._proc = None
            return False

    def add_frame(self, surface: pygame.Surface) -> None:
        """Write one frame.  Surface is scaled to recording dimensions if needed."""
        if self._proc is None or self._proc.stdin is None:
            return
        sw, sh = surface.get_size()
        if sw != self._w or sh != self._h:
            surface = pygame.transform.scale(surface, (self._w, self._h))
        try:
            self._proc.stdin.write(pygame.image.tostring(surface, "RGB"))
        except (BrokenPipeError, OSError):
            self._proc = None

    def stop(self) -> None:
        """Close the pipe and wait for ffmpeg to finish encoding."""
        if self._proc is None:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.wait(timeout=60)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    @property
    def active(self) -> bool:
        return self._proc is not None
