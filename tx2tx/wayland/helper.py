"""Wayland helper client for privileged input operations."""

from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any, Optional, TextIO


class WaylandHelperClient:
    """JSON line protocol client for a privileged Wayland helper."""

    def __init__(self, command: str) -> None:
        """
        Initialize helper client.
        
        Args:
            command: command value.
        
        Returns:
            Result value.
        """
        self._command: str = command
        self._process: Optional[subprocess.Popen[str]] = None
        self._stdin: Optional[TextIO] = None
        self._stdout: Optional[TextIO] = None

    def connection_establish(self) -> None:
        """
        Start helper process and validate handshake.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Start helper process and validate handshake."""
        if self._process is not None:
            return

        self._process = subprocess.Popen(
            shlex.split(self._command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._stdin = self._process.stdin
        self._stdout = self._process.stdout

        if self._stdin is None or self._stdout is None:
            raise RuntimeError("Failed to open helper stdin/stdout")

        self._request("hello", {})

    def connection_close(self) -> None:
        """
        Request shutdown and terminate helper process.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Request shutdown and terminate helper process."""
        if self._stdin:
            try:
                self._stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                self._stdin.flush()
            except Exception:
                pass

        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None
            self._stdin = None
            self._stdout = None

    def _request(self, cmd: str, payload: dict[str, Any]) -> Any:
        """
        Send request to helper and parse JSON response.
        
        Args:
            cmd: Command name
            payload: Command payload
        
        Returns:
            Helper result payload
        """
        if self._stdin is None or self._stdout is None:
            raise RuntimeError("Helper connection not established")

        request = {"cmd": cmd, "payload": payload}
        self._stdin.write(json.dumps(request) + "\n")
        self._stdin.flush()

        response_line = self._stdout.readline()
        if not response_line:
            raise RuntimeError("Helper terminated unexpectedly")

        response = json.loads(response_line)
        if not response.get("ok", False):
            raise RuntimeError(response.get("error", "Helper error"))
        return response.get("result")

    def screenGeometry_get(self) -> tuple[int, int]:
        """
        Return screen geometry from helper.
        
        Args:
            None.
        
        Returns:
            Screen geometry.
        """
        """Return screen geometry from helper."""
        result = self._request("screen_geometry_get", {})
        return int(result["width"]), int(result["height"])

    def pointerPosition_get(self) -> tuple[int, int]:
        """
        Return pointer position from helper.
        
        Args:
            None.
        
        Returns:
            Pointer position.
        """
        """Return pointer position from helper."""
        result = self._request("pointer_position_get", {})
        return int(result["x"]), int(result["y"])

    def cursorPosition_set(self, x: int, y: int) -> None:
        """
        Set cursor position via helper.
        
        Args:
            x: x value.
            y: y value.
        
        Returns:
            Result value.
        """
        """Set cursor position via helper."""
        self._request("cursor_position_set", {"x": x, "y": y})

    def pointer_grab(self) -> None:
        """
        Grab pointer via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab pointer via helper."""
        self._request("pointer_grab", {})

    def pointer_ungrab(self) -> None:
        """
        Release pointer grab via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release pointer grab via helper."""
        self._request("pointer_ungrab", {})

    def keyboard_grab(self) -> None:
        """
        Grab keyboard via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab keyboard via helper."""
        self._request("keyboard_grab", {})

    def keyboard_ungrab(self) -> None:
        """
        Release keyboard grab via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release keyboard grab via helper."""
        self._request("keyboard_ungrab", {})

    def cursor_hide(self) -> None:
        """
        Hide cursor via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Hide cursor via helper."""
        self._request("cursor_hide", {})

    def cursor_show(self) -> None:
        """
        Show cursor via helper.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Show cursor via helper."""
        self._request("cursor_show", {})

    def inputEvents_read(self) -> tuple[list[dict[str, Any]], int]:
        """
        Return pending input events and modifier state from helper.
        
        Args:
            None.
        
        Returns:
            Tuple of input events and modifier state.
        """
        """Return pending input events and modifier state from helper."""
        result = self._request("input_events_read", {})
        events = result.get("events", [])
        modifier_state = int(result.get("modifier_state", 0))
        return events, modifier_state

    def mouseEvent_inject(self, payload: dict[str, Any]) -> None:
        """
        Inject mouse event via helper.
        
        Args:
            payload: payload value.
        
        Returns:
            Result value.
        """
        """Inject mouse event via helper."""
        self._request("inject_mouse", payload)

    def keyEvent_inject(self, payload: dict[str, Any]) -> None:
        """
        Inject key event via helper.
        
        Args:
            payload: payload value.
        
        Returns:
            Result value.
        """
        """Inject key event via helper."""
        self._request("inject_key", payload)

    def session_isNative_check(self) -> bool:
        """
        Return True if helper reports native session.
        
        Args:
            None.
        
        Returns:
            True if session is native.
        """
        """Return True if helper reports native session."""
        result = self._request("session_is_native", {})
        return bool(result.get("native", False))

    def connection_sync(self) -> None:
        """
        Synchronize helper state.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Synchronize helper state."""
        self._request("sync", {})
