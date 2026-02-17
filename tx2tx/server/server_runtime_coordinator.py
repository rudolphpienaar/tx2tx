"""
Server runtime coordinator.

This module orchestrates end-to-end server startup and main-loop execution.
It composes configuration loading, backend wiring, pointer/network
initialization, and polling-loop dispatch through injected callbacks.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, Protocol

from tx2tx import __version__
from tx2tx.common.config import Config
from tx2tx.common.layout import ClientPosition
from tx2tx.common.runtime_models import ServerBackendOptions
from tx2tx.common.types import Position, Screen, ScreenContext
from tx2tx.input.backend import DisplayBackend, InputCapturer
from tx2tx.server.bootstrap import (
    backendOptions_resolve,
    configWithSettings_load,
    contextToClientMap_build,
    loggingWithConfig_setup,
    serverBackendComponents_create,
)
from tx2tx.server.network import ServerNetwork
from tx2tx.server.runtime_loop import JumpHotkeyConfigProtocol
from tx2tx.server.state import RuntimeStateProtocol
from tx2tx.x11.pointer import PointerTracker

__all__ = [
    "RuntimeResources",
    "ServerRunCallbacks",
    "server_run",
]


class LoggerProtocol(Protocol):
    """Minimal logger contract for runtime coordinator."""

    def info(self, msg: str, *args: object) -> None:
        """Emit info-level message."""
        ...

    def warning(self, msg: str, *args: object) -> None:
        """Emit warning-level message."""
        ...

    def error(self, msg: str, *args: object, exc_info: bool = False) -> None:
        """Emit error-level message."""
        ...


class PanicKeyConfigParseProtocol(Protocol):
    """Callback contract for panic-key parse logic."""

    def __call__(self, config: Config) -> tuple[set[int], int]:
        """Parse panic-key configuration."""
        ...


class JumpHotkeyConfigParseProtocol(Protocol):
    """Callback contract for jump-hotkey parse logic."""

    def __call__(self, config: Config) -> JumpHotkeyConfigProtocol:
        """Parse jump-hotkey configuration."""
        ...


class PollingLoopProcessProtocol(Protocol):
    """Callback contract for one polling-loop iteration."""

    def __call__(
        self,
        network: ServerNetwork,
        display_manager: DisplayBackend,
        pointer_tracker: PointerTracker,
        screen_geometry: Screen,
        config: Config,
        context_to_client: dict[ScreenContext, str],
        panic_keysyms: set[int],
        panic_modifiers: int,
        x11native: bool,
        input_capturer: InputCapturer,
        jump_hotkey: JumpHotkeyConfigProtocol,
        die_on_disconnect: bool,
        runtime_state: RuntimeStateProtocol,
    ) -> None:
        """Process one polling-loop step."""
        ...


LoggingSetupProtocol = Callable[[str, str, str | None], None]


@dataclass
class ServerRunCallbacks:
    """
    Callback bundle used by server runtime coordinator.

    Attributes:
        panicKeyConfig_parse:
            Panic-key config parser.
        jumpHotkeyConfig_parse:
            Jump-hotkey config parser.
        pollingLoop_process:
            One-step polling-loop dispatcher.
        logging_setup:
            Runtime logging setup routine.
    """

    panicKeyConfig_parse: PanicKeyConfigParseProtocol
    jumpHotkeyConfig_parse: JumpHotkeyConfigParseProtocol
    pollingLoop_process: PollingLoopProcessProtocol
    logging_setup: LoggingSetupProtocol


@dataclass
class RuntimeResources:
    """
    Runtime resources required by polling loop.

    Attributes:
        config:
            Loaded server config.
        display_manager:
            Display backend.
        input_capturer:
            Input-capture backend.
        pointer_tracker:
            Pointer tracker instance.
        screen_geometry:
            Local screen geometry.
        network:
            Server network manager.
        context_to_client:
            Context-to-client map.
        panic_keysyms:
            Panic-key keysyms.
        panic_modifiers:
            Panic-key modifier mask.
        jump_hotkey:
            Parsed jump-hotkey runtime config.
        x11native:
            Native X11 mode flag.
        die_on_disconnect:
            Whether to stop after client disconnect.
    """

    config: Config
    display_manager: DisplayBackend
    input_capturer: InputCapturer
    pointer_tracker: PointerTracker
    screen_geometry: Screen
    network: ServerNetwork
    context_to_client: dict[ScreenContext, str]
    panic_keysyms: set[int]
    panic_modifiers: int
    jump_hotkey: JumpHotkeyConfigProtocol
    x11native: bool
    die_on_disconnect: bool


def server_run(
    args: argparse.Namespace,
    callbacks: ServerRunCallbacks,
    runtime_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Execute server startup and polling-loop lifecycle.

    Args:
        args:
            Parsed CLI namespace.
        callbacks:
            Runtime callback bundle.
        runtime_state:
            Mutable runtime state instance.
        logger:
            Runtime logger.
    """
    resources: RuntimeResources = runtimeResources_initialize(args, callbacks, logger)
    runtime_state.reset()
    runtimeLoop_run(resources, callbacks, runtime_state, logger)


