"""X11 display connection and management"""

import os
from typing import Optional
from Xlib import display as xdisplay, X
from Xlib.display import Display

from tx2tx.common.types import Position, ScreenGeometry


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
        self._cursor_confined: bool = False
        self._original_position: Optional[Position] = None
        self._cursor_hidden: bool = False
        self._blank_cursor: Optional[int] = None

    def connection_establish(self) -> None:
        """Establish connection to X11 display"""
        # Termux workaround: Monkey-patch python-xlib to find X11 socket in PREFIX/tmp
        # PyPI's python-xlib hardcodes /tmp/.X11-unix/, but termux has it at $PREFIX/tmp/.X11-unix/
        if 'PREFIX' in os.environ:
            try:
                from Xlib.support import unix_connect
                import socket as socket_module

                # Patch get_socket to use termux path
                original_get_socket = unix_connect.get_socket

                def _termux_get_socket(dname: str, protocol: object, host: object, dno: int) -> object:
                    # For unix sockets, check termux location first
                    if (protocol == 'unix' or (not protocol and (not host or host == 'unix'))):
                        termux_address = f"{os.environ['PREFIX']}/tmp/.X11-unix/X{dno}"
                        if os.path.exists(termux_address):
                            # Connect directly to termux socket
                            s = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
                            s.connect(termux_address)
                            return s
                    # Fall back to original implementation
                    return original_get_socket(dname, protocol, host, dno)

                unix_connect.get_socket = _termux_get_socket
            except (ImportError, AttributeError):
                pass  # Not an issue if module structure is different

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

    def cursor_confine(self, position: Position) -> None:
        """
        Confine cursor to a 1x1 pixel area at given position
        This effectively freezes the cursor in place

        Args:
            position: Position to confine cursor to

        Raises:
            RuntimeError: If not connected to display
        """
        if self._cursor_confined:
            return  # Already confined

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Store current position for restoration
        pointer_data = root.query_pointer()
        self._original_position = Position(x=pointer_data.root_x, y=pointer_data.root_y)

        # Move cursor to confinement position
        root.warp_pointer(position.x, position.y)
        display.sync()

        # Grab pointer to confine it
        # This prevents the physical mouse from moving the cursor
        result = root.grab_pointer(
            True,  # owner_events
            X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask,
            X.GrabModeAsync,
            X.GrabModeAsync,
            root,  # confine_to
            0,  # cursor
            X.CurrentTime
        )

        if result == 0:  # GrabSuccess
            self._cursor_confined = True
            display.sync()
        else:
            raise RuntimeError(f"Failed to confine cursor: grab result {result}")

    def cursor_release(self) -> None:
        """
        Release cursor confinement and restore original position

        Raises:
            RuntimeError: If not connected to display
        """
        if not self._cursor_confined:
            return  # Not confined

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Release pointer grab
        display.ungrab_pointer(X.CurrentTime)
        display.sync()

        # Restore original cursor position if we have it
        if self._original_position:
            root.warp_pointer(self._original_position.x, self._original_position.y)
            display.sync()
            self._original_position = None

        self._cursor_confined = False

    def cursorPosition_set(self, position: Position) -> None:
        """
        Move cursor to absolute position

        Args:
            position: Target position

        Raises:
            RuntimeError: If not connected to display
        """
        display = self.display_get()
        screen = display.screen()
        root = screen.root
        root.warp_pointer(position.x, position.y)
        display.sync()

    def cursor_hide(self) -> None:
        """
        Hide the cursor by setting it to a blank (invisible) cursor

        Raises:
            RuntimeError: If not connected to display
        """
        if self._cursor_hidden:
            return  # Already hidden

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Create a blank cursor if we haven't already
        if self._blank_cursor is None:
            # Create a 1x1 blank pixmap
            blank_pixmap = root.create_pixmap(1, 1, 1)

            # Create cursor from blank pixmap (both foreground and background)
            self._blank_cursor = root.create_cursor(
                blank_pixmap, blank_pixmap,
                (0, 0, 0),  # foreground color (doesn't matter, it's blank)
                (0, 0, 0),  # background color
                0, 0        # hotspot
            )
            blank_pixmap.free()

        # Set the blank cursor
        root.change_attributes(cursor=self._blank_cursor)
        display.sync()
        self._cursor_hidden = True

    def cursor_show(self) -> None:
        """
        Restore the normal cursor (undo cursor_hide)

        Raises:
            RuntimeError: If not connected to display
        """
        if not self._cursor_hidden:
            return  # Not hidden

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Restore default cursor (0 = default)
        root.change_attributes(cursor=0)
        display.sync()
        self._cursor_hidden = False
