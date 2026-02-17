"""
tx2tx server runtime orchestration and transition policy.

This module defines the server-side runtime behavior for mixed-display input
sharing. It is responsible for:
1. Parsing runtime key policy (panic and jump hotkeys).
2. Resolving context transitions between CENTER and REMOTE logical screens.
3. Forwarding normalized pointer and keyboard/mouse events to active clients.
4. Enforcing safety invariants that prevent stuck grabs or local-only input.

The polling mechanics are delegated to `tx2tx.server.runtime_loop`; this module
provides the context-specific behavior callbacks consumed by that loop.

Compatibility API:
1. `arguments_parse`
2. `clientMessage_handle`
3. `logging_setup`
4. `server_run`

All other symbols are internal runtime wiring helpers or policy adapters.
"""

import argparse
from dataclasses import dataclass
from functools import partial
import logging
from typing import Optional

from tx2tx.common.config import Config
from tx2tx.common.types import (
    EventType,
    KeyEvent,
    Position,
    Screen,
    ScreenContext,
)
from tx2tx.input.backend import DisplayBackend, InputCapturer, InputEvent
from tx2tx.protocol.message import Message, MessageBuilder
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.server.runtime_loop import (
    JumpHotkeyConfigProtocol,
    PollingLoopCallbacks,
    PollingLoopDependencies,
    pollingLoop_process,
)
from tx2tx.server.state import RuntimeStateProtocol, server_state
from tx2tx.server import transition_state as transitionPolicy
from tx2tx.server import jump_hotkey_state as jumpHotkeyStatePolicy
from tx2tx.server import recovery_state as recoveryStatePolicy
from tx2tx.server import server_cli as serverCliPolicy
from tx2tx.server import server_handshake as serverHandshakePolicy
from tx2tx.server import server_logging as serverLoggingPolicy
from tx2tx.server import server_runtime_coordinator as runtimeCoordinatorPolicy
from tx2tx.server.transition_state import TransitionCallbacks
from tx2tx.server.server_runtime_coordinator import ServerRunCallbacks
from tx2tx.x11.pointer import PointerTracker

logger = logging.getLogger(__name__)

__all__ = [
    "JumpHotkeyRuntimeConfig",
    "arguments_parse",
    "clientMessage_handle",
    "jumpHotkeyConfig_parse",
    "jumpHotkeyEvents_process",
    "logging_setup",
    "panicKeyConfig_parse",
    "panicKey_check",
    "remoteContext_process",
    "remoteInputEvents_send",
    "remoteWarpEnforcement_apply",
    "server_run",
    "state_revertToCenter",
]

# Keysym lookup table for common key names
# See /usr/include/X11/keysymdef.h for full list
KEY_NAME_TO_KEYSYM = {
    # Function keys
    "F1": 0xFFBE,
    "F2": 0xFFBF,
    "F3": 0xFFC0,
    "F4": 0xFFC1,
    "F5": 0xFFC2,
    "F6": 0xFFC3,
    "F7": 0xFFC4,
    "F8": 0xFFC5,
    "F9": 0xFFC6,
    "F10": 0xFFC7,
    "F11": 0xFFC8,
    "F12": 0xFFC9,
    # Special keys
    "Scroll_Lock": 0xFF14,
    "Pause": 0xFF13,
    "Break": 0xFF13,
    "Escape": 0xFF1B,
    "Esc": 0xFF1B,
    "Print": 0xFF61,
    "Print_Screen": 0xFF61,
    "Insert": 0xFF63,
    "Delete": 0xFFFF,
    "Home": 0xFF50,
    "End": 0xFF57,
    "Page_Up": 0xFF55,
    "Page_Down": 0xFF56,
    "BackSpace": 0xFF08,
    "Tab": 0xFF09,
    "Return": 0xFF0D,
    "Enter": 0xFF0D,
    "space": 0x0020,
    "Space": 0x0020,
    "slash": 0x002F,
    "/": 0x002F,
    "0": 0x0030,
    "1": 0x0031,
    "2": 0x0032,
    # Arrow keys
    "Left": 0xFF51,
    "Up": 0xFF52,
    "Right": 0xFF53,
    "Down": 0xFF54,
    # Modifier keys (for reference, not typically used as panic key)
    "Shift_L": 0xFFE1,
    "Shift_R": 0xFFE2,
    "Control_L": 0xFFE3,
    "Control_R": 0xFFE4,
    "Alt_L": 0xFFE9,
    "Alt_R": 0xFFEA,
    "Super_L": 0xFFEB,
    "Super_R": 0xFFEC,
}

