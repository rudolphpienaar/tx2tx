"""tx2tx server main entry point"""

import argparse
import logging
import sys
import time
from enum import Enum
from pathlib import Path
from typing import NoReturn, Optional, Union

from Xlib import X

from tx2tx import __version__
from tx2tx.common.config import ConfigLoader
from tx2tx.common.layout import ClientPosition, ScreenLayout
from tx2tx.common.settings import settings
from tx2tx.common.types import Direction, EventType, KeyEvent, MouseEvent, NormalizedPoint, Position, Screen, ScreenContext, ScreenTransition
from tx2tx.protocol.message import Message, MessageBuilder, MessageParser, MessageType
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.x11.display import DisplayManager
from tx2tx.x11.pointer import PointerTracker

logger = logging.getLogger(__name__)


def read_input_events(display_manager: DisplayManager) -> list[Union[MouseEvent, KeyEvent]]:
    """
    Read pending X11 input events (buttons and keys)

    Args:
        display_manager: Display manager instance

    Returns:
        List of MouseEvent and KeyEvent objects
    """
    display = display_manager.display_get()
    events = []

    while display.pending_events() > 0:
        event = display.next_event()

        if event.type == X.ButtonPress:
            events.append(MouseEvent(
                event_type=EventType.MOUSE_BUTTON_PRESS,
                position=Position(x=event.root_x, y=event.root_y),
                button=event.detail
            ))
        elif event.type == X.ButtonRelease:
            events.append(MouseEvent(
                event_type=EventType.MOUSE_BUTTON_RELEASE,
                position=Position(x=event.root_x, y=event.root_y),
                button=event.detail
            ))
        elif event.type == X.KeyPress:
            events.append(KeyEvent(
                event_type=EventType.KEY_PRESS,
                keycode=event.detail,
                keysym=display.keycode_to_keysym(event.detail, 0)
            ))
        elif event.type == X.KeyRelease:
            events.append(KeyEvent(
                event_type=EventType.KEY_RELEASE,
                keycode=event.detail,
                keysym=display.keycode_to_keysym(event.detail, 0)
            ))

    return events


def arguments_parse() -> argparse.Namespace:
    """
    Parse command line arguments

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="tx2tx server - captures and broadcasts input events"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"tx2tx {__version__}"
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: search standard locations)"
    )

    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host address to bind to (overrides config)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on (overrides config)"
    )

    parser.add_argument(
        "--edge-threshold",
        type=int,
        default=None,
        dest="edge_threshold",
        help="Pixels from edge to trigger screen transition (overrides config)"
    )

    parser.add_argument(
        "--display",
        type=str,
        default=None,
        help="X11 display name (overrides config)"
    )

    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Server name for logging and identification (default: from config)"
    )

    return parser.parse_args()


def logging_setup(level: str, log_format: str, log_file: Optional[str]) -> None:
    """
    Setup logging configuration

    Args:
        level: Log level string
        log_format: Log format string
        log_file: Optional log file path
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=handlers
    )


def clientMessage_handle(
    client: ClientConnection,
    message: Message,
    context: Optional[list[ScreenContext]] = None,
    display_manager: Optional[DisplayManager] = None,
    screen_layout: Optional[ScreenLayout] = None,
    server_screen: Optional[Screen] = None,
    last_center_time: Optional[list[float]] = None
) -> None:
    """
    Handle message received from client

    Args:
        client: Client connection
        message: Received message
        context: Mutable reference [ScreenContext] to track global screen context
        display_manager: Display manager for cursor control
        screen_layout: Screen layout for coordinate transformation
        server_screen: Server screen for coordinate transformation
    """
    logger.info(f"Received {message.msg_type.value} from {client.address}")

    if message.msg_type == MessageType.HELLO:
        # Parse and store client screen geometry from handshake
        payload = message.payload
        if "screen_width" in payload and "screen_height" in payload:
            client.screen_width = payload["screen_width"]
            client.screen_height = payload["screen_height"]
        
        if "client_name" in payload:
            client.name = payload["client_name"]
            
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


