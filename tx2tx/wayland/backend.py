"""Wayland backend implementations using a privileged helper."""

from __future__ import annotations

import logging
from typing import Any, Optional

from tx2tx.common.types import EventType, KeyEvent, MouseEvent, Position, Screen
from tx2tx.input.backend import DisplayBackend, InputCapturer, InputEvent, InputInjector
from tx2tx.wayland.gnome_pointer import GnomePointerProvider
from tx2tx.wayland.helper import WaylandHelperClient
from tx2tx.wayland.keysym_mapping import keysymFromEvdevKeycode_get

logger = logging.getLogger(__name__)


def _keysym_from_evdev(keycode: int) -> Optional[int]:
    """
    Best-effort mapping from evdev keycode to X11 keysym.

    Args:
        keycode: evdev keycode

    Returns:
        X11 keysym integer or None if unknown.
    """
    return keysymFromEvdevKeycode_get(keycode)


class WaylandDisplayBackend(DisplayBackend):
    """Display backend backed by a privileged Wayland helper."""

    def __init__(
        self,
        helper_command: Optional[str],
        screen_width: Optional[int],
        screen_height: Optional[int],
        pointer_provider: str = "helper",
    ) -> None:
        """
        Initialize Wayland display backend.
        
        Args:
            helper_command: helper_command value.
            screen_width: screen_width value.
            screen_height: screen_height value.
            pointer_provider: pointer_provider value.
        
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
        self._pointer_provider: str = pointer_provider
        self._gnome_pointer_provider: Optional[GnomePointerProvider] = None
        self._cursor_hide_unsupported_warned: bool = False
        if pointer_provider == "gnome":
            self._gnome_pointer_provider = GnomePointerProvider()
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
        if self._gnome_pointer_provider is not None:
            try:
                x, y = self._gnome_pointer_provider.pointerPosition_get()
                return Position(x=x, y=y)
            except Exception as error:
                self._gnome_pointer_provider.fallback_log(error)

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
        result: dict[str, Any] = self._helper.pointer_grab()
        effective_grabbed: int = int(result.get("grabbed", 0)) + int(
            result.get("already_grabbed", 0)
        )
        logger.info(
            "Wayland pointer grab: grabbed=%s already_grabbed=%s failed=%s grabbed_devices=%s already_grabbed_devices=%s failed_devices=%s",
            result.get("grabbed", 0),
            result.get("already_grabbed", 0),
            result.get("failed", 0),
            result.get("grabbed_devices", []),
            result.get("already_grabbed_devices", []),
            result.get("failed_devices", []),
        )
        if effective_grabbed == 0:
            logger.warning(
                "Wayland pointer grab did not capture any devices (failed=%s).",
                result.get("failed", 0),
            )

    def pointer_ungrab(self) -> None:
        """
        Release pointer grab via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release pointer grab via helper."""
        _ = self._helper.pointer_ungrab()

    def keyboard_grab(self) -> None:
        """
        Grab keyboard via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab keyboard via helper."""
        result: dict[str, Any] = self._helper.keyboard_grab()
        if int(result.get("required_failed", 0)) > 0:
            logger.warning(
                "Wayland keyboard grab missing required devices %s; restarting helper and retrying once",
                result.get("required_failed_devices", []),
            )
            self._helper.connection_restart()
            result = self._helper.keyboard_grab()

        effective_grabbed: int = int(result.get("grabbed", 0)) + int(
            result.get("already_grabbed", 0)
        )
        logger.info(
            "Wayland keyboard grab: grabbed=%s already_grabbed=%s failed=%s typing_grabbed=%s required_failed=%s grabbed_devices=%s already_grabbed_devices=%s failed_devices=%s required_failed_devices=%s",
            result.get("grabbed", 0),
            result.get("already_grabbed", 0),
            result.get("failed", 0),
            result.get("typing_grabbed", 0),
            result.get("required_failed", 0),
            result.get("grabbed_devices", []),
            result.get("already_grabbed_devices", []),
            result.get("failed_devices", []),
            result.get("required_failed_devices", []),
        )
        if int(result.get("required_failed", 0)) > 0:
            raise RuntimeError(
                "Wayland keyboard grab failed on required typing keyboard device(s): "
                f"{result.get('required_failed_devices', [])}. "
                "Refusing REMOTE mode to prevent local-only keystrokes."
            )
        if int(result.get("typing_grabbed", 0)) <= 0:
            raise RuntimeError(
                "Wayland keyboard grab captured zero typing keyboards. "
                "Refusing REMOTE mode to prevent local-only keystrokes."
            )
        if effective_grabbed == 0:
            message: str = (
                "Wayland keyboard grab did not capture any devices (failed=%s). "
                "Keystrokes may still execute on the server."
            )
            logger.error(message, result.get("failed", 0))
            raise RuntimeError(
                "Wayland keyboard exclusive grab failed; refusing REMOTE mode without keyboard capture."
            )

    def keyboard_ungrab(self) -> None:
        """
        Release keyboard grab via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release keyboard grab via helper."""
        _ = self._helper.keyboard_ungrab()

    def cursor_hide(self) -> None:
        """
        Hide cursor via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Hide cursor via helper."""
        supported: bool = self._helper.cursor_hide()
        if not supported and not self._cursor_hide_unsupported_warned:
            logger.warning(
                "Wayland helper does not implement cursor hide/show; "
                "server-side ghost cursor may remain visible in REMOTE mode."
            )
            self._cursor_hide_unsupported_warned = True

    def cursor_show(self) -> None:
        """
        Show cursor via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Show cursor via helper."""
        _ = self._helper.cursor_show()

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
            event_type: Optional[str] = event.get("event_type")
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
                linux_keycode: int = int(event["keycode"])
                x11_keycode: int = linux_keycode + 8
                keysym: Optional[int] = (
                    int(event["keysym"]) if event.get("keysym") is not None else None
                )
                if keysym is None:
                    keysym = _keysym_from_evdev(linux_keycode)
                if keysym is None and not (8 <= x11_keycode <= 255):
                    logger.debug(
                        "Skipping unsupported Wayland key press: linux_keycode=%s x11_keycode=%s",
                        linux_keycode,
                        x11_keycode,
                    )
                    continue
                events.append(
                    KeyEvent(
                        event_type=EventType.KEY_PRESS,
                        keycode=x11_keycode,
                        keysym=keysym,
                        state=(
                            int(event["state"]) if event.get("state") is not None else None
                        ),
                    )
                )
            elif event_type == EventType.KEY_RELEASE.value:
                linux_keycode: int = int(event["keycode"])
                x11_keycode: int = linux_keycode + 8
                keysym: Optional[int] = (
                    int(event["keysym"]) if event.get("keysym") is not None else None
                )
                if keysym is None:
                    keysym = _keysym_from_evdev(linux_keycode)
                if keysym is None and not (8 <= x11_keycode <= 255):
                    logger.debug(
                        "Skipping unsupported Wayland key release: linux_keycode=%s x11_keycode=%s",
                        linux_keycode,
                        x11_keycode,
                    )
                    continue
                events.append(
                    KeyEvent(
                        event_type=EventType.KEY_RELEASE,
                        keycode=x11_keycode,
                        keysym=keysym,
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
