"""Unit tests for server jump-hotkey parsing and sequence processing."""

from __future__ import annotations

from types import SimpleNamespace

from tx2tx.common.types import EventType, KeyEvent, ScreenContext
from tx2tx.server.runtime import (
    JumpHotkeyRuntimeConfig,
    jumpHotkeyConfig_parse,
    jumpHotkeyEvents_process,
)
from tx2tx.server.state import server_state


class TestJumpHotkeyConfigParse:
    """Tests for jumpHotkeyConfig_parse."""

    def test_parse_ctrl_slash_sequence(self) -> None:
        """
        Parse configured Ctrl+/ sequence with 0/1/2 actions.

        Returns:
            None.
        """
        config = SimpleNamespace(
            server=SimpleNamespace(
                jump_hotkey=SimpleNamespace(
                    enabled=True,
                    prefix_key="/",
                    prefix_modifiers=["Ctrl"],
                    timeout_ms=800,
                    west_key="1",
                    east_key="2",
                    center_key="0",
                )
            )
        )

        parsed = jumpHotkeyConfig_parse(config)

        assert parsed.enabled is True
        assert parsed.prefix_keysym == 0x2F
        assert 61 in parsed.prefix_keycodes
        assert parsed.prefix_modifier_mask == 0x4
        assert parsed.action_keysyms_to_context[0x31] == ScreenContext.WEST
        assert parsed.action_keysyms_to_context[0x32] == ScreenContext.EAST
        assert parsed.action_keysyms_to_context[0x30] == ScreenContext.CENTER
        assert parsed.action_keycodes_to_context[10] == ScreenContext.WEST
        assert parsed.action_keycodes_to_context[11] == ScreenContext.EAST
        assert parsed.action_keycodes_to_context[19] == ScreenContext.CENTER


class TestJumpHotkeyEventsProcess:
    """Tests for jumpHotkeyEvents_process."""

    def teardown_method(self) -> None:
        """
        Reset global server state after each test.

        Returns:
            None.
        """
        server_state.reset()

    def test_prefix_then_west_action_on_release(self) -> None:
        """
        Ctrl+/ then 1 release should resolve WEST and consume keys.

        Returns:
            None.
        """
        config = JumpHotkeyRuntimeConfig(
            enabled=True,
            prefix_keysym=0x2F,
            prefix_keycodes={61},
            prefix_modifier_mask=0x4,
            timeout_seconds=0.8,
            action_keysyms_to_context={
                0x31: ScreenContext.WEST,
                0x32: ScreenContext.EAST,
                0x30: ScreenContext.CENTER,
            },
            action_keycodes_to_context={
                10: ScreenContext.WEST,
                11: ScreenContext.EAST,
                19: ScreenContext.CENTER,
            },
        )
        events = [
            KeyEvent(event_type=EventType.KEY_PRESS, keycode=0, keysym=0x2F, state=0x4),
            KeyEvent(event_type=EventType.KEY_PRESS, keycode=0, keysym=0x31, state=0x0),
            KeyEvent(event_type=EventType.KEY_RELEASE, keycode=0, keysym=0x31, state=0x0),
        ]

        filtered_events, target_context = jumpHotkeyEvents_process(
            input_events=events,
            modifier_state=0x4,
            jump_hotkey=config,
        )

        assert target_context == ScreenContext.WEST
        assert filtered_events == []

    def test_non_sequence_key_passthrough(self) -> None:
        """
        Unrelated key should pass through unchanged.

        Returns:
            None.
        """
        config = JumpHotkeyRuntimeConfig(
            enabled=True,
            prefix_keysym=0x2F,
            prefix_keycodes={61},
            prefix_modifier_mask=0x4,
            timeout_seconds=0.8,
            action_keysyms_to_context={0x31: ScreenContext.WEST},
            action_keycodes_to_context={10: ScreenContext.WEST},
        )
        key_event = KeyEvent(event_type=EventType.KEY_PRESS, keycode=0, keysym=0x61, state=0x0)

        filtered_events, target_context = jumpHotkeyEvents_process(
            input_events=[key_event],
            modifier_state=0x0,
            jump_hotkey=config,
        )

        assert target_context is None
        assert filtered_events == [key_event]

    def test_action_press_without_release_does_not_trigger(self) -> None:
        """
        Action key press alone should not trigger jump until release.

        Returns:
            None.
        """
        config = JumpHotkeyRuntimeConfig(
            enabled=True,
            prefix_keysym=0x2F,
            prefix_keycodes={61},
            prefix_modifier_mask=0x4,
            timeout_seconds=0.8,
            action_keysyms_to_context={0x31: ScreenContext.WEST},
            action_keycodes_to_context={10: ScreenContext.WEST},
        )
        events = [
            KeyEvent(event_type=EventType.KEY_PRESS, keycode=61, keysym=0x2F, state=0x4),
            KeyEvent(event_type=EventType.KEY_PRESS, keycode=10, keysym=0x31, state=0x0),
        ]

        filtered_events, target_context = jumpHotkeyEvents_process(
            input_events=events,
            modifier_state=0x4,
            jump_hotkey=config,
        )

        assert target_context is None
        assert filtered_events == []

    def test_keycode_fallback_matches_when_keysym_missing(self) -> None:
        """
        Keycode fallback should resolve action when keysym is missing.

        Returns:
            None.
        """
        config = JumpHotkeyRuntimeConfig(
            enabled=True,
            prefix_keysym=0x2F,
            prefix_keycodes={61},
            prefix_modifier_mask=0x4,
            timeout_seconds=0.8,
            action_keysyms_to_context={0x31: ScreenContext.WEST},
            action_keycodes_to_context={10: ScreenContext.WEST},
        )
        events = [
            KeyEvent(event_type=EventType.KEY_PRESS, keycode=61, keysym=None, state=0x4),
            KeyEvent(event_type=EventType.KEY_PRESS, keycode=10, keysym=None, state=0x0),
            KeyEvent(event_type=EventType.KEY_RELEASE, keycode=10, keysym=None, state=0x0),
        ]

        filtered_events, target_context = jumpHotkeyEvents_process(
            input_events=events,
            modifier_state=0x4,
            jump_hotkey=config,
        )

        assert target_context == ScreenContext.WEST
        assert filtered_events == []
