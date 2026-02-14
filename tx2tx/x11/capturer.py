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
            display_manager: display_manager value.
        
        Returns:
            Result value.
        """
        self._display_manager: DisplayManager = display_manager
        self._keyboard_grabbed: bool = False
        self._last_pointer_position: Position = Position(x=0, y=0)

    def keyboard_grab(self) -> bool:
        """
        Grab keyboard to receive all keyboard events
        
        Args:
            None.
        
        Returns:
            Result value.
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
        """
        Release keyboard grab
        
        Args:
            None.
        
        Returns:
            Result value.
        """
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
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        display = self._display_manager.display_get()
        events: list[MouseEvent | KeyEvent] = []

        while display.pending_events() > 0:
            xev = display.next_event()
            self._xEvent_handle(xev, events)

        return events

    def _xEvent_handle(self, xev, events: list[MouseEvent | KeyEvent]) -> None:
        """
        Convert one X11 event into internal typed event(s).

        Args:
            xev: Raw X11 event.
            events: Output event accumulator.
        """
        if xev.type == X.ButtonPress:
            self._mouseButtonEvent_append(xev, EventType.MOUSE_BUTTON_PRESS, events)
            return
        if xev.type == X.ButtonRelease:
            self._mouseButtonEvent_append(xev, EventType.MOUSE_BUTTON_RELEASE, events)
            return
        if xev.type == X.MotionNotify:
            self._pointerPositionFromEvent_update(xev)
            return
        if xev.type == X.KeyPress:
            self._keyEvent_append(xev, EventType.KEY_PRESS, events)
            return
        if xev.type == X.KeyRelease:
            self._keyEvent_append(xev, EventType.KEY_RELEASE, events)

    def _mouseButtonEvent_append(
        self, xev, event_type: EventType, events: list[MouseEvent | KeyEvent]
    ) -> None:
        """
        Append a mouse button event if fields are present.

        Args:
            xev: Raw X11 event.
            event_type: Target mouse event type.
            events: Output event accumulator.
        """
        if not (hasattr(xev, "root_x") and hasattr(xev, "root_y") and hasattr(xev, "detail")):
            return
        position: Position = Position(x=xev.root_x, y=xev.root_y)
        self._last_pointer_position = position
        events.append(
            MouseEvent(
                event_type=event_type,
                position=position,
                button=xev.detail,
            )
        )

    def _pointerPositionFromEvent_update(self, xev) -> None:
        """
        Update tracked pointer position from motion event.

        Args:
            xev: Raw X11 motion event.
        """
        if not (hasattr(xev, "root_x") and hasattr(xev, "root_y")):
            return
        self._last_pointer_position = Position(x=xev.root_x, y=xev.root_y)

    def _keyEvent_append(
        self, xev, event_type: EventType, events: list[MouseEvent | KeyEvent]
    ) -> None:
        """
        Append a key event if keycode field is present.

        Args:
            xev: Raw X11 event.
            event_type: Target key event type.
            events: Output event accumulator.
        """
        if not hasattr(xev, "detail"):
            return
        events.append(KeyEvent(event_type=event_type, keycode=xev.detail))

    def isKeyboardGrabbed_check(self) -> bool:
        """
        Check if keyboard is currently grabbed
        
        Args:
            None.
        
        Returns:
            True if keyboard is grabbed.
        """
        """Check if keyboard is currently grabbed"""
        return self._keyboard_grabbed

    def positionLast_get(self) -> Position:
        """
        Get last captured pointer position
        
        Args:
            None.
        
        Returns:
            Last tracked pointer position, if any.
        """
        """Get last captured pointer position"""
        return self._last_pointer_position
