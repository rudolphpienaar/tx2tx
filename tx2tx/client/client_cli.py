"""
Client CLI parsing and server-address validation policies.

This module contains only argument parsing and server address parsing logic
for the tx2tx client runtime.
"""

from __future__ import annotations

import argparse

from tx2tx import __version__

__all__ = ["arguments_parse", "serverAddress_parse"]


def arguments_parse() -> argparse.Namespace:
    """
    Parse client command-line arguments.

    Returns:
        Parsed client CLI namespace.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="tx2tx client - receives and injects input events"
    )

    parser.add_argument("--version", action="version", version=f"tx2tx {__version__}")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: search standard locations)",
    )
    parser.add_argument(
        "--server",
        type=str,
        default=None,
        help="Server address to connect to (overrides config, e.g., 192.168.1.100:24800)",
    )
    parser.add_argument(
        "--display",
        type=str,
        default=None,
        help="X11 display name (overrides config)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=None,
        help="Input backend to use (e.g., x11, wayland). Defaults to x11.",
    )
    parser.add_argument(
        "--wayland-helper",
        type=str,
        default=None,
        help="Wayland helper command for privileged input operations.",
    )
    parser.add_argument(
        "--wayland-start-x",
        type=int,
        default=None,
        help="Wayland initial cursor X override (pixels).",
    )
    parser.add_argument(
        "--wayland-start-y",
        type=int,
        default=None,
        help="Wayland initial cursor Y override (pixels).",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Client name for logging and identification (e.g., 'phomux')",
    )
    parser.add_argument(
        "--software-cursor",
        action="store_true",
        help="Enable software rendered cursor (useful if hardware cursor is invisible)",
    )

    return parser.parse_args()


def serverAddress_parse(server: str) -> tuple[str, int]:
    """
    Parse `host:port` server address string.

    Args:
        server:
            Server endpoint as `host:port`.

    Returns:
        Tuple of `(host, port)`.

    Raises:
        ValueError:
            Raised when address format is invalid.
    """
    if ":" not in server:
        raise ValueError("Server address must be in format host:port")

    host: str
    port_str: str
    host, port_str = server.rsplit(":", 1)
    try:
        port: int = int(port_str)
    except ValueError as exc:
        raise ValueError(f"Invalid port number: {port_str}") from exc

    return host, port
