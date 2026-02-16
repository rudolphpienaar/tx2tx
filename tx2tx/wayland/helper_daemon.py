"""Privileged Wayland helper daemon using evdev/uinput."""

from __future__ import annotations

import json
import select
import sys
import threading
from dataclasses import dataclass
from typing import Any, Optional

from evdev import AbsInfo, InputDevice, UInput, ecodes

from tx2tx.common.types import EventType
from tx2tx.wayland.device_components import DeviceRegistry, GrabRefCounter, InputEventQueue


@dataclass
class InputEventRecord:
    """Captured input event record."""

    event_type: str
    payload: dict[str, Any]


class ModifierState:
    """Tracks modifier key state for masking."""

    def __init__(self) -> None:
        """Initialize modifier state tracker."""
        self._pressed: set[int] = set()

    def update(self, keycode: int, pressed: bool) -> None:
        """
        Update modifier state for a keycode.

        Args:
            keycode: Key code from evdev
            pressed: True if key is pressed, False if released
        """
        if pressed:
            self._pressed.add(keycode)
        else:
            self._pressed.discard(keycode)

    def mask_get(self) -> int:
        """
        Get X11-style modifier mask.

        Returns:
            Modifier bitmask.
        """
        mask = 0
        if ecodes.KEY_LEFTSHIFT in self._pressed or ecodes.KEY_RIGHTSHIFT in self._pressed:
            mask |= 0x1
        if ecodes.KEY_LEFTCTRL in self._pressed or ecodes.KEY_RIGHTCTRL in self._pressed:
            mask |= 0x4
        if ecodes.KEY_LEFTALT in self._pressed or ecodes.KEY_RIGHTALT in self._pressed:
            mask |= 0x8
        if ecodes.KEY_LEFTMETA in self._pressed or ecodes.KEY_RIGHTMETA in self._pressed:
            mask |= 0x40
        return mask

    def state_reset(self) -> None:
        """
        Reset tracked modifier state.

        Returns:
            None.
        """
        self._pressed.clear()


class PointerState:
    """Tracks pointer position based on relative events."""

    def __init__(self, width: Optional[int], height: Optional[int]) -> None:
        """
        Initialize pointer state.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
        """
        self._width: Optional[int] = width
        self._height: Optional[int] = height
        self._x: int = width // 2 if width else 0
        self._y: int = height // 2 if height else 0

    def update_rel(self, dx: int, dy: int) -> None:
        """
        Update pointer position using relative deltas.

        Args:
            dx: Relative x delta
            dy: Relative y delta
        """
        self._x += dx
        self._y += dy
        self._clamp()

    def position_get(self) -> tuple[int, int]:
        """
        Return current pointer position.

        Returns:
            Tuple of (x, y).
        """
        return self._x, self._y

    def position_set(self, x: int, y: int) -> None:
        """
        Set pointer position.

        Args:
            x: Absolute x position
            y: Absolute y position
        """
        self._x = x
        self._y = y
        self._clamp()

    def _clamp(self) -> None:
        """Clamp pointer position within screen bounds if known."""
        if self._width is not None:
            self._x = max(0, min(self._x, self._width - 1))
        if self._height is not None:
            self._y = max(0, min(self._y, self._height - 1))


