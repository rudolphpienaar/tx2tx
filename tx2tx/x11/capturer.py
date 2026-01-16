"""X11 event capturing for keyboard and mouse"""

from Xlib import X

from tx2tx.common.types import EventType, KeyEvent, MouseEvent, Position
from tx2tx.x11.display import DisplayManager


class EventCapturer:
    """Captures keyboard and mouse events from X11"""

    def __init__(self, display_manager: DisplayManager) -> None:
        """
        Initialize event capturer

        Args:
            display_manager: X11 display manager
        """
        self._display_manager: DisplayManager = display_manager
        self._keyboard_grabbed: bool = False
        self._last_pointer_position: Position = Position(x=0, y=0)

    def keyboard_grab(self) -> bool:
        """
        Grab keyboard to receive all keyboard events

        Returns:
            True if successful, False otherwise
        """
        if self._keyboard_grabbed:
            return True

        display = self._display_manager.display_get()
        screen = display.screen()
        root = screen.root

        result = root.grab_keyboard(
            True, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime  # owner_events
        )

        if result == 0:  # GrabSuccess
            self._keyboard_grabbed = True
            display.sync()
            return True
        return False

    def keyboard_release(self) -> None:
        """Release keyboard grab"""
        if not self._keyboard_grabbed:
            return

        display = self._display_manager.display_get()
        display.ungrab_keyboard(X.CurrentTime)
        display.sync()
        self._keyboard_grabbed = False

    def events_poll(self) -> list[MouseEvent | KeyEvent]:
        """
        Poll for pending events and convert to typed events

        Returns:
            List of MouseEvent and KeyEvent objects
        """
        display = self._display_manager.display_get()
        events: list[MouseEvent | KeyEvent] = []

        # Process all pending events
        while display.pending_events() > 0:
            xev = display.next_event()

            # Mouse button press
            if xev.type == X.ButtonPress:
                if hasattr(xev, "root_x") and hasattr(xev, "root_y") and hasattr(xev, "detail"):
                    position = Position(x=xev.root_x, y=xev.root_y)
                    self._last_pointer_position = position
                    events.append(
                        MouseEvent(
                            event_type=EventType.MOUSE_BUTTON_PRESS,
                            position=position,
                            button=xev.detail,
                        )
                    )

            # Mouse button release
            elif xev.type == X.ButtonRelease:
                if hasattr(xev, "root_x") and hasattr(xev, "root_y") and hasattr(xev, "detail"):
                    position = Position(x=xev.root_x, y=xev.root_y)
                    self._last_pointer_position = position
                    events.append(
                        MouseEvent(
                            event_type=EventType.MOUSE_BUTTON_RELEASE,
                            position=position,
                            button=xev.detail,
                        )
                    )

            # Motion notify (mouse movement)
            elif xev.type == X.MotionNotify:
                if hasattr(xev, "root_x") and hasattr(xev, "root_y"):
                    position = Position(x=xev.root_x, y=xev.root_y)
                    self._last_pointer_position = position
                    # We already send mouse moves from pointer tracking,
                    # but we update position for button events

            # Key press
            elif xev.type == X.KeyPress:
                if hasattr(xev, "detail"):
                    events.append(KeyEvent(event_type=EventType.KEY_PRESS, keycode=xev.detail))

            # Key release
            elif xev.type == X.KeyRelease:
                if hasattr(xev, "detail"):
                    events.append(KeyEvent(event_type=EventType.KEY_RELEASE, keycode=xev.detail))

        return events

    def isKeyboardGrabbed_check(self) -> bool:
        """Check if keyboard is currently grabbed"""
        return self._keyboard_grabbed

    def positionLast_get(self) -> Position:
        """Get last captured pointer position"""
        return self._last_pointer_position
