"""Large numeric hint overlay for X11 clients."""

from __future__ import annotations

import logging
import time

from Xlib import X

logger = logging.getLogger(__name__)


class HintOverlay:
    """Displays a centered, temporary numeric hint window."""

    def __init__(self, display_manager) -> None:
        """
        Initialize hint overlay.

        Args:
            display_manager: X11 display manager instance.
        """
        self._display_manager = display_manager
        self._window = None
        self._gc = None
        self._visible: bool = False
        self._hide_deadline: float = 0.0
        self._label: str = ""

    def _setup(self) -> None:
        """
        Create hint window and graphics context.

        Returns:
            None.
        """
        if self._window is not None:
            return

        display = self._display_manager.display_get()
        screen = display.screen()
        root = screen.root
        width: int = 260
        height: int = 260
        x: int = max(0, (screen.width_in_pixels - width) // 2)
        y: int = max(0, (screen.height_in_pixels - height) // 2)

        colormap = screen.default_colormap
        background = colormap.alloc_color(0, 0, 0).pixel
        foreground = colormap.alloc_color(65535, 65535, 65535).pixel

        self._window = root.create_window(
            x,
            y,
            width,
            height,
            0,
            screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=background,
            border_pixel=foreground,
            override_redirect=True,
            event_mask=0,
        )
        self._gc = self._window.create_gc(foreground=foreground, background=background)
        self._window.configure(stack_mode=X.Above)
        display.sync()

    def show(self, label: str, timeout_ms: int) -> None:
        """
        Show overlay label for timeout window.

        Args:
            label: Single-digit label.
            timeout_ms: Visibility timeout in milliseconds.
        """
        self._setup()
        if self._window is None or self._gc is None:
            return

        self._label = label.strip()[:1]
        self._window.clear_area()
        self._digit_draw(self._label)
        self._window.map()
        self._window.configure(stack_mode=X.Above)
        self._display_manager.connection_sync()
        self._visible = True
        self._hide_deadline = time.time() + max(0.1, timeout_ms / 1000.0)

    def hide(self) -> None:
        """
        Hide hint overlay.

        Returns:
            None.
        """
        if self._window is None or not self._visible:
            return
        try:
            self._window.unmap()
            self._display_manager.connection_sync()
        except Exception as exc:
            logger.debug("Hint overlay hide failed: %s", exc)
        self._visible = False
        self._hide_deadline = 0.0

    def tick(self) -> None:
        """
        Expire overlay when timeout elapses.

        Returns:
            None.
        """
        if self._visible and self._hide_deadline > 0 and time.time() >= self._hide_deadline:
            self.hide()

    def destroy(self) -> None:
        """
        Destroy overlay window resources.

        Returns:
            None.
        """
        if self._window is None:
            return
        try:
            self._window.destroy()
            self._display_manager.connection_sync()
        except Exception as exc:
            logger.debug("Hint overlay destroy failed: %s", exc)
        self._window = None
        self._gc = None
        self._visible = False
        self._hide_deadline = 0.0

    def _digit_draw(self, label: str) -> None:
        """
        Draw large seven-segment digit for label.

        Args:
            label: Label character.
        """
        if self._window is None or self._gc is None:
            return

        segment_rects = {
            "a": (60, 25, 140, 20),
            "b": (200, 45, 20, 75),
            "c": (200, 140, 20, 75),
            "d": (60, 215, 140, 20),
            "e": (40, 140, 20, 75),
            "f": (40, 45, 20, 75),
            "g": (60, 120, 140, 20),
        }
        digit_segments = {
            "0": ("a", "b", "c", "d", "e", "f"),
            "1": ("b", "c"),
            "2": ("a", "b", "g", "e", "d"),
            "3": ("a", "b", "g", "c", "d"),
            "4": ("f", "g", "b", "c"),
            "5": ("a", "f", "g", "c", "d"),
            "6": ("a", "f", "g", "e", "c", "d"),
            "7": ("a", "b", "c"),
            "8": ("a", "b", "c", "d", "e", "f", "g"),
            "9": ("a", "b", "c", "d", "f", "g"),
        }
        segments = digit_segments.get(label)
        if segments is None:
            self._window.draw_text(self._gc, 110, 145, label)
            return
        for segment_name in segments:
            x, y, width, height = segment_rects[segment_name]
            self._window.fill_rectangle(self._gc, x, y, width, height)
