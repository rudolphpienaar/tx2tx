"""Wayland backend implementations using a privileged helper."""

from __future__ import annotations

from typing import Optional

from tx2tx.common.types import EventType, KeyEvent, MouseEvent, Position, Screen
from tx2tx.input.backend import DisplayBackend, InputCapturer, InputEvent, InputInjector
from tx2tx.wayland.helper import WaylandHelperClient

_KEYCODE_TO_KEYNAME: Optional[dict[int, str]] = None


def _keysym_from_evdev(keycode: int) -> Optional[int]:
    """
    Best-effort mapping from evdev keycode to X11 keysym.

    Args:
        keycode: evdev keycode

    Returns:
        X11 keysym integer or None if unknown.
    """
    try:
        from evdev import ecodes
        from Xlib import XK
    except Exception:
        return None

    global _KEYCODE_TO_KEYNAME
    if _KEYCODE_TO_KEYNAME is None:
        mapping: dict[int, str] = {}
        for name, value in ecodes.KEY.items():
            if not isinstance(name, str) or not name.startswith("KEY_"):
                continue
            if isinstance(value, int):
                mapping.setdefault(value, name)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, int):
                        mapping.setdefault(item, name)
        _KEYCODE_TO_KEYNAME = mapping

    key_name = _KEYCODE_TO_KEYNAME.get(keycode)

    if not key_name or not key_name.startswith("KEY_"):
        return None

    base = key_name[4:]
    special = {
        "ENTER": "Return",
        "ESC": "Escape",
        "SPACE": "space",
        "TAB": "Tab",
        "BACKSPACE": "BackSpace",
        "MINUS": "minus",
        "EQUAL": "equal",
        "LEFTBRACE": "bracketleft",
        "RIGHTBRACE": "bracketright",
        "SEMICOLON": "semicolon",
        "APOSTROPHE": "apostrophe",
        "GRAVE": "grave",
        "BACKSLASH": "backslash",
        "COMMA": "comma",
        "DOT": "period",
        "SLASH": "slash",
        "LEFTSHIFT": "Shift_L",
        "RIGHTSHIFT": "Shift_R",
        "LEFTCTRL": "Control_L",
        "RIGHTCTRL": "Control_R",
        "LEFTALT": "Alt_L",
        "RIGHTALT": "Alt_R",
        "LEFTMETA": "Super_L",
        "RIGHTMETA": "Super_R",
        "CAPSLOCK": "Caps_Lock",
        "DELETE": "Delete",
        "INSERT": "Insert",
        "HOME": "Home",
        "END": "End",
        "PAGEUP": "Page_Up",
        "PAGEDOWN": "Page_Down",
        "UP": "Up",
        "DOWN": "Down",
        "LEFT": "Left",
        "RIGHT": "Right",
        "PRINT": "Print",
        "PAUSE": "Pause",
    }

    if base in special:
        keysym_name = special[base]
    elif len(base) == 1 and base.isalpha():
        keysym_name = base.lower()
    elif base.isdigit():
        keysym_name = base
    elif base.startswith("F") and base[1:].isdigit():
        keysym_name = base
    else:
        return None

    keysym = XK.string_to_keysym(keysym_name)
    return keysym if keysym != 0 else None


class WaylandDisplayBackend(DisplayBackend):
    """Display backend backed by a privileged Wayland helper."""

    def __init__(
        self,
        helper_command: Optional[str],
        screen_width: Optional[int],
        screen_height: Optional[int],
    ) -> None:
        """
        Initialize Wayland display backend.
        
        Args:
            helper_command: helper_command value.
            screen_width: screen_width value.
            screen_height: screen_height value.
        
        Returns:
            Result value.
        """
        if not helper_command:
            raise RuntimeError(
                "Wayland backend requires a helper command. "
                "Provide --wayland-helper or set it in config."
            )
        self._helper: WaylandHelperClient = WaylandHelperClient(helper_command)
        self._screen_override: Optional[Screen] = None
        if screen_width is not None and screen_height is not None:
            self._screen_override = Screen(width=screen_width, height=screen_height)

    def connection_establish(self) -> None:
        """
        Establish connection to the Wayland helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Establish connection to the Wayland helper."""
        self._helper.connection_establish()

    def connection_close(self) -> None:
        """
        Close connection to the Wayland helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Close connection to the Wayland helper."""
        self._helper.connection_close()

    def connection_sync(self) -> None:
        """
        Synchronize helper state.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Synchronize helper state."""
        self._helper.connection_sync()

    def screenGeometry_get(self) -> Screen:
        """
        Return screen geometry from helper or override.
        
        Args:
            None.
        
        Returns:
            Screen geometry.
        """
        """Return screen geometry from helper or override."""
        if self._screen_override is not None:
            return self._screen_override

        width, height = self._helper.screenGeometry_get()
        return Screen(width=width, height=height)

    def pointerPosition_get(self) -> Position:
        """
        Return current pointer position from helper.
        
        Args:
            None.
        
        Returns:
            Pointer position.
        """
        """Return current pointer position from helper."""
        x, y = self._helper.pointerPosition_get()
        return Position(x=x, y=y)

    def cursorPosition_set(self, position: Position) -> None:
        """
        Set cursor position via helper.
        
        Args:
            position: position value.
        
        Returns:
            Result value.
        """
        """Set cursor position via helper."""
        self._helper.cursorPosition_set(position.x, position.y)

    def pointer_grab(self) -> None:
        """
        Grab pointer via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab pointer via helper."""
        self._helper.pointer_grab()

    def pointer_ungrab(self) -> None:
        """
        Release pointer grab via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release pointer grab via helper."""
        self._helper.pointer_ungrab()

    def keyboard_grab(self) -> None:
        """
        Grab keyboard via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab keyboard via helper."""
        self._helper.keyboard_grab()

    def keyboard_ungrab(self) -> None:
        """
        Release keyboard grab via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release keyboard grab via helper."""
        self._helper.keyboard_ungrab()

    def cursor_hide(self) -> None:
        """
        Hide cursor via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Hide cursor via helper."""
        self._helper.cursor_hide()

    def cursor_show(self) -> None:
        """
        Show cursor via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Show cursor via helper."""
        self._helper.cursor_show()

    def session_isNative_check(self) -> bool:
        """
        Return True if helper reports native session.
        
        Args:
            None.
        
        Returns:
            True if session is native.
        """
        """Return True if helper reports native session."""
        return self._helper.session_isNative_check()

    def helper_get(self) -> WaylandHelperClient:
        """
        Return underlying helper client.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Return underlying helper client."""
        return self._helper


