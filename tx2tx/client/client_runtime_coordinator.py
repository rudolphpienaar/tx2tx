"""
Client runtime coordinator.

This module orchestrates client startup, backend wiring, network session
lifecycle, and the receive/inject loop through explicit callback injection.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from tx2tx import __version__
from tx2tx.client.bootstrap import (
    backendOptions_resolve,
    configWithSettings_load,
    displayConnection_establish,
    loggingWithConfig_setup,
    serverAddressWithConfig_parse,
    softwareCursor_create,
)
from tx2tx.client.network import ClientNetwork
from tx2tx.common.config import Config
from tx2tx.common.runtime_models import ClientBackendOptions
from tx2tx.common.settings import settings
from tx2tx.common.types import Screen
from tx2tx.input.backend import DisplayBackend, InputInjector
from tx2tx.input.factory import clientBackend_create
from tx2tx.protocol.message import Message
from tx2tx.x11.software_cursor import SoftwareCursor

__all__ = [
    "ClientRuntimeResources",
    "ClientRunCallbacks",
    "client_run",
    "messageLoop_run",
    "messageLoopWithComponents_run",
]


class LoggerProtocol(Protocol):
    """Minimal logger contract used by client runtime coordinator."""

    def info(self, msg: str, *args: object) -> None:
        """Emit info-level log message."""
        ...

    def warning(self, msg: str, *args: object) -> None:
        """Emit warning-level log message."""
        ...

    def error(self, msg: str, *args: object, exc_info: bool = False) -> None:
        """Emit error-level log message."""
        ...


class ServerAddressParseProtocol(Protocol):
    """Contract for server address parse callback."""

    def __call__(self, server: str) -> tuple[str, int]:
        """Parse host and port from server string."""
        ...


class LoggingSetupProtocol(Protocol):
    """Contract for logging setup callback."""

    def __call__(self, level: str, log_format: str, log_file: str | None) -> None:
        """Configure runtime logging for client process."""
        ...


class ServerMessageHandleProtocol(Protocol):
    """Contract for single-message dispatch callback."""

    def __call__(
        self,
        message: Message,
        injector: InputInjector | None,
        display_manager: DisplayBackend | None,
        software_cursor: SoftwareCursor | None,
    ) -> None:
        """Handle one incoming server message."""
        ...


@dataclass
class ClientRunCallbacks:
    """
    Callback bundle used by client runtime coordinator.

    Attributes:
        serverAddress_parse:
            Server-address parse callback.
        logging_setup:
            Logging setup callback.
        serverMessage_handle:
            Message dispatch callback.
    """

    serverAddress_parse: ServerAddressParseProtocol
    logging_setup: LoggingSetupProtocol
    serverMessage_handle: ServerMessageHandleProtocol


@dataclass
class ClientRuntimeResources:
    """
    Runtime resources required by client message loop.

    Attributes:
        config:
            Loaded client config.
        network:
            Client network transport.
        event_injector:
            Backend input injector.
        display_manager:
            Backend display manager.
        software_cursor:
            Optional software cursor.
        reconnect_enabled:
            Whether automatic reconnect is enabled.
        client_name:
            Optional client name.
        host:
            Target server host.
        port:
            Target server port.
        screen_geometry:
            Local screen geometry.
    """

    config: Config
    network: ClientNetwork
    event_injector: InputInjector
    display_manager: DisplayBackend
    software_cursor: SoftwareCursor | None
    reconnect_enabled: bool
    client_name: str | None
    host: str
    port: int
    screen_geometry: Screen


def client_run(
    args: argparse.Namespace,
    callbacks: ClientRunCallbacks,
    logger: LoggerProtocol,
) -> None:
    """
    Execute client startup and runtime loop lifecycle.

    Args:
        args:
            Parsed client CLI namespace.
        callbacks:
            Runtime callback bundle.
        logger:
            Runtime logger.
    """
    resources: ClientRuntimeResources = runtimeResources_initialize(args, callbacks, logger)
    runtimeLoop_run(resources, callbacks, logger)


def runtimeResources_initialize(
    args: argparse.Namespace,
    callbacks: ClientRunCallbacks,
    logger: LoggerProtocol,
) -> ClientRuntimeResources:
    """
    Initialize client runtime resources.

    Args:
        args:
            Parsed client CLI namespace.
        callbacks:
            Runtime callback bundle.
        logger:
            Runtime logger.

    Returns:
        Fully initialized client runtime resources.
    """
    config: Config = configWithSettings_load(args)
    loggingWithConfig_setup(args, config, callbacks.logging_setup)
    host: str
    port: int
    host, port = serverAddressWithConfig_parse(config, callbacks.serverAddress_parse)
    startupConfiguration_log(args, config, host, port, logger)

    backend_options: ClientBackendOptions = backendOptions_resolve(args, config)
    display_manager, event_injector = clientBackend_create(
        backend_name=backend_options.backend_name,
        display_name=config.client.display,
        wayland_helper=backend_options.wayland_helper,
    )
    screen_geometry: Screen = displayConnection_establish(display_manager)
    injectionReadiness_validate(event_injector, display_manager, logger)

    software_cursor: SoftwareCursor | None = softwareCursor_create(
        args=args,
        backend_name=backend_options.backend_name,
        display_manager=display_manager,
    )

    network: ClientNetwork = ClientNetwork(
        host=host,
        port=port,
        reconnect_enabled=config.client.reconnect.enabled,
        reconnect_max_attempts=config.client.reconnect.max_attempts,
        reconnect_delay=config.client.reconnect.delay_seconds,
    )

    return ClientRuntimeResources(
        config=config,
        network=network,
        event_injector=event_injector,
        display_manager=display_manager,
        software_cursor=software_cursor,
        reconnect_enabled=config.client.reconnect.enabled,
        client_name=args.name,
        host=host,
        port=port,
        screen_geometry=screen_geometry,
    )


def startupConfiguration_log(
    args: argparse.Namespace,
    config: Config,
    host: str,
    port: int,
    logger: LoggerProtocol,
) -> None:
    """
    Emit startup configuration telemetry for client process.

    Args:
        args:
            Parsed client CLI namespace.
        config:
            Loaded client config.
        host:
            Target server host.
        port:
            Target server port.
        logger:
            Runtime logger.
    """
    logger.info("tx2tx client v%s", __version__)
    if args.name:
        logger.info("Client name: %s", args.name)
    logger.info("Connecting to %s:%s", host, port)
    logger.info("Display: %s", config.client.display or "$DISPLAY")


def injectionReadiness_validate(
    event_injector: InputInjector,
    display_manager: DisplayBackend,
    logger: LoggerProtocol,
) -> None:
    """
    Validate backend injection readiness before network session start.

    Args:
        event_injector:
            Input injector instance.
        display_manager:
            Display backend instance.
        logger:
            Runtime logger.
    """
    if event_injector.injectionReady_check():
        logger.info("Input injection ready")
        return

    logger.error("Input injection not available for selected backend")
    display_manager.connection_close()
    sys.exit(1)


def runtimeLoop_run(
    resources: ClientRuntimeResources,
    callbacks: ClientRunCallbacks,
    logger: LoggerProtocol,
) -> None:
    """
    Execute connection lifecycle and process message loop.

    Args:
        resources:
            Initialized client runtime resources.
        callbacks:
            Runtime callback bundle.
        logger:
            Runtime logger.
    """
    try:
        resources.network.connection_establish(
            screen_width=resources.screen_geometry.width,
            screen_height=resources.screen_geometry.height,
            client_name=resources.client_name,
        )
        logger.info("Client running. Press Ctrl+C to stop.")
        messageLoop_run(resources, callbacks, logger)
    except ConnectionError as exc:
        logger.error("Failed to connect: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Client error: %s", exc, exc_info=True)
        raise
    finally:
        resources.network.connection_close()
        resources.display_manager.connection_close()


def messageLoop_run(
    resources: ClientRuntimeResources,
    callbacks: ClientRunCallbacks,
    logger: LoggerProtocol,
) -> None:
    """
    Run client receive/inject loop.

    Args:
        resources:
            Client runtime resources.
        callbacks:
            Runtime callback bundle.
        logger:
            Runtime logger.
    """
    messageLoopWithComponents_run(
        network=resources.network,
        event_injector=resources.event_injector,
        display_manager=resources.display_manager,
        software_cursor=resources.software_cursor,
        reconnect_enabled=resources.reconnect_enabled,
        callbacks=callbacks,
        logger=logger,
    )


def messageLoopWithComponents_run(
    network: ClientNetwork,
    event_injector: InputInjector,
    display_manager: DisplayBackend,
    software_cursor: SoftwareCursor | None,
    reconnect_enabled: bool,
    callbacks: ClientRunCallbacks,
    logger: LoggerProtocol,
) -> None:
    """
    Run client receive/inject loop from explicit components.

    Args:
        network:
            Client network transport.
        event_injector:
            Input injector.
        display_manager:
            Display backend.
        software_cursor:
            Optional software cursor.
        reconnect_enabled:
            Whether automatic reconnect is enabled.
        callbacks:
            Runtime callback bundle.
        logger:
            Runtime logger.
    """
    while network.connectionStatus_check():
        try:
            loopStepWithComponents_process(
                network=network,
                event_injector=event_injector,
                display_manager=display_manager,
                software_cursor=software_cursor,
                callbacks=callbacks,
            )
            time.sleep(settings.RECONNECT_CHECK_INTERVAL)
        except ConnectionError as exc:
            logger.error("Connection error: %s", exc)
            if not reconnect_enabled:
                break
            if network.reconnection_attempt():
                logger.info("Reconnected successfully")
                continue
            logger.error("Reconnection failed, exiting")
            break


def loopStep_process(resources: ClientRuntimeResources, callbacks: ClientRunCallbacks) -> None:
    """
    Process one loop step by receiving and dispatching all pending messages.

    Args:
        resources:
            Client runtime resources.
        callbacks:
            Runtime callback bundle.
    """
    loopStepWithComponents_process(
        network=resources.network,
        event_injector=resources.event_injector,
        display_manager=resources.display_manager,
        software_cursor=resources.software_cursor,
        callbacks=callbacks,
    )


def loopStepWithComponents_process(
    network: ClientNetwork,
    event_injector: InputInjector,
    display_manager: DisplayBackend,
    software_cursor: SoftwareCursor | None,
    callbacks: ClientRunCallbacks,
) -> None:
    """
    Process one loop step from explicit components.

    Args:
        network:
            Client network transport.
        event_injector:
            Input injector.
        display_manager:
            Display backend.
        software_cursor:
            Optional software cursor.
        callbacks:
            Runtime callback bundle.
    """
    messages: list[Message] = network.messages_receive()
    message: Message
    for message in messages:
        callbacks.serverMessage_handle(
            message,
            event_injector,
            display_manager,
            software_cursor,
        )
