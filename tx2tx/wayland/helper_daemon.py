"""Privileged Wayland helper daemon using evdev/uinput."""

from __future__ import annotations

import json
import os
import select
import sys
import threading
from dataclasses import dataclass
from typing import Any, Optional

from evdev import AbsInfo, InputDevice, UInput, ecodes

from tx2tx.common.types import EventType


class _PointerProvider:
    """Optional GNOME pointer provider via DBus."""

    def position_get(self) -> Optional[tuple[int, int]]:
        raise NotImplementedError

    @staticmethod
    def create() -> Optional["_PointerProvider"]:
        """
        Create a pointer provider if GNOME DBus is available and enabled.

        Returns:
            Provider instance or None.
        """
        if os.environ.get("TX2TX_GNOME_POINTER", "").lower() not in {"1", "true", "yes"}:
            return None
        try:
            from gi.repository import Gio
        except Exception:
            return None

        class _GNOMEProvider(_PointerProvider):
            def __init__(self) -> None:
                self._proxy = Gio.DBusProxy.new_for_bus_sync(
                    Gio.BusType.SESSION,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    "org.tx2tx.Pointer",
                    "/org/tx2tx/Pointer",
                    "org.tx2tx.Pointer",
                    None,
                )

            def position_get(self) -> Optional[tuple[int, int]]:
                try:
                    result = self._proxy.call_sync(
                        "GetPointer",
                        None,
                        Gio.DBusCallFlags.NONE,
                        100,
                        None,
                    )
                    x, y = result.unpack()
                    return int(x), int(y)
                except Exception:
                    return None

        return _GNOMEProvider()


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
        self._devices: list[InputDevice] = []
        self._pointer_state = PointerState(width=width, height=height)
        self._modifier_state = ModifierState()
        self._events: list[InputEventRecord] = []
        self._lock = threading.Lock()

        self._devices = self._devices_open(device_paths)
        self._mouse_devices = [d for d in self._devices if self._device_is_mouse(d)]
        self._keyboard_devices = [d for d in self._devices if self._device_is_keyboard(d)]

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
        with self._lock:
            events = [record.payload for record in self._events]
            self._events.clear()
        return events, self._modifier_state.mask_get()

    def pointer_grab(self) -> None:
        """Grab pointer devices to capture mouse input exclusively."""
        for dev in self._mouse_devices:
            dev.grab()

    def pointer_ungrab(self) -> None:
        """Release pointer device grabs."""
        for dev in self._mouse_devices:
            dev.ungrab()

    def keyboard_grab(self) -> None:
        """Grab keyboard devices to capture keyboard input exclusively."""
        for dev in self._keyboard_devices:
            dev.grab()

    def keyboard_ungrab(self) -> None:
        """Release keyboard device grabs."""
        for dev in self._keyboard_devices:
            dev.ungrab()

    def _devices_open(self, device_paths: Optional[list[str]]) -> list[InputDevice]:
        """
        Open input devices.

        Args:
            device_paths: Optional list of device paths

        Returns:
            List of opened input devices.
        """
        devices: list[InputDevice] = []
        paths = device_paths or [os.path.join("/dev/input", d) for d in os.listdir("/dev/input") if d.startswith("event")]
        for path in paths:
            try:
                dev = InputDevice(path)
                devices.append(dev)
            except Exception:
                continue
        return devices

    def _device_is_keyboard(self, device: InputDevice) -> bool:
        """
        Check if device is a keyboard.

        Args:
            device: Input device to inspect

        Returns:
            True if device looks like a keyboard.
        """
        caps = device.capabilities().get(ecodes.EV_KEY, [])
        return ecodes.KEY_A in caps or ecodes.KEY_Q in caps

    def _device_is_mouse(self, device: InputDevice) -> bool:
        """
        Check if device is a mouse/pointer.

        Args:
            device: Input device to inspect

        Returns:
            True if device looks like a mouse.
        """
        caps = device.capabilities()
        if ecodes.EV_REL in caps and (ecodes.REL_X in caps[ecodes.EV_REL] or ecodes.REL_Y in caps[ecodes.EV_REL]):
            return True
        keys = caps.get(ecodes.EV_KEY, [])
        return ecodes.BTN_LEFT in keys or ecodes.BTN_RIGHT in keys

    def _events_loop(self) -> None:
        """Background loop to read input events."""
        while True:
            if not self._devices:
                return
            rlist, _, _ = select.select(self._devices, [], [], 0.1)
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
            event: evdev input event
        """
        if event.type == ecodes.EV_REL:
            if event.code == ecodes.REL_X:
                self._pointer_state.update_rel(event.value, 0)
            elif event.code == ecodes.REL_Y:
                self._pointer_state.update_rel(0, event.value)
            return

        if event.type == ecodes.EV_ABS:
            self._abs_event_handle(device, event)
            return

        if event.type == ecodes.EV_KEY:
            x, y = self._pointer_state.position_get()
            if event.code in (ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE, ecodes.BTN_SIDE, ecodes.BTN_EXTRA):
                event_type = EventType.MOUSE_BUTTON_PRESS.value if event.value else EventType.MOUSE_BUTTON_RELEASE.value
                payload = {
                    "event_type": event_type,
                    "x": x,
                    "y": y,
                    "button": self._button_map(event.code),
                }
                self._event_record(payload)
            else:
                pressed = event.value == 1
                self._modifier_state.update(event.code, pressed)
                event_type = EventType.KEY_PRESS.value if pressed else EventType.KEY_RELEASE.value
                payload = {
                    "event_type": event_type,
                    "keycode": event.code,
                    "keysym": None,
                    "state": self._modifier_state.mask_get(),
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
        with self._lock:
            self._events.append(InputEventRecord(event_type=payload["event_type"], payload=payload))

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
        self._width = width
        self._height = height
        self._device_manager = InputDeviceManager(device_paths=devices, width=width, height=height)
        self._uinput = UInputManager(width=width, height=height)
        self._pointer_provider = _PointerProvider.create()

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
        if cmd == "hello":
            return {"version": "0.1.0"}
        if cmd == "screen_geometry_get":
            width, height = self._screen_geometry_get()
            return {"width": width, "height": height}
        if cmd == "pointer_position_get":
            x, y = self._pointer_position_get()
            return {"x": x, "y": y}
        if cmd == "cursor_position_set":
            x = int(payload["x"])
            y = int(payload["y"])
            self._device_manager.pointerPosition_set(x, y)
            self._uinput.mouse_move(x=x, y=y)
            return {}
        if cmd == "pointer_grab":
            self._device_manager.pointer_grab()
            return {}
        if cmd == "pointer_ungrab":
            self._device_manager.pointer_ungrab()
            return {}
        if cmd == "keyboard_grab":
            self._device_manager.keyboard_grab()
            return {}
        if cmd == "keyboard_ungrab":
            self._device_manager.keyboard_ungrab()
            return {}
        if cmd == "cursor_hide":
            return {}
        if cmd == "cursor_show":
            return {}
        if cmd == "input_events_read":
            events, modifier_state = self._device_manager.inputEvents_read()
            return {"events": events, "modifier_state": modifier_state}
        if cmd == "inject_mouse":
            self._inject_mouse(payload)
            return {}
        if cmd == "inject_key":
            self._inject_key(payload)
            return {}
        if cmd == "session_is_native":
            return {"native": False}
        if cmd == "sync":
            return {}
        if cmd == "shutdown":
            sys.exit(0)
        raise ValueError(f"Unknown command: {cmd}")

    def _pointer_position_get(self) -> tuple[int, int]:
        """
        Get current pointer position, preferring GNOME provider when available.

        Returns:
            Tuple of (x, y).
        """
        if self._pointer_provider is not None:
            provider_pos = self._pointer_provider.position_get()
            if provider_pos is not None:
                self._device_manager.pointerPosition_set(*provider_pos)
                return provider_pos
        return self._device_manager.pointerPosition_get()

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
