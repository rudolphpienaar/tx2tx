"""tx2tx client main entry point"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import NoReturn, Optional

from tx2tx import __version__
from tx2tx.client.network import ClientNetwork
from tx2tx.common.config import ConfigLoader
from tx2tx.protocol.message import Message, MessageParser, MessageType
from tx2tx.x11.display import DisplayManager
from tx2tx.x11.injector import EventInjector
from tx2tx.x11.pointer import PointerTracker

logger = logging.getLogger(__name__)


def arguments_parse() -> argparse.Namespace:
    """
    Parse command line arguments

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="tx2tx client - receives and injects input events"
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
        "--server",
        type=str,
        default=None,
        help="Server address to connect to (overrides config, e.g., 192.168.1.100:24800)"
    )

    parser.add_argument(
        "--display",
        type=str,
        default=None,
        help="X11 display name (overrides config)"
    )

    return parser.parse_args()


def serverAddress_parse(server: str) -> tuple[str, int]:
    """
    Parse server address into host and port

    Args:
        server: Server address string (host:port)

    Returns:
        Tuple of (host, port)

    Raises:
        ValueError: If address format is invalid
    """
    if ":" not in server:
        raise ValueError("Server address must be in format host:port")

    host, port_str = server.rsplit(":", 1)
    try:
        port = int(port_str)
    except ValueError:
        raise ValueError(f"Invalid port number: {port_str}")

    return host, port


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


def serverMessage_handle(
    message: Message,
    injector: Optional[EventInjector] = None,
    monitoring_boundaries: Optional[list[bool]] = None
) -> None:
    """
    Handle message received from server

    Args:
        message: Received message
        injector: Optional event injector for handling input events
        monitoring_boundaries: Mutable flag [bool] to enable/disable boundary monitoring
    """
    logger.info(f"Received {message.msg_type.value} from server")

    if message.msg_type == MessageType.HELLO:
        logger.info(f"Server handshake: {message.payload}")

    elif message.msg_type == MessageType.SCREEN_INFO:
        logger.info(f"Server screen info: {message.payload}")

    elif message.msg_type == MessageType.SCREEN_LEAVE:
        transition = MessageParser.screenTransition_parse(message)
        logger.info(
            f"Server lost control at {transition.direction.value} edge "
            f"({transition.position.x}, {transition.position.y})"
        )
        # Client should now be receiving mouse events and monitoring boundaries
        if monitoring_boundaries is not None:
            monitoring_boundaries[0] = True
            logger.info("Client started monitoring boundaries for re-entry")

    elif message.msg_type == MessageType.SCREEN_ENTER:
        transition = MessageParser.screenTransition_parse(message)
        logger.info(
            f"Server regained control at {transition.direction.value} edge "
            f"({transition.position.x}, {transition.position.y})"
        )
        # Client should stop receiving mouse events

    elif message.msg_type == MessageType.MOUSE_EVENT:
        if injector:
            mouse_event = MessageParser.mouseEvent_parse(message)
            injector.mouseEvent_inject(mouse_event)
            logger.debug(f"Injected mouse event: {mouse_event.event_type.value}")
        else:
            logger.warning("Received mouse event but injector not available")

    elif message.msg_type == MessageType.KEY_EVENT:
        if injector:
            key_event = MessageParser.keyEvent_parse(message)
            injector.keyEvent_inject(key_event)
            logger.debug(f"Injected key event: {key_event.event_type.value}")
        else:
            logger.warning("Received key event but injector not available")

    else:
        logger.debug(f"Message: {message.msg_type.value}")


def client_run(args: argparse.Namespace) -> None:
    """
    Run tx2tx client

    Args:
        args: Parsed command line arguments
    """
    # Load configuration
    config_path = Path(args.config) if args.config else None

    try:
        config = ConfigLoader.configWithOverrides_load(
            file_path=config_path,
            server_address=args.server,
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

    # Parse server address
    try:
        host, port = serverAddress_parse(config.client.server_address)
    except ValueError as e:
        logger.error(f"Invalid server address: {e}")
        sys.exit(1)

    logger.info(f"tx2tx client v{__version__}")
    logger.info(f"Connecting to {host}:{port}")
    logger.info(f"Display: {config.client.display or '$DISPLAY'}")

    # Initialize X11 display and event injector
    display_manager = DisplayManager(display_name=config.client.display)

    try:
        display_manager.connection_establish()
        screen_geometry = display_manager.screenGeometry_get()
        logger.info(f"Screen geometry: {screen_geometry.width}x{screen_geometry.height}")
    except Exception as e:
        logger.error(f"Failed to connect to X11 display: {e}")
        sys.exit(1)

    event_injector = EventInjector(display_manager=display_manager)

    # Verify XTest extension is available
    if not event_injector.xtestExtension_verify():
        logger.error("XTest extension not available, cannot inject events")
        display_manager.connection_close()
        sys.exit(1)

    logger.info("XTest extension verified, event injection ready")

    # Initialize pointer tracker for boundary detection (for re-entry)
    pointer_tracker = PointerTracker(
        display_manager=display_manager,
        edge_threshold=0  # Detect at exact screen edge
    )

    # Initialize network client
    network = ClientNetwork(
        host=host,
        port=port,
        reconnect_enabled=config.client.reconnect.enabled,
        reconnect_max_attempts=config.client.reconnect.max_attempts,
        reconnect_delay=config.client.reconnect.delay_seconds
    )

    # Boundary monitoring flag (mutable reference for serverMessage_handle)
    monitoring_boundaries = [False]

    try:
        # Connect to server
        network.connection_establish()

        # Main event loop
        logger.info("Client running. Press Ctrl+C to stop.")

        while network.connectionStatus_check():
            try:
                # Receive messages from server
                messages = network.messages_receive()

                for message in messages:
                    serverMessage_handle(message, event_injector, monitoring_boundaries)

                # Check for boundary crossings when monitoring is enabled
                if monitoring_boundaries[0]:
                    position = pointer_tracker.position_query()
                    transition = pointer_tracker.boundary_detect(position, screen_geometry)

                    if transition:
                        logger.info(
                            f"Client boundary crossed: {transition.direction.value} at "
                            f"({transition.position.x}, {transition.position.y})"
                        )

                        # Send screen enter message to server
                        from tx2tx.protocol.message import MessageBuilder
                        enter_msg = MessageBuilder.screenEnterMessage_create(transition)
                        network.message_send(enter_msg)
                        logger.info("Sent screen_enter to server")

                        # Stop monitoring boundaries
                        monitoring_boundaries[0] = False
                        logger.info("Client stopped monitoring boundaries")

                # Small sleep to prevent busy waiting
                time.sleep(0.01)

            except ConnectionError as e:
                logger.error(f"Connection error: {e}")
                if config.client.reconnect.enabled:
                    if network.reconnection_attempt():
                        logger.info("Reconnected successfully")
                    else:
                        logger.error("Reconnection failed, exiting")
                        break
                else:
                    break

    except ConnectionError as e:
        logger.error(f"Failed to connect: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Client error: {e}", exc_info=True)
        raise
    finally:
        network.connection_close()
        display_manager.connection_close()


def main() -> NoReturn:
    """Main entry point"""
    args = arguments_parse()

    try:
        client_run(args)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