# Modifier key masks (from X11)
MODIFIER_MASKS = {
    "Shift": 0x1,
    "Lock": 0x2,  # Caps Lock
    "Ctrl": 0x4,
    "Control": 0x4,
    "Alt": 0x8,
    "Mod1": 0x8,
    "Mod2": 0x10,  # Num Lock typically
    "Mod3": 0x20,
    "Mod4": 0x40,  # Super/Windows key typically
    "Mod5": 0x80,
}

# Default panic keysyms (used if config parsing fails)
DEFAULT_PANIC_KEYSYMS = {0xFF14, 0xFF13}  # Scroll_Lock, Pause


@dataclass
class JumpHotkeyRuntimeConfig:
    """
    Runtime-resolved jump hotkey configuration.

    Attributes:
        enabled: Whether jump hotkeys are enabled.
        prefix_keysym: Keysym for prefix key.
        prefix_alt_keysyms: Alternate keysyms for prefix matching.
        prefix_keycodes: Keycode fallbacks for prefix key.
        prefix_modifier_mask: Modifier mask required for prefix.
        timeout_seconds: Sequence timeout window.
        action_keysyms_to_context: Mapping from suffix keysym to target context.
        action_keycodes_to_context: Mapping from suffix keycode to target context.
    """

    enabled: bool
    prefix_keysym: int
    prefix_alt_keysyms: set[int]
    prefix_keycodes: set[int]
    prefix_modifier_mask: int
    timeout_seconds: float
    action_keysyms_to_context: dict[int, ScreenContext]
    action_keycodes_to_context: dict[int, ScreenContext]


def panicKeyConfig_parse(config: Config) -> tuple[set[int], int]:
    """
    Parse panic-key configuration into executable runtime values.

    The panic key is a safety escape that forces immediate return to CENTER
    context when remote control becomes unstable or disconnected.

    Args:
        config:
            Loaded server configuration.

    Returns:
        Tuple of `(panic_keysyms, required_modifier_mask)`.
    """
    try:
        panic_cfg = config.server.panic_key
        key_name = panic_cfg.key
        modifiers = panic_cfg.modifiers

        # Look up keysym
        if key_name in KEY_NAME_TO_KEYSYM:
            keysym = KEY_NAME_TO_KEYSYM[key_name]
        else:
            # Try to parse as hex (e.g., "0xff14")
            try:
                keysym = int(key_name, 0)
            except ValueError:
                logger.warning(f"Unknown panic key '{key_name}', using defaults")
                return DEFAULT_PANIC_KEYSYMS, 0

        # Calculate modifier mask
        mod_mask = 0
        for mod in modifiers:
            if mod in MODIFIER_MASKS:
                mod_mask |= MODIFIER_MASKS[mod]
            else:
                logger.warning(f"Unknown modifier '{mod}' in panic key config")

        logger.info(
            f"Panic key configured: {'+'.join(modifiers + [key_name])} (keysym=0x{keysym:x}, mask=0x{mod_mask:x})"
        )
        return {keysym}, mod_mask

    except Exception as e:
        logger.warning(f"Failed to parse panic key config: {e}, using defaults")
        return DEFAULT_PANIC_KEYSYMS, 0


def panicKey_check(
    events: list[InputEvent],
    panic_keysyms: set[int],
    required_modifiers: int,
    current_modifiers: int,
) -> bool:
    """
    Evaluate input events for panic-key activation.

    Panic activation is matched on key press events, with optional required
    modifiers. Event-local modifier state is preferred when available.

    Args:
        events:
            Input events to inspect.
        panic_keysyms:
            Keysyms that trigger panic mode.
        required_modifiers:
            Modifier mask that must be present for activation.
        current_modifiers:
            Fallback modifier mask when event state is unavailable.

    Returns:
        `True` when panic trigger is detected, otherwise `False`.
    """
    for event in events:
        if isinstance(event, KeyEvent):
            if event.event_type == EventType.KEY_PRESS:
                # Use event-specific state if available, otherwise fallback
                event_state = event.state if event.state is not None else current_modifiers

                # Check modifiers
                if required_modifiers != 0:
                    if (event_state & required_modifiers) != required_modifiers:
                        continue

                if event.keysym in panic_keysyms:
                    return True
    return False