class WaylandInputCapturer(InputCapturer):
    """Input capturer using Wayland helper event stream."""

    def __init__(self, display_backend: WaylandDisplayBackend) -> None:
        """
        Initialize Wayland input capturer.
        
        Args:
            display_backend: display_backend value.
        
        Returns:
            Result value.
        """
        self._display_backend: WaylandDisplayBackend = display_backend

    def inputEvents_read(self) -> tuple[list[InputEvent], int]:
        """
        Read pending input events from helper.
        
        Args:
            None.
        
        Returns:
            Tuple of input events and modifier state.
        """
        raw_events, modifier_state = self._display_backend.helper_get().inputEvents_read()
        events: list[InputEvent] = []

        for event in raw_events:
            event_type = event.get("event_type")
            if event_type == EventType.MOUSE_BUTTON_PRESS.value:
                events.append(
                    MouseEvent(
                        event_type=EventType.MOUSE_BUTTON_PRESS,
                        position=Position(x=int(event["x"]), y=int(event["y"])),
                        button=int(event["button"]),
                    )
                )
            elif event_type == EventType.MOUSE_BUTTON_RELEASE.value:
                events.append(
                    MouseEvent(
                        event_type=EventType.MOUSE_BUTTON_RELEASE,
                        position=Position(x=int(event["x"]), y=int(event["y"])),
                        button=int(event["button"]),
                    )
                )
            elif event_type == EventType.KEY_PRESS.value:
                events.append(
                    KeyEvent(
                        event_type=EventType.KEY_PRESS,
                        keycode=int(event["keycode"]),
                        keysym=(
                            int(event["keysym"])
                            if event.get("keysym") is not None
                            else _keysym_from_evdev(int(event["keycode"]))
                        ),
                        state=(
                            int(event["state"]) if event.get("state") is not None else None
                        ),
                    )
                )
            elif event_type == EventType.KEY_RELEASE.value:
                events.append(
                    KeyEvent(
                        event_type=EventType.KEY_RELEASE,
                        keycode=int(event["keycode"]),
                        keysym=(
                            int(event["keysym"])
                            if event.get("keysym") is not None
                            else _keysym_from_evdev(int(event["keycode"]))
                        ),
                        state=(
                            int(event["state"]) if event.get("state") is not None else None
                        ),
                    )
                )

        return events, modifier_state


class WaylandInputInjector(InputInjector):
    """Input injector using Wayland helper injection."""

    def __init__(self, display_backend: WaylandDisplayBackend) -> None:
        """
        Initialize Wayland input injector.
        
        Args:
            display_backend: display_backend value.
        
        Returns:
            Result value.
        """
        self._display_backend: WaylandDisplayBackend = display_backend

    def injectionReady_check(self) -> bool:
        """
        Return True if helper injection is available.
        
        Args:
            None.
        
        Returns:
            True if input injection is supported.
        """
        """Return True if helper injection is available."""
        return True

    def mouseEvent_inject(self, event: MouseEvent) -> None:
        """
        Inject a mouse event via helper.
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        """Inject a mouse event via helper."""
        payload = {"event_type": event.event_type.value}
        if event.position is not None:
            payload["x"] = event.position.x
            payload["y"] = event.position.y
        if event.button is not None:
            payload["button"] = event.button
        self._display_backend.helper_get().mouseEvent_inject(payload)

    def keyEvent_inject(self, event: KeyEvent) -> None:
        """
        Inject a key event via helper.
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        """Inject a key event via helper."""
        payload = {
            "event_type": event.event_type.value,
            "keycode": event.keycode,
        }
        if event.keysym is not None:
            payload["keysym"] = event.keysym
        if event.state is not None:
            payload["state"] = event.state
        self._display_backend.helper_get().keyEvent_inject(payload)
