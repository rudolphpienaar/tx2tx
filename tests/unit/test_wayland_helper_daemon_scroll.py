"""Unit tests for Wayland helper wheel capture and injection behavior."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from typing import cast

from evdev import ecodes

from tx2tx.common.types import EventType
from tx2tx.wayland.helper_daemon import InputDeviceManager, UInputManager
from tx2tx.wayland.helper_daemon import _POINTER_SOURCE_SWITCH_IDLE_SECONDS
from tx2tx.wayland.helper_daemon import _READ_ERROR_DISABLE_THRESHOLD


class _FakeMouseDevice:
    """Fake uinput mouse device that records writes and sync calls."""

    def __init__(self) -> None:
        """Initialize fake device buffers."""
        self.writes: list[tuple[int, int, int]] = []
        self.syn_calls: int = 0

    def write(self, event_type: int, code: int, value: int) -> None:
        """Record one write operation."""
        self.writes.append((event_type, code, value))

    def syn(self) -> None:
        """Record one sync operation."""
        self.syn_calls += 1


class _FakePointerState:
    """Fake pointer state with fixed current position."""

    def position_get(self) -> tuple[int, int]:
        """Return deterministic pointer position."""
        return (321, 654)


class _FakeRegistry:
    """Fake device registry returning deterministic source paths."""

    def pathForFd_get(self, fd: int) -> str:
        """Return deterministic device path by fd."""
        return f"/dev/input/event{fd}"


class _FakeGrabRefCounter:
    """Fake grab-ref counter exposing per-fd grabbed state."""

    def __init__(self, grabbed_fds: set[int]) -> None:
        """Initialize fake grabbed fd set."""
        self._grabbed_fds: set[int] = grabbed_fds

    def grabbed_check(self, fd: int) -> bool:
        """Return whether fd is marked as grabbed."""
        return fd in self._grabbed_fds


class TestUInputManagerWheelButton:
    """Tests for wheel-button injection translation to REL events."""

    def test_scrollButtonsInjectRelativeWheel_onlyOnPress(self) -> None:
        """
        Wheel buttons should emit REL wheel deltas only on press events.

        Returns:
            None.
        """
        fake_mouse: _FakeMouseDevice = _FakeMouseDevice()
        manager: UInputManager = UInputManager.__new__(UInputManager)
        manager._mouse = fake_mouse

        manager.mouse_button(4, True)
        manager.mouse_button(4, False)
        manager.mouse_button(5, True)
        manager.mouse_button(6, True)
        manager.mouse_button(7, True)

        assert (ecodes.EV_REL, ecodes.REL_WHEEL, 1) in fake_mouse.writes
        assert (ecodes.EV_REL, ecodes.REL_WHEEL, -1) in fake_mouse.writes
        assert (ecodes.EV_REL, ecodes.REL_HWHEEL, -1) in fake_mouse.writes
        assert (ecodes.EV_REL, ecodes.REL_HWHEEL, 1) in fake_mouse.writes
        assert fake_mouse.syn_calls == 4


class TestInputDeviceManagerWheelCapture:
    """Tests for conversion from EV_REL wheel to synthetic button events."""

    def test_wheelRelativeEventRecordsPressReleasePairs(self) -> None:
        """
        Relative wheel motion should produce button press+release payload pairs.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager_any: Any = cast(Any, manager)
        manager_any._pointer_state = _FakePointerState()
        manager_any._registry = _FakeRegistry()
        manager_any._wheel_vertical_accum = 0
        manager_any._wheel_horizontal_accum = 0

        recorded_events: list[dict[str, object]] = []

        def event_record(payload: dict[str, object]) -> None:
            """Append payload to local capture list."""
            recorded_events.append(payload)

        manager_any._event_record = event_record

        fake_device = SimpleNamespace(fd=23)
        manager._wheelRelativeEvent_record(
            device=fake_device,
            code=ecodes.REL_WHEEL,
            value=1,
        )

        assert len(recorded_events) == 2
        assert recorded_events[0]["event_type"] == EventType.MOUSE_BUTTON_PRESS.value
        assert recorded_events[1]["event_type"] == EventType.MOUSE_BUTTON_RELEASE.value
        assert recorded_events[0]["button"] == 4
        assert recorded_events[1]["button"] == 4
        assert recorded_events[0]["x"] == 321
        assert recorded_events[0]["y"] == 654
        assert recorded_events[0]["source_device"] == "/dev/input/event23"

    def test_wheelIgnored_whenDeviceNotGrabbed(self) -> None:
        """
        Wheel rel events should be ignored when source device is not grabbed.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager_any: Any = cast(Any, manager)
        manager_any._pointer_state = _FakePointerState()
        manager_any._registry = SimpleNamespace(
            mouseFds_get=lambda: {23},
            keyboardFds_get=lambda: set(),
            pathForFd_get=lambda fd: f"/dev/input/event{fd}",
        )
        manager_any._grab_refcounter = _FakeGrabRefCounter(grabbed_fds=set())
        manager_any._wheel_vertical_accum = 0
        manager_any._wheel_horizontal_accum = 0

        recorded_events: list[dict[str, object]] = []
        manager_any._event_record = recorded_events.append

        fake_device = SimpleNamespace(fd=23)
        fake_event = SimpleNamespace(
            type=ecodes.EV_REL,
            code=ecodes.REL_WHEEL,
            value=1,
        )

        manager._event_handle(fake_device, fake_event)
        assert recorded_events == []

    def test_hiResWheelDeltaAccumulates_untilDetentThreshold(self) -> None:
        """
        Hi-res wheel deltas should accumulate and emit only after threshold.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager._wheel_vertical_accum = 0
        manager._wheel_horizontal_accum = 0

        first_detents: int = manager._wheelDetentsFromRelEvent_resolve(
            code=ecodes.REL_WHEEL_HI_RES, value=60
        )
        second_detents: int = manager._wheelDetentsFromRelEvent_resolve(
            code=ecodes.REL_WHEEL_HI_RES, value=60
        )
        assert first_detents == 0
        assert second_detents == 1

    def test_hiResWheelJitterSuppressed_belowNoiseThreshold(self) -> None:
        """
        Tiny hi-res wheel deltas should be suppressed as jitter.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager._wheel_vertical_accum = 0
        manager._wheel_horizontal_accum = 0

        detents: int = manager._wheelDetentsFromRelEvent_resolve(
            code=ecodes.REL_WHEEL_HI_RES, value=4
        )
        assert detents == 0


class TestInputDeviceManagerReadFailureQuarantine:
    """Tests for flapping-device read-failure handling in helper loop."""

    def test_readFailureHandle_disablesDevice_afterThreshold(self) -> None:
        """
        Read failures should disable a device after configured threshold.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager_any: Any = cast(Any, manager)
        manager_any._disabled_device_fds = set()
        manager_any._read_error_count_by_fd = {}
        fake_device = SimpleNamespace(fd=23)

        for _ in range(_READ_ERROR_DISABLE_THRESHOLD):
            manager._readFailure_handle(fake_device)

        assert 23 in manager_any._disabled_device_fds
        assert 23 not in manager_any._read_error_count_by_fd

    def test_activeDevicesGet_filtersDisabledFds(self) -> None:
        """
        Active-device list should exclude disabled file descriptors.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager_any: Any = cast(Any, manager)
        manager_any._disabled_device_fds = {22}
        manager_any._read_error_count_by_fd = {}
        manager_any._registry = SimpleNamespace(
            devices_all=lambda: [SimpleNamespace(fd=21), SimpleNamespace(fd=22)]
        )

        active_devices = manager._activeDevices_get()
        active_fds = {device.fd for device in active_devices}
        assert active_fds == {21}


class TestInputDeviceManagerPointerSourceSelection:
    """Tests for single-source REL pointer tracking in helper."""

    def test_pointerTrackingSourceEligible_allowsCurrentFd(self) -> None:
        """
        Current tracked fd should stay eligible for motion updates.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager_any: Any = cast(Any, manager)
        manager_any._pointer_tracking_fd = 23
        manager_any._pointer_tracking_last_event_at = 0.0
        assert manager._pointerTrackingSourceEligible_check(23) is True

    def test_pointerTrackingSourceEligible_blocksCompetingFd_beforeIdle(self) -> None:
        """
        Competing fd should be ignored while current source is active.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager_any: Any = cast(Any, manager)
        manager_any._pointer_tracking_fd = 23
        manager_any._pointer_tracking_last_event_at = time.time()
        assert manager._pointerTrackingSourceEligible_check(24) is False
        assert manager_any._pointer_tracking_fd == 23

    def test_pointerTrackingSourceEligible_switchesAfterIdleGap(self) -> None:
        """
        Competing fd should take over after idle timeout passes.

        Returns:
            None.
        """
        manager: InputDeviceManager = InputDeviceManager.__new__(InputDeviceManager)
        manager_any: Any = cast(Any, manager)
        manager_any._pointer_tracking_fd = 23
        manager_any._pointer_tracking_last_event_at = (
            time.time() - _POINTER_SOURCE_SWITCH_IDLE_SECONDS - 0.05
        )
        assert manager._pointerTrackingSourceEligible_check(24) is True
        assert manager_any._pointer_tracking_fd == 24