def keysymFromKeyName_get(key_name: str) -> int | None:
    """
    Resolve keysym integer from configured key name.

    Args:
        key_name: Configured key name.

    Returns:
        Keysym integer or None when unresolved.
    """
    if key_name in KEY_NAME_TO_KEYSYM:
        return KEY_NAME_TO_KEYSYM[key_name]
    key_name_lower: str = key_name.lower()
    if key_name_lower in KEY_NAME_TO_KEYSYM:
        return KEY_NAME_TO_KEYSYM[key_name_lower]
    try:
        return int(key_name, 0)
    except ValueError:
        return None


def keycodeFallbacksFromKeyName_get(key_name: str) -> set[int]:
    """
    Resolve likely X11 keycode fallbacks for a configured key token.

    Args:
        key_name: Configured key token.

    Returns:
        Candidate X11 keycodes for fallback matching.
    """
    normalized_key_name: str = key_name.strip()
    digit_keycode_map: dict[str, int] = {
        "1": 10,
        "2": 11,
        "3": 12,
        "4": 13,
        "5": 14,
        "6": 15,
        "7": 16,
        "8": 17,
        "9": 18,
        "0": 19,
    }
    if normalized_key_name in digit_keycode_map:
        return {digit_keycode_map[normalized_key_name]}
    if normalized_key_name in {"/", "slash", "SLASH"}:
        return {61, 106}
    if normalized_key_name in {"KP_Divide", "KPSLASH"}:
        return {106}
    return set()


def prefixAltKeysymsFromKeyName_get(key_name: str) -> set[int]:
    """
    Resolve alternate keysyms accepted for jump prefix key.

    Args:
        key_name: Configured prefix key token.

    Returns:
        Alternate keysyms set.
    """
    normalized_key_name: str = key_name.strip()
    if normalized_key_name in {"/", "slash", "SLASH"}:
        # Ctrl+/ is commonly emitted as Ctrl+underscore in terminals (^_, 0x1f).
        return {0x1F}
    return set()


def jumpHotkeyConfig_parse(config: Config) -> JumpHotkeyRuntimeConfig:
    """
    Parse jump-hotkey config into runtime-resolved keysyms/modifiers.

    Args:
        config: Loaded config.

    Returns:
        Resolved runtime jump-hotkey configuration.
    """
    jump_cfg = config.server.jump_hotkey
    if not jump_cfg.enabled:
        return JumpHotkeyRuntimeConfig(
            enabled=False,
            prefix_keysym=0,
            prefix_alt_keysyms=set(),
            prefix_keycodes=set(),
            prefix_modifier_mask=0,
            timeout_seconds=0.0,
            action_keysyms_to_context={},
            action_keycodes_to_context={},
        )

    prefix_keysym: int | None = keysymFromKeyName_get(jump_cfg.prefix_key)
    if prefix_keysym is None:
        logger.warning("Unknown jump-hotkey prefix key '%s'; disabling jump hotkey", jump_cfg.prefix_key)
        return JumpHotkeyRuntimeConfig(
            enabled=False,
            prefix_keysym=0,
            prefix_alt_keysyms=set(),
            prefix_keycodes=set(),
            prefix_modifier_mask=0,
            timeout_seconds=0.0,
            action_keysyms_to_context={},
            action_keycodes_to_context={},
        )

    prefix_modifier_mask: int = 0
    for modifier_name in jump_cfg.prefix_modifiers:
        if modifier_name in MODIFIER_MASKS:
            prefix_modifier_mask |= MODIFIER_MASKS[modifier_name]
        else:
            logger.warning("Unknown jump-hotkey modifier '%s' ignored", modifier_name)

    action_keysyms_to_context: dict[int, ScreenContext] = {}
    action_keycodes_to_context: dict[int, ScreenContext] = {}
    action_pairs: list[tuple[str, ScreenContext]] = [
        (jump_cfg.west_key, ScreenContext.WEST),
        (jump_cfg.east_key, ScreenContext.EAST),
        (jump_cfg.center_key, ScreenContext.CENTER),
    ]
    for key_name, target_context in action_pairs:
        action_keysym: int | None = keysymFromKeyName_get(key_name)
        if action_keysym is None:
            logger.warning("Unknown jump-hotkey action key '%s' ignored", key_name)
            continue
        action_keysyms_to_context[action_keysym] = target_context
        for fallback_keycode in keycodeFallbacksFromKeyName_get(key_name):
            action_keycodes_to_context[fallback_keycode] = target_context

    if not action_keysyms_to_context:
        logger.warning("Jump hotkey enabled but no valid action keys resolved; disabling")
        return JumpHotkeyRuntimeConfig(
            enabled=False,
            prefix_keysym=0,
            prefix_alt_keysyms=set(),
            prefix_keycodes=set(),
            prefix_modifier_mask=0,
            timeout_seconds=0.0,
            action_keysyms_to_context={},
            action_keycodes_to_context={},
        )

    timeout_seconds: float = max(0.1, jump_cfg.timeout_ms / 1000.0)
    logger.info(
        "Jump hotkey enabled: prefix=%s+%s timeout_ms=%s",
        "+".join(jump_cfg.prefix_modifiers) or "(none)",
        jump_cfg.prefix_key,
        jump_cfg.timeout_ms,
    )
    return JumpHotkeyRuntimeConfig(
        enabled=True,
        prefix_keysym=prefix_keysym,
        prefix_alt_keysyms=prefixAltKeysymsFromKeyName_get(jump_cfg.prefix_key),
        prefix_keycodes=keycodeFallbacksFromKeyName_get(jump_cfg.prefix_key),
        prefix_modifier_mask=prefix_modifier_mask,
        timeout_seconds=timeout_seconds,
        action_keysyms_to_context=action_keysyms_to_context,
        action_keycodes_to_context=action_keycodes_to_context,
    )


