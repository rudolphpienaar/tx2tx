"""
Server CLI argument parser construction.

This module owns server-specific argument-parser definition so runtime policy
code remains focused on execution behavior rather than CLI schema setup.
"""

from __future__ import annotations

import argparse

from tx2tx import __version__

__all__ = [
    "arguments_parse",
    "parser_create",
    "coreArgs_populate",
    "waylandArgs_populate",
    "identityArgs_populate",
]


def arguments_parse() -> argparse.Namespace:
    """
    Parse server command-line arguments.

    Returns:
        Parsed argparse namespace for server startup.
    """
    parser: argparse.ArgumentParser = parser_create()
    return parser.parse_args()


def parser_create() -> argparse.ArgumentParser:
    """
    Create fully populated server argument parser.

    Returns:
        Configured argument parser.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="tx2tx server - captures and broadcasts input events"
    )
    parser.add_argument("--version", action="version", version=f"tx2tx {__version__}")
    coreArgs_populate(parser)
    waylandArgs_populate(parser)
    identityArgs_populate(parser)
    return parser


def coreArgs_populate(parser: argparse.ArgumentParser) -> None:
    """
    Populate backend-agnostic core server arguments.

    Args:
        parser: Target argument parser.
    """
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: search standard locations)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host address to bind to (overrides config)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on (overrides config)",
    )
    parser.add_argument(
        "--edge-threshold",
        type=int,
        default=None,
        dest="edge_threshold",
        help="Pixels from edge to trigger screen transition (overrides config)",
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


def waylandArgs_populate(parser: argparse.ArgumentParser) -> None:
    """
    Populate Wayland-specific server arguments.

    Args:
        parser: Target argument parser.
    """
    parser.add_argument(
        "--wayland-helper",
        type=str,
        default=None,
        help="Wayland helper command for privileged input operations.",
    )
    parser.add_argument(
        "--wayland-screen-width",
        type=int,
        default=None,
        help="Wayland screen width override (pixels).",
    )
    parser.add_argument(
        "--wayland-screen-height",
        type=int,
        default=None,
        help="Wayland screen height override (pixels).",
    )
    parser.add_argument(
        "--wayland-calibrate",
        action="store_true",
        help="Wayland: warp cursor to center on startup to sync helper state.",
    )
    parser.add_argument(
        "--wayland-pointer-provider",
        type=str,
        choices=["helper", "gnome"],
        default=None,
        help="Wayland pointer coordinate provider (default: helper).",
    )


def identityArgs_populate(parser: argparse.ArgumentParser) -> None:
    """
    Populate identity and naming arguments.

    Args:
        parser: Target argument parser.
    """
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Server name for logging and identification (default: from config)",
    )
