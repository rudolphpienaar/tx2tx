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
from tx2tx.common.types import EventType, MouseEvent, Position, ScreenGeometry, ScreenTransition
from tx2tx.protocol.message import Message, MessageBuilder, MessageType
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.x11.display import DisplayManager
from tx2tx.x11.pointer import PointerTracker

logger = logging.getLogger(__name__)


class ControlState(Enum):
    """Server control state"""
    LOCAL = "local"  # Server has control of mouse
    REMOTE = "remote"  # Client has control of mouse


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
    control_state: Optional[list[ControlState]] = None,
    display_manager: Optional[DisplayManager] = None
) -> None:
    """
    Handle message received from client

    Args:
        client: Client connection
        message: Received message
        control_state: Mutable reference [ControlState] to track server control state
        display_manager: Display manager for cursor control
    """
    logger.info(f"Received {message.msg_type.value} from {client.address}")

    if message.msg_type == MessageType.HELLO:
        logger.info(f"Client handshake: {message.payload}")
    elif message.msg_type == MessageType.KEEPALIVE:
        logger.debug("Keepalive received")
    elif message.msg_type == MessageType.SCREEN_ENTER:
        # Client is returning control to server
        from tx2tx.protocol.message import MessageParser
        transition = MessageParser.screenTransition_parse(message)
        logger.info(
            f"Client re-entry at {transition.direction.value} edge "
            f"({transition.position.x}, {transition.position.y})"
        )

        if control_state is not None and display_manager is not None:
            # Release cursor confinement
            display_manager.cursor_release()
            logger.debug("Cursor released")

            # Position cursor at appropriate edge for smooth re-entry
            display_manager.cursorPosition_set(transition.position)

            # Switch back to local control
            control_state[0] = ControlState.LOCAL
            logger.info("Switched to LOCAL control")
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

    # Initialize network server
    network = ServerNetwork(
        host=config.server.host,
        port=config.server.port,
        max_clients=config.server.max_clients
    )

    # Control state (wrapped in list for mutable reference)
    control_state_ref = [ControlState.LOCAL]
    last_local_switch_time = [0.0]  # Timestamp of last REMOTE→LOCAL switch

    try:
        network.server_start()

        # Main event loop
        logger.info("Server running. Press Ctrl+C to stop.")

        while network.is_running:
            # Accept new connections
            network.connections_accept()

            # Receive messages from clients with callback closure
            def message_handler(client: ClientConnection, message: Message) -> None:
                clientMessage_handle(client, message, control_state_ref, display_manager)
                # Record timestamp when switching back to LOCAL
                if control_state_ref[0] == ControlState.LOCAL and message.msg_type == MessageType.SCREEN_ENTER:
                    last_local_switch_time[0] = time.time()

            network.clientData_receive(message_handler)

            # Track pointer when we have clients
            if network.clients_count() > 0:
                # Poll pointer position
                position = pointer_tracker.position_query()

                if control_state_ref[0] == ControlState.LOCAL:
                    # Add hysteresis: skip boundary detection for 200ms after switching to LOCAL
                    # This prevents immediate re-detection of boundary after cursor release
                    time_since_local_switch = time.time() - last_local_switch_time[0]

                    if time_since_local_switch >= 0.2:
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

                            # Confine cursor at boundary to prevent visible movement
                            display_manager.cursor_confine(transition.position)
                            logger.debug("Cursor confined")

                            # Switch to remote control
                            control_state_ref[0] = ControlState.REMOTE
                            logger.info("Switched to REMOTE control")

                elif control_state_ref[0] == ControlState.REMOTE:
                    # Send mouse movements to clients
                    mouse_event = MouseEvent(
                        event_type=EventType.MOUSE_MOVE,
                        position=position
                    )
                    move_msg = MessageBuilder.mouseEventMessage_create(mouse_event)
                    network.messageToAll_broadcast(move_msg)

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
