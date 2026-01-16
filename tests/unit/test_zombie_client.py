import unittest
from unittest.mock import MagicMock
from tx2tx.server.network import ServerNetwork, ClientConnection
from tx2tx.protocol.message import Message, MessageType, MessageBuilder
from tx2tx.server.main import clientMessage_handle


class TestZombieClient(unittest.TestCase):
    def test_zombie_client_blackhole_repro(self):
        """
        Verify that if two clients exist with the same name,
        messageToClient_send picks the first one.
        This confirms the NEED for the fix.
        """
        server = ServerNetwork("localhost", 0)

        # Create "Zombie" client
        zombie_socket = MagicMock()
        zombie_client = ClientConnection(zombie_socket, ("127.0.0.1", 10001))
        zombie_client.name = "west"
        server.clients.append(zombie_client)

        # Create "New" client
        new_socket = MagicMock()
        new_client = ClientConnection(new_socket, ("127.0.0.1", 10002))
        new_client.name = "west"
        server.clients.append(new_client)

        # Verify blackhole behavior exists in the Network class itself
        # (This logic wasn't changed, but we avoid it by ensuring unique names)
        msg = Message(MessageType.KEEPALIVE, {})
        server.messageToClient_send("west", msg)
        zombie_socket.sendall.assert_called()
        new_socket.sendall.assert_not_called()

    def test_zombie_cleanup(self):
        """
        Verify that clientMessage_handle disconnects existing clients
        with the same name when a new HELLO is received.
        """
        server = MagicMock(spec=ServerNetwork)
        server.clients = []

        # 1. Setup Zombie Client
        zombie_client = MagicMock(spec=ClientConnection)
        zombie_client.name = "west"
        zombie_client.address = ("127.0.0.1", 10001)
        server.clients.append(zombie_client)

        # 2. Setup New Client (connecting now)
        new_client = MagicMock(spec=ClientConnection)
        new_client.name = None  # Not identified yet
        new_client.address = ("127.0.0.1", 10002)
        new_client.screen_width = 1920
        new_client.screen_height = 1080
        server.clients.append(new_client)

        # 3. Send HELLO from New Client
        hello_msg = MessageBuilder.helloMessage_create(
            client_name="WEST"
        )  # Check case insensitivity too

        # 4. Call handler
        clientMessage_handle(new_client, hello_msg, server)

        # 5. Verify New Client is named correctly
        self.assertEqual(new_client.name, "west")

        # 6. VERIFY: Zombie client was disconnected
        server.client_disconnect.assert_called_with(zombie_client)

        print("\nCONFIRMED: Zombie client disconnected upon name collision.")


if __name__ == "__main__":
    unittest.main()
