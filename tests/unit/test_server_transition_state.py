"""Unit tests for REMOTE return-boundary trigger policy."""

from __future__ import annotations

from tx2tx.common.types import Position, Screen, ScreenContext
from tx2tx.server.transition_state import _parkingPositionFromContext_get
from tx2tx.server.transition_state import _remoteReturnTriggered_check


class TestRemoteReturnTriggeredCheck:
    """Tests for REMOTE->CENTER return trigger guard and thresholds."""

    def test_returnSuppressed_withinPostSwitchGuardWindow(self) -> None:
        """
        Return must be suppressed immediately after entering REMOTE context.

        Returns:
            None.
        """
        should_return: bool = _remoteReturnTriggered_check(
            context=ScreenContext.EAST,
            position=Position(x=0, y=1000),
            screen_geometry=Screen(width=3840, height=2160),
            velocity=2000.0,
            velocity_threshold=50.0,
            remote_switch_age_seconds=0.10,
        )
        assert not should_return


class TestParkingPositionFromContext:
    """Tests for REMOTE entry parking-position policy selection."""

    def test_centerParkingEnabled_returnsScreenCenter(self) -> None:
        """
        Center parking mode should place pointer at local screen midpoint.

        Returns:
            None.
        """
        parking_position: Position = _parkingPositionFromContext_get(
            target_context=ScreenContext.EAST,
            position=Position(x=100, y=200),
            screen_geometry=Screen(width=3840, height=2160),
            center_parking_enabled=True,
        )
        assert parking_position == Position(x=1920, y=1080)

    def test_returnAllowed_afterGuard_whenBoundaryAndVelocitySatisfied(self) -> None:
        """
        Return should trigger after guard window when boundary and velocity match.

        Returns:
            None.
        """
        should_return: bool = _remoteReturnTriggered_check(
            context=ScreenContext.EAST,
            position=Position(x=0, y=1000),
            screen_geometry=Screen(width=3840, height=2160),
            velocity=2000.0,
            velocity_threshold=50.0,
            remote_switch_age_seconds=2.0,
        )
        assert should_return

    def test_returnSuppressed_afterGuard_whenVelocityTooLow(self) -> None:
        """
        Return must stay suppressed when velocity threshold is not met.

        Returns:
            None.
        """
        should_return: bool = _remoteReturnTriggered_check(
            context=ScreenContext.EAST,
            position=Position(x=0, y=1000),
            screen_geometry=Screen(width=3840, height=2160),
            velocity=10.0,
            velocity_threshold=50.0,
            remote_switch_age_seconds=2.0,
        )
        assert not should_return
