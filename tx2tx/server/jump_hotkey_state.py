"""
Jump-hotkey state machine policy.

This module owns jump-hotkey parsing and state transitions. It evaluates
captured input events, updates runtime jump-hotkey state, and returns both
filtered passthrough events and optional resolved context action.
"""

from __future__ import annotations

import time
from typing import Protocol

from tx2tx.common.types import EventType, KeyEvent, ScreenContext
from tx2tx.input.backend import InputEvent
from tx2tx.server.runtime_loop import JumpHotkeyConfigProtocol
from tx2tx.server.state import RuntimeStateProtocol

__all__ = [
    "jumpHotkeyEvents_process",
    "keyEventMatchesJumpToken_check",
]


class LoggerProtocol(Protocol):
    """Minimal logger contract for jump-hotkey processing."""

    def info(self, msg: str, *args: object) -> None:
        """Emit info-level message."""
        ...


def keyEventMatchesJumpToken_check(
    event: KeyEvent,
    expected_keysym: int,
    alt_keysyms: set[int],
    fallback_keycodes: set[int],
) -> bool:
    """
    Check whether one key event matches configured jump token.

    Args:
        event:
            Key event under evaluation.
        expected_keysym:
            Primary keysym configured for token.
        alt_keysyms:
            Alternate accepted keysyms.
        fallback_keycodes:
            Accepted fallback keycodes.

    Returns:
        `True` when event matches token.
    """
    if event.keysym is not None and event.keysym == expected_keysym:
        return True
    if event.keysym is not None and event.keysym in alt_keysyms:
        return True
    if event.keycode in fallback_keycodes:
        return True
    return False


