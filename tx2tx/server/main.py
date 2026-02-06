"""tx2tx server main entry point"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import NoReturn, Optional

from tx2tx import __version__
from tx2tx.common.config import ConfigLoader
from tx2tx.common.layout import ClientPosition, ScreenLayout
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
from tx2tx.input.factory import serverBackend_create
from tx2tx.protocol.message import Message, MessageBuilder, MessageType
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


def panicKeyConfig_parse(config) -> tuple[set[int], int]:
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


def _process_polling_loop(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    config, # Config object from ConfigLoader
    context_to_client: dict[ScreenContext, str],
    panic_keysyms: set[int],
    panic_modifiers: int,
    x11native: bool,
    input_capturer: InputCapturer,
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
    
    Returns:
        Result value.
    """
    # Accept new connections
    network.connections_accept()

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

            # Add hysteresis: skip boundary detection after switching to CENTER
            # This prevents immediate re-detection of boundary after cursor release
            time_since_center_switch = time.time() - server_state.last_center_switch_time

            if time_since_center_switch >= settings.HYSTERESIS_DELAY_SEC:
                # Detect boundary crossings
                transition = pointer_tracker.boundary_detect(position, screen_geometry)

                if transition:
                    # Map direction to context
                    direction_to_context = {
                        Direction.LEFT: ScreenContext.WEST,
                        Direction.RIGHT: ScreenContext.EAST,
                        Direction.TOP: ScreenContext.NORTH,
                        Direction.BOTTOM: ScreenContext.SOUTH,
                    }
                    new_context = direction_to_context.get(transition.direction)
                    if not new_context:
                        logger.error(
                            f"Invalid transition direction: {transition.direction}"
                        )
                        return

                    logger.info(
                        f"[TRANSITION] Boundary crossed: pos=({transition.position.x},{transition.position.y}), "
                        f"velocity={velocity:.1f}px/s, direction={transition.direction.value.upper()}, "
                        f"CENTER → {new_context.value.upper()}"
                    )

                    try:
                        t0 = time.time()
                        # Get target client name
                        target_client_name = context_to_client.get(new_context)
                        if not target_client_name:
                            logger.error(f"No client configured for {new_context.value}")
                            return

                        # Calculate where cursor should be warped to (Opposite Edge)
                        # We park at the far side so that coordinates sent to the client
                        # map naturally to its entry edge.
                        parking_offset = 30
                        if transition.direction == Direction.LEFT:
                            warp_pos = Position(
                                x=screen_geometry.width - parking_offset, y=transition.position.y
                            )
                        elif transition.direction == Direction.RIGHT:
                            warp_pos = Position(x=parking_offset, y=transition.position.y)
                        elif transition.direction == Direction.TOP:
                            warp_pos = Position(
                                x=transition.position.x, y=screen_geometry.height - parking_offset
                            )
                        else:  # BOTTOM
                            warp_pos = Position(x=transition.position.x, y=parking_offset)

                        # Now transition state
                        server_state.context = new_context
                        logger.debug(f"[CONTEXT] Changed to {new_context.value.upper()}")

                        # WARP (Parking): Anchor cursor near transition edge
                        logger.info(
                            f"[WARP] Parking cursor at ({warp_pos.x}, {warp_pos.y}) near {transition.direction.value} edge"
                        )
                        display_manager.cursorPosition_set(warp_pos)
                        logger.info("[TIMING] cursorPosition_set: %.3f sec", time.time() - t0)
                        t0 = time.time()
                        
                        # Grab input (may fail - handle gracefully)
                        try:
                            display_manager.pointer_grab()
                            display_manager.keyboard_grab()
                        except RuntimeError as e:
                            logger.warning(f"Input grab failed: {e}, continuing anyway")
                        logger.info("[TIMING] input_grab: %.3f sec", time.time() - t0)
                        t0 = time.time()

                        # Hide cursor
                        display_manager.cursor_hide()
                        logger.info("[TIMING] cursor_hide: %.3f sec", time.time() - t0)

                        # Reset velocity tracker and last sent position
                        pointer_tracker.reset()
                        server_state.last_sent_position = (
                            None  # Ensure first position in new context is sent
                        )
                        server_state.last_remote_switch_time = time.time()

                        logger.info(f"[STATE] → {new_context.value.upper()} context")

                    except Exception as e:
                        # Cleanup on error
                        logger.error(f"Transition failed: {e}", exc_info=True)
                        try:
                            display_manager.keyboard_ungrab()
                            display_manager.pointer_ungrab()
                            display_manager.cursor_show()
                        except Exception:
                            pass
                        server_state.context = ScreenContext.CENTER
                        server_state.last_center_switch_time = (
                            time.time()
                        )  # Prevent rapid re-entry
                        logger.warning("Reverted to CENTER after failed transition")

        elif server_state.context != ScreenContext.CENTER:
            # In REMOTE mode - Server Authoritative Return Logic
            target_client_name = context_to_client.get(server_state.context)

            # 0. WARP ENFORCEMENT (Grace Period)
            # Only needed on Crostini where warp is unreliable
            # On native X11, pointer grab prevents mouse movement (position still updates but cursor doesn't move)
            if not (x11native or display_manager.session_isNative_check()):
                if (time.time() - server_state.last_remote_switch_time) < 0.5:
                    # Determine where we SHOULD be
                    target_pos = None
                    if server_state.context == ScreenContext.WEST:
                        target_pos = Position(x=screen_geometry.width - 3, y=position.y)
                    elif server_state.context == ScreenContext.EAST:
                        target_pos = Position(x=2, y=position.y)

                    # Only checking WEST/EAST for now as they are primary use cases
                    if target_pos:
                        # If we are far from target (e.g. at wrong edge), re-warp
                        if abs(position.x - target_pos.x) > 100:
                            logger.info(f"[ENFORCE] Cursor at ({position.x},{position.y}), enforcing warp to ({target_pos.x},{target_pos.y})")
                            display_manager.cursorPosition_set(target_pos)
                            # Skip return check this iteration to allow warp to take effect
                            time.sleep(0.01)
                            return  # Exit function early, don't check return yet

            # 1. Check for Return Condition
            # Determine which edge triggers return based on current context
            should_return = False

            if server_state.context == ScreenContext.WEST:
                # West Client: Return when hitting RIGHT edge of server screen
                should_return = position.x >= screen_geometry.width - 1
            elif server_state.context == ScreenContext.EAST:
                # East Client: Return when hitting LEFT edge
                should_return = position.x <= 0
            elif server_state.context == ScreenContext.NORTH:
                # North Client: Return when hitting BOTTOM edge
                should_return = position.y >= screen_geometry.height - 1
            elif server_state.context == ScreenContext.SOUTH:
                # South Client: Return when hitting TOP edge
                should_return = position.y <= 0

            # Check velocity for return (to prevent accidental triggers)
            # Use lower threshold for return to make it feel natural
            if should_return and velocity >= (config.server.velocity_threshold * 0.5):
                logger.info(
                    f"[BOUNDARY] Returning from {server_state.context.value.upper()} at ({position.x}, {position.y})"
                )

                try:
                    # 1. Send Hide Signal to Client
                    if target_client_name:
                        hide_event = MouseEvent(
                            event_type=EventType.MOUSE_MOVE,
                            normalized_point=NormalizedPoint(x=-1.0, y=-1.0),
                        )
                        hide_msg = MessageBuilder.mouseEventMessage_create(hide_event)
                        # We try to send it, but if it fails we still need to revert local state
                        network.messageToClient_send(target_client_name, hide_msg)

                    # 2. Revert State (Restore desktop)
                    state_revertToCenter(
                        display_manager, screen_geometry, position, pointer_tracker
                    )

                except Exception as e:
                    logger.error(f"Return transition failed: {e}", exc_info=True)
                    # Emergency cleanup
                    server_state.context = ScreenContext.CENTER
                    try:
                        display_manager.cursor_show()
                        display_manager.keyboard_ungrab()
                        display_manager.pointer_ungrab()
                    except Exception:
                        pass
            else:
                if target_client_name:
                    # Not returning - Send events to active client ONLY if position changed
                    if server_state.positionChanged_check(position):
                        logger.info(
                            f"[MOUSE] Sending pos ({position.x}, {position.y}) to {target_client_name}"
                        )
                        normalized_point = screen_geometry.coordinates_normalize(position)

                        mouse_event = MouseEvent(
                            event_type=EventType.MOUSE_MOVE,
                            normalized_point=normalized_point,
                        )
                        move_msg = MessageBuilder.mouseEventMessage_create(mouse_event)

                        # If sending fails, revert to CENTER
                        if not network.messageToClient_send(target_client_name, move_msg):
                            connected_names = [c.name for c in network.clients]
                            logger.error(
                                f"Failed to send movement to '{target_client_name}'. Connected clients: {connected_names}. Reverting."
                            )
                            state_revertToCenter(
                                display_manager, screen_geometry, position, pointer_tracker
                            )
                            return

                        # Update last sent position
                        server_state.lastSentPosition_update(position)

                    # Send Input Events (Buttons & Keys)
                    input_events, modifier_state = input_capturer.inputEvents_read()

                    # Check for panic key - configurable escape hatch
                    if panicKey_check(
                        input_events, panic_keysyms, panic_modifiers, modifier_state
                    ):
                        logger.warning(
                            "[PANIC] Panic key pressed - forcing return to CENTER"
                        )
                        state_revertToCenter(
                            display_manager, screen_geometry, position, pointer_tracker
                        )
                        return

                    for event in input_events:
                        msg = None
                        if isinstance(event, MouseEvent):
                            # Normalize position for button events
                            if event.position:
                                norm_pos = screen_geometry.coordinates_normalize(event.position)
                                # Create new event with normalized point
                                norm_event = MouseEvent(
                                    event_type=event.event_type,
                                    normalized_point=norm_pos,
                                    button=event.button,
                                )
                                msg = MessageBuilder.mouseEventMessage_create(norm_event)
                                logger.debug(
                                    f"[BUTTON] {event.event_type.value} button={event.button}"
                                )
                        elif isinstance(event, KeyEvent):
                            msg = MessageBuilder.keyEventMessage_create(event)
                            logger.debug(
                                f"[KEY] {event.event_type.value} keycode={event.keycode}"
                            )

                        if msg:
                            if not network.messageToClient_send(target_client_name, msg):
                                logger.error(
                                    f"Failed to send {event.event_type.value} to {target_client_name}"
                                )
                                # We don't break/continue here, the next loop iteration will handle it if move fails
                                # but actually we should probably revert now.
                                state_revertToCenter(
                                    display_manager,
                                    screen_geometry,
                                    position,
                                    pointer_tracker,
                                )
                                break
                else:
                    # Drain events if no client connected but in remote mode
                    _, _ = input_capturer.inputEvents_read()
                    logger.error(
                        f"Active context {server_state.context.value} has no connected client, reverting"
                    )
                    state_revertToCenter(
                        display_manager, screen_geometry, position, pointer_tracker
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
    # Load configuration
    config_path = Path(args.config) if args.config else None

    try:
        config = ConfigLoader.configWithOverrides_load(
            file_path=config_path,
            name=args.name,
            host=args.host,
            port=args.port,
            edge_threshold=args.edge_threshold,
            display=args.display,
            overlay_enabled=getattr(args, "overlay_enabled", None),
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Create a config.yml file or specify path with --config", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    # Initialize settings singleton with loaded config
    settings.initialize(config)

    # Setup logging
    logging_setup(config.logging.level, config.logging.format, config.logging.file)

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

    # Parse panic key configuration
    panic_keysyms, panic_modifiers = panicKeyConfig_parse(config)

    # Determine overlay and x11native settings
    # Priority: CLI args > config file
    x11native = getattr(args, "x11native", False)
    if x11native:
        overlay_enabled = False  # Force disable overlay on native X11
        logger.info("Native X11 mode enabled (--x11native)")
    else:
        overlay_enabled = getattr(args, "overlay_enabled", None)
        if overlay_enabled is None:
            overlay_enabled = config.server.overlay_enabled  # Use config default
        if overlay_enabled:
            logger.info("Overlay window enabled (Crostini mode)")

    backend_name = getattr(args, "backend", None) or config.backend.name or "x11"
    if backend_name.lower() not in {"x11", "wayland"}:
        logger.error(f"Unsupported backend '{backend_name}'. Supported: x11, wayland.")
        sys.exit(1)
    logger.info(f"Backend: {backend_name}")
    wayland_helper = getattr(args, "wayland_helper", None) or config.backend.wayland.helper_command
    if backend_name.lower() == "wayland" and not wayland_helper:
        logger.error(
            "Wayland backend requires a helper command. "
            "Provide --wayland-helper or set backend.wayland.helper_command in config."
        )
        sys.exit(1)
    wayland_screen_width = (
        getattr(args, "wayland_screen_width", None) or config.backend.wayland.screen_width
    )
    wayland_screen_height = (
        getattr(args, "wayland_screen_height", None) or config.backend.wayland.screen_height
    )
    wayland_calibrate = getattr(args, "wayland_calibrate", False) or config.backend.wayland.calibrate
    wayland_pointer_provider = (
        getattr(args, "wayland_pointer_provider", None)
        or config.backend.wayland.pointer_provider
        or "helper"
    ).lower()
    if wayland_pointer_provider not in {"helper", "gnome"}:
        logger.error(
            "Unsupported Wayland pointer provider '%s'. Supported: helper, gnome.",
            wayland_pointer_provider,
        )
        sys.exit(1)
    if backend_name.lower() == "wayland":
        logger.info("Wayland pointer provider: %s", wayland_pointer_provider)

    # Initialize backend display and input capture
    display_manager, input_capturer = serverBackend_create(
        backend_name=backend_name,
        display_name=config.server.display,
        overlay_enabled=overlay_enabled,
        x11native=x11native,
        wayland_helper=wayland_helper,
        wayland_screen_width=wayland_screen_width,
        wayland_screen_height=wayland_screen_height,
        wayland_pointer_provider=wayland_pointer_provider,
    )

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

    # Initialize screen layout for coordinate transformations
    try:
        client_position = ClientPosition(config.server.client_position)
        screen_layout = ScreenLayout(client_position=client_position)
        logger.info(f"Client position: {client_position.value}")
    except ValueError:
        logger.error(f"Invalid client_position in config: {config.server.client_position}")
        sys.exit(1)

    # Initialize network server
    network = ServerNetwork(
        host=config.server.host, port=config.server.port, max_clients=config.server.max_clients
    )

    # Map context to client name
    context_to_client = {}
    if config.clients:
        for client_cfg in config.clients:
            try:
                ctx = ScreenContext(client_cfg.position.lower())
                # Normalize name to lowercase
                context_to_client[ctx] = client_cfg.name.lower()
            except ValueError:
                logger.warning(
                    f"Invalid position '{client_cfg.position}' for client {client_cfg.name}"
                )

    # Reset server state singleton to initial values
    server_state.reset()

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
            )
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise
    finally:
        network.server_stop()
        display_manager.connection_close()

def main() -> NoReturn:
    """
    Main entry point
    
    Args:
        None.
    
    Returns:
        Result value.
    """
    """Main entry point"""
    args = arguments_parse()

    try:
        server_run(args)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
