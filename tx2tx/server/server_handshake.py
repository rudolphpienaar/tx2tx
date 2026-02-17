"""
Server-side client handshake and control-plane message handling.

This module owns processing of inbound non-input client messages during server
runtime. It keeps handshake semantics, duplicate-client eviction, and message
classification isolated from runtime orchestration.
"""

from __future__ import annotations

from typing import Protocol

from tx2tx.protocol.message import Message, MessageType
from tx2tx.server.network import ClientConnection, ServerNetwork

__all__ = [
    "clientMessage_handle",
    "helloMessage_handle",
    "clientGeometryFromPayload_apply",
    "clientNameFromPayload_apply",
    "duplicateNameClients_disconnect",
]


class LoggerProtocol(Protocol):
    """Minimal logger contract for handshake message handling."""

    def info(self, msg: str, *args: object) -> None:
        """Emit info-level message."""
        ...

    def debug(self, msg: str, *args: object) -> None:
        """Emit debug-level message."""
        ...

    def warning(self, msg: str, *args: object) -> None:
        """Emit warning-level message."""
        ...


def clientMessage_handle(
    client: ClientConnection,
    message: Message,
    network: ServerNetwork,
    logger: LoggerProtocol,
) -> None:
    """
    Process one client control-plane message.

    Args:
        client:
            Originating client connection.
        message:
            Decoded inbound message.
        network:
            Server network manager.
        logger:
            Runtime logger.
    """
    logger.info("Received %s from %s", message.msg_type.value, client.address)

    if message.msg_type == MessageType.HELLO:
        helloMessage_handle(client, message, network, logger)
        return
    if message.msg_type == MessageType.KEEPALIVE:
        logger.debug("Keepalive received")
        return
    if message.msg_type == MessageType.SCREEN_ENTER:
        logger.warning("Received deprecated SCREEN_ENTER message from client (ignored)")
        return

    logger.warning("Unexpected message type: %s", message.msg_type.value)


def helloMessage_handle(
    client: ClientConnection,
    message: Message,
    network: ServerNetwork,
    logger: LoggerProtocol,
) -> None:
    """
    Process HELLO handshake message and update client metadata.

    Args:
        client:
            Originating client connection.
        message:
            HELLO message payload.
        network:
            Server network manager.
        logger:
            Runtime logger.
    """
    payload: dict[str, object] = message.payload
    clientGeometryFromPayload_apply(client, payload)
    clientNameFromPayload_apply(client, payload, network, logger)

    logger.info(
        "Client handshake: version=%s, screen=%sx%s, name=%s",
        payload.get("version"),
        client.screen_width,
        client.screen_height,
        client.name,
    )


def clientGeometryFromPayload_apply(
    client: ClientConnection,
    payload: dict[str, object],
) -> None:
    """
    Apply optional screen geometry metadata from handshake payload.

    Args:
        client:
            Originating client connection.
        payload:
            HELLO message payload dictionary.
    """
    if "screen_width" not in payload or "screen_height" not in payload:
        return
    screen_width_raw: object = payload["screen_width"]
    screen_height_raw: object = payload["screen_height"]
    if not isinstance(screen_width_raw, (int, str)):
        return
    if not isinstance(screen_height_raw, (int, str)):
        return
    client.screen_width = int(screen_width_raw)
    client.screen_height = int(screen_height_raw)


def clientNameFromPayload_apply(
    client: ClientConnection,
    payload: dict[str, object],
    network: ServerNetwork,
    logger: LoggerProtocol,
) -> None:
    """
    Apply normalized client name and evict stale duplicate-name clients.

    Args:
        client:
            Originating client connection.
        payload:
            HELLO message payload dictionary.
        network:
            Server network manager.
        logger:
            Runtime logger.
    """
    if "client_name" not in payload:
        return

    normalized_name: str = str(payload["client_name"]).lower()
    client.name = normalized_name
    duplicateNameClients_disconnect(client, normalized_name, network, logger)


def duplicateNameClients_disconnect(
    client: ClientConnection,
    normalized_name: str,
    network: ServerNetwork,
    logger: LoggerProtocol,
) -> None:
    """
    Disconnect older clients that collide on normalized logical name.

    Args:
        client:
            Newly identified client.
        normalized_name:
            Lowercase normalized client name.
        network:
            Server network manager.
        logger:
            Runtime logger.
    """
    for existing_client in list(network.clients):
        if existing_client is client:
            continue
        if existing_client.name != normalized_name:
            continue
        logger.warning(
            "Duplicate client name '%s' detected. Disconnecting old connection from %s.",
            normalized_name,
            existing_client.address,
        )
        network.client_disconnect(existing_client)
