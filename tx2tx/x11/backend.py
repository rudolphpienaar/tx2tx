"""X11 backend implementations for display, capture, and injection."""

from __future__ import annotations

from typing import Optional

from Xlib import X

from tx2tx.common.types import EventType, KeyEvent, MouseEvent, Position, Screen
from tx2tx.input.backend import DisplayBackend, InputCapturer, InputEvent, InputInjector
from tx2tx.x11.display import DisplayManager, is_native_x11
from tx2tx.x11.injector import EventInjector


class X11DisplayBackend(DisplayBackend):
    """Display backend backed by X11."""

    def __init__(
        self,
        display_name: Optional[str] = None,
        overlay_enabled: bool = False,
        x11native: bool = False,
    ) -> None:
        """
        Initialize X11 display backend.
        
        Args:
            display_name: display_name value.
            overlay_enabled: overlay_enabled value.
            x11native: x11native value.
        
        Returns:
            Result value.
        """
        self._display_manager: DisplayManager = DisplayManager(
            display_name=display_name,
            overlay_enabled=overlay_enabled,
            x11native=x11native,
        )

    def connection_establish(self) -> None:
        """
        Establish connection to the X11 display.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Establish connection to the X11 display."""
        self._display_manager.connection_establish()

    def connection_close(self) -> None:
        """
        Close connection to the X11 display.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Close connection to the X11 display."""
        self._display_manager.connection_close()

    def connection_sync(self) -> None:
        """
        Flush and synchronize the X11 connection.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Flush and synchronize the X11 connection."""
        self._display_manager.connection_sync()

    def screenGeometry_get(self) -> Screen:
        """
        Return screen geometry for the X11 display.
        
        Args:
            None.
        
        Returns:
            Screen geometry.
        """
        """Return screen geometry for the X11 display."""
        return self._display_manager.screenGeometry_get()

    def pointerPosition_get(self) -> Position:
        """
        Return current pointer position from X11.
        
        Args:
            None.
        
        Returns:
            Pointer position.
        """
        """Return current pointer position from X11."""
        display = self._display_manager.display_get()
        screen = display.screen()
        root = screen.root
        pointer_data = root.query_pointer()
        return Position(x=pointer_data.root_x, y=pointer_data.root_y)

    def cursorPosition_set(self, position: Position) -> None:
        """
        Set cursor position in X11.
        
        Args:
            position: position value.
        
        Returns:
            Result value.
        """
        """Set cursor position in X11."""
        self._display_manager.cursorPosition_set(position)

    def pointer_grab(self) -> None:
        """
        Grab the pointer at the X11 level.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab the pointer at the X11 level."""
        self._display_manager.pointer_grab()

    def pointer_ungrab(self) -> None:
        """
        Release the pointer grab in X11.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release the pointer grab in X11."""
        self._display_manager.pointer_ungrab()

    def keyboard_grab(self) -> None:
        """
        Grab the keyboard at the X11 level.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab the keyboard at the X11 level."""
        self._display_manager.keyboard_grab()

    def keyboard_ungrab(self) -> None:
        """
        Release the keyboard grab in X11.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release the keyboard grab in X11."""
        self._display_manager.keyboard_ungrab()

    def cursor_hide(self) -> None:
        """
        Hide the cursor in X11.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Hide the cursor in X11."""
        self._display_manager.cursor_hide()

    def cursor_show(self) -> None:
        """
        Show the cursor in X11.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Show the cursor in X11."""
        self._display_manager.cursor_show()

    def session_isNative_check(self) -> bool:
        """
        Return True if the session is native X11.
        
        Args:
            None.
        
        Returns:
            True if session is native.
        """
        """Return True if the session is native X11."""
        return is_native_x11()

    def displayManager_get(self) -> DisplayManager:
        """
        Access underlying DisplayManager (X11-specific).
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Access underlying DisplayManager (X11-specific)."""
        return self._display_manager


class X11InputCapturer(InputCapturer):
    """Input capturer using X11 events."""

    def __init__(self, display_backend: X11DisplayBackend) -> None:
        """
        Initialize X11 input capturer.
        
        Args:
            display_backend: display_backend value.
        
        Returns:
            Result value.
        """
        self._display_backend: X11DisplayBackend = display_backend

    def inputEvents_read(self) -> tuple[list[InputEvent], int]:
        """
        Read pending X11 input events.
        
        Args:
            None.
        
        Returns:
            Tuple of input events and modifier state.
        """
        display = self._display_backend.displayManager_get().display_get()
        events: list[InputEvent] = []
        modifier_state = 0

        while display.pending_events() > 0:
            event = display.next_event()

            if event.type == X.ButtonPress:
                events.append(
                    MouseEvent(
                        event_type=EventType.MOUSE_BUTTON_PRESS,
                        position=Position(x=event.root_x, y=event.root_y),
                        button=event.detail,
                    )
                )
                modifier_state = event.state
            elif event.type == X.ButtonRelease:
                events.append(
                    MouseEvent(
                        event_type=EventType.MOUSE_BUTTON_RELEASE,
                        position=Position(x=event.root_x, y=event.root_y),
                        button=event.detail,
                    )
                )
                modifier_state = event.state
            elif event.type == X.KeyPress:
                events.append(
                    KeyEvent(
                        event_type=EventType.KEY_PRESS,
                        keycode=event.detail,
                        keysym=display.keycode_to_keysym(event.detail, 0),
                        state=event.state,
                    )
                )
                modifier_state = event.state
            elif event.type == X.KeyRelease:
                events.append(
                    KeyEvent(
                        event_type=EventType.KEY_RELEASE,
                        keycode=event.detail,
                        keysym=display.keycode_to_keysym(event.detail, 0),
                        state=event.state,
                    )
                )
                modifier_state = event.state

        return events, modifier_state


class X11InputInjector(InputInjector):
    """Input injector using X11 XTest."""

    def __init__(self, display_backend: X11DisplayBackend) -> None:
        """
        Initialize X11 input injector.
        
        Args:
            display_backend: display_backend value.
        
        Returns:
            Result value.
        """
        self._display_backend: X11DisplayBackend = display_backend
        self._injector: EventInjector = EventInjector(
            display_manager=display_backend.displayManager_get()
        )

    def injectionReady_check(self) -> bool:
        """
        Return True if XTest injection is available.
        
        Args:
            None.
        
        Returns:
            True if input injection is supported.
        """
        """Return True if XTest injection is available."""
        return self._injector.xtestExtension_verify()

    def mouseEvent_inject(self, event: MouseEvent) -> None:
        """
        Inject a mouse event via X11 XTest.
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        """Inject a mouse event via X11 XTest."""
        self._injector.mouseEvent_inject(event)

    def keyEvent_inject(self, event: KeyEvent) -> None:
        """
        Inject a key event via X11 XTest.
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        """Inject a key event via X11 XTest."""
        self._injector.keyEvent_inject(event)
