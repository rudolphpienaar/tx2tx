"""Wayland helper device component primitives."""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

from evdev import InputDevice, ecodes


class DeviceRegistry:
    """Discovers and classifies evdev devices for helper usage."""

    def __init__(self, device_paths: Optional[list[str]]) -> None:
        """
        Initialize and classify input devices.

        Args:
            device_paths: Optional explicit device paths.
        """
        self._devices: list[InputDevice] = self._devices_open(device_paths)
        self._mouse_devices: list[InputDevice] = [
            device for device in self._devices if self._deviceIsMouse_check(device)
        ]
        self._keyboard_devices: list[InputDevice] = [
            device for device in self._devices if ecodes.EV_KEY in device.capabilities()
        ]
        self._mouse_fds: set[int] = {device.fd for device in self._mouse_devices}
        self._keyboard_fds: set[int] = {device.fd for device in self._keyboard_devices}
        self._path_by_fd: dict[int, str] = {device.fd: device.path for device in self._devices}

    def devices_all(self) -> list[InputDevice]:
        """Return all tracked devices."""
        return self._devices

    def devices_mouse(self) -> list[InputDevice]:
        """Return pointer-class devices."""
        return self._mouse_devices

    def devices_keyboard(self) -> list[InputDevice]:
        """Return keyboard-class devices."""
        return self._keyboard_devices

    def mouseFds_get(self) -> set[int]:
        """Return mouse device file descriptors."""
        return self._mouse_fds

    def keyboardFds_get(self) -> set[int]:
        """Return keyboard device file descriptors."""
        return self._keyboard_fds

    def pathForFd_get(self, fd: int) -> str:
        """
        Resolve device path for fd.

        Args:
            fd: Device file descriptor.

        Returns:
            Device path or 'unknown'.
        """
        return self._path_by_fd.get(fd, "unknown")

    def _devices_open(self, device_paths: Optional[list[str]]) -> list[InputDevice]:
        """
        Open evdev devices.

        Args:
            device_paths: Optional explicit device paths.

        Returns:
            Opened devices.
        """
        paths: list[str]
        if device_paths is None:
            paths = [
                os.path.join("/dev/input", entry)
                for entry in os.listdir("/dev/input")
                if entry.startswith("event")
            ]
        else:
            paths = device_paths

        devices: list[InputDevice] = []
        for path in paths:
            try:
                devices.append(InputDevice(path))
            except Exception:
                continue
        return devices

    def _deviceIsMouse_check(self, device: InputDevice) -> bool:
        """
        Determine whether device is pointer-like.

        Args:
            device: Input device.

        Returns:
            True when device has pointer characteristics.
        """
        capabilities: dict[int, Any] = device.capabilities()
        rel_caps = capabilities.get(ecodes.EV_REL, [])
        if ecodes.REL_X in rel_caps or ecodes.REL_Y in rel_caps:
            return True
        key_caps = capabilities.get(ecodes.EV_KEY, [])
        return ecodes.BTN_LEFT in key_caps or ecodes.BTN_RIGHT in key_caps


class GrabRefCounter:
    """Tracks exclusive grab reference counts per device fd."""

    def __init__(self, registry: DeviceRegistry) -> None:
        """
        Initialize grab tracker.

        Args:
            registry: Device registry.
        """
        self._registry: DeviceRegistry = registry
        self._refcount_by_fd: dict[int, int] = {}

    def grab_apply(self, device: InputDevice) -> tuple[str, str]:
        """
        Apply refcounted grab.

        Args:
            device: Device to grab.

        Returns:
            Tuple of (status, device_path).
        """
        fd: int = device.fd
        path: str = self._registry.pathForFd_get(fd)
        current_count: int = self._refcount_by_fd.get(fd, 0)
        if current_count > 0:
            self._refcount_by_fd[fd] = current_count + 1
            return "already_grabbed", path
        try:
            device.grab()
            self._refcount_by_fd[fd] = 1
            return "grabbed", path
        except Exception:
            return "failed", path

    def ungrab_apply(self, device: InputDevice) -> tuple[str, str]:
        """
        Apply refcounted ungrab.

        Args:
            device: Device to ungrab.

        Returns:
            Tuple of (status, device_path).
        """
        fd: int = device.fd
        path: str = self._registry.pathForFd_get(fd)
        current_count: int = self._refcount_by_fd.get(fd, 0)
        if current_count <= 0:
            return "failed", path
        if current_count > 1:
            self._refcount_by_fd[fd] = current_count - 1
            return "deferred", path
        try:
            device.ungrab()
            self._refcount_by_fd.pop(fd, None)
            return "released", path
        except Exception:
            return "failed", path

    def grabbed_check(self, fd: int) -> bool:
        """
        Check whether a device fd is currently grabbed.

        Args:
            fd: Device file descriptor.

        Returns:
            True when refcount indicates an active grab.
        """
        return self._refcount_by_fd.get(fd, 0) > 0


class InputEventQueue:
    """Thread-safe queue of helper event payloads."""

    def __init__(self) -> None:
        """Initialize queue."""
        self._lock: threading.Lock = threading.Lock()
        self._events: list[dict[str, Any]] = []

    def event_add(self, payload: dict[str, Any]) -> None:
        """
        Append an event payload.

        Args:
            payload: Event payload.
        """
        with self._lock:
            self._events.append(payload)

    def events_drain(self) -> list[dict[str, Any]]:
        """
        Drain all queued payloads.

        Returns:
            Collected payload list.
        """
        with self._lock:
            events: list[dict[str, Any]] = list(self._events)
            self._events.clear()
        return events
