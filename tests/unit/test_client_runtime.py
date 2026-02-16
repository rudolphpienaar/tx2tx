"""Unit tests for client runtime mouse event conversion behavior."""

from __future__ import annotations

from tx2tx.client.runtime import mouseEventForInjection_build
from tx2tx.common.types import EventType, MouseEvent, NormalizedPoint, Screen


class _FakeDisplayBackend:
    """Fake display backend for runtime mouse conversion tests."""

    def __init__(self, screen: Screen) -> None:
        """Initialize backend state."""
        self._screen: Screen = screen
        self.cursor_hide_calls: int = 0
        self.cursor_show_calls: int = 0

    def screenGeometry_get(self) -> Screen:
        """Return fake screen geometry."""
        return self._screen

    def cursor_hide(self) -> None:
        """Record cursor hide call."""
        self.cursor_hide_calls += 1

    def cursor_show(self) -> None:
        """Record cursor show call."""
        self.cursor_show_calls += 1


class _FakeSoftwareCursor:
    """Fake software cursor for runtime mouse conversion tests."""

    def __init__(self) -> None:
        """Initialize fake cursor state."""
        self.show_calls: int = 0
        self.hide_calls: int = 0
        self.moves: list[tuple[int, int]] = []

    def show(self) -> None:
        """Record show call."""
        self.show_calls += 1

    def hide(self) -> None:
        """Record hide call."""
        self.hide_calls += 1

    def move(self, x: int, y: int) -> None:
        """Record cursor move."""
        self.moves.append((x, y))


class TestMouseEventForInjectionBuild:
    """Tests for remote mouse normalization and software cursor behavior."""

    def test_hide_signal_hides_software_cursor(self) -> None:
        """Negative normalized signal should hide both hardware and software cursor."""
        display_backend = _FakeDisplayBackend(screen=Screen(width=1920, height=1080))
        software_cursor = _FakeSoftwareCursor()
        mouse_event = MouseEvent(
            event_type=EventType.MOUSE_MOVE,
            normalized_point=NormalizedPoint(x=-1.0, y=-1.0),
        )

        result_event = mouseEventForInjection_build(
            mouse_event=mouse_event,
            display_manager=display_backend,
            software_cursor=software_cursor,
        )

        assert result_event is None
        assert display_backend.cursor_hide_calls == 1
        assert display_backend.cursor_show_calls == 0
        assert software_cursor.hide_calls == 1
        assert software_cursor.show_calls == 0
        assert software_cursor.moves == []

    def test_normalized_move_shows_and_moves_software_cursor(self) -> None:
        """Visible normalized move should show and move software cursor."""
        display_backend = _FakeDisplayBackend(screen=Screen(width=1920, height=1080))
        software_cursor = _FakeSoftwareCursor()
        mouse_event = MouseEvent(
            event_type=EventType.MOUSE_MOVE,
            normalized_point=NormalizedPoint(x=0.5, y=0.5),
        )

        result_event = mouseEventForInjection_build(
            mouse_event=mouse_event,
            display_manager=display_backend,
            software_cursor=software_cursor,
        )

        assert result_event is not None
        assert result_event.position is not None
        assert result_event.position.x == 960
        assert result_event.position.y == 540
        assert display_backend.cursor_show_calls == 1
        assert display_backend.cursor_hide_calls == 0
        assert software_cursor.show_calls == 1
        assert software_cursor.hide_calls == 0
        assert software_cursor.moves == [(960, 540)]