def jumpHotkeyEvents_process(
    input_events: list[InputEvent],
    modifier_state: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    runtime_state: RuntimeStateProtocol = server_state,
) -> tuple[list[InputEvent], ScreenContext | None]:
    """
    Process jump-hotkey prefix sequence and filter consumed key events.

    Args:
        input_events: Captured input events.
        modifier_state: Current modifier state fallback.
        jump_hotkey: Parsed jump-hotkey runtime config.

    Returns:
        Tuple of (filtered_events, target_context_or_none).
    """
    return jumpHotkeyStatePolicy.jumpHotkeyEvents_process(
        input_events=input_events,
        modifier_state=modifier_state,
        jump_hotkey=jump_hotkey,
        runtime_state=runtime_state,
        logger=logger,
    )


def state_revertToCenter(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    pointer_tracker: PointerTracker,
    runtime_state: RuntimeStateProtocol = server_state,
) -> None:
    """
    Emergency revert to CENTER context (restore input and cursor).

    Args:
        display_manager:
            Active display backend.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        pointer_tracker:
            Pointer tracker.
        runtime_state:
            Runtime-state instance.
    """
    recoveryStatePolicy.state_revertToCenter(
        display_manager=display_manager,
        screen_geometry=screen_geometry,
        position=position,
        pointer_tracker=pointer_tracker,
        runtime_state=runtime_state,
        logger=logger,
    )


def arguments_parse() -> argparse.Namespace:
    """
    Parse server command-line arguments.

    Returns:
        Parsed argparse namespace for server startup.
    """
    return serverCliPolicy.arguments_parse()


def logging_setup(level: str, log_format: str, log_file: Optional[str]) -> None:
    """
    Configure logging handlers and version-tagged format string.

    Args:
        level:
            Effective log level token (for example `INFO` or `DEBUG`).
        log_format:
            Base log formatter string.
        log_file:
            Optional log file path; when set, file logging is added.
    """
    serverLoggingPolicy.logging_setup(
        level=level,
        log_format=log_format,
        log_file=log_file,
    )


def clientMessage_handle(
    client: ClientConnection, message: Message, network: ServerNetwork
) -> None:
    """
    Handle one message received from a connected client.

    This handler resolves handshake metadata (name, screen dimensions),
    de-duplicates zombie clients by logical name, and applies control-plane
    messages such as explicit return-to-center requests.

    Args:
        client:
            Client connection that originated the message.
        message:
            Decoded protocol message.
        network:
            Server network state/controller.
    """
    serverHandshakePolicy.clientMessage_handle(
        client=client,
        message=message,
        network=network,
        logger=logger,
    )


