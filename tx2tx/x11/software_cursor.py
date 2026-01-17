"""Software cursor implementation using X11 Overlay Window"""

import logging
from typing import Optional
from Xlib import X, display
from Xlib.protocol import request

logger = logging.getLogger(__name__)

class SoftwareCursor:
    """
    Renders a software cursor using an override-redirect X11 window.
    Useful when the OS/Compositor hides the hardware cursor or fails to update it.
    """

    def __init__(self, display_manager, color: str = "red") -> None:
        """
        Initialize software cursor

        Args:
            display_manager: DisplayManager instance
            color: Cursor color ("red", "green", "blue", "white")
        """
        self._display_manager = display_manager
        self._window = None
        self._width = 20
        self._height = 20
        self._color = color
        self._visible = False

    def _setup(self) -> None:
        """Create the cursor window"""
        if self._window:
            return

        display = self._display_manager.display_get()
        screen = display.screen()
        root = screen.root

        # Allocate color
        cmap = screen.default_colormap
        if self._color == "red":
            bg_color = cmap.alloc_color(65535, 0, 0)
        elif self._color == "green":
            bg_color = cmap.alloc_color(0, 65535, 0)
        elif self._color == "blue":
            bg_color = cmap.alloc_color(0, 0, 65535)
        else:
            bg_color = cmap.alloc_color(65535, 65535, 65535)

        # Create window
        # override_redirect=True is CRITICAL: it tells the Window Manager (and Sommelier)
        # to leave this window alone (no title bar, no positioning logic).
        self._window = root.create_window(
            0, 0, self._width, self._height, 0,
            screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=bg_color.pixel,
            override_redirect=True
        )

        # Shape Extension for Input Transparency (Click-through)
        # If possible, we want to make the window "input transparent".
        # Standard X11 rectangular windows catch input.
        # We try to use XShape to mask the shape if available, 
        # or XFixes SetWindowShapeRegion if supported.
        # For now, simplistic approach: The window catches input.
        # Since we are injecting input *logically* via XTest, 
        # physical clicks on this window might be blocked?
        # Actually, XTest injects to the 'pointer', which might be 'under' this window.
        
        # Let's draw a simple crosshair shape using standard window background for now.
        # A solid square is fine for MVP.

        self._window.map()
        display.sync()
        self._visible = True
        logger.info("Software cursor created")

    def move(self, x: int, y: int) -> None:
        """
        Move cursor to position

        Args:
            x: X coordinate
            y: Y coordinate
        """
        if not self._window:
            self._setup()

        # Center the cursor window on the hotspot
        win_x = x - (self._width // 2)
        win_y = y - (self._height // 2)

        display = self._display_manager.display_get()
        
        # Use configure to move
        # stack_mode=X.Above ensures it stays on top of other windows
        self._window.configure(
            x=win_x, 
            y=win_y, 
            stack_mode=X.Above
        )
        # No sync() here for performance, rely on periodic event loop sync

    def show(self) -> None:
        """Show the cursor"""
        if self._window and not self._visible:
            self._window.map()
            self._visible = True

    def hide(self) -> None:
        """Hide the cursor"""
        if self._window and self._visible:
            self._window.unmap()
            self._visible = False

    def destroy(self) -> None:
        """Destroy the cursor window"""
        if self._window:
            self._window.destroy()
            self._window = None
