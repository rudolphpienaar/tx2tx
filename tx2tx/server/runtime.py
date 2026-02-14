"""tx2tx server main entry point"""

import argparse
import logging
import sys
import time
from typing import Optional

from tx2tx import __version__
from tx2tx.common.config import Config
from tx2tx.common.layout import ClientPosition
from tx2tx.common.runtime_models import ServerBackendOptions
from tx2tx.common.settings import settings
from tx2tx.common.types import (
    Direction,
    EventType,
    KeyEvent,
    MouseEvent,
    NormalizedPoint,
    Position,
    Screen,
    ScreenContext,
)
from tx2tx.input.backend import DisplayBackend, InputCapturer, InputEvent
from tx2tx.protocol.message import Message, MessageBuilder, MessageType
from tx2tx.server.bootstrap import (
    backendOptions_resolve,
    configWithSettings_load,
    contextToClientMap_build,
    loggingWithConfig_setup,
    serverBackendComponents_create,
)
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.server.state import server_state
from tx2tx.x11.pointer import PointerTracker

logger = logging.getLogger(__name__)

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


def panicKeyConfig_parse(config: Config) -> tuple[set[int], int]:
    """
    Parse panic key configuration into keysym set and modifier mask.
    
    Args:
        config: The loaded Config object
    
    Returns:
        Tuple of (keysym_set, required_modifier_mask)
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
    Check if any event in the list is a panic key press.
    
    
    
    
    The panic key forces immediate return to CENTER context, providing
    an escape hatch if the client dies or the user gets stuck.
    
    Args:
        events: List of input events to check
        panic_keysyms: Set of keysyms that trigger panic
        required_modifiers: Modifier mask that must be active
        current_modifiers: Currently active modifier mask (fallback)
    
    Returns:
        True if a panic key press was detected
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


def state_revertToCenter(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    pointer_tracker: PointerTracker,
) -> None:
    """
    Emergency revert to CENTER context (restore input and cursor)
    
    Args:
        display_manager: display_manager value.
        screen_geometry: screen_geometry value.
        position: position value.
        pointer_tracker: pointer_tracker value.
    
    Returns:
        Result value.
    """
    if server_state.context == ScreenContext.CENTER:
        return

    logger.warning(f"[SAFETY] Reverting from {server_state.context.value.upper()} to CENTER")

    # Clear boundary crossing state and last sent position
    server_state.boundaryCrossed_clear()
    server_state.last_sent_position = None  # Reset so next context sends first position
    server_state.active_remote_client_name = None

    prev_context = server_state.context
    server_state.context = ScreenContext.CENTER
    server_state.last_center_switch_time = time.time()

    # Calculate Entry Position (Inverse of Exit)
    # Use a safe offset (30px) to ensure we are clearly 'inside' the screen.
    offset = 30
    if prev_context == ScreenContext.WEST:
        entry_pos = Position(x=offset, y=position.y)
    elif prev_context == ScreenContext.EAST:
        entry_pos = Position(x=screen_geometry.width - offset, y=position.y)
    elif prev_context == ScreenContext.NORTH:
        entry_pos = Position(x=position.x, y=offset)
    else:  # SOUTH
        entry_pos = Position(x=position.x, y=screen_geometry.height - offset)

    try:
        # 1. Ungrab FIRST: Release control back to the OS.
        try:
            display_manager.keyboard_ungrab()
            display_manager.pointer_ungrab()
            display_manager.connection_sync()
            # Give OS a moment to 'register' the ungrabbed state.
            time.sleep(0.05)
        except Exception as e:
            logger.warning(f"Ungrab failed: {e}")

        # 2. Show cursor: Ensure it is visible before we move it.
        # This prevents WMs from ignoring warps on hidden cursors.
        display_manager.cursor_show()
        display_manager.connection_sync()
        time.sleep(0.05)

        # 3. Final Warp: Teleport to the correct edge.
        # Now that we are ungrabbed and visible, this is guaranteed to work.
        try:
            logger.info(f"[WARP RETURN] Teleporting to entry position ({entry_pos.x}, {entry_pos.y})")
            display_manager.cursorPosition_set(entry_pos)
            display_manager.connection_sync()
        except Exception as e:
            logger.error(f"Warp failed during revert: {e}")

        # Reset tracker to prevent velocity spike from triggering immediate re-entry
        pointer_tracker.reset()

        logger.info(f"[STATE] → CENTER (revert) - Cursor at ({entry_pos.x}, {entry_pos.y})")
    except Exception as e:
        logger.error(f"Emergency revert failed: {e}")
        # Last ditch effort to unlock desktop
        try:
            display_manager.cursor_show()
            display_manager.keyboard_ungrab()
            display_manager.pointer_ungrab()
        except Exception:
            pass


def arguments_parse() -> argparse.Namespace:
    """
    Parse command line arguments
    
    Args:
        None.
    
    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="tx2tx server - captures and broadcasts input events"
    )

    parser.add_argument("--version", action="version", version=f"tx2tx {__version__}")

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: search standard locations)",
    )

    parser.add_argument(
        "--host", type=str, default=None, help="Host address to bind to (overrides config)"
    )

    parser.add_argument(
        "--port", type=int, default=None, help="Port to listen on (overrides config)"
    )

    parser.add_argument(
        "--edge-threshold",
        type=int,
        default=None,
        dest="edge_threshold",
        help="Pixels from edge to trigger screen transition (overrides config)",
    )

    parser.add_argument(
        "--display", type=str, default=None, help="X11 display name (overrides config)"
    )

    parser.add_argument(
        "--backend",
        type=str,
        default=None,
        help="Input backend to use (e.g., x11, wayland). Defaults to x11.",
    )

    parser.add_argument(
        "--wayland-helper",
        type=str,
        default=None,
        help="Wayland helper command for privileged input operations.",
    )

    parser.add_argument(
        "--wayland-screen-width",
        type=int,
        default=None,
        help="Wayland screen width override (pixels).",
    )

    parser.add_argument(
        "--wayland-screen-height",
        type=int,
        default=None,
        help="Wayland screen height override (pixels).",
    )

    parser.add_argument(
        "--wayland-calibrate",
        action="store_true",
        help="Wayland: warp cursor to center on startup to sync helper state.",
    )

    parser.add_argument(
        "--wayland-pointer-provider",
        type=str,
        choices=["helper", "gnome"],
        default=None,
        help="Wayland pointer coordinate provider (default: helper).",
    )

    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Server name for logging and identification (default: from config)",
    )

    return parser.parse_args()


