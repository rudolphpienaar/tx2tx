"""X11 display connection and management"""

import logging
import os
import time
from typing import Optional
from Xlib import display as xdisplay, X
from Xlib.display import Display
from Xlib.ext import xtest

from tx2tx.common.types import Position, ScreenGeometry

logger = logging.getLogger(__name__)


def is_native_x11() -> bool:
    """
    Detect if running on native X11 vs Wayland/Crostini compositor.

    Returns:
        True if native X11 (XFCE4, KDE, GNOME on X11), False for Wayland/Crostini
    """
    # Check session type environment variable
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session_type == "x11":
        return True
    elif session_type == "wayland":
        return False

    # Check for Crostini/sommelier compositor (Wayland-based)
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    if "wayland" in wayland_display.lower() or "sommelier" in wayland_display.lower():
        return False

    # Check for termux environment (Android X11)
    if "PREFIX" in os.environ:
        prefix = os.environ.get("PREFIX", "")
        if "termux" in prefix or "com.termux" in prefix:
            return False  # termux-x11 needs special handling

    # Default: assume native X11 if DISPLAY is set without Wayland indicators
    return "DISPLAY" in os.environ

# X11 cursor font constants (from X11/cursorfont.h)
# Each cursor shape has an even number; the mask is shape + 1
XC_X_CURSOR = 0  # X shape
XC_CROSSHAIR = 34  # Crosshair +
XC_DOT = 38  # Small dot
XC_TCROSS = 130  # Thin cross
XC_PIRATE = 88  # Skull and crossbones


