"""Client bootstrap helpers for config, backend, and session wiring."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import cast

from tx2tx.client.network import ClientNetwork
from tx2tx.common.config import Config, ConfigLoader
from tx2tx.common.runtime_models import ClientBackendOptions
from tx2tx.common.settings import settings
from tx2tx.common.types import Screen
from tx2tx.input.backend import DisplayBackend, InputInjector
from tx2tx.x11.backend import X11DisplayBackend
from tx2tx.x11.hint_overlay import HintOverlay
from tx2tx.x11.software_cursor import SoftwareCursor

logger = logging.getLogger(__name__)


def configWithSettings_load(args: argparse.Namespace) -> Config:
    """
    Load client config and initialize settings.

    Args:
        args: Parsed CLI args.

    Returns:
        Loaded config.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    try:
        config: Config = ConfigLoader.configWithOverrides_load(
            file_path=config_path, server_address=args.server, display=args.display
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Create a config.yml file or specify path with --config", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)
    settings.initialize(config)
    return config


def loggingWithConfig_setup(args: argparse.Namespace, config: Config, logging_setup_func) -> None:
    """
    Setup client logging from config and optional CLI override.

    Args:
        args: Parsed CLI args.
        config: Loaded config.
        logging_setup_func: Logging setup callback.
    """
    log_level: str = getattr(args, "log_level", None) or config.logging.level
    logging_setup_func(log_level, config.logging.format, config.logging.file)


def serverAddressWithConfig_parse(config: Config, server_address_parse_func) -> tuple[str, int]:
    """
    Parse and validate server address from config.

    Args:
        config: Loaded config.
        server_address_parse_func: Address parsing callback.

    Returns:
        Host and port tuple.
    """
    try:
        host: str
        port: int
        host, port = server_address_parse_func(config.client.server_address)
        return host, port
    except ValueError as e:
        logger.error(f"Invalid server address: {e}")
        sys.exit(1)


def backendOptions_resolve(args: argparse.Namespace, config: Config) -> ClientBackendOptions:
    """
    Resolve client backend options from args/config.

    Args:
        args: Parsed CLI args.
        config: Loaded config.

    Returns:
        Typed backend options.
    """
    backend_name: str = getattr(args, "backend", None) or config.backend.name or "x11"
    if backend_name.lower() not in {"x11", "wayland"}:
        logger.error(f"Unsupported backend '{backend_name}'. Supported: x11, wayland.")
        sys.exit(1)
    wayland_helper: str | None = (
        getattr(args, "wayland_helper", None) or config.backend.wayland.helper_command
    )
    return ClientBackendOptions(
        backend_name=backend_name,
        wayland_helper=wayland_helper,
    )


def displayConnection_establish(display_manager: DisplayBackend) -> Screen:
    """
    Establish display backend connection.

    Args:
        display_manager: Display backend.

    Returns:
        Screen geometry.
    """
    try:
        display_manager.connection_establish()
        screen_geometry: Screen = display_manager.screenGeometry_get()
        logger.info(f"Screen geometry: {screen_geometry.width}x{screen_geometry.height}")
        return screen_geometry
    except Exception as e:
        logger.error(f"Failed to connect to X11 display: {e}")
        sys.exit(1)


def softwareCursor_create(
    args: argparse.Namespace, backend_name: str, display_manager: DisplayBackend
) -> SoftwareCursor | None:
    """
    Create software cursor when requested and supported.

    Args:
        args: Parsed CLI args.
        backend_name: Selected backend.
        display_manager: Display backend.

    Returns:
        Software cursor or None.
    """
    if not args.software_cursor:
        return None
    if backend_name.lower() != "x11":
        logger.warning("Software cursor is only supported on X11 backends")
        return None
    x11_display: X11DisplayBackend = cast(X11DisplayBackend, display_manager)
    software_cursor: SoftwareCursor = SoftwareCursor(x11_display.displayManager_get())
    logger.info("Software cursor enabled")
    return software_cursor


def hintOverlay_create(backend_name: str, display_manager: DisplayBackend) -> HintOverlay | None:
    """
    Create hint overlay for supported backends.

    Args:
        backend_name: Selected backend.
        display_manager: Display backend.

    Returns:
        Hint overlay or None.
    """
    if backend_name.lower() != "x11":
        return None
    x11_display: X11DisplayBackend = cast(X11DisplayBackend, display_manager)
    return HintOverlay(x11_display.displayManager_get())


def clientSession_run(
    network: ClientNetwork,
    screen_geometry: Screen,
    client_name: str | None,
    message_loop_run_func,
    event_injector: InputInjector,
    display_manager: DisplayBackend,
    software_cursor: SoftwareCursor | None,
    hint_overlay: HintOverlay | None,
    reconnect_enabled: bool,
) -> None:
    """
    Establish session and run message loop.

    Args:
        network: Client network transport.
        screen_geometry: Screen geometry.
        client_name: Optional client name.
        message_loop_run_func: Message loop callback.
        event_injector: Input injector.
        display_manager: Display backend.
        software_cursor: Optional software cursor.
        hint_overlay: Optional hint overlay.
        reconnect_enabled: Reconnect policy.
    """
    network.connection_establish(
        screen_width=screen_geometry.width,
        screen_height=screen_geometry.height,
        client_name=client_name,
    )
    logger.info("Client running. Press Ctrl+C to stop.")
    message_loop_run_func(
        network=network,
        event_injector=event_injector,
        display_manager=display_manager,
        software_cursor=software_cursor,
        hint_overlay=hint_overlay,
        reconnect_enabled=reconnect_enabled,
    )
