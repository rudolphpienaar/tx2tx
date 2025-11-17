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
from tx2tx.common.settings import settings
from tx2tx.common.types import Direction, EventType, MouseEvent, Position, Screen, ScreenTransition
from tx2tx.protocol.message import Message, MessageBuilder, MessageParser, MessageType
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

    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Client name for logging and identification (e.g., 'phomux')"
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
    display_manager: Optional[DisplayManager] = None,
    client_active: Optional[list[bool]] = None
) -> None:
    """
    Handle message received from server

    Args:
        message: Received message
        injector: Optional event injector for handling input events
        display_manager: Optional display manager for cursor positioning
        client_active: Mutable reference [bool] to track if client is actively receiving control
    """
    logger.info(f"Received {message.msg_type.value} from server")

    if message.msg_type == MessageType.HELLO:
        logger.info(f"Server handshake: {message.payload}")

    elif message.msg_type == MessageType.SCREEN_INFO:
        logger.info(f"Server screen info: {message.payload}")

    elif message.msg_type == MessageType.SCREEN_LEAVE:
        transition = MessageParser.screenTransition_parse(message)
        logger.info(
            f"[SCREEN_LEAVE] Server crossed {transition.direction.value} edge - CLIENT NOW ACTIVE"
        )
        # Activate client - start detecting boundaries for return
        if client_active is not None:
            client_active[0] = True
            logger.info("[CLIENT ACTIVE] Now detecting boundaries for return to server")

    elif message.msg_type == MessageType.SCREEN_ENTER:
        transition = MessageParser.screenTransition_parse(message)
        logger.info(
            f"Server regained control at {transition.direction.value} edge "
            f"({transition.position.x}, {transition.position.y})"
        )
        # Client should stop receiving mouse events

    elif message.msg_type == MessageType.MOUSE_EVENT:
        if injector and display_manager:
            mouse_event = MessageParser.mouseEvent_parse(message)

            # Deactivate client - server is sending movements again (server regained control)
            if client_active is not None and client_active[0]:
                client_active[0] = False
                logger.info("[CLIENT INACTIVE] Server regained control")

            if mouse_event.event_type == EventType.MOUSE_MOVE:
                # Handle normalized coordinates (v2.0 protocol)
                if mouse_event.normalized_point is not None:
                    norm_point = mouse_event.normalized_point

                    # Check for hide signal (negative coordinates)
                    if norm_point.x < 0 or norm_point.y < 0:
                        display_manager.cursor_hide()
                        logger.info("Cursor hidden")
                    else:
                        # Convert normalized coordinates to client pixel position
                        client_screen = display_manager.screenGeometry_get()
                        pixel_position = client_screen.denormalize(norm_point)

                        # Create pixel position mouse event for injection
                        actual_event = MouseEvent(
                            event_type=EventType.MOUSE_MOVE,
                            position=pixel_position
                        )

                        # Show cursor and move
                        display_manager.cursor_show()
                        injector.mouseEvent_inject(actual_event)
                        logger.debug(
                            f"Cursor at ({pixel_position.x}, {pixel_position.y}) "
                            f"from normalized ({norm_point.x:.4f}, {norm_point.y:.4f})"
                        )
                else:
                    # Fallback for old protocol or pixel-based events
                    logger.warning("Received MOUSE_MOVE without normalized_point (old protocol?)")
                    if mouse_event.position:
                        injector.mouseEvent_inject(mouse_event)
            else:
                # Button events
                injector.mouseEvent_inject(mouse_event)
                logger.info(
                    f"Mouse {mouse_event.event_type.value}: button={mouse_event.button}"
                )
        else:
            logger.warning("Received mouse event but injector or display_manager not available")

    elif message.msg_type == MessageType.KEY_EVENT:
        if injector:
            key_event = MessageParser.keyEvent_parse(message)
            injector.keyEvent_inject(key_event)
            # Log key events with keycode and keysym info
            if key_event.keysym is not None:
                logger.info(
                    f"Key {key_event.event_type.value}: keycode={key_event.keycode} "
                    f"keysym={key_event.keysym:#x}"
                )
            else:
                logger.info(
                    f"Key {key_event.event_type.value}: keycode={key_event.keycode}"
                )
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

    # Initialize settings singleton with loaded config
    settings.initialize(config)

    # Setup logging
    logging_setup(config.logging.level, config.logging.format, config.logging.file)

    # Parse server address
    try:
        host, port = serverAddress_parse(config.client.server_address)
    except ValueError as e:
        logger.error(f"Invalid server address: {e}")
        sys.exit(1)

    logger.info(f"tx2tx client v{__version__}")
    if args.name:
        logger.info(f"Client name: {args.name}")
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

    # Initialize pointer tracker for boundary detection (when client is active)
    pointer_tracker = PointerTracker(
        display_manager=display_manager,
        edge_threshold=5,  # Use same threshold as server
        velocity_threshold=100.0  # Use same velocity threshold
    )
    logger.info("Pointer tracker initialized for boundary detection")

    # Initialize network client
    network = ClientNetwork(
        host=host,
        port=port,
        reconnect_enabled=config.client.reconnect.enabled,
        reconnect_max_attempts=config.client.reconnect.max_attempts,
        reconnect_delay=config.client.reconnect.delay_seconds
    )

    # Client active state (wrapped in list for mutable reference)
    client_active_ref = [False]

    try:
        # Connect to server with screen geometry
        network.connection_establish(
            screen_width=screen_geometry.width,
            screen_height=screen_geometry.height
        )

        # Main event loop
        logger.info("Client running. Press Ctrl+C to stop.")

        while network.connectionStatus_check():
            try:
                # Receive messages from server
                messages = network.messages_receive()

                for message in messages:
                    serverMessage_handle(message, event_injector, display_manager, client_active_ref)

                # When client is active, poll for boundary crossings to return to server
                if client_active_ref[0]:
                    position = pointer_tracker.position_query()
                    velocity = pointer_tracker.velocity_calculate()

                    logger.debug(f"[CLIENT POLL] pos=({position.x},{position.y}) velocity={velocity:.1f}px/s")

                    # Detect boundary crossings
                    transition = pointer_tracker.boundary_detect(position, screen_geometry)

                    if transition:
                        logger.info(
                            f"[CLIENT BOUNDARY] Crossed {transition.direction.value} edge at "
                            f"({transition.position.x}, {transition.position.y}) - RETURNING TO SERVER"
                        )

                        # Send SCREEN_ENTER to server (client is entering server's screen)
                        enter_msg = MessageBuilder.screenEnterMessage_create(transition)
                        network.message_send(enter_msg)
                        logger.info("[CLIENT] Sent SCREEN_ENTER to server")

                        # Deactivate client
                        client_active_ref[0] = False
                        logger.info("[CLIENT INACTIVE] Returning control to server")

                # Small sleep to prevent busy waiting
                time.sleep(settings.RECONNECT_CHECK_INTERVAL)

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