class InputDeviceManager:
    """Manages evdev device capture and event reading."""

    def __init__(self, device_paths: Optional[list[str]], width: Optional[int], height: Optional[int]) -> None:
        """
        Initialize input device manager.

        Args:
            device_paths: Optional list of device paths to open
            width: Screen width in pixels
            height: Screen height in pixels
        """
        self._pointer_state = PointerState(width=width, height=height)
        self._modifier_state = ModifierState()
        self._event_queue: InputEventQueue = InputEventQueue(max_events=8192)
        self._registry: DeviceRegistry = DeviceRegistry(device_paths)
        self._grab_refcounter: GrabRefCounter = GrabRefCounter(self._registry)

        self._reader = threading.Thread(target=self._events_loop, daemon=True)
        self._reader.start()

    def pointerPosition_get(self) -> tuple[int, int]:
        """
        Get current pointer position.

        Returns:
            Tuple of (x, y).
        """
        return self._pointer_state.position_get()

    def pointerPosition_set(self, x: int, y: int) -> None:
        """
        Set current pointer position.

        Args:
            x: Absolute x position
            y: Absolute y position
        """
        self._pointer_state.position_set(x, y)

    def inputEvents_read(self) -> tuple[list[dict[str, Any]], int]:
        """
        Return captured events and modifier state.

        Returns:
            Tuple of (event_list, modifier_state).
        """
        events: list[dict[str, Any]] = self._event_queue.events_drain()
        return events, self._modifier_state.mask_get()

    def pointer_grab(self) -> dict[str, Any]:
        """
        Grab pointer devices to capture mouse input exclusively.

        Returns:
            Dictionary containing grab counts and device paths.
        """
        self._event_queue.events_clear()
        self._modifier_state.state_reset()
        grabbed: int = 0
        already_grabbed: int = 0
        failed: int = 0
        grabbed_devices: list[str] = []
        already_grabbed_devices: list[str] = []
        failed_devices: list[str] = []
        for dev in self._registry.devices_mouse():
            status: str
            device_path: str
            status, device_path = self._grab_refcounter.grab_apply(dev)
            if status == "grabbed":
                grabbed += 1
                grabbed_devices.append(device_path)
            elif status == "already_grabbed":
                already_grabbed += 1
                already_grabbed_devices.append(device_path)
            else:
                failed += 1
                failed_devices.append(device_path)
        return {
            "grabbed": grabbed,
            "already_grabbed": already_grabbed,
            "failed": failed,
            "grabbed_devices": grabbed_devices,
            "already_grabbed_devices": already_grabbed_devices,
            "failed_devices": failed_devices,
        }

    def pointer_ungrab(self) -> dict[str, Any]:
        """
        Release pointer device grabs.

        Returns:
            Dictionary containing release counts and device paths.
        """
        released: int = 0
        deferred_release: int = 0
        failed: int = 0
        released_devices: list[str] = []
        deferred_release_devices: list[str] = []
        failed_devices: list[str] = []
        for dev in self._registry.devices_mouse():
            status: str
            device_path: str
            status, device_path = self._grab_refcounter.ungrab_apply(dev)
            if status == "released":
                released += 1
                released_devices.append(device_path)
            elif status == "deferred":
                deferred_release += 1
                deferred_release_devices.append(device_path)
            else:
                failed += 1
                failed_devices.append(device_path)
        return {
            "released": released,
            "deferred_release": deferred_release,
            "failed": failed,
            "released_devices": released_devices,
            "deferred_release_devices": deferred_release_devices,
            "failed_devices": failed_devices,
        }

    def keyboard_grab(self) -> dict[str, Any]:
        """
        Grab keyboard devices to capture keyboard input exclusively.

        Returns:
            Dictionary containing grab counts and device paths.
        """
        self._event_queue.events_clear()
        self._modifier_state.state_reset()
        grabbed: int = 0
        already_grabbed: int = 0
        failed: int = 0
        required_failed: int = 0
        grabbed_devices: list[str] = []
        already_grabbed_devices: list[str] = []
        failed_devices: list[str] = []
        required_failed_devices: list[str] = []
        typing_keyboard_fds: set[int] = self._registry.typingKeyboardFds_get()
        for dev in self._registry.devices_keyboard():
            status: str
            device_path: str
            status, device_path = self._grab_refcounter.grab_apply(dev)
            if status == "grabbed":
                grabbed += 1
                grabbed_devices.append(device_path)
            elif status == "already_grabbed":
                already_grabbed += 1
                already_grabbed_devices.append(device_path)
            else:
                failed += 1
                failed_devices.append(device_path)
                if dev.fd in typing_keyboard_fds:
                    required_failed += 1
                    required_failed_devices.append(device_path)
        return {
            "grabbed": grabbed,
            "already_grabbed": already_grabbed,
            "failed": failed,
            "grabbed_devices": grabbed_devices,
            "already_grabbed_devices": already_grabbed_devices,
            "failed_devices": failed_devices,
            "required_failed": required_failed,
            "required_failed_devices": required_failed_devices,
        }

    def keyboard_ungrab(self) -> dict[str, Any]:
        """
        Release keyboard device grabs.

        Returns:
            Dictionary containing release counts and device paths.
        """
        released: int = 0
        deferred_release: int = 0
        failed: int = 0
        released_devices: list[str] = []
        deferred_release_devices: list[str] = []
        failed_devices: list[str] = []
        for dev in self._registry.devices_keyboard():
            status: str
            device_path: str
            status, device_path = self._grab_refcounter.ungrab_apply(dev)
            if status == "released":
                released += 1
                released_devices.append(device_path)
            elif status == "deferred":
                deferred_release += 1
                deferred_release_devices.append(device_path)
            else:
                failed += 1
                failed_devices.append(device_path)
        return {
            "released": released,
            "deferred_release": deferred_release,
            "failed": failed,
            "released_devices": released_devices,
            "deferred_release_devices": deferred_release_devices,
            "failed_devices": failed_devices,
        }

    def _events_loop(self) -> None:
        """Background loop to read input events."""
        while True:
            devices: list[InputDevice] = self._registry.devices_all()
            if not devices:
                return
            rlist, _, _ = select.select(devices, [], [], 0.1)
            for dev in rlist:
                try:
                    for event in dev.read():
                        self._event_handle(dev, event)
                except Exception:
                    continue

    def _event_handle(self, device: InputDevice, event) -> None:
        """
        Handle a single evdev event.

        Args:
            device: evdev input device emitting the event.
            event: evdev input event
        """
        is_mouse_device: bool = device.fd in self._registry.mouseFds_get()
        is_keyboard_device: bool = device.fd in self._registry.keyboardFds_get()

        if event.type == ecodes.EV_REL:
            if not is_mouse_device:
                return
            if event.code == ecodes.REL_X:
                self._pointer_state.update_rel(event.value, 0)
            elif event.code == ecodes.REL_Y:
                self._pointer_state.update_rel(0, event.value)
            return

        if event.type == ecodes.EV_ABS:
            if not is_mouse_device:
                return
            self._abs_event_handle(device, event)
            return

        if event.type == ecodes.EV_KEY:
            x: int
            y: int
            x, y = self._pointer_state.position_get()
            is_mouse_button: bool = event.code in (
                ecodes.BTN_LEFT,
                ecodes.BTN_RIGHT,
                ecodes.BTN_MIDDLE,
                ecodes.BTN_SIDE,
                ecodes.BTN_EXTRA,
            )

            # Mouse buttons: only from pointer-class devices.
            if is_mouse_button and is_mouse_device:
                event_type: str = (
                    EventType.MOUSE_BUTTON_PRESS.value
                    if event.value
                    else EventType.MOUSE_BUTTON_RELEASE.value
                )
                device_path: str = self._registry.pathForFd_get(device.fd)
                payload: dict[str, Any] = {
                    "event_type": event_type,
                    "x": x,
                    "y": y,
                    "button": self._button_map(event.code),
                    "source_device": device_path,
                }
                self._event_record(payload)
                return

            if not is_keyboard_device:
                return

            # Treat KEY_* codes (< BTN_MISC) as keyboard events even if device
            # classification is imperfect (common on mixed/virtual devices).
            if event.code >= ecodes.BTN_MISC:
                return

            # Ignore auto-repeat notifications (value=2) to prevent phantom
            # repeat bursts on transition into REMOTE mode.
            if event.value == 2:
                return

            pressed: bool = event.value == 1
            self._modifier_state.update(event.code, pressed)
            event_type: str = EventType.KEY_PRESS.value if pressed else EventType.KEY_RELEASE.value
            device_path = self._registry.pathForFd_get(device.fd)
            payload: dict[str, Any] = {
                "event_type": event_type,
                "keycode": event.code,
                "keysym": None,
                "state": self._modifier_state.mask_get(),
                "source_device": device_path,
            }
            self._event_record(payload)

    def _abs_event_handle(self, device: InputDevice, event) -> None:
        """
        Handle absolute pointer events (touchpads/tablets).

        Args:
            device: Input device emitting the event
            event: evdev input event
        """
        if event.code not in (ecodes.ABS_X, ecodes.ABS_Y):
            return

        width = self._pointer_state._width
        height = self._pointer_state._height
        if width is None or height is None:
            return

        absinfo = device.absinfo(event.code)
        if absinfo is None or absinfo.max == absinfo.min:
            return

        if event.code == ecodes.ABS_X:
            x = int((event.value - absinfo.min) * (width - 1) / (absinfo.max - absinfo.min))
            _, y = self._pointer_state.position_get()
            self._pointer_state.position_set(x, y)
        else:
            y = int((event.value - absinfo.min) * (height - 1) / (absinfo.max - absinfo.min))
            x, _ = self._pointer_state.position_get()
            self._pointer_state.position_set(x, y)

    def _event_record(self, payload: dict[str, Any]) -> None:
        """
        Append an event payload to the queue.

        Args:
            payload: Event payload dictionary
        """
        self._event_queue.event_add(payload)

    def _button_map(self, code: int) -> int:
        """
        Map evdev button codes to X11-style button numbers.

        Args:
            code: evdev button code

        Returns:
            Button number (1=left, 2=middle, 3=right, 4/5=wheel, 8/9=side).
        """
        mapping = {
            ecodes.BTN_LEFT: 1,
            ecodes.BTN_MIDDLE: 2,
            ecodes.BTN_RIGHT: 3,
            ecodes.BTN_SIDE: 8,
            ecodes.BTN_EXTRA: 9,
        }
        return mapping.get(code, 1)