def transitionCallbacksWithState_create(runtime_state: RuntimeStateProtocol) -> TransitionCallbacks:
    """
    Create transition-policy callbacks bound to one runtime-state instance.

    Args:
        runtime_state: Explicit runtime-state instance.

    Returns:
        Transition callback bundle bound to provided state.
    """
    return TransitionCallbacks(
        panicKey_check=panicKey_check,
        jumpHotkeyEvents_process=partial(
            jumpHotkeyEventsProcessWithState_bound,
            runtime_state=runtime_state,
        ),
        jumpHotkeyAction_apply=partial(
            jumpHotkeyActionApplyWithState_bound,
            runtime_state=runtime_state,
        ),
        state_revertToCenter=partial(
            stateRevertToCenterWithState_bound,
            runtime_state=runtime_state,
        ),
        remoteWarpEnforcement_apply=partial(
            remoteWarpEnforcementApplyWithState_bound,
            runtime_state=runtime_state,
        ),
        remoteInputEvents_send=partial(
            remoteInputEventsSendWithState_bound,
            runtime_state=runtime_state,
        ),
    )


def remoteWarpEnforcement_apply(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    x11native: bool,
    runtime_state: RuntimeStateProtocol = server_state,
) -> bool:
    """
    Test seam and adapter for REMOTE warp-enforcement policy.

    Args:
        display_manager: Active display backend.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        x11native: Native X11 mode flag.
        runtime_state: Runtime-state instance.

    Returns:
        True when enforcement consumed current step.
    """
    return transitionPolicy.remoteWarpEnforcement_apply(
        display_manager=display_manager,
        screen_geometry=screen_geometry,
        position=position,
        x11native=x11native,
        server_state=runtime_state,
        logger=logger,
    )


def remoteInputEvents_send(
    network: ServerNetwork,
    target_client_name: str,
    screen_geometry: Screen,
    input_events: list[InputEvent],
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    position: Position,
    runtime_state: RuntimeStateProtocol = server_state,
) -> None:
    """
    Test seam and adapter for REMOTE input-forwarding policy.

    Args:
        network: Active server network.
        target_client_name: Destination client name.
        screen_geometry: Local screen geometry.
        input_events: Captured input events.
        display_manager: Active display backend.
        pointer_tracker: Pointer tracker instance.
        position: Current pointer position.
        runtime_state: Runtime-state instance.
    """
    transitionPolicy.remoteInputEvents_send(
        network=network,
        target_client_name=target_client_name,
        screen_geometry=screen_geometry,
        input_events=input_events,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        position=position,
        state_revertToCenter=partial(
            stateRevertToCenterWithState_bound,
            runtime_state=runtime_state,
        ),
        logger=logger,
    )


def remoteContext_process(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    config: Config,
    position: Position,
    velocity: float,
    context_to_client: dict[ScreenContext, str],
    x11native: bool,
    input_capturer: InputCapturer,
    panic_keysyms: set[int],
    panic_modifiers: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    runtime_state: RuntimeStateProtocol = server_state,
) -> None:
    """
    Compatibility wrapper for one REMOTE-context processing step.

    Args:
        network: Active server network.
        display_manager: Active display backend.
        pointer_tracker: Pointer tracker.
        screen_geometry: Local screen geometry.
        config: Loaded server config.
        position: Current pointer position.
        velocity: Current pointer velocity.
        context_to_client: Context-to-client routing map.
        x11native: Native X11 mode flag.
        input_capturer: Input capture backend.
        panic_keysyms: Panic-key keysyms.
        panic_modifiers: Panic-key modifier mask.
        jump_hotkey: Parsed jump-hotkey config.
        runtime_state: Runtime-state instance.
    """
    transitionPolicy.remoteContext_process(
        network=network,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        config=config,
        position=position,
        velocity=velocity,
        context_to_client=context_to_client,
        x11native=x11native,
        input_capturer=input_capturer,
        panic_keysyms=panic_keysyms,
        panic_modifiers=panic_modifiers,
        jump_hotkey=jump_hotkey,
        callbacks=transitionCallbacksWithState_create(runtime_state),
        server_state=runtime_state,
        logger=logger,
    )


def stateRevertToCenterWithState_bound(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    pointer_tracker: PointerTracker,
    runtime_state: RuntimeStateProtocol,
) -> None:
    """
    Bind CENTER revert operation to explicit runtime state.

    Args:
        display_manager: Active display backend.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        pointer_tracker: Pointer tracker instance.
        runtime_state: Explicit runtime-state instance.
    """
    state_revertToCenter(
        display_manager=display_manager,
        screen_geometry=screen_geometry,
        position=position,
        pointer_tracker=pointer_tracker,
        runtime_state=runtime_state,
    )


