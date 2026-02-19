"""Unit tests for Wayland helper wheel capture and injection behavior."""

from __future__ import annotations

from types import SimpleNamespace

from evdev import ecodes

from tx2tx.common.types import EventType
from tx2tx.wayland.helper_daemon import InputDeviceManager, UInputManager


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
        manager._pointer_state = _FakePointerState()
        manager._registry = _FakeRegistry()
        manager._wheel_vertical_accum = 0
        manager._wheel_horizontal_accum = 0

        recorded_events: list[dict[str, object]] = []

        def event_record(payload: dict[str, object]) -> None:
            """Append payload to local capture list."""
            recorded_events.append(payload)

        manager._event_record = event_record  # type: ignore[method-assign]

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
