"""Unit tests for REMOTE context input forwarding behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from tx2tx.common.types import EventType, KeyEvent, Position, Screen, ScreenContext
from tx2tx.server import runtime
from tx2tx.server.state import server_state


class TestRemoteContextProcess:
    """Tests for remoteContext_process behavior."""

    def teardown_method(self) -> None:
        """
        Reset global server state after each test.

        Returns:
            None.
        """
        server_state.reset()

    def test_keyboardForwarded_whenWarpEnforcementActive(self, monkeypatch) -> None:
        """
        Key events must still forward when warp enforcement path is active.

        Returns:
            None.
        """
        server_state.context = ScreenContext.EAST
        context_to_client: dict[ScreenContext, str] = {ScreenContext.EAST: "penguin"}
        position: Position = Position(x=200, y=300)
        screen_geometry: Screen = Screen(width=3840, height=2160)
        config = SimpleNamespace(server=SimpleNamespace(velocity_threshold=50))

        input_event = KeyEvent(event_type=EventType.KEY_PRESS, keycode=38, state=0)
        input_capturer = Mock()
        input_capturer.inputEvents_read.return_value = ([input_event], 0)

        remote_input_events_send = Mock()

        monkeypatch.setattr(runtime, "remoteWarpEnforcement_apply", lambda **_: True)
        monkeypatch.setattr(runtime, "panicKey_check", lambda *args, **kwargs: False)
        monkeypatch.setattr(runtime, "remoteInputEvents_send", remote_input_events_send)

        runtime.remoteContext_process(
            network=Mock(),
            display_manager=Mock(),
            pointer_tracker=Mock(),
            screen_geometry=screen_geometry,
            config=config,
            position=position,
            velocity=0.0,
            context_to_client=context_to_client,
            x11native=False,
            input_capturer=input_capturer,
            panic_keysyms=set(),
            panic_modifiers=0,
        )

        assert input_capturer.inputEvents_read.call_count == 1
        remote_input_events_send.assert_called_once()
        send_kwargs = remote_input_events_send.call_args.kwargs
        assert send_kwargs["target_client_name"] == "penguin"
        assert len(send_kwargs["input_events"]) == 1
