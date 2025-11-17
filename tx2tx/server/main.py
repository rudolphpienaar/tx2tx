"""tx2tx server main entry point"""

import argparse
import logging
import sys
import time
from enum import Enum
from pathlib import Path
from typing import NoReturn, Optional

from tx2tx import __version__
from tx2tx.common.config import ConfigLoader
from tx2tx.common.layout import ClientPosition, ScreenLayout
from tx2tx.common.settings import settings
from tx2tx.common.types import Direction, EventType, MouseEvent, NormalizedPoint, Position, Screen, ScreenContext, ScreenTransition
from tx2tx.protocol.message import Message, MessageBuilder, MessageParser, MessageType
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.x11.display import DisplayManager
from tx2tx.x11.pointer import PointerTracker

logger = logging.getLogger(__name__)


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
    server_screen: Optional[Screen] = None
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
            logger.info(
                f"Client handshake: version={payload.get('version')}, "
                f"screen={client.screen_width}x{client.screen_height}"
            )
        else:
            logger.info(f"Client handshake: {message.payload}")
    elif message.msg_type == MessageType.KEEPALIVE:
        logger.debug("Keepalive received")
    elif message.msg_type == MessageType.SCREEN_ENTER:
        # Client is returning control to server
        client_transition = MessageParser.screenTransition_parse(message)
        logger.info(
            f"Client re-entry at {client_transition.direction.value} edge "
            f"({client_transition.position.x}, {client_transition.position.y})"
        )

        if context is not None and display_manager is not None:
            # Transform client coordinates to server coordinates
            if screen_layout is not None and server_screen is not None:
                if client.screen_width and client.screen_height:
                    client_screen = Screen(
                        width=client.screen_width,
                        height=client.screen_height
                    )
                    # Transform client exit coordinates to server re-entry coordinates
                    server_transition = screen_layout.toServerCoordinates_transform(
                        client_transition=client_transition,
                        client_geometry=client_screen,
                        server_geometry=server_screen
                    )
                    logger.info(
                        f"Transformed to server: {server_transition.direction.value} at "
                        f"({server_transition.position.x}, {server_transition.position.y})"
                    )
                else:
                    logger.warning("Client screen geometry not available, using untransformed coordinates")
                    server_transition = client_transition
            else:
                logger.warning("Screen layout not available, using untransformed coordinates")
                server_transition = client_transition

            # Show CENTER cursor again
            display_manager.cursor_show()
            logger.info("[CURSOR] Restored CENTER cursor visibility")

            # Position cursor at appropriate edge for smooth re-entry
            display_manager.cursorPosition_set(server_transition.position)
            logger.info(
                f"[CURSOR] Positioned at server re-entry point ({server_transition.position.x}, {server_transition.position.y})"
            )

            # Switch back to CENTER context
            context[0] = ScreenContext.CENTER
            logger.info("[STATE] Switched to CENTER context")
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

    pointer_tracker = PointerTracker(
        display_manager=display_manager,
        edge_threshold=config.server.edge_threshold,
        velocity_threshold=config.server.velocity_threshold
    )

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

            # Receive messages from clients with callback closure
            def message_handler(client: ClientConnection, message: Message) -> None:
                """Handle incoming messages from clients and track context switches"""
                clientMessage_handle(
                    client, message, context_ref, display_manager,
                    screen_layout, screen_geometry
                )
                # Record timestamp when switching back to CENTER
                if context_ref[0] == ScreenContext.CENTER and message.msg_type == MessageType.SCREEN_ENTER:
                    last_center_switch_time[0] = time.time()

            network.clientData_receive(message_handler)

            # Track pointer when we have clients
            if network.clients_count() > 0:
                # Poll pointer position
                position = pointer_tracker.position_query()
                velocity = pointer_tracker.velocity_calculate()

                # DEBUG: Log position and velocity on every iteration
                logger.debug(f"[POLL] context={context_ref[0].value} pos=({position.x},{position.y}) velocity={velocity:.1f}px/s")

                if context_ref[0] == ScreenContext.CENTER:
                    # Add hysteresis: skip boundary detection after switching to CENTER
                    # This prevents immediate re-detection of boundary after cursor release
                    time_since_center_switch = time.time() - last_center_switch_time[0]

                    if time_since_center_switch >= settings.HYSTERESIS_DELAY_SEC:
                        # Detect boundary crossings
                        transition = pointer_tracker.boundary_detect(position, screen_geometry)

                        if transition:
                            logger.info(
                                f"[BOUNDARY] Server boundary crossed: {transition.direction.value} at "
                                f"({transition.position.x}, {transition.position.y})"
                            )

                            # FIX Issue 1: Map direction to context instead of hardcoding WEST
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

                            context_ref[0] = new_context

                            # FIX Issue 2: Calculate opposite edge position based on direction
                            # Position cursor safely away from the return edge to avoid immediate return detection
                            if transition.direction == Direction.LEFT:
                                edge_position = Position(x=screen_geometry.width - settings.EDGE_ENTRY_OFFSET - 1, y=position.y)
                            elif transition.direction == Direction.RIGHT:
                                edge_position = Position(x=settings.EDGE_ENTRY_OFFSET, y=position.y)
                            elif transition.direction == Direction.TOP:
                                edge_position = Position(x=position.x, y=screen_geometry.height - settings.EDGE_ENTRY_OFFSET - 1)
                            else:  # BOTTOM
                                edge_position = Position(x=position.x, y=settings.EDGE_ENTRY_OFFSET)

                            # DON'T position cursor - let it move naturally for return detection
                            try:
                                logger.info(f"[TRANSITION] Moving to {new_context.value.upper()}")
                                # DON'T position cursor - breaks return detection!
                                # display_manager.cursorPosition_set(edge_position)
                                logger.info(f"[CURSOR] NOT repositioning - letting cursor move naturally")

                                # DEBUG: No grabs at all - just test mouse transitions
                                # display_manager.keyboard_grab()
                                logger.info("[INPUT] No grabs (DEBUG MODE)")

                                logger.info(f"[STATE] → {new_context.value.upper()} context")
                            except Exception as e:
                                # Cleanup on error
                                logger.error(f"Transition failed: {e}", exc_info=True)
                                try:
                                    # display_manager.keyboard_ungrab()
                                    display_manager.cursor_show()
                                except:
                                    pass
                                context_ref[0] = ScreenContext.CENTER
                                logger.warning("Reverted to CENTER after failed transition")

                elif context_ref[0] != ScreenContext.CENTER:
                    # FIX Issue 3: Determine which edge to check based on current context
                    return_edges = {
                        ScreenContext.WEST: lambda p, g: p.x >= g.width - 1,
                        ScreenContext.EAST: lambda p, g: p.x <= 0,
                        ScreenContext.NORTH: lambda p, g: p.y >= g.height - 1,
                        ScreenContext.SOUTH: lambda p, g: p.y <= 0
                    }

                    should_return = return_edges[context_ref[0]](position, screen_geometry)

                    # DEBUG: Log return edge detection
                    if context_ref[0] == ScreenContext.WEST:
                        logger.debug(f"[RETURN CHECK] WEST: pos.x={position.x} >= {screen_geometry.width - 1} ? {should_return}, velocity={velocity:.1f} >= {config.server.velocity_threshold}")
                    elif context_ref[0] == ScreenContext.EAST:
                        logger.debug(f"[RETURN CHECK] EAST: pos.x={position.x} <= 0 ? {should_return}, velocity={velocity:.1f} >= {config.server.velocity_threshold}")
                    elif context_ref[0] == ScreenContext.NORTH:
                        logger.debug(f"[RETURN CHECK] NORTH: pos.y={position.y} >= {screen_geometry.height - 1} ? {should_return}, velocity={velocity:.1f} >= {config.server.velocity_threshold}")
                    elif context_ref[0] == ScreenContext.SOUTH:
                        logger.debug(f"[RETURN CHECK] SOUTH: pos.y={position.y} <= 0 ? {should_return}, velocity={velocity:.1f} >= {config.server.velocity_threshold}")

                    if should_return:
                        # TEMPORARY DEBUG: Bypass velocity check to test position tracking
                        # if velocity >= config.server.velocity_threshold:
                        if True:  # DEBUG: Always allow return when at edge
                            logger.info(f"[BOUNDARY] Returning from {context_ref[0].value.upper()} at ({position.x}, {position.y}) velocity={velocity:.1f}")

                            # Send hide signal to client (negative coordinates = hide)
                            hide_event = MouseEvent(
                                event_type=EventType.MOUSE_MOVE,
                                normalized_point=NormalizedPoint(x=-1.0, y=-1.0)
                            )
                            hide_msg = MessageBuilder.mouseEventMessage_create(hide_event)
                            network.messageToAll_broadcast(hide_msg)
                            logger.info("[CLIENT] Sent hide signal")

                            # Switch back to CENTER context
                            previous_context = context_ref[0]
                            context_ref[0] = ScreenContext.CENTER

                            # DON'T reposition cursor - it's already where the user moved it
                            logger.info(f"[CURSOR] NOT repositioning - cursor already at return position ({position.x}, {position.y})")

                            # DEBUG: No grabs, so no ungrab needed
                            # display_manager.keyboard_ungrab()
                            logger.info("[INPUT] No ungrab needed (DEBUG MODE)")

                            logger.info(f"[STATE] → CENTER context")

                            # Record timestamp
                            last_center_switch_time[0] = time.time()
                    else:
                        # Not returning to CENTER - send normalized coordinates to active client
                        normalized_point = screen_geometry.normalize(position)

                        mouse_event = MouseEvent(
                            event_type=EventType.MOUSE_MOVE,
                            normalized_point=normalized_point
                        )
                        move_msg = MessageBuilder.mouseEventMessage_create(mouse_event)
                        network.messageToAll_broadcast(move_msg)

                        logger.debug(
                            f"[{context_ref[0].value.upper()}] Sent "
                            f"normalized=({normalized_point.x:.4f}, {normalized_point.y:.4f})"
                        )

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
