"""X11 display connection and management"""

from typing import Optional
from Xlib import display as xdisplay
from Xlib.display import Display

from tx2tx.common.types import ScreenGeometry


class DisplayManager:
    """Manages X11 display connection and screen information"""

    def __init__(self, display_name: Optional[str] = None) -> None:
        """
        Initialize display manager

        Args:
            display_name: X11 display name (e.g., ':0'), None for default
        """
        self._display: Optional[Display] = None
        self._display_name: Optional[str] = display_name

    def connection_establish(self) -> None:
        """Establish connection to X11 display"""
        self._display = xdisplay.Display(self._display_name)

    def connection_close(self) -> None:
        """Close X11 display connection"""
        if self._display is not None:
            self._display.close()
            self._display = None

    def display_get(self) -> Display:
        """
        Get X11 display object

        Returns:
            X11 Display object

        Raises:
            RuntimeError: If not connected to display
        """
        if self._display is None:
            raise RuntimeError("Not connected to X11 display")
        return self._display

    def screenGeometry_get(self) -> ScreenGeometry:
        """
        Get screen geometry (dimensions)

        Returns:
            Screen geometry with width and height

        Raises:
            RuntimeError: If not connected to display
        """
        display = self.display_get()
        screen = display.screen()
        root = screen.root
        geom = root.get_geometry()

        return ScreenGeometry(width=geom.width, height=geom.height)

    def __enter__(self) -> "DisplayManager":
        """Context manager entry"""
        self.connection_establish()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit"""
        self.connection_close()