class UInputManager:
    """Manages uinput devices for injection."""

    def __init__(self, width: Optional[int], height: Optional[int]) -> None:
        """
        Initialize uinput devices.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
        """
        self._width = width
        self._height = height
        self._keyboard = self._keyboard_create()
        self._mouse = self._mouse_create()

    def mouse_move(self, x: Optional[int], y: Optional[int], dx: int = 0, dy: int = 0) -> None:
        """
        Inject mouse movement.

        Args:
            x: Absolute x position
            y: Absolute y position
            dx: Relative x delta
            dy: Relative y delta
        """
        if x is not None and y is not None and self._mouse_supports_abs:
            self._mouse.write(ecodes.EV_ABS, ecodes.ABS_X, x)
            self._mouse.write(ecodes.EV_ABS, ecodes.ABS_Y, y)
        else:
            if dx != 0:
                self._mouse.write(ecodes.EV_REL, ecodes.REL_X, dx)
            if dy != 0:
                self._mouse.write(ecodes.EV_REL, ecodes.REL_Y, dy)
        self._mouse.syn()

    def mouse_button(self, button: int, pressed: bool) -> None:
        """
        Inject mouse button event.

        Args:
            button: Button number (1=left, 2=middle, 3=right)
            pressed: True for press, False for release
        """
        code = {
            1: ecodes.BTN_LEFT,
            2: ecodes.BTN_MIDDLE,
            3: ecodes.BTN_RIGHT,
            8: ecodes.BTN_SIDE,
            9: ecodes.BTN_EXTRA,
        }.get(button, ecodes.BTN_LEFT)
        self._mouse.write(ecodes.EV_KEY, code, 1 if pressed else 0)
        self._mouse.syn()

    def key(self, keycode: int, pressed: bool) -> None:
        """
        Inject keyboard event.

        Args:
            keycode: Keycode to inject
            pressed: True for press, False for release
        """
        self._keyboard.write(ecodes.EV_KEY, keycode, 1 if pressed else 0)
        self._keyboard.syn()

    def _keyboard_create(self) -> UInput:
        """
        Create uinput keyboard device.

        Returns:
            UInput keyboard device.
        """
        key_codes = sorted(self._keycodes_collect())
        capabilities = {ecodes.EV_KEY: key_codes}
        return UInput(capabilities, name="tx2tx-virtual-keyboard")

    def _keycodes_collect(self) -> list[int]:
        """
        Collect integer keycodes from evdev mappings.

        Returns:
            Sorted list of integer key codes.
        """
        codes: set[int] = set()
        for value in ecodes.keys.values():
            if isinstance(value, int):
                codes.add(value)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, int):
                        codes.add(item)
        return sorted(codes)

    def _mouse_create(self) -> UInput:
        """
        Create uinput mouse device.

        Returns:
            UInput mouse device.
        """
        capabilities = {
            ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_MIDDLE, ecodes.BTN_RIGHT, ecodes.BTN_SIDE, ecodes.BTN_EXTRA],
            ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL, ecodes.REL_HWHEEL],
        }
        abs_caps = None
        if self._width is not None and self._height is not None:
            abs_caps = [
                (ecodes.ABS_X, AbsInfo(value=0, min=0, max=self._width - 1, fuzz=0, flat=0, resolution=0)),
                (ecodes.ABS_Y, AbsInfo(value=0, min=0, max=self._height - 1, fuzz=0, flat=0, resolution=0)),
            ]
            capabilities[ecodes.EV_ABS] = abs_caps
        self._mouse_supports_abs = abs_caps is not None
        return UInput(capabilities, name="tx2tx-virtual-mouse")


