"""Unit tests for Wayland device component primitives."""

from __future__ import annotations

from tx2tx.wayland.device_components import GrabRefCounter


class _FakeRegistry:
    """Fake device registry for GrabRefCounter tests."""

    def pathForFd_get(self, _fd: int) -> str:
        """
        Return stable fake path.

        Args:
            _fd: Device file descriptor.

        Returns:
            Fake device path.
        """
        return "/dev/input/event-test"


class _FakeDevice:
    """Fake input device with controllable grab/ungrab behavior."""

    def __init__(self, fd: int) -> None:
        """
        Initialize fake device.

        Args:
            fd: Fake file descriptor.
        """
        self.fd: int = fd
        self.grab_calls: int = 0
        self.ungrab_calls: int = 0
        self.ungrab_should_fail: bool = False

    def grab(self) -> None:
        """Record grab call."""
        self.grab_calls += 1

    def ungrab(self) -> None:
        """
        Record ungrab call or raise when configured.

        Raises:
            RuntimeError: When configured to fail.
        """
        self.ungrab_calls += 1
        if self.ungrab_should_fail:
            raise RuntimeError("simulated ungrab failure")


class TestGrabRefCounter:
    """Tests for refcounted grab/ungrab lifecycle handling."""

    def test_ungrab_failure_clears_stale_refcount(self) -> None:
        """
        Ungrab failure should clear local refcount for recovery.

        After a failed ungrab, next grab must attempt a real kernel grab
        instead of returning `already_grabbed` from stale userspace state.
        """
        ref_counter = GrabRefCounter(_FakeRegistry())
        device = _FakeDevice(fd=10)

        first_grab_status, _ = ref_counter.grab_apply(device)
        assert first_grab_status == "grabbed"
        assert device.grab_calls == 1

        device.ungrab_should_fail = True
        ungrab_status, _ = ref_counter.ungrab_apply(device)
        assert ungrab_status == "failed"

        device.ungrab_should_fail = False
        second_grab_status, _ = ref_counter.grab_apply(device)
        assert second_grab_status == "grabbed"
        assert device.grab_calls == 2
