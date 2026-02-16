"""Unit tests for client hint message handling."""

from __future__ import annotations

from tx2tx.client.runtime import hintHide_handle, hintShow_handle
from tx2tx.protocol.message import Message, MessageType


class _FakeHintOverlay:
    """Fake hint overlay for client message tests."""

    def __init__(self) -> None:
        """Initialize fake hint overlay state."""
        self.show_calls: list[tuple[str, int]] = []
        self.hide_calls: int = 0

    def show(self, label: str, timeout_ms: int) -> None:
        """Record show call."""
        self.show_calls.append((label, timeout_ms))

    def hide(self) -> None:
        """Record hide call."""
        self.hide_calls += 1


class TestClientHintHandlers:
    """Tests for hint show/hide message handlers."""

    def test_hint_show_handler_calls_overlay(self) -> None:
        """Hint show message should render overlay."""
        overlay = _FakeHintOverlay()
        message = Message(
            msg_type=MessageType.HINT_SHOW,
            payload={"label": "2", "timeout_ms": 800},
        )

        hintShow_handle(message=message, hint_overlay=overlay)

        assert overlay.show_calls == [("2", 800)]

    def test_hint_hide_handler_calls_overlay(self) -> None:
        """Hint hide message should hide overlay."""
        overlay = _FakeHintOverlay()
        hintHide_handle(hint_overlay=overlay)
        assert overlay.hide_calls == 1