class DisplayManager:
    """Manages X11 display connection and screen information"""

    def __init__(
        self,
        display_name: Optional[str] = None,
        overlay_enabled: bool = False,
        x11native: bool = False,
    ) -> None:
        """
        Initialize display manager

        Args:
            display_name: X11 display name (e.g., ':0'), None for default
            overlay_enabled: Whether to use fullscreen overlay window (Crostini workaround)
            x11native: Whether to optimize for native X11 (disables Crostini workarounds)
        """
        self._display: Optional[Display] = None
        self._display_name: Optional[str] = display_name
        self._overlay_enabled: bool = overlay_enabled
        self._x11native: bool = x11native
        self._cursor_confined: bool = False
        self._original_position: Optional[Position] = None
        self._cursor_hidden: bool = False
        self._blank_cursor: Optional[int] = None
        self._remote_cursor: Optional[int] = None  # Gray X cursor for remote mode
        self._cursor_overlay_window = None  # Fullscreen overlay for cursor display

    def connection_establish(self) -> None:
        """Establish connection to X11 display"""
        # Termux workaround: Monkey-patch python-xlib to find X11 socket in PREFIX/tmp
        # PyPI's python-xlib hardcodes /tmp/.X11-unix/, but termux has it at $PREFIX/tmp/.X11-unix/
        if "PREFIX" in os.environ:
            try:
                from Xlib.support import unix_connect
                import socket as socket_module

                # Patch get_socket to use termux path
                original_get_socket = unix_connect.get_socket

                def _termux_get_socket(
                    dname: str, protocol: object, host: object, dno: int
                ) -> object:
                    """Termux-specific socket locator that checks PREFIX/tmp before /tmp"""
                    # For unix sockets, check termux location first
                    if protocol == "unix" or (not protocol and (not host or host == "unix")):
                        termux_address = f"{os.environ['PREFIX']}/tmp/.X11-unix/X{dno}"
                        if os.path.exists(termux_address):
                            # Connect directly to termux socket
                            s = socket_module.socket(
                                socket_module.AF_UNIX, socket_module.SOCK_STREAM
                            )
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

        # Move cursor to confinement position (uses warp_pointer on native X11, XTest on Crostini)
        self.cursorPosition_set(position)

        # Grab pointer to confine it
        # This prevents the physical mouse from moving the cursor
        result = root.grab_pointer(
            True,  # owner_events
            X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask,
            X.GrabModeAsync,
            X.GrabModeAsync,
            root,  # confine_to
            0,  # cursor
            X.CurrentTime,
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

        # Release pointer grab
        display.ungrab_pointer(X.CurrentTime)
        display.sync()

        # Restore original cursor position (uses warp_pointer on native X11, XTest on Crostini)
        if self._original_position:
            self.cursorPosition_set(self._original_position)
            self._original_position = None

        self._cursor_confined = False

    def cursorPosition_set(self, position: Position) -> None:
        """
        Move cursor to absolute position (environment-aware implementation).

        Uses native warp_pointer on X11, XTest fake_input on Wayland/Crostini.

        Args:
            position: Target position

        Raises:
            RuntimeError: If not connected to display
        """
        # Use native warp_pointer on native X11 for proper cursor control
        if self._x11native or is_native_x11():
            self.cursorPosition_setViaWarpPointer(position)
        else:
            # Fall back to XTest for Crostini/Wayland where warp_pointer is blocked
            self.cursorPosition_setViaXTest(position)

    def cursorPosition_setViaWarpPointer(self, position: Position) -> None:
        """
        Move cursor using native X11 warp_pointer (works on native X11 only).

        This is the proper X11 API for cursor positioning and works perfectly
        on native X11 desktops (XFCE4, KDE, GNOME on X11). Wayland compositors
        may block or ignore this method.

        Args:
            position: Target position

        Raises:
            RuntimeError: If not connected to display
        """
        display = self.display_get()
        screen = display.screen()
        root = screen.root

        logger.debug(f"[X11] warp_pointer to ({position.x}, {position.y})")
        root.warp_pointer(position.x, position.y)
        display.sync()

        # Verify position
        pointer_data = root.query_pointer()
        actual_x = pointer_data.root_x
        actual_y = pointer_data.root_y
        logger.debug(f"[X11] After warp: actual position = ({actual_x}, {actual_y})")

    def cursorPosition_setViaXTest(self, position: Position) -> None:
        """
        Move cursor using XTest fake_input (Crostini/Wayland workaround).

        XTest was designed for testing/automation, not cursor control, but
        it works in environments where warp_pointer is blocked by compositors.

        Args:
            position: Target position

        Raises:
            RuntimeError: If not connected to display
        """
        display = self.display_get()

        logger.debug(f"[X11] XTest fake_input MotionNotify to ({position.x}, {position.y})")
        xtest.fake_input(display, X.MotionNotify, detail=0, x=position.x, y=position.y)
        display.sync()

        # Verify position
        screen = display.screen()
        root = screen.root
        pointer_data = root.query_pointer()
        actual_x = pointer_data.root_x
        actual_y = pointer_data.root_y
        logger.debug(f"[X11] After XTest move: actual position = ({actual_x}, {actual_y})")

    def cursorPosition_setAndVerify(
        self, position: Position, timeout_ms: int = 100, tolerance: int = 5
    ) -> bool:
        """
        Move cursor to absolute position and verify it actually moved there.
        This prevents race conditions where we query position before warp takes effect.

        Args:
            position: Target position
            timeout_ms: Maximum time to wait for verification (milliseconds)
            tolerance: Maximum pixel difference to consider position correct

        Returns:
            True if cursor successfully moved to position, False on timeout

        Raises:
            RuntimeError: If not connected to display
        """
        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Issue warp command (uses warp_pointer on native X11, XTest on Crostini)
        self.cursorPosition_set(position)

        # Poll position until it matches or timeout
        start_time = time.time()
        timeout_sec = timeout_ms / 1000.0

        while (time.time() - start_time) < timeout_sec:
            # Query actual position
            pointer_data = root.query_pointer()
            actual_x = pointer_data.root_x
            actual_y = pointer_data.root_y

            # Check if position matches within tolerance
            if abs(actual_x - position.x) <= tolerance and abs(actual_y - position.y) <= tolerance:
                return True

            # Small delay before next poll (1ms)
            time.sleep(0.001)
            display.sync()

        # Timeout - position never matched
        logger.warning(
            f"Cursor warp verification failed: target=({position.x},{position.y}), "
            f"actual=({actual_x},{actual_y}), timeout={timeout_ms}ms"
        )
        return False

    def _ensure_blank_cursor(self) -> int:
        """Create a blank cursor if one doesn't exist"""
        if self._blank_cursor is not None:
            return self._blank_cursor

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        try:
            # Create a 1x1 bitmap (depth 1)
            pixmap = root.create_pixmap(1, 1, 1)

            # Create a GC to draw into the pixmap
            gc = pixmap.create_gc(foreground=0, background=0)

            # clear the pixmap (make it 0)
            pixmap.fill_rectangle(gc, 0, 0, 1, 1)

            # Color must be a dictionary with RGB values for python-xlib
            color = {"red": 0, "green": 0, "blue": 0}

            # Create cursor. mask=pixmap means the shape is defined by pixmap.
            # since pixmap is all 0s, the mask is empty -> fully transparent.
            cursor = display.create_pixmap_cursor(pixmap, pixmap, color, color, 0, 0)

            # Cleanup
            pixmap.free()
            gc.free()

            self._blank_cursor = cursor
            return cursor
        except Exception as e:
            logger.error(f"Failed to create blank cursor: {e}")
            return 0

    def _remoteCursor_create(self) -> int:
        """
        Create a gray X cursor to indicate remote control mode.
        Uses the standard X11 cursor font which is universally supported.

        Returns:
            Cursor ID, or 0 on failure
        """
        if self._remote_cursor is not None:
            return self._remote_cursor

        display = self.display_get()

        try:
            # Open the standard cursor font
            cursor_font = display.open_font("cursor")

            # Create cursor from font glyph
            # XC_X_CURSOR = 0, mask is always glyph + 1
            # Colors are 16-bit RGB values (0-65535)
            # Gray foreground (50% gray), white background
            cursor = cursor_font.create_glyph_cursor(
                cursor_font,  # mask font (same as source)
                XC_X_CURSOR,  # source char (0 = X shape)
                XC_X_CURSOR + 1,  # mask char
                (32768, 32768, 32768),  # foreground: 50% gray
                (65535, 65535, 65535),  # background: white
            )

            cursor_font.close()
            self._remote_cursor = cursor
            logger.debug("Created gray X cursor for remote mode")
            return cursor

        except Exception as e:
            logger.error(f"Failed to create gray X cursor: {e}")
            return 0

    def _cursorOverlay_create(self) -> bool:
        """
        Create a fullscreen overlay window with the remote-mode cursor.

        In Crostini/Wayland, changing the root window cursor doesn't work
        because the compositor ignores root window cursor settings. However,
        it DOES respect cursor settings on actual X11 windows.

        This creates a fullscreen, input-transparent overlay window with
        the gray X cursor. When mapped, the cursor appears over the entire
        screen.

        Returns:
            True if overlay created successfully, False otherwise
        """
        if self._cursor_overlay_window is not None:
            return True  # Already exists

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        try:
            # Create the cursor first
            cursor = self._remoteCursor_create()
            if not cursor:
                logger.error("Failed to create cursor for overlay")
                return False

            # Create fullscreen overlay window
            # override_redirect=True: window manager won't decorate or manage it
            # We use a 1x1 window that we'll resize to fullscreen
            # Input events pass through because we have pointer grabbed anyway
            self._cursor_overlay_window = root.create_window(
                0,
                0,  # position (top-left)
                screen.width_in_pixels,  # full width
                screen.height_in_pixels,  # full height
                0,  # border width
                screen.root_depth,  # depth
                X.InputOutput,  # window class
                X.CopyFromParent,  # visual
                background_pixel=0,  # transparent (won't matter)
                override_redirect=True,  # bypass window manager
                cursor=cursor,  # the gray X cursor
                event_mask=0,  # don't capture any events
            )

            # Make window transparent using the
            # We set colormap to make the background not drawn
            # The window exists only to provide cursor, not visuals

            logger.debug("Created cursor overlay window")
            return True

        except Exception as e:
            logger.error(f"Failed to create cursor overlay: {e}")
            self._cursor_overlay_window = None
            return False

    def _cursorOverlay_show(self) -> bool:
        """Map (show) the cursor overlay window."""
        if self._cursor_overlay_window is None:
            if not self._cursorOverlay_create():
                return False

        try:
            display = self.display_get()
            self._cursor_overlay_window.map()
            # Raise to top to ensure cursor is visible
            self._cursor_overlay_window.configure(stack_mode=X.Above)
            display.sync()
            logger.info("Cursor overlay shown (gray X cursor active)")
            return True
        except Exception as e:
            logger.error(f"Failed to show cursor overlay: {e}")
            return False

    def _cursorOverlay_hide(self) -> None:
        """Unmap (hide) the cursor overlay window."""
        if self._cursor_overlay_window is None:
            return

        try:
            display = self.display_get()
            self._cursor_overlay_window.unmap()
            display.sync()
            logger.debug("Cursor overlay hidden")
        except Exception as e:
            logger.warning(f"Failed to hide cursor overlay: {e}")

    def cursor_hide(self) -> None:
        """
        Hide cursor or change to remote-mode indicator.

        Strategy depends on environment:
        - Native X11 (--x11native or auto-detected): Use XFixes/root cursor (optimal)
        - Crostini/Wayland: Use overlay window (workaround for compositor issues)

        Raises:
            RuntimeError: If not connected to display
        """
        if self._cursor_hidden:
            return

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Determine if we're on native X11
        native_x11 = self._x11native or is_native_x11()

        # NATIVE X11 PATH - Optimal methods that work perfectly on full X11
        if native_x11 and not self._overlay_enabled:
            logger.debug("Using native X11 cursor hiding methods")

            # Method 1: XFixes (best - true invisibility)
            try:
                if display.has_extension("XFIXES"):
                    display.xfixes.hide_cursor(root)
                    display.sync()
                    self._cursor_hidden = True
                    logger.info("Cursor hidden (XFixes - native X11)")
                    return
            except Exception as e:
                logger.debug(f"XFixes hide_cursor failed: {e}")

            # Method 2: Gray X Cursor on root window
            try:
                cursor = self._remoteCursor_create()
                if cursor:
                    root.change_attributes(cursor=cursor)
                    display.sync()
                    self._cursor_hidden = True
                    logger.info("Cursor set to gray X (remote mode indicator)")
                    return
            except Exception as e:
                logger.debug(f"Failed to set gray X cursor: {e}")

            # Method 3: Blank pixmap cursor (fallback)
            try:
                cursor = self._ensure_blank_cursor()
                if cursor:
                    root.change_attributes(cursor=cursor)
                    display.sync()
                    self._cursor_hidden = True
                    logger.info("Cursor hidden (blank pixmap)")
                    return
            except Exception as e:
                logger.debug(f"Failed to set blank cursor: {e}")

        # CROSTINI/WAYLAND PATH - Overlay window workaround
        else:
            logger.debug("Using Crostini/Wayland cursor hiding methods")

            # Method 1: Fullscreen overlay window with cursor
            # This WORKS in Crostini because compositor respects window cursors
            if self._overlay_enabled:
                if self._cursorOverlay_show():
                    self._cursor_hidden = True
                    return
            else:
                logger.debug("Overlay disabled, trying fallback methods")

            # Method 2: Gray X Cursor on root window (may not work but try anyway)
            try:
                cursor = self._remoteCursor_create()
                if cursor:
                    root.change_attributes(cursor=cursor)
                    display.sync()
                    self._cursor_hidden = True
                    logger.info("Cursor set to gray X (remote mode indicator)")
                    return
            except Exception as e:
                logger.debug(f"Failed to set gray X cursor: {e}")

            # Method 3: XFixes (may not work in Crostini but try anyway)
            try:
                if display.has_extension("XFIXES"):
                    display.xfixes.hide_cursor(root)
                    display.sync()
                    self._cursor_hidden = True
                    logger.debug("Cursor hidden (XFixes)")
                    return
            except Exception as e:
                logger.debug(f"XFixes hide_cursor failed: {e}")

            # Method 4: Blank Cursor (last resort)
            try:
                cursor = self._ensure_blank_cursor()
                if cursor:
                    root.change_attributes(cursor=cursor)
                    display.sync()
                    self._cursor_hidden = True
                    logger.debug("Cursor hidden (blank cursor)")
                    return
            except Exception as e:
                logger.debug(f"Failed to set blank cursor: {e}")

        logger.warning("All cursor hiding methods failed")

    def cursor_show(self) -> None:
        """
        Show cursor (restore normal cursor appearance)

        Raises:
            RuntimeError: If not connected to display
        """
        if not self._cursor_hidden:
            return

        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # First: Hide overlay window if it exists
        self._cursorOverlay_hide()

        # Method 1: XFixes show_cursor
        try:
            if display.has_extension("XFIXES"):
                display.xfixes.show_cursor(root)
                display.sync()
                self._cursor_hidden = False
                logger.debug("Cursor shown (XFixes)")
                return
        except Exception as e:
            logger.warning(f"XFixes show_cursor failed: {e}")

        # Method 2: Restore default cursor on root
        try:
            root.change_attributes(cursor=0)
            display.sync()
            self._cursor_hidden = False
            logger.debug("Cursor shown (default)")
        except Exception as e:
            logger.error(f"Failed to show cursor: {e}")

    def pointer_grab(self) -> None:
        """
        Grab pointer to capture all mouse events (prevents desktop from seeing them)

        Raises:
            RuntimeError: If not connected to display or grab fails
        """
        display = self.display_get()
        screen = display.screen()
        root = screen.root

        # Use blank cursor if hidden, otherwise 0 (None/default)
        cursor = self._blank_cursor if (self._cursor_hidden and self._blank_cursor) else 0

        result = root.grab_pointer(
            True,  # owner_events - we receive events
            X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask,
            X.GrabModeAsync,
            X.GrabModeAsync,
            0,  # Don't confine to window (0 = no confinement)
            cursor,  # Use blank cursor if hidden
            X.CurrentTime,
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
            X.CurrentTime,
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

    def connection_fileno(self) -> int:
        """
        Get file descriptor for X11 connection

        Returns:
            File descriptor number

        Raises:
            RuntimeError: If not connected to display
        """
        return self.display_get().fileno()

    def events_process(self) -> None:
        """Process all pending X11 events."""
        display = self.display_get()
        while display.pending_events() > 0:
            display.next_event()
