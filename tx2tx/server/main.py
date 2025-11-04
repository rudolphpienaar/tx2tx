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
from tx2tx.common.types import Direction, EventType, MouseEvent, Position, ScreenGeometry, ScreenTransition
from tx2tx.protocol.message import Message, MessageBuilder, MessageParser, MessageType
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.x11.capturer import EventCapturer
from tx2tx.x11.display import DisplayManager
from tx2tx.x11.pointer import PointerTracker

logger = logging.getLogger(__name__)


class ControlState(Enum):
    """Server control state"""
    LOCAL = "local"  # Server has control of mouse
    REMOTE = "remote"  # Client has control of mouse


def coordinateForReEntry_calculate(direction: Direction, geometry: ScreenGeometry) -> Position:
    """
    Calculate cursor position on server when re-entering from client

    Args:
        direction: Direction of re-entry (which edge of client cursor crossed)
        geometry: Server screen geometry

    Returns:
        Position where cursor should appear on server
    """
    # Place cursor slightly inside the screen, not at the exact edge
    margin = 10

    if direction == Direction.LEFT:
        # Client cursor crossed left edge, cursor should appear on server right edge
        return Position(x=geometry.width - margin, y=geometry.height // 2)
    elif direction == Direction.RIGHT:
        # Client cursor crossed right edge, cursor should appear on server left edge
        return Position(x=margin, y=geometry.height // 2)
    elif direction == Direction.TOP:
        # Client cursor crossed top edge, cursor should appear on server bottom edge
        return Position(x=geometry.width // 2, y=geometry.height - margin)
    elif direction == Direction.BOTTOM:
        # Client cursor crossed bottom edge, cursor should appear on server top edge
        return Position(x=geometry.width // 2, y=margin)
    else:
        # Fallback to center
        return Position(x=geometry.width // 2, y=geometry.height // 2)


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
    display_manager: DisplayManager,
    screen_geometry: ScreenGeometry,
    control_state_ref: list[ControlState],
    event_capturer: EventCapturer
) -> None:
    """
    Handle message received from client

    Args:
        client: Client connection
        message: Received message
        display_manager: Display manager for cursor control
        screen_geometry: Screen geometry for coordinate mapping
        control_state_ref: Reference to control state (list with single element for mutability)
        event_capturer: Event capturer for keyboard and mouse events
    """
    logger.info(f"Received {message.msg_type.value} from {client.address}")

    if message.msg_type == MessageType.HELLO:
        logger.info(f"Client handshake: {message.payload}")
    elif message.msg_type == MessageType.KEEPALIVE:
        logger.debug("Keepalive received")
    elif message.msg_type == MessageType.SCREEN_ENTER:
        # Client cursor crossed boundary back to server
        transition = MessageParser.screenTransition_parse(message)
        logger.info(
            f"Client re-entry at {transition.direction.value} edge "
            f"({transition.position.x}, {transition.position.y})"
        )

        # Switch back to LOCAL control
        if control_state_ref[0] == ControlState.REMOTE:
            control_state_ref[0] = ControlState.LOCAL
            logger.info("Switched to LOCAL control")

            # Release cursor confinement and keyboard grab
            try:
                display_manager.cursor_release()
                logger.debug("Cursor released")
            except Exception as e:
                logger.warning(f"Failed to release cursor: {e}")

            try:
                event_capturer.keyboard_release()
                logger.debug("Keyboard released")
            except Exception as e:
                logger.warning(f"Failed to release keyboard: {e}")

            # Map client cursor position to server screen and move cursor there
            # For now, use simple mapping based on direction
            entry_position = coordinateForReEntry_calculate(
                transition.direction, screen_geometry
            )
            try:
                display_manager.cursorPosition_set(entry_position)
                logger.debug(f"Cursor positioned at ({entry_position.x}, {entry_position.y})")
            except Exception as e:
                logger.warning(f"Failed to set cursor position: {e}")
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

    # Setup logging
    logging_setup(config.logging.level, config.logging.format, config.logging.file)

    logger.info(f"tx2tx server v{__version__}")
    logger.info(f"Listening on {config.server.host}:{config.server.port}")
    logger.info(f"Edge threshold: {config.server.edge_threshold} pixels")
    logger.info(f"Display: {config.server.display or '$DISPLAY'}")
    logger.info(f"Max clients: {config.server.max_clients}")

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
        edge_threshold=config.server.edge_threshold
    )

    # Initialize event capturer for keyboard and mouse button events
    event_capturer = EventCapturer(display_manager=display_manager)

    # Initialize network server
    network = ServerNetwork(
        host=config.server.host,
        port=config.server.port,
        max_clients=config.server.max_clients
    )

    # Control state (wrapped in list for mutability in callback)
    control_state_ref = [ControlState.LOCAL]

    try:
        network.server_start()

        # Main event loop
        logger.info("Server running. Press Ctrl+C to stop.")

        while network.is_running:
            # Accept new connections
            network.connections_accept()

            # Receive messages from clients
            network.clientData_receive(
                lambda client, message: clientMessage_handle(
                    client, message, display_manager, screen_geometry, control_state_ref, event_capturer
                )
            )

            # Track pointer when we have clients
            if network.clients_count() > 0:
                # Poll pointer position
                position = pointer_tracker.position_query()

                if control_state_ref[0] == ControlState.LOCAL:
                    # Detect boundary crossings
                    transition = pointer_tracker.boundary_detect(position, screen_geometry)

                    if transition:
                        logger.info(
                            f"Boundary crossed: {transition.direction.value} at "
                            f"({transition.position.x}, {transition.position.y})"
                        )

                        # Send screen leave message to all clients
                        leave_msg = MessageBuilder.screenLeaveMessage_create(transition)
                        network.messageToAll_broadcast(leave_msg)

                        # Switch to remote control
                        control_state_ref[0] = ControlState.REMOTE
                        logger.info("Switched to REMOTE control")

                        # Confine cursor on server to prevent visible movement
                        try:
                            # Confine cursor to the edge position
                            display_manager.cursor_confine(transition.position)
                            logger.debug("Cursor confined")
                        except Exception as e:
                            logger.warning(f"Failed to confine cursor: {e}")

                        # Grab keyboard to capture key events
                        try:
                            if event_capturer.keyboard_grab():
                                logger.debug("Keyboard grabbed for event capture")
                            else:
                                logger.warning("Failed to grab keyboard")
                        except Exception as e:
                            logger.warning(f"Failed to grab keyboard: {e}")

                elif control_state_ref[0] == ControlState.REMOTE:
                    # Send mouse movements to clients
                    mouse_event = MouseEvent(
                        event_type=EventType.MOUSE_MOVE,
                        position=position
                    )
                    move_msg = MessageBuilder.mouseEventMessage_create(mouse_event)
                    network.messageToAll_broadcast(move_msg)

                    # Capture and send keyboard and mouse button events
                    try:
                        captured_events = event_capturer.events_poll()
                        for event in captured_events:
                            if isinstance(event, MouseEvent):
                                # Send mouse button events
                                msg = MessageBuilder.mouseEventMessage_create(event)
                                network.messageToAll_broadcast(msg)
                                logger.debug(f"Sent mouse button event: {event.event_type.value}")
                            else:
                                # Send keyboard events
                                msg = MessageBuilder.keyEventMessage_create(event)
                                network.messageToAll_broadcast(msg)
                                logger.debug(f"Sent key event: {event.event_type.value}")
                    except Exception as e:
                        logger.warning(f"Error capturing events: {e}")

            # Small sleep to prevent busy waiting
            time.sleep(config.server.poll_interval_ms / 1000.0)

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
