"""Server bootstrap helpers for config, logging, and backend wiring."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tx2tx.common.config import Config, ConfigLoader
from tx2tx.common.runtime_models import ServerBackendOptions
from tx2tx.common.settings import settings
from tx2tx.common.types import ScreenContext
from tx2tx.input.backend import DisplayBackend, InputCapturer
from tx2tx.input.factory import serverBackend_create

logger = logging.getLogger(__name__)


def configWithSettings_load(args: argparse.Namespace) -> Config:
    """
    Load configuration and initialize settings singleton.

    Args:
        args: Parsed server CLI args.

    Returns:
        Loaded config.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    try:
        config: Config = ConfigLoader.configWithOverrides_load(
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
    settings.initialize(config)
    return config


def loggingWithConfig_setup(
    args: argparse.Namespace, config: Config, logging_setup_func
) -> None:
    """
    Setup logging from config and CLI override.

    Args:
        args: Parsed server args.
        config: Loaded config.
        logging_setup_func: Logging setup callback.
    """
    log_level: str = getattr(args, "log_level", None) or config.logging.level
    logging_setup_func(log_level, config.logging.format, config.logging.file)


def backendOptions_resolve(args: argparse.Namespace, config: Config) -> ServerBackendOptions:
    """
    Resolve backend policy/options from CLI and config.

    Args:
        args: Parsed server args.
        config: Loaded config.

    Returns:
        Typed backend options.
    """
    x11native: bool = bool(getattr(args, "x11native", False))
    if x11native:
        overlay_enabled: bool | None = False
        logger.info("Native X11 mode enabled (--x11native)")
    else:
        overlay_enabled = getattr(args, "overlay_enabled", None)
        if overlay_enabled is None:
            overlay_enabled = config.server.overlay_enabled
        if overlay_enabled:
            logger.info("Overlay window enabled (Crostini mode)")

    backend_name: str = getattr(args, "backend", None) or config.backend.name or "x11"
    if backend_name.lower() not in {"x11", "wayland"}:
        logger.error(f"Unsupported backend '{backend_name}'. Supported: x11, wayland.")
        sys.exit(1)
    logger.info(f"Backend: {backend_name}")

    wayland_helper: str | None = (
        getattr(args, "wayland_helper", None) or config.backend.wayland.helper_command
    )
    if backend_name.lower() == "wayland" and not wayland_helper:
        logger.error(
            "Wayland backend requires a helper command. "
            "Provide --wayland-helper or set backend.wayland.helper_command in config."
        )
        sys.exit(1)
    wayland_screen_width: int | None = (
        getattr(args, "wayland_screen_width", None) or config.backend.wayland.screen_width
    )
    wayland_screen_height: int | None = (
        getattr(args, "wayland_screen_height", None) or config.backend.wayland.screen_height
    )
    wayland_calibrate: bool = bool(
        getattr(args, "wayland_calibrate", False) or config.backend.wayland.calibrate
    )
    wayland_pointer_provider: str = (
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

    return ServerBackendOptions(
        backend_name=backend_name,
        overlay_enabled=overlay_enabled,
        x11native=x11native,
        wayland_helper=wayland_helper,
        wayland_screen_width=wayland_screen_width,
        wayland_screen_height=wayland_screen_height,
        wayland_calibrate=wayland_calibrate,
        wayland_pointer_provider=wayland_pointer_provider,
    )


def serverBackendComponents_create(
    config: Config, backend_options: ServerBackendOptions
) -> tuple[DisplayBackend, InputCapturer]:
    """
    Create server backend display and input components.

    Args:
        config: Loaded config.
        backend_options: Resolved backend options.

    Returns:
        Display backend and input capturer.
    """
    return serverBackend_create(
        backend_name=backend_options.backend_name,
        display_name=config.server.display,
        overlay_enabled=backend_options.overlay_enabled,
        x11native=backend_options.x11native,
        wayland_helper=backend_options.wayland_helper,
        wayland_screen_width=backend_options.wayland_screen_width,
        wayland_screen_height=backend_options.wayland_screen_height,
        wayland_pointer_provider=backend_options.wayland_pointer_provider,
    )


def contextToClientMap_build(config: Config) -> dict[ScreenContext, str]:
    """
    Build context-to-client map from configured clients.

    Args:
        config: Loaded config.

    Returns:
        Context-to-client name map.
    """
    context_to_client: dict[ScreenContext, str] = {}
    if config.clients:
        for client_cfg in config.clients:
            try:
                context: ScreenContext = ScreenContext(client_cfg.position.lower())
                context_to_client[context] = client_cfg.name.lower()
            except ValueError:
                logger.warning(
                    f"Invalid position '{client_cfg.position}' for client {client_cfg.name}"
                )
    return context_to_client
