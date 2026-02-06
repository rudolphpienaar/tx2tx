"""GNOME-specific pointer position provider for Wayland sessions."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess

logger = logging.getLogger(__name__)


class GnomePointerProvider:
    """Read pointer coordinates from GNOME Shell over D-Bus."""

    _METHOD = "org.gnome.Shell.Eval"
    _OBJECT_PATH = "/org/gnome/Shell"
    _DEST = "org.gnome.Shell"
    _JS = "JSON.stringify(global.get_pointer())"

    def __init__(self) -> None:
        self._warned = False

    def pointerPosition_get(self) -> tuple[int, int]:
        """
        Return current pointer coordinates from GNOME Shell.

        Returns:
            (x, y) pointer coordinates.

        Raises:
            RuntimeError if the command fails or output cannot be parsed.
        """
        command = [
            "gdbus",
            "call",
            "--session",
            "--dest",
            self._DEST,
            "--object-path",
            self._OBJECT_PATH,
            "--method",
            self._METHOD,
            self._JS,
        ]

        # When tx2tx is started as sudo, query GNOME as the original user.
        sudo_user = os.environ.get("SUDO_USER")
        if os.geteuid() == 0 and sudo_user:
            command = ["sudo", "-u", sudo_user] + command

        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "gdbus call failed")

        output = completed.stdout.strip()
        if not output:
            raise RuntimeError("gdbus returned empty output")

        try:
            return self._parse_coordinates(output)
        except Exception as exc:
            raise RuntimeError(f"unexpected gdbus output: {output}") from exc

    @staticmethod
    def _parse_coordinates(output: str) -> tuple[int, int]:
        """
        Parse gdbus Eval output and extract pointer x/y.

        GNOME Shell typically returns one of:
        - "(true, '[x,y,mods]')"
        - "(true, \"[x,y,mods]\")"
        """
        # First try to decode bracketed JSON payload.
        bracket_match = re.search(r"\[[^\]]+\]", output)
        if bracket_match:
            values = json.loads(bracket_match.group(0))
            if isinstance(values, list) and len(values) >= 2:
                return int(values[0]), int(values[1])

        # Fallback: parse first two integers found.
        numbers = re.findall(r"-?\d+", output)
        if len(numbers) >= 2:
            return int(numbers[0]), int(numbers[1])

        raise ValueError("no coordinates found")

    def fallback_log(self, error: Exception) -> None:
        """Log a one-time warning when falling back to helper coordinates."""
        if not self._warned:
            logger.warning("GNOME pointer provider unavailable, falling back to helper: %s", error)
            self._warned = True
