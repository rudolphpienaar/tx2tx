"""Unit tests for server handshake/control-plane message handling."""

from __future__ import annotations

from unittest.mock import Mock

from tx2tx.protocol.message import Message, MessageBuilder, MessageType
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.server import server_handshake


class TestServerHandshake:
    """Tests for server handshake policy module."""

    def test_helloMessage_setsGeometryAndName(self) -> None:
        """HELLO payload should set geometry and normalized client name."""
        client = Mock(spec=ClientConnection)
        client.address = ("127.0.0.1", 9999)
        client.name = None
        client.screen_width = None
        client.screen_height = None

        network = Mock(spec=ServerNetwork)
        network.clients = [client]

        logger = Mock()

        hello_message: Message = MessageBuilder.helloMessage_create(
            version="0.1.0",
            screen_width=1920,
            screen_height=1080,
            client_name="PENGUIN",
        )

        server_handshake.clientMessage_handle(
            client=client,
            message=hello_message,
            network=network,
            logger=logger,
        )

        assert client.screen_width == 1920
        assert client.screen_height == 1080
        assert client.name == "penguin"

    def test_helloMessage_disconnectsDuplicateNameClients(self) -> None:
        """HELLO with duplicate name must disconnect stale client entry."""
        stale_client = Mock(spec=ClientConnection)
        stale_client.name = "west"
        stale_client.address = ("127.0.0.1", 10001)

        new_client = Mock(spec=ClientConnection)
        new_client.name = None
        new_client.address = ("127.0.0.1", 10002)
        new_client.screen_width = None
        new_client.screen_height = None

        network = Mock(spec=ServerNetwork)
        network.clients = [stale_client, new_client]

        logger = Mock()

        hello_message: Message = MessageBuilder.helloMessage_create(client_name="WEST")

        server_handshake.clientMessage_handle(
            client=new_client,
            message=hello_message,
            network=network,
            logger=logger,
        )

        network.client_disconnect.assert_called_once_with(stale_client)
        assert new_client.name == "west"

    def test_keepaliveMessage_logsDebugOnly(self) -> None:
        """KEEPALIVE should not mutate client/network state."""
        client = Mock(spec=ClientConnection)
        client.address = ("127.0.0.1", 9999)

        network = Mock(spec=ServerNetwork)
        network.clients = [client]

        logger = Mock()

        keepalive_message: Message = Message(msg_type=MessageType.KEEPALIVE, payload={})
        server_handshake.clientMessage_handle(
            client=client,
            message=keepalive_message,
            network=network,
            logger=logger,
        )

        network.client_disconnect.assert_not_called()
        logger.debug.assert_called_once_with("Keepalive received")
