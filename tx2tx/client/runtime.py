"""
Client runtime compatibility API.

This module preserves legacy import symbols while delegating implementation
to focused client modules.
"""

from __future__ import annotations

import argparse
import logging

from tx2tx.client.client_cli import arguments_parse as _arguments_parse
from tx2tx.client.client_cli import serverAddress_parse as _serverAddress_parse
from tx2tx.client.client_dispatch import keyMessage_handle as _keyMessage_handle
from tx2tx.client.client_dispatch import mouseEventForInjection_build as _mouseEventForInjection_build
from tx2tx.client.client_dispatch import mouseMessage_handle as _mouseMessage_handle
from tx2tx.client.client_dispatch import serverMessage_handle as _serverMessage_handle
from tx2tx.client.client_logging import logging_setup as _logging_setup
from tx2tx.client.client_runtime_coordinator import ClientRunCallbacks
from tx2tx.client.client_runtime_coordinator import client_run as _client_run
from tx2tx.client.network import ClientNetwork
from tx2tx.common.types import MouseEvent
from tx2tx.input.backend import DisplayBackend, InputInjector
from tx2tx.protocol.message import Message
from tx2tx.client.client_runtime_coordinator import (
    messageLoopWithComponents_run as _messageLoopWithComponents_run,
)
from tx2tx.x11.software_cursor import SoftwareCursor

logger = logging.getLogger(__name__)

__all__ = [
    "arguments_parse",
    "serverAddress_parse",
    "logging_setup",
    "serverMessage_handle",
    "mouseMessage_handle",
    "mouseEventForInjection_build",
    "keyMessage_handle",
    "client_run",
    "messageLoop_run",
    "ClientRunCallbacks",
]


def arguments_parse() -> argparse.Namespace:
    """
    Compatibility wrapper for client CLI argument parsing.

    Returns:
        Parsed client CLI namespace.
    """
    return _arguments_parse()


def serverAddress_parse(server: str) -> tuple[str, int]:
    """
    Compatibility wrapper for server-address parsing.

    Args:
        server:
            Server endpoint as `host:port`.

    Returns:
        Tuple of `(host, port)`.
    """
    return _serverAddress_parse(server)


def logging_setup(level: str, log_format: str, log_file: str | None) -> None:
    """
    Compatibility wrapper for client logging setup.

    Args:
        level:
            Log level name.
        log_format:
            Base logging format string.
        log_file:
            Optional log-file path.
    """
    _logging_setup(level, log_format, log_file)


def serverMessage_handle(
    message: Message,
    injector: InputInjector | None = None,
    display_manager: DisplayBackend | None = None,
    software_cursor: SoftwareCursor | None = None,
) -> None:
    """
    Compatibility wrapper for server message dispatch.

    Args:
        message:
            Incoming protocol message.
        injector:
            Optional input injector.
        display_manager:
            Optional display backend.
        software_cursor:
            Optional software cursor.
    """
    _serverMessage_handle(message, injector, display_manager, software_cursor)


def mouseMessage_handle(
    message: Message,
    injector: InputInjector | None,
    display_manager: DisplayBackend | None,
    software_cursor: SoftwareCursor | None,
) -> None:
    """
    Compatibility wrapper for mouse message handling.

    Args:
        message:
            Incoming protocol message.
        injector:
            Optional input injector.
        display_manager:
            Optional display backend.
        software_cursor:
            Optional software cursor.
    """
    _mouseMessage_handle(message, injector, display_manager, software_cursor)


def mouseEventForInjection_build(
    mouse_event: MouseEvent,
    display_manager: DisplayBackend,
    software_cursor: SoftwareCursor | None,
) -> MouseEvent | None:
    """
    Compatibility wrapper for mouse event normalization policy.

    Args:
        mouse_event:
            Incoming protocol mouse event.
        display_manager:
            Local display backend.
        software_cursor:
            Optional software cursor.

    Returns:
        Injection-ready mouse event, or `None`.
    """
    return _mouseEventForInjection_build(mouse_event, display_manager, software_cursor)


def keyMessage_handle(message: Message, injector: InputInjector | None) -> None:
    """
    Compatibility wrapper for key message handling.

    Args:
        message:
            Incoming protocol message.
        injector:
            Optional input injector.
    """
    _keyMessage_handle(message, injector)


def client_run(args: argparse.Namespace) -> None:
    """
    Compatibility wrapper for client runtime execution.

    Args:
        args:
            Parsed client CLI namespace.
    """
    callbacks: ClientRunCallbacks = ClientRunCallbacks(
        serverAddress_parse=serverAddress_parse,
        logging_setup=logging_setup,
        serverMessage_handle=serverMessage_handle,
    )
    _client_run(args=args, callbacks=callbacks, logger=logger)


def messageLoop_run(
    network: ClientNetwork,
    event_injector: InputInjector,
    display_manager: DisplayBackend,
    software_cursor: SoftwareCursor | None,
    reconnect_enabled: bool,
) -> None:
    """
    Compatibility wrapper for legacy message-loop signature.

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
            Reconnect policy flag.
    """
    callbacks: ClientRunCallbacks = ClientRunCallbacks(
        serverAddress_parse=serverAddress_parse,
        logging_setup=logging_setup,
        serverMessage_handle=serverMessage_handle,
    )
    _messageLoopWithComponents_run(
        network=network,
        event_injector=event_injector,
        display_manager=display_manager,
        software_cursor=software_cursor,
        reconnect_enabled=reconnect_enabled,
        callbacks=callbacks,
        logger=logger,
    )