def runtimeResources_initialize(
    args: argparse.Namespace,
    callbacks: ServerRunCallbacks,
    logger: LoggerProtocol,
) -> RuntimeResources:
    """
    Initialize all runtime resources required for server loop.

    Args:
        args:
            Parsed CLI namespace.
        callbacks:
            Runtime callback bundle.
        logger:
            Runtime logger.

    Returns:
        Fully initialized runtime resources.
    """
    config: Config = configWithSettings_load(args)
    loggingWithConfig_setup(args, config, callbacks.logging_setup)
    startupConfiguration_log(config, logger)

    panic_keysyms, panic_modifiers = callbacks.panicKeyConfig_parse(config)
    jump_hotkey = callbacks.jumpHotkeyConfig_parse(config)

    display_manager, input_capturer, screen_geometry, x11native = backendDisplay_initialize(
        args=args,
        config=config,
        logger=logger,
    )
    pointer_tracker: PointerTracker = pointerTracker_initialize(
        display_manager=display_manager,
        config=config,
        logger=logger,
    )
    clientPosition_validate(config, logger)

    network: ServerNetwork = ServerNetwork(
        host=config.server.host,
        port=config.server.port,
        max_clients=config.server.max_clients,
    )
    context_to_client: dict[ScreenContext, str] = contextToClientMap_build(config)
    die_on_disconnect: bool = bool(getattr(args, "die_on_disconnect", False))

    return RuntimeResources(
        config=config,
        display_manager=display_manager,
        input_capturer=input_capturer,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        network=network,
        context_to_client=context_to_client,
        panic_keysyms=panic_keysyms,
        panic_modifiers=panic_modifiers,
        jump_hotkey=jump_hotkey,
        x11native=x11native,
        die_on_disconnect=die_on_disconnect,
    )


def startupConfiguration_log(config: Config, logger: LoggerProtocol) -> None:
    """
    Emit startup configuration telemetry.

    Args:
        config:
            Loaded server config.
        logger:
            Runtime logger.
    """
    logger.info("tx2tx server v%s", __version__)
    logger.info("Server name: %s", config.server.name)
    logger.info("Listening on %s:%s", config.server.host, config.server.port)
    logger.info("Edge threshold: %s pixels", config.server.edge_threshold)
    logger.info(
        "Velocity threshold: %s px/s (edge resistance)",
        config.server.velocity_threshold,
    )
    logger.info("Display: %s", config.server.display or "$DISPLAY")
    logger.info("Max clients: %s", config.server.max_clients)

    if config.clients:
        logger.info("Configured clients: %s", len(config.clients))
        for client in config.clients:
            logger.info("  - %s (position: %s)", client.name, client.position)
    else:
        logger.warning("No clients configured in config.yml")


