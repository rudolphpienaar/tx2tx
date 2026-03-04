"""
GNOME truth-bridge pointer provider.

This provider reads compositor-authoritative pointer telemetry from a local
Unix stream socket produced by a GNOME Shell extension bridge. The bridge emits
JSON lines with at least `x` and `y` fields.
"""

from __future__ import annotations

import json
import logging
import os
import select
import socket
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PointerSample:
    """Immutable pointer sample emitted by GNOME truth bridge."""

    x: int
    y: int
    timestamp_seconds: float


class GnomeTruthBridgePointerProvider:
    """
    Read pointer coordinates from GNOME truth-bridge Unix socket.

    The provider keeps one open connection, consumes all currently-available
    frames, and returns the newest fresh sample. Frames older than the staleness
    threshold are treated as invalid.
    """

    def __init__(
        self,
        socket_path: str,
        stale_after_seconds: float = 0.25,
        connect_timeout_seconds: float = 0.1,
    ) -> None:
        """
        Initialize bridge provider.

        Args:
            socket_path:
                Unix socket path published by GNOME extension bridge.
            stale_after_seconds:
                Maximum accepted sample age.
            connect_timeout_seconds:
                Socket connect timeout.
        """
        self._socket_path: str = socket_path
        self._stale_after_seconds: float = stale_after_seconds
        self._connect_timeout_seconds: float = connect_timeout_seconds
        self._socket: socket.socket | None = None
        self._buffer: str = ""
        self._latest_sample: _PointerSample | None = None
        self._warned: bool = False

    def pointerPosition_get(self) -> tuple[int, int]:
        """
        Return current pointer coordinates from bridge stream.

        Returns:
            `(x, y)` pointer coordinates.

        Raises:
            RuntimeError:
                When bridge connection or sample freshness requirements fail.
        """
        self._connectionEnsure_establish()
        self._framesAvailable_consume()
        if self._latest_sample is None:
            raise RuntimeError("GNOME truth bridge has no pointer sample yet")
        sample_age: float = time.time() - self._latest_sample.timestamp_seconds
        if sample_age > self._stale_after_seconds:
            raise RuntimeError(
                "GNOME truth bridge sample stale: "
                f"age={sample_age:.3f}s threshold={self._stale_after_seconds:.3f}s"
            )
        return self._latest_sample.x, self._latest_sample.y

    def fallback_log(self, error: Exception) -> None:
        """
        Emit one-time warning when backend must fall back to helper telemetry.

        Args:
            error:
                Bridge read failure.
        """
        if not self._warned:
            logger.warning("GNOME truth bridge unavailable, falling back to helper: %s", error)
            self._warned = True

    def connection_close(self) -> None:
        """Close bridge socket and reset parser state."""
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None
        self._buffer = ""

    def _connectionEnsure_establish(self) -> None:
        """
        Ensure socket connection is established.

        Raises:
            RuntimeError:
                When socket path is invalid or connection fails.
        """
        if self._socket is not None:
            return
        if not self._socket_path:
            raise RuntimeError("GNOME truth bridge socket path is empty")
        if not os.path.exists(self._socket_path):
            raise RuntimeError(f"GNOME truth bridge socket not found: {self._socket_path}")
        bridge_socket: socket.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            bridge_socket.settimeout(self._connect_timeout_seconds)
            bridge_socket.connect(self._socket_path)
            bridge_socket.settimeout(None)
            bridge_socket.setblocking(False)
        except OSError as exc:
            bridge_socket.close()
            raise RuntimeError(
                f"failed to connect GNOME truth bridge socket '{self._socket_path}': {exc}"
            ) from exc
        self._socket = bridge_socket
        self._warned = False

    def _framesAvailable_consume(self) -> None:
        """
        Consume all currently available bridge frames without blocking.

        Raises:
            RuntimeError:
                When stream closes or frame parse fails.
        """
        assert self._socket is not None
        while True:
            readable, _, _ = select.select([self._socket], [], [], 0.0)
            if not readable:
                return
            try:
                chunk: bytes = self._socket.recv(8192)
            except BlockingIOError:
                return
            except OSError as exc:
                self.connection_close()
                raise RuntimeError(f"GNOME truth bridge recv failed: {exc}") from exc
            if not chunk:
                self.connection_close()
                raise RuntimeError("GNOME truth bridge disconnected")
            self._buffer += chunk.decode("utf-8")
            self._bufferLines_parse()

    def _bufferLines_parse(self) -> None:
        """
        Parse complete newline-delimited JSON frames in internal buffer.

        Raises:
            RuntimeError:
                When a complete frame is malformed.
        """
        while "\n" in self._buffer:
            frame_raw, self._buffer = self._buffer.split("\n", 1)
            frame_trimmed: str = frame_raw.strip()
            if not frame_trimmed:
                continue
            self._latest_sample = self._frameSample_parse(frame_trimmed)

    @staticmethod
    def _frameSample_parse(frame_json: str) -> _PointerSample:
        """
        Parse one JSON frame into immutable pointer sample.

        Args:
            frame_json:
                One JSON frame from bridge stream.

        Returns:
            Parsed pointer sample.

        Raises:
            RuntimeError:
                When required fields are missing or invalid.
        """
        try:
            payload = json.loads(frame_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid GNOME truth bridge JSON frame: {frame_json}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"GNOME truth bridge frame is not object: {frame_json}")
        if "x" not in payload or "y" not in payload:
            raise RuntimeError(f"GNOME truth bridge frame missing coordinates: {frame_json}")
        x_value: int = int(payload["x"])
        y_value: int = int(payload["y"])
        timestamp_value: float = float(payload.get("ts", time.time()))
        return _PointerSample(x=x_value, y=y_value, timestamp_seconds=timestamp_value)
