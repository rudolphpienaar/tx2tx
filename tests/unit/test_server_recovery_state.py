"""Unit tests for server recovery-state revert behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import Mock

from tx2tx.common.types import Position, Screen, ScreenContext
from tx2tx.server import recovery_state


@dataclass
class DummyRuntimeState:
    """Minimal runtime-state test double."""

    context: ScreenContext = ScreenContext.CENTER
    last_center_switch_time: float = 0.0
    last_remote_switch_time: float = 0.0
    boundary_crossed: bool = False
    target_warp_position: Position | None = None
    last_sent_position: Position | None = None
    active_remote_client_name: str | None = None
    jump_hotkey_armed_until: float = 0.0
    jump_hotkey_swallow_keysyms: set[int] = field(default_factory=set)
    jump_hotkey_pending_target_context: ScreenContext | None = None

    def reset(self) -> None:
        """Reset runtime-state fields."""
        self.context = ScreenContext.CENTER
        self.last_center_switch_time = 0.0
        self.last_remote_switch_time = 0.0
        self.boundary_crossed = False
        self.target_warp_position = None
        self.last_sent_position = None
        self.active_remote_client_name = None
        self.jump_hotkey_armed_until = 0.0
        self.jump_hotkey_swallow_keysyms = set()
        self.jump_hotkey_pending_target_context = None

    def boundaryCrossed_clear(self) -> None:
        """Clear boundary-crossing marker."""
        self.boundary_crossed = False
        self.target_warp_position = None

    def positionChanged_check(self, current_position: Position) -> bool:
        """Check position update against last sent value."""
        if self.last_sent_position is None:
            return True
        return (
            self.last_sent_position.x != current_position.x
            or self.last_sent_position.y != current_position.y
        )

    def lastSentPosition_update(self, position: Position) -> None:
        """Update last-sent position."""
        self.last_sent_position = position


class TestRecoveryState:
    """Tests for recovery-state policy module."""

    def test_entryPositionMapping_resolves_expected_edges(self) -> None:
        """Entry-position mapping must invert previous REMOTE context."""
        screen_geometry: Screen = Screen(width=3840, height=2160)
        current_position: Position = Position(x=1000, y=1200)

        west_position: Position = recovery_state.centerRevertEntryPosition_get(
            previous_context=ScreenContext.WEST,
            current_position=current_position,
            screen_geometry=screen_geometry,
        )
        east_position: Position = recovery_state.centerRevertEntryPosition_get(
            previous_context=ScreenContext.EAST,
            current_position=current_position,
            screen_geometry=screen_geometry,
        )
        north_position: Position = recovery_state.centerRevertEntryPosition_get(
            previous_context=ScreenContext.NORTH,
            current_position=current_position,
            screen_geometry=screen_geometry,
        )
        south_position: Position = recovery_state.centerRevertEntryPosition_get(
            previous_context=ScreenContext.SOUTH,
            current_position=current_position,
            screen_geometry=screen_geometry,
        )

        assert west_position == Position(x=30, y=1200)
        assert east_position == Position(x=3810, y=1200)
        assert north_position == Position(x=1000, y=30)
        assert south_position == Position(x=1000, y=2130)

    def test_revertFromRemote_updatesStateAndWarps(self, monkeypatch) -> None:
        """Remote revert should reset state, unlock input, and warp to entry edge."""
        monkeypatch.setattr(recovery_state.time, "sleep", lambda _: None)

        runtime_state: DummyRuntimeState = DummyRuntimeState(context=ScreenContext.EAST)
        runtime_state.boundary_crossed = True
        runtime_state.last_sent_position = Position(x=99, y=88)
        runtime_state.active_remote_client_name = "penguin"

        display_manager = Mock()
        pointer_tracker = Mock()
        logger = Mock()

        recovery_state.state_revertToCenter(
            display_manager=display_manager,
            screen_geometry=Screen(width=3840, height=2160),
            position=Position(x=100, y=777),
            pointer_tracker=pointer_tracker,
            runtime_state=runtime_state,
            logger=logger,
        )

        assert runtime_state.context == ScreenContext.CENTER
        assert runtime_state.boundary_crossed is False
        assert runtime_state.last_sent_position is None
        assert runtime_state.active_remote_client_name is None

        display_manager.keyboard_ungrab.assert_called_once()
        display_manager.pointer_ungrab.assert_called_once()
        display_manager.cursor_show.assert_called_once()
        display_manager.cursorPosition_set.assert_called_once_with(Position(x=3810, y=777))
        pointer_tracker.reset.assert_called_once()

    def test_revertNoop_whenAlreadyCenter(self) -> None:
        """CENTER context should bypass revert side effects."""
        runtime_state: DummyRuntimeState = DummyRuntimeState(context=ScreenContext.CENTER)
        display_manager = Mock()
        pointer_tracker = Mock()
        logger = Mock()

        recovery_state.state_revertToCenter(
            display_manager=display_manager,
            screen_geometry=Screen(width=3840, height=2160),
            position=Position(x=10, y=20),
            pointer_tracker=pointer_tracker,
            runtime_state=runtime_state,
            logger=logger,
        )

        display_manager.keyboard_ungrab.assert_not_called()
        display_manager.pointer_ungrab.assert_not_called()
        display_manager.cursorPosition_set.assert_not_called()
        pointer_tracker.reset.assert_not_called()