def backendDisplay_initialize(
    args: argparse.Namespace,
    config: Config,
    logger: LoggerProtocol,
) -> tuple[DisplayBackend, InputCapturer, Screen, bool]:
    """
    Initialize backend components and display connection.

    Args:
        args:
            Parsed CLI namespace.
        config:
            Loaded server config.
        logger:
            Runtime logger.

    Returns:
        Tuple of `(display_manager, input_capturer, screen_geometry, x11native)`.
    """
    backend_options: ServerBackendOptions = backendOptions_resolve(args, config)
    display_manager, input_capturer = serverBackendComponents_create(
        config=config,
        backend_options=backend_options,
    )
    try:
        display_manager.connection_establish()
        screen_geometry: Screen = display_manager.screenGeometry_get()
        logger.info("Screen geometry: %sx%s", screen_geometry.width, screen_geometry.height)
        waylandCalibration_apply(
            display_manager=display_manager,
            screen_geometry=screen_geometry,
            backend_name=backend_options.backend_name,
            wayland_calibrate=backend_options.wayland_calibrate,
            logger=logger,
        )
    except Exception as exc:
        logger.error("Failed to connect to X11 display: %s", exc)
        sys.exit(1)

    return (
        display_manager,
        input_capturer,
        screen_geometry,
        backend_options.x11native,
    )


def waylandCalibration_apply(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    backend_name: str,
    wayland_calibrate: bool,
    logger: LoggerProtocol,
) -> None:
    """
    Apply optional Wayland helper calibration warp at startup.

    Args:
        display_manager:
            Display backend.
        screen_geometry:
            Local screen geometry.
        backend_name:
            Selected backend token.
        wayland_calibrate:
            Whether calibration was requested.
        logger:
            Runtime logger.
    """
    if backend_name.lower() != "wayland":
        return
    if not wayland_calibrate:
        return
    center_position: Position = Position(
        x=screen_geometry.width // 2,
        y=screen_geometry.height // 2,
    )
    logger.info(
        "[CALIBRATE] Warping cursor to (%s, %s) to sync helper state",
        center_position.x,
        center_position.y,
    )
    display_manager.cursorPosition_set(center_position)


def pointerTracker_initialize(
    display_manager: DisplayBackend,
    config: Config,
    logger: LoggerProtocol,
) -> PointerTracker:
    """
    Create pointer tracker with configured thresholds.

    Args:
        display_manager:
            Display backend.
        config:
            Loaded server config.
        logger:
            Runtime logger.

    Returns:
        Initialized pointer tracker.
    """
    pointer_tracker: PointerTracker = PointerTracker(
        display_manager=display_manager,
        edge_threshold=config.server.edge_threshold,
        velocity_threshold=config.server.velocity_threshold,
    )
    logger.info(
        "Pointer tracker initialized (velocity_threshold=%s)",
        config.server.velocity_threshold,
    )
    return pointer_tracker


def clientPosition_validate(config: Config, logger: LoggerProtocol) -> None:
    """
    Validate configured client-position token.

    Args:
        config:
            Loaded server config.
        logger:
            Runtime logger.
    """
    try:
        client_position: ClientPosition = ClientPosition(config.server.client_position)
        logger.info("Client position: %s", client_position.value)
    except ValueError:
        logger.error("Invalid client_position in config: %s", config.server.client_position)
        sys.exit(1)


def runtimeLoop_run(
    resources: RuntimeResources,
    callbacks: ServerRunCallbacks,
    runtime_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Run server network lifecycle and polling loop.

    Args:
        resources:
            Initialized runtime resources.
        callbacks:
            Runtime callback bundle.
        runtime_state:
            Mutable runtime-state instance.
        logger:
            Runtime logger.
    """
    try:
        resources.network.server_start()
        logger.info("Server running. Press Ctrl+C to stop.")
        while resources.network.is_running:
            callbacks.pollingLoop_process(
                network=resources.network,
                display_manager=resources.display_manager,
                pointer_tracker=resources.pointer_tracker,
                screen_geometry=resources.screen_geometry,
                config=resources.config,
                context_to_client=resources.context_to_client,
                panic_keysyms=resources.panic_keysyms,
                panic_modifiers=resources.panic_modifiers,
                x11native=resources.x11native,
                input_capturer=resources.input_capturer,
                jump_hotkey=resources.jump_hotkey,
                die_on_disconnect=resources.die_on_disconnect,
                runtime_state=runtime_state,
            )
    except Exception as exc:
        logger.error("Server error: %s", exc, exc_info=True)
        raise
    finally:
        resources.network.server_stop()
        resources.display_manager.connection_close()