def logging_setup(level: str, log_format: str, log_file: Optional[str]) -> None:
    """
    Setup logging configuration with version injection
    
    Args:
        level: level value.
        log_format: log_format value.
        log_file: log_file value.
    
    Returns:
        Result value.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    # Inject version and commit hash into log format after timestamp
    # Format: "%(asctime)s [v2.0.3.c0f8] - %(name)s - %(levelname)s - %(message)s"
    enhanced_format = log_format.replace("%(asctime)s", f"%(asctime)s [v{__version__}]")

    logging.basicConfig(
        level=getattr(logging, level.upper()), format=enhanced_format, handlers=handlers
    )


def clientMessage_handle(
    client: ClientConnection, message: Message, network: ServerNetwork
) -> None:
    """
    Handle message received from client
    
    Args:
        client: client value.
        message: message value.
        network: network value.
    
    Returns:
        Result value.
    """
    logger.info(f"Received {message.msg_type.value} from {client.address}")

    if message.msg_type == MessageType.HELLO:
        # Parse and store client screen geometry from handshake
        payload = message.payload
        if "screen_width" in payload and "screen_height" in payload:
            client.screen_width = payload["screen_width"]
            client.screen_height = payload["screen_height"]

        if "client_name" in payload:
            # Normalize name to lowercase for consistent matching
            new_name = payload["client_name"].lower()
            client.name = new_name

            # Check for existing clients with same name (Zombie detection)
            # We iterate over a copy since we might modify the list
            for existing_client in list(network.clients):
                if existing_client is not client and existing_client.name == new_name:
                    logger.warning(
                        f"Duplicate client name '{new_name}' detected. "
                        f"Disconnecting old connection from {existing_client.address}."
                    )
                    network.client_disconnect(existing_client)

        logger.info(
            f"Client handshake: version={payload.get('version')}, "
            f"screen={client.screen_width}x{client.screen_height}, "
            f"name={client.name}"
        )
    elif message.msg_type == MessageType.KEEPALIVE:
        logger.debug("Keepalive received")
    elif message.msg_type == MessageType.SCREEN_ENTER:
        logger.warning("Received deprecated SCREEN_ENTER message from client (ignored)")
    else:
        logger.warning(f"Unexpected message type: {message.msg_type.value}")


def centerContext_process(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    position: Position,
    velocity: float,
    context_to_client: dict[ScreenContext, str],
) -> None:
    """
    Process boundary transition logic while server is in CENTER context.

    Args:
        network: Active server network.
        display_manager: Server display backend.
        pointer_tracker: Pointer tracker.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        velocity: Current pointer velocity.
        context_to_client: Context-to-client routing map.
    """
    time_since_center_switch: float = time.time() - server_state.last_center_switch_time
    if time_since_center_switch < settings.HYSTERESIS_DELAY_SEC:
        return

    transition = pointer_tracker.boundary_detect(position, screen_geometry)
    if transition is None:
        return

    new_context: ScreenContext | None = contextFromDirection_get(transition.direction)
    if new_context is None:
        logger.error(f"Invalid transition direction: {transition.direction}")
        return

    logger.info(
        f"[TRANSITION] Boundary crossed: pos=({transition.position.x},{transition.position.y}), "
        f"velocity={velocity:.1f}px/s, direction={transition.direction.value.upper()}, "
        f"CENTER → {new_context.value.upper()}"
    )

    try:
        t0: float = time.time()
        resolved_target = transitionTargetClient_resolve(network, new_context, context_to_client)
        if resolved_target is None:
            return
        target_client_name: str = resolved_target[0]
        target_client: ClientConnection = resolved_target[1]
        warp_pos: Position = transitionParkingPosition_get(
            transition.direction, transition.position, screen_geometry
        )

        server_state.context = new_context
        server_state.active_remote_client_name = target_client.name or target_client_name
        logger.debug(f"[CONTEXT] Changed to {new_context.value.upper()}")

        logger.info(
            f"[WARP] Parking cursor at ({warp_pos.x}, {warp_pos.y}) near {transition.direction.value} edge"
        )
        display_manager.cursorPosition_set(warp_pos)
        logger.info("[TIMING] cursorPosition_set: %.3f sec", time.time() - t0)
        t0 = time.time()

        display_manager.pointer_grab()
        display_manager.keyboard_grab()
        logger.info("[TIMING] input_grab: %.3f sec", time.time() - t0)
        t0 = time.time()

        display_manager.cursor_hide()
        logger.info("[TIMING] cursor_hide: %.3f sec", time.time() - t0)

        pointer_tracker.reset()
        server_state.last_sent_position = None
        server_state.last_remote_switch_time = time.time()
        logger.info(f"[STATE] → {new_context.value.upper()} context")
    except Exception as e:
        logger.error(f"Transition failed: {e}", exc_info=True)
        try:
            display_manager.keyboard_ungrab()
            display_manager.pointer_ungrab()
            display_manager.cursor_show()
        except Exception:
            pass
        server_state.context = ScreenContext.CENTER
        server_state.active_remote_client_name = None
        server_state.last_center_switch_time = time.time()
        logger.warning("Reverted to CENTER after failed transition")


def contextFromDirection_get(direction: Direction) -> ScreenContext | None:
    """
    Map pointer boundary direction to screen context.

    Args:
        direction: Transition direction.

    Returns:
        Target screen context or None.
    """
    direction_to_context: dict[Direction, ScreenContext] = {
        Direction.LEFT: ScreenContext.WEST,
        Direction.RIGHT: ScreenContext.EAST,
        Direction.TOP: ScreenContext.NORTH,
        Direction.BOTTOM: ScreenContext.SOUTH,
    }
    return direction_to_context.get(direction)


def transitionTargetClient_resolve(
    network: ServerNetwork,
    new_context: ScreenContext,
    context_to_client: dict[ScreenContext, str],
) -> tuple[str, ClientConnection] | None:
    """
    Resolve target client for a context transition.

    Args:
        network: Active server network.
        new_context: Transition target context.
        context_to_client: Context-to-client routing map.

    Returns:
        Tuple of (target_client_name, target_connection) or None.
    """
    target_client_name: str | None = context_to_client.get(new_context)
    if not target_client_name:
        logger.error(f"No client configured for {new_context.value}")
        return None
    target_client: ClientConnection | None = network.clientByName_get(target_client_name)
    if target_client is None:
        connected_names: list[str | None] = [client.name for client in network.clients]
        logger.error(
            "Transition blocked: target '%s' unresolved. Connected clients: %s",
            target_client_name,
            connected_names,
        )
        return None
    return target_client_name, target_client


def transitionParkingPosition_get(
    direction: Direction, transition_position: Position, screen_geometry: Screen
) -> Position:
    """
    Compute local parking position after CENTER->REMOTE transition.

    Args:
        direction: Transition direction.
        transition_position: Position at transition edge.
        screen_geometry: Local screen geometry.

    Returns:
        Parking cursor position.
    """
    parking_offset: int = 30
    if direction == Direction.LEFT:
        return Position(x=screen_geometry.width - parking_offset, y=transition_position.y)
    if direction == Direction.RIGHT:
        return Position(x=parking_offset, y=transition_position.y)
    if direction == Direction.TOP:
        return Position(x=transition_position.x, y=screen_geometry.height - parking_offset)
    return Position(x=transition_position.x, y=parking_offset)


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
) -> None:
    """
    Process forwarding/return logic while server is in REMOTE context.

    Args:
        network: Active server network.
        display_manager: Server display backend.
        pointer_tracker: Pointer tracker.
        screen_geometry: Local screen geometry.
        config: Loaded config.
        position: Current pointer position.
        velocity: Current pointer velocity.
        context_to_client: Context-to-client routing map.
        x11native: Native X11 mode flag.
        input_capturer: Input capture backend.
        panic_keysyms: Panic key keysyms.
        panic_modifiers: Panic key modifier mask.
    """
    target_client_name: str | None = remoteTargetClientName_get(context_to_client)

    if remoteWarpEnforcement_apply(
        display_manager=display_manager,
        screen_geometry=screen_geometry,
        position=position,
        x11native=x11native,
    ):
        return

    should_return: bool = remoteReturnBoundary_check(server_state.context, position, screen_geometry)
    if should_return and velocity >= (config.server.velocity_threshold * 0.5):
        remoteReturn_process(
            network=network,
            target_client_name=target_client_name,
            display_manager=display_manager,
            screen_geometry=screen_geometry,
            position=position,
            pointer_tracker=pointer_tracker,
        )
        return

    if not target_client_name:
        _, _ = input_capturer.inputEvents_read()
        logger.error(
            f"Active context {server_state.context.value} has no connected client, reverting"
        )
        state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
        return

    if not remoteMotionPosition_send(
        network=network,
        target_client_name=target_client_name,
        screen_geometry=screen_geometry,
        position=position,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
    ):
        return

    input_events, modifier_state = input_capturer.inputEvents_read()
    if panicKey_check(input_events, panic_keysyms, panic_modifiers, modifier_state):
        logger.warning("[PANIC] Panic key pressed - forcing return to CENTER")
        state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
        return

    remoteInputEvents_send(
        network=network,
        target_client_name=target_client_name,
        screen_geometry=screen_geometry,
        input_events=input_events,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        position=position,
    )


def remoteTargetClientName_get(context_to_client: dict[ScreenContext, str]) -> str | None:
    """
    Resolve active remote target client name from server state.

    Args:
        context_to_client: Context-to-client routing map.

    Returns:
        Target client name or None.
    """
    return server_state.active_remote_client_name or context_to_client.get(server_state.context)


def remoteWarpEnforcement_apply(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    x11native: bool,
) -> bool:
    """
    Apply early REMOTE warp enforcement when compositor may drift pointer.

    Args:
        display_manager: Server display backend.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        x11native: Native X11 mode flag.

    Returns:
        True when enforcement warped and caller should return early.
    """
    if x11native or display_manager.session_isNative_check():
        return False
    if (time.time() - server_state.last_remote_switch_time) >= 0.5:
        return False
    target_pos: Position | None = None
    if server_state.context == ScreenContext.WEST:
        target_pos = Position(x=screen_geometry.width - 3, y=position.y)
    elif server_state.context == ScreenContext.EAST:
        target_pos = Position(x=2, y=position.y)
    if target_pos is None or abs(position.x - target_pos.x) <= 100:
        return False
    logger.info(
        f"[ENFORCE] Cursor at ({position.x},{position.y}), enforcing warp to ({target_pos.x},{target_pos.y})"
    )
    display_manager.cursorPosition_set(target_pos)
    time.sleep(0.01)
    return True


def remoteReturn_process(
    network: ServerNetwork,
    target_client_name: str | None,
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    pointer_tracker: PointerTracker,
) -> None:
    """
    Process REMOTE->CENTER return sequence.

    Args:
        network: Active server network.
        target_client_name: Active target client name.
        display_manager: Server display backend.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        pointer_tracker: Pointer tracker.
    """
    logger.info(
        f"[BOUNDARY] Returning from {server_state.context.value.upper()} at ({position.x}, {position.y})"
    )
    try:
        if target_client_name:
            hide_event = MouseEvent(
                event_type=EventType.MOUSE_MOVE,
                normalized_point=NormalizedPoint(x=-1.0, y=-1.0),
            )
            hide_msg = MessageBuilder.mouseEventMessage_create(hide_event)
            network.messageToClient_send(target_client_name, hide_msg)
        state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
    except Exception as e:
        logger.error(f"Return transition failed: {e}", exc_info=True)
        server_state.context = ScreenContext.CENTER
        try:
            display_manager.cursor_show()
            display_manager.keyboard_ungrab()
            display_manager.pointer_ungrab()
        except Exception:
            pass


def remoteMotionPosition_send(
    network: ServerNetwork,
    target_client_name: str,
    screen_geometry: Screen,
    position: Position,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
) -> bool:
    """
    Send pointer position update to active remote client if changed.

    Args:
        network: Active server network.
        target_client_name: Destination client name.
        screen_geometry: Local screen geometry.
        position: Current pointer position.
        display_manager: Server display backend.
        pointer_tracker: Pointer tracker.

    Returns:
        True when caller can continue processing.
    """
    if not server_state.positionChanged_check(position):
        return True
    logger.debug(f"[MOUSE] Sending pos ({position.x}, {position.y}) to {target_client_name}")
    normalized_point = screen_geometry.coordinates_normalize(position)
    mouse_event = MouseEvent(
        event_type=EventType.MOUSE_MOVE,
        normalized_point=normalized_point,
    )
    move_msg = MessageBuilder.mouseEventMessage_create(mouse_event)
    if network.messageToClient_send(target_client_name, move_msg):
        server_state.lastSentPosition_update(position)
        return True
    connected_names = [client.name for client in network.clients]
    logger.error(
        f"Failed to send movement to '{target_client_name}'. Connected clients: {connected_names}. Reverting."
    )
    state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
    return False


def remoteReturnBoundary_check(
    context: ScreenContext, position: Position, screen_geometry: Screen
) -> bool:
    """
    Check whether current pointer position hits return boundary for active context.

    Args:
        context: Active remote context.
        position: Current pointer position.
        screen_geometry: Local screen geometry.

    Returns:
        True when return boundary is reached.
    """
    if context == ScreenContext.WEST:
        return position.x >= screen_geometry.width - 1
    if context == ScreenContext.EAST:
        return position.x <= 0
    if context == ScreenContext.NORTH:
        return position.y >= screen_geometry.height - 1
    if context == ScreenContext.SOUTH:
        return position.y <= 0
    return False


def remoteInputEvents_send(
    network: ServerNetwork,
    target_client_name: str,
    screen_geometry: Screen,
    input_events: list[InputEvent],
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    position: Position,
) -> None:
    """
    Forward captured mouse/key input events to active remote client.

    Args:
        network: Active server network.
        target_client_name: Destination client name.
        screen_geometry: Local screen geometry.
        input_events: Captured input event list.
        display_manager: Server display backend.
        pointer_tracker: Pointer tracker.
        position: Current pointer position.
    """
    for event in input_events:
        msg: Message | None = None
        if isinstance(event, MouseEvent) and event.position:
            norm_pos = screen_geometry.coordinates_normalize(event.position)
            norm_event = MouseEvent(
                event_type=event.event_type,
                normalized_point=norm_pos,
                button=event.button,
            )
            msg = MessageBuilder.mouseEventMessage_create(norm_event)
            logger.debug(f"[BUTTON] {event.event_type.value} button={event.button}")
        elif isinstance(event, KeyEvent):
            msg = MessageBuilder.keyEventMessage_create(event)
            logger.debug(f"[KEY] {event.event_type.value} keycode={event.keycode}")

        if msg and not network.messageToClient_send(target_client_name, msg):
            logger.error(f"Failed to send {event.event_type.value} to {target_client_name}")
            state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
            break


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
    die_on_disconnect: bool = False,
) -> None:
    """
    Processes events in the polling loop (fallback mode).
    
    Args:
        network: network value.
        display_manager: display_manager value.
        pointer_tracker: pointer_tracker value.
        screen_geometry: screen_geometry value.
        config: config value.
        context_to_client: context_to_client value.
        panic_keysyms: panic_keysyms value.
        panic_modifiers: panic_modifiers value.
        x11native: x11native value.
        input_capturer: input_capturer value.
        die_on_disconnect: die_on_disconnect value.
    
    Returns:
        Result value.
    """
    # Accept new connections
    network.connections_accept()

    # Track client count for --die-on-disconnect
    initial_client_count = network.clients_count()

    # Receive messages from clients
    def message_handler(client: ClientConnection, message: Message) -> None:
        """
        Handle a single client message within the polling loop.
        
        Args:
            client: client value.
            message: message value.
        
        Returns:
            Result value.
        """
        clientMessage_handle(client, message, network)

    network.clientData_receive(message_handler)

    # If --die-on-disconnect is set and a client disconnected, shut down
    if die_on_disconnect and network.clients_count() < initial_client_count:
        logger.warning(
            "[NETWORK] Client disconnected and --die-on-disconnect is set. Shutting down."
        )
        network.is_running = False
        return

    # Track pointer when we have clients
    if network.clients_count() > 0:
        # Poll pointer position
        position = pointer_tracker.position_query()
        velocity = pointer_tracker.velocity_calculate()
        now = time.time()
        last_pos_log = getattr(_process_polling_loop, "_last_pos_log_time", 0.0)
        if (now - last_pos_log) >= 0.5:
            logger.debug(
                "[POS] x=%s/%s y=%s/%s",
                position.x,
                screen_geometry.width - 1,
                position.y,
                screen_geometry.height - 1,
            )
            _process_polling_loop._last_pos_log_time = now
        if (
            position.x >= screen_geometry.width - 5
            or position.x <= 4
            or position.y >= screen_geometry.height - 5
            or position.y <= 4
        ):
            logger.debug(
                "[EDGE] pos=(%s,%s) vel=%.1f",
                position.x,
                position.y,
                velocity,
            )

        if server_state.context == ScreenContext.CENTER:
            centerContext_process(
                network=network,
                display_manager=display_manager,
                pointer_tracker=pointer_tracker,
                screen_geometry=screen_geometry,
                position=position,
                velocity=velocity,
                context_to_client=context_to_client,
            )
        else:
            remoteContext_process(
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
            )

    # Small sleep to prevent busy waiting
    time.sleep(config.server.poll_interval_ms / settings.POLL_INTERVAL_DIVISOR)


def server_run(args: argparse.Namespace) -> None:
    """
    Run tx2tx server
    
    Args:
        args: args value.
    
    Returns:
        Result value.
    """
    config = configWithSettings_load(args)
    loggingWithConfig_setup(args, config, logging_setup)

    logger.info(f"tx2tx server v{__version__}")
    logger.info(f"Server name: {config.server.name}")
    logger.info(f"Listening on {config.server.host}:{config.server.port}")
    logger.info(f"Edge threshold: {config.server.edge_threshold} pixels")
    logger.info(f"Velocity threshold: {config.server.velocity_threshold} px/s (edge resistance)")
    logger.info(f"Display: {config.server.display or '$DISPLAY'}")
    logger.info(f"Max clients: {config.server.max_clients}")

    # Log configured clients
    if config.clients:
        logger.info(f"Configured clients: {len(config.clients)}")
        for client in config.clients:
            logger.info(f"  - {client.name} (position: {client.position})")
    else:
        logger.warning("No clients configured in config.yml")

    panic_keysyms, panic_modifiers = panicKeyConfig_parse(config)

    backend_options: ServerBackendOptions = backendOptions_resolve(args, config)
    display_manager, input_capturer = serverBackendComponents_create(
        config=config, backend_options=backend_options
    )
    backend_name: str = backend_options.backend_name
    wayland_calibrate: bool = backend_options.wayland_calibrate
    x11native: bool = backend_options.x11native

    try:
        display_manager.connection_establish()
        screen_geometry = display_manager.screenGeometry_get()
        logger.info(f"Screen geometry: {screen_geometry.width}x{screen_geometry.height}")
        if backend_name.lower() == "wayland" and wayland_calibrate:
            center = Position(
                x=screen_geometry.width // 2,
                y=screen_geometry.height // 2,
            )
            logger.info(
                "[CALIBRATE] Warping cursor to (%s, %s) to sync helper state",
                center.x,
                center.y,
            )
            display_manager.cursorPosition_set(center)
    except Exception as e:
        logger.error(f"Failed to connect to X11 display: {e}")
        sys.exit(1)

    # Initialize pointer tracker
    pointer_tracker = PointerTracker(
        display_manager=display_manager,
        edge_threshold=config.server.edge_threshold,
        velocity_threshold=config.server.velocity_threshold,
    )
    logger.info(
        f"Pointer tracker initialized (velocity_threshold={config.server.velocity_threshold})"
    )

    # Validate configured client position
    try:
        client_position = ClientPosition(config.server.client_position)
        logger.info(f"Client position: {client_position.value}")
    except ValueError:
        logger.error(f"Invalid client_position in config: {config.server.client_position}")
        sys.exit(1)

    # Initialize network server
    network = ServerNetwork(
        host=config.server.host, port=config.server.port, max_clients=config.server.max_clients
    )

    context_to_client: dict[ScreenContext, str] = contextToClientMap_build(config)

    # Reset server state singleton to initial values
    server_state.reset()

    die_on_disconnect = getattr(args, "die_on_disconnect", False)

    try:
        network.server_start()
        logger.info("Server running. Press Ctrl+C to stop.")

        while network.is_running:
            _process_polling_loop(
                network,
                display_manager,
                pointer_tracker,
                screen_geometry,
                config,
                context_to_client,
                panic_keysyms,
                panic_modifiers,
                x11native,
                input_capturer,
                die_on_disconnect,
            )
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise
    finally:
        network.server_stop()
        display_manager.connection_close()