class WaylandHelperDaemon:
    """Main helper daemon implementing the JSON command protocol."""

    def __init__(self, width: Optional[int], height: Optional[int], devices: Optional[list[str]]) -> None:
        """
        Initialize helper daemon.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
            devices: Optional list of device paths
        """
        resolved_width: Optional[int]
        resolved_height: Optional[int]
        resolved_width, resolved_height = self._screenGeometryWithFallback_resolve(width, height)
        self._width = resolved_width
        self._height = resolved_height
        self._device_manager = InputDeviceManager(
            device_paths=devices, width=resolved_width, height=resolved_height
        )
        self._uinput = UInputManager(width=resolved_width, height=resolved_height)
        self._command_handlers = self._commandHandlers_get()

    def _screenGeometryWithFallback_resolve(
        self, width: Optional[int], height: Optional[int]
    ) -> tuple[Optional[int], Optional[int]]:
        """
        Resolve startup geometry with fb0 fallback.

        Args:
            width: Optional explicit width.
            height: Optional explicit height.

        Returns:
            Tuple of resolved `(width, height)` values (possibly None when
            neither explicit nor fallback geometry is available).
        """
        if width is not None and height is not None:
            return width, height

        fallback: Optional[tuple[int, int]] = self._fb0_geometry_get()
        if fallback is None:
            return width, height

        fallback_width: int
        fallback_height: int
        fallback_width, fallback_height = fallback
        resolved_width: int = width if width is not None else fallback_width
        resolved_height: int = height if height is not None else fallback_height
        return resolved_width, resolved_height

    def run(self) -> None:
        """
        Run the command loop.

        Returns:
            None.
        """
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                cmd = request.get("cmd")
                payload = request.get("payload", {})
                result = self._command_handle(cmd, payload)
                self._respond_ok(result)
            except Exception as e:
                self._respond_error(str(e))

    def _command_handle(self, cmd: str, payload: dict[str, Any]) -> Any:
        """
        Execute a command and return its result.

        Args:
            cmd: Command name
            payload: Command payload

        Returns:
            Command result payload.
        """
        command_handler = self._command_handlers.get(cmd)
        if command_handler is None:
            raise ValueError(f"Unknown command: {cmd}")
        return command_handler(payload)

    def _commandHandlers_get(self) -> dict[str, Any]:
        """
        Build command dispatch table for helper protocol.

        Returns:
            Mapping of command name to handler callable.
        """
        return {
            "hello": self._cmdHello_handle,
            "screen_geometry_get": self._cmdScreenGeometryGet_handle,
            "pointer_position_get": self._cmdPointerPositionGet_handle,
            "cursor_position_set": self._cmdCursorPositionSet_handle,
            "pointer_grab": self._cmdPointerGrab_handle,
            "pointer_ungrab": self._cmdPointerUngrab_handle,
            "keyboard_grab": self._cmdKeyboardGrab_handle,
            "keyboard_ungrab": self._cmdKeyboardUngrab_handle,
            "cursor_hide": self._cmdCursorHide_handle,
            "cursor_show": self._cmdCursorShow_handle,
            "input_events_read": self._cmdInputEventsRead_handle,
            "inject_mouse": self._cmdInjectMouse_handle,
            "inject_key": self._cmdInjectKey_handle,
            "session_is_native": self._cmdSessionIsNative_handle,
            "sync": self._cmdSync_handle,
            "shutdown": self._cmdShutdown_handle,
        }

    def _cmdHello_handle(self, payload: dict[str, Any]) -> dict[str, str]:
        """
        Handle helper hello command.

        Args:
            payload: Request payload.

        Returns:
            Helper version payload.
        """
        _ = payload
        return {"version": "0.1.0"}

    def _cmdScreenGeometryGet_handle(self, payload: dict[str, Any]) -> dict[str, int]:
        """
        Handle screen geometry command.

        Args:
            payload: Request payload.

        Returns:
            Width/height payload.
        """
        _ = payload
        width: int
        height: int
        width, height = self._screen_geometry_get()
        return {"width": width, "height": height}

    def _cmdPointerPositionGet_handle(self, payload: dict[str, Any]) -> dict[str, int]:
        """
        Handle pointer position query command.

        Args:
            payload: Request payload.

        Returns:
            Pointer x/y payload.
        """
        _ = payload
        x: int
        y: int
        x, y = self._device_manager.pointerPosition_get()
        return {"x": x, "y": y}

    def _cmdCursorPositionSet_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle cursor position set command.

        Args:
            payload: Request payload.

        Returns:
            Empty result payload.
        """
        x: int = int(payload["x"])
        y: int = int(payload["y"])
        self._device_manager.pointerPosition_set(x, y)
        self._uinput.mouse_move(x=x, y=y)
        return {}

    def _cmdPointerGrab_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle pointer grab command.

        Args:
            payload: Request payload.

        Returns:
            Pointer grab stats.
        """
        _ = payload
        return self._device_manager.pointer_grab()

    def _cmdPointerUngrab_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle pointer ungrab command.

        Args:
            payload: Request payload.

        Returns:
            Pointer ungrab stats.
        """
        _ = payload
        return self._device_manager.pointer_ungrab()

    def _cmdKeyboardGrab_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle keyboard grab command.

        Args:
            payload: Request payload.

        Returns:
            Keyboard grab stats.
        """
        _ = payload
        return self._device_manager.keyboard_grab()

    def _cmdKeyboardUngrab_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle keyboard ungrab command.

        Args:
            payload: Request payload.

        Returns:
            Keyboard ungrab stats.
        """
        _ = payload
        return self._device_manager.keyboard_ungrab()

    def _cmdCursorHide_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle cursor hide command.

        Args:
            payload: Request payload.

        Returns:
            Capability payload.
        """
        _ = payload
        return {
            "supported": False,
            "reason": "cursor hide/show is not implemented by this helper",
        }

    def _cmdCursorShow_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle cursor show command.

        Args:
            payload: Request payload.

        Returns:
            Capability payload.
        """
        _ = payload
        return {
            "supported": False,
            "reason": "cursor hide/show is not implemented by this helper",
        }

    def _cmdInputEventsRead_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle input events read command.

        Args:
            payload: Request payload.

        Returns:
            Event stream payload.
        """
        _ = payload
        events: list[dict[str, Any]]
        modifier_state: int
        events, modifier_state = self._device_manager.inputEvents_read()
        return {"events": events, "modifier_state": modifier_state}

    def _cmdInjectMouse_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle mouse injection command.

        Args:
            payload: Mouse injection payload.

        Returns:
            Empty result payload.
        """
        self._inject_mouse(payload)
        return {}

    def _cmdInjectKey_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle key injection command.

        Args:
            payload: Key injection payload.

        Returns:
            Empty result payload.
        """
        self._inject_key(payload)
        return {}

    def _cmdSessionIsNative_handle(self, payload: dict[str, Any]) -> dict[str, bool]:
        """
        Handle session-is-native query command.

        Args:
            payload: Request payload.

        Returns:
            Native session status payload.
        """
        _ = payload
        return {"native": False}

    def _cmdSync_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle sync command.

        Args:
            payload: Request payload.

        Returns:
            Empty result payload.
        """
        _ = payload
        return {}

    def _cmdShutdown_handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle shutdown command.

        Args:
            payload: Request payload.

        Returns:
            Unreachable empty payload.
        """
        _ = payload
        sys.exit(0)

    def _screen_geometry_get(self) -> tuple[int, int]:
        """
        Determine screen geometry from overrides or system info.

        Returns:
            Tuple of (width, height).
        """
        if self._width is not None and self._height is not None:
            return self._width, self._height

        fallback = self._fb0_geometry_get()
        if fallback is not None:
            return fallback
        raise RuntimeError("Screen geometry unavailable; set --screen-width/--screen-height")

    def _fb0_geometry_get(self) -> Optional[tuple[int, int]]:
        """
        Read screen geometry from /sys/class/graphics/fb0/virtual_size.

        Returns:
            Tuple of (width, height) if available, else None.
        """
        try:
            with open("/sys/class/graphics/fb0/virtual_size", "r") as handle:
                data = handle.read().strip()
            width_str, height_str = data.split(",")
            return int(width_str), int(height_str)
        except Exception:
            return None

    def _inject_mouse(self, payload: dict[str, Any]) -> None:
        """
        Inject mouse event through uinput.

        Args:
            payload: Mouse event payload
        """
        event_type = payload.get("event_type")
        if event_type == EventType.MOUSE_MOVE.value:
            x = payload.get("x")
            y = payload.get("y")
            self._uinput.mouse_move(x=x, y=y)
            return
        if event_type == EventType.MOUSE_BUTTON_PRESS.value:
            self._uinput.mouse_button(int(payload["button"]), True)
            return
        if event_type == EventType.MOUSE_BUTTON_RELEASE.value:
            self._uinput.mouse_button(int(payload["button"]), False)
            return
        raise ValueError(f"Unsupported mouse event: {event_type}")

    def _inject_key(self, payload: dict[str, Any]) -> None:
        """
        Inject key event through uinput.

        Args:
            payload: Key event payload
        """
        event_type = payload.get("event_type")
        keycode = int(payload["keycode"])
        if event_type == EventType.KEY_PRESS.value:
            self._uinput.key(keycode, True)
            return
        if event_type == EventType.KEY_RELEASE.value:
            self._uinput.key(keycode, False)
            return
        raise ValueError(f"Unsupported key event: {event_type}")

    def _respond_ok(self, result: Any) -> None:
        """
        Write a success response to stdout.

        Args:
            result: Result payload
        """
        response = {"ok": True, "result": result}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    def _respond_error(self, message: str) -> None:
        """
        Write an error response to stdout.

        Args:
            message: Error message
        """
        response = {"ok": False, "error": message}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def _devices_parse(value: Optional[str]) -> Optional[list[str]]:
    """
    Parse comma-separated device list.

    Args:
        value: Comma-separated device paths

    Returns:
        List of device paths or None.
    """
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def arguments_parse() -> dict[str, Any]:
    """
    Parse helper command-line arguments.

    Returns:
        Dictionary with parsed values.
    """
    args = sys.argv[1:]
    width = None
    height = None
    devices = None
    idx = 0
    while idx < len(args):
        if args[idx] == "--screen-width":
            idx += 1
            width = int(args[idx])
        elif args[idx] == "--screen-height":
            idx += 1
            height = int(args[idx])
        elif args[idx] == "--devices":
            idx += 1
            devices = _devices_parse(args[idx])
        idx += 1
    return {"width": width, "height": height, "devices": devices}


def main() -> None:
    """
    Launch the Wayland helper daemon.

    Returns:
        None.
    """
    parsed = arguments_parse()
    daemon = WaylandHelperDaemon(
        width=parsed["width"],
        height=parsed["height"],
        devices=parsed["devices"],
    )
    daemon.run()


if __name__ == "__main__":
    main()