def remoteWarpEnforcementApplyWithState_bound(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    x11native: bool,
    runtime_state: RuntimeStateProtocol,
) -> bool:
    """
    Bind REMOTE warp enforcement operation to explicit runtime state.

    Args:
        display_manager: Active display backend.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        x11native: Native X11 mode flag.
        runtime_state: Explicit runtime-state instance.

    Returns:
        True when warp enforcement handled current step.
    """
    return remoteWarpEnforcement_apply(
        display_manager=display_manager,
        screen_geometry=screen_geometry,
        position=position,
        x11native=x11native,
        runtime_state=runtime_state,
    )


def remoteInputEventsSendWithState_bound(
    network: ServerNetwork,
    target_client_name: str,
    screen_geometry: Screen,
    input_events: list[InputEvent],
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    position: Position,
    runtime_state: RuntimeStateProtocol,
) -> None:
    """
    Bind REMOTE input forwarding operation to explicit runtime state.

    Args:
        network: Active server network.
        target_client_name: Destination client name.
        screen_geometry: Local screen geometry.
        input_events: Captured input events.
        display_manager: Active display backend.
        pointer_tracker: Pointer tracker instance.
        position: Current pointer position.
        runtime_state: Explicit runtime-state instance.
    """
    remoteInputEvents_send(
        network=network,
        target_client_name=target_client_name,
        screen_geometry=screen_geometry,
        input_events=input_events,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        position=position,
        runtime_state=runtime_state,
    )


def centerContextProcessWithState_bound(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    position: Position,
    velocity: float,
    context_to_client: dict[ScreenContext, str],
    runtime_state: RuntimeStateProtocol,
) -> None:
    """
    Bind CENTER context processing to explicit runtime state.

    Args:
        network: Active server network.
        display_manager: Active display backend.
        pointer_tracker: Pointer tracker instance.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        velocity: Current pointer velocity.
        context_to_client: Context-to-client routing map.
        runtime_state: Explicit runtime state instance.
    """
    transitionPolicy.centerContext_process(
        network=network,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        position=position,
        velocity=velocity,
        context_to_client=context_to_client,
        server_state=runtime_state,
        logger=logger,
    )


def remoteContextProcessWithState_bound(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    config: Config,
    position: Position,
    velocity: float,
    context_to_client: dict[ScreenContext, str],
    x11native: bool,
    input_capturer: InputCapturer,
    panic_keysyms: set[int],
    panic_modifiers: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    runtime_state: RuntimeStateProtocol,
) -> None:
    """
    Bind REMOTE context processing to explicit runtime state.

    Args:
        network: Active server network.
        display_manager: Active display backend.
        pointer_tracker: Pointer tracker instance.
        screen_geometry: Local screen geometry.
        config: Loaded server config.
        position: Current pointer position.
        velocity: Current pointer velocity.
        context_to_client: Context-to-client routing map.
        x11native: Native X11 mode flag.
        input_capturer: Input capture backend.
        panic_keysyms: Panic-key keysyms.
        panic_modifiers: Panic-key modifier mask.
        jump_hotkey: Runtime jump-hotkey config.
        runtime_state: Explicit runtime state instance.
    """
    transitionPolicy.remoteContext_process(
        network=network,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        config=config,
        position=position,
        velocity=velocity,
        context_to_client=context_to_client,
        x11native=x11native,
        input_capturer=input_capturer,
        panic_keysyms=panic_keysyms,
        panic_modifiers=panic_modifiers,
        jump_hotkey=jump_hotkey,
        callbacks=transitionCallbacksWithState_create(runtime_state),
        server_state=runtime_state,
        logger=logger,
    )


def jumpHotkeyEventsProcessWithState_bound(
    input_events: list[InputEvent],
    modifier_state: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    runtime_state: RuntimeStateProtocol,
) -> tuple[list[InputEvent], ScreenContext | None]:
    """
    Bind jump-hotkey event parsing to explicit runtime state.

    Args:
        input_events: Captured input events.
        modifier_state: Fallback modifier state.
        jump_hotkey: Runtime jump-hotkey config.
        runtime_state: Explicit runtime state instance.

    Returns:
        Filtered input events and optional target context.
    """
    return jumpHotkeyEvents_process(
        input_events=input_events,
        modifier_state=modifier_state,
        jump_hotkey=jump_hotkey,
        runtime_state=runtime_state,
    )


