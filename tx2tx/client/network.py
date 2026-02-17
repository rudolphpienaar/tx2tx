"""
TCP client transport for tx2tx.

This module owns connection lifecycle, handshake transmission, and message I/O
for the tx2tx client process.
"""

from __future__ import annotations

import logging
import select
import socket
import time

from tx2tx.protocol.message import Message, MessageBuilder

logger = logging.getLogger(__name__)

# Maximum buffer size to prevent memory exhaustion (1MB).
MAX_BUFFER_SIZE = 1024 * 1024


class ClientNetwork:
    """
    TCP transport used by the tx2tx client runtime.

    The transport supports optional reconnect policy and newline-delimited
    protocol message framing.
    """

    def __init__(
        self,
        host: str,
        port: int,
        reconnect_enabled: bool = True,
        reconnect_max_attempts: int = 5,
        reconnect_delay: float = 2.0,
    ) -> None:
        """
        Initialize client network transport configuration.

        Args:
            host:
                Server host.
            port:
                Server port.
            reconnect_enabled:
                Whether reconnect attempts are enabled.
            reconnect_max_attempts:
                Maximum reconnect attempt count.
            reconnect_delay:
                Delay between reconnect attempts in seconds.
        """
        self.host: str = host
        self.port: int = port
        self.reconnect_enabled: bool = reconnect_enabled
        self.reconnect_max_attempts: int = reconnect_max_attempts
        self.reconnect_delay: float = reconnect_delay

        self.socket: socket.socket | None = None
        self.buffer: str = ""
        self.is_connected: bool = False
        self.reconnect_attempts: int = 0

        self._hello_screen_width: int | None = None
        self._hello_screen_height: int | None = None
        self._hello_client_name: str | None = None

    def connection_establish(
        self,
        screen_width: int | None = None,
        screen_height: int | None = None,
        client_name: str | None = None,
    ) -> None:
        """
        Establish server connection and send client hello.

        Args:
            screen_width:
                Optional local screen width reported in hello.
            screen_height:
                Optional local screen height reported in hello.
            client_name:
                Optional client name reported in hello.

        Raises:
            ConnectionError:
                Raised when all connection attempts fail.
        """
        self.helloMetadata_store(screen_width, screen_height, client_name)
        while self.reconnectAttempts_available():
            if self.connectionAttempt_try():
                return
        raise ConnectionError(
            f"Failed to connect to {self.host}:{self.port} after "
            f"{self.reconnect_max_attempts} attempts"
        )

    def helloMetadata_store(
        self,
        screen_width: int | None,
        screen_height: int | None,
        client_name: str | None,
    ) -> None:
        """
        Persist hello metadata for initial connect and future reconnects.

        Args:
            screen_width:
                Optional screen width.
            screen_height:
                Optional screen height.
            client_name:
                Optional client name.
        """
        if screen_width is not None:
            self._hello_screen_width = screen_width
        if screen_height is not None:
            self._hello_screen_height = screen_height
        if client_name is not None:
            self._hello_client_name = client_name

    def reconnectAttempts_available(self) -> bool:
        """
        Check whether another connect attempt is available.

        Returns:
            `True` when attempts remain, else `False`.
        """
        return self.reconnect_attempts < self.reconnect_max_attempts

    def connectionAttempt_try(self) -> bool:
        """
        Attempt one connect+hello sequence.

        Returns:
            `True` when connection succeeds, else `False`.
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.socket.setblocking(False)
            self.is_connected = True
            self.reconnect_attempts = 0
            logger.info("Connected to server %s:%s", self.host, self.port)
            self.helloMessage_send()
            return True
        except (socket.error, OSError) as exc:
            self.connectionAttemptFailed_handle(exc)
            return False

    def helloMessage_send(self) -> None:
        """
        Send hello message with persisted screen metadata.

        Raises:
            ConnectionError:
                Raised when message write fails.
        """
        hello_msg: Message = MessageBuilder.helloMessage_create(
            screen_width=self._hello_screen_width,
            screen_height=self._hello_screen_height,
            client_name=self._hello_client_name,
        )
        self.message_send(hello_msg)

    def connectionAttemptFailed_handle(self, error: Exception) -> None:
        """
        Handle failed connection attempt and retry backoff policy.

        Args:
            error:
                Connect error for log context.
        """
        self.reconnect_attempts += 1
        logger.warning(
            "Connection attempt %s/%s failed: %s",
            self.reconnect_attempts,
            self.reconnect_max_attempts,
            error,
        )
        self.socket_cleanup()

        if self.reconnect_attempts >= self.reconnect_max_attempts:
            return
        if not self.reconnect_enabled:
            self.reconnect_attempts = self.reconnect_max_attempts
            return
        time.sleep(self.reconnect_delay)

    def socket_cleanup(self) -> None:
        """
        Close and reset socket handle.

        This helper suppresses close errors intentionally because the caller is
        already in an error-recovery path.
        """
        if self.socket is None:
            return
        try:
            self.socket.close()
        except Exception:
            pass
        self.socket = None
        self.is_connected = False

    def connection_close(self) -> None:
        """
        Close connection to server.

        This method is idempotent.
        """
        self.is_connected = False
        if self.socket is not None:
            try:
                self.socket.close()
            except Exception as exc:
                logger.error("Error closing socket: %s", exc)
            finally:
                self.socket = None
        logger.info("Connection closed")

    def message_send(self, message: Message) -> None:
        """
        Send protocol message to server.

        Args:
            message:
                Protocol message to send.

        Raises:
            ConnectionError:
                Raised when socket is unavailable or write fails.
        """
        if not self.is_connected or self.socket is None:
            raise ConnectionError("Not connected to server")

        try:
            data: str = message.json_serialize() + "\n"
            self.socket.sendall(data.encode("utf-8"))
        except (socket.error, OSError) as exc:
            self.is_connected = False
            raise ConnectionError(f"Failed to send message: {exc}") from exc

    def messages_receive(self) -> list[Message]:
        """
        Receive and decode available server messages.

        Returns:
            List of parsed protocol messages.

        Raises:
            ConnectionError:
                Raised on socket disconnect, buffer overflow, or decode failure.
        """
        if not self.is_connected or self.socket is None:
            raise ConnectionError("Not connected to server")

        try:
            readable, _, _ = select.select([self.socket], [], [], 0)
            if not readable:
                return []

            data: bytes = self.socket.recv(4096)
            if not data:
                self.is_connected = False
                raise ConnectionError("Connection closed by server")

            decoded: str = data.decode("utf-8")
            self.bufferOverflow_validate(decoded)
            self.buffer += decoded
            return self.bufferMessages_parse()
        except (socket.error, UnicodeDecodeError) as exc:
            self.is_connected = False
            raise ConnectionError(f"Socket error: {exc}") from exc

    def bufferOverflow_validate(self, decoded: str) -> None:
        """
        Validate buffered payload does not exceed configured cap.

        Args:
            decoded:
                Newly decoded payload chunk.

        Raises:
            ConnectionError:
                Raised when buffer limit would be exceeded.
        """
        if len(self.buffer) + len(decoded) <= MAX_BUFFER_SIZE:
            return
        logger.error("Buffer overflow: buffer size would exceed %s bytes", MAX_BUFFER_SIZE)
        self.is_connected = False
        raise ConnectionError("Buffer size limit exceeded")

    def bufferMessages_parse(self) -> list[Message]:
        """
        Parse newline-delimited messages from internal buffer.

        Returns:
            List of successfully parsed protocol messages.
        """
        messages: list[Message] = []
        while "\n" in self.buffer:
            line: str
            line, self.buffer = self.buffer.split("\n", 1)
            if not line.strip():
                continue
            try:
                message: Message = Message.json_deserialize(line)
                messages.append(message)
                logger.debug("Received from server: %s", message.msg_type.value)
            except Exception as exc:
                logger.error("Failed to parse message: %s", exc)
        return messages

    def reconnection_attempt(self) -> bool:
        """
        Attempt reconnect using persisted hello metadata.

        Returns:
            `True` when reconnect succeeds, else `False`.
        """
        if not self.reconnect_enabled:
            return False

        logger.info("Attempting to reconnect...")
        self.connection_close()
        self.reconnect_attempts = 0

        try:
            self.connection_establish(
                screen_width=self._hello_screen_width,
                screen_height=self._hello_screen_height,
                client_name=self._hello_client_name,
            )
            return True
        except ConnectionError as exc:
            logger.error("Reconnection failed: %s", exc)
            return False

    def connectionStatus_check(self) -> bool:
        """
        Check connection status.

        Returns:
            `True` when connected, else `False`.
        """
        return self.is_connected and self.socket is not None