def server_run(args: argparse.Namespace) -> None:
    """
    Run tx2tx server

    Args:
        args: Parsed command line arguments
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
            display=args.display
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

    # Initialize X11 display and pointer tracking
    display_manager = DisplayManager(display_name=config.server.display)

    try:
        display_manager.connection_establish()
        screen_geometry = display_manager.screenGeometry_get()
        logger.info(f"Screen geometry: {screen_geometry.width}x{screen_geometry.height}")
    except Exception as e:
        logger.error(f"Failed to connect to X11 display: {e}")
        sys.exit(1)

    # TEMP: Use very low velocity threshold for testing (bypass velocity check)
    pointer_tracker = PointerTracker(
        display_manager=display_manager,
        edge_threshold=config.server.edge_threshold,
        velocity_threshold=10.0  # TEMP: Very low threshold instead of config.server.velocity_threshold
    )
    logger.info("Pointer tracker initialized (velocity_threshold=10.0 for testing)")

    # Initialize screen layout for coordinate transformations
    try:
        client_position = ClientPosition(config.server.client_position)
        screen_layout = ScreenLayout(client_position=client_position)
        logger.info(f"Client position: {client_position.value}")
    except ValueError as e:
        logger.error(f"Invalid client_position in config: {config.server.client_position}")
        sys.exit(1)

    # Initialize network server
    network = ServerNetwork(
        host=config.server.host,
        port=config.server.port,
        max_clients=config.server.max_clients
    )

    # Map context to client name
    context_to_client = {}
    if config.clients:
        for client_cfg in config.clients:
            try:
                ctx = ScreenContext(client_cfg.position.lower())
                context_to_client[ctx] = client_cfg.name
            except ValueError:
                logger.warning(f"Invalid position '{client_cfg.position}' for client {client_cfg.name}")

    # Screen context (wrapped in list for mutable reference)
    context_ref = [ScreenContext.CENTER]
    last_center_switch_time = [0.0]  # Timestamp of last non-CENTER→CENTER switch

    try:
        network.server_start()

        # Main event loop
        logger.info("Server running. Press Ctrl+C to stop.")

        while network.is_running:
            # Accept new connections
            network.connections_accept()

            # Receive messages from clients
            def message_handler(client: ClientConnection, message: Message) -> None:
                """Handle incoming messages from clients"""
                clientMessage_handle(
                    client, message, context_ref, display_manager,
                    screen_layout, screen_geometry, last_center_switch_time
                )

            network.clientData_receive(message_handler)

            # Track pointer when we have clients
            if network.clients_count() > 0:
                # Poll pointer position
                position = pointer_tracker.position_query()
                velocity = pointer_tracker.velocity_calculate()

                if context_ref[0] == ScreenContext.CENTER:
                    # Add hysteresis: skip boundary detection after switching to CENTER
                    # This prevents immediate re-detection of boundary after cursor release
                    time_since_center_switch = time.time() - last_center_switch_time[0]

                    if time_since_center_switch >= settings.HYSTERESIS_DELAY_SEC:
                        # Detect boundary crossings
                        transition = pointer_tracker.boundary_detect(position, screen_geometry)

                        if transition:
                            # Map direction to context
                            direction_to_context = {
                                Direction.LEFT: ScreenContext.WEST,
                                Direction.RIGHT: ScreenContext.EAST,
                                Direction.TOP: ScreenContext.NORTH,
                                Direction.BOTTOM: ScreenContext.SOUTH
                            }
                            new_context = direction_to_context.get(transition.direction)
                            if not new_context:
                                logger.error(f"Invalid transition direction: {transition.direction}")
                                continue

                            logger.info(
                                f"[TRANSITION] Boundary crossed: pos=({transition.position.x},{transition.position.y}), "
                                f"velocity={velocity:.1f}px/s, direction={transition.direction.value.upper()}, "
                                f"CENTER → {new_context.value.upper()}"
                            )

                            try:
                                context_ref[0] = new_context

                                # Calculate position on OPPOSITE edge (where we enter the new context)
                                # e.g., Crossing LEFT edge means we start at RIGHT edge of new context
                                if transition.direction == Direction.LEFT:
                                    # Start at Right Edge of Server Screen (simulating Remote Screen)
                                    edge_position = Position(x=screen_geometry.width - settings.EDGE_ENTRY_OFFSET - 1, y=position.y)
                                elif transition.direction == Direction.RIGHT:
                                    edge_position = Position(x=settings.EDGE_ENTRY_OFFSET, y=position.y)
                                elif transition.direction == Direction.TOP:
                                    edge_position = Position(x=position.x, y=screen_geometry.height - settings.EDGE_ENTRY_OFFSET - 1)
                                else:  # BOTTOM
                                    edge_position = Position(x=position.x, y=settings.EDGE_ENTRY_OFFSET)

                                # 1. Hide Cursor
                                display_manager.cursor_hide()

                                # 2. Grab Input
                                display_manager.pointer_grab()
                                display_manager.keyboard_grab()

                                # 3. Reposition Cursor
                                display_manager.cursorPosition_set(edge_position)
                                logger.info(f"[CURSOR] Repositioned to ({edge_position.x}, {edge_position.y})")

                                logger.info(f"[STATE] → {new_context.value.upper()} context")

                            except Exception as e:
                                # Cleanup on error
                                logger.error(f"Transition failed: {e}", exc_info=True)
                                try:
                                    display_manager.keyboard_ungrab()
                                    display_manager.pointer_ungrab()
                                    display_manager.cursor_show()
                                except:
                                    pass
                                context_ref[0] = ScreenContext.CENTER
                                logger.warning("Reverted to CENTER after failed transition")

                elif context_ref[0] != ScreenContext.CENTER:
                    # In REMOTE mode - Server Authoritative Return Logic
                    target_client_name = context_to_client.get(context_ref[0])

                    # 1. Check for Return Condition
                    # Determine which edge triggers return based on current context
                    should_return = False

                    if context_ref[0] == ScreenContext.WEST:
                        # West Client: Return when hitting RIGHT edge of server screen
                        should_return = position.x >= screen_geometry.width - 1
                    elif context_ref[0] == ScreenContext.EAST:
                        # East Client: Return when hitting LEFT edge
                        should_return = position.x <= 0
                    elif context_ref[0] == ScreenContext.NORTH:
                        # North Client: Return when hitting BOTTOM edge
                        should_return = position.y >= screen_geometry.height - 1
                    elif context_ref[0] == ScreenContext.SOUTH:
                        # South Client: Return when hitting TOP edge
                        should_return = position.y <= 0

                    # Check velocity for return (to prevent accidental triggers)
                    # Use lower threshold for return to make it feel natural
                    if should_return and velocity >= (config.server.velocity_threshold * 0.5):
                        logger.info(f"[BOUNDARY] Returning from {context_ref[0].value.upper()} at ({position.x}, {position.y})")

                        try:
                            # 1. Send Hide Signal to Client
                            if target_client_name:
                                hide_event = MouseEvent(
                                    event_type=EventType.MOUSE_MOVE,
                                    normalized_point=NormalizedPoint(x=-1.0, y=-1.0)
                                )
                                hide_msg = MessageBuilder.mouseEventMessage_create(hide_event)
                                network.messageToClient_send(target_client_name, hide_msg)

                            # 2. Switch Context
                            prev_context = context_ref[0]
                            context_ref[0] = ScreenContext.CENTER
                            last_center_switch_time[0] = time.time()

                            # 3. Calculate Entry Position (Inverse of Exit)
                            if prev_context == ScreenContext.WEST:
                                # Returning from West -> Enter at Left Edge
                                entry_pos = Position(x=1, y=position.y)
                            elif prev_context == ScreenContext.EAST:
                                # Returning from East -> Enter at Right Edge
                                entry_pos = Position(x=screen_geometry.width - 2, y=position.y)
                            elif prev_context == ScreenContext.NORTH:
                                # Returning from North -> Enter at Top Edge
                                entry_pos = Position(x=position.x, y=1)
                            else: # SOUTH
                                # Returning from South -> Enter at Bottom Edge
                                entry_pos = Position(x=position.x, y=screen_geometry.height - 2)

                            # 4. Restore Desktop State
                            display_manager.cursorPosition_set(entry_pos)
                            display_manager.cursor_show()
                            display_manager.keyboard_ungrab()
                            display_manager.pointer_ungrab()

                            logger.info(f"[STATE] → CENTER, cursor shown at ({entry_pos.x}, {entry_pos.y})")

                        except Exception as e:
                            logger.error(f"Return transition failed: {e}", exc_info=True)
                            # Try to ensure we are at least in a usable state
                            try:
                                display_manager.cursor_show()
                                display_manager.keyboard_ungrab()
                                display_manager.pointer_ungrab()
                            except:
                                pass
                            context_ref[0] = ScreenContext.CENTER

                    else:
                        if target_client_name:
                            # Not returning - Send events to active client
                            normalized_point = screen_geometry.normalize(position)

                            mouse_event = MouseEvent(
                                event_type=EventType.MOUSE_MOVE,
                                normalized_point=normalized_point
                            )
                            move_msg = MessageBuilder.mouseEventMessage_create(mouse_event)
                            network.messageToClient_send(target_client_name, move_msg)

                            # Send Input Events (Buttons & Keys)
                            input_events = read_input_events(display_manager)
                            for event in input_events:
                                msg = None
                                if isinstance(event, MouseEvent):
                                    # Normalize position for button events
                                    if event.position:
                                        norm_pos = screen_geometry.normalize(event.position)
                                        # Create new event with normalized point
                                        norm_event = MouseEvent(
                                            event_type=event.event_type,
                                            normalized_point=norm_pos,
                                            button=event.button
                                        )
                                        msg = MessageBuilder.mouseEventMessage_create(norm_event)
                                        logger.debug(f"[BUTTON] {event.event_type.value} button={event.button}")
                                elif isinstance(event, KeyEvent):
                                    msg = MessageBuilder.keyEventMessage_create(event)
                                    logger.debug(f"[KEY] {event.event_type.value} keycode={event.keycode}")

                                if msg:
                                    network.messageToClient_send(target_client_name, msg)
                        else:
                            # Drain events if no client connected but in remote mode
                            read_input_events(display_manager)

            # Small sleep to prevent busy waiting
            time.sleep(config.server.poll_interval_ms / settings.POLL_INTERVAL_DIVISOR)

    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise
    finally:
        network.server_stop()
        display_manager.connection_close()


def main() -> NoReturn:
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
