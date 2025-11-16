"""X11 display connection and management"""

import logging
import os
from typing import Optional
from Xlib import display as xdisplay, X
from Xlib.display import Display

from tx2tx.common.types import Position, ScreenGeometry

logger = logging.getLogger(__name__)


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
        Hide cursor using XFixes extension with pixmap fallback

        Raises:
            RuntimeError: If not connected to display
        """
        if self._cursor_hidden:
            return

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Try XFixes first (modern, simple)
        xfixes_worked = False
        try:
            # Check if extension exists
            if display.has_extension('XFIXES') or display.query_extension('XFIXES'):
                root.xfixes_hide_cursor()
                display.sync()
                self._cursor_hidden = True
                xfixes_worked = True
                logger.debug("Cursor hidden using XFixes")
                return
        except Exception as e:
            logger.debug(f"XFixes failed, using fallback: {e}")
            xfixes_worked = False

        # Fallback: Skip cursor hiding if XFixes not available
        # (Cursor will remain visible but system will still work)
        if not xfixes_worked:
            logger.warning("XFixes not available, cursor will remain visible")
            logger.warning("System will continue to function normally")
            # FIX Issue 9: Don't mark as hidden if cursor is actually visible
            # This prevents state inconsistency
            # self._cursor_hidden remains False

    def cursor_show(self) -> None:
        """
        Show cursor

        Raises:
            RuntimeError: If not connected to display
        """
        if not self._cursor_hidden:
            return

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Try XFixes first
        xfixes_worked = False
        try:
            if display.has_extension('XFIXES') or display.query_extension('XFIXES'):
                root.xfixes_show_cursor()
                display.sync()
                self._cursor_hidden = False
                xfixes_worked = True
                logger.debug("Cursor shown using XFixes")
                return
        except Exception as e:
            logger.debug(f"XFixes failed, using fallback: {e}")
            xfixes_worked = False

        # Fallback: Restore default cursor
        if not xfixes_worked:
            try:
                root.change_attributes(cursor=0)  # 0 = use default cursor
                display.sync()
                self._cursor_hidden = False
                logger.debug("Cursor shown using default cursor")
            except Exception as e:
                logger.error(f"Failed to show cursor: {e}")
                raise

    def pointer_grab(self) -> None:
        """
        Grab pointer to capture all mouse events (prevents desktop from seeing them)

        Raises:
            RuntimeError: If not connected to display or grab fails
        """
        display = self.display_get()
        screen = display.screen()
        root = screen.root

        result = root.grab_pointer(
            True,  # owner_events - we receive events
            X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask,
            X.GrabModeAsync,
            X.GrabModeAsync,
            0,       # Don't confine to window (0 = no confinement)
            0,       # Don't change cursor
            X.CurrentTime
        )

        if result == 0:  # GrabSuccess
            display.sync()
            logger.debug("Pointer grabbed successfully")
        else:
            raise RuntimeError(f"Failed to grab pointer: result {result}")

    def pointer_ungrab(self) -> None:
        """
        Release pointer grab (return mouse events to desktop)

        Raises:
            RuntimeError: If not connected to display
        """
        display = self.display_get()
        display.ungrab_pointer(X.CurrentTime)
        display.sync()
        logger.debug("Pointer ungrabbed")

    def keyboard_grab(self) -> None:
        """
        Grab keyboard to capture all keyboard events (prevents desktop from seeing them)

        Raises:
            RuntimeError: If not connected to display or grab fails
        """
        display = self.display_get()
        screen = display.screen()
        root = screen.root

        result = root.grab_keyboard(
            True,  # owner_events - we receive events
            X.GrabModeAsync,
            X.GrabModeAsync,
            X.CurrentTime
        )

        if result == 0:  # GrabSuccess
            display.sync()
            logger.debug("Keyboard grabbed successfully")
        else:
            raise RuntimeError(f"Failed to grab keyboard: result {result}")

    def keyboard_ungrab(self) -> None:
        """
        Release keyboard grab (return keyboard events to desktop)

        Raises:
            RuntimeError: If not connected to display
        """
        display = self.display_get()
        display.ungrab_keyboard(X.CurrentTime)
        display.sync()
        logger.debug("Keyboard ungrabbed")
