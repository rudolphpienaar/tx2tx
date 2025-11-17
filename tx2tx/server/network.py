"""TCP server for tx2tx event broadcasting"""

import logging
import select
import socket
from typing import Callable, List, Optional

from tx2tx.protocol.message import Message, MessageBuilder

logger = logging.getLogger(__name__)

# Maximum buffer size to prevent memory exhaustion (1MB)
MAX_BUFFER_SIZE = 1024 * 1024


class ClientConnection:
    """Represents a connected client"""

    def __init__(self, client_socket: socket.socket, address: tuple[str, int]) -> None:
        """
        Initialize client connection

        Args:
            client_socket: Client socket
            address: Client address (host, port)
        """
        self.socket: socket.socket = client_socket
        self.address: tuple[str, int] = address
        self.buffer: str = ""
        self.screen_width: int | None = None
        self.screen_height: int | None = None

    def message_send(self, message: Message) -> None:
        """
        Send message to client

        Args:
            message: Message to send
        """
        data = message.json_serialize() + "\n"
        self.socket.sendall(data.encode("utf-8"))
        # Removed debug log - too noisy

    def data_receive(self) -> List[Message]:
        """
        Receive data from client and parse into messages

        Returns:
            List of complete messages received

        Raises:
            ConnectionError: If connection is closed or error occurs
        """
        try:
            data = self.socket.recv(4096)
            if not data:
                raise ConnectionError("Connection closed by client")

            decoded = data.decode("utf-8")

            # Check buffer size to prevent memory exhaustion
            if len(self.buffer) + len(decoded) > MAX_BUFFER_SIZE:
                logger.error(f"Buffer overflow from {self.address}: buffer size would exceed {MAX_BUFFER_SIZE} bytes")
                raise ConnectionError("Buffer size limit exceeded")

            self.buffer += decoded

            # Parse complete messages (newline-delimited)
            messages: List[Message] = []
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                if line.strip():
                    try:
                        msg = Message.json_deserialize(line)
                        messages.append(msg)
                        # Removed debug log - too noisy
                    except Exception as e:
                        logger.error(f"Failed to parse message from {self.address}: {e}")

            return messages

        except (socket.error, UnicodeDecodeError) as e:
            raise ConnectionError(f"Socket error: {e}")

    def connection_close(self) -> None:
        """Close connection to client"""
        try:
            self.socket.close()
        except Exception as e:
            logger.error(f"Error closing connection to {self.address}: {e}")


class ServerNetwork:
    """TCP server for accepting and managing client connections"""

    def __init__(self, host: str, port: int, max_clients: int = 1) -> None:
        """
        Initialize server network

        Args:
            host: Host address to bind to
            port: Port to listen on
            max_clients: Maximum number of concurrent clients
        """
        self.host: str = host
        self.port: int = port
        self.max_clients: int = max_clients
        self.server_socket: Optional[socket.socket] = None
        self.clients: List[ClientConnection] = []
        self.is_running: bool = False

    def server_start(self) -> None:
        """
        Start TCP server and begin listening for connections

        Raises:
            OSError: If unable to bind to address
        """
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(self.max_clients)
        self.server_socket.setblocking(False)
        self.is_running = True

        logger.info(f"Server listening on {self.host}:{self.port}")

    def server_stop(self) -> None:
        """Stop server and close all connections"""
        self.is_running = False

        # Close all client connections
        for client in self.clients[:]:
            self.client_disconnect(client)

        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                logger.error(f"Error closing server socket: {e}")
            finally:
                self.server_socket = None

        logger.info("Server stopped")

    def connections_accept(self) -> None:
        """Accept pending client connections (non-blocking)"""
        if not self.server_socket:
            return

        # Use select to check if there's a pending connection
        readable, _, _ = select.select([self.server_socket], [], [], 0)
        if not readable:
            return

        try:
            client_socket, address = self.server_socket.accept()
            client_socket.setblocking(False)

            # Check if we've reached max clients
            if len(self.clients) >= self.max_clients:
                logger.warning(f"Max clients reached, rejecting {address}")
                client_socket.close()
                return

            client = ClientConnection(client_socket, address)
            self.clients.append(client)

            # Send hello message
            hello_msg = MessageBuilder.helloMessage_create()
            client.message_send(hello_msg)

            logger.info(f"Client connected: {address}")

        except Exception as e:
            logger.error(f"Error accepting connection: {e}")

    def client_disconnect(self, client: ClientConnection) -> None:
        """
        Disconnect a client

        Args:
            client: Client to disconnect
        """
        if client in self.clients:
            self.clients.remove(client)
            client.connection_close()
            logger.info(f"Client disconnected: {client.address}")

    def clientData_receive(
        self,
        message_handler: Callable[[ClientConnection, Message], None]
    ) -> None:
        """
        Receive data from all connected clients (non-blocking)

        Args:
            message_handler: Callback function for handling received messages
        """
        for client in self.clients[:]:
            # Check if client has data available
            try:
                readable, _, _ = select.select([client.socket], [], [], 0)
                if not readable:
                    continue

                messages = client.data_receive()
                for message in messages:
                    message_handler(client, message)

            except ConnectionError as e:
                logger.warning(f"Client {client.address} connection error: {e}")
                self.client_disconnect(client)
            except Exception as e:
                logger.error(f"Error receiving from {client.address}: {e}")
                self.client_disconnect(client)

    def messageToAll_broadcast(self, message: Message) -> None:
        """
        Broadcast message to all connected clients

        Args:
            message: Message to broadcast
        """
        for client in self.clients[:]:
            try:
                client.message_send(message)
            except Exception as e:
                logger.error(f"Error sending to {client.address}: {e}")
                self.client_disconnect(client)

    def clients_count(self) -> int:
        """
        Get number of connected clients

        Returns:
            Number of connected clients
        """
        return len(self.clients)