def jumpHotkeyEvents_process(
    input_events: list[InputEvent],
    modifier_state: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    runtime_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> tuple[list[InputEvent], ScreenContext | None]:
    """
    Process jump-hotkey prefix/action sequence for one input batch.

    Args:
        input_events:
            Captured input events for current poll iteration.
        modifier_state:
            Fallback modifier mask when event state is missing.
        jump_hotkey:
            Runtime jump-hotkey configuration.
        runtime_state:
            Mutable runtime state storing hotkey sequence state.
        logger:
            Logger used for hotkey telemetry.

    Returns:
        Tuple of `(filtered_events, target_context_or_none)`.
    """
    if not jump_hotkey.enabled:
        return input_events, None

    _jumpHotkeyArmExpiry_apply(runtime_state)

    filtered_events: list[InputEvent] = []
    target_context: ScreenContext | None = None
    now: float = time.time()

    for input_event in input_events:
        if not isinstance(input_event, KeyEvent):
            filtered_events.append(input_event)
            continue

        key_event: KeyEvent = input_event
        if key_event.event_type == EventType.KEY_RELEASE:
            event_consumed, resolved_context = _keyRelease_process(
                key_event=key_event,
                jump_hotkey=jump_hotkey,
                runtime_state=runtime_state,
                now=now,
                logger=logger,
            )
            if resolved_context is not None:
                target_context = resolved_context
            if event_consumed:
                continue
            filtered_events.append(key_event)
            continue

        if key_event.event_type != EventType.KEY_PRESS:
            filtered_events.append(key_event)
            continue

        key_press_consumed: bool = _keyPress_process(
            key_event=key_event,
            modifier_state=modifier_state,
            jump_hotkey=jump_hotkey,
            runtime_state=runtime_state,
            now=now,
            logger=logger,
        )
        if key_press_consumed:
            continue
        filtered_events.append(key_event)

    return filtered_events, target_context


def _jumpHotkeyArmExpiry_apply(runtime_state: RuntimeStateProtocol) -> None:
    """
    Expire armed jump-hotkey window when timeout elapsed.

    Args:
        runtime_state:
            Mutable runtime state storing jump-hotkey sequence fields.
    """
    now: float = time.time()
    if now <= runtime_state.jump_hotkey_armed_until:
        return
    runtime_state.jump_hotkey_armed_until = 0.0
    runtime_state.jump_hotkey_pending_target_context = None


def _keyRelease_process(
    key_event: KeyEvent,
    jump_hotkey: JumpHotkeyConfigProtocol,
    runtime_state: RuntimeStateProtocol,
    now: float,
    logger: LoggerProtocol,
) -> tuple[bool, ScreenContext | None]:
    """
    Process one key-release event for jump-hotkey state machine.

    Args:
        key_event:
            Key-release event.
        jump_hotkey:
            Runtime jump-hotkey configuration.
        runtime_state:
            Mutable runtime state.
        now:
            Current monotonic wall-clock timestamp.
        logger:
            Logger used for hotkey telemetry.

    Returns:
        Tuple `(event_consumed, resolved_target_context)`.
    """
    resolved_target_context: ScreenContext | None = _releaseContext_resolve(
        key_event,
        jump_hotkey,
    )
    if _pendingReleaseMatches_check(resolved_target_context, runtime_state, now):
        assert resolved_target_context is not None
        runtime_state.jump_hotkey_armed_until = 0.0
        runtime_state.jump_hotkey_pending_target_context = None
        logger.info("[HOTKEY] Action captured: %s", resolved_target_context.value.upper())
        return True, resolved_target_context

    if _swallowedRelease_apply(key_event, runtime_state):
        return True, None

    return False, None


def _keyPress_process(
    key_event: KeyEvent,
    modifier_state: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    runtime_state: RuntimeStateProtocol,
    now: float,
    logger: LoggerProtocol,
) -> bool:
    """
    Process one key-press event for jump-hotkey state machine.

    Args:
        key_event:
            Key-press event.
        modifier_state:
            Fallback modifier state.
        jump_hotkey:
            Runtime jump-hotkey configuration.
        runtime_state:
            Mutable runtime state.
        now:
            Current wall-clock timestamp.
        logger:
            Logger used for telemetry.

    Returns:
        `True` when event is consumed by jump-hotkey flow.
    """
    if _prefixPressMatches_check(key_event, modifier_state, jump_hotkey):
        runtime_state.jump_hotkey_armed_until = now + jump_hotkey.timeout_seconds
        runtime_state.jump_hotkey_pending_target_context = None
        _keysymSwallow_add(key_event.keysym, runtime_state)
        logger.info("[HOTKEY] Prefix captured")
        return True

    if now > runtime_state.jump_hotkey_armed_until:
        return False

    pressed_context: ScreenContext | None = _pressedContext_resolve(key_event, jump_hotkey)
    if pressed_context is not None:
        runtime_state.jump_hotkey_pending_target_context = pressed_context
    _keysymSwallow_add(key_event.keysym, runtime_state)
    return True


def _releaseContext_resolve(
    key_event: KeyEvent,
    jump_hotkey: JumpHotkeyConfigProtocol,
) -> ScreenContext | None:
    """
    Resolve target context from action key release event.

    Args:
        key_event:
            Key-release event.
        jump_hotkey:
            Runtime jump-hotkey configuration.

    Returns:
        Resolved target context or `None`.
    """
    if key_event.keysym is not None and key_event.keysym in jump_hotkey.action_keysyms_to_context:
        return jump_hotkey.action_keysyms_to_context[key_event.keysym]
    if key_event.keycode in jump_hotkey.action_keycodes_to_context:
        return jump_hotkey.action_keycodes_to_context[key_event.keycode]
    return None


def _pressedContext_resolve(
    key_event: KeyEvent,
    jump_hotkey: JumpHotkeyConfigProtocol,
) -> ScreenContext | None:
    """
    Resolve target context from action key press event.

    Args:
        key_event:
            Key-press event.
        jump_hotkey:
            Runtime jump-hotkey configuration.

    Returns:
        Resolved target context or `None`.
    """
    if key_event.keysym is not None and key_event.keysym in jump_hotkey.action_keysyms_to_context:
        return jump_hotkey.action_keysyms_to_context[key_event.keysym]
    if key_event.keycode in jump_hotkey.action_keycodes_to_context:
        return jump_hotkey.action_keycodes_to_context[key_event.keycode]
    return None


def _pendingReleaseMatches_check(
    resolved_target_context: ScreenContext | None,
    runtime_state: RuntimeStateProtocol,
    now: float,
) -> bool:
    """
    Check whether released action matches pending armed context.

    Args:
        resolved_target_context:
            Context resolved from current release event.
        runtime_state:
            Mutable runtime state.
        now:
            Current wall-clock timestamp.

    Returns:
        `True` when release completes armed jump sequence.
    """
    if now > runtime_state.jump_hotkey_armed_until:
        return False
    if runtime_state.jump_hotkey_pending_target_context is None:
        return False
    if resolved_target_context is None:
        return False
    return resolved_target_context == runtime_state.jump_hotkey_pending_target_context


def _prefixPressMatches_check(
    key_event: KeyEvent,
    modifier_state: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
) -> bool:
    """
    Check whether key press matches configured jump prefix.

    Args:
        key_event:
            Key-press event.
        modifier_state:
            Fallback modifier state.
        jump_hotkey:
            Runtime jump-hotkey configuration.

    Returns:
        `True` when event is recognized as prefix press.
    """
    event_state: int = key_event.state if key_event.state is not None else modifier_state
    prefix_token_matches: bool = keyEventMatchesJumpToken_check(
        event=key_event,
        expected_keysym=jump_hotkey.prefix_keysym,
        alt_keysyms=jump_hotkey.prefix_alt_keysyms,
        fallback_keycodes=jump_hotkey.prefix_keycodes,
    )
    if not prefix_token_matches:
        return False
    if jump_hotkey.prefix_modifier_mask == 0:
        return True
    return (event_state & jump_hotkey.prefix_modifier_mask) == jump_hotkey.prefix_modifier_mask


def _swallowedRelease_apply(
    key_event: KeyEvent,
    runtime_state: RuntimeStateProtocol,
) -> bool:
    """
    Consume release events for previously swallowed keysyms.

    Args:
        key_event:
            Key-release event.
        runtime_state:
            Mutable runtime state.

    Returns:
        `True` when event is consumed.
    """
    if key_event.keysym is None:
        return False
    if key_event.keysym not in runtime_state.jump_hotkey_swallow_keysyms:
        return False
    runtime_state.jump_hotkey_swallow_keysyms.discard(key_event.keysym)
    return True


def _keysymSwallow_add(keysym: int | None, runtime_state: RuntimeStateProtocol) -> None:
    """
    Track keysym for swallow-on-release behavior.

    Args:
        keysym:
            Keysym to swallow on release.
        runtime_state:
            Mutable runtime state.
    """
    if keysym is None:
        return
    runtime_state.jump_hotkey_swallow_keysyms.add(keysym)
