"""tx2tx client main entry point"""

import argparse
import logging
import sys
import time
from typing import Optional

from tx2tx import __version__
from tx2tx.client.bootstrap import (
    backendOptions_resolve,
    clientSession_run,
    configWithSettings_load,
    displayConnection_establish,
    hintOverlay_create,
    loggingWithConfig_setup,
    serverAddressWithConfig_parse,
    softwareCursor_create,
)
from tx2tx.client.network import ClientNetwork
from tx2tx.common.runtime_models import ClientBackendOptions
from tx2tx.common.settings import settings
from tx2tx.common.types import EventType, MouseEvent
from tx2tx.input.backend import DisplayBackend, InputInjector
from tx2tx.input.factory import clientBackend_create
from tx2tx.protocol.message import Message, MessageParser, MessageType
from tx2tx.x11.software_cursor import SoftwareCursor
from tx2tx.x11.hint_overlay import HintOverlay

logger = logging.getLogger(__name__)


def arguments_parse() -> argparse.Namespace:
    """
    Parse command line arguments
    
    Args:
        None.
    
    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(description="tx2tx client - receives and injects input events")

    parser.add_argument("--version", action="version", version=f"tx2tx {__version__}")

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: search standard locations)",
    )

    parser.add_argument(
        "--server",
        type=str,
        default=None,
        help="Server address to connect to (overrides config, e.g., 192.168.1.100:24800)",
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
        "--wayland-start-x",
        type=int,
        default=None,
        help="Wayland initial cursor X override (pixels).",
    )

    parser.add_argument(
        "--wayland-start-y",
        type=int,
        default=None,
        help="Wayland initial cursor Y override (pixels).",
    )

    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Client name for logging and identification (e.g., 'phomux')",
    )

    parser.add_argument(
        "--software-cursor",
        action="store_true",
        help="Enable software rendered cursor (useful if hardware cursor is invisible)",
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


def serverMessage_handle(
    message: Message,
    injector: Optional[InputInjector] = None,
    display_manager: Optional[DisplayBackend] = None,
    software_cursor: Optional[SoftwareCursor] = None,
    hint_overlay: Optional[HintOverlay] = None,
) -> None:
    """
    Handle message received from server
    
    Args:
        message: message value.
        injector: injector value.
        display_manager: display_manager value.
        software_cursor: software_cursor value.
        hint_overlay: hint_overlay value.
    
    Returns:
        Result value.
    """
    logger.info(f"Received {message.msg_type.value} from server")

    if message.msg_type == MessageType.HELLO:
        logger.info(f"Server handshake: {message.payload}")

    elif message.msg_type == MessageType.SCREEN_INFO:
        logger.info(f"Server screen info: {message.payload}")

    elif message.msg_type == MessageType.SCREEN_LEAVE:
        # Deprecated: Server now handles state. Just log it.
        logger.debug("Received SCREEN_LEAVE (informational)")

    elif message.msg_type == MessageType.SCREEN_ENTER:
        # Deprecated: Server now handles state. Just log it.
        logger.debug("Received SCREEN_ENTER (informational)")

    elif message.msg_type == MessageType.MOUSE_EVENT:
        mouseMessage_handle(message, injector, display_manager, software_cursor)

    elif message.msg_type == MessageType.KEY_EVENT:
        keyMessage_handle(message, injector)
    elif message.msg_type == MessageType.HINT_SHOW:
        hintShow_handle(message, hint_overlay)
    elif message.msg_type == MessageType.HINT_HIDE:
        hintHide_handle(hint_overlay)

    else:
        logger.debug(f"Message: {message.msg_type.value}")


def mouseMessage_handle(
    message: Message,
    injector: Optional[InputInjector],
    display_manager: Optional[DisplayBackend],
    software_cursor: Optional[SoftwareCursor],
) -> None:
    """
    Handle incoming mouse event message.

    Args:
        message: Protocol message.
        injector: Input injector instance.
        display_manager: Display backend instance.
        software_cursor: Optional software cursor.
    """
    if injector is None or display_manager is None:
        logger.warning("Received mouse event but injector or display_manager not available")
        return

    mouse_event: MouseEvent = MessageParser.mouseEvent_parse(message)
    actual_event: MouseEvent | None = mouseEventForInjection_build(
        mouse_event, display_manager, software_cursor
    )
    if actual_event is None:
        return

    try:
        injector.mouseEvent_inject(actual_event)
    except ValueError as e:
        logger.warning(f"Failed to inject mouse event: {e}")
        return

    if actual_event.event_type == EventType.MOUSE_MOVE and actual_event.position is not None:
        logger.debug(f"Cursor at ({actual_event.position.x}, {actual_event.position.y})")
        return
    logger.info(f"Mouse {actual_event.event_type.value}: button={actual_event.button}")


def mouseEventForInjection_build(
    mouse_event: MouseEvent,
    display_manager: DisplayBackend,
    software_cursor: Optional[SoftwareCursor],
) -> MouseEvent | None:
    """
    Convert incoming protocol mouse event into injection-ready event.

    Args:
        mouse_event: Parsed protocol mouse event.
        display_manager: Display backend instance.
        software_cursor: Optional software cursor.

    Returns:
        Mouse event suitable for injector, or None when event is consume-only.
    """
    if mouse_event.normalized_point is None:
        return mouse_event

    norm_point = mouse_event.normalized_point
    if norm_point.x < 0 or norm_point.y < 0:
        if software_cursor is not None:
            software_cursor.hide()
        display_manager.cursor_hide()
        logger.info("Cursor hidden")
        return None

    client_screen = display_manager.screenGeometry_get()
    pixel_position = client_screen.coordinates_denormalize(norm_point)
    if software_cursor is not None:
        software_cursor.show()
        software_cursor.move(pixel_position.x, pixel_position.y)
    display_manager.cursor_show()
    return MouseEvent(
        event_type=mouse_event.event_type,
        position=pixel_position,
        button=mouse_event.button,
    )


def keyMessage_handle(message: Message, injector: Optional[InputInjector]) -> None:
    """
    Handle incoming key event message.

    Args:
        message: Protocol message.
        injector: Input injector instance.
    """
    if injector is None:
        logger.warning("Received key event but injector not available")
        return

    key_event = MessageParser.keyEvent_parse(message)
    injector.keyEvent_inject(key_event)
    if key_event.keysym is not None:
        logger.info(
            f"Key {key_event.event_type.value}: keycode={key_event.keycode} "
            f"keysym={key_event.keysym:#x}"
        )
        return
    logger.info(f"Key {key_event.event_type.value}: keycode={key_event.keycode}")


def hintShow_handle(message: Message, hint_overlay: Optional[HintOverlay]) -> None:
    """
    Handle hint-show protocol message.

    Args:
        message: Protocol message.
        hint_overlay: Optional overlay instance.
    """
    if hint_overlay is None:
        return
    label: str = str(message.payload.get("label", "")).strip()
    timeout_ms: int = int(message.payload.get("timeout_ms", 800))
    if not label:
        return
    hint_overlay.show(label=label, timeout_ms=timeout_ms)


def hintHide_handle(hint_overlay: Optional[HintOverlay]) -> None:
    """
    Handle hint-hide protocol message.

    Args:
        hint_overlay: Optional overlay instance.
    """
    if hint_overlay is None:
        return
    hint_overlay.hide()


def client_run(args: argparse.Namespace) -> None:
    """
    Run tx2tx client
    
    Args:
        args: args value.
    
    Returns:
        Result value.
    """
    config = configWithSettings_load(args)
    loggingWithConfig_setup(args, config, logging_setup)
    host, port = serverAddressWithConfig_parse(config, serverAddress_parse)

    logger.info(f"tx2tx client v{__version__}")
    if args.name:
        logger.info(f"Client name: {args.name}")
    logger.info(f"Connecting to {host}:{port}")
    logger.info(f"Display: {config.client.display or '$DISPLAY'}")

    backend_options: ClientBackendOptions = backendOptions_resolve(args, config)
    backend_name: str = backend_options.backend_name
    wayland_helper: str | None = backend_options.wayland_helper
    logger.info(f"Backend: {backend_name}")

    display_manager, event_injector = clientBackend_create(
        backend_name=backend_name,
        display_name=config.client.display,
        wayland_helper=wayland_helper,
    )

    screen_geometry = displayConnection_establish(display_manager)

    # Verify injection capability is available
    if not event_injector.injectionReady_check():
        logger.error("Input injection not available for selected backend")
        display_manager.connection_close()
        sys.exit(1)

    logger.info("Input injection ready")

    software_cursor = softwareCursor_create(args, backend_name, display_manager)
    hint_overlay = hintOverlay_create(backend_name, display_manager)

    network = ClientNetwork(
        host=host,
        port=port,
        reconnect_enabled=config.client.reconnect.enabled,
        reconnect_max_attempts=config.client.reconnect.max_attempts,
        reconnect_delay=config.client.reconnect.delay_seconds,
    )

    try:
        clientSession_run(
            network=network,
            screen_geometry=screen_geometry,
            client_name=args.name,
            message_loop_run_func=messageLoop_run,
            event_injector=event_injector,
            display_manager=display_manager,
            software_cursor=software_cursor,
            hint_overlay=hint_overlay,
            reconnect_enabled=config.client.reconnect.enabled,
        )
    except ConnectionError as e:
        logger.error(f"Failed to connect: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Client error: {e}", exc_info=True)
        raise
    finally:
        if hint_overlay is not None:
            hint_overlay.destroy()
        network.connection_close()
        display_manager.connection_close()


def messageLoop_run(
    network: ClientNetwork,
    event_injector: InputInjector,
    display_manager: DisplayBackend,
    software_cursor: SoftwareCursor | None,
    hint_overlay: HintOverlay | None,
    reconnect_enabled: bool,
) -> None:
    """
    Run main client receive/inject loop.

    Args:
        network: Client network transport.
        event_injector: Input injector.
        display_manager: Display backend.
        software_cursor: Optional software cursor.
        hint_overlay: Optional hint overlay.
        reconnect_enabled: Whether reconnect is enabled.
    """
    while network.connectionStatus_check():
        try:
            messages = network.messages_receive()
            for message in messages:
                serverMessage_handle(
                    message,
                    event_injector,
                    display_manager,
                    software_cursor,
                    hint_overlay,
                )
            if hint_overlay is not None:
                hint_overlay.tick()
            time.sleep(settings.RECONNECT_CHECK_INTERVAL)
        except ConnectionError as e:
            logger.error(f"Connection error: {e}")
            if not reconnect_enabled:
                break
            if network.reconnection_attempt():
                logger.info("Reconnected successfully")
                continue
            logger.error("Reconnection failed, exiting")
            break
