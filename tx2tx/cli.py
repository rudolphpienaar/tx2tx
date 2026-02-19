"""tx2tx unified command-line interface"""

import argparse
import sys
from typing import NoReturn

from tx2tx import __version__


def arguments_parse() -> argparse.Namespace:
    """
    Parse command line arguments
    
    Args:
        None.
    
    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        prog="tx2tx",
        description="Share mouse/keyboard across networked X11 and Wayland backends",
    )

    parser.add_argument("--version", action="version", version=f"tx2tx {__version__}")

    # Mode selection: --server means client mode (connect to server)
    # No --server means run as server
    parser.add_argument(
        "--server",
        type=str,
        metavar="HOST:PORT",
        default=None,
        help="Connect to server at HOST:PORT (client mode). If omitted, run as server.",
    )

    # Common options
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: search standard locations)",
    )

    parser.add_argument(
        "--display", type=str, default=None, help="X11 display name (overrides config)"
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
        "--wayland-calibrate",
        action="store_true",
        help="Wayland: warp cursor to center on startup to sync helper state.",
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
        "--wayland-pointer-provider",
        type=str,
        choices=["helper", "gnome"],
        default=None,
        help="Wayland pointer coordinate provider (server mode; default: helper).",
    )

    # Server-specific options
    parser.add_argument(
        "--host", type=str, default=None, help="[Server] Host address to bind to (overrides config)"
    )

    parser.add_argument(
        "--port", type=int, default=None, help="[Server] Port to listen on (overrides config)"
    )

    parser.add_argument(
        "--edge-threshold",
        type=int,
        default=None,
        dest="edge_threshold",
        help="[Server] Pixels from edge to trigger transition (overrides config)",
    )

    parser.add_argument(
        "--name", type=str, default=None, help="[Server] Server name for logging (overrides config)"
    )

    parser.add_argument(
        "--overlay",
        action="store_true",
        help="[Server] Enable fullscreen overlay window to hide cursor (Crostini workaround)",
    )

    parser.add_argument(
        "--x11native",
        action="store_true",
        help="[Server] Optimize for native X11 (disables Crostini workarounds, uses blank cursor)",
    )

    parser.add_argument(
        "--software-cursor",
        action="store_true",
        help="[Client] Enable software rendered cursor (useful if hardware cursor is invisible)",
    )

    parser.add_argument(
        "--client", type=str, default=None, help="[Client] Client name from config (e.g., 'phomux')"
    )

    parser.add_argument(
        "--die-on-disconnect",
        action="store_true",
        help="[Server] Exit server immediately if a client disconnects",
    )

    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging (overrides config)"
    )

    parser.add_argument(
        "--info", action="store_true", help="Enable info logging (overrides config)"
    )

    parser.add_argument(
        "--warning", action="store_true", help="Enable warning logging (overrides config)"
    )

    parser.add_argument(
        "--error", action="store_true", help="Enable error logging (overrides config)"
    )

    parser.add_argument(
        "--critical", action="store_true", help="Enable critical logging (overrides config)"
    )

    return parser.parse_args()


def main() -> NoReturn:
    """
    Main entry point for unified tx2tx command
    
    Args:
        None.
    
    Returns:
        Result value.
    """
    """Main entry point for unified tx2tx command"""
    args = arguments_parse()

    log_level_override: str | None = logLevelOverride_get(args)

    try:
        argsWithLogLevel_apply(args, log_level_override)
        if clientMode_isEnabled(args):
            clientMode_run(args)
        else:
            serverMode_run(args)
        # Both client_run and server_run are NoReturn, so this is unreachable
        # But we need explicit exit for mypy
        sys.exit(0)

    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def logLevelOverride_get(args: argparse.Namespace) -> str | None:
    """
    Resolve explicit log level override flags.

    Args:
        args: Parsed CLI args.

    Returns:
        Selected log level or None.
    """
    if args.critical:
        return "CRITICAL"
    if args.error:
        return "ERROR"
    if args.warning:
        return "WARNING"
    if args.info:
        return "INFO"
    if args.debug:
        return "DEBUG"
    return None


def argsWithLogLevel_apply(args: argparse.Namespace, log_level: str | None) -> None:
    """
    Apply optional log level override to args.

    Args:
        args: Parsed CLI args.
        log_level: Optional log level string.
    """
    if log_level is not None:
        setattr(args, "log_level", log_level)


def clientMode_isEnabled(args: argparse.Namespace) -> bool:
    """
    Determine whether CLI should run client mode.

    Args:
        args: Parsed CLI args.

    Returns:
        True when client mode should run.
    """
    return bool(args.server or args.client or args.software_cursor)


def clientMode_run(args: argparse.Namespace) -> None:
    """
    Run client mode entrypoint.

    Args:
        args: Parsed CLI args.
    """
    if args.client and not args.name:
        args.name = args.client

    from tx2tx.client.main import client_run

    client_run(args)


def serverMode_run(args: argparse.Namespace) -> None:
    """
    Run server mode entrypoint.

    Args:
        args: Parsed CLI args.
    """
    from tx2tx.server.main import server_run

    overlay_enabled: bool | None = True if args.overlay else None
    if args.x11native:
        setattr(args, "x11native", True)
        overlay_enabled = False
    else:
        setattr(args, "x11native", False)
    setattr(args, "overlay_enabled", overlay_enabled)
    server_run(args)


if __name__ == "__main__":
    main()