def jumpHotkeyActionApplyWithState_bound(
    target_context: ScreenContext,
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    position: Position,
    context_to_client: dict[ScreenContext, str],
    runtime_state: RuntimeStateProtocol,
) -> bool:
    """
    Bind jump-hotkey action application to explicit runtime state.

    Args:
        target_context: Requested destination context.
        network: Active server network.
        display_manager: Active display backend.
        pointer_tracker: Pointer tracker instance.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        context_to_client: Context-to-client routing map.
        runtime_state: Explicit runtime state instance.

    Returns:
        True when action is handled.
    """
    return transitionPolicy.jumpHotkeyAction_apply(
        target_context=target_context,
        network=network,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        position=position,
        context_to_client=context_to_client,
        server_state=runtime_state,
        logger=logger,
        state_revertToCenter=partial(
            stateRevertToCenterWithState_bound,
            runtime_state=runtime_state,
        ),
    )


def _process_polling_loop(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    config: Config,
    context_to_client: dict[ScreenContext, str],
    panic_keysyms: set[int],
    panic_modifiers: int,
    x11native: bool,
    input_capturer: InputCapturer,
    jump_hotkey: JumpHotkeyConfigProtocol,
    die_on_disconnect: bool = False,
    runtime_state: RuntimeStateProtocol = server_state,
) -> None:
    """
    Bridge runtime policies into the polling-loop orchestrator.

    This adapter constructs callback/dependency bundles for
    `runtime_loop.pollingLoop_process`, preserving backward compatibility with
    existing `server_run` wiring while centralizing loop mechanics.

    Args:
        network:
            Network controller for connected clients.
        display_manager:
            Active display backend implementation.
        pointer_tracker:
            Pointer telemetry and edge detector.
        screen_geometry:
            Local screen dimensions.
        config:
            Loaded runtime configuration.
        context_to_client:
            Mapping from logical contexts to configured client names.
        panic_keysyms:
            Panic key keysyms.
        panic_modifiers:
            Panic key required modifier mask.
        x11native:
            Whether session is native X11.
        input_capturer:
            Input-event capture backend.
        jump_hotkey:
            Parsed jump-hotkey runtime config.
        die_on_disconnect:
            Whether server exits after disconnect.
    """
    callbacks = PollingLoopCallbacks(
        clientMessage_handle=clientMessage_handle,
        centerContext_process=partial(
            centerContextProcessWithState_bound,
            runtime_state=runtime_state,
        ),
        remoteContext_process=partial(
            remoteContextProcessWithState_bound,
            runtime_state=runtime_state,
        ),
        jumpHotkeyEvents_process=partial(
            jumpHotkeyEventsProcessWithState_bound,
            runtime_state=runtime_state,
        ),
        jumpHotkeyAction_apply=partial(
            jumpHotkeyActionApplyWithState_bound,
            runtime_state=runtime_state,
        ),
    )
    deps = PollingLoopDependencies(
        network=network,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        config=config,
        context_to_client=context_to_client,
        panic_keysyms=panic_keysyms,
        panic_modifiers=panic_modifiers,
        x11native=x11native,
        input_capturer=input_capturer,
        jump_hotkey=jump_hotkey,
        die_on_disconnect=die_on_disconnect,
    )
    pollingLoop_process(
        deps=deps,
        callbacks=callbacks,
        server_state=runtime_state,
        logger=logger,
    )


def server_run(args: argparse.Namespace) -> None:
    """
    Initialize and run the tx2tx server main loop.

    Startup sequence:
    1. Load config and configure logging.
    2. Resolve backend/display/input components.
    3. Establish display connection and pointer tracker.
    4. Validate client positioning and initialize network transport.
    5. Enter polling loop until shutdown or fatal error.

    Args:
        args:
            Parsed CLI argument namespace.
    """
    callbacks: ServerRunCallbacks = ServerRunCallbacks(
        panicKeyConfig_parse=panicKeyConfig_parse,
        jumpHotkeyConfig_parse=jumpHotkeyConfig_parse,
        pollingLoop_process=_process_polling_loop,
        logging_setup=logging_setup,
    )
    runtimeCoordinatorPolicy.server_run(
        args=args,
        callbacks=callbacks,
        runtime_state=server_state,
        logger=logger,
    )
