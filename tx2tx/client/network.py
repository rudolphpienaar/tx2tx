"""TCP client for tx2tx event reception"""

import logging
import select
import socket
import time
from typing import List, Optional

from tx2tx.protocol.message import Message, MessageBuilder

logger = logging.getLogger(__name__)

# Maximum buffer size to prevent memory exhaustion (1MB)
MAX_BUFFER_SIZE = 1024 * 1024


class ClientNetwork:
    """TCP client for connecting to tx2tx server"""

    def __init__(
        self,
        host: str,
        port: int,
        reconnect_enabled: bool = True,
        reconnect_max_attempts: int = 5,
        reconnect_delay: float = 2.0,
    ) -> None:
        """
        Initialize client network
        
        Args:
            host: host value.
            port: port value.
            reconnect_enabled: reconnect_enabled value.
            reconnect_max_attempts: reconnect_max_attempts value.
            reconnect_delay: reconnect_delay value.
        
        Returns:
            Result value.
        """
        self.host: str = host
        self.port: int = port
        self.reconnect_enabled: bool = reconnect_enabled
        self.reconnect_max_attempts: int = reconnect_max_attempts
        self.reconnect_delay: float = reconnect_delay

        self.socket: Optional[socket.socket] = None
        self.buffer: str = ""
        self.is_connected: bool = False
        self.reconnect_attempts: int = 0

    def connection_establish(
        self,
        screen_width: int | None = None,
        screen_height: int | None = None,
        client_name: str | None = None,
    ) -> None:
        """
        Connect to server
        
        Args:
            screen_width: screen_width value.
            screen_height: screen_height value.
            client_name: client_name value.
        
        Returns:
            Result value.
        """
        while self.reconnect_attempts < self.reconnect_max_attempts:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.host, self.port))
                self.socket.setblocking(False)
                self.is_connected = True
                self.reconnect_attempts = 0

                logger.info(f"Connected to server {self.host}:{self.port}")

                # Send hello message with optional screen geometry
                hello_msg = MessageBuilder.helloMessage_create(
                    screen_width=screen_width, screen_height=screen_height, client_name=client_name
                )
                self.message_send(hello_msg)

                return

            except (socket.error, OSError) as e:
                self.reconnect_attempts += 1
                logger.warning(
                    f"Connection attempt {self.reconnect_attempts}/{self.reconnect_max_attempts} "
                    f"failed: {e}"
                )

                if self.socket:
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                    self.socket = None

                if self.reconnect_attempts < self.reconnect_max_attempts:
                    if self.reconnect_enabled:
                        time.sleep(self.reconnect_delay)
                    else:
                        break

        raise ConnectionError(
            f"Failed to connect to {self.host}:{self.port} after "
            f"{self.reconnect_max_attempts} attempts"
        )

    def connection_close(self) -> None:
        """
        Close connection to server
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Close connection to server"""
        self.is_connected = False

        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"Error closing socket: {e}")
            finally:
                self.socket = None

        logger.info("Connection closed")

    def message_send(self, message: Message) -> None:
        """
        Send message to server
        
        Args:
            message: message value.
        
        Returns:
            None.
        """
        if not self.is_connected or not self.socket:
            raise ConnectionError("Not connected to server")

        try:
            data = message.json_serialize() + "\n"
            self.socket.sendall(data.encode("utf-8"))
            # Removed debug log - too noisy

        except (socket.error, OSError) as e:
            self.is_connected = False
            raise ConnectionError(f"Failed to send message: {e}")

    def messages_receive(self) -> List[Message]:
        """
        Receive messages from server (non-blocking)
        
        Args:
            None.
        
        Returns:
            List of received protocol messages.
        """
        if not self.is_connected or not self.socket:
            raise ConnectionError("Not connected to server")

        # Check if data is available
        try:
            readable, _, _ = select.select([self.socket], [], [], 0)
            if not readable:
                return []

            data = self.socket.recv(4096)
            if not data:
                self.is_connected = False
                raise ConnectionError("Connection closed by server")

            decoded = data.decode("utf-8")

            # Check buffer size to prevent memory exhaustion
            if len(self.buffer) + len(decoded) > MAX_BUFFER_SIZE:
                logger.error(f"Buffer overflow: buffer size would exceed {MAX_BUFFER_SIZE} bytes")
                self.is_connected = False
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
                        logger.debug(f"Received from server: {msg.msg_type.value}")
                    except Exception as e:
                        logger.error(f"Failed to parse message: {e}")

            return messages

        except (socket.error, UnicodeDecodeError) as e:
            self.is_connected = False
            raise ConnectionError(f"Socket error: {e}")

    def reconnection_attempt(self) -> bool:
        """
        Attempt to reconnect to server
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        if not self.reconnect_enabled:
            return False

        logger.info("Attempting to reconnect...")

        self.connection_close()
        self.reconnect_attempts = 0

        try:
            self.connection_establish()
            return True
        except ConnectionError as e:
            logger.error(f"Reconnection failed: {e}")
            return False

    def connectionStatus_check(self) -> bool:
        """
        Check if connected to server
        
        Args:
            None.
        
        Returns:
            True if connection is active.
        """
        return self.is_connected
