"""Unit tests for X11 event injector focus behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from tx2tx.common.types import EventType, KeyEvent
from tx2tx.x11.injector import EventInjector


class _FakeWindow:
    """Fake X11 window object with focus tracking."""

    def __init__(self) -> None:
        """Initialize fake window state."""
        self.focus_calls: int = 0

    def set_input_focus(self, _revert_to: int, _time: int) -> None:
        """Record focus requests."""
        self.focus_calls += 1


class _FakeRoot:
    """Fake X11 root window with pointer query support."""

    def __init__(self, child_window: Any) -> None:
        """Initialize fake root with pointer child window."""
        self._child_window = child_window

    def query_pointer(self) -> SimpleNamespace:
        """Return pointer reply with child window."""
        return SimpleNamespace(child=self._child_window)


class _FakeDisplay:
    """Fake X11 display object for EventInjector tests."""

    def __init__(self, child_window: Any) -> None:
        """Initialize fake display state."""
        self._root = _FakeRoot(child_window=child_window)
        self.sync_calls: int = 0
        self.keysym_calls: list[int] = []

    def query_extension(self, _name: str) -> object:
        """Return fake extension object."""
        return object()

    def screen(self) -> SimpleNamespace:
        """Return fake screen with fake root."""
        return SimpleNamespace(root=self._root)

    def keysym_to_keycode(self, keysym: int) -> int:
        """Return fallback keycode mapping for keysym."""
        self.keysym_calls.append(keysym)
        return 38

    def sync(self) -> None:
        """Record sync calls."""
        self.sync_calls += 1


class _FakeDisplayManager:
    """Fake display manager returning a fake display."""

    def __init__(self, display: _FakeDisplay) -> None:
        """Initialize fake display manager."""
        self._display = display

    def display_get(self) -> _FakeDisplay:
        """Return fake display."""
        return self._display


class TestEventInjectorFocus:
    """Tests for pointer-window focus behavior during key injection."""

    def test_key_event_focuses_pointer_child_window(
        self, monkeypatch
    ) -> None:
        """Key injection should focus the pointer child window first."""
        child_window = _FakeWindow()
        fake_display = _FakeDisplay(child_window=child_window)
        injector = EventInjector(_FakeDisplayManager(fake_display))

        fake_calls: list[tuple[Any, int, int]] = []

        def _fake_input(display: Any, event_type: int, detail: int) -> None:
            fake_calls.append((display, event_type, detail))

        monkeypatch.setattr("tx2tx.x11.injector.xtest.fake_input", _fake_input)

        key_event = KeyEvent(event_type=EventType.KEY_PRESS, keycode=12, keysym=0x0061)
        injector.keyEvent_inject(key_event)

        assert child_window.focus_calls == 1
        assert len(fake_calls) == 1
        assert fake_calls[0][2] == 38
        assert fake_display.sync_calls == 1

    def test_key_event_without_pointer_child_still_injects(
        self, monkeypatch
    ) -> None:
        """Key injection should continue when pointer has no child window."""
        fake_display = _FakeDisplay(child_window=0)
        injector = EventInjector(_FakeDisplayManager(fake_display))

        fake_calls: list[tuple[Any, int, int]] = []

        def _fake_input(display: Any, event_type: int, detail: int) -> None:
            fake_calls.append((display, event_type, detail))

        monkeypatch.setattr("tx2tx.x11.injector.xtest.fake_input", _fake_input)

        key_event = KeyEvent(event_type=EventType.KEY_RELEASE, keycode=44, keysym=None)
        injector.keyEvent_inject(key_event)

        assert len(fake_calls) == 1
        assert fake_calls[0][2] == 44
        assert fake_display.sync_calls == 1
